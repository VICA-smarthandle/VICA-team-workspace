#!/usr/bin/env python3
"""VICA 기동용 Terminator 레이아웃 생성기.

`docs/vica_robot_bringup_manual.md`의 실행 순서를 15개 터미널(3열 x 5행)로 배치한다.

각 터미널은 전용 rc 파일로 bash를 띄운다. rc가 하는 일:

1. `~/.bashrc`를 읽어 개인 alias·함수(`vica_rs` 등)를 살린다
2. ROS 2와 `vica_ros2_ws`를 source하고 통신 환경변수를 맞춘다
3. 작업 디렉터리로 이동한다
4. 실행 방식에 따라 명령을 처리한다
   - auto : 바로 실행한다 (센서·TF·Safety 등 바퀴를 움직이지 않는 것)
   - hold : `history`에 넣어두고 안내만 출력한다. 위 화살표 + Enter로 실행한다

바퀴가 도는 단계(motor, Nav2, Mission, teleop)와 순서 의존성이 있는 단계
(Docker 카메라·nvblox)는 auto로 두지 않는다. 사람이 순서를 통제해야 한다.

사용법:

    python3 scripts/vica_terminator_layout.py        # 생성
    terminator -l vica                               # 실행

기존 `~/.config/terminator/config`는 타임스탬프를 붙여 백업한다.
"""
from __future__ import annotations

import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

LAYOUT_NAME = "vica"
# 이 레이아웃을 새로 만들 때 함께 지울 옛 레이아웃 이름.
OBSOLETE_LAYOUTS = ("vica", "vicavoice")

HOME = Path.home()
WORKSPACE = HOME / "VICA-smarthandle"
ROS_WS = WORKSPACE / "vica_ros2_ws"
VOICE = WORKSPACE / "vica-voice-llm"
SUPERVISOR = WORKSPACE / "VICA_Supervisor"
MAP_YAML = ROS_WS / "maps" / "vica_map_0630.yaml"
MAP_ID = "vica_map_0630"

RC_DIR = HOME / ".config" / "vica-terminator"
TERMINATOR_CONFIG = HOME / ".config" / "terminator" / "config"

AUTO = "auto"
HOLD = "hold"

# ROS source가 필요 없는 터미널(컨테이너 안에서 따로 source한다).
NO_ROS = "no_ros"


class Term:
    """터미널 한 칸."""

    def __init__(
        self,
        name: str,
        title: str,
        note: str,
        command: str,
        mode: str = HOLD,
        workdir: Path | None = None,
        ros: bool = True,
    ) -> None:
        self.name = name
        self.title = title
        self.note = note
        self.command = command
        self.mode = mode
        self.workdir = workdir
        self.ros = ros


