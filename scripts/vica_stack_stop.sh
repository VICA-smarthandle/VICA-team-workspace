#!/usr/bin/env bash

set -u

PAT='ros2 launch|ros2 run|src\.ros_|rplidar_node|robot_state_publisher|joint_state_publisher|ekf_node|encoder_feedback|mdrobot|nvblox|component_container|realsense2_camera|rviz2|rosbridge|supervisor_bringup|tegrastats|pointcloud_to_laserscan'

survivors() {
  ps -eo pid,cmd | grep -E "$PAT" | grep -v -E "grep|vica_stack_stop" || true
}

send() {
  local sig="$1"; shift
  [ $# -gt 0 ] && kill "-$sig" "$@" 2>/dev/null || true
}

echo "[1/4] 생존 프로세스 확인"
alive="$(survivors)"
if [ -z "$alive" ]; then
  echo "  살아있는 스택 프로세스가 없다."
else
  echo "$alive" | sed 's/^/  /'
  parents=$(echo "$alive" | grep -E "ros2 (launch|run)" | awk '{print $1}')
  echo "[2/4] launch/run 부모 ${parents:+$(echo $parents | wc -w)개 }SIGINT"
  send INT $parents
  sleep 6
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
