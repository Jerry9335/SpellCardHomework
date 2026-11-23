"""东方风格问候语：按时段随机、近期去重、尽量不连续同一角色。"""
from __future__ import annotations

import datetime as dt
import random

MORNING = "morning"
AFTERNOON = "afternoon"
EVENING = "evening"
LATE = "late"

SLOT_LABELS = {
    MORNING: "早晨",
    AFTERNOON: "下午",
    EVENING: "晚上",
    LATE: "深夜",
}

ROTATE_SECONDS = 30

# (speaker, avatar, slot, text)
# slot: morning / afternoon / evening / late / any
_RAW = [
    # ---------------- 早晨 ----------------
    ("灵梦", "reimu", MORNING, "早，{name}。茶还没泡好，你就来退治了？"),
    ("灵梦", "reimu", MORNING, "早上好，{name}。神社今天也缺香火钱呢。"),
    ("魔理沙", "marisa", MORNING, "早上好，{name}。今天也要被我一炮解决吗？"),
    ("魔理沙", "marisa", MORNING, "早啊，{name}。昨晚的魔法实验，想看看吗？"),
    ("慧音", "keine", MORNING, "早上好，{name}。寺子屋的课，可别迟到。"),
    ("慧音", "keine", MORNING, "早安，{name}。今天的历史课，不许打瞌睡。"),
    ("咲夜", "sakuya", MORNING, "早安，{name}。红茶和日程都准备好了。"),
    ("咲夜", "sakuya", MORNING, "早上好，{name}。大小姐还在睡，请小声一点。"),
    ("文文", "aya", MORNING, "早上好，{name}。今天的号外，给你留了一份。"),
    ("文文", "aya", MORNING, "早，{name}。有新闻的话，记得先告诉我。"),
    ("紫", "yukari", MORNING, "早安，{name}。境界的早晨，难得这么安静呢～"),
    ("紫", "yukari", MORNING, "早上好，{name}。再睡一会儿，也不过分吧～"),
    ("帕秋莉", "patchouli", MORNING, "早上好，{name}。图书馆刚开门，别弄乱书。"),
    ("芙兰", "flandre", MORNING, "早上好，{name}。今天玩什么？"),

    # ---------------- 下午 ----------------
    ("灵梦", "reimu", AFTERNOON, "下午好，{name}。香火钱没涨，麻烦事倒不少。"),
    ("灵梦", "reimu", AFTERNOON, "{name}，下午了。要喝茶吗？我请客——才怪。"),
    ("魔理沙", "marisa", AFTERNOON, "下午好，{name}。普通魔法使的图书馆时间到了。"),
    ("魔理沙", "marisa", AFTERNOON, "{name}，下午好。这次借的书，我会还的啦。"),
    ("帕秋莉", "patchouli", AFTERNOON, "下午好，{name}。这本书，看完再走。"),
    ("帕秋莉", "patchouli", AFTERNOON, "{name}，别把书页折了。"),
    ("紫", "yukari", AFTERNOON, "下午好，{name}。要不要来境界这边打个盹？"),
    ("紫", "yukari", AFTERNOON, "{name}，下午好～。境界的缝隙里，时间过得很慢呢。"),
    ("咲夜", "sakuya", AFTERNOON, "下午好，{name}。需要我停一下时间吗？"),
    ("咲夜", "sakuya", AFTERNOON, "{name}，下午茶准备好了。要加糖吗？"),
    ("慧音", "keine", AFTERNOON, "下午好，{name}。历史作业写完了吗？"),
    ("慧音", "keine", AFTERNOON, "{name}，下午好。温习一遍再玩吧。"),
    ("文文", "aya", AFTERNOON, "下午好，{name}。有独家消息吗？"),
    ("芙兰", "flandre", AFTERNOON, "下午好，{name}。陪我玩嘛，就一会儿。"),

    # ---------------- 晚上 ----------------
    ("灵梦", "reimu", EVENING, "晚上好，{name}。退治完就回去，神社要关门了。"),
    ("灵梦", "reimu", EVENING, "{name}，天黑了。别在神社附近乱晃哦。"),
    ("魔理沙", "marisa", EVENING, "晚上好，{name}。夜战可是我的主场，别拖后腿。"),
    ("魔理沙", "marisa", EVENING, "{name}，晚上好。星星出来了，正是实验的好时候！"),
    ("紫", "yukari", EVENING, "晚上好，{name}。夜晚的境界，最适合读书了～"),
    ("紫", "yukari", EVENING, "{name}，晚上好。要不要一起看月亮？"),
    ("蕾米莉亚", "remilia", EVENING, "晚上好，{name}。红月之下，命运在微笑。"),
    ("蕾米莉亚", "remilia", EVENING, "{name}，夜晚才是我等的时间。"),
    ("咲夜", "sakuya", EVENING, "晚上好，{name}。大小姐的晚餐时间到了。"),
    ("咲夜", "sakuya", EVENING, "{name}，晚上好。请把今天的日程交给我。"),
    ("芙兰", "flandre", EVENING, "晚上好，{name}。夜里也能玩吗？"),
    ("芙兰", "flandre", EVENING, "{name}，来玩捉迷藏吧，输的人会被破坏哦。"),
    ("文文", "aya", EVENING, "晚上好，{name}。夜里的新闻，才最有趣呢。"),
    ("帕秋莉", "patchouli", EVENING, "晚上好，{name}。图书馆的灯，还亮着。"),

    # ---------------- 深夜 ----------------
    ("紫", "yukari", LATE, "{name}，凌晨了哦。连我都要睡了～"),
    ("紫", "yukari", LATE, "{name}，这个点还不睡？境界也要休息的。"),
    ("灵梦", "reimu", LATE, "{name}，这个点还不睡？符卡都要失效了。"),
    ("灵梦", "reimu", LATE, "{name}，熬夜退治，明天会起不来的。"),
    ("魔理沙", "marisa", LATE, "{name}，深夜才是魔女的黄金时间！"),
    ("魔理沙", "marisa", LATE, "{name}，还醒着？来陪我做个实验吧。"),
    ("帕秋莉", "patchouli", LATE, "{name}，熬夜看书，小心哮喘。"),
    ("帕秋莉", "patchouli", LATE, "{name}，图书馆要闭馆了。"),
    ("芙兰", "flandre", LATE, "{name}，还醒着？陪我玩一会儿嘛。"),
    ("咲夜", "sakuya", LATE, "{name}，夜深了。请早点休息。"),

    # ---------------- 通用 ----------------
    ("灵梦", "reimu", "any", "欢迎回来，{name}。神社今天也照常营业。"),
    ("魔理沙", "marisa", "any", "{name}，又来退治啦？这次可别输给我。"),
    ("紫", "yukari", "any", "{name}，境界这边请～"),
    ("慧音", "keine", "any", "{name}，学习也要劳逸结合。"),
    ("咲夜", "sakuya", "any", "{name}，需要红茶吗？"),
    ("帕秋莉", "patchouli", "any", "{name}，图书馆保持安静。"),
    ("文文", "aya", "any", "{name}，要接受采访吗？"),
    ("蕾米莉亚", "remilia", "any", "{name}，命运把你带到这里了呢。"),

    # ---------------- 新角色：永远亭 / 竹林 ----------------
    ("辉夜", "kaguya", MORNING, "早安，{name}。竹林的晨露还没干，你就来打扰我的清梦了？"),
    ("辉夜", "kaguya", AFTERNOON, "下午好，{name}。要不要陪我下一局棋？输的人负责泡茶。"),
    ("辉夜", "kaguya", EVENING, "晚上好，{name}。月亮升起来了，正是听公主讲故事的时候。"),
    ("辉夜", "kaguya", LATE, "{name}，夜深了。永夜的时间，也别熬坏了身子。"),
    ("辉夜", "kaguya", "any", "{name}，欢迎来到永远亭。这里的时光，走得比外面慢一些。"),

    ("永琳", "eirin", MORNING, "早上好，{name}。先让我看看气色——昨晚又熬夜了吧？"),
    ("永琳", "eirin", AFTERNOON, "下午好，{name}。药已经配好，记得按时服用。"),
    ("永琳", "eirin", EVENING, "晚上好，{name}。月之头脑也要休息，闲聊就到此为止吧。"),
    ("永琳", "eirin", LATE, "{name}，这个时辰还不睡？再这样，我可要开药方了。"),
    ("永琳", "eirin", "any", "{name}，身体是退治的本钱。先坐下，让我诊一诊。"),

    ("铃仙", "reisen", MORNING, "早上好，{name}。今天也要精神满满地退治哦……大概。"),
    ("铃仙", "reisen", AFTERNOON, "下午好，{name}。我的眼睛有点晕，你、你别靠太近。"),
    ("铃仙", "reisen", EVENING, "晚上好，{name}。月兔的耳朵很灵，小声一点也没关系。"),
    ("铃仙", "reisen", LATE, "{name}，已经这么晚了……再不睡，明天会没精神的。"),
    ("铃仙", "reisen", "any", "{name}，欢迎回来。要买点月都的药吗？很、很有效的。"),

    ("天为", "tewi", MORNING, "早啊，{name}！今天也来试试运气吧，我保证不骗你～"),
    ("天为", "tewi", AFTERNOON, "下午好，{name}。胡萝卜分你一半——只有一半哦。"),
    ("天为", "tewi", EVENING, "晚上好，{name}。月兔的恶作剧时间到啦！"),
    ("天为", "tewi", LATE, "{name}，这么晚还不睡？嘿嘿，是不是在等我讲鬼故事？"),
    ("天为", "tewi", "any", "{name}，来玩吧！输了的人请我吃胡萝卜。"),

    ("影狼", "kagerou", MORNING, "早、早上好，{name}。今天的太阳……真好啊。"),
    ("影狼", "kagerou", AFTERNOON, "下午好，{name}。那个，我最近有在好好控制变身了……"),
    ("影狼", "kagerou", EVENING, "晚上好，{name}。月亮一出来，我就有点……别、别在意。"),
    ("影狼", "kagerou", LATE, "{name}，夜深了。狼的耳朵会听到很多声音，快休息吧。"),
    ("影狼", "kagerou", "any", "{name}，欢迎。要、要一起散步吗？我不会咬人的。"),
]

