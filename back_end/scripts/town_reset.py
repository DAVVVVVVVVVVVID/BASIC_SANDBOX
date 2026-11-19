#!/usr/bin/env python3
"""全镇重置（主播 11-19 定：11-20 12:00 起；whale docs/systems/memory-reset-plan.md 总控补）——沙盒侧。

顺序（与总控 runbook 对齐）：
  1. roster   沙盒还在跑或已停都行：从检查点读出现有角色（id / 名字 / 身份 / dnd）→ roster.json
  2. archive  **沙盒必须已停**：数据目录 / school 试跑日志 / interventions 整份打包 + sha256 + MANIFEST；
              原数据目录改名封存（不删），新建空目录；school 只挪走沙盒写的 answers / attendance / submissions / grades，
              A 的课案 / syllabus / a_grades 不动；interventions 改名封存、新建空目录
  3. （总控起沙盒 = 新世界；起 8100；A 按 closeness-init.json 播种）
  4. restore  按原 player id 重建角色（agent 加入时从自我层播种七变量 / closeness；人类阿蝉 closeness 按表写）
  5. verify   核：mapVersion、物件数、角色 id 与身份、位置 = 出生点、金币 = 初值、背包 = 初值、QQ 空、
              school 无试跑日志、term_start = 配置 2026-11-23、closeness 与表一致（agent 读自我层播种结果）

用法：
  python scripts/town_reset.py roster  --data /home/shan-dw/Project/run/data/sandbox --out /path/roster.json
  python scripts/town_reset.py archive --data ... --school /home/shan-dw/Project/run/data/main/school \\
         --interventions /home/shan-dw/Project/run/data/main/interventions --port 8000 --out /home/shan-dw/Project/run/archive/reset-20261120
  python scripts/town_reset.py restore --base http://127.0.0.1:8000 --roster roster.json --closeness <closeness-init.json>
  python scripts/town_reset.py verify  --base http://127.0.0.1:8000 --roster roster.json --closeness <closeness-init.json> --school <dir>
鉴权：restore 用环境变量 SANDBOX_ADMIN_TOKEN 或 SELF_TOKEN（与沙盒进程同一份 ~/.env）。
"""
import argparse, hashlib, json, os, shutil, socket, sqlite3, subprocess, sys, tarfile, time, urllib.parse, urllib.request
from datetime import datetime
from pathlib import Path

SCHOOL_LOGS = ("answers.jsonl", "attendance.jsonl", "submissions.jsonl", "grades.jsonl")   # 沙盒写的；A 的 a_grades / 课案 / syllabus 不动


