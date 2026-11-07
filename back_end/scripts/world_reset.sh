#!/usr/bin/env bash
# W11 ⑤ 冻结日一键重置：停掉该数据目录的实例 → 归档旧数据 → 空目录起新世界（SANDBOX_MAP=<map>）。
#
#   scripts/world_reset.sh --map v1 --data run/data/sandbox [--port 8000] [--archive-tag v0] [--no-archive] [-- <run_town.sh 其余参数>]
#   例：scripts/world_reset.sh --map v1 --data /home/shan-dw/Project/run/data/bench_v1/sandbox --port 8091 -- --no-sync --scenario --env SANDBOX_TOWN=bench_v1
#
# --map：game/maps/<name>（v1 / m1c / legacy_v0）或目录；--archive-tag：旧数据目录改名为 <data>.<tag>-<时间戳>（默认 v0）；
# --no-archive：直接删除旧数据（慎用）。主镇 8000 冻结日前不要对它跑。
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MAP="v1"; DATA=""; PORT=8000; TAG="v0"; ARCHIVE=1; REST=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --map) MAP="$2"; shift 2;;
    --data) DATA="$2"; shift 2;;
    --port) PORT="$2"; shift 2;;
    --archive-tag) TAG="$2"; shift 2;;
    --no-archive) ARCHIVE=0; shift;;
    --) shift; REST=("$@"); break;;
    -h|--help) sed -n '2,10p' "$0"; exit 0;;
    *) echo "unknown arg: $1" >&2; exit 2;;
  esac
done
[[ -z "$DATA" ]] && { echo "--data 必填" >&2; exit 2; }
if [[ -d "$MAP" ]]; then MAP_DIR="$(cd "$MAP" && pwd)"; else MAP_DIR="$HERE/game/maps/$MAP"; fi
[[ -f "$MAP_DIR/map.json" ]] || { echo "map not found: $MAP_DIR" >&2; exit 2; }
mkdir -p "$(dirname "$DATA")"; DATA="$(cd "$(dirname "$DATA")" && pwd)/$(basename "$DATA")"
# 1) 停实例
if [[ -f "$DATA/sandbox.pid" ]]; then
  PID="$(cat "$DATA/sandbox.pid")"
  if kill -0 "$PID" 2>/dev/null; then
    echo "stopping pid $PID"; kill "$PID"
    for _ in $(seq 1 50); do kill -0 "$PID" 2>/dev/null || break; sleep 0.2; done
    kill -0 "$PID" 2>/dev/null && { echo "pid $PID still alive, kill -9"; kill -9 "$PID" || true; }
  fi
fi
if ss -ltn 2>/dev/null | awk '{print $4}' | grep -q ":$PORT\$"; then
  echo "port $PORT still in use (not ours?) — abort" >&2; exit 1
fi
# 2) 归档 / 清空
if [[ -d "$DATA" ]]; then
  if [[ "$ARCHIVE" == 1 ]]; then
    ARCH="$DATA.$TAG-$(date +%Y%m%d-%H%M%S)"; mv "$DATA" "$ARCH"; echo "archived -> $ARCH"
  else
    rm -rf "$DATA"; echo "removed $DATA"
  fi
fi
mkdir -p "$DATA"
# 3) 起新世界
exec "$HERE/scripts/run_town.sh" --port "$PORT" --data "$DATA" --map "$MAP_DIR" "${REST[@]}"