ENTRIES = [
    {"id": i, "speaker": speaker, "avatar": avatar, "slot": slot, "text": text}
    for i, (speaker, avatar, slot, text) in enumerate(_RAW)
]
assert len(ENTRIES) == 85, len(ENTRIES)


def slot_for_hour(hour: int) -> str:
    if 6 <= hour < 12:
        return MORNING
    if 12 <= hour < 18:
        return AFTERNOON
    if 18 <= hour < 23:
        return EVENING
    return LATE


def slot_for_now(now: dt.datetime | None = None) -> str:
    now = now or dt.datetime.now()
    return slot_for_hour(now.hour)


def next_boundary(now: dt.datetime | None = None) -> dt.datetime:
    """下一个时段切换点：06 / 12 / 18 / 23 / 次日 06。"""
    now = now or dt.datetime.now()
    today = now.date()
    points = [6, 12, 18, 23]
    candidates = [dt.datetime.combine(today, dt.time(h)) for h in points]
    candidates.append(dt.datetime.combine(today + dt.timedelta(days=1), dt.time(6)))
    for point in candidates:
        if point > now:
            return point
    return candidates[-1]


def entries_for(slot: str) -> list[dict]:
    return [e for e in ENTRIES if e["slot"] in (slot, "any")]


def pick_entry(slot: str, recent_ids=(), last_avatar: str = "",
               rng: random.Random | None = None) -> dict:
    rng = rng or random
    # 时段专属文案权重更高，避免总是抽到通用句
    specific = [e for e in ENTRIES if e["slot"] == slot]
    general = [e for e in ENTRIES if e["slot"] == "any"]
    pool = specific * 3 + general
    recent = set(recent_ids)
    fresh = [e for e in pool if e["id"] not in recent]
    if last_avatar:
        changed = [e for e in fresh if e["avatar"] != last_avatar]
        if changed:
            fresh = changed
    if not fresh:
        fresh = pool
    return rng.choice(fresh)


def format_entry(entry: dict, name: str) -> str:
    return entry["text"].replace("{name}", name or "旅人")


def all_avatars() -> set[str]:
    return {e["avatar"] for e in ENTRIES}
