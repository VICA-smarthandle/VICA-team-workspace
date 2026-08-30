#!/bin/bash
# 주행 테스트 기록. 사전 점검을 먼저 하고, 통과해야 기록을 시작한다.
#
#   bash scripts/vica_drive_record.sh run01
#   bash scripts/vica_drive_record.sh run01 --check-only    사전 점검만
#
#   VICA_RECORD_NVBLOX=1 bash scripts/vica_drive_record.sh run01
#       nvblox 슬라이스까지 기록한다(용량이 크다. 아래 '기록' 절 주석 참조).
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

# 2026-08-11: 드라이버를 500 kbps로 바꿨다. 50000 이던 값이다.
B=$(ip -details link show can1 2>/dev/null | grep -oE 'bitrate [0-9]+' | head -1)
[ "$B" = "bitrate 500000" ] && ok "$B" || bad "bitrate 가 '$B' 다. 500000 이어야 한다"

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

# --- 인지 보조: nvblox 슬라이스 -------------------------------------------
# 왜 보는가 — 2026-08-02 회의용 의자 정면 충돌. 다리가 얇은 금속 파이프라
# 라이다 빔이 다리 사이로 통과했다 막혔다 하며 전방 거리가 0.5 m ↔ 3.1 m로
# 진동했다. 그 틈을 3D로 메우는 것이 costmap의 nvblox_layer인데, 이 플러그인은
# 슬라이스를 한 번도 못 받아도(slice_ == nullptr) 모든 셀에 NO_INFORMATION을 쓰고
# 조용히 넘어간다. 경고도 진단도 토픽도 없고, 라이다의 expected_update_rate 같은
# timeout 파라미터도 없다(guideline/vica_system_health_monitoring_draft.md §8.5의
# 안전 공백). 그래서 '그날 nvblox가 일했는가'를 사후에 확인할 방법이 없었다.
# 최소한 '붙어 있는가'만이라도 시작 전에 눈으로 본다.
#
# 여기서 막지 않는 이유 — 라이다만으로 주행하는 회차가 정상적으로 있다.
# 실패해도 warn 이고 기록은 시작한다.
#
# ros2 topic hz 처럼 스스로 끝나지 않는 명령은 쓰지 않는다. timeout 으로 죽였다가
# /dev/shm 에 fastrtps 고아 세그먼트가 쌓여 DDS 가 막힌 사고가 있다.
# topic info 는 즉시 반환한다.
NV_TOPIC=/nvblox_node/static_map_slice
NV=$(ros2 topic info "$NV_TOPIC" 2>/dev/null)
if ! echo "$NV" | grep -q 'Publisher count:'; then
  warn "$NV_TOPIC 없음 — nvblox_node 미기동. 이 회차는 라이다만 본다"
else
  NP=$(echo "$NV" | grep -oE 'Publisher count: [0-9]+' | grep -oE '[0-9]+$')
  NS=$(echo "$NV" | grep -oE 'Subscription count: [0-9]+' | grep -oE '[0-9]+$')
  [ "${NP:-0}" -ge 1 ] && ok "$NV_TOPIC 발행자 $NP (nvblox_node)" \
    || warn "$NV_TOPIC 발행자 0 — nvblox_node 가 죽었다. 3D 장애물이 안 들어온다"
  # 구독자는 local·global costmap 의 nvblox_layer 둘이다(2026-08-02 실측 2).
  # 0이면 플러그인이 안 붙은 것이고, 그때 costmap 은 아무 말 없이 라이다만 본다.
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

# --- 기록 -----------------------------------------------------------------
# costmap 은 always_send_full_costmap 이라 크다. 갇힘 분석에 꼭 필요하므로 넣되,
# 용량이 문제가 되면 아래 두 줄을 빼고 실패 시점에 따로 echo 로 받는다.
#
# nvblox 슬라이스는 기본에서 뺀다 — 크기 실측(2026-08-02, 주행 중 한 건):
#   width 280 x height 249 = 69,720 셀,  float32 4 B  ->  약 0.27 MB/건
#   280 = map_clearing_radius_m 7.0 x 2 / 해상도 0.05 이므로 이 폭이 상한이다.
#   발행 9.4 Hz(2026-07-31 실측) -> 약 2.5 MB/s, 10분 주행이면 약 1.5 GB.
# 매 회차에 켜면 다른 토픽을 전부 합친 것보다 큰 파일이 매번 쌓인다. 그래서
# nvblox 기여를 확인하는 회차에만 켠다:
#   VICA_RECORD_NVBLOX=1 bash scripts/vica_drive_record.sh run01
# 이 토픽이 bag 에 있으면 사후에 '슬라이스가 왔는가 / 의자 자리가 메워졌는가'를
# 직접 볼 수 있다. 2026-08-02 회차는 기록이 없어 그것을 못 했다.
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
