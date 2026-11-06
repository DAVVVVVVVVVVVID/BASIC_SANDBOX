#!/usr/bin/env bash
# 一机多镇：起一个独立的沙盒实例。所有可变路径都走参数 / 环境变量，实例之间没有共享文件。
#
#   scripts/run_town.sh --port 8010 --data run/data/m2a [--self-url http://127.0.0.1:8310] [--log run/data/m2a.log]
#                       [--cors http://localhost:5183] [--host 127.0.0.1] [--no-sync] [--fg]
#
# 隔离点：SANDBOX_DATA_DIR（检查点 sandbox.db、actions/*.jsonl、phone 等全部在此目录下）、SELF_URL、日志文件、
# pid 文件 <data>/sandbox.pid。端口先查 README 第 9 条的登记（主镇 8000；其他镇 k：8000+10k）。
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT=8000; DATA=""; SELF_URL="${SELF_URL:-http://127.0.0.1:8100}"; LOG=""; HOST=127.0.0.1; CORS=""; SYNC=1; FG=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --port) PORT="$2"; shift 2;;
    --data) DATA="$2"; shift 2;;
    --self-url) SELF_URL="$2"; shift 2;;
    --log) LOG="$2"; shift 2;;
    --host) HOST="$2"; shift 2;;
    --cors) CORS="$2"; shift 2;;
    --no-sync) SYNC=0; shift;;
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
export SANDBOX_DATA_DIR="$DATA" SELF_URL="$SELF_URL" SELF_SYNC="$SYNC"
[[ -n "$CORS" ]] && export SANDBOX_CORS_ORIGINS="$CORS"
echo "sandbox :$PORT  data=$DATA  self=$SELF_URL  sync=$SYNC  log=$LOG"
cd "$HERE"
if [[ "$FG" == 1 ]]; then
  exec uv run uvicorn main:app --host "$HOST" --port "$PORT"
else
  nohup uv run uvicorn main:app --host "$HOST" --port "$PORT" >>"$LOG" 2>&1 &
  echo $! > "$DATA/sandbox.pid"
  echo "pid $(cat "$DATA/sandbox.pid") (stop: kill \$(cat $DATA/sandbox.pid))"
fi
