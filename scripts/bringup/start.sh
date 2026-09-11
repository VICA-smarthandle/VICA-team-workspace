#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"

VICA_QUIET=1
source "$DIR/vica_env.sh"
unset VICA_QUIET
warn() { echo "  [경고] $1"; }
echo "[점검]"
command -v terminator >/dev/null || { echo "  terminator 가 없습니다. sudo apt install terminator"; exit 1; }
[ -f "$VICA_ROS_WS/install/setup.bash" ] || warn "로봇 저장소 install 이 없습니다 → cd $VICA_ROS_WS && colcon build"
[ -f "$VICA_MAP" ]                        || warn "지도 파일이 없습니다: $VICA_MAP"
[ -x "$VICA_VOICE/.venv/bin/python" ]     || warn "음성 .venv 파이썬이 없습니다: $VICA_VOICE/.venv"
[ -f "$VICA_VOICE/.env" ]                 || warn "음성 .env 가 없습니다 → OLLAMA_API_KEY 설정 필요(의도 해석에 필요)"

cat <<'SAFETY'

┌──────────────────────────────────────────────────────────────┐
│  ⚠️  실기 종단은 [미검증](P0)이다.                            │
│  처음에는 반드시 로봇 바퀴를 공중에 띄운 상태로 시작하고,     │
│  먼저 "멈춰"라고 말해 E-stop 이 바퀴를 즉시 세우는지 확인한   │
│  뒤에 목적지 명령을 준다. 절차: docs/voice-field-test.md      │
└──────────────────────────────────────────────────────────────┘
SAFETY
read -r -p "위 안전 절차를 지키겠습니까? 계속하려면 엔터 (취소 Ctrl+C) > " _

CFG="$(mktemp --suffix=.terminator)"
trap 'rm -f "$CFG"' EXIT
sed "s|@DIR@|$DIR|g" "$DIR/layout.terminator.in" > "$CFG"

echo "[실행] terminator 레이아웃 'vica_bringup'"
terminator -g "$CFG" -l vica_bringup
