# VICA Team Workspace

VICA는 Jetson Orin NX와 ROS 2 Humble 기반의 실내 안내 AMR 프로젝트다. 이 저장소는
제품 코드를 합치는 monorepo가 아니라 팀 작업 규칙, 시스템 계약, 개발 기록과 세 제품
저장소를 같은 구조로 받기 위한 manifest를 관리한다.

## 1. 저장소와 branch

| 저장소 | 역할 | 현재 기준 |
| --- | --- | --- |
| [VICA-team-workspace](https://github.com/VICA-smarthandle/VICA-team-workspace) | 지침, 아키텍처, 시나리오, 공식 URL, manifest | 안정 `main`, 개발 `dev` |
| [vica_ros2_ws](https://github.com/VICA-smarthandle/vica_ros2_ws) | ROS 2, Nav2, SLAM, EKF, Safety, motor | 안정 `main`, 개발 `dev` |
| [vica-voice-llm](https://github.com/VICA-smarthandle/vica-voice-llm) | STT, TTS, 긴급어 감지, LLM | 현재 `main` |
| [VICA_Supervisor](https://github.com/myw411/VICA_Supervisor) | Flutter 관리자 앱과 rosbridge client | 현재 `main` |

기본 branch 역할은 단순하게 유지한다.

```text
dev   일상 개발, 문서 수정, 기능 통합과 시험
main  팀 검토와 필요한 실기 검증을 통과한 안정·배포 기준
```

- 일반 작업은 `dev`에서 commit하고 push한다.
- `main`에는 직접 push하지 않고 `dev → main` Pull Request로 반영한다.
- 공유 branch에서 force push와 history 재작성을 금지한다.
- LLM과 앱에 `dev`를 도입할 때는 branch를 먼저 만든 뒤 `workspace.repos`를 갱신한다.

## 2. 최초 설치

### 2.1 기본 도구

Ubuntu 22.04와 ROS 2 Humble이 설치된 환경을 기준으로 한다.

```bash
sudo apt update
sudo apt install -y git python3-vcstool python3-rosdep python3-colcon-common-extensions
```

### 2.2 전체 Workspace 받기

```bash
git clone https://github.com/VICA-smarthandle/VICA-team-workspace.git VICA-smarthandle
cd VICA-smarthandle
vcs import . < workspace.repos
```

완료 후 다음 제품 디렉터리가 생성된다.

```text
VICA-smarthandle/
├── vica_ros2_ws/
├── vica-voice-llm/
└── VICA_Supervisor/
```

### 2.3 ROS 외부 패키지와 dependency

```bash
cd vica_ros2_ws
vcs import < vica.repos

source /opt/ros/humble/setup.bash
rosdep update
rosdep install --from-paths src --ignore-src -r -y
sudo apt install -y ros-humble-robot-localization python3-can
```

`rosdep`이 초기화되지 않은 새 PC에서는 최초 한 번 `sudo rosdep init`을 실행한 뒤
`rosdep update`를 다시 실행한다.

### 2.4 ROS 빌드

```bash
source /opt/ros/humble/setup.bash
colcon build --symlink-install
source install/setup.bash
```

기본 확인:

```bash
colcon list
ros2 pkg prefix vica_localization
ros2 pkg executables mdrobot_can_control
```

초기 설치 확인에서는 motor/CAN launch, Nav2 Goal, teleop과 E-stop reset을 실행하지 않는다.

## 3. 매일 작업하는 방법

최상위와 세 제품 디렉터리는 각각 별도 Git 저장소다. 최상위의 `git status`만 확인하면
제품 저장소의 변경은 보이지 않는다.

```bash
git status --short
git -C vica_ros2_ws status --short
git -C vica-voice-llm status --short
git -C VICA_Supervisor status --short
```

팀 워크스페이스 문서 작업:

```bash
git switch dev
git pull --ff-only origin dev
```

ROS 작업:

```bash
git -C vica_ros2_ws switch dev
git -C vica_ros2_ws pull --ff-only origin dev
git -C vica_ros2_ws status --short
git -C vica_ros2_ws diff --check
git -C vica_ros2_ws diff
```

변경한 파일만 stage하고 commit한다.

```bash
git -C vica_ros2_ws add path/to/changed_file
git -C vica_ros2_ws diff --cached
git -C vica_ros2_ws diff --cached --check
git -C vica_ros2_ws commit -m "fix(scope): concise summary"
git -C vica_ros2_ws push origin dev
```

미추적 파일은 일반 `git diff`에 나오지 않으므로 `git status --short`를 반드시 확인한다.
같은 파일을 여러 명이 수정할 때는 작업 시작 전에 담당 범위를 팀에 공유한다.

## 4. 가장 중요한 규칙

1. 작업 전 `AGENTS.md`, `GOVERNANCE.md`와 관련 guideline을 읽는다.
2. 대상 저장소의 branch, status와 diff를 먼저 확인한다.
3. 기존 팀원의 변경을 reset, stash, 덮어쓰기 또는 임의 commit하지 않는다.
4. 실제 코드·설정·launch와 재현 결과를 현재 구현의 기준으로 사용한다.
5. 미구현은 `[TARGET]`, 끊어진 연결은 `[GAP]`, 미확인은 `[미검증]`으로 표시한다.
6. topic, service, action, message, JSON 또는 TF 변경 시 producer와 consumer를 함께 찾는다.
7. Safety, E-stop, TF와 큰 개발 방향 변경은 guideline과 devlog를 함께 갱신한다.
8. 개인 절대경로, secret, `.env`, token과 생성물을 GitHub에 올리지 않는다.
9. `source_file/` 원본은 Git에서 제외하고 공식 URL 또는 별도 공유 위치로 전달한다.
10. commit과 push 전에 diff 검사와 관련 build/test 결과를 확인한다.

## 5. 디렉터리와 핵심 파일

```text
VICA-smarthandle/
├── README.md
├── AGENTS.md
├── GOVERNANCE.md
├── CLAUDE.md
├── workspace.repos
├── guideline/
├── devlog/
├── source_file/
├── vica_ros2_ws/
├── vica-voice-llm/
└── VICA_Supervisor/
```

| 경로 | 설명 |
| --- | --- |
| `README.md` | 최초 설치, branch 사용법, 핵심 규칙과 디렉터리 안내 |
| `AGENTS.md` | AI agent가 반드시 따르는 실행 규칙 |
| `GOVERNANCE.md` | 팀 승인, 저장소 경계, 변경·배포의 최상위 기준 |
| `CLAUDE.md` | Claude가 공통 지침을 빠르게 찾기 위한 요약 |
| `workspace.repos` | 세 제품 저장소 URL과 현재 기준 branch manifest |
| `guideline/` | 시나리오, 아키텍처, BT·파일 구조와 공식 URL |
| `devlog/` | 중요한 결정, 장애 원인과 실기 검증 기록 |
| `source_file/` | 로컬 하드웨어 매뉴얼·도면 원본, Git 제외 |
| `vica_ros2_ws/` | 주행, Safety, SLAM, Nav2, motor와 공용 ROS 인터페이스 |
| `vica-voice-llm/` | 음성 입출력, 긴급어 감지와 목적지 후보 생성 |
| `VICA_Supervisor/` | 관리자 앱, 상태·지도·장소·안전 관리 UI |

### 5.1 `guideline/`

| 파일 | 설명 |
| --- | --- |
| `vica_scenario.md` | 앱 기능과 사용자·관리자 동작 시나리오 |
| `vica_architecture.md` | ROS 계약, Safety, TF와 저장소 경계 |
| `bt와 visual hierarchy of your folders and files.md` | Nav2 BT, 패키지, 폴더와 파일 구조 |
| `official_reference_urls.md` | ROS 2 Humble, Nav2, NVIDIA와 Isaac ROS 공식 문서 |

### 5.2 `vica_ros2_ws/`

```text
vica_ros2_ws/
├── README.md
├── vica.repos                       # 외부 ROS 저장소 버전
├── ekf_config/                      # 호환용, 정본은 vica_localization
└── src/
    ├── vica_interfaces/             # 공용 ROS message 정본
    ├── vica_mission_manager/        # 목적지 검증, Nav2 Goal, Mission 상태
    ├── vica_nav2/                   # 저장 지도 Nav2 launch와 parameter
    ├── vica_cartographer/           # Cartographer 2D SLAM
    ├── vica_localization/           # wheel+IMU EKF와 표준 /odom
    ├── vica_description/            # URDF, mesh와 robot_state_publisher
    ├── vica_sensor_adapters/        # IMU와 VSLAM adapter
    ├── encoder_feedback/            # MDROBOT encoder → /wheel/odom
    └── mdrobot_can_control/         # Safety Supervisor, E-stop, CAN motor
```

### 5.3 앱과 LLM

- LLM은 목적지 후보와 음성 응답을 만들지만 Nav2 Goal, `/cmd_vel*`과 CAN을 직접 제어하지 않는다.
- 앱은 관리자 로그인, 지도작성모드, Nav2 운영모드, 상태·장소·안전 관리 기능을 제공하는
  제품 요구사항을 가진다. 문서의 요구사항과 현재 구현 상태를 구분해서 관리한다.
- 앱은 Safety와 Mission Manager를 우회해 motor를 직접 제어하지 않는다.

## 6. 주행·Safety·Odometry 계약

주행 명령의 목표 경로:

```text
Nav2 /cmd_vel
→ /cmd_vel_req
→ Safety Supervisor
→ /cmd_vel_safe
→ mdrobot_can_keyboard_knob_node
→ CAN motor
```

E-stop 목표 경로:

```text
물리 버튼 · 관리자 앱 · STT 긴급어
→ emergency_stop_node 중앙 통합·래치
→ /emergency_stop
→ Mission Manager + Safety Supervisor
→ /cmd_vel_safe=0
```

Odometry 계약:

```text
/wheel/odom + /imu/base_link
→ robot_localization EKF
→ /odom + odom → base_footprint TF
```

핵심 안전 원칙:

- motor node에는 별도 E-stop 래치와 reset 권한을 두지 않는다.
- reset은 원인이 해제된 뒤 로그인한 관리자가 앱에서 명시적으로 요청한다.
- LLM과 STT에는 reset 권한이 없고 E-stop 해제 후 이전 Goal을 자동 재개하지 않는다.
- 소프트웨어 E-stop은 물리 전원·토크 차단 회로를 대체하지 않는다.
- motor/CAN, `/cmd_vel*`, Nav2 Goal과 reset은 승인과 안전 확보 없이 시험하지 않는다.
- EKF 설정 정본은 `vica_ros2_ws/src/vica_localization/config/ekf.yaml`이다.
- D455는 별도 Docker/Isaac ROS 환경에서 실행한다.

현재 Nav2 `/cmd_vel → /cmd_vel_req`, 중앙 E-stop 래치·관리자 reset과 C5+D455 실기 융합은
종단 검증 완료 상태가 아니다.

2D LiDAR는 YDLIDAR G2를 수리 보내 임시로 RPLIDAR를 `/scan` 공급원으로 사용한다(2026-07-22
기준). Nav2 costmap과 Cartographer는 공급 라이다와 무관하게 `/scan`을 입력으로 쓰므로 토픽
계약은 유지되지만, RPLIDAR 운용 동안 `laser_frame` 장착 위치와 라이다 드라이버 launch를
실측에 맞춰 확인한다. YDLIDAR G2 복귀 시 원복한다.

## 7. Build·검증·배포

ROS 패키지 최소 검증:

```bash
source /opt/ros/humble/setup.bash
colcon build --symlink-install --packages-select package_name
colcon test --packages-select package_name
colcon test-result --verbose
```

결과는 `빌드 성공`, `테스트 통과`, `정적 검사 실패`, `실기 미검증`으로 구분한다. 일부
테스트 통과를 전체 검증 완료라고 표현하지 않는다.

개발용 `workspace.repos`는 branch를 사용한다. 정식 릴리스는 세 제품 저장소의 검증된
commit SHA를 기록한 `workspace.release.repos`를 별도로 만들어 재현 가능하게 고정한다.

```text
dev에서 개발·검증
→ dev → main PR
→ 필요한 실기 검증
→ main merge
→ release manifest와 version tag 작성
```

## 8. 금지 사항

공유 작업공간에서 다음 명령을 임의로 실행하지 않는다.

```bash
git reset --hard
git checkout -- .
git clean -fd
git push --force
```

다음 항목은 GitHub에 올리지 않는다.

- `build/`, `install/`, `log/`
- `.env`, token, credential과 private key
- 개인 절대경로가 포함된 설정과 로그
- 임시 rosbag과 대용량 생성물
- `source_file/`의 PDF와 도면 원본

문제가 생기면 먼저 `git status`, `git diff`, branch와 commit hash를 팀에 공유한 뒤 복구
방법을 정한다.

## 9. 팀원용 핵심 요약

1. 팀 워크스페이스를 clone하고 `workspace.repos`로 제품 저장소를 받는다.
2. 개발은 `dev`, 안정·배포는 `main`을 사용한다.
3. `main`은 직접 push하지 않고 `dev → main` PR로 반영한다.
4. 최상위와 제품 저장소의 Git 상태를 각각 확인한다.
5. 작업 전 지침, status와 diff를 먼저 확인한다.
6. Safety·TF·공용 계약 변경은 코드와 guideline을 함께 갱신한다.
7. motor/CAN과 주행 시험은 승인과 안전 확보 없이 실행하지 않는다.
8. 테스트 실패와 실기 미검증 사항을 정확히 기록한다.
9. secret, 개인 경로, 생성물과 `source_file/` 원본을 push하지 않는다.
10. 릴리스는 branch가 아니라 검증된 commit SHA로 고정한다.
