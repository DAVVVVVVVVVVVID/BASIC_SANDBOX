#!/usr/bin/env python3
"""
闭测周 ⑤：一周房租 / 日薪结算核对（只读）。

  cd back_end && uv run python scripts/econ_reconcile.py --data /home/shan-dw/Project/run/data/sandbox --from 2026-11-15 --to 2026-11-21
      [--economy game/economy.json] [--db <data>/sandbox.db] [--json]

做三件事：
1. 期间表：按账号 × kind 汇总 economy/<日>.jsonl 的 delta（wage / wage_paid / wage_debt / rent / buy / sell / income / expense / adjust / 其他），按**游戏日期**（game_time）落在 [from, to] 的行。
2. 期望对照：日薪账号每个游戏日应有且只有 1 行 wage（金额 = 配置；从开户日起算，开户时刻取检查点 economy.opened）；房租 due_day 落在期间内的账号应有 1 行 rent（金额 = items 合计）；
   小克时薪只报实际（在岗小时沙盒按在场计，脚本不知道她在不在）。
3. 余额恒等：initial_gold + Σ所有 economy 行 delta（全部文件，不限期间）== 检查点 balances[账号]（在线玩家的 gold 以检查点为准；差额 ≠ 0 列出）。
任一对照不符 → 退出码 1。不改任何数据。
"""
from __future__ import annotations

import argparse, json, sqlite3, sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

GAME_TZ = timezone(timedelta(hours=8))


