#!/bin/bash

VICA_ROS_WS=${VICA_ROS_WS:-$HOME/VICA-smarthandle/vica_ros2_ws}

source /opt/ros/humble/setup.bash
source $VICA_ROS_WS/install/setup.bash
export ROS_DOMAIN_ID=7
export ROS_LOCALHOST_ONLY=0
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp

MAP=$VICA_MAP_ID
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

REQ=$(cat /proc/sys/kernel/random/uuid)

echo "  요청: $NAME  ($ID)"
ros2 service call /vica/mission/request_destination \
  vica_interfaces/srv/RequestDestination \
  "{request_id: '$REQ', map_id: '$MAP', destination_id: '$ID'}" 2>&1 \
  | grep -E "accepted|message" | sed 's/^/  /'
