#!/usr/bin/env python3
"""VICA 기동용 Terminator 레이아웃 생성기.

`docs/vica_robot_bringup_manual.md` 5절의 실행 순서를 용도별 레이아웃으로 배치한다.
한 번 실행하면 프로파일 수만큼 Terminator 레이아웃이 생기고, 그 뒤로는
`terminator -l <레이아웃>`만 치면 된다.

    python3 scripts/vica_terminator_layout.py     # 다섯 프로파일 모두 생성
    terminator -l vica                            # 주행 전체
    terminator -l vica_drive                      # 음성 제외 주행
    terminator -l vica_app                        # 앱·안전·감시 검증
    terminator -l vica_sensor                     # 센서·인지만 (바퀴 없음)
    terminator -l vica_map                        # 지도 작성 (Nav2 없음)

각 터미널은 전용 rc 파일로 bash를 띄운다. rc가 하는 일:

1. `~/.bashrc`를 읽어 개인 alias·함수(`vica_rs`, `can_set` 등)를 살린다
2. ROS 2와 운영 워크스페이스를 source하고 통신 환경변수를 맞춘다
3. 작업 디렉터리로 이동한다
4. 실행 방식에 따라 명령을 처리한다
   - auto  : 바로 실행한다 (바퀴를 움직이지 않고 순서 의존성도 없는 것)
   - hold  : `history`에 넣어두고 안내만 출력한다. 위 화살표 + Enter로 실행한다
   - shell : 명령 없이 source만 끝낸 자유 터미널

hold를 쓰는 이유는 세 가지다.

- 바퀴가 도는 단계(motor, Nav2, Mission, teleop)는 사람이 시점을 통제해야 한다
- 순서 의존성이 있는 단계(Docker 카메라 → nvblox → Nav2)를 앞질러 띄우면 실패한다
- `sudo`가 필요한 단계(전력모드, CAN)는 스크립트가 대신 실행하면 안 된다.
  비-tty에서 sudo가 실패하기도 하고, 무엇보다 CAN은 잘못 내리면 복구가 비싸다

`can1`을 down/up하는 명령은 절대 auto로 두지 않는다. 드라이버에 한 번 전원이 들어간
뒤 CAN이 OFF되면 동력이 차단되어 물리적으로 전원을 재투입해야 복구된다. ① 칸은
현재 링크 상태만 읽어서 보여주고, 실제 설정 명령은 사람이 눌러야 나간다.

기존 `~/.config/terminator/config`는 타임스탬프를 붙여 백업한다.
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

HOME = Path.home()
WORKSPACE = HOME / "VICA-smarthandle"
VOICE = WORKSPACE / "vica-voice-llm"
SUPERVISOR = WORKSPACE / "VICA_Supervisor"

# 운영 빌드 워크스페이스의 기본 경로. rc 안에서는 `$VICA_ROS_WS`로 참조하므로,
# 다른 빌드를 쓰려면 터미널을 띄우기 전에 그 환경변수만 export하면 된다.
DEFAULT_ROS_WS = WORKSPACE / "vica_ros2_ws"

# 감시 노드 overlay 후보. 운영 빌드에 `vica_system_monitor`가 없을 때만 덧씌운다.
# 2026-08-01 기준 `vica_ros2_ws` 본체는 `nav2-plannerhybrid-change`에 있고 그 빌드에는
# 감시 패키지가 없다. devlog/2026-07-31-health-monitor-implementation.md 14.1이
# "로봇 스택은 vica_ros2_ws/install, 감시 노드는 별도 worktree"를 실측 구성으로 기록했다.
MONITOR_OVERLAYS = ("$HOME/wt-dev", "$HOME/wt-monitor")

# `maps/CURRENT_MAP`이 없을 때만 쓰는 fallback. 평소 지도는 실행 시점에
# CURRENT_MAP이 정하므로 이 값은 거의 쓰이지 않는다. 생성 시점에 이름을 굳혀
# 명령에 박아 넣던 방식이 칸마다 지도가 갈리던 원인이라 그렇게 바꿨다.
DEFAULT_MAP_ID = "vica_map_0630"

RC_DIR = HOME / ".config" / "vica-terminator"
TERMINATOR_CONFIG = HOME / ".config" / "terminator" / "config"

AUTO = "auto"
HOLD = "hold"
SHELL = "shell"

# 이 스크립트가 만드는 레이아웃과, 과거에 만들었다가 이름이 바뀐 레이아웃.
# 다시 만들 때 함께 지워서 config에 유령 레이아웃이 쌓이지 않게 한다.
OBSOLETE_LAYOUTS = (
    "vica",
    "vica_drive",
    "vica_app",
    "vica_sensor",
    "vica_map",
    "vicavoice",
)


class Term:
    """터미널 한 칸."""

    def __init__(
        self,
        title: str,
        note: tuple[str, ...],
        command: str = "",
        mode: str = HOLD,
        workdir: Path | None = None,
        ros: bool = True,
        precheck: str = "",
        monitor_overlay: bool = False,
        guard: tuple[str, ...] = (),
        uses_map: bool = False,
    ) -> None:
        self.title = title
        self.note = note
        self.command = command
        self.mode = mode
        self.workdir = workdir
        # ROS source가 필요 없는 칸(Docker 안에서 따로 source하거나 sudo만 쓰는 칸).
        self.ros = ros
        # 명령을 내밀기 전에 자동으로 실행하는 읽기 전용 점검. 상태를 모르고
        # 위험한 명령을 누르는 일을 막는다.
        self.precheck = precheck
        # 감시 패키지 overlay 탐색이 필요한 칸.
        self.monitor_overlay = monitor_overlay
        # 중복 실행을 막을 프로세스 이름들(`pgrep -x` 기준, 15자 comm).
        # 비어 있으면 검사하지 않는다 — shell 처럼 여러 개 띄워도 되는 칸이다.
        self.guard = guard
        # 명령이 $VICA_MAP_ID / $VICA_MAP_YAML 을 쓰는 칸. 어느 지도인지 화면에
        # 찍고 지도·목적지 파일이 실제로 있는지 확인한다.
        self.uses_map = uses_map


def build_terms() -> dict[str, Term]:
    """터미널 정의를 만든다.

    명령 안의 `$VICA_ROS_WS`·`$VICA_MAP_ID`·`$VICA_MAP_YAML`은 rc가 정한 값을
    실행 시점에 펼친다. 생성 시점의 경로나 지도 이름을 굳혀버리면 워크스페이스를
    옮기거나 지도를 새로 그렸을 때 조용히 옛것을 읽는다. 실제로 2026-08-13 이전에는
    지도 이름이 칸마다 박혀 있어 nav2 와 initpose 가 서로 다른 지도를 보고 있었다.
    """
    return {
        # ------------------------------------------------------------------
        # ⓪~④ 준비·센서·안전. 바퀴가 돌지 않는다.
        # ------------------------------------------------------------------
        "power": Term(
            title="⓪ power",
            note=(
                "전력·클럭 모드 고정. DVFS로 클럭이 내려가면 nvblox depth와 STT/TTS가",
                "GPU를 시분할할 때 경합이 악화된다. 안전상 손해는 없다.",
                "sudo가 필요하므로 이 칸에서 직접 입력한다.",
            ),
            command="sudo nvpmodel -m 0 && sudo jetson_clocks && sudo jetson_clocks --show",
            mode=HOLD,
            ros=False,
            precheck="nvpmodel -q 2>&1 | head -4",
        ),
        "can": Term(
            title="① can1",
            note=(
                "[위험] 아래 상태 출력에 state UP이 보이면 실행하지 말 것.",
                "드라이버에 전원이 들어간 뒤 CAN이 OFF되면 동력이 차단되고,",
                "물리적으로 전원을 재투입해야 복구된다.",
                "bitrate는 500000이다 (2026-08-11 드라이버를 500 kbps로 바꿨다).",
                "옛 문서의 50000으로 되돌리면 ERROR-PASSIVE로 통신이 끊긴다.",
                "기동 순서는 드라이버 전원 → can1 up → ⑤ motor 다.",
            ),
            command=(
                "sudo ip link set can1 down 2>/dev/null || true;"
                " sudo ip link set can1 type can bitrate 500000"
                " berr-reporting on restart-ms 100;"
                " sudo ip link set can1 up; ip -details link show can1"
            ),
            mode=HOLD,
            ros=False,
            precheck="ip -details link show can1 2>&1 | head -6",
        ),
        "display": Term(
            title="② display",
            note=(
                "URDF·TF. base_link → laser_frame / camera_link TF의 공급원이라",
                "화면이 없어도 생략하지 않는다. robot_state_publisher + joint_state_publisher만",
                "뜨고 RViz는 뜨지 않는다.",
                "확인용으로 RViz를 보려면 전용 rviz 칸을 쓰거나 display.launch.py를 직접 띄운다.",
            ),
            command="ros2 launch vica_description robot_state.launch.py",
            mode=AUTO,
                    guard=("robot_state_pub", "joint_state_pub",),
),
        "lidar": Term(
            title="③ lidar",
            note=(
                "RPLIDAR A2M8-R4. /scan 의 frame_id는 laser_frame 이어야 ②의 TF와 맞는다.",
            ),
            command=(
                "ros2 run rplidar_ros rplidar_node --ros-args"
                " -p channel_type:=serial -p serial_port:=/dev/rplidar"
                " -p serial_baudrate:=115200 -p frame_id:=laser_frame"
                " -p angle_compensate:=true -p inverted:=false"
                " -p flip_x_axis:=true -p scan_mode:=Express"
            ),
            mode=AUTO,
                    guard=("rplidar_node",),
),
        "safety": Term(
            title="④ safety",
            note=(
                "emergency_stop_node / safety_supervisor_node / app_emergency_node.",
                "⑤ motor보다 반드시 먼저 떠 있어야 한다.",
                "중앙 E-stop 래치와 /cmd_vel_req → /cmd_vel_safe 승인이 여기서 난다.",
            ),
            command="ros2 launch vica_safety safety_bringup.launch.py",
            mode=AUTO,
                    guard=("emergency_stop_", "safety_supervis", "app_emergency_n",),
),
        # ------------------------------------------------------------------
        # ⑤~⑩ 구동·인지·주행. 바퀴가 돈다.
        # ------------------------------------------------------------------
        "motor": Term(
            title="⑤ motor",
            note=(
                "[바퀴가 돕니다] 바퀴를 띄웠는지, 물리 E-stop이 손에 닿는지 먼저 확인한다.",
                "선행 조건은 ① can1 UP 과 ④ safety 기동이다.",
                "이 칸은 can1을 건드리지 않는다. 링크 작업은 ① 칸에서만 한다.",
            ),
            command="ros2 launch mdrobot_can_control motor_bringup.launch.py",
            mode=HOLD,
                    guard=("mdrobot_can_ke", "keyboard_knob",),
),
        "d455": Term(
            title="⑥ d455",
            note=(
                "D455 카메라(Docker). vica_rs 로 컨테이너에 들어간 뒤",
                "컨테이너 안에서 ./run_d455.sh 를 실행한다.",
            ),
            command="vica_rs",
            mode=HOLD,
            ros=False,
        ),
        "imu": Term(
            title="⑦ imu",
            note=(
                "D455 IMU를 base_link 기준으로 바꿔 /imu/base_link 로 낸다.",
                "⑥ 카메라가 떠야 데이터가 흐른다. 먼저 띄워도 구독만 하고 기다린다.",
            ),
            command=(
                "ros2 run vica_sensor_adapters imu_base_link_adapter --ros-args"
                " -p input_topic:=/camera/camera/imu"
                " -p output_topic:=/imu/base_link"
                " -p target_frame:=base_link"
            ),
            mode=AUTO,
                    guard=("imu_base_link_a",),
),
        "nvblox": Term(
            title="⑧ nvblox",
            note=(
                "nvblox(Docker). ⑥ 카메라가 뜬 뒤에 실행한다.",
                "Nav2 local_costmap이 nvblox_layer를 쓰므로 ⑨보다 먼저다.",
            ),
            command=(
                "docker exec -it vica_rs_container bash -lc"
                " 'source /opt/ros/humble/setup.bash"
                " && source /workspaces/isaac_ros-dev/install/setup.bash"
                " && ros2 launch vica_nvblox_bringup vica_nvblox.launch.py'"
            ),
            mode=HOLD,
            ros=False,
                    guard=("nvblox_node",),
),
        "nav2": Term(
            title="⑨ nav2",
            note=(
                "[바퀴가 돕니다] Nav2 + EKF + encoder를 한 launch가 함께 띄운다.",
                "wheel_ekf.launch.py 를 따로 띄우지 말 것 — /odom 과 odom→base_footprint",
                "TF가 이중 발행되어 위치추정이 깨진다.",
                "기동 뒤 RViz에서 2D Pose Estimate로 초기 위치를 찍는다. 안 찍으면",
                "global_costmap이 activating [13]에서 멈춘다. 고장이 아니다.",
                "",
                "지도는 위에 찍힌 '현재 지도'다. 바꾸려면 터미네이터를 다 닫고",
                "VICA_MAP_ID 를 export 한 뒤 새로 띄운다. 이 칸에서만 고치면 mission·",
                "app·initpose 는 옛 지도를 계속 보고, Nav2 는 아무 불평 없이 돈다.",
            ),
            command=(
                "ros2 launch vica_nav2 nav2_map_test.launch.py map:=$VICA_MAP_YAML"
            ),
            mode=HOLD,
            uses_map=True,
                    guard=("bt_navigator", "planner_server", "controller_serv", "amcl",),
),
        # slam 과 nav2 는 상호 배타다. 둘 다 wheel_ekf.launch.py 를 include 하므로
        # 함께 띄우면 /odom 과 odom→base_footprint 가 이중 발행되고, AMCL 과
        # Cartographer 가 둘 다 map→odom 을 내보내 위치가 통째로 깨진다.
        # 그래서 vica_map 레이아웃에는 nav2 칸을 아예 넣지 않는다.
        "slam": Term(
            title="slam",
            note=(
                "[금지] ⑨ nav2 와 함께 띄우지 말 것. 두 launch 가 모두 wheel_ekf 를",
                "include 해 /odom 과 odom→base_footprint TF 가 이중 발행되고,",
                "AMCL 과 Cartographer 가 둘 다 map→odom 을 내보내 위치가 깨진다.",
                "",
                "선행 조건은 ⑤ motor 다. encoder_feedback 은 request_position_feedback",
                "이 False 라 피드백을 스스로 요청하지 않는다. motor node 가 없으면",
                "/wheel/odom 이 아예 나오지 않는다.",
                "",
                "[정정 2026-08-15] 전에 이 칸은 odom_topic:=/wheel/odom 을 넘겼고",
                "설명도 그것이 2026-08-12 매핑 실패의 원인이라고 적었다. 둘 다 틀렸다.",
                "  · 그 인자는 launch 가 '/odom' 을 하드코딩해서 조용히 무시됐다.",
                "    ROS 2 는 선언 안 된 인자를 오류로 잡지 않는다. 지금은 배선을",
                "    고쳤으므로 넘기면 실제로 먹는다 — 그래서 이 칸에서는 뺐다.",
                "  · 8/11~8/12 매핑 13회가 전부 /odom 이었다. 성공한 vica_map_0810 도",
                "    실패한 회차들도 같은 값이다. odom 소스는 바뀐 적이 없다.",
                "/wheel/odom 은 아직 한 번도 시험된 적이 없다. 바꿀 때는 그 축만 바꾼다.",
                "",
                "실제 실패 원인은 로그에 찍혀 있었다(8/12 12:56 캡쳐).",
                "  constraint_builder_2d: differs by translation 3.83 rotation 0.000",
                "회전은 멀쩡한데 위치만 3.8 m 어긋났다 — 복도 방향으로 미끄러진 것이다.",
                "복도는 어디서 봐도 같아서 '얼마나 왔는지'를 스캔으로 못 잡는다.",
                "같은 회차에 자이로 보정도 실패했다:",
                "  Gyro bias calibration aborted: motion detected during startup",
                "",
                "그래서 시작 절차가 중요하다. imu 노드를 띄운 뒤 20초 동안",
                "(50 Hz x 1000샘플) 로봇을 완전히 세워 둔다. 움직이면 보정이 중단되고",
                "yaw 가 시간당 25도씩 흐른다. EKF 가 그 IMU 를 쓰고 Cartographer 는",
                "그 EKF 를 읽으므로, 보정 실패는 지도까지 그대로 온다.",
                "",
                "EKF 는 이 launch 가 함께 띄운다. 끄지 말 것 —",
                "odom→base_footprint TF 의 유일한 발행자다.",
                "",
                "RViz Fixed Frame 을 map 으로 두고 지도가 자라는 것을 보며 끌고 다닌다.",
                "회전은 천천히. 그리고 긴 복도는 한 방향으로만 훑지 말고 왕복한다 —",
                "왔던 자리를 다시 지나야 pose graph 가 쌓인 오차를 당겨 준다.",
            ),
            command=(
                "ros2 launch vica_cartographer vica_slam_bringup.launch.py"
            ),
            mode=HOLD,
                    guard=("cartographer_no", "cartographer_oc", "ekf_node",
                           "encoder_feedbac",),
),
        "mission": Term(
            title="⑩ mission",
            note=(
                "[바퀴가 돕니다] 일반 운영 Goal의 단일 권한자다.",
                "목적지 catalog 는 지도마다 다르다 —",
                "  ~/vica_data/destinations/<map_id>/destinations.yaml",
                "그래서 map_id 가 갈리면 ⑨ nav2·⑫ 음성과 목적지가 따로 논다.",
                "이 칸을 포함해 전부 $VICA_MAP_ID 하나를 읽으므로 갈릴 일이 없다.",
                "앱이 다른 map_id 로 요청하면 거부하고 current/requested 를 남긴다.",
            ),
            command=(
                "ros2 launch vica_mission_manager mission_manager.launch.py"
                " map_id:=$VICA_MAP_ID map_yaml:=$VICA_MAP_YAML"
            ),
            mode=HOLD,
            uses_map=True,
                    guard=("vica_mission_ma",),
),
        # ------------------------------------------------------------------
        # ⑪~⑬ 앱·감시·음성.
        # ------------------------------------------------------------------
        "app": Term(
            title="⑪ app bridge",
            note=(
                "rosbridge 9090 / 지도 HTTP 8000 / Destination·MapList·Status 노드.",
                "앱이 연결 timeout이면 대개 Jetson DHCP IP가 바뀐 것이다. ip -br addr 확인.",
            ),
            command=(
                f"ros2 launch {SUPERVISOR}/ros2/supervisor_bringup.launch.py"
                " map_yaml:=$VICA_MAP_YAML"
            ),
            mode=HOLD,
            uses_map=True,
                    guard=("rosbridge_webso",),
),
        "monitor": Term(
            title="⑪-1 monitor",
            note=(
                "external_diagnostics_node / aggregator_node / robot_health_monitor_node.",
                "⑤~⑪이 다 뜬 뒤에 띄운다. 먼저 띄우면 아직 없는 노드가 전부 결함으로 잡힌다.",
                "관측·보고만 한다. 이 노드가 죽어도 정지 경로는 그대로 동작한다.",
                "현재 임계값은 전부 [미검증]이다. 결함 표시를 단독 판정 근거로 쓰지 않는다.",
            ),
            command="ros2 launch vica_system_monitor system_monitor.launch.py",
            mode=HOLD,
            monitor_overlay=True,
                    guard=("robot_health_mo", "external_diagno", "aggregator_node",),
),
        "gui": Term(
            title="app GUI",
            note=(
                "관리자 앱(Flutter Linux 빌드)을 이 장비 화면에 띄운다.",
                "devlog 2026-07-31-health-monitor-implementation.md 16절의 앱 종단 검증 구성이다.",
                "빌드가 없으면 VICA_Supervisor 에서 flutter build linux 를 먼저 한다.",
            ),
            command=(
                "DISPLAY=${DISPLAY:-:1}"
                f" {SUPERVISOR}/build/linux/arm64/release/bundle/vica_supervisor"
            ),
            mode=HOLD,
            ros=False,
            precheck=(
                f"ls -l {SUPERVISOR}/build/linux/arm64/release/bundle/vica_supervisor"
                " 2>&1 | head -2"
            ),
                    guard=("vica_supervisor",),
),
        "llm": Term(
            title="⑫ llm+tts",
            note=(
                "LLM 해석 / TTS 재생 / 긴급어 상시 감시 세 프로세스.",
                "시작 로그에 '목적지 catalog가 없어' WARN이 뜨면 map_id가 틀린 것이다.",
                "그 상태에서도 노드는 정상으로 보이지만 모든 목적지가 gate에서 막힌다.",
            ),
            command="ros2 launch launch/vica_voice.launch.py map_id:=$VICA_MAP_ID",
            mode=HOLD,
            workdir=VOICE,
            uses_map=True,
                    guard=("vica_llm_node", "vica_tts_node",),
),
        "stt": Term(
            title="⑬ stt",
            note=(
                "push-to-talk. 엔터로 녹음 시작, 다시 엔터로 종료. 종료는 Ctrl+C.",
                "터미널 입력이 필요해 ⑫ launch에 넣지 않는다.",
            ),
            command=".venv/bin/python -m src.ros_stt_node",
            mode=HOLD,
            workdir=VOICE,
                    guard=("vica_stt_node",),
),
        # ------------------------------------------------------------------
        # 조작·점검. 운영 단계가 아니라 사람이 쓰는 도구다.
        # ------------------------------------------------------------------
        "goto": Term(
            title="goto",
            note=(
                "목적지 요청(CLI). 인자 없이 실행하면 번호 목록이 나온다.",
                "  vica_goto.sh          목록",
                "  vica_goto.sh 4        4번으로 주행 요청",
                "  vica_goto.sh cancel   진행 중 주행 취소",
                "목적지 이름이 한글인데 xfreerdp(RDP)에서 한영 전환이 안 되어",
                "번호로 고르게 만들었다. 서비스가 받는 것은 UUID라 이름은 표시용이다.",
                "초기 위치를 먼저 잡아야 승인된다 — 왼쪽 initpose 칸을 본다.",
                "목적지 목록은 현재 지도의 catalog 에서 읽고, 요청에도 그 map_id 를",
                "실어 보낸다. Mission Manager 쪽 map_id 와 다르면 거부된다.",
            ),
            command="bash $VICA_ROOT/scripts/vica_goto.sh",
            mode=HOLD,
            uses_map=True,
        ),
        "initpose": Term(
            title="initpose",
            note=(
                "AMCL 초기 위치를 명령으로 넣는다. RViz의 2D Pose Estimate와 같은 일이다.",
                "  vica_set_initial_pose.sh              장소 목록",
                "  vica_set_initial_pose.sh 안내소        저장된 장소로",
                "  vica_set_initial_pose.sh -6.18 3.68 0  좌표로 (x y yaw도)",
                "RViz가 원격에서 CPU 170 %를 쓰며 느려지면 클릭-드래그가 완성되지 않는다.",
                "2026-08-01에 실제로 그래서 못 찍었다. 이 칸이 그 우회로다.",
                "안 넣으면 map->odom TF가 없어 Nav2가 경로를 내지 못한다.",
                "",
                "장소 이름은 현재 지도의 목적지 catalog 에서 읽는다. 지도가 바뀌면",
                "목록도 바뀐다. catalog 가 없는 지도면 목록이 비므로 좌표로 넣는다.",
            ),
            command="bash $VICA_ROOT/scripts/vica_set_initial_pose.sh",
            mode=HOLD,
            uses_map=True,
        ),
        "record": Term(
            title="record",
            note=(
                "주행 회차 기록. 사전 점검을 먼저 하고 통과해야 기록을 시작한다.",
                "  vica_drive_record.sh run03               점검 + 기록",
                "  vica_drive_record.sh run03 --check-only  점검만",
                "점검이 막는 것은 can1 상태·필수 노드·주행 명령 배선이다.",
                "배선이 끊긴 채로 기록하면 그 회차가 통째로 무효가 되므로 먼저 잡는다.",
                "Ctrl+C로 멈춘다. 파일은 ~/vica_data/bags/<이름>/ 에 남는다.",
            ),
            command="bash $VICA_ROOT/scripts/vica_drive_record.sh run$(date +%H%M)",
            mode=HOLD,
        ),
        "save": Term(
            title="save",
            note=(
                "지도 저장 + 앱용 png 변환 + 검증을 한 번에 한다.",
                "이름을 바꾸려면 위 화살표로 꺼내 마지막 인자만 고친다.",
                "",
                "같은 이름이 이미 있으면 거부한다 — 어렵게 그린 지도를 덮어쓰지 않는다.",
                "SLAM 이 안 떠 있으면 저장을 시작하지 않는다. map_saver_cli 가 /map 없이도",
                "timeout 까지 조용히 기다린 뒤 빈 손으로 끝나기 때문이다.",
                "",
                "png 를 함께 만드는 이유는 앱이 maps/*.png 만 훑기 때문이다.",
                "pgm 만 있으면 지도를 떠도 앱 목록에 나타나지 않는다.",
                "성공하면 maps/CURRENT_MAP 이 갱신된다.",
                "",
                "제한시간은 120 초다(map_saver_cli 기본값 2 초). 노드가 십수 개 뜬",
                "상태에서는 /map 구독을 맺는 데만 2 초를 넘겨, 지도가 멀쩡히 발행",
                "중인데도 'Failed to spin map subscription' 으로 끝난다.",
                "정상일 때는 첫 장이 오는 즉시 끝나므로 길게 잡아도 느려지지 않는다.",
                "더 필요하면 앞에 붙인다:  VICA_MAP_SAVE_TIMEOUT=300",
            ),
            command="bash $VICA_ROOT/scripts/vica_map_save.sh vica_map_$(date +%m%d)",
            mode=HOLD,
        ),
        "handle": Term(
            title="⑭ handle",
            note=(
                "스마트핸들. /odom을 보고 회전 예고를 /vica/turn_guide로 낸다.",
                "핸들 하드웨어가 연결돼 있어야 driver 쪽이 의미가 있다.",
                "바퀴를 돌리지 않으므로 순서 제약은 없지만 /odom이 먼저 나와야 한다.",
            ),
            command="ros2 launch vica_user_guidance user_guidance.launch.py",
            mode=HOLD,
                    guard=("turn_guide_node", "user_guidance_d",),
),
        "rviz": Term(
            title="rviz",
            note=(
                "[무거움] 원격(xrdp)에서 CPU 코어 2개를 쓴다. 주행 중에는 끄는 것이 낫다.",
                "켜둔 채 주행하면 Nav2 계산이 밀려 '로봇이 느린 것'과 구분되지 않는다.",
                "초기 위치는 왼쪽 initpose 칸으로 넣을 수 있어 RViz 없이도 주행한다.",
                "Fixed Frame이 map이어야 2D Pose Estimate가 AMCL에 닿는다.",
                "지도 확인이 끝나면 Ctrl+C로 바로 끈다.",
            ),
            command=(
                "ros2 run rviz2 rviz2 -d"
                " $VICA_ROS_WS/src/vica_description/rviz/urdf.rviz"
            ),
            mode=HOLD,
                    guard=("rviz2",),
),
        "reset": Term(
            title="reset",
            note=(
                "E-stop reset(유지보수). 모든 위험 원인을 직접 해제 확인한 뒤에만 실행한다.",
                "거부되면 로그의 active sources 를 읽는다 — 그것이 아직 남은 원인이다.",
                "정본은 로그인한 관리자가 앱에서 하는 단일 reset이다. 이 칸은 그 대체가 아니다.",
                "",
                "선행 조건은 ④ safety 와 ⑤ motor 다. /motor/can_ok 가 래치 원인의 하나라",
                "motor node 가 없으면 motor_can_stale 이 남아 reset 이 거부된다.",
                "고장이 아니라 설계다 — 동력 상태를 모르는 채로는 풀지 않는다.",
            ),
            command='ros2 service call /safety_reset std_srvs/srv/Trigger "{}"',
            mode=HOLD,
        ),
        "check": Term(
            title="check",
            note=(
                "기동 검증용 칸이다. 자주 쓰는 확인 명령:",
                "  ros2 topic hz /scan                             LiDAR",
                "  ros2 topic hz /odom                             EKF 출력, 발행자 1개인지",
                "  ros2 topic hz /nvblox_node/static_map_slice     9Hz 부근이면 정상",
                "  ros2 lifecycle get /local_costmap/local_costmap active [3]",
                "  ros2 topic echo /cmd_vel_req                    Nav2 최종 요청",
                "  ros2 topic echo /cmd_vel_safe                   Safety 승인 출력",
                "  ros2 topic hz /robot/health                     감시 1Hz",
                "[금지] ros2 CLI를 timeout으로 죽이지 말 것. /dev/shm도 건드리지 말 것.",
            ),
            command="ros2 node list",
            mode=HOLD,
        ),
        "teleop": Term(
            title="teleop",
            note=(
                "[TEST ONLY][바퀴가 돕니다] /cmd_vel 을 /cmd_vel_req 로 remap해 Safety를 거친다.",
                "Nav2 주행 중에는 명령이 충돌하므로 쓰지 않는다.",
            ),
            command=(
                "ros2 run teleop_twist_keyboard teleop_twist_keyboard"
                " --ros-args -r /cmd_vel:=/cmd_vel_req"
            ),
            mode=HOLD,
        ),
        "shell": Term(
            title="shell",
            note=(
                "source까지 끝난 자유 터미널이다. 임시 확인은 여기서 한다.",
                "다른 칸을 Ctrl+C로 끊고 재사용하면 그 단계가 내려간다. 이 칸을 대신 쓴다.",
            ),
            mode=SHELL,
        ),
    }


class Profile:
    """레이아웃 하나. 열 → 칸 이름 목록으로 정의한다."""

    def __init__(
        self,
        layout: str,
        title: str,
        summary: str,
        basis: str,
        columns: list[list[str]],
    ) -> None:
        self.layout = layout
        self.title = title
        self.summary = summary
        # 이 조합을 그렇게 정한 근거. 사람이 프로파일을 고를 때 읽는다.
        self.basis = basis
        self.columns = columns

    @property
    def size(self) -> int:
        return sum(len(column) for column in self.columns)


# 열 배치는 왼쪽부터 기동 순서다. 같은 열 안에서도 위에서 아래로 순서가 흐른다.
PROFILES: dict[str, Profile] = {
    "full": Profile(
        layout="vica",
        title="VICA bringup (full)",
        summary="주행 전체 — 매뉴얼 ⓪~⑬ 과 조작·점검 칸",
        basis="2026-08-01 실기에서 두 번 올린 조합. 음성까지 포함한 종단 구성이다.",
        columns=[
            ["power", "can", "display", "lidar", "safety"],
            ["motor", "d455", "imu", "nvblox", "nav2"],
            ["mission", "app", "gui", "monitor", "handle"],
            ["initpose", "goto", "record", "reset", "rviz"],
            ["llm", "stt", "check", "teleop", "shell"],
        ],
    ),
    "drive": Profile(
        layout="vica_drive",
        title="VICA bringup (drive, 음성 제외)",
        summary="주행 전체에서 ⑫⑬ 음성만 뺀 구성",
        basis=(
            "매뉴얼 5절이 '⑫⑬은 앱·CLI만 쓸 때 생략 가능'이라고 적었고, 2026-08-01에도"
            " 목적지 요청을 goto CLI로만 넣은 구간이 있다. GPU 여유도 그만큼 늘어난다."
        ),
        columns=[
            ["power", "can", "display", "lidar", "safety"],
            ["motor", "d455", "imu", "nvblox", "nav2"],
            ["mission", "app", "gui", "monitor", "handle"],
            ["initpose", "goto", "record", "reset", "rviz"],
            ["check", "teleop", "shell"],
        ],
    ),
    "app": Profile(
        layout="vica_app",
        title="VICA app 검증",
        summary="앱·안전·감시 종단 검증 — 라이다·카메라·Nav2 없음",
        basis=(
            "devlog/2026-07-31-health-monitor-implementation.md 16.1의 실측 구성 그대로다."
            " 센서를 일부러 빼서 결함이 뜨게 두고 앱의 오류 표시와 reset 거부 사유를 본다."
            " 모터는 reset이 /motor/can_ok 를 요구해서 2단계로 올린다."
        ),
        columns=[
            ["can", "safety", "monitor", "motor"],
            ["app", "gui", "reset", "shell"],
        ],
    ),
    "sensor": Profile(
        layout="vica_sensor",
        title="VICA sensor 확인",
        summary="센서·인지·감시만 — CAN도 모터도 올리지 않는다",
        basis=(
            "nvblox 유령 장애물 조사나 GPU 경합 측정처럼 주행 없이 인지만 보는 작업용이다."
            " 바퀴가 도는 칸을 아예 넣지 않아 잘못 눌러도 로봇이 움직이지 않는다."
        ),
        columns=[
            ["power", "display", "lidar", "d455"],
            ["imu", "nvblox", "monitor", "shell"],
        ],
    ),
    "map": Profile(
        layout="vica_map",
        title="VICA 지도 작성 (Cartographer)",
        summary="지도를 그려서 저장하고 앱 형식까지 바꾼다 — Nav2 없음",
        basis=(
            "Cartographer 는 /scan 과 오도메트리 토픽 하나만 본다"
            " (vica_2d.lua: use_odometry = true, use_imu_data = false)."
            " nvblox·Mission·앱·음성은 지도 작성에 관여하지 않아 뺐다."
            " nav2 는 뺀 것이 아니라 넣으면 안 되는 것이다 — SLAM 과 EKF·map→odom TF"
            " 가 충돌한다."
            " motor 는 뺄 수 없다. 엔코더 피드백을 요청하는 쪽이 motor node 라서,"
            " 없으면 /wheel/odom 이 나오지 않는다."
            " d455·imu 는 뺐다. slam 칸이 odom_topic:=/wheel/odom 으로 뜨므로 IMU 가"
            " 지도에 닿는 유일한 통로(EKF)가 끊긴다 — /imu/base_link 의 구독자는"
            " ekf.yaml 하나뿐이고 Cartographer 는 use_imu_data = false 다."
            " EKF 자체는 slam 칸의 launch 가 함께 띄운다. odom→base_footprint TF 의"
            " 유일한 발행자라 끄면 map→odom 이 나오지 않는다."
            " rviz 는 주행 프로파일과 달리 여기서는 필수다 — 지도가 자라는 것을 보지"
            " 않고는 어디를 더 돌아야 하는지 알 수 없다."
            " reset 은 teleop 앞에 둔다. 중앙 래치는 기동 직후 latched 로 시작하고"
            " /motor/can_ok 가 원인의 하나라, safety·motor 가 다 뜬 뒤에야 풀린다."
            " 풀지 않으면 teleop 을 눌러도 /cmd_vel_safe 가 나가지 않아 로봇을"
            " 끌고 다닐 수 없다 — 지도 작성 자체가 시작되지 않는다."
        ),
        columns=[
            ["power", "can", "display", "lidar", "safety"],
            ["motor", "reset", "slam", "teleop"],
            ["rviz", "save", "check", "shell"],
        ],
    ),
}


RC_TEMPLATE = """\
# 자동 생성 파일 — scripts/vica_terminator_layout.py 가 다시 만든다. 직접 고치지 말 것.
[ -f "$HOME/.bashrc" ] && source "$HOME/.bashrc"
{helper_block}{ros_block}{overlay_block}{cd_block}
printf '\\n\\033[1;36m=== %s ===\\033[0m\\n' {title_q}
{note_block}printf '\\n'
{map_block}{precheck_block}{run_block}
"""

ROS_BLOCK = """\
# 운영 빌드 워크스페이스. 다른 빌드를 쓰려면 터미널을 띄우기 전에 export 한다.
# 대기 중인 명령이 $VICA_ROS_WS 를 그대로 담고 있으므로 export 해서 자식에도 넘긴다.
export VICA_ROS_WS="${{VICA_ROS_WS:-{ros_ws}}}"
# 저장소 루트. scripts/ 아래 도구(goto·initpose·record)가 여기를 기준으로 돈다.
# 워크스페이스의 부모라 별도 인자 없이 유도한다.
export VICA_ROOT="${{VICA_ROOT:-$(dirname "$VICA_ROS_WS")}}"

