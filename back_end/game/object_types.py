# Object 类型定义表
#
# prototype: "instant" | "continuous"
#
# 共有字段：
#   name, interactable, description, size, sprite
#   success_message, failure_message
#   effects: 效果列表
#
# instant 专有（effect 仅允许 instant_effect / timed buff）：
#   无 max_users / use_state_label / tag / persistent buff
#   行为：use → 应用效果 → 立即返回，不进入 using 状态
#
# continuous 专有：
#   max_users, use_state_label
#   max_duration: 秒（float）或 null（无限）
#   leave_message: max_duration 到期自动退出时的提示
#   行为：use → 进入 using 状态 → Q 键或 max_duration 到期退出

OBJECT_TYPES: dict[str, dict] = {
    # ── 瞬间使用型 ────────────────────────────────────────────────────────────

    "toilet": {
        "prototype":       "instant",
        "name":            "马桶",
        "interactable":    True,
        "description":     "一个干净的马桶。",
        "size":            (1, 1),
        "sprite":          "toilet",
        "success_message": "你使用了马桶，感觉轻松多了。",
        "failure_message": "现在无法使用马桶。",
        "effects": [
            {"type": "instant_effect", "key": "energy", "value": 5},
        ],
    },

    "sink": {
        "prototype":       "instant",
        "name":            "洗手台",
        "interactable":    True,
        "description":     "一个白色的洗手台，水龙头锃光瓦亮。",
        "size":            (1, 1),
        "sprite":          "sink",
        "success_message": "你洗了洗手，感觉干净了许多。",
        "failure_message": "现在无法使用洗手台。",
        "effects": [
            {"type": "instant_effect", "key": "hp", "value": 3},
        ],
    },

    # ── 持续使用型 ────────────────────────────────────────────────────────────

    "sofa": {
        "prototype":       "continuous",
        "name":            "沙发",
        "interactable":    True,
        "description":     "一张舒适的沙发，坐上去软绵绵的。",
        "size":            (2, 1),
        "sprite":          "sofa",
        "max_users":       2,
        "use_state_label": "{entity} 正在沙发上休息",
        "max_duration":    None,
        "success_message": "你坐在沙发上，身体慢慢放松下来。",
        "failure_message": "沙发已经没有空位了。",
        "leave_message":   "你从沙发上起身，感觉休息得不错。",
        "effects": [
            {"type": "buff", "key": "no_move",      "mode": "persistent"},
            {"type": "buff", "key": "no_interact",  "mode": "persistent"},
            {"type": "buff", "key": "no_use",       "mode": "persistent"},
            {"type": "buff", "key": "energy_regen", "value": 1, "mode": "timed", "duration": 60000},
            {"type": "tag",  "key": "resting",      "mode": "persistent"},
        ],
    },

    "bed": {
        "prototype":       "continuous",
        "name":            "床",
        "interactable":    True,
        "description":     "一张整洁的单人床。",
        "size":            (2, 3),
        "sprite":          "bed",
        "max_users":       1,
        "use_state_label": "{entity} 正在睡觉",
        "max_duration":    None,
        "success_message": "你躺在床上，闭上眼睛，困意慢慢袭来。",
        "failure_message": "床上已经有人了。",
        "leave_message":   "你睡得很香，精神焕发地起床了。",
        "effects": [
            {"type": "buff", "key": "no_move",      "mode": "persistent"},
            {"type": "buff", "key": "no_interact",  "mode": "persistent"},
            {"type": "buff", "key": "no_use",       "mode": "persistent"},
            {"type": "buff", "key": "energy_regen", "value": 3, "mode": "persistent"},
            {"type": "tag",  "key": "sleeping",     "mode": "persistent"},
        ],
    },

    "book": {
        "prototype":       "continuous",
        "name":            "书",
        "interactable":    True,
        "description":     "一本厚厚的书，封面上写着看不懂的文字。",
        "size":            (3, 1),
        "sprite":          "book",
        "max_users":       1,
        "use_state_label": "{entity} 正在阅读",
        "max_duration":    None,
        "success_message": "你打开书，开始专注地阅读起来。",
        "failure_message": "书台已被占用。",
        "leave_message":   "你合上书，回味着刚才读到的内容。",
        "effects": [
            {"type": "buff", "key": "no_move",      "mode": "persistent"},
            {"type": "buff", "key": "no_interact",  "mode": "persistent"},
            {"type": "buff", "key": "no_use",       "mode": "persistent"},
            {"type": "buff", "key": "energy_regen", "value": -3, "mode": "persistent"},
            {"type": "tag",  "key": "reading",      "mode": "persistent"},
        ],
    },

    "cook": {
        "prototype":       "continuous",
        "name":            "炉灶",
        "interactable":    True,
        "description":     "炉火正旺，锅里咕嘟咕嘟地冒着热气。",
        "size":            (2, 1),
        "sprite":          "cook",
        "max_users":       1,
        "use_state_label": "{entity} 正在烹饪",
        "max_duration":    None,
        "success_message": "你开始在炉灶前忙碌起来，香气慢慢飘散开来。",
        "failure_message": "炉灶已经有人在使用了。",
        "leave_message":   "你关掉炉火，菜肴的香气弥漫在空气中。",
        "effects": [
            {"type": "buff", "key": "no_move",     "mode": "persistent"},
            {"type": "buff", "key": "no_interact", "mode": "persistent"},
            {"type": "buff", "key": "no_use",      "mode": "persistent"},
            {"type": "tag",  "key": "cooking",     "mode": "persistent"},
        ],
    },

    "desk": {
        "prototype":       "continuous",
        "name":            "书桌",
        "interactable":    True,
        "description":     "一张木制书桌，桌面上摆着一些文件。",
        "size":            (2, 1),
        "sprite":          "desk",
        "max_users":       1,
        "use_state_label": "{entity} 正在工作",
        "max_duration":    None,
        "success_message": "你坐到书桌前，准备开始工作。",
        "failure_message": "书桌已经有人在使用了。",
        "leave_message":   "你放下笔，结束了今天的工作。",
        "effects": [
            {"type": "buff", "key": "no_move",      "mode": "persistent"},
            {"type": "buff", "key": "no_interact",  "mode": "persistent"},
            {"type": "buff", "key": "no_use",       "mode": "persistent"},
            {"type": "buff", "key": "energy_regen", "value": -1, "mode": "timed", "duration": 60000},
            {"type": "tag",  "key": "working",      "mode": "persistent"},
        ],
    },

    "bath": {
        "prototype":       "continuous",
        "name":            "浴缸",
        "interactable":    True,
        "description":     "一个白色的浴缸，里面的水还是温热的。",
        "size":            (1, 2),
        "sprite":          "bath",
        "max_users":       1,
        "use_state_label": "{entity} 正在泡澡",
        "max_duration":    None,
        "success_message": "你泡进浴缸，热水让紧绷的肌肉慢慢放松。",
        "failure_message": "浴缸已经有人在使用了。",
        "leave_message":   "你从浴缸里出来，感觉神清气爽。",
        "effects": [
            {"type": "buff", "key": "no_move",      "mode": "persistent"},
            {"type": "buff", "key": "no_interact",  "mode": "persistent"},
            {"type": "buff", "key": "no_use",       "mode": "persistent"},
            {"type": "buff", "key": "energy_regen", "value": 2, "mode": "persistent"},
            {"type": "tag",  "key": "bathing",      "mode": "persistent"},
        ],
    },
}
