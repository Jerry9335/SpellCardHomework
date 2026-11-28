"""多路求解引擎：独立采样 → 投票 → 交叉审核 → 本地验算 → 置信度。

设计目标与 screen-qa 的 solver 相同：不让单个模型的随机错误直接决定答案。
与 Pearson 页面交互完全解耦——本模块只接收 QuestionPacket 和 ask 回调。
"""
from __future__ import annotations

import re
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

from modules import answer_format, prompts
from modules.verify_math import (canonical_value, extract_functions,
                                 verify_candidate, verify_graph_objects)


class SolveError(RuntimeError):
    """求解失败（不是“答错”，而是没有得到可用答案）。"""


class SolveCancelled(RuntimeError):
    pass


class SolveResult:
    def __init__(self, spec: dict, confidence: str, agreement: float,
                 verified: str, detail: str, candidates: list[dict],
                 review: dict | None = None, trace: list[str] | None = None):
        self.spec = spec
        self.confidence = confidence
        self.agreement = agreement
        self.verified = verified
        self.detail = detail
        self.candidates = candidates
        self.review = review
        self.trace = trace or []

    @property
    def ok(self) -> bool:
        return bool(self.spec)

    def summary(self) -> str:
        return (f"{self.confidence}（一致度 {self.agreement:.0%}，"
                f"验算 {self.verified}：{self.detail}）")


def _has_answer(spec: dict) -> bool:
    return bool(spec.get("choices") or spec.get("value") or spec.get("values")
                or spec.get("matrix") or spec.get("drops"))


def _spec_key(spec: dict) -> str:
    """归一化投票 key；不同表达但同值的答案应投到同一票。"""
    parts = []
    choices = spec.get("choices") or ([] if not spec.get("choice")
                                      else [spec["choice"]])
    if choices:
        parts.append("C:" + ",".join(sorted(str(x).upper() for x in choices)))
    matrix = spec.get("matrix")
    if matrix:
        rows, cols, cells = matrix
        parts.append("M:%d,%d:%s" % (
            int(rows), int(cols), ",".join(canonical_value(x) for x in cells)))
    drops = spec.get("drops") or []
    if drops:
        parts.append("D:" + ",".join(str(int(x)) for x in drops if str(x).isdigit()))
    values = spec.get("values") or ([] if not spec.get("value")
                                    else [spec["value"]])
    if values:
        parts.append("V:" + "|".join(canonical_value(x) for x in values))
    return ";".join(parts)


def _spec_text(spec: dict) -> str:
    parts = []
    choices = spec.get("choices") or []
    if choices:
        parts.append("CHOICE: " + ",".join(choices))
    if spec.get("matrix"):
        r, c, cells = spec["matrix"]
        parts.append("MATRIX: %dx%d: %s" % (r, c, ", ".join(str(x) for x in cells)))
    if spec.get("drops"):
        parts.append("DROPDOWN: " + ";".join(str(x) for x in spec["drops"]))
    values = spec.get("values") or ([] if not spec.get("value") else [spec["value"]])
    if values:
        parts.append("VALUE: " + "; ".join(str(x) for x in values))
    return "\n".join(parts) or "（式神这次没交出答案）"


def _control_hint(packet: dict) -> str:
    lines = []
    fields = (packet.get("fields") or []) + (packet.get("inputs") or [])
    if fields:
        lines.append("填空框按页面顺序如下（VALUE 必须按同样顺序，多个用分号）：")
        for i, f in enumerate(fields):
            lines.append(f"{i + 1}. {f.get('label') or '(无标签)'}")
    if packet.get("radios") or packet.get("checks"):
        lines.append("选项为页面顺序的 A/B/C…，多选把所有正确字母写全。")
    if packet.get("dropdowns"):
        lines.append("下拉框按页面顺序写编号，多个用分号。")
    if packet.get("graph"):
        _low = str(packet.get("text") or "").lower()
        # “从图里读极限/读数”不是“用工具画图”。旧提示一律说“画图由程序完成”，
        # 会把读图题误导成只答文字；只有明确要求画图时才提示程序代画。
        _drawing = bool(re.search(
            r"\bgraph\s+(?:the|both|f\b|y\b|equation|function)|"
            r"use the graphing tool|draw the graph|sketch the graph", _low))
        if not _drawing:
            lines.append("题目带有坐标图/图形；请根据题干里的图注、坐标和文字描述判断，"
                         "不要输出画图协议。")
        elif fields or packet.get("radios") or packet.get("checks") or packet.get("dropdowns"):
            lines.append("这道题包含图形工具，画图由程序完成；你只需要回答本小问的文字/填空部分，"
                         "VALUE 按页面填空框顺序给出。")
        else:
            lines.append("这道题只要求画图，不要输出 VALUE。")
    return "\n".join(lines)


