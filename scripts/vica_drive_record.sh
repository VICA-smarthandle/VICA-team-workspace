#!/bin/bash
# 주행 테스트 기록. 사전 점검을 먼저 하고, 통과해야 기록을 시작한다.
#
#   bash scripts/vica_drive_record.sh run01
#   bash scripts/vica_drive_record.sh run01 --check-only    사전 점검만
#
# 왜 사전 점검을 붙였는가 — 2026-08-01에 발행만 하고 "주행했다"고 보고한 적이 있다.
# 배선이 끊긴 채로 기록하면 그 회차는 통째로 무효다. 시작 전에 잡는 편이 싸다.
#
# Ctrl+C 로 멈춘다. 파일은 ~/vica_data/bags/<이름>/ 에 남는다.

# set -u 를 쓰지 않는다. ROS 2의 setup.bash 가 미정의 변수를 참조해서
# `AMENT_TRACE_SETUP_FILES: unbound variable` 로 즉시 죽는다.
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

# --- 하드웨어 -------------------------------------------------------------
S=$(ip -br link show can1 2>/dev/null | awk '{print $2}')
[ "$S" = "UP" ] && ok "can1 UP" || bad "can1 이 $S 다. 매뉴얼 ①절 세 줄로 복구한다"

B=$(ip -details link show can1 2>/dev/null | grep -oE 'bitrate [0-9]+' | head -1)
[ "$B" = "bitrate 50000" ] && ok "$B" || bad "bitrate 가 '$B' 다. 50000 이어야 한다"

# --- 노드 -----------------------------------------------------------------
NODES=$(ros2 node list 2>/dev/null)
for n in emergency_stop_node safety_supervisor_node app_emergency_node \
         mdrobot_can_keyboard_knob_node robot_health_monitor_node; do
  echo "$NODES" | grep -q "$n" && ok "노드 $n" || bad "노드 $n 없음"
done
for n in controller_server planner_server bt_navigator amcl; do
  echo "$NODES" | grep -q "$n" && ok "노드 $n" || warn "노드 $n 없음 (Nav2 미기동?)"
done

# --- 주행 명령 배선 --------------------------------------------------------
# 이번 테스트가 답해야 할 숙제다. 발행자 0이면 Nav2 명령이 Safety에 닿지 않는다.
P=$(ros2 topic info /cmd_vel_req 2>/dev/null | grep -oE 'Publisher count: [0-9]+' | grep -oE '[0-9]+$')
S1=$(ros2 topic info /cmd_vel_req 2>/dev/null | grep -oE 'Subscription count: [0-9]+' | grep -oE '[0-9]+$')
[ "${P:-0}" -ge 1 ] && ok "/cmd_vel_req 발행자 $P" || bad "/cmd_vel_req 발행자 0 — Nav2 remap 확인"
[ "${S1:-0}" -ge 1 ] && ok "/cmd_vel_req 구독자 $S1 (Safety)" || bad "/cmd_vel_req 구독자 0"

P2=$(ros2 topic info /cmd_vel_safe 2>/dev/null | grep -oE 'Publisher count: [0-9]+' | grep -oE '[0-9]+$')
S2=$(ros2 topic info /cmd_vel_safe 2>/dev/null | grep -oE 'Subscription count: [0-9]+' | grep -oE '[0-9]+$')
[ "${P2:-0}" -ge 1 ] && ok "/cmd_vel_safe 발행자 $P2" || bad "/cmd_vel_safe 발행자 0"
[ "${S2:-0}" -ge 1 ] && ok "/cmd_vel_safe 구독자 $S2 (motor)" || bad "/cmd_vel_safe 구독자 0 — 모터가 못 받는다"

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

# --- 기록 -----------------------------------------------------------------
# costmap 은 always_send_full_costmap 이라 크다. 갇힘 분석에 꼭 필요하므로 넣되,
# 용량이 문제가 되면 아래 두 줄을 빼고 실패 시점에 따로 echo 로 받는다.
echo
echo "=== 기록 시작: $OUT ==="
echo "  Ctrl+C 로 멈춘다."
mkdir -p "$(dirname "$OUT")"

exec ros2 bag record -o "$OUT" \
  /cmd_vel_req /cmd_vel_safe \
  /odom /wheel/odom /imu/base_link /amcl_pose /tf /tf_static \
  /scan \
  /plan /local_plan \
  /speed_limit \
  /robot_status /robot/health /robot/events /diagnostics_agg \
  /estop_state /safety_state /app_estop_state /motor/can_ok \
  /rosout \
  /local_costmap/costmap /global_costmap/costmap \
  /navigate_to_pose/_action/status
