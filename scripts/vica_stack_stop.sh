#!/usr/bin/env bash
# VICA 스택 정리 — 터미네이터가 죽어도 살아남은 프로세스를 안전하게 전부 내린다.
#
#   bash ~/VICA-smarthandle/scripts/vica_stack_stop.sh
#
# 하는 일 (사람이 손으로 하던 절차 그대로):
#   1. ros2 launch/run 부모에 SIGINT  (Ctrl+C 를 대신 눌러줌 — 자식이 따라 내려감)
#   2. 그래도 남은 노드에 SIGINT → SIGTERM 순으로 격상
#   3. 터미네이터 칸 껍데기 셸(bash --rcfile)은 SIGHUP 으로 정리
#      (대화형 bash 는 SIGTERM 을 무시한다 — 2026-08-18 실증)
#   4. ros2 daemon stop (다음 기동 때 깨끗한 노드 목록을 보게)
#
# pkill -f 를 쓰지 않는 이유: 패턴이 자기 자신·다른 셸까지 잡는다 (2026-08-16 사고).
# kill -9 는 스스로 하지 않는다 — 끝까지 안 죽는 PID 만 사람에게 보고한다.

set -u

# 스택을 이루는 프로세스들. 새 구성 요소가 생기면 여기에만 추가하면 된다.
PAT='ros2 launch|ros2 run|src\.ros_|rplidar_node|robot_state_publisher|joint_state_publisher|ekf_node|encoder_feedback|mdrobot|nvblox|component_container|realsense2_camera|rviz2|rosbridge|supervisor_bringup|tegrastats|pointcloud_to_laserscan'

survivors() {
  ps -eo pid,cmd | grep -E "$PAT" | grep -v -E "grep|vica_stack_stop" || true
}

send() {  # send <시그널> <pid...>
  local sig="$1"; shift
  [ $# -gt 0 ] && kill "-$sig" "$@" 2>/dev/null || true
}

echo "[1/4] 생존 프로세스 확인"
alive="$(survivors)"
if [ -z "$alive" ]; then
  echo "  살아있는 스택 프로세스가 없다."
else
  echo "$alive" | sed 's/^/  /'
  # launch/run 부모 먼저 — Ctrl+C 대행. 자식은 따라 내려간다.
  parents=$(echo "$alive" | grep -E "ros2 (launch|run)" | awk '{print $1}')
  echo "[2/4] launch/run 부모 ${parents:+$(echo $parents | wc -w)개 }SIGINT"
  send INT $parents
  sleep 6
  # 남은 것(고아 노드 포함)에 INT, 더 남으면 TERM.
  rest=$(survivors | awk '{print $1}')
  if [ -n "$rest" ]; then
    send INT $rest; sleep 5
    rest=$(survivors | awk '{print $1}')
    [ -n "$rest" ] && { send TERM $rest; sleep 3; }
  fi
fi

echo "[3/4] 터미네이터 칸 셸 정리 (SIGHUP)"
shells=$(ps -eo pid,cmd | grep "bash --rcfile" | grep "vica-terminator" | grep -v grep | awk '{print $1}')
send HUP $shells
sleep 1

echo "[4/4] ros2 daemon 초기화"
# subshell + set +u: ROS setup.bash 는 미정의 변수를 참조해 set -u 에서 죽는다
( set +u; source /opt/ros/humble/setup.bash 2>/dev/null
  ros2 daemon stop >/dev/null 2>&1 ) && echo "  daemon 내림." || true

left="$(survivors)"
if [ -z "$left" ]; then
  echo "정리 완료 — 0개. 터미네이터를 새로 띄워도 된다."
  echo "재기동 주의: ① can1 은 precheck 에 state UP 이면 건너뛴다."
else
  echo "안 죽는 프로세스가 남았다. 확인 후 최후수단으로 kill -9 <PID>:"
  echo "$left" | sed 's/^/  /'
  exit 1
fi