def days(a: date, b: date):
    d = a
    while d <= b:
        yield d; d += timedelta(days=1)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True); ap.add_argument("--from", dest="d0", required=True); ap.add_argument("--to", dest="d1", required=True)
    ap.add_argument("--economy", default=str(Path(__file__).resolve().parent.parent / "game" / "economy.json"))
    ap.add_argument("--db", default=None); ap.add_argument("--json", action="store_true")
    ap.add_argument("--now", default=None, help="当前游戏时刻 ISO（缺省从检查点 time_state 推算；没有检查点用墙钟）")
    a = ap.parse_args()
    data = Path(a.data); d0, d1 = date.fromisoformat(a.d0), date.fromisoformat(a.d1)
    cfg = json.load(open(a.economy, encoding="utf-8"))
    wages = cfg.get("wages", {}); rent = cfg.get("rent", {}) or {}; ig = cfg.get("initial_gold", {})
    rows = []
    for f in sorted((data / "economy").glob("*.jsonl")):
        for ln in f.read_text(encoding="utf-8").splitlines():
            if ln.strip():
                try:
                    rows.append(json.loads(ln))
                except Exception:
                    pass
    db = Path(a.db) if a.db else data / "sandbox.db"
    balances, opened = {}, {}
    now_g = datetime.now(GAME_TZ)
    if db.exists():
        c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        eco = json.loads(dict(c.execute("SELECT key, value FROM meta").fetchall()).get("economy") or "{}")
        balances = {k: int(v) for k, v in (eco.get("balances") or {}).items()}
        opened = {k: datetime.fromtimestamp(float(v), GAME_TZ).date() for k, v in (eco.get("opened") or {}).items()}
        ts = c.execute("SELECT anchor_real, anchor_game, speed, running FROM time_state").fetchone()
        if ts:
            ar, ag, sp, run = ts
            now_g = datetime.fromtimestamp(ag + ((datetime.now().timestamp() - ar) * sp if run else 0.0), GAME_TZ)
    if a.now:
        now_g = datetime.fromisoformat(a.now)
    today_g, now_hm = now_g.date(), now_g.strftime("%H:%M")

    def reached(d: date, hm: str) -> bool:                  # 该游戏日的结算时刻是否已到
        return d < today_g or (d == today_g and now_hm >= hm)
    # 1. 期间表
    def gday(r):
        try:
            return datetime.fromisoformat(r["game_time"]).date()
        except Exception:
            return None
    period = [r for r in rows if (g := gday(r)) and d0 <= g <= d1]
    tbl: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    cnt: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    wage_days: dict[str, set] = defaultdict(set)
    for r in period:
        acc = r.get("account") or r.get("entity") or "?"
        tbl[acc][r["kind"]] += int(r.get("delta", 0)); cnt[acc][r["kind"]] += 1
        if r["kind"] == "wage":
            wage_days[acc].add(gday(r))
    problems = []
    # 2. 期望：日薪
    expect = {}
    for acc, w in wages.items():
        if w.get("kind") != "daily":
            continue
        start = max(d0, opened.get(acc, d0)) if acc in opened else None
        exp_days = [d for d in days(start, d1) if reached(d, w.get("pay_at", "00:00"))] if start else []
        exp_amt = len(exp_days) * int(w["amount"])
        expect[acc] = {"wage_expected": exp_amt, "wage_days_expected": len(exp_days), "wage_days_actual": len(wage_days.get(acc, set())), "opened": str(opened.get(acc)) if acc in opened else "未开户（不发）"}
        if acc in opened and (tbl[acc]["wage"] != exp_amt or len(wage_days[acc]) != len(exp_days)):
            problems.append(f"{acc} 日薪：期望 {len(exp_days)} 天 × {w['amount']} = {exp_amt}，实际 {len(wage_days[acc])} 天 {tbl[acc]['wage']}")
        if acc not in opened and tbl[acc]["wage"]:
            problems.append(f"{acc} 未开户却有日薪 {tbl[acc]['wage']}")
    # 2. 期望：房租
    if rent.get("enabled"):
        due_day = int(rent.get("due_day", 1))
        dues = [d for d in days(d0, d1) if d.day == due_day and reached(d, rent.get("due_at", "08:00"))]
        for acc, items in (rent.get("items") or {}).items():
            amt = -sum(int(x.get("amount", 0)) for x in items)
            exp = amt * len([d for d in dues if acc in opened and opened[acc] <= d])
            expect.setdefault(acc, {})["rent_expected"] = exp
            if tbl[acc]["rent"] != exp:
                problems.append(f"{acc} 房租：期望 {exp}（期内到期日 {[str(d) for d in dues]}），实际 {tbl[acc]['rent']}（{cnt[acc]['rent']} 行）")
    # 3. 余额恒等
    total: dict[str, int] = defaultdict(int)
    for r in rows:
        total[r.get("account") or r.get("entity") or "?"] += int(r.get("delta", 0))
    bal_check = {}
    for acc, b in sorted(balances.items()):
        init = int(ig.get(acc, ig.get("default", 0)))
        calc = init + total.get(acc, 0)
        bal_check[acc] = {"initial": init, "sum_delta": total.get(acc, 0), "computed": calc, "checkpoint": b, "diff": b - calc}
        if b != calc:
            problems.append(f"{acc} 余额：初始 {init} + 流水 {total.get(acc, 0)} = {calc}，检查点 {b}（差 {b - calc}）")
    out = {"range": [a.d0, a.d1], "rows_in_period": len(period), "period": {k: dict(v) for k, v in tbl.items()}, "expect": expect, "balance": bal_check, "problems": problems}
    if a.json:
        print(json.dumps(out, ensure_ascii=False, indent=1))
    else:
        print(f"期间 {a.d0} → {a.d1}（按游戏日期；游戏当前 {now_g.isoformat(timespec='minutes')}）：{len(period)} 行流水；检查点 {db if db.exists() else '无'}")
        kinds = sorted({k for v in tbl.values() for k in v})
        print("账号".ljust(16) + "".join(k.rjust(11) for k in kinds))
        for acc in sorted(set(tbl) | set(balances)):
            print(acc.ljust(16) + "".join(str(tbl[acc].get(k, 0)).rjust(11) for k in kinds))
        print("\n期望对照：")
        for acc, e in expect.items():
            print(f"  {acc}: {e}")
        print("\n余额恒等（初始 + 全部流水 vs 检查点）：")
        for acc, b in bal_check.items():
            print(f"  {acc}: {b['initial']} + {b['sum_delta']} = {b['computed']} | 检查点 {b['checkpoint']} | 差 {b['diff']}")
        print("\n结论：" + ("全部对上" if not problems else "\n  - " + "\n  - ".join(problems)))
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
