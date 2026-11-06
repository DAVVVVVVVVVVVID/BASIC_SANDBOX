#!/usr/bin/env python3
"""
从沙盒 GET /admin/export?date= 拉一天数据并与 manifest 对账（模拟 A 的 dataset_export.py 的沙盒源）。

  cd back_end && uv run python scripts/dataset_fetch.py --base http://127.0.0.1:8000 --date 2026-11-06 [--out /tmp/ds] [--data-dir run/data/sandbox]
输出 <out>/<town>/<date>/{actions,chat,state}.jsonl + manifest.json；校验：写出的行数 == manifest.counts；给 --data-dir 时再与
沙盒本地 data/<kind>/<date>.jsonl 的行数对账（同机）。退出码 0 = 全部一致。
"""
import argparse
import json
import sys
import urllib.request
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--date", required=True)
    ap.add_argument("--out", default="/tmp/sandbox_dataset")
    ap.add_argument("--data-dir", default=None, help="沙盒本地数据目录，用来与文件行数对账")
    args = ap.parse_args()
    with urllib.request.urlopen(f"{args.base}/admin/export?date={args.date}", timeout=60) as r:
        d = json.load(r)
    out = Path(args.out) / d["town"] / args.date
    out.mkdir(parents=True, exist_ok=True)
    ok = True
    print(f"town={d['town']} map_version={d['map_version']} seed={d['seed']} schema={d['schema']} generated_at={d['generated_at']}")
    for kind in ("actions", "chat", "state"):
        rows = d.get(kind, [])
        fp = out / f"{kind}.jsonl"
        fp.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
        n_written = len(fp.read_text(encoding="utf-8").splitlines())
        n_manifest = d["manifest"]["counts"][kind]
        line = f"  {kind:8s} manifest={n_manifest:6d} written={n_written:6d}"
        good = n_written == n_manifest
        if args.data_dir:
            src = Path(args.data_dir) / kind / f"{args.date}.jsonl"
            n_src = len(src.read_text(encoding="utf-8").splitlines()) if src.exists() else 0
            line += f" local_file={n_src:6d}"
            good = good and n_src == n_manifest
        # 每行都带数据集字段
        missing = [i for i, r in enumerate(rows) if not {"town", "map_version", "seed"} <= set(r)]
        if missing:
            line += f" rows_missing_dataset_fields={len(missing)}"; good = False
        print(line + ("  OK" if good else "  MISMATCH"))
        ok &= good
    (out / "manifest.json").write_text(json.dumps({**d["manifest"], "date": d["date"], "town": d["town"], "map_version": d["map_version"],
                                                    "seed": d["seed"], "schema": d["schema"], "generated_at": d["generated_at"]},
                                                   ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"→ {'PASS' if ok else 'FAIL'}  ({out})")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
