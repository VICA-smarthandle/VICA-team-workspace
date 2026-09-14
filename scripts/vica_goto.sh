#!/bin/bash
# 목적지를 번호로 골라 Mission Manager에 요청한다.
#
#   bash scripts/vica_goto.sh          목록만 본다
#   bash scripts/vica_goto.sh 4        4번으로 주행 요청
#   bash scripts/vica_goto.sh cancel   진행 중 주행 취소
#
# 왜 번호인가 — 목적지 이름이 한글인데 xfreerdp(RDP) 세션에서 한영 전환이
# 동작하지 않아 이름을 칠 수 없다. 2026-08-01 실기에서 막혔다.
# 서비스가 받는 것은 destination_id(UUID)라 이름은 표시용일 뿐이다.

VICA_ROS_WS=${VICA_ROS_WS:-$HOME/VICA-smarthandle/vica_ros2_ws}

source /opt/ros/humble/setup.bash
source $VICA_ROS_WS/install/setup.bash
export ROS_DOMAIN_ID=7
export ROS_LOCALHOST_ONLY=0
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp

# 현재 지도. nav2·mission·app·initpose 와 같은 규칙으로 정한다 —
# 환경변수 > maps/CURRENT_MAP 순서다. 옛 fallback 은 vica_map_0630 고정이라
# 터미네이터 밖에서 단독 실행하면 조용히 옛 지도의 목적지를 보냈다.
# 2026-09-04: 한글 표시 이름도 받는다. 이름 -> id 변환은 vica_map_resolve.py 한 곳이
# 한다(터미네이터 rc 와 같은 도구). 실패하면 옛 방식(id 그대로)으로 내려간다.
MAP=$(python3 "$(dirname "${BASH_SOURCE[0]}")/vica_map_resolve.py" -- "${VICA_MAP_ID:-}" 2>/dev/null | cut -f1)
if [ -z "$MAP" ]; then
  MAP=$VICA_MAP_ID
fi
if [ -z "$MAP" ]; then
  MAP=$(head -1 "$VICA_ROS_WS/maps/CURRENT_MAP" 2>/dev/null | tr -d '[:space:]')
fi
if [ -z "$MAP" ]; then
  echo "[중단] 현재 지도를 알 수 없다. export VICA_MAP_ID=<이름> 뒤 다시 실행한다."
  exit 1
fi
DEST=$HOME/vica_data/destinations/$MAP/destinations.yaml

if [ "${1:-}" = "cancel" ]; then
  echo "  주행 취소 요청"
  ros2 topic pub --once /navigate_to_pose/_action/cancel_goal \
    action_msgs/msg/GoalInfo "{}" >/dev/null 2>&1
  echo "  완료. /cmd_vel_safe 로 정지 확인:"
  ros2 topic echo /cmd_vel_safe --once 2>/dev/null | grep -A1 linear | tail -1
  exit 0
fi

list() {
  python3 -c "
import yaml
d=yaml.safe_load(open('$DEST'))
for i,x in enumerate(d['destinations'],1):
    p=x['pose']
    print(f\"  {i}. {x['name']:<10} x={p['x']:7.2f} y={p['y']:7.2f} yaw={p['yaw']:6.1f}\")
" 2>/dev/null
}

if [ -z "${1:-}" ]; then
  echo "지도: $MAP"
  list
  echo
  echo "사용법: $0 <번호>    /    $0 cancel"
  exit 0
fi

read -r ID NAME < <(python3 -c "
import yaml,sys
d=yaml.safe_load(open('$DEST'))
n=int('$1')
ds=d['destinations']
if not (1<=n<=len(ds)): sys.exit(1)
print(ds[n-1]['id'], ds[n-1]['name'])
" 2>/dev/null) || { echo "번호가 범위를 벗어났다."; list; exit 1; }

# request_id도 UUID여야 한다. Mission Manager가 형식을 검사하며,
# 'cli-1234' 같은 값은 "request_id와 destination_id는 UUID여야 합니다"로 거부된다.
REQ=$(cat /proc/sys/kernel/random/uuid)

echo "  요청: $NAME  ($ID)"
ros2 service call /vica/mission/request_destination \
  vica_interfaces/srv/RequestDestination \
  "{request_id: '$REQ', map_id: '$MAP', destination_id: '$ID'}" 2>&1 \
  | grep -E "accepted|message" | sed 's/^/  /'
