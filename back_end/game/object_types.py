# Object 类型定义表
# size: (width, height) 单位为 tile，从 position 锚点向右、向下展开
# sprite: 对应 assets/sprites/<sprite>.png，None 表示无贴图（用纯色块代替）
# max_users: 最多同时使用人数
# use_state_label: E 键使用后玩家 state 文字，{entity} 替换为实体名
# effects: buff/tag 列表
#   - type: "buff" | "tag"
#   - key: 效果标识
#   - value: 数值（buff 专用）
#   - mode: "while_active"（使用期间持续）| "instant"（进入时触发，有 duration）
#   - duration: 毫秒（仅 instant 模式需要）

OBJECT_TYPES: dict[str, dict] = {
    "tree": {
        "name": "老橡树",
        "interactable": True,
        "description": "一棵粗壮的老橡树，树皮上刻着一些符文。",
        "size": (1, 1),
        "sprite": None,
        "max_users": 1,
        "use_state_label": "{entity} 正在抚摸老橡树",
        "effects": [
            {"type": "buff", "key": "no_move",     "mode": "while_active"},
            {"type": "buff", "key": "no_interact", "mode": "while_active"},
            {"type": "buff", "key": "no_use",      "mode": "while_active"},
            {"type": "tag",  "key": "nature",      "mode": "while_active"},
        ],
    },
    "well": {
        "name": "古老的水井",
        "interactable": True,
        "description": "井水清澈，似乎深不见底。",
        "size": (1, 1),
        "sprite": None,
        "max_users": 1,
        "use_state_label": "{entity} 正在打水",
        "effects": [
            {"type": "buff", "key": "no_move",     "mode": "while_active"},
            {"type": "buff", "key": "no_interact", "mode": "while_active"},
            {"type": "buff", "key": "no_use",      "mode": "while_active"},
            {"type": "buff", "key": "hp_regen", "value": 1, "mode": "while_active"},
        ],
    },
    "sofa": {
        "name": "沙发",
        "interactable": True,
        "description": "一张舒适的沙发，坐上去软绵绵的。",
        "size": (2, 1),
        "sprite": "sofa",
        "max_users": 2,
        "use_state_label": "{entity} 正在沙发上休息",
        "effects": [
            {"type": "buff", "key": "no_move",     "mode": "while_active"},
            {"type": "buff", "key": "no_interact", "mode": "while_active"},
            {"type": "buff", "key": "no_use",      "mode": "while_active"},
            {"type": "buff", "key": "energy_regen", "value": 1, "mode": "while_active"},
            {"type": "tag",  "key": "resting", "mode": "while_active"},
        ],
    },
    "bed": {
        "name": "床",
        "interactable": True,
        "description": "一张整洁的单人床。",
        "size": (2, 3),
        "sprite": "bed",
        "max_users": 1,
        "use_state_label": "{entity} 正在睡觉",
        "effects": [
            {"type": "buff", "key": "no_move",     "mode": "while_active"},
            {"type": "buff", "key": "no_interact", "mode": "while_active"},
            {"type": "buff", "key": "no_use",      "mode": "while_active"},
            {"type": "buff", "key": "energy_regen", "value": 3, "mode": "while_active"},
            {"type": "tag",  "key": "sleeping", "mode": "while_active"},
        ],
    },
    "book": {
        "name": "书",
        "interactable": True,
        "description": "一本厚厚的书，封面上写着看不懂的文字。",
        "size": (3, 1),
        "sprite": "book",
        "max_users": 1,
        "use_state_label": "{entity} 正在阅读",
        "effects": [
            {"type": "buff", "key": "no_move",     "mode": "while_active"},
            {"type": "buff", "key": "no_interact", "mode": "while_active"},
            {"type": "buff", "key": "no_use",      "mode": "while_active"},
            {"type": "tag",  "key": "reading", "mode": "while_active"},
        ],
    },
    "cook": {
        "name": "炉灶",
        "interactable": True,
        "description": "炉火正旺，锅里咕嘟咕嘟地冒着热气。",
        "size": (2, 1),
        "sprite": "cook",
        "max_users": 1,
        "use_state_label": "{entity} 正在烹饪",
        "effects": [
            {"type": "buff", "key": "no_move",     "mode": "while_active"},
            {"type": "buff", "key": "no_interact", "mode": "while_active"},
            {"type": "buff", "key": "no_use",      "mode": "while_active"},
            {"type": "tag",  "key": "cooking", "mode": "while_active"},
        ],
    },
    "desk": {
        "name": "书桌",
        "interactable": True,
        "description": "一张木制书桌，桌面上摆着一些文件。",
        "size": (2, 1),
        "sprite": "desk",
        "max_users": 1,
        "use_state_label": "{entity} 正在工作",
        "effects": [
            {"type": "buff", "key": "no_move",     "mode": "while_active"},
            {"type": "buff", "key": "no_interact", "mode": "while_active"},
            {"type": "buff", "key": "no_use",      "mode": "while_active"},
            {"type": "tag",  "key": "working", "mode": "while_active"},
        ],
    },
    "bath": {
        "name": "浴缸",
        "interactable": True,
        "description": "一个白色的浴缸，里面的水还是温热的。",
        "size": (1, 2),
        "sprite": "bath",
        "max_users": 1,
        "use_state_label": "{entity} 正在泡澡",
        "effects": [
            {"type": "buff", "key": "no_move",     "mode": "while_active"},
            {"type": "buff", "key": "no_interact", "mode": "while_active"},
            {"type": "buff", "key": "no_use",      "mode": "while_active"},
            {"type": "buff", "key": "energy_regen", "value": 2, "mode": "while_active"},
            {"type": "tag",  "key": "bathing", "mode": "while_active"},
        ],
    },
    "toilet": {
        "name": "马桶",
        "interactable": True,
        "description": "一个干净的马桶。",
        "size": (1, 1),
        "sprite": "toilet",
        "max_users": 1,
        "use_state_label": "{entity} 正在使用马桶",
        "effects": [
            {"type": "buff", "key": "no_move",     "mode": "while_active"},
            {"type": "buff", "key": "no_interact", "mode": "while_active"},
            {"type": "buff", "key": "no_use",      "mode": "while_active"},
        ],
    },
    "sink": {
        "name": "洗手台",
        "interactable": True,
        "description": "一个白色的洗手台，水龙头锃光瓦亮。",
        "size": (1, 1),
        "sprite": "sink",
        "max_users": 1,
        "use_state_label": "{entity} 正在洗手",
        "effects": [
            {"type": "buff", "key": "no_move",     "mode": "while_active"},
            {"type": "buff", "key": "no_interact", "mode": "while_active"},
            {"type": "buff", "key": "no_use",      "mode": "while_active"},
            {"type": "tag",  "key": "clean", "mode": "while_active"},
        ],
    },
}
