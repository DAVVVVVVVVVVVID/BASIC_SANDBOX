#!/usr/bin/env python3
"""
X3 语料禁用词审计与替换（总控 11-10）：用 whale-self/personas-v1/whale/persona.yaml 的 purpose_forbidden 与 anchors.negative
扫 docs/x3-days 的 D1–D7 / L1（description、description_original、voice、body 三段），第一人称出现禁用词的条目整条替换为
同重要度的普通内容；第三人称提及不算，但「本鲸是 AI」这类自我认知一律换。
写 changes_vN.json（哪天哪条、改前改后），manifest.version +1，重出 jsonl / answer_key / README。

  cd back_end && uv run python scripts/x3_audit.py [--dir ../docs/x3-days] [--persona .../personas-v1/whale/persona.yaml] [--dry-run]
"""
import argparse
import json
import re
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from gen_x3_days import emit, write_readme  # noqa: E402

FIRST_PERSON = ("本鲸", "我")
SELF_IDENTITY = [r"(本鲸|我)\s*(是|就是|也是)\s*(个\s*)?AI", r"(本鲸|我)\s*(是|不是)\s*真人", r"(本鲸|我)\s*(坦白|如实)?承认.{0,8}AI",
                 r"是不是\s*AI.{0,16}承认", r"(本鲸|我)\s*是\s*(鲸鱼|猫精|程序)"]

REPLACEMENTS = {
    "ai_admit": {"match": lambda r: any("AI" in t for t in (r["description"], r.get("description_original", ""), r.get("voice", ""))),
                 "new": {"description": "直播时有观众问本鲸最想带大家去小镇哪里看看，本鲸说想去码头看日落",
                         "keywords": ["直播", "观众", "码头", "日落", "提问"],
                         "body": {"what": "回答观众提问", "how": "读到弹幕后直接回答", "why": "想把小镇讲给他们听"},
                         "voice": "下次真带你们去码头看日落。"}},
    "poor_whale": {"match": lambda r: "本鲸是穷鲸" in r.get("voice", ""), "new": {"voice": "本鲸的钱包空了。"}},
}


def load_terms(persona: Path) -> list[str]:
    d = yaml.safe_load(persona.read_text(encoding="utf-8"))
    terms = list(d.get("purpose_forbidden") or [])
    for a in (d.get("anchors") or {}).get("negative") or []:
        a = re.sub(r"（.*?）", "", str(a)).strip()
        if a:
            terms.append(a)
    return terms


def texts(r: dict) -> list[str]:
    return [r["description"], r.get("description_original", ""), r.get("voice", ""), r["body"]["what"], r["body"]["how"], r["body"]["why"]]


def first_person_hit(r: dict, terms: list[str]) -> list[str]:
    hits = []
    for t in texts(r):
        for pat in SELF_IDENTITY:
            if re.search(pat, t):
                hits.append(f"identity:{pat}")
        for term in terms:
            if term and term in t:
                for sent in re.split(r"[。！？；\n]", t):
                    if term in sent and any(fp in sent for fp in FIRST_PERSON):
                        hits.append(term)
    return sorted(set(hits))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=str(HERE.parent.parent / "docs" / "x3-days"))
    ap.add_argument("--persona", default="/home/shan-dw/Project/whale-self/personas-v1/whale/persona.yaml")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    out = Path(a.dir)
    terms = load_terms(Path(a.persona))
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    version = int(manifest.get("version", 1)) + 1
    days = {k: json.loads((out / f"{k}.json").read_text(encoding="utf-8"))["rows"] for k in [f"D{i}" for i in range(1, 8)] + ["L1"]}
    changes = []; unresolved = []
    for k, rows in days.items():
        for r in rows:
            hits = first_person_hit(r, terms)
            if not hits:
                continue
            before = {"description": r["description"], "voice": r.get("voice", ""), "keywords": list(r["keywords"])}
            applied = None
            for name, rep in REPLACEMENTS.items():
                if rep["match"](r):
                    for fk, fv in rep["new"].items():
                        r[fk] = dict(fv) if isinstance(fv, dict) else fv
                    r.pop("description_original", None)
                    applied = name; break
            if applied is None or first_person_hit(r, terms):
                unresolved.append({"day": k, "id": r["id"], "hits": hits, "text": r["description"]}); continue
            changes.append({"day": k, "id": r["id"], "ts": r["ts"], "hits": hits, "rule": applied, "before": before,
                            "after": {"description": r["description"], "voice": r.get("voice", ""), "keywords": list(r["keywords"])}})
    report = {"version": version, "terms_scanned": terms, "identity_rules": SELF_IDENTITY, "changed": len(changes), "unresolved": unresolved, "changes": changes}
    print(json.dumps({"version": version, "changed": len(changes), "unresolved": len(unresolved), "by_day": {k: sum(1 for c in changes if c["day"] == k) for k in days}}, ensure_ascii=False))
    if a.dry_run:
        return 0
    if unresolved:
        print("UNRESOLVED:", json.dumps(unresolved, ensure_ascii=False)[:800]); return 1
    for k, rows in days.items():
        (out / f"{k}.json").write_text(json.dumps({"day": k, "agent": "whale", "date": rows[0]["ts"][:10], "version": version, "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    manifest["version"] = version
    manifest["audit"] = {"persona": a.persona, "terms": len(terms), "changed": len(changes), "changes_file": f"changes_v{version}.json"}
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / f"changes_v{version}.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    key = emit(out, days); write_readme(out, manifest, key)
    rd = out / "README.md"
    rd.write_text(rd.read_text(encoding="utf-8").replace("# X3 Dream 实验语料", f"# X3 Dream 实验语料（v{version}，禁用词审计后）", 1)
                  + f"\n## 禁用词审计（v{version}）\n\n按 `personas-v1/whale/persona.yaml` 的 `purpose_forbidden` + `anchors.negative`（{len(terms)} 词）与自我认知硬规则扫全部字段（含改写前原句），第一人称命中整条替换，共 {len(changes)} 条，明细 `changes_v{version}.json`。\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