class AnswerEngine:
    def __init__(self, ask, *, samples: int = 3, escalate: int = 2,
                 review: bool = True, reasoner: bool = True,
                 on_status=None, cancel: threading.Event | None = None):
        """
        ask(messages, temperature, tag) -> str
            调用一次模型；tag 可能是 "sample" / "review" / "reasoner"。
        """
        self.ask = ask
        self.samples = max(1, int(samples))
        self.escalate = max(0, int(escalate))
        self.review = bool(review)
        self.reasoner = bool(reasoner)
        self.on_status = on_status
        self.cancel = cancel or threading.Event()
        self._lock = threading.Lock()

    def _status(self, text: str) -> None:
        if not self.on_status:
            return
        try:
            self.on_status(text)
        except Exception:
            pass

    def _check_cancel(self) -> None:
        if self.cancel.is_set():
            raise SolveCancelled("咲夜：时间到了，先停手。")

    def _messages(self, packet: dict, extra: str = "") -> list[dict]:
        text = str(packet.get("text") or "")
        hint = _control_hint(packet)
        body = text
        if hint:
            body += "\n\n" + hint
        if extra:
            body += "\n\n" + extra
        return prompts.web_messages(body)

    def _ask_raw(self, messages, temperature: float, tag: str) -> str:
        self._check_cancel()
        raw = self.ask(messages, temperature, tag)
        if self.cancel.is_set():
            raise SolveCancelled("咲夜：时间到了，先停手。")
        return str(raw or "")

    def _parse_one(self, packet: dict, raw: str) -> dict | None:
        """慧音：一份答案卷先看格式，缺控件/空答案都不算数。"""
        spec = prompts.parse_web_answer(raw)
        if not _has_answer(spec):
            return None
        status, _detail = verify_candidate(packet, spec)
        if status == "fail" and "没有" in _detail and "答案" in _detail:
            # 缺控件属于格式错误，不作为候选
            return None
        return spec

    def _parse_samples(self, packet: dict, raws: list[str]) -> list[dict]:
        out = []
        for raw in raws:
            spec = self._parse_one(packet, raw)
            if spec is not None:
                out.append(spec)
        return out

    def _run_samples(self, packet: dict, n: int) -> tuple[list[dict], list[str]]:
        """魔理沙：一次叫 n 路式神；没回话或答案不成形的再催，最多催两轮。"""
        if n <= 0:
            return [], []
        specs: list[dict] = []
        errors: list[str] = []
        msgs = self._messages(
            packet,
            "这是独立作答。请先自己在草稿里算一遍，再只输出 CHOICE / MATRIX / DROPDOWN / VALUE 四行；"
            "不要参考其他答案。"
        )
        self._status(f"灵梦：独立求解 {n} 路，正在采样…")
        attempt = 0
        while len(specs) < n and attempt < 3:  # 初采 + 最多 2 轮补采
            need = n - len(specs)
            if attempt:
                self._status(
                    f"魔理沙：还有 {need} 路式神没交出可用答案，再催一轮…（{attempt}/2）")
            with ThreadPoolExecutor(max_workers=max(1, need)) as pool:
                futs = {pool.submit(self._ask_raw, msgs, 0.7, "sample"): i
                        for i in range(need)}
                for fut in as_completed(futs):
                    try:
                        raw = fut.result()
                    except SolveCancelled:
                        raise
                    except Exception as e:
                        errors.append(str(e))
                        continue
                    spec = self._parse_one(packet, raw)
                    if spec is None:
                        _raw_show = " ".join(str(raw or "").split())[:180]
                        errors.append("答案格式没读懂：" + (_raw_show or "<空回复>"))
                    else:
                        specs.append(spec)
                        if len(specs) < n:
                            # 让用户看到“还在收答案”，而不是盯着一句“正在采样”
                            # 几十秒以为程序卡死了。
                            self._status(
                                f"灵梦：已收回 {len(specs)}/{n} 路可用答案，继续等…")
            attempt += 1
        return specs, errors

    @staticmethod
    def _is_tie(counter: Counter) -> bool:
        """咲夜：最高票不止一个，就是平票。"""
        if not counter:
            return False
        top = max(counter.values())
        return sum(1 for n in counter.values() if n == top) > 1

    def _tie_break(self, packet: dict, specs: list[dict],
                   counter: Counter) -> dict | None:
        """帕秋莉：平票先看验算；都没法验算就按 key 稳定排序，绝不靠到达顺序。"""
        if not counter:
            return None
        top = max(counter.values())
        keys = sorted(k for k, n in counter.items() if n == top)
        reps = {}
        for key in keys:
            for s in specs:
                if _spec_key(s) == key:
                    reps[key] = s
                    break
        for key in keys:
            spec = reps.get(key)
            if spec is None:
                continue
            try:
                if verify_candidate(packet, spec)[0] == "ok":
                    return spec
            except Exception:
                continue
        return reps.get(keys[0]) if keys else None

    def _vote(self, specs: list[dict], total: int | None = None
              ) -> tuple[dict | None, float, Counter]:
        keys = [_spec_key(s) for s in specs if _spec_key(s)]
        if not keys:
            return None, 0.0, Counter()
        counter = Counter(keys)
        best_key, best_n = counter.most_common(1)[0]
        denom = int(total) if total and int(total) > 0 else len(keys)
        # 分母是“请求样本数”（含失败），这样 1/3 有效不会被当成满票。
        denom = max(denom, len(keys))
        for s in specs:
            if _spec_key(s) == best_key:
                return s, min(1.0, best_n / denom), counter
        return None, 0.0, counter

    def _review_candidates(self, packet: dict, specs: list[dict]) -> dict | None:
        if not specs:
            return None
        cand = []
        seen = set()
        for s in specs:
            k = _spec_key(s)
            if not k or k in seen:
                continue
            seen.add(k)
            cand.append(_spec_text(s))
        body = ("慧音：下面是同一道题的多个候选答案。请你独立检查题目和每个候选，"
                "找出错误并给出最终正确答案。只输出 CHOICE / MATRIX / DROPDOWN / "
                "VALUE 四行，不要解释。\n\n候选：\n" + "\n\n".join(
                    f"[{i + 1}]\n{c}" for i, c in enumerate(cand)))
        try:
            raw = self._ask_raw(self._messages(packet, body), 0.3, "review")
        except SolveCancelled:
            raise
        except Exception:
            return None
        spec = prompts.parse_web_answer(raw)
        return spec if _has_answer(spec) else None

    def _reasoner_check(self, packet: dict, spec: dict) -> dict | None:
        body = ("灵梦：请复核这道题，尤其检查计算和符号。当前候选答案如下：\n"
                + _spec_text(spec)
                + "\n如果你认为有错，给出修正后的最终答案；如果正确，原样输出。"
                  "只输出 CHOICE / MATRIX / DROPDOWN / VALUE 四行。")
        try:
            raw = self._ask_raw(self._messages(packet, body), 0.2, "reasoner")
        except SolveCancelled:
            raise
        except Exception:
            return None
        out = prompts.parse_web_answer(raw)
        return out if _has_answer(out) else None

    def solve(self, packet: dict) -> SolveResult:
        """魔理沙：带着几路式神去退治；没人给出能用的答案就抛 SolveError。"""
        self._check_cancel()
        specs, errors = self._run_samples(packet, self.samples)
        if not specs:
            # 式神偶尔集体走神，追加一次再判失败
            self._status("魔理沙：第一轮居然全军覆没，再抓一路式神来问…")
            specs, errors2 = self._run_samples(packet, 1)
            errors += errors2
            if not specs:
                # 并发采样遇到 SSE 截断/网关抽风时，三路可能一起失败；
                # 最后用**单路串行、低温度**再问一次，别直接把整题判死。
                self._status("魔理沙：多路都被截断了，改成单路串行再试最后一次…")
                raw = ""
                try:
                    raw = self._ask_raw(self._messages(packet), 0.2, "fallback")
                    spec = self._parse_one(packet, raw)
                except SolveCancelled:
                    raise
                except Exception as exc:
                    spec = None
                    errors.append(str(exc))
                if spec is None:
                    _raw_show = " ".join(str(raw or "").split())[:220]
                    errors.append("单路兜底格式没读懂：" + (_raw_show or "<空回复>"))
                    self._status(
                        "魔理沙：单路兜底的回复也没读懂：" + (_raw_show[:160] or "<空回复>"))
                if spec:
                    specs = [spec]
                    # 单路兜底不再追加/审核/复核，避免再被并发流截断拖死
                    self.escalate = 0
                    self.review = False
                    self.reasoner = False
                else:
                    tail = f"（最后一句：{errors[-1]}）" if errors else ""
                    raise SolveError("魔理沙：式神们一个能用的答案都没吐出来……" + tail)

        best, agreement, counter = self._vote(specs, self.samples)
        if best is None:
            raise SolveError("魔理沙：答案写成一团乱麻，根本没法读……")
        tie = self._is_tie(counter)
        if tie:
            best = self._tie_break(packet, specs, counter)
            if best is None:
                raise SolveError("魔理沙：平票平得连个能站出来的答案都没有……")
        trace = [f"初采样 {len(specs)} 个有效答案，一致度 {agreement:.0%}"]
        if tie:
            trace.append("魔理沙：票数打平，先让帕秋莉验算，再按稳定顺序定一个")
        if errors:
            trace.append(
                f"魔理沙：有 {len(errors)} 路式神没给出可用答案（{str(errors[-1])[:80]}）")

        if (agreement < 1.0 or tie) and self.escalate:
            self._status(f"魔理沙：答案有分歧（一致度 {agreement:.0%}），追加 {self.escalate} 路…")
            more, errors3 = self._run_samples(packet, self.escalate)
            errors += errors3
            if errors3:
                trace.append(
                    f"魔理沙：追加采样又有 {len(errors3)} 路没给出可用答案"
                    f"（{str(errors3[-1])[:80]}）")
            if more:
                specs += more
                best, agreement, counter = self._vote(
                    specs, self.samples + self.escalate)
                tie = self._is_tie(counter)
                if tie:
                    best = self._tie_break(packet, specs, counter)
                    if best is None:
                        raise SolveError("魔理沙：追加之后还是平票，没个准话……")
                trace.append(f"追加后 {len(specs)} 个样本，一致度 {agreement:.0%}")

        def _verified(spec):
            return verify_candidate(packet, spec)

        v_best = _verified(best)
        # 帕秋莉：如果有其他候选能通过本地验算，而多数票没过，优先信验算。
        chosen = best
        if v_best[0] != "ok":
            seen = {_spec_key(best)}
            for s in specs:
                k = _spec_key(s)
                if k in seen:
                    continue
                seen.add(k)
                if _verified(s)[0] == "ok":
                    chosen = s
                    v_best = _verified(s)
                    trace.append("帕秋莉：多数票没过验算，换这个能代入的候选")
                    break

        review_spec = None
        review_conflict = False
        if self.review and (agreement < 1.0 or v_best[0] == "fail" or tie):
            self._status("慧音：交叉审核中…")
            review_spec = self._review_candidates(packet, specs)
            if review_spec:
                v_review = _verified(review_spec)
                if _spec_key(review_spec) != _spec_key(chosen):
                    review_conflict = True
                    # 慧音：只有审核答案过了验算，或多数票本来就没压倒性，才改判。
                    if v_review[0] == "ok" and v_best[0] != "ok":
                        chosen, v_best = review_spec, v_review
                        trace.append("慧音：审核答案过了验算，采用审核答案")
                    elif agreement <= 0.5 and v_best[0] != "ok" and v_review[0] != "fail":
                        chosen, v_best = review_spec, v_review
                        trace.append("慧音：票数没有压倒性，采用交叉审核答案")
                    else:
                        trace.append("慧音：审核与多数票不同，保留能通过验算的多数票")
                else:
                    trace.append("慧音：审核与多数票一致")

        # 只有投票/审核/验算仍有疑点时才追加一次复核，避免每题多花一次调用
        if self.reasoner and (v_best[0] == "fail" or agreement < 0.99
                              or review_conflict or tie):
            self._status("灵梦：答案还不确定，做最后一次复核…")
            r_spec = self._reasoner_check(packet, chosen)
            if r_spec:
                v_r = _verified(r_spec)
                if _spec_key(r_spec) != _spec_key(chosen):
                    if v_best[0] == "fail" and v_r[0] == "ok":
                        chosen, v_best = r_spec, v_r
                        trace.append("灵梦：复核答案过了验算，采用复核答案")
                    elif v_r[0] == "ok":
                        chosen, v_best = r_spec, v_r
                        trace.append("灵梦：复核给出一个能验算的新答案")
                    else:
                        trace.append("灵梦：复核与当前答案不同，但没法判定，保留当前答案")

        # 格式整理（验算用的是原始值；这里只整理最终提交格式）
        try:
            labels = [str(x.get("label") or "") for x in
                      (packet.get("fields") or []) + (packet.get("inputs") or [])]
            vals = chosen.get("values") or ([] if not chosen.get("value")
                                            else [chosen["value"]])
            if vals:
                formatted = answer_format.format_values(
                    vals, str(packet.get("text") or ""), labels)
                chosen["values"] = formatted
                chosen["value"] = formatted[0] if formatted else ""
        except Exception:
            pass

        if v_best[0] == "ok" and agreement >= 0.99:
            confidence = "high"
        elif v_best[0] == "ok":
            confidence = "medium"
        elif agreement >= 0.99:
            confidence = "medium"
        elif agreement >= 0.66:
            confidence = "medium"
        else:
            confidence = "doubt"
        if tie and v_best[0] != "ok":
            confidence = "doubt"  # 慧音：平票又没人验算得过，只能交给人里。

        trace.append(f"最终：{confidence}，验算 {v_best[0]}，{v_best[1]}")
        return SolveResult(chosen, confidence, agreement, v_best[0], v_best[1],
                           specs, review_spec, trace)


def verify_drawing(packet: dict, objects: list[dict]) -> tuple[str, str]:
    funcs = extract_functions(str(packet.get("text") or ""))
    return verify_graph_objects(objects, funcs)
