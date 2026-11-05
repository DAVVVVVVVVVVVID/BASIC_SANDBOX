"""
需求值分档文字（B13）。只给越过阈值的分档，不给数值（报告 §4.3）。
文案沿用 mood.py 的 label()，与 whale-self/whale_self/state.py 的 LABELS 同源。
"""

THRESHOLDS = {"low": 25, "critical": 15, "emergency": 10}

LABELS: dict[str, dict[str, str]] = {
    "fullness": {"low": "饿了", "critical": "饿得没力气了，得先吃点东西", "emergency": "饿到眼前发黑，什么都顾不上，先吃饭"},
    "energy":   {"low": "好累，想休息", "critical": "快撑不住了，得睡一觉", "emergency": "困到站不住，必须马上睡"},
    "social": {
        "low":       "蔫蔫的（没人陪太久了），但有人来就会马上打起精神",
        "critical":  "好久没人说话了，蔫得不行，碎碎念里都是想找人聊",
        "emergency": "孤单到有点慌，特别想找个人说话",
    },
    "fun": {"low": "有点无聊，想找新鲜事", "critical": "无聊到坐不住，必须找点新鲜事", "emergency": "闷得快爆炸了，干什么都比发呆好"},
}
TAG_LABELS = {"smug": "得意（刚被夸了）"}
MOOD_LOW_LABEL = "有点委屈（刚被凶了），但不记仇"
MOOD_LOW_THRESHOLD = 35.0
MOOD_HIGH_LABEL = "开心"
MOOD_HIGH_THRESHOLD = 75.0
OK_LABEL = "还好"
HIGH_LABEL = "元气满满、超开心"

# 亲密度分档（假设：契约只说「分档」，阈值自定）
CLOSENESS_TIERS = [(70, "很亲近"), (40, "熟悉"), (15, "认识"), (0, "陌生")]


def tier(value: float) -> str | None:
    if value < THRESHOLDS["emergency"]:
        return "emergency"
    if value < THRESHOLDS["critical"]:
        return "critical"
    if value < THRESHOLDS["low"]:
        return "low"
    return None


def needs_text(player: dict) -> dict:
    """
    返回 perceive 用的 needs 块：
    {"fullness": "饿了" | "还好", ..., "mood": "开心" | "还好" | "...", "emotion_tags": [...],
     "lines": [越过阈值的文字], "hard": ["energy<15"]}
    """
    out: dict = {}
    lines: list[str] = []
    hard: list[str] = []
    for key in ("fullness", "energy", "social", "fun"):
        x = float(player.get(key, 50.0))
        t = tier(x)
        out[key] = LABELS[key][t] if t else OK_LABEL
        if t:
            lines.append(LABELS[key][t])
        if x < THRESHOLDS["critical"]:
            hard.append(f"{key}<{THRESHOLDS['critical']}")
    mood = float(player.get("mood", 65.0))
    if mood < MOOD_LOW_THRESHOLD:
        out["mood"] = MOOD_LOW_LABEL
        lines.append(MOOD_LOW_LABEL)
    elif mood > MOOD_HIGH_THRESHOLD:
        out["mood"] = MOOD_HIGH_LABEL
    else:
        out["mood"] = OK_LABEL
    tags = [TAG_LABELS.get(t["key"], t["key"]) for t in player.get("emotion_tags", [])]
    out["emotion_tags"] = tags
    lines.extend(tags)
    if not lines and float(player.get("social", 0)) > 85 and mood > 75:
        lines.append(HIGH_LABEL)
    out["lines"] = lines
    out["hard"] = hard
    return out


def closeness_tier(value: float) -> str:
    for threshold, label in CLOSENESS_TIERS:
        if value >= threshold:
            return label
    return CLOSENESS_TIERS[-1][1]
