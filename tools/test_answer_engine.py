"""求解引擎/本地验算/格式整理/题目包 的离线回归测试。

这些测试不依赖浏览器和网络，跑得很快，适合每次改自动流程前先跑。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from modules import answer_engine, answer_format, prompts, question_reader, verify_math  # noqa: E402


def test_poly_and_functions():
    cases = {
        "y=-x^2+4": (-1.0, 0.0, 4.0),
        "y=x^2-4": (1.0, 0.0, -4.0),
        "y=x squared minus 4": (1.0, 0.0, -4.0),
        "-5x^2-20x-15": (-5.0, -20.0, -15.0),
        "x+18": (0.0, 1.0, 18.0),
        "3": (0.0, 0.0, 3.0),
        "y=-x^2+10x": (-1.0, 10.0, 0.0),
    }
    for expr, want in cases.items():
        got = verify_math.parse_poly(expr)
        assert got == want, (expr, got, want)

    funcs = verify_math.extract_functions(
        "Let C(x)=x+18 and R(x)=-x^2+10x. Graph both functions.")
    names = {f["name"]: f["poly"] for f in funcs}
    assert names.get("C") == (0.0, 1.0, 18.0), names
    assert names.get("R") == (-1.0, 10.0, 0.0), names
    print("poly/function parser OK")


def test_verify_candidate():
    packet = {
        "text": "Let C(x)=x+18 and R(x)=-x^2+10x. Identify the vertex of R(x). "
                "Identify the y-intercept of C(x).",
        "fields": [{"label": "The vertex of R(x) is at"},
                   {"label": "The y-intercept of C(x) is at y="}],
        "radios": [], "dropdowns": [], "inputs": [],
    }
    good = prompts.parse_web_answer("VALUE: (5,25); 18")
    assert verify_math.verify_candidate(packet, good)[0] == "ok"
    bad = prompts.parse_web_answer("VALUE: (5,20); 18")
    assert verify_math.verify_candidate(packet, bad)[0] == "fail"
    swapped = prompts.parse_web_answer("VALUE: 18; (5,25)")
    assert verify_math.verify_candidate(packet, swapped)[0] == "fail"
    assert answer_engine._spec_key(good) != answer_engine._spec_key(bad)
    assert "525" not in answer_engine._spec_key(good)
    print("verify candidate OK")


def test_graph_verify():
    text = "Let C(x)=x+18 and R(x)=-x^2+10x. Graph both functions."
    funcs = verify_math.extract_functions(text)
    objs = [
        {"objectType": "quadratic",
         "points": [{"x": 5, "y": 25}, {"x": 3, "y": 21}, {"x": 7, "y": 21}]},
        {"objectType": "line",
         "points": [{"x": 0, "y": 18}, {"x": 20, "y": 38}]},
    ]
    assert verify_math.verify_graph_objects(objs, funcs)[0] == "ok"
    bad = [{"objectType": "quadratic",
            "points": [{"x": 5, "y": 20}, {"x": 4, "y": 24}, {"x": 6, "y": 24}]}]
    assert verify_math.verify_graph_objects(bad, funcs)[0] == "fail"
    print("graph verify OK")


def test_engine():
    packet = {
        "text": "Let C(x)=x+18 and R(x)=-x^2+10x. Identify the vertex of R(x) "
                "and the y-intercept of C(x).",
        "fields": [{"label": "The vertex of R(x) is at"},
                   {"label": "The y-intercept of C(x) is at y="}],
        "radios": [], "dropdowns": [], "inputs": [],
    }
    replies = ["VALUE: (5,20); 18", "VALUE: (5,25); 18", "CHOICE: A", "VALUE: (5,25); 18"]
    state = {"n": 0}

    def ask(messages, temperature, tag):
        if tag == "sample":
            state["n"] += 1
            return replies[(state["n"] - 1) % len(replies)]
        return "VALUE: (5,25); 18"

    result = answer_engine.AnswerEngine(ask, samples=3, escalate=0).solve(packet)
    assert result.ok
    assert result.spec["values"] == ["(5,25)", "18"], result.spec
    assert result.verified == "ok", result.detail
    print("engine vote/verify OK")


def test_engine_all_bad():
    packet = {"text": "1+1", "fields": [{"label": "answer"}],
              "radios": [], "dropdowns": [], "inputs": []}

    def ask(messages, temperature, tag):
        return "VALUE: ->"

    try:
        answer_engine.AnswerEngine(ask, samples=1, escalate=0).solve(packet)
    except answer_engine.SolveError:
        print("engine all-bad OK")
        return
    raise AssertionError("all-bad should raise SolveError")


def test_format():
    fmt = answer_format.infer_format(
        "Identify the vertex. (Type an ordered pair. Simplify your answer.)",
        "The vertex of R(x) is at")
    assert fmt["kind"] == "ordered_pair"
    assert answer_format.format_value("(5, 25)", fmt) == "(5,25)"
    fmt2 = answer_format.infer_format("Write the answer as a percent.", "rate")
    assert fmt2["percent"] is True
    assert answer_format.format_value("0.25", fmt2) == "25"
    assert answer_format.format_value("25%", fmt2) == "25%"
    print("answer format OK")


def test_packet():
    st = {
        "text": "Solve x+1=2", "part": [2, 3], "qno": 7,
        "fields": [{"id": "f1", "label": "x="}], "inputs": [],
        "radios": [{"id": "r1", "label": "A. 1"}], "checks": [],
        "dropdowns": [], "selects": [], "graph": {},
    }
    pkt = question_reader.build_packet(st)
    assert pkt["qno"] == 7 and pkt["part_n"] == 2 and pkt["part_m"] == 3
    assert pkt["has_inputs"] and pkt["has_choices"]
    assert "第 2 小问" in pkt["text"]
    print("question packet OK")


def test_control_hint():
    graph_only = {"text": "Graph the parabola.", "graph": {"xmin": 0},
                  "fields": [], "inputs": [], "radios": [], "checks": [],
                  "dropdowns": []}
    hint = answer_engine._control_hint(graph_only)
    assert "不要输出 VALUE" in hint, hint

    graph_plus_fields = {"text": "Graph both and find the vertex.", "graph": {"xmin": 0},
                         "fields": [{"label": "vertex"}], "inputs": [],
                         "radios": [], "checks": [], "dropdowns": []}
    hint2 = answer_engine._control_hint(graph_plus_fields)
    assert "不要输出 VALUE" not in hint2, hint2
    assert "填空" in hint2, hint2
    print("control hint OK")


if __name__ == "__main__":
    test_poly_and_functions()
    test_verify_candidate()
    test_graph_verify()
    test_engine()
    test_engine_all_bad()
    test_format()
    test_packet()
    test_control_hint()
    print("RESULT: PASS")
