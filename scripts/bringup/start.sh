#!/usr/bin/env bash
# VICA 음성 주행 노드 6개를 Terminator 격자 한 창으로 띄운다.
#
#   ./start.sh
#
# 프로젝트 전역 Terminator 설정(~/.config/terminator/config)은 건드리지 않는다.
# 이 스크립트가 만든 임시 설정으로만 실행한다.
set -euo pipefail

DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"

# ── 가벼운 사전 점검 (막지는 않고 경고만) ──
# VICA_QUIET: 여기서는 창별 인트로 안내를 찍지 않는다(각 창이 열릴 때 찍힘).
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

# ── 템플릿의 @DIR@ 치환 후 임시 설정으로 실행 ──
CFG="$(mktemp --suffix=.terminator)"
trap 'rm -f "$CFG"' EXIT
sed "s|@DIR@|$DIR|g" "$DIR/layout.terminator.in" > "$CFG"

echo "[실행] terminator 레이아웃 'vica_bringup'"
terminator -g "$CFG" -l vica_bringup
