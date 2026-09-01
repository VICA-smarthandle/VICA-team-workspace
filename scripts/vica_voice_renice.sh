#!/usr/bin/env bash
# 음성 노드들의 CPU 우선순위를 낮춘다 (nice +10) — 주행 보호 (2026-09-01).
#
# 왜: Jetson 에서 STT·TTS 버스트가 Nav2 컨트롤러(20Hz)와 CPU·메모리 대역을
# 다툰다. 음성이 양보해도 사용자 체감은 수십 ms 지연뿐이지만, 컨트롤러가
# 밀리면 주행이 멈칫한다 — 항상 주행이 이기게 한다.
#
# 사용: 스택 기동 후 1회 실행 (sudo 불필요 — 내 프로세스의 양보라서).
#     bash scripts/vica_voice_renice.sh
# 재기동하면 우선순위가 초기화되므로 다시 실행한다.
set -u

pids=$(pgrep -f 'python[0-9.]* .*-m src\.ros_' || true)
if [ -z "$pids" ]; then
    echo "음성 노드를 찾지 못했다 — 스택 기동 후에 실행할 것"
    exit 1
fi

echo "적용 전:"
ps -o pid,ni,comm,args -p $pids | cut -c1-90
renice -n 10 -p $pids > /dev/null
echo
echo "적용 후 (NI=10 이면 성공):"
ps -o pid,ni,comm,args -p $pids | cut -c1-90