def _http(base, method, path, body=None, token=None):
    h = {"content-type": "application/json"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(base + urllib.parse.quote(path, safe="/?=&%"), method=method,
                                 data=json.dumps(body).encode() if body is not None else None, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read().decode() or "null")
    except urllib.error.HTTPError as e:
        return e.code, (json.loads(e.read().decode() or "null") if e.headers.get_content_type() == "application/json" else None)


def _sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def _port_busy(port: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def cmd_roster(a):
    db = Path(a.data) / "sandbox.db"
    c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    rows = []
    for pid, pj in c.execute("SELECT id, player FROM players"):
        d = json.loads(pj)
        rows.append({"player_id": pid, "name": d.get("name"), "controller": d.get("controller"), "agent_id": d.get("agent_id"),
                     "dnd": bool(d.get("dnd")), "dnd_auto": bool(d.get("dnd_auto"))})
    c.close()
    rows.sort(key=lambda r: (r["controller"] != "human", r["player_id"]))
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps({"from": str(db), "at": datetime.now().astimezone().isoformat(timespec="seconds"), "players": rows},
                                      ensure_ascii=False, indent=1), encoding="utf-8")
    for r in rows:
        print(f"  {r['player_id']:<20} {r['name']:<6} {r['controller']:<6} agent_id={r['agent_id']} dnd={r['dnd']} dnd_auto={r['dnd_auto']}")
    print(f"roster → {a.out}（{len(rows)} 人）")


def cmd_archive(a):
    data = Path(a.data).resolve(); out = Path(a.out).resolve(); ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    if _port_busy(a.port):
        sys.exit(f"端口 {a.port} 还有人在听——沙盒没停，不归档（先停沙盒）")
    pidf = data / "sandbox.pid"
    if pidf.exists():
        try:
            os.kill(int(pidf.read_text().strip()), 0); sys.exit(f"{pidf} 里的进程还活着——先停沙盒")
        except (ProcessLookupError, ValueError):
            pass
    out.mkdir(parents=True, exist_ok=True)
    made = []
    def pack(src: Path, name: str):
        if not src.exists():
            print(f"  （跳过，不存在）{src}"); return
        t0 = time.time(); tp = out / f"{name}.tar.gz"
        with tarfile.open(tp, "w:gz") as tf:
            tf.add(src, arcname=src.name)
        with tarfile.open(tp, "r:gz") as tf:                       # 读回一遍确认能解
            n = sum(1 for _ in tf)
        made.append(tp); print(f"  打包 {src} → {tp.name}（{n} 项，{tp.stat().st_size/1e6:.1f} MB，{time.time()-t0:.0f}s）")
    pack(data, "sandbox-data")
    if a.school:
        pack(Path(a.school), "school")
    if a.interventions:
        pack(Path(a.interventions), "interventions")
    if a.log and Path(a.log).exists():
        shutil.copy2(a.log, out / Path(a.log).name); made.append(out / Path(a.log).name)
    if a.roster and Path(a.roster).exists():
        if Path(a.roster).resolve() != (out / "roster.json").resolve():
            shutil.copy2(a.roster, out / "roster.json")
        made.append(out / "roster.json")
    lines = [f"{_sha(p)}  {p.name}" for p in made]
    (out / "MANIFEST.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")
    # 回初始：原目录改名封存（不删），新建空目录
    sealed = data.with_name(f"{data.name}.closed-test-{ts}")
    data.rename(sealed); data.mkdir()
    moved = []
    if a.school:
        sch = Path(a.school); keep = sch / f"_closed-test-{ts}"; keep.mkdir(exist_ok=True)
        for f in SCHOOL_LOGS:
            if (sch / f).exists():
                shutil.move(str(sch / f), keep / f); moved.append(f)
    iv_sealed = None
    if a.interventions and Path(a.interventions).exists():
        iv = Path(a.interventions).resolve(); iv_sealed = iv.with_name(f"{iv.name}.closed-test-{ts}"); iv.rename(iv_sealed); iv.mkdir()
    (out / "MANIFEST.txt").write_text("\n".join([
        f"全镇重置归档（沙盒侧）{datetime.now().astimezone().isoformat(timespec='seconds')}",
        f"数据目录 {data} → 封存为 {sealed}（原样，未删）；新建空目录",
        f"school {a.school}：{', '.join(moved) or '无'} → {Path(a.school) / f'_closed-test-{ts}' if a.school else '-'}（A 的课案 / syllabus / a_grades 未动）",
        f"interventions → 封存为 {iv_sealed}；新建空目录" if iv_sealed else "interventions：未指定 / 不存在",
        "sha256 见 MANIFEST.sha256", ""]), encoding="utf-8")
    print("\n".join(lines)); print(f"MANIFEST → {out}；数据目录已清空（封存 {sealed.name}）")


def _table(path):
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    return d.get("closeness_init", d)


def cmd_restore(a):
    tok = os.environ.get("SANDBOX_ADMIN_TOKEN") or os.environ.get("SELF_TOKEN")
    roster = json.loads(Path(a.roster).read_text(encoding="utf-8"))["players"]
    table = _table(a.closeness) if a.closeness else {}
    for r in roster:
        body = {"player_id": r["player_id"], "name": r["name"], "controller": r["controller"],
                "profile": {"agent_id": r["agent_id"]} if r.get("agent_id") else None, "online": False}
        if r["controller"] == "human":
            body["dnd"] = r.get("dnd", True)
        st, res = _http(a.base, "POST", "/admin/player/restore", body, tok)
        if st != 200:
            sys.exit(f"restore {r['player_id']} 失败：HTTP {st} {res}")
        p = res["player"]
        print(f"  重建 {p['id']:<20} {p['name']:<6} {p['controller']:<6} pos=({p['position']['x']},{p['position']['y']}) gold={p.get('gold')} dnd={p.get('dnd')} dnd_auto={p.get('dnd_auto')}")
        if r["controller"] == "human" and r.get("agent_id") in table:      # 人类没有自我层播种：按表写（新世界里从 0 起，delta = 初值）
            effs = [{"type": "closeness_delta", "target": t, "value": float(v)} for t, v in table[r["agent_id"]].items()]
            st, res = _http(a.base, "POST", f"/player/{r['player_id']}/effects", {"effects": effs, "source": "reset", "event": "town_reset_closeness"})
            print(f"    closeness ← 表 {table[r['agent_id']]}：HTTP {st}")
    print("restore 完成；agent 等 C 用原 id rejoin")


def cmd_verify(a):
    roster = json.loads(Path(a.roster).read_text(encoding="utf-8"))["players"]
    table = _table(a.closeness) if a.closeness else {}
    bad = []
    def check(ok, msg):
        print(("  ✓ " if ok else "  ✗ ") + msg)
        if not ok:
            bad.append(msg)
    _, w = _http(a.base, "GET", "/world")
    ws = w["worldState"]
    check(ws["mapVersion"].endswith(a.map_version), f"mapVersion {ws['mapVersion']}")
    check(len(w["objects"]) == a.objects, f"物件 {len(w['objects'])}（应 {a.objects}）")
    ids = {p["id"] for p in w["players"]}
    check(ids == {r["player_id"] for r in roster}, f"角色 {len(ids)} 人，id 与名单一致：{sorted(ids)}")
    _, tt = _http(a.base, "GET", "/school/timetable")
    check(tt.get("term_start") == a.term_start and tt.get("term_start_source") == "config", f"开学日 {tt.get('term_start')}（来源 {tt.get('term_start_source')}）")
    if a.school:
        left = [f for f in SCHOOL_LOGS if (Path(a.school) / f).exists()]
        check(not left, f"school 试跑日志已清：{left or '无残留'}")
    _, wa = _http(a.base, "GET", "/world?view=admin")                  # 不用 GET /player：对人类那是心跳（会把离线的阿蝉标成在线）
    byid = {p["id"]: p for p in wa["players"]}
    for r in roster:
        p = byid.get(r["player_id"])
        st, sv = _http(a.base, "GET", f"/player/{r['player_id']}/state")   # 不刷心跳
        if p is None or st != 200:
            check(False, f"{r['player_id']} 不在 /world 或 /state HTTP {st}"); continue
        p = {**p, "closeness": sv.get("closeness") or {}}
        _, ib = _http(a.base, "GET", f"/qq/inbox?player={r['player_id']}")
        inv = sorted((e.get("type") or e.get("item"), e.get("qty", 1)) for e in p.get("inventory") or [])
        check(ib.get("total", 0) == 0, f"{r['name']} QQ 空（{ib.get('total')} 条）")
        print(f"     {r['name']} pos=({p['position']['x']},{p['position']['y']}) gold={p.get('gold')} inv={inv} dnd={p.get('dnd')} online={p.get('online')}")
        if r.get("agent_id") in table:
            want = {k: float(v) for k, v in table[r["agent_id"]].items()}
            got = {k: round(float(v), 3) for k, v in (p.get("closeness") or {}).items()}
            diff = {k: (want.get(k, 0.0), got.get(k, 0.0)) for k in set(want) | set(got) if abs(want.get(k, 0.0) - got.get(k, 0.0)) > a.tol}
            check(not diff, f"{r['name']} closeness 与表一致" + (f"：差异 {diff}（表, 沙盒）" if diff else f" {got}"))
    try:                                                               # v1.4.8 钓鱼个人纪录 = 初始表（只读 agent 的 GET /player；对人类那是心跳）
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from game import fishing as _f
        ini = _f.cfg().get("records_initial") or {}
        for r in roster:
            if r["controller"] != "agent":
                continue
            st, pp = _http(a.base, "GET", f"/player/{r['player_id']}")
            best = ((pp or {}).get("fishing") or {}).get("record", {}).get("best") if st == 200 else None
            want = ini.get(r.get("agent_id"))
            ok = (best is None and want is None) or (best and want and best.get("species") == want["species"] and abs(float(best["weight"]) - float(want["weight"])) < 1e-6)
            check(bool(ok), f"{r['name']} 钓鱼纪录 = 初始表（{(best or {}).get('name')} {(best or {}).get('weight')}）")
    except Exception as e:
        check(False, f"钓鱼纪录核对出错：{e}")
    print("verify:", "全过" if not bad else f"{len(bad)} 项不过")
    sys.exit(1 if bad else 0)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("roster"); s.add_argument("--data", required=True); s.add_argument("--out", required=True)
    s = sub.add_parser("archive"); s.add_argument("--data", required=True); s.add_argument("--out", required=True); s.add_argument("--port", type=int, required=True)
    s.add_argument("--school"); s.add_argument("--interventions"); s.add_argument("--log"); s.add_argument("--roster")
    s = sub.add_parser("restore"); s.add_argument("--base", required=True); s.add_argument("--roster", required=True); s.add_argument("--closeness")
    s = sub.add_parser("verify"); s.add_argument("--base", required=True); s.add_argument("--roster", required=True); s.add_argument("--closeness")
    s.add_argument("--school"); s.add_argument("--term-start", default="2026-11-23"); s.add_argument("--map-version", default="@a18e6a70e84a")
    s.add_argument("--objects", type=int, default=72); s.add_argument("--tol", type=float, default=0.5, help="closeness 容差（播种后到核对之间的自然衰减）")
    a = ap.parse_args()
    {"roster": cmd_roster, "archive": cmd_archive, "restore": cmd_restore, "verify": cmd_verify}[a.cmd](a)


if __name__ == "__main__":
    main()
