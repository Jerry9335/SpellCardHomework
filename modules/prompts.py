import re
"""提示词：题目提取（视觉 OCR）、中文翻译、作答。"""

OCR_SYSTEM = """你是一个精准的“题目提取器”。用户会给你一张屏幕截图，截图里是某道练习题。

你的任务：只把【题目本身】原样抄录下来，不要解题、不要翻译。

需要抄录：
- 题干与问句
- 公式、表达式、数学符号
- 所有选项（A/B/C/D...）
- 填空处的空位
- 与题目直接相关的表格数据、图形/坐标轴说明

必须忽略（这些是软件界面，不是题目）：
- 浏览器地址栏、标签页、书签栏、课程名/用户信息
- 题号导航列表（Question 1 ~ Question N）、侧边栏、滚动条
- 得分、时间、页码、进度、提示气泡
- 按钮与帮助链接（Save、Clear all、Check answer、Help me solve this、View an example 等）

格式要求：
1. 数学公式一律用 LaTeX，行内用 $...$ 包裹；保留上下标、根号、分数、不等号、绝对值、区间。
2. 选项每个占一行，以 “A. ” “B. ” 开头，选项里的公式照样用 LaTeX。
3. 填空题的空位写成 ____ 。
4. 图中若出现多道题，只提取正在作答的那一道（通常是主内容区、带选项的那道）。
5. 直接输出题目文字。不要前言、不要“以下是提取结果”、不要代码块围栏。
6. 反斜杠不能省：写 $\\sqrt{x}$、$\\frac{1}{2}$、$x \\le 3$，不要写 sqrt{x}、frac{1}{2}、xle 3。"""


def ocr_messages(image_data_url: str, extra_hint: str = "") -> list[dict]:
    hint = "请提取这张截图里的题目。" + (f"（补充说明：{extra_hint}）" if extra_hint else "")
    return [
        {"role": "system", "content": OCR_SYSTEM},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": hint},
                {"type": "image_url", "image_url": {"url": image_data_url, "detail": "high"}},
            ],
        },
    ]


TRANSLATE_SYSTEM = """把下面这道题目完整翻译成简体中文。

要求：
1. 题干、问句、选项都要翻译，保持原有结构与顺序。
2. 公式与数学符号原样保留，不要翻译、不要改写 LaTeX。
3. 选项编号（A. B. C.）保留。
4. 填空处的 ____ 保留。
5. 公式保持 $...$ 包裹与反斜杠原样，例如 $\\sqrt{3}$、$x \\le 3$，不要写成 sqrt{3}、xle 3。
6. 只输出译文，不要任何解释、不要代码块围栏。"""


def translate_messages(question_text: str) -> list[dict]:
    return [
        {"role": "system", "content": TRANSLATE_SYSTEM},
        {"role": "user", "content": question_text},
    ]


ANSWER_SYSTEM = """你是严谨的解题助手。用户会给你一道题（可能来自 OCR，可能有少量识别错误）。
请严格按以下格式输出，不要寒暄、不要重复题目：

【答案】<选择题：字母 + 正确选项内容；填空题：要填的内容；多选题：全部字母>
【解析】<2~5 句中文，讲清关键步骤或依据>

格式要求（重要）：所有数学式子都必须写成 LaTeX 并用 $...$ 包起来，命令必须带反斜杠。
例如：$\\sqrt{3}$、$\\frac{1}{2}$、$x \\le 3$、$x \\ge 3$、$(3,+\\infty)$、$\\theta \\in [0,\\pi]$。
禁止写 sqrt{3}、frac{1}{2}、xge 3、+infty 这种没有反斜杠的伪 LaTeX。

规则：
1. 先把题目理解正确。如果题目信息明显残缺（缺图形、缺条件、缺选项），在【答案】里写「信息不足：<缺什么>」，然后按最合理的假设给出解法。
2. 选择题要逐一核对选项，不要因个别符号看不清就乱选；不确定时给出你的概率判断。
3. 数学与计算题请自行验算，确保结果满足题设条件（例如定义域、取值范围）。
4. 若题干来自 OCR，请结合上下文修正明显识别错误（如 x2→x²、rn→m、0→O、l→1 等）。"""


def answer_messages(question_text: str, from_ocr: bool = True, translated: str = "") -> list[dict]:
    note = ""
    if from_ocr:
        note = "\n\n（说明：以上文字来自 OCR 识别，可能有错字或公式丢失，请自行纠正后再作答。）"
    if translated:
        note += "\n\n（参考译文：\n" + translated + "\n）"
    return [
        {"role": "system", "content": ANSWER_SYSTEM},
        {"role": "user", "content": question_text + note},
    ]


