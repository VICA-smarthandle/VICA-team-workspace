#!/bin/bash
# AMCL 초기 위치를 명령으로 넣는다. RViz의 2D Pose Estimate와 같은 일을 한다.
#
#   bash scripts/vica_set_initial_pose.sh 입구
#   bash scripts/vica_set_initial_pose.sh -5.83 -0.04 90
#   bash scripts/vica_set_initial_pose.sh --list
#
# 왜 필요한가 — RViz가 원격(xrdp)에서 CPU 184 %를 쓰며 느려지면 클릭-드래그
# 제스처가 완성되지 않는다. 2026-08-01에 실제로 그래서 초기 위치를 못 찍었다.
# 배선(/initialpose: rviz -> amcl)은 정상이었다.
#
# AMCL은 대략만 맞으면 라이다로 스스로 보정한다. 정확할 필요는 없다.

VICA_ROS_WS=${VICA_ROS_WS:-$HOME/VICA-smarthandle/vica_ros2_ws}

source /opt/ros/humble/setup.bash
source $VICA_ROS_WS/install/setup.bash
export ROS_DOMAIN_ID=7
export ROS_LOCALHOST_ONLY=0
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp

# 장소 목록은 지도마다 다르다. 현재 지도는 nav2·mission·app 과 같은 규칙으로
# 정한다 — 환경변수 > maps/CURRENT_MAP 순서다.
#
# 2026-08-13 이전에는 여기에 vica_map_0630 이 박혀 있었다. 그래서 0810 지도로
# 주행하면서 0630 의 좌표를 초기 위치로 찍고 있었다. 장소 이름이 양쪽에 다 있으면
# 오류도 나지 않는다 — 로봇이 엉뚱한 곳에 있다고 믿은 채 출발할 뿐이다.
# 2026-09-04: 한글 표시 이름도 받는다. 변환은 vica_map_resolve.py 한 곳이 한다.
_resolved=$(python3 "$(dirname "${BASH_SOURCE[0]}")/vica_map_resolve.py" -- "${VICA_MAP_ID:-}" 2>/dev/null | cut -f1)
[ -n "$_resolved" ] && VICA_MAP_ID=$_resolved
unset _resolved
if [ -z "$VICA_MAP_ID" ]; then
  VICA_MAP_ID=$(head -1 "$VICA_ROS_WS/maps/CURRENT_MAP" 2>/dev/null | tr -d '[:space:]')
fi
if [ -z "$VICA_MAP_ID" ]; then
  echo "[중단] 현재 지도를 알 수 없다."
  echo "       $VICA_ROS_WS/maps/CURRENT_MAP 이 없고 VICA_MAP_ID 도 비어 있다."
  echo "       쓸 수 있는 지도는 여기서 본다:  ls $VICA_ROS_WS/maps/*.yaml"
  echo "       정한 뒤 다시 실행한다:          export VICA_MAP_ID=<지도이름>"
  exit 1
fi

DEST=$HOME/vica_data/destinations/$VICA_MAP_ID/destinations.yaml

echo "  지도: $VICA_MAP_ID"
if [ ! -f "$DEST" ]; then
  echo "  [경고] 이 지도의 목적지 catalog 가 없다: $DEST"
  echo "         장소 이름은 못 쓴다. 좌표로 넣는다: $0 <x> <y> <yaw도>"
fi

if [ "${1:-}" = "--list" ] || [ -z "${1:-}" ]; then
  echo "저장된 장소:"
  python3 -c "
import yaml,sys
d=yaml.safe_load(open('$DEST'))
for x in d['destinations']:
    p=x['pose']
    print(f\"  {x['name']:<10} x={p['x']:7.2f} y={p['y']:7.2f} yaw={p['yaw']:6.1f}\")
" 2>/dev/null
  echo
  echo "사용법: $0 <장소이름>   또는   $0 <x> <y> <yaw도>"
  exit 0
fi

if [ $# -ge 3 ]; then
  X=$1; Y=$2; YAW=$3
else
  read -r X Y YAW < <(python3 -c "
import yaml,sys
d=yaml.safe_load(open('$DEST'))
for x in d['destinations']:
    if x['name']=='$1':
        p=x['pose']; print(p['x'],p['y'],p['yaw']); break
else:
    sys.exit(1)
" 2>/dev/null) || { echo "'$1' 을 찾지 못했다. --list 로 확인한다."; exit 1; }
fi

# 공분산은 RViz 기본값과 같게 둔다. x·y 0.25, yaw 약 0.068 rad^2 이다.
# 0으로 두면 AMCL이 "완벽히 확신한다"고 보고 라이다 보정을 거의 안 한다.
read -r QZ QW < <(python3 -c "
import math
h=math.radians(float('$YAW'))/2
print(math.sin(h), math.cos(h))
")

echo "  초기 위치: x=$X  y=$Y  yaw=${YAW}도"
ros2 topic pub --once /initialpose geometry_msgs/msg/PoseWithCovarianceStamped "{
  header: {frame_id: 'map'},
  pose: {
    pose: {
      position: {x: $X, y: $Y, z: 0.0},
      orientation: {x: 0.0, y: 0.0, z: $QZ, w: $QW}
    },
    covariance: [0.25,0,0,0,0,0,
                 0,0.25,0,0,0,0,
                 0,0,0,0,0,0,
                 0,0,0,0,0,0,
                 0,0,0,0,0,0,
                 0,0,0,0,0,0.06853891945200942]
  }
}" > /dev/null 2>&1

sleep 3
echo
echo "  === map -> odom TF 가 생겼나 ==="
if ros2 run tf2_ros tf2_echo map odom --once 2>/dev/null | grep -q "Translation"; then
  ros2 run tf2_ros tf2_echo map odom --once 2>/dev/null | grep -E "Translation|Rotation: in RPY" | head -2 | sed 's/^/  /'
  echo "  ✅ 초기 위치가 적용됐다"
else
  echo "  ⬜ 아직 없다. 몇 초 더 기다렸다가 다시 확인한다:"
  echo "     ros2 run tf2_ros tf2_echo map odom"
fi
