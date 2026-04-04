# Arena 层区域字符图，尺寸必须与 map_data.py 一致
# '.' = 未归属

ARENA_MAP: list[str] = [
    "............",
    ".aaaaaa.bbb.",
    ".aaaaaa.bbb.",
    ".aaaaaa...b.",
    ".aaaaaa.....",
    ".aaaaaa.ccc.",
    ".aaaaaa.ccc.",
    "............",
]

ARENA_CHARS: dict[str, str] = {
    "a": "bedroom",
    "b": "bathroom",
    "c": "kitchen",
}
