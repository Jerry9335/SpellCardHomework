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
    "只输出下面三行，不要解释、不要复述题目：\n"
    "CHOICE: <单选题写一个字母；多选题写全部正确字母，用逗号分隔，如 A,C；否则写 ->\n"
    "MATRIX: <如果答案要填一个矩阵，写 行x列: 值1, 值2, …（行优先，每格用 a/b 形式的分数）；否则写 ->\n"
    "DROPDOWN: <如果题目有下拉框，按顺序写每个下拉框要选的选项编号，用 ; 分隔；没有下拉框就写 ->\n"
    "VALUE: <只写要填进输入框的内容，不要写 x= / y=，不要带单位、解释或句号；只有一个空就写这个值（分数写成 a/b）；有两个空就用分号分隔写 值1 ; 值2；否则写 ->\n"
    "矩阵元素不要乘开标量倍数，也不要因式分解。\n"
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


def _parse_letters(body: str) -> list[str]:
    """从 CHOICE 内容里解析选项字母。

    - "A, C"        -> ['A', 'C']
    - "A and C"     -> ['A', 'C']   （忽略 and）
    - "AC"          -> ['A', 'C']   （紧凑写法）
    - "none of these" -> []        （不能被当成 N,O,N,E）
    """
    text = (body or "").upper()
    out: list[str] = []
    for token in re.split(r"[^A-Z]+", text):
        if not token:
            continue
        if len(token) == 1:
            if token in _ALLOWED_CHOICES and token not in out:
                out.append(token)
        elif len(token) <= 8 and all(ch in _ALLOWED_CHOICES for ch in token):
            # 紧凑写法 "AC" / "ABD"
            for ch in token:
                if ch not in out:
                    out.append(ch)
        # 其他长单词（AND / NONE / OF / THESE）直接忽略
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

    out = {"choice": "", "choices": [], "matrix": None, "value": "", "drops": [], "raw": (raw or "").strip()}
    for line in (raw or "").splitlines():
        line = line.strip()
        head, _, body = line.partition(":")
        head = head.strip().upper()
        body = body.strip()
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
            out["value"] = "" if _spec_empty(body) else body
    v = (out.get("value") or "").strip()
    vals = [x.strip() for x in v.split(";") if x.strip()]
    out["values"] = vals
    out["value"] = vals[0] if vals else ""
    return out
