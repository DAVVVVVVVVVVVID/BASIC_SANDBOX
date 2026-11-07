#!/usr/bin/env bash
# 一机多镇：起一个独立的沙盒实例。所有可变路径都走参数 / 环境变量，实例之间没有共享文件。
#
#   scripts/run_town.sh --port 8010 --data run/data/m2a [--self-url http://127.0.0.1:8310] [--log run/data/m2a.log]
#                       [--cors http://localhost:5183] [--host 127.0.0.1] [--tz Asia/Shanghai] [--seed 2]
#                       [--env K=V ...] [--no-sync] [--scenario] [--fg]
#   --scenario：开 SANDBOX_SCENARIO=1（行为验收夹具 POST /admin/scenario，只给 bench 镇）
#   --map DIR|NAME：地图目录（SANDBOX_MAP_DIR），如 game/maps/v1，或名字 v1 / m1c / legacy_v0；不给则按 SANDBOX_MAP 环境变量（W11 冻结开关，默认 v0）
#
# 与总控 townctl.py 的 start() 对齐：townctl 传 SANDBOX_DATA_DIR / SELF_URL / SANDBOX_TZ 与 towns.yaml 的 sandbox_env
# （SANDBOX_SEED、SELF_SYNC），这里分别对应 --data / --self-url / --tz / --seed / --env；日志由 --log（townctl 自己重定向）。
# 隔离点：SANDBOX_DATA_DIR（检查点 sandbox.db、actions/*.jsonl、chat/*.jsonl、pid 文件）、SELF_URL、日志文件。
# 端口先查 README 第 9 条的登记（主镇 8000；其他镇 k：8000+10k）。
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT=8000; DATA=""; SELF_URL="${SELF_URL:-http://127.0.0.1:8100}"; LOG=""; HOST=127.0.0.1; CORS=""; SYNC=1; FG=0
TZ_NAME="${SANDBOX_TZ:-Asia/Shanghai}"; SEED="${SANDBOX_SEED:-}"; EXTRA_ENV=(); SCENARIO=0; MAP_DIR="${SANDBOX_MAP_DIR:-}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --port) PORT="$2"; shift 2;;
    --data) DATA="$2"; shift 2;;
    --self-url) SELF_URL="$2"; shift 2;;
    --log) LOG="$2"; shift 2;;
    --host) HOST="$2"; shift 2;;
    --cors) CORS="$2"; shift 2;;
    --tz) TZ_NAME="$2"; shift 2;;
    --seed) SEED="$2"; shift 2;;
    --env) EXTRA_ENV+=("$2"); shift 2;;
    --no-sync) SYNC=0; shift;;
    --scenario) SCENARIO=1; shift;;
    --map) MAP_DIR="$2"; shift 2;;
    --fg) FG=1; shift;;
    -h|--help) sed -n '2,12p' "$0"; exit 0;;
    *) echo "unknown arg: $1" >&2; exit 2;;
  esac
done
[[ -z "$DATA" ]] && DATA="$HERE/data/town_$PORT"
mkdir -p "$DATA"
DATA="$(cd "$DATA" && pwd)"
[[ -z "$LOG" ]] && LOG="$DATA/sandbox.log"
if ss -ltn 2>/dev/null | awk '{print $4}' | grep -q ":$PORT\$"; then
  echo "port $PORT already in use (check handoffs/README.md 第 9 条 端口登记)" >&2; exit 1
fi
export SANDBOX_DATA_DIR="$DATA" SELF_URL="$SELF_URL" SELF_SYNC="$SYNC" SANDBOX_TZ="$TZ_NAME"
[[ -n "$CORS" ]] && export SANDBOX_CORS_ORIGINS="$CORS"
[[ -n "$SEED" ]] && export SANDBOX_SEED="$SEED"
[[ "$SCENARIO" == 1 ]] && export SANDBOX_SCENARIO=1
if [[ -n "$MAP_DIR" ]]; then                       # W11：--map 可给目录，也可给名字（v1 / m1c / legacy_v0 → game/maps/<name>）
  [[ -d "$MAP_DIR" ]] || MAP_DIR="$HERE/game/maps/$MAP_DIR"
  export SANDBOX_MAP_DIR="$(cd "$MAP_DIR" && pwd)"
fi
for kv in "${EXTRA_ENV[@]:-}"; do [[ -n "$kv" ]] && export "$kv"; done
echo "sandbox :$PORT  data=$DATA  self=$SELF_URL  sync=$SYNC  tz=$TZ_NAME  seed=${SEED:-none}  scenario=$SCENARIO  map=${MAP_DIR:-default}  log=$LOG"
cd "$HERE"
if [[ "$FG" == 1 ]]; then
  exec uv run uvicorn main:app --host "$HOST" --port "$PORT"
else
  nohup uv run uvicorn main:app --host "$HOST" --port "$PORT" >>"$LOG" 2>&1 &
  echo $! > "$DATA/sandbox.pid"
  echo "pid $(cat "$DATA/sandbox.pid") (stop: kill \$(cat $DATA/sandbox.pid))"
fi