# 현재 지도를 한 곳에서 정한다. nav2·mission·app·initpose 가 모두 이 값을 읽으므로
# 칸마다 다른 지도를 보는 일이 생기지 않는다. 2026-08-13 이전에는 생성 시점의
# 이름이 칸마다 박혀 있어서, nav2·mission 은 0810 을 보고 initpose 는 0630 을 보는
# 상태로 주행했다. 어느 쪽도 오류를 내지 않아 눈에 띄지 않았다.
#
# 우선순위는 환경변수 > maps/CURRENT_MAP > 아래 fallback 이다.
#
# CURRENT_MAP 은 "가장 새 지도"가 아니라 "마지막으로 끝까지 성공한 저장"이다.
# vica_map_save.sh 가 마지막 단계까지 통과했을 때만 쓴다 — png 변환이나 검증에서
# 멈추면 옛 이름이 그대로 남는다. 반쪽짜리 지도가 현재 지도가 되지 않게 하려는
# 것이라 의도한 동작이다.
if [ -n "$VICA_MAP_ID" ]; then
  VICA_MAP_SRC="환경변수"
else
  # 손으로 고쳤을 때를 대비해 첫 줄만 읽고 공백을 턴다.
  VICA_MAP_ID=$(head -1 "$VICA_ROS_WS/maps/CURRENT_MAP" 2>/dev/null | tr -d '[:space:]')
  VICA_MAP_SRC="maps/CURRENT_MAP"