# ---------------------------------------------------------------- 网页模式
WEB_PROMPT = (
    "你在帮我做 Pearson 的数学作业。下面是题目的纯文本（公式可能被拍平成一行，"
    "矩阵会写成 1st Row 1st Column … 这种）。\n"
    "只输出下面四行，不要解释、不要复述题目：\n"
    "CHOICE: <单选题写一个字母；多选题写全部正确字母，用逗号分隔，如 A,C；否则写 ->\n"
    "MATRIX: <如果答案要填一个矩阵，写 行x列: 值1, 值2, …（行优先，每格用 a/b 形式的分数）；否则写 ->\n"
    "DROPDOWN: <如果题目有下拉框，按顺序写每个下拉框要选的选项编号，用 ; 分隔；没有下拉框就写 ->\n"
    "VALUE: <只写要填进输入框的内容，不要写 x= / y=，不要带单位、解释或句号；只有一个空就写这个值（分数写成 a/b）；有两个空就用分号分隔写 值1 ; 值2；否则写 ->\n"
    # 多空题最稳的是「逐空位」写法（学自《作业侠客》的 FIELDn 协议）：
    # 位置型 VALUE 在 2 个空时经常只回来一个值，被当成没答出来反复重采。
    "另外：如果空位清单里有**多个空**，请改用逐空位写法，每行一个——\n"
    "  FIELD1: 第 1 个空的值\n"
    "  FIELD2: 第 2 个空的值\n"
    "（顺序就是空位清单的顺序；这种情况下 VALUE 行可以省略）\n"
    "矩阵元素不要乘开标量倍数，也不要因式分解。\n"
    "如果题目写了 Do not simplify / Do not evaluate / 不化简，就保留未化简的式子或分数"
    "（例如 5/10，不要写成 1/2）。\n"
    "对数底数必须写成 log_7(5) 这种带下划线的形式；不要写 log7(5)，"
    "否则编辑器会把它当成 log × 7，Check 会判错。\n"
    "计算题先在草稿里代入算一遍，确认数值正确再输出；不确定就写 ->。\n"
    "如果题目里带【图注】或坐标轴描述（例如 A coordinate system has ...），以这段文字为准来判断图形，不要只靠数像素。\n"
    "分段函数只回答当前小问对应分支的表达式，不要写 if 条件、不要分段。"
)


def web_messages(question_text: str) -> list[dict]:
    return [{"role": "user", "content": WEB_PROMPT + "\n\n题目：\n" + question_text}]


def web_messages_image(question_text: str, data_url: str) -> list[dict]:
    """题目带图（函数图像、几何图）时，把截图一起交给视觉模型。"""
    return [{
        "role": "user",
        "content": [
            {"type": "text", "text": WEB_PROMPT + "\n\n题目（文字）：\n" + question_text
                                     + "\n\n（下面是题目的截图，图里的图表/图像信息以截图为准。）"},
            {"type": "image_url", "image_url": {"url": data_url, "detail": "high"}},
        ],
    }]


def _spec_empty(body: str) -> bool:
    """模型用 - / — / -> 表示「这一项没有」。"""
    return body.replace(" ", "").replace("＞", ">") in ("", "-", "—", "–", "->", "→", "none", "null")


_ALLOWED_CHOICES = set("ABCDEFGH")
_PROTOCOL_STOP = re.compile(r"\b(?:VALUE|MATRIX|DROPDOWN)\b", re.I)


def _parse_letters(body: str) -> list[str]:
    """慧音：从 CHOICE 内容里解析选项字母，规矩要讲清楚。

    - "A, C" / "A and C" / "A、C" -> ['A', 'C']（显式分隔）
    - "AC"（全大写、按字母序、无重复）-> ['A', 'C']（紧凑写法）
    - "none of these" -> []（不能被当成 N,O,N,E）
    - "B because BE is correct" 里的 BE 不会再被拆成 B,E
    - 遇到 VALUE/MATRIX/DROPDOWN 关键字立即截断本行
    """
    text = _PROTOCOL_STOP.split(body or "", maxsplit=1)[0].strip()
    if not text:
        return []
    # 紧凑写法：整行必须只有大写 A-H，且按字母序、无重复；单词会被挡下。
    core = text.strip("`*# \t")
    core = re.sub(r"^[\s\(\[\{]+|[\s\)\]\}]+$", "", core)
    core = core.strip("`*# \t.,;:!?，。、；：")
    if (re.fullmatch(r"[A-H]{2,8}", core)
            and len(set(core)) == len(core)
            and core == "".join(sorted(core))):
        return list(core)

    out: list[str] = []
    for token in re.split(r"[\s,;、/|]+|\band\b", text, flags=re.I):
        token = token.strip(".:()[]{}<>，。、；：!?！？'\"`*# ").upper()
        if len(token) == 1 and token in _ALLOWED_CHOICES and token not in out:
            out.append(token)
    return sorted(out, key=lambda x: "ABCDEFGH".index(x)) if out else []


