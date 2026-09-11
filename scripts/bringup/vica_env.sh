#!/usr/bin/env bash

VICA_ENV="$(readlink -f "${BASH_SOURCE[0]}")"
export VICA_ENV

export VICA_DOMAIN_ID=7

export VICA_ROS_WS="/home/tony/VICA-smarthandle/vica_ros2_ws"
export VICA_VOICE="/home/tony/VICA-smarthandle/vica-voice-llm"

export VICA_MAP="$VICA_ROS_WS/maps/vica_map_0630.yaml"

export VICA_CAN="can1"

_vica_base_env() {
  source /opt/ros/humble/setup.bash
  source "$VICA_ROS_WS/install/setup.bash"
  export ROS_DOMAIN_ID="$VICA_DOMAIN_ID"
  export ROS_LOCALHOST_ONLY=0
  export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
}

_banner() {
  echo
  echo "==================== $1 ===================="
  if [ -n "${2:-}" ]; then
    echo "  ↻ 이 창만 다시 실행:  source \"$VICA_ENV\"; $2"
  fi
  echo
}

_vica_intro() {
  cat <<INTRO
────────────────────────────────────────────────────────────
 VICA 음성 주행 창입니다. 이 창은 노드 하나를 자동 실행합니다.
 (전체 6개: Nav2 · Safety · Motor · Mission · Voice · STT)

 • 노드가 죽어도 이 창은 안 닫힙니다(아래에 bash 프롬프트가 남음).
 • 오류가 나면: 메시지를 읽고 → 아래 '↻ 재실행' 줄을 그대로 붙여넣으세요.
 • 값(지도·도메인·경로)을 바꾸려면: $VICA_ENV 위쪽을 편집 후 재실행.
────────────────────────────────────────────────────────────
INTRO
}

run_nav2() {
  _vica_base_env
  _banner "1) Nav2 (map=$VICA_MAP)" run_nav2
  ros2 launch vica_nav2 nav2_map_test.launch.py \
    map:="$VICA_MAP" start_localization:=true can:="$VICA_CAN"
}

run_safety() {
  _vica_base_env
  sleep 2
  _banner "2) Safety (중앙 래치 + Supervisor)" run_safety
  ros2 launch vica_safety safety_bringup.launch.py
}

run_motor() {
  _vica_base_env
  sleep 3
  _banner "3) Motor (CAN=$VICA_CAN)" run_motor
  ros2 launch mdrobot_can_control motor_bringup.launch.py
}

run_mission() {
  _vica_base_env
  sleep 8
  _banner "4) Mission Manager (게이트 + 긴급어 브리지)" run_mission
  ros2 launch vica_mission_manager mission_manager.launch.py
}

run_voice() {
  _vica_base_env
  sleep 4
  _banner "5) Voice (LLM intent + TTS + 상시 긴급어)" run_voice
  cd "$VICA_VOICE" || return 1
  ros2 launch launch/vica_voice.launch.py
}

run_stt() {
  _vica_base_env
  sleep 6
  _banner "6) STT (엔터로 녹음)" run_stt
  cd "$VICA_VOICE" || return 1
  .venv/bin/python -m src.ros_stt_node
}

if [ -z "${VICA_QUIET:-}" ]; then
  _vica_intro
fi
