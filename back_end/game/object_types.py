import json
from pathlib import Path

with open(Path(__file__).parent / "object_types.json", encoding="utf-8") as _f:
    OBJECT_TYPES: dict[str, dict] = json.load(_f)
