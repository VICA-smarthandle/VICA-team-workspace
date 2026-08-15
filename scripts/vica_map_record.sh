#!/bin/bash
# 매핑 기록. 사전 점검을 먼저 하고, 통과해야 기록을 시작한다.
#
#   bash scripts/vica_map_record.sh map01
#   bash scripts/vica_map_record.sh map01 --check-only    사전 점검만
#
# 왜 만들었는가 — 2026-08-15까지 매핑 bag이 하나도 없었다. 2026-08-12에 매핑이
# 아홉 번 실패했는데 저장조차 안 돼서, 남은 것은 성공한 두 장뿐이었다. 결과물만
# 놓고 거꾸로 추정하느라 원인을 화면 캡쳐에서 겨우 찾았다.
#
# bag이 있으면 재주행이 필요 없다. cartographer_offline_node가 같은 bag으로
# 설정을 바꿔 가며 지도를 다시 만든다:
#
#   ros2 launch cartographer_ros offline_backpack_2d.launch.py \
#       bag_filenames:=$HOME/vica_data/bags/map01
#
# Ctrl+C 로 멈춘다. 파일은 ~/vica_data/bags/<이름>/ 에 남는다.

# set -u 를 쓰지 않는다. ROS 2의 setup.bash 가 미정의 변수를 참조해서
# `AMENT_TRACE_SETUP_FILES: unbound variable` 로 즉시 죽는다.
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

# --- 중복 실행 -------------------------------------------------------------
# 2026-08-11 20:07 에 cartographer 가 두 벌 떠서 두 회차를 잃었다. 두 벌이 돌면
# /odom 발행자가 둘이 되어 위치가 튀고, 회차가 통째로 무효가 된다.
for n in cartographer_node ekf_node encoder_feedback; do
  C=$(pgrep -xc "${n:0:15}" 2>/dev/null)
  case "${C:-0}" in
    0) bad "$n 이 안 떠 있다" ;;
    1) ok  "$n 1개" ;;
    *) bad "$n 이 $C 개다 — 두 벌이 돌고 있다. 하나를 내린다" ;;
  esac
done

# --- 오도메트리 발행자 -----------------------------------------------------
for t in /odom /wheel/odom; do
  P=$(ros2 topic info "$t" 2>/dev/null | grep -oE 'Publisher count: [0-9]+' | grep -oE '[0-9]+$')
  case "${P:-0}" in
    1) ok  "$t 발행자 1" ;;
    0) bad "$t 발행자 0 — motor 칸이 먼저다. encoder_feedback 은 스스로 요청하지 않는다" ;;
    *) bad "$t 발행자 $P — 중복 발행이다" ;;
  esac
done

# --- 라이다 ---------------------------------------------------------------
# 주기 측정은 넣지 않는다. `ros2 topic hz` 를 kill 로 끊으면 /dev/shm 에 fastrtps
# 고아 세그먼트가 남아 DDS 가 막힌다. 발행자 수만 본다.
S=$(ros2 topic info /scan 2>/dev/null | grep -oE 'Publisher count: [0-9]+' | grep -oE '[0-9]+$')
[ "${S:-0}" -eq 1 ] && ok "/scan 발행자 1" || bad "/scan 발행자 ${S:-0}"

# --- 자이로 편향 보정 ------------------------------------------------------
# 2026-08-12 12:56 회차가 이것 때문에 흔들렸다:
#   "Gyro bias calibration aborted: motion detected during startup"
# imu 노드를 띄운 뒤 20초(50 Hz x 1000샘플) 동안 로봇을 완전히 세워 둬야 한다.
# EKF 가 이 IMU 를 쓰고 Cartographer 가 그 EKF 를 읽으므로 지도까지 그대로 온다.
if echo "$NODES" | grep -q imu_base_link_adapter; then
  ok "imu_base_link_adapter 떠 있음"
  warn "자이로 보정 성공 여부는 그 칸 로그에서 직접 본다:"
  warn "  성공 → 'Gyro bias calibrated over 1000 samples'"
  warn "  실패 → 'calibration aborted: motion detected' (노드를 다시 띄운다)"
else
  warn "imu_base_link_adapter 없음 — EKF 가 IMU 없이 돈다"
fi

# --- 저장 공간 -------------------------------------------------------------
AVAIL=$(df -BG --output=avail "$HOME" 2>/dev/null | tail -1 | tr -dc '0-9')
[ "${AVAIL:-0}" -ge 5 ] && ok "여유 공간 ${AVAIL}G" || bad "여유 공간 ${AVAIL}G — 5G 이상 필요"

echo
if [ "$fail" -gt 0 ]; then
  printf "\033[31m사전 점검 %d건 실패. 기록을 시작하지 않는다.\033[0m\n" "$fail"
  exit 1
fi
printf "\033[32m사전 점검 통과\033[0m\n"
[ "$CHECK_ONLY" = "--check-only" ] && exit 0

# --- 기록 -----------------------------------------------------------------
# cartographer_offline_node 로 재현하려면 /scan · /tf_static · odom 이 필요하다.
# 두 오도메트리를 모두 담는다 — 나중에 어느 쪽으로도 다시 돌려볼 수 있다.
# /map 과 submap_list 는 결과물이라 재현에는 불필요하지만, 실패 회차에서 무엇이
# 보였는지 되짚을 때 쓴다.
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