def _parse_dropdown_nums(body: str) -> list[int]:
    """解析 DROPDOWN 的编号。

    - "1; 2"    -> [1, 2]
    - "1) 3"    -> [3]     （"1)" 只是编号标签）
    - "1、2、3" -> [1, 2, 3]
    """
    nums: list[int] = []
    for seg in re.split(r"[;；,，、]+", body or ""):
        seg = seg.strip()
        if not seg:
            continue
        seg = re.sub(r"^\s*\d+\s*[).、:：]\s*", "", seg)
        m = re.search(r"\d+", seg)
        if m:
            nums.append(int(m.group(0)))
    return nums


def parse_web_answer(raw: str) -> dict:
    """把模型的三行回答解析成 {choice, matrix, value, raw}。"""
    import re

    # 兜底解析时允许出现的多字母词（真答案里只可能有这些函数名）
    _FUNC_WORDS = {
        "log", "ln", "sin", "cos", "tan", "sec", "csc", "cot", "sinh", "cosh",
        "tanh", "arcsin", "arccos", "arctan", "lim", "max", "min", "sqrt",
        "det", "gcd", "lcm", "exp", "inf", "int", "abs",
    }

    # 中文模型经常输出全角标点：CHOICE：B / VALUE：42；这里先统一成半角。
    # 只影响解析，保留原文到 out["raw"] 方便排查。
    text = (raw or "").translate(str.maketrans({
        "：": ":", "；": ";", "，": ",", "＝": "=", "　": " ",
    }))
    out = {"choice": "", "choices": [], "matrix": None, "value": "", "drops": [], "raw": (raw or "").strip()}
    for line in text.splitlines():
        line = line.strip().strip("`*# ").strip()
        if not line:
            continue
        head, _, body = line.partition(":")
        head = re.sub(r"^[\s*`#_]+|[\s*`#_]+$", "", head).strip().upper()
        body = body.strip()
        if re.match(r"^(FIELD|SELECT)\s*\d+$", head) or head == "GRAPH":
            pass                     # 逐空位协议（《作业侠客》的格式），下面单独处理
        elif head not in ("CHOICE", "MATRIX", "DROPDOWN", "VALUE"):
            # 容忍 "CHOICE B"、"**CHOICE**: A"、"CHOICE = B" 这类没冒号/带格式的写法
            m = re.match(r"^(CHOICE|MATRIX|DROPDOWN|VALUE)\b[\s:：=\-]*(.*)$", line, re.I)
            if not m:
                continue
            head, body = m.group(1).upper(), m.group(2).strip()
        if head == "DROPDOWN":
            out["drops"] = _parse_dropdown_nums(body)
            continue

        if head == "CHOICE":
            if _spec_empty(body):
                out["choice"] = ""
                out["choices"] = []
            else:
                # 只认 A-H 的独立选项；"A and C" 不能被拆成 A,N,D,C
                letters = _parse_letters(body)
                out["choice"] = letters[0] if letters else ""
                out["choices"] = letters
        elif head == "MATRIX" and not _spec_empty(body):
            m = re.match(r"(\d+)\s*[x×*]\s*(\d+)\s*[:：]\s*(.+)", body)
            if m:
                vals = [v.strip() for v in re.split(r"[,，;；]", m.group(3)) if v.strip()]
                out["matrix"] = (int(m.group(1)), int(m.group(2)), vals)
        elif head == "VALUE":
            # 多空题模型常常写**多行** `VALUE:`；旧代码后一行覆盖前一行，
            # 于是「2 个空只解析出 1 个值」，被判「没交出可用答案」反复重采。
            # （2026-11-28 B5-10.5 Q4 实测）
            # 注意：VALUE 的 none/null 是合法数学答案（无实根/无交点），
            # 不能像协议占位符那样丢掉；只把 - / -> 之类当“没填”。
            _body_low = str(body or "").strip().lower()
            _empty = _spec_empty(body) and _body_low not in ("none", "null")
            if not _empty:
                out.setdefault("_vals", []).append(body)
        elif re.match(r"^FIELD\s*\d+$", head):
            # 《作业侠客》的逐空位协议：FIELD1: … / FIELD2: …，比位置型 VALUE 稳得多
            idx = int(re.sub(r"^FIELD\s*", "", head)) - 1
            if idx >= 0:
                out.setdefault("_slots", {})[idx] = "" if _spec_empty(body) else body
        elif re.match(r"^SELECT\s*\d+$", head):
            idx = int(re.sub(r"^SELECT\s*", "", head)) - 1
            if idx >= 0:
                out.setdefault("_sels", {})[idx] = "" if _spec_empty(body) else body
    _slots = out.pop("_slots", {}) or {}
    _sels = out.pop("_sels", {}) or {}
    _vals = out.pop("_vals", []) or []
    if _slots:
        n = max(_slots) + 1
        out["values"] = [_slots.get(i, "") for i in range(n)]
    else:
        # 多行 VALUE: 与单行 `VALUE: a; b` 都支持；旧代码后一行覆盖前一行，
        # 「2 个空只解析出 1 个值」→ 被判没交出答案反复重采（2026-11-28 实测）。
        joined = ";".join(_vals)
        vals = [x.strip() for x in re.split(r"[;；]", joined) if x.strip()]
        if not vals and out.get("value"):
            vals = [str(out["value"]).strip()]
        out["values"] = vals
    out["sel_values"] = ([_sels.get(i, "") for i in range(max(_sels) + 1)]
                         if _sels else [])
    out["value"] = out["values"][0] if out["values"] else ""

    # 兜底：模型没写 CHOICE:/VALUE: 前缀，只把答案丢过来。
    # 帕秋莉：有些式神不爱按格式说话，只把结果递过来 —— 只要它短得像答案，就收下。
    # （2026-11-28：13 小问的长题里，式神经常直接回一个数字，被当成「没给答案」
    #   重采三轮，最后整题跳过。）
    if not any((out["choices"], out["matrix"], out["drops"], out["values"])):
        bare = re.sub(r"^[`*\s]+|[`*\s]+$", "", (raw or "").strip())
        bare = bare.strip().rstrip("。.;；")
        if re.fullmatch(r"[A-Ha-h]", bare):
            out["choice"] = bare.upper()
            out["choices"] = [bare.upper()]
        elif (0 < len(bare) <= 24
              and re.fullmatch(r"[-+0-9A-Za-z_.,/^()\[\]{}=√∞π≤≥<> ]+", bare)
              and re.search(r"[0-9]", bare)
              and len(bare.split()) <= 2
              # 不能是英文句子：真答案里允许出现的多字母词只有这些函数名
              and all(w.lower() in _FUNC_WORDS
                      for w in re.findall(r"[A-Za-z]{3,}", bare))):
            out["value"] = bare
            out["values"] = [bare]
    return out