fi
if [ -z "$VICA_MAP_ID" ]; then
  VICA_MAP_ID={map_id}
  VICA_MAP_SRC="fallback — CURRENT_MAP 이 없다"
fi
export VICA_MAP_ID VICA_MAP_SRC
export VICA_MAP_YAML="$VICA_ROS_WS/maps/$VICA_MAP_ID.yaml"
export VICA_DEST_YAML="$HOME/vica_data/destinations/$VICA_MAP_ID/destinations.yaml"

source /opt/ros/humble/setup.bash
if [ -f "$VICA_ROS_WS/install/setup.bash" ]; then
  source "$VICA_ROS_WS/install/setup.bash"
else
  printf '\\033[0;31m[경고]\\033[0m %s 가 없다. colcon build 를 먼저 한다.\\n' \\
    "$VICA_ROS_WS/install/setup.bash"
fi
export ROS_DOMAIN_ID=7
export ROS_LOCALHOST_ONLY=0
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
"""

# 아래 도우미들은 ros 여부와 무관하게 모든 칸에 넣는다.
#
# 2026-08-13 이전에는 이 정의가 ROS_BLOCK 안에 있었다. 그래서 `ros=False` 인 칸
# (nvblox·gui)은 vica_guard 를 부르는데 정의는 없는 rc 를 받았고, "command not
# found" 로 127이 나면서 GUARD_BLOCK 의 `|| return` 이 rc 를 거기서 끊었다.
# 뒤에 오는 history -s 까지 못 가므로 위 화살표를 눌러도 명령이 나오지 않았다.
# 중복 방지가 사라진 것보다 이쪽이 먼저 눈에 띄었을 뿐, 두 가지가 함께 깨져 있었다.
#
# 조건부로 넣으면 같은 결함이 되살아난다. 함수 정의뿐이라 비용이 없으므로 항상 넣는다.
HELPER_BLOCK = """\
# 패키지 존재 확인. AMENT_PREFIX_PATH만 훑으므로 ros2 CLI도 DDS도 건드리지 않는다.
vica_have_pkg() {
  local _pkg="$1" _prefix
  local IFS=:
  for _prefix in $AMENT_PREFIX_PATH; do
    [ -f "$_prefix/share/ament_index/resource_index/packages/$_pkg" ] && return 0
  done
  return 1
}

