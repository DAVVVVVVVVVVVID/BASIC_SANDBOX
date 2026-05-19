# 认知地图 — 纯语义树，只存 id / name / 嵌套关系，零坐标
# 树形结构：worlds → sectors → arenas

COGNITIVE_MAP: dict = {
    "worlds": [
        {
            "id":   "town",
            "name": "小镇",
            "sectors": [
                {
                    "id":   "house",
                    "name": "房子",
                    "arenas": [
                        {"id": "bedroom",  "name": "卧室"},
                        {"id": "kitchen",  "name": "厨房"},
                        {"id": "bathroom", "name": "浴室"},
                    ],
                },
            ],
        },
    ],
}
