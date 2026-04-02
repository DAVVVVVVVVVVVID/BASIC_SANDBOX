# Object 类型定义表
# size: (width, height) 单位为 tile，从 position 锚点向右、向下展开
# sprite: 对应 assets/sprites/<sprite>.png，None 表示无贴图（用纯色块代替）
# tags: 用于未来扩展（筛选、行为分类等），目前仅作标注

OBJECT_TYPES: dict[str, dict] = {
    "tree": {
        "name": "老橡树",
        "interactable": True,
        "description": "一棵粗壮的老橡树，树皮上刻着一些符文。",
        "size": (1, 1),
        "sprite": None,
        "tags": ["nature"],
    },
    "well": {
        "name": "古老的水井",
        "interactable": True,
        "description": "井水清澈，似乎深不见底。",
        "size": (1, 1),
        "sprite": None,
        "tags": ["nature", "water"],
    },
    "sofa": {
        "name": "沙发",
        "interactable": True,
        "description": "一张舒适的沙发，坐上去软绵绵的。",
        "size": (2, 1),
        "sprite": "sofa",
        "tags": ["furniture", "sit"],
    },
    "bed": {
        "name": "床",
        "interactable": True,
        "description": "一张整洁的单人床。",
        "size": (2, 3),
        "sprite": "bed",
        "tags": ["furniture", "sleep"],
    },
    "book": {
        "name": "书",
        "interactable": True,
        "description": "一本厚厚的书，封面上写着看不懂的文字。",
        "size": (3, 1),
        "sprite": "book",
        "tags": ["item", "read"],
    },
    "cook": {
        "name": "炉灶",
        "interactable": True,
        "description": "炉火正旺，锅里咕嘟咕嘟地冒着热气。",
        "size": (2, 1),
        "sprite": "cook",
        "tags": ["furniture", "cook"],
    },
    "desk": {
        "name": "书桌",
        "interactable": True,
        "description": "一张木制书桌，桌面上摆着一些文件。",
        "size": (2, 1),
        "sprite": "desk",
        "tags": ["furniture", "surface"],
    },
    "bath": {
        "name": "浴缸",
        "interactable": True,
        "description": "一个白色的浴缸，里面的水还是温热的。",
        "size": (1, 2),
        "sprite": "bath",
        "tags": ["furniture", "wash"],
    },
    "toilet": {
        "name": "马桶",
        "interactable": True,
        "description": "一个干净的马桶。",
        "size": (1, 1),
        "sprite": "toilet",
        "tags": ["furniture"],
    },
    "sink": {
        "name": "洗手台",
        "interactable": True,
        "description": "一个白色的洗手台，水龙头锃光瓦亮。",
        "size": (1, 1),
        "sprite": "sink",
        "tags": ["furniture", "wash"],
    },
}