# 같은 노드가 이미 떠 있는지 본다. 인자는 `pgrep -x`가 쓰는 comm 이름들이다.
#
# 2026-08-01에 이것 때문에 하루를 잃었다. 터미네이터를 두 화면(:1, :10)에 띄워
# 스택이 통째로 두 벌 돌았고, /odom 발행자가 둘이 되어 위치가 튀었다. 뒤이어
# RViz만 두 개 뜬 적도 있었는데 그때는 CPU가 모자라 EKF가 설정 30 Hz의 절반인
# 15.5 Hz로 떨어졌다(RViz 하나가 코어 1.5개를 쓴다). 둘 다 증상이 "위치추정
# 오류"로 나타나 설정을 의심하며 시간을 썼다.
#
# ros2 CLI를 쓰지 않는다. DDS graph는 죽은 노드를 한동안 캐시해서 오탐이 나고,
# 조회 자체가 느리다. 프로세스 테이블이 지금 이 순간의 사실이다.
vica_running() {
  local _name _pid _self=$$
  for _name in "$@"; do
    for _pid in $(pgrep -x "$_name" 2>/dev/null); do
      [ "$_pid" = "$_self" ] && continue
      return 0
    done
  done
  return 1
}

# 실행 직전 중복을 막는다. 이미 떠 있으면 명령을 내보내지 않는다.
vica_guard() {
  if vica_running "$@"; then
    printf '\\033[0;31m[중복]\\033[0m 이미 실행 중입니다:\\n'
    local _n _p
    for _n in "$@"; do
      for _p in $(pgrep -x "$_n" 2>/dev/null); do
        printf '  %-20s pid %-8s 경과 %s초\\n' "$_n" "$_p" \\
          "$(ps -o etimes= -p "$_p" 2>/dev/null | tr -d ' ')"
      done
    done
    printf '\\033[0;33m두 벌이 돌면 /odom 발행자가 둘이 되어 위치가 튑니다.\\033[0m\\n'
    printf '그 칸에서 Ctrl+C 로 내리고 다시 실행하거나, 이 칸을 쓰지 마세요.\\n'
    printf '그래도 띄우려면: \\033[0;36mVICA_FORCE=1\\033[0m 을 붙여 실행합니다.\\n\\n'
    [ -n "$VICA_FORCE" ] || return 1
    printf '\\033[0;33m[VICA_FORCE] 경고를 무시하고 진행합니다.\\033[0m\\n'
  fi
  return 0
}
"""

# 감시 패키지는 운영 빌드에 없을 수 있다. 없을 때만 overlay를 덧씌운다.
# 두 워크스페이스는 DDS로 통신하므로 나머지 노드와 섞여도 문제가 없다.
OVERLAY_BLOCK = """
if ! vica_have_pkg vica_system_monitor; then
  for _ws in "${{VICA_MONITOR_WS:-}}" {candidates}; do
    [ -n "$_ws" ] || continue
    if [ -d "$_ws/install/vica_system_monitor" ] \\
       && [ -f "$_ws/install/local_setup.bash" ]; then
      source "$_ws/install/local_setup.bash"
      printf '\\033[0;36m[overlay]\\033[0m vica_system_monitor <- %s\\n' "$_ws"
      break
    fi
  done
  unset _ws