# 열 단위로 정의한다. 왼쪽부터 센서·안전 / Docker·주행 / 음성·조작.
COLUMNS: list[list[Term]] = [
    [
        Term(
            "t_display",
            "display",
            "② URDF·TF·RViz — base_link→laser_frame TF 공급원이라 필수",
            "ros2 launch vica_description display.launch.py",
            mode=AUTO,
        ),
        Term(
            "t_lidar",
            "lidar",
            "③ LiDAR — /scan (frame_id=laser_frame)",
            "ros2 run rplidar_ros rplidar_node --ros-args"
            " -p channel_type:=serial -p serial_port:=/dev/rplidar"
            " -p serial_baudrate:=115200 -p frame_id:=laser_frame"
            " -p angle_compensate:=true -p inverted:=false"
            " -p flip_x_axis:=true -p scan_mode:=Express",
            mode=AUTO,
        ),
        Term(
            "t_safety",
            "safety",
            "④ Safety — emergency_stop_node / safety_supervisor_node / app_emergency_node",
            "ros2 launch vica_safety safety_bringup.launch.py",
            mode=AUTO,
        ),
        Term(
            "t_imu",
            "imu",
            "⑦ IMU adapter — D455(⑥) 기동 후에 의미가 있다",
            "ros2 run vica_sensor_adapters imu_base_link_adapter --ros-args"
            " -p input_topic:=/camera/camera/imu"
            " -p output_topic:=/imu/base_link"
            " -p target_frame:=base_link",
            mode=AUTO,
        ),
        Term(
            "t_motor",
            "motor",
            "①+⑤ CAN 활성화 후 motor — 바퀴가 돕니다."
            " 바퀴를 띄우고 물리 E-stop을 확인한 뒤 실행하세요",
            "can_set && ros2 launch mdrobot_can_control motor_bringup.launch.py",
        ),
    ],
    [
        Term(
            "t_d455",
            "d455",
            "⑥ D455 카메라 (Docker) — 컨테이너 진입 후 ./run_d455.sh 를 실행하세요",
            "vica_rs",
            ros=False,
        ),
        Term(
            "t_nvblox",
            "nvblox",
            "⑧ nvblox (Docker) — ⑥ 카메라가 뜬 뒤에 실행하세요",
            "docker exec -it vica_rs_container bash -lc"
            " 'source /opt/ros/humble/setup.bash"
            " && source /workspaces/isaac_ros-dev/install/setup.bash"
            " && ros2 launch vica_nvblox_bringup vica_nvblox.launch.py'",
            ros=False,
        ),
        Term(
            "t_nav2",
            "nav2",
            "⑨ Nav2 + EKF + encoder — ⑧ nvblox 이후에 실행."
            " wheel_ekf 를 따로 띄우지 마세요(중복 발행)",
            f"ros2 launch vica_nav2 nav2_map_test.launch.py map:={MAP_YAML}",
        ),
        Term(
            "t_mission",
            "mission",
            "⑩ Mission Manager — 일반 운영 Goal 의 단일 권한자",
            "ros2 launch vica_mission_manager mission_manager.launch.py"
            f" map_id:={MAP_ID} map_yaml:={MAP_YAML}",
        ),
        Term(
            "t_app",
            "app",
            "⑪ Supervisor 앱 브리지 — rosbridge 9090 / 지도 HTTP 8000",
            f"ros2 launch {SUPERVISOR}/ros2/supervisor_bringup.launch.py"
            f" map_yaml:={MAP_YAML}",
        ),
    ],
    [
        Term(
            "t_llm",
            "llm+tts",
            "⑫ 음성·LLM — 시작 로그에 '목적지 catalog가 없어' WARN 이 없어야 정상",
            f"ros2 launch launch/vica_voice.launch.py map_id:={MAP_ID}",
            workdir=VOICE,
        ),
        Term(
            "t_stt",
            "stt",
            "⑬ STT push-to-talk — 엔터로 녹음 시작, 다시 엔터로 종료",
            ".venv/bin/python -m src.ros_stt_node",
            workdir=VOICE,
        ),
        Term(
            "t_goto",
            "goto",
            "목적지 요청(CLI) — 따옴표 안 목적지명을 바꿔 실행하세요."
            " RViz 2D Pose Estimate 로 초기 위치를 먼저 잡습니다",
            f'python3 {SUPERVISOR}/ros2/vica_goto_goal.py {MAP_ID} "목적지명"',
        ),
        Term(
            "t_reset",
            "reset",
            "E-stop reset(유지보수) — 모든 위험 원인을 직접 해제 확인한 뒤에만 실행",
            'ros2 service call /safety_reset std_srvs/srv/Trigger "{}"',
        ),
        Term(
            "t_teleop",
            "teleop",
            "[TEST ONLY] 수동 조종 — /cmd_vel_req 로 보내 Safety 를 거칩니다."
            " Nav2 주행 중에는 명령이 충돌하니 쓰지 마세요",
            "ros2 run teleop_twist_keyboard teleop_twist_keyboard"
            " --ros-args -r /cmd_vel:=/cmd_vel_req",
        ),
    ],
]

RC_TEMPLATE = """\
# 자동 생성 파일 — scripts/vica_terminator_layout.py 가 다시 만든다. 직접 고치지 말 것.
[ -f "$HOME/.bashrc" ] && source "$HOME/.bashrc"
{ros_block}{cd_block}
printf '\\n\\033[1;36m=== %s ===\\033[0m\\n' "{title}"
printf '\\033[0;37m%s\\033[0m\\n\\n' "{note}"
{run_block}
"""

