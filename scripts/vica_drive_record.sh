#!/bin/bash

NAME=${1:-run$(date +%H%M%S)}
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

S=$(ip -br link show can1 2>/dev/null | awk '{print $2}')
[ "$S" = "UP" ] && ok "can1 UP" || bad "can1 이 $S 다. 매뉴얼 ①절 세 줄로 복구한다"

B=$(ip -details link show can1 2>/dev/null | grep -oE 'bitrate [0-9]+' | head -1)
[ "$B" = "bitrate 500000" ] && ok "$B" || bad "bitrate 가 '$B' 다. 500000 이어야 한다"

NODES=$(ros2 node list 2>/dev/null)
for n in emergency_stop_node safety_supervisor_node app_emergency_node \
         mdrobot_can_keyboard_knob_node robot_health_monitor_node; do
  echo "$NODES" | grep -q "$n" && ok "노드 $n" || bad "노드 $n 없음"
done
for n in controller_server planner_server bt_navigator amcl; do
  echo "$NODES" | grep -q "$n" && ok "노드 $n" || warn "노드 $n 없음 (Nav2 미기동?)"
done

P=$(ros2 topic info /cmd_vel_req 2>/dev/null | grep -oE 'Publisher count: [0-9]+' | grep -oE '[0-9]+$')
S1=$(ros2 topic info /cmd_vel_req 2>/dev/null | grep -oE 'Subscription count: [0-9]+' | grep -oE '[0-9]+$')
[ "${P:-0}" -ge 1 ] && ok "/cmd_vel_req 발행자 $P" || bad "/cmd_vel_req 발행자 0 — Nav2 remap 확인"
[ "${S1:-0}" -ge 1 ] && ok "/cmd_vel_req 구독자 $S1 (Safety)" || bad "/cmd_vel_req 구독자 0"

P2=$(ros2 topic info /cmd_vel_safe 2>/dev/null | grep -oE 'Publisher count: [0-9]+' | grep -oE '[0-9]+$')
S2=$(ros2 topic info /cmd_vel_safe 2>/dev/null | grep -oE 'Subscription count: [0-9]+' | grep -oE '[0-9]+$')
[ "${P2:-0}" -ge 1 ] && ok "/cmd_vel_safe 발행자 $P2" || bad "/cmd_vel_safe 발행자 0"
[ "${S2:-0}" -ge 1 ] && ok "/cmd_vel_safe 구독자 $S2 (motor)" || bad "/cmd_vel_safe 구독자 0 — 모터가 못 받는다"

NV_TOPIC=/nvblox_node/static_map_slice
NV=$(ros2 topic info "$NV_TOPIC" 2>/dev/null)
if ! echo "$NV" | grep -q 'Publisher count:'; then
  warn "$NV_TOPIC 없음 — nvblox_node 미기동. 이 회차는 라이다만 본다"
else
  NP=$(echo "$NV" | grep -oE 'Publisher count: [0-9]+' | grep -oE '[0-9]+$')
  NS=$(echo "$NV" | grep -oE 'Subscription count: [0-9]+' | grep -oE '[0-9]+$')
  [ "${NP:-0}" -ge 1 ] && ok "$NV_TOPIC 발행자 $NP (nvblox_node)" \
    || warn "$NV_TOPIC 발행자 0 — nvblox_node 가 죽었다. 3D 장애물이 안 들어온다"
  [ "${NS:-0}" -ge 1 ] && ok "$NV_TOPIC 구독자 $NS (costmap nvblox_layer)" \
    || warn "$NV_TOPIC 구독자 0 — nvblox_layer 미부착. 3D 보정 없이 주행한다"
fi

echo
echo "=== 안전 상태 (참고 — 여기서 막지는 않는다) ==="
echo -n "  래치 /estop_state : "; ros2 topic echo /estop_state --once 2>/dev/null | head -1
echo -n "  게이트 /safety_state: "; ros2 topic echo /safety_state --once 2>/dev/null | head -1

echo
if [ "$fail" -gt 0 ]; then
  echo "  ❌ 실패 $fail 건. 고치고 다시 실행한다."
  exit 1
fi
echo "  ✅ 사전 점검 통과"

[ "$CHECK_ONLY" = "--check-only" ] && { echo "  (--check-only 라 기록하지 않는다)"; exit 0; }

RECORD_NVBLOX=${VICA_RECORD_NVBLOX:-0}
NVBLOX_TOPICS=""
if [ "$RECORD_NVBLOX" = "1" ]; then
  NVBLOX_TOPICS=/nvblox_node/static_map_slice
fi

echo
echo "=== 기록 시작: $OUT ==="
if [ -n "$NVBLOX_TOPICS" ]; then
  echo "  nvblox 슬라이스 포함 (VICA_RECORD_NVBLOX=1). 약 2.5 MB/s = 10분에 약 1.5 GB."
  echo "  남은 용량: $(df -h "$HOME" 2>/dev/null | awk 'NR==2{print $4}')"
else
  echo "  nvblox 슬라이스 제외. 검증 회차에는 VICA_RECORD_NVBLOX=1 을 붙인다."
fi
echo "  Ctrl+C 로 멈춘다."
mkdir -p "$(dirname "$OUT")"

exec ros2 bag record -o "$OUT" \
  $NVBLOX_TOPICS \
  /cmd_vel_req /cmd_vel_safe \
  /odom /wheel/odom /imu/base_link /amcl_pose /tf /tf_static \
  /scan \
  `# 2026-08-30: 깊이를 2D 로 눌러 costmap 에 넣게 되면서(NAV2-B9) 이 토픽이 없으면` \
  `# "라이다가 본 것인가 카메라가 본 것인가"를 나중에 못 가린다. 실제로 통창 앞` \
  `# 멈춤을 진단하려다 막혔다. 173빔 x 15 Hz 라 용량 부담은 거의 없다.` \
  /camera/depth_scan \
  /plan /local_plan \
  /speed_limit \
  /robot_status /robot/health /robot/events /diagnostics_agg \
  /estop_state /safety_state /app_estop_state /motor/can_ok \
  /rosout \
  /local_costmap/costmap /global_costmap/costmap \
  /navigate_to_pose/_action/status