fi
if ! vica_have_pkg vica_system_monitor; then
  printf '\\033[0;31m[경고]\\033[0m vica_system_monitor 를 찾지 못했다.\\n'
  printf '        운영 빌드에 없으면 dev worktree 에서 빌드하거나\\n'
  printf '        VICA_MONITOR_WS 로 경로를 지정한다.\\n'
fi
if ! vica_have_pkg diagnostic_aggregator; then
  printf '\\033[0;31m[경고]\\033[0m diagnostic_aggregator 미설치 — aggregator 기동에 실패한다.\\n'
  printf '        sudo apt install -y ros-humble-diagnostic-aggregator\\n'
fi
"""

PRECHECK_BLOCK = """\
printf '\\033[0;34m현재 상태\\033[0m\\n'
{precheck}
printf '\\n'
"""

# 지도를 쓰는 칸에서만 어느 지도인지 눈에 보이게 한다. 칸끼리 어긋나는 사고는
# 전부 "조용히 어긋남"이라, 사람이 명령을 누르기 전에 소리를 내게 하는 것이
# 가장 값싼 방어다. 목적지 카탈로그를 함께 보는 이유는 지도만 있고 카탈로그가
# 없는 상태가 실제로 흔하기 때문이다 — 방금 그린 지도가 늘 그렇다.
MAP_BLOCK = """\
printf '\\033[0;36m현재 지도\\033[0m %s  \\033[0;37m(%s)\\033[0m\\n' \\
  "$VICA_MAP_ID" "$VICA_MAP_SRC"