# 学自《作业侠客》hwai.py 的 VERIFY_PROMPT：
# 交卷前让模型把已填的答案复核一遍 —— 这是它「很少交错」的关键一步。
VERIFY_PROMPT = (
    "你在帮我核对 Pearson 作业页面上已经填好的答案。下面给你题目文本和「当前已填」。\n"
    "先自己把题重算一遍，再和已填的答案逐项比对。\n"
    "**「当前已填」是页面的朗读式文字，必须先翻译成数学再看**：\n"
    "  · StartFraction 3 Over 4 EndFraction = 3/4；Superscript 4 = ^4；Subscript 6 = _6\n"
    "  · log Subscript 6 Baseline p = log₆(p)；left parenthesis = (；right parenthesis = )\n"
    "  · negative 2.5 = -2.5；plus = +；minus = −\n"
    "**只要数学含义一样就算对**：写法、空格、括号、项的先后顺序不同都不算错\n"
    "（例：`1 + log6(p) − log6(7) − log6(k)` 与 `log6(p)-log6(7)-log6(k)+1` 是同一个答案）。\n"
    "只有真的算错、符号错、漏项才判 WRONG。\n"
    "只输出一行，不要解释、不要复述题目：\n"
    "VERDICT: OK\n"
    "或者\n"
    "VERDICT: WRONG: 第几个空应该填什么（一句话，例：第2空应该是 3/4）"
)


def parse_verify(raw: str):
    """解析复核结果：("ok", "") / ("wrong", 说明) / (None, "")。

    (None, "") 表示模型没按格式回 —— 调用方应当停下，别硬交。
    """
    for line in (raw or "").splitlines():
        line = line.strip()
        if not line.upper().startswith("VERDICT"):
            continue
        body = line.split(":", 1)[1].strip() if ":" in line else ""
        if body.upper().startswith("OK"):
            return ("ok", "")
        if body.upper().startswith("WRONG"):
            why = body.split(":", 1)[1].strip() if ":" in body else body
            return ("wrong", why[:120] or "模型认为已填的答案不对")
        return (None, "")
    return (None, "")
