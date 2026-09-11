#!/bin/bash

NAME=${1:-map$(date +%H%M%S)}
CHECK_ONLY=${2:-}
OUT=$HOME/vica_data/bags/$NAME

source /opt/ros/humble/setup.bash
source $HOME/VICA-smarthandle/vica_ros2_ws/install/setup.bash
export ROS_DOMAIN_ID=7
export ROS_LOCALHOST_ONLY=0
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp

fail=0
ok()   { printf "  \033[32mOK\033[0m   %s\n" "$1"; }
bad()  { printf "  \033[31mNG\033[0m   %s\n" "$1"; fail=$((fail+1)); }
warn() { printf "  \033[33m--\033[0m   %s\n" "$1"; }

echo "=== 사전 점검 ==="

NODES=$(ros2 node list 2>/dev/null)

for n in cartographer_node ekf_node encoder_feedback; do
  C=$(pgrep -xc "${n:0:15}" 2>/dev/null)
  case "${C:-0}" in
    0) bad "$n 이 안 떠 있다" ;;
    1) ok  "$n 1개" ;;
    *) bad "$n 이 $C 개다 — 두 벌이 돌고 있다. 하나를 내린다" ;;
  esac
done

for t in /odom /wheel/odom; do
  P=$(ros2 topic info "$t" 2>/dev/null | grep -oE 'Publisher count: [0-9]+' | grep -oE '[0-9]+$')
  case "${P:-0}" in
    1) ok  "$t 발행자 1" ;;
    0) bad "$t 발행자 0 — motor 칸이 먼저다. encoder_feedback 은 스스로 요청하지 않는다" ;;
    *) bad "$t 발행자 $P — 중복 발행이다" ;;
  esac
done

S=$(ros2 topic info /scan 2>/dev/null | grep -oE 'Publisher count: [0-9]+' | grep -oE '[0-9]+$')
[ "${S:-0}" -eq 1 ] && ok "/scan 발행자 1" || bad "/scan 발행자 ${S:-0}"

if echo "$NODES" | grep -q imu_base_link_adapter; then
  ok "imu_base_link_adapter 떠 있음"
  warn "자이로 보정 성공 여부는 그 칸 로그에서 직접 본다:"
  warn "  성공 → 'Gyro bias calibrated over 1000 samples'"
  warn "  실패 → 'calibration aborted: motion detected' (노드를 다시 띄운다)"
else
  warn "imu_base_link_adapter 없음 — EKF 가 IMU 없이 돈다"
fi

AVAIL=$(df -BG --output=avail "$HOME" 2>/dev/null | tail -1 | tr -dc '0-9')
[ "${AVAIL:-0}" -ge 5 ] && ok "여유 공간 ${AVAIL}G" || bad "여유 공간 ${AVAIL}G — 5G 이상 필요"

echo
if [ "$fail" -gt 0 ]; then
  printf "\033[31m사전 점검 %d건 실패. 기록을 시작하지 않는다.\033[0m\n" "$fail"
  exit 1
fi
printf "\033[32m사전 점검 통과\033[0m\n"
[ "$CHECK_ONLY" = "--check-only" ] && exit 0

TOPICS="/scan /tf /tf_static /odom /wheel/odom /imu/base_link /joint_states \
/map /submap_list /trajectory_node_list /constraint_list"

echo
echo "=== 기록 시작 ==="
echo "  이름   $NAME"
echo "  위치   $OUT"
echo "  토픽   $(echo $TOPICS | tr ' ' '\n' | wc -l) 개"
echo
echo "  Ctrl+C 로 멈춘다. 멈춘 뒤 지도 저장은 save 칸에서 한다."
echo
exec ros2 bag record -o "$OUT" $TOPICS