if [ ! -f "$VICA_MAP_YAML" ]; then
  printf '\\033[0;31m[경고]\\033[0m 지도 파일이 없다: %s\\n' "$VICA_MAP_YAML"
  printf '        maps/ 를 확인하고 VICA_MAP_ID 를 다시 정한다.\\n'
fi
if [ ! -f "$VICA_DEST_YAML" ]; then
  printf '\\033[0;31m[경고]\\033[0m 목적지 카탈로그가 없다: %s\\n' "$VICA_DEST_YAML"
  printf '        Mission Manager 는 정상으로 뜬 채 모든 목적지 요청을 막는다.\\n'
  printf '        새로 그린 지도는 늘 이 상태다 — 목적지를 먼저 등록한다.\\n'
fi
printf '\\n'
"""

GUARD_BLOCK = """\
vica_guard {names} || return 2>/dev/null || exit 0
"""

AUTO_BLOCK = """\
printf '\\033[0;32m실행:\\033[0m %s\\n\\n' {command_q}
{command}
"""

HOLD_BLOCK = """\
history -s {command_q}
printf '\\033[0;33m대기 중\\033[0m — 위 화살표(↑) 한 번 + Enter 로 실행합니다:\\n'
printf '  %s\\n\\n' {command_q}
"""

SHELL_BLOCK = """\
printf '\\033[0;32m준비 완료\\033[0m — 명령을 직접 입력하세요.\\n\\n'
"""


def shell_quote(text: str) -> str:
    """작은따옴표로 안전하게 감싼다."""
    return "'" + text.replace("'", "'\\''") + "'"


def rc_name(term_key: str) -> str:
    return f"t_{term_key}"


def render_rc(term: Term, ros_ws: Path, fallback_map_id: str) -> str:
    """터미널 한 칸의 rc 내용을 만든다.

    `fallback_map_id`는 `maps/CURRENT_MAP`이 없을 때만 쓰인다. 생성 시점의
    이름을 명령에 박지 않는다 — 그것이 칸마다 지도가 갈리던 원인이었다.
    """
    ros_block = (
        ROS_BLOCK.format(ros_ws=ros_ws, map_id=fallback_map_id) if term.ros else ""
    )

    if term.monitor_overlay:
        candidates = " ".join(f'"{path}"' for path in MONITOR_OVERLAYS)
        overlay_block = OVERLAY_BLOCK.format(candidates=candidates)
    else:
        overlay_block = ""

    if term.workdir:
        # 경로가 사라졌을 때 조용히 홈에서 실행되는 사고를 막는다.
        cd_block = (
            f'cd "{term.workdir}" || printf '
            f"'\\033[0;31m[경고]\\033[0m 작업 디렉터리 없음: %s\\\\n' "
            f'"{term.workdir}"\n'
        )
    else:
        cd_block = ""

    note_block = "".join(
        f"printf '\\033[0;37m%s\\033[0m\\n' {shell_quote(line)}\n" for line in term.note
    )

    precheck_block = (
        PRECHECK_BLOCK.format(precheck=term.precheck) if term.precheck else ""
    )

    # 중복 검사. auto 는 바로 실행하므로 실행 직전에, hold 는 사람이 누르기 전에
    # 알려 주면 되므로 명령을 history 에 넣기 전에 둔다. 둘 다 같은 자리다.
    if term.guard:
        names = " ".join(f'"{n}"' for n in term.guard)
        guard_block = GUARD_BLOCK.format(names=names)
    else:
        guard_block = ""

    if term.mode == AUTO:
        run_block = AUTO_BLOCK.format(
            command=term.command, command_q=shell_quote(term.command)
        )
    elif term.mode == SHELL:
        run_block = SHELL_BLOCK
    else:
        run_block = HOLD_BLOCK.format(command_q=shell_quote(term.command))

    return RC_TEMPLATE.format(
        helper_block=HELPER_BLOCK,
        ros_block=ros_block,
        overlay_block=overlay_block,
        cd_block=cd_block,
        title_q=shell_quote(term.title),
        note_block=note_block,
        map_block=MAP_BLOCK if term.uses_map else "",
        precheck_block=precheck_block + guard_block,
        run_block=run_block,
    )


def check_rc(key: str, term: Term, text: str) -> None:
    """만들어 낸 rc 가 스스로를 끊지 않는지 본다.

    rc 가 중간에서 멈추면 터미널은 멀쩡히 열린다. 머리말은 이미 찍혔고 프롬프트도
    뜨므로 눈으로는 정상과 구별되지 않는다 — 위 화살표를 눌러 봐야 비어 있는 것을
    안다. 그래서 사람 눈이 아니라 여기서 잡는다.
    """
    if "\nvica_guard " in text and "vica_guard() {" not in text:
        raise SystemExit(
            f"[오류] 칸 '{key}' 의 rc 가 vica_guard 를 부르는데 정의가 없다.\n"
            "       실행하면 command not found 로 127 이 나고 rc 가 거기서 끊긴다."
        )

    if term.mode == HOLD and "history -s " not in text:
        raise SystemExit(
            f"[오류] 칸 '{key}' 는 대기(HOLD) 인데 rc 에 history -s 가 없다.\n"
            "       위 화살표를 눌러도 명령이 나오지 않는다."
        )


def write_rc_files(
    terms: dict[str, Term], used: set[str], ros_ws: Path, fallback_map_id: str
) -> dict[str, Path]:
    """선택된 프로파일이 쓰는 rc 파일만 만들고 경로를 돌려준다."""
    RC_DIR.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}

    for key in sorted(used):
        path = RC_DIR / f"{rc_name(key)}.rc"
        text = render_rc(terms[key], ros_ws, fallback_map_id)
        check_rc(key, terms[key], text)
        path.write_text(text, encoding="utf-8")
        paths[key] = path

    return paths


def build_layout(
    profile: Profile, terms: dict[str, Term], rc_paths: dict[str, Path]
) -> str:
    """Terminator config 의 `[[레이아웃]]` 블록 문자열을 만든다.

    열은 오른쪽으로 이어지는 HPaned 사슬, 행은 아래로 이어지는 VPaned 사슬이다.
    남은 칸 수로 ratio를 정해서 열·행 수가 달라도 균등 분할이 된다.
    """
    lines = [f"  [[{profile.layout}]]"]

    def node(name: str, **fields: object) -> None:
        lines.append(f"    [[[{name}]]]")
        for key, value in fields.items():
            lines.append(f"      {key} = {value}")

    def terminal(key: str, parent: str, order: int) -> None:
        node(
            rc_name(key),
            type="Terminal",
            parent=parent,
            order=order,
            profile="default",
            command=f"bash --rcfile {rc_paths[key]}",
            title=terms[key].title,
        )

    node("window0", type="Window", parent='""', title=profile.title)

    columns = profile.columns
    total = len(columns)

    # 열 부모를 정한다. 열이 하나면 창에 바로 붙인다.
    column_parents: list[tuple[str, int]] = []
    if total == 1:
        column_parents.append(("window0", 0))
    else:
        parent, order = "window0", 0
        for index in range(total - 1):
            name = f"hp{index}"
            node(
                name,
                type="HPaned",
                parent=parent,
                order=order,
                ratio=round(1.0 / (total - index), 4),
            )
            column_parents.append((name, 0))
            parent, order = name, 1
        # 마지막 열은 직전 HPaned 의 오른쪽 자리다.
        column_parents.append((parent, 1))

    for index, (column, (parent, order)) in enumerate(zip(columns, column_parents)):
        rows = len(column)
        if rows == 1:
            terminal(column[0], parent, order)
            continue

        current_parent, current_order = parent, order
        for depth in range(rows - 1):
            vp_name = f"vp{index}_{depth}"
            node(
                vp_name,
                type="VPaned",
                parent=current_parent,
                order=current_order,
                ratio=round(1.0 / (rows - depth), 4),
            )
            terminal(column[depth], vp_name, 0)
            current_parent, current_order = vp_name, 1

        terminal(column[-1], current_parent, 1)

    return "\n".join(lines) + "\n"


def strip_layout(text: str, name: str) -> str:
    """`[layouts]` 안의 `[[name]]` 블록을 통째로 지운다."""
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    skipping = False

    for line in lines:
        if re.match(rf"^  \[\[{re.escape(name)}\]\]\s*$", line):
            skipping = True
            continue
        if skipping:
            # 같은 깊이의 다음 레이아웃이나 최상위 섹션을 만나면 멈춘다.
            if re.match(r"^  \[\[[^\[]", line) or re.match(r"^\[[^\[]", line):
                skipping = False
            else:
                continue
        out.append(line)

    return "".join(out)


def insert_layout(text: str, block: str) -> str:
    """`[layouts]` 섹션 끝에 블록을 넣는다."""
    lines = text.splitlines(keepends=True)
    start = None
    for index, line in enumerate(lines):
        if line.startswith("[layouts]"):
            start = index
            break
    if start is None:
        return text.rstrip("\n") + "\n[layouts]\n" + block

    end = len(lines)
    for index in range(start + 1, len(lines)):
        if re.match(r"^\[[^\[]", lines[index]):
            end = index
            break

    return "".join(lines[:end]) + block + "".join(lines[end:])


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="VICA 기동용 Terminator 레이아웃을 만든다.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="프로파일:\n"
        + "\n".join(
            f"  {key:7s} {profile.layout:12s} {profile.size:2d}칸  {profile.summary}"
            for key, profile in PROFILES.items()
        ),
    )
    parser.add_argument(
        "--profile",
        choices=(*PROFILES, "all"),
        default="all",
        help="만들 프로파일. 기본은 all — 네 레이아웃을 한 번에 만든다.",
    )
    parser.add_argument(
        "--map-id",
        default=DEFAULT_MAP_ID,
        help="maps/CURRENT_MAP 이 없을 때만 쓰는 fallback 지도 id."
        f" 기본 {DEFAULT_MAP_ID}. 평소 지도는 실행 시점에 CURRENT_MAP 이 정하므로"
        " 이 값을 바꿔도 대개 아무 영향이 없다. 지도를 바꾸려면 터미네이터를 띄우기"
        " 전에 VICA_MAP_ID 를 export 한다.",
    )
    parser.add_argument(
        "--ros-ws",
        type=Path,
        default=DEFAULT_ROS_WS,
        help=f"운영 빌드 워크스페이스. 기본 {DEFAULT_ROS_WS}",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="프로파일 구성과 근거만 출력하고 끝낸다.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="rc 파일과 config 를 쓰지 않고 무엇을 만들지만 출력한다.",
    )
    return parser.parse_args(argv)


def print_profiles(terms: dict[str, Term]) -> None:
    for key, profile in PROFILES.items():
        print(f"\n[{key}] {profile.layout} — {profile.summary} ({profile.size}칸)")
        print(f"  근거: {profile.basis}")
        for index, column in enumerate(profile.columns, start=1):
            titles = " · ".join(terms[name].title for name in column)
            print(f"  {index}열: {titles}")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    terms = build_terms()

    # 정의만 검사한다. 오타 난 칸 이름은 config 를 쓰기 전에 잡는다.
    for key, profile in PROFILES.items():
        for column in profile.columns:
            for name in column:
                if name not in terms:
                    print(
                        f"[오류] 프로파일 '{key}' 가 없는 칸 '{name}' 을 참조한다.",
                        file=sys.stderr,
                    )
                    return 1

    # guard 이름 길이. 리눅스 comm 은 15자에서 잘리므로(TASK_COMM_LEN 16, NUL 포함)
    # 16자로 적은 이름은 `pgrep -x` 가 영원히 못 맞춘다. 검사가 통과하는 것처럼
    # 보이면서 중복 실행 방지만 조용히 꺼진다 — 2026-08-12 에 motor·mission·app
    # 세 칸이 실제로 그 상태였다. 눈으로는 안 보이므로 여기서 막는다.
    for key, term in terms.items():
        for name in term.guard:
            if len(name) > 15:
                print(
                    f"[오류] 칸 '{key}' 의 guard 이름이 15자를 넘는다: '{name}'"
                    f" ({len(name)}자).\n"
                    "       리눅스 comm 은 15자에서 잘려 pgrep -x 가 못 맞춘다."
                    " 실기에서 `ps -eo comm=` 로 잘린 이름을 확인해 적는다.",
                    file=sys.stderr,
                )
                return 1

    if args.list:
        print_profiles(terms)
        return 0

    selected = list(PROFILES) if args.profile == "all" else [args.profile]
    used = {name for key in selected for column in PROFILES[key].columns for name in column}

    if not args.ros_ws.exists():
        # 치명적이지는 않다. rc 는 실행 시점에 다시 확인하고 경고한다.
        print(f"[경고] 워크스페이스가 지금은 없다: {args.ros_ws}", file=sys.stderr)

    if args.dry_run:
        print(f"fallback 지도 id: {args.map_id}")
        print(f"워크스페이스: {args.ros_ws}")
        print(f"rc 파일 {len(used)}개 예정: {RC_DIR}")
        for key in selected:
            profile = PROFILES[key]
            print(f"레이아웃 '{profile.layout}' — 터미널 {profile.size}개")
        print("(dry-run: 아무것도 쓰지 않았다)")
        return 0

    rc_paths = write_rc_files(terms, used, args.ros_ws, args.map_id)
    print(f"rc 파일 {len(rc_paths)}개 생성: {RC_DIR}")

    if TERMINATOR_CONFIG.exists():
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = TERMINATOR_CONFIG.with_suffix(f".bak.{stamp}")
        shutil.copy2(TERMINATOR_CONFIG, backup)
        print(f"기존 config 백업: {backup}")
        text = TERMINATOR_CONFIG.read_text(encoding="utf-8")
    else:
        TERMINATOR_CONFIG.parent.mkdir(parents=True, exist_ok=True)
        text = "[layouts]\n"

    # 이 스크립트가 만든 레이아웃은 모두 지우고 다시 넣는다. 선택하지 않은
    # 프로파일의 옛 블록이 남아 rc 와 어긋나는 것을 막는다.
    for name in OBSOLETE_LAYOUTS:
        text = strip_layout(text, name)

    for key in selected:
        profile = PROFILES[key]
        text = insert_layout(text, build_layout(profile, terms, rc_paths))

    TERMINATOR_CONFIG.write_text(text, encoding="utf-8")

    # 지도는 생성 시점이 아니라 실행 시점에 정해진다. 지금 무엇이 잡힐지 그대로
    # 보여 준다 — 여기서 한 번 보고 나면 칸을 띄우고 놀랄 일이 없다.
    current = args.ros_ws / "maps" / "CURRENT_MAP"
    if current.is_file() and current.read_text(encoding="utf-8").split():
        map_id = current.read_text(encoding="utf-8").split()[0]
        print(f"현재 지도: {map_id}  (maps/CURRENT_MAP)")
    else:
        map_id = args.map_id
        print(f"현재 지도: {map_id}  (fallback — CURRENT_MAP 이 없다)")
    if not (args.ros_ws / "maps" / f"{map_id}.yaml").is_file():
        print(f"  [경고] 지도 파일이 없다: maps/{map_id}.yaml", file=sys.stderr)
    if not (HOME / "vica_data" / "destinations" / map_id / "destinations.yaml").is_file():
        print(
            f"  [경고] 목적지 catalog 가 없다: ~/vica_data/destinations/{map_id}/",
            file=sys.stderr,
        )
    print("  바꾸려면 터미네이터를 모두 닫고 export VICA_MAP_ID=<이름> 뒤 다시 띄운다.")
    for key in selected:
        profile = PROFILES[key]
        auto = sum(
            1
            for column in profile.columns
            for name in column
            if terms[name].mode == AUTO
        )
        print(
            f"레이아웃 '{profile.layout}' — 터미널 {profile.size}개"
            f" (자동 {auto} / 대기 {profile.size - auto})"
            f"   terminator -l {profile.layout}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
