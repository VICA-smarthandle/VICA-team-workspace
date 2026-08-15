#!/usr/bin/env bash
# VICA 음성 주행 bringup 공통 환경 + 노드별 실행 함수.
#
# 이 파일 하나만 고치면 모든 창(pane)에 반영된다. Terminator 레이아웃의 각 칸은
# 이 파일을 source 한 뒤 run_XXX 함수 하나를 부른다.
#
# ⚠️ 여기 로컬(개발기)이 아니라 "로봇과 연결된 Jetson"에서 돌려야 실제로 주행한다.

# 이 파일 자신의 절대 경로 (재실행 안내에 쓴다).
VICA_ENV="$(readlink -f "${BASH_SOURCE[0]}")"
export VICA_ENV

# ─────────────────────────────────────────────────────────────
# ▼▼▼ 환경에 맞게 여기만 고친다 ▼▼▼
# ─────────────────────────────────────────────────────────────

# ROS 도메인. 음성 노드와 로봇 노드가 "같은 번호"여야 서로 토픽이 보인다.
# (팀 기존 스크립트가 7을 쓰고 있음 — 로봇 실제 설정과 반드시 일치시킬 것)
export VICA_DOMAIN_ID=7

# 저장소 경로 (로봇 Jetson의 실제 clone 위치로 맞춘다)
export VICA_ROS_WS="/home/tony/VICA-smarthandle/vica_ros2_ws"
export VICA_VOICE="/home/tony/VICA-smarthandle/vica-voice-llm"

# Nav2 지도 (map_server 가 읽는 .yaml)
export VICA_MAP="$VICA_ROS_WS/maps/vica_map_0630.yaml"

# 모터/센서 CAN 인터페이스 (미리 `ip link`로 up 되어 있어야 함)
export VICA_CAN="can1"

# ─────────────────────────────────────────────────────────────
# ▲▲▲ 여기까지만 고치면 된다 ▲▲▲
# ─────────────────────────────────────────────────────────────

# 모든 노드 공통 ROS 환경. 음성 노드도 vica_interfaces(정본은 로봇 저장소)를
# 써야 하므로 로봇 저장소 install 을 함께 source 한다.
_vica_base_env() {
  source /opt/ros/humble/setup.bash
  source "$VICA_ROS_WS/install/setup.bash"
  export ROS_DOMAIN_ID="$VICA_DOMAIN_ID"
  export ROS_LOCALHOST_ONLY=0
  export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
}

# 각 창 상단에 "무엇을 실행하는지 + 이 창만 다시 실행하는 법"을 찍는다.
#   $1 = 제목, $2 = 이 창의 실행 함수 이름(재실행 안내용)
_banner() {
  echo
  echo "==================== $1 ===================="
  if [ -n "${2:-}" ]; then
    echo "  ↻ 이 창만 다시 실행:  source \"$VICA_ENV\"; $2"
  fi
  echo
}

# 창이 처음 열릴 때(= 이 파일이 source 될 때) 한 번 찍는 공통 안내.
# start.sh 의 사전점검용 source 에서는 VICA_QUIET=1 로 건너뛴다.
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

# 1) Nav2 + 위치추정 + 지도 → /cmd_vel_req 생성
run_nav2() {
  _vica_base_env
  _banner "1) Nav2 (map=$VICA_MAP)" run_nav2
  ros2 launch vica_nav2 nav2_map_test.launch.py \
    map:="$VICA_MAP" start_localization:=true can:="$VICA_CAN"
}

# 2) 중앙 E-stop 래치 + Safety Supervisor(/cmd_vel_req→/cmd_vel_safe) + 앱 E-stop
run_safety() {
  _vica_base_env
  sleep 2
  _banner "2) Safety (중앙 래치 + Supervisor)" run_safety
  ros2 launch vica_safety safety_bringup.launch.py
}

# 3) CAN 모터 (/cmd_vel_safe 만 받는다)
run_motor() {
  _vica_base_env
  sleep 3
  _banner "3) Motor (CAN=$VICA_CAN)" run_motor
  ros2 launch mdrobot_can_control motor_bringup.launch.py
}

# 4) Mission Manager (/vica/intent 심사 → Nav2 목적지 전송) + 긴급어 브리지
run_mission() {
  _vica_base_env
  sleep 8   # Nav2 action server 가 뜬 뒤 goal 이 수락되도록 잠시 기다린다
  _banner "4) Mission Manager (게이트 + 긴급어 브리지)" run_mission
  ros2 launch vica_mission_manager mission_manager.launch.py
}

# 5) 음성 서비스: LLM 의도 노드 + TTS + 상시 긴급어 감지
run_voice() {
  _vica_base_env
  sleep 4
  _banner "5) Voice (LLM intent + TTS + 상시 긴급어)" run_voice
  cd "$VICA_VOICE" || return 1
  ros2 launch launch/vica_voice.launch.py
}

# 6) STT: 마이크 push-to-talk (엔터 → 말하기 → 엔터). 대화형이라 마지막에 둔다.
run_stt() {
  _vica_base_env
  sleep 6
  _banner "6) STT (엔터로 녹음)" run_stt
  cd "$VICA_VOICE" || return 1
  .venv/bin/python -m src.ros_stt_node
}

# 창이 열려 이 파일을 source 하면 안내를 한 번 찍는다.
# (start.sh 는 사전점검용으로 source 하므로 VICA_QUIET=1 로 건너뛴다.)
if [ -z "${VICA_QUIET:-}" ]; then
  _vica_intro
fi