ROS_BLOCK = """\
source /opt/ros/humble/setup.bash
source "{ros_ws}/install/setup.bash"
export ROS_DOMAIN_ID=7
export ROS_LOCALHOST_ONLY=0
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
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


def shell_quote(text: str) -> str:
    """작은따옴표로 안전하게 감싼다."""
    return "'" + text.replace("'", "'\\''") + "'"


def write_rc_files() -> dict[str, Path]:
    """터미널별 rc 파일을 만들고 경로를 돌려준다."""
    RC_DIR.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}

    for column in COLUMNS:
        for term in column:
            ros_block = ROS_BLOCK.format(ros_ws=ROS_WS) if term.ros else ""
            cd_block = f'cd "{term.workdir}"\n' if term.workdir else ""
            quoted = shell_quote(term.command)
            if term.mode == AUTO:
                run_block = AUTO_BLOCK.format(command=term.command, command_q=quoted)
            else:
                run_block = HOLD_BLOCK.format(command_q=quoted)

            content = RC_TEMPLATE.format(
                ros_block=ros_block,
                cd_block=cd_block,
                title=term.title,
                note=term.note,
                run_block=run_block,
            )
            path = RC_DIR / f"{term.name}.rc"
            path.write_text(content, encoding="utf-8")
            paths[term.name] = path

    return paths


def build_layout(rc_paths: dict[str, Path]) -> str:
    """Terminator config 의 `[[vica]]` 블록 문자열을 만든다."""
    lines = [f"  [[{LAYOUT_NAME}]]"]

    def node(name: str, **fields: object) -> None:
        lines.append(f"    [[[{name}]]]")
        for key, value in fields.items():
            lines.append(f"      {key} = {value}")

    node("window0", type="Window", parent='""', title="VICA bringup")

    # 3열: hp0 = [열1 | hp1], hp1 = [열2 | 열3]
    node("hp0", type="HPaned", parent="window0", order=0, ratio=0.3333)
    node("hp1", type="HPaned", parent="hp0", order=1, ratio=0.5)
    column_parents = [("hp0", 0), ("hp1", 0), ("hp1", 1)]

    for index, (column, (parent, order)) in enumerate(zip(COLUMNS, column_parents)):
        # 5행을 VPaned 4단 중첩으로 균등 분할한다.
        ratios = [0.2, 0.25, 0.3333, 0.5]
        current_parent, current_order = parent, order

        for depth, ratio in enumerate(ratios):
            vp_name = f"vp{index}_{depth}"
            node(
                vp_name,
                type="VPaned",
                parent=current_parent,
                order=current_order,
                ratio=ratio,
            )
            term = column[depth]
            node(
                term.name,
                type="Terminal",
                parent=vp_name,
                order=0,
                profile="default",
                command=f"bash --rcfile {rc_paths[term.name]}",
                title=term.title,
            )
            current_parent, current_order = vp_name, 1

        last = column[-1]
        node(
            last.name,
            type="Terminal",
            parent=current_parent,
            order=1,
            profile="default",
            command=f"bash --rcfile {rc_paths[last.name]}",
            title=last.title,
        )

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


def main() -> int:
    if not ROS_WS.exists():
        print(f"[오류] ROS workspace 를 찾을 수 없습니다: {ROS_WS}", file=sys.stderr)
        return 1

    rc_paths = write_rc_files()
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

    for name in OBSOLETE_LAYOUTS:
        text = strip_layout(text, name)

    text = insert_layout(text, build_layout(rc_paths))
    TERMINATOR_CONFIG.write_text(text, encoding="utf-8")

    total = sum(len(column) for column in COLUMNS)
    auto = sum(1 for column in COLUMNS for t in column if t.mode == AUTO)
    print(f"레이아웃 '{LAYOUT_NAME}' 작성 완료 — 터미널 {total}개 (자동 {auto} / 대기 {total - auto})")
    print(f"실행: terminator -l {LAYOUT_NAME}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
