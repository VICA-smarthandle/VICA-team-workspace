# VICA 개발 공식 참고자료 URL

최종 확인일: 2026-07-22

VICA 개발 중 사용하는 Nav2, ROS 2, NVIDIA Jetson 및 Isaac ROS 공식 문서를 기능별로 정리한 목록이다.

## 문서 선택 기준

- VICA Host 환경: Ubuntu 22.04, ROS 2 Humble
- NVIDIA 환경: Jetson Orin NX 16GB, JetPack 6.x / Jetson Linux R36
- GPU perception 환경: Isaac ROS Docker, RealSense D455, Visual SLAM, nvblox
- 현재 저장소에서 직접 URL이 확인된 문서는 ROS 2 Humble Ubuntu 설치 문서다.
- 나머지는 현재 코드와 설정에서 사용하는 기능에 대응하는 공식 문서를 추가로 정리한 것이다.

> **버전 주의:** Nav2의 `docs.nav2.org`는 최신 문서를 제공하므로 파라미터 이름과 기본값이 Humble과 다를 수 있다. 예제의 `Twist`/`TwistStamped`, plugin 이름, 파라미터 배열 형식 등을 VICA에 적용하기 전에 Humble 버전과 비교해야 한다.
>
> **Isaac ROS 주의:** NVIDIA 최신 Isaac ROS 문서는 현재 ROS 2 Jazzy 중심이다. VICA의 ROS 2 Humble + JetPack 6.x 구성에는 버전이 고정된 Isaac ROS `release-3.2` 문서를 우선 참고한다.

---

## 1. ROS 2 Humble 공식 문서

### 기본 설치와 개발 환경

| 문서 | 용도 | URL |
| --- | --- | --- |
| ROS 2 Humble 문서 홈 | Humble 문서 전체 목차 | <https://docs.ros.org/en/humble/index.html> |
| Ubuntu deb 패키지 설치 | Ubuntu 22.04에 ROS 2 Humble 설치 | <https://docs.ros.org/en/humble/Installation/Ubuntu-Install-Debs.html> |
| Workspace 만들기 | `colcon` workspace 생성·빌드·overlay 사용 | <https://docs.ros.org/en/humble/Tutorials/Beginner-Client-Libraries/Creating-A-Workspace/Creating-A-Workspace.html> |
| rosdep 사용법 | ROS 패키지 의존성 설치와 관리 | <https://docs.ros.org/en/humble/Tutorials/Intermediate/Rosdep.html> |

### 노드와 통신 인터페이스

| 문서 | 용도 | URL |
| --- | --- | --- |
| Topic·Service·Action 비교 | 연속 데이터, 요청/응답, 장시간 작업 인터페이스 선택 | <https://docs.ros.org/en/humble/Concepts/Basic/Interfaces-Topics-Services-Actions.html> |
| ROS 2 Topic 튜토리얼 | topic 목록, type, echo, hz 등 기본 진단 | <https://docs.ros.org/en/humble/Tutorials/Beginner-CLI-Tools/Understanding-ROS2-Topics/Understanding-ROS2-Topics.html> |
| QoS 설정 | 센서 데이터와 노드 간 QoS 호환성 확인 | <https://docs.ros.org/en/humble/Concepts/Intermediate/About-Quality-of-Service-Settings.html> |
| 사용자 정의 msg/srv | `vica_interfaces` 메시지 정의와 빌드 | <https://docs.ros.org/en/humble/Tutorials/Beginner-Client-Libraries/Custom-ROS2-Interfaces.html> |
| ROS 2 Action | Nav2 goal처럼 피드백과 취소가 필요한 작업 이해 | <https://docs.ros.org/en/humble/Tutorials/Beginner-CLI-Tools/Understanding-ROS2-Actions/Understanding-ROS2-Actions.html> |

### TF, URDF, launch와 데이터 기록

| 문서 | 용도 | URL |
| --- | --- | --- |
| tf2 소개 | `map -> odom -> base_footprint -> base_link` TF 이해 | <https://docs.ros.org/en/humble/Tutorials/Intermediate/Tf2/Introduction-To-Tf2.html> |
| tf2 정적 transform | 센서 고정 TF와 중복 publisher 점검 | <https://docs.ros.org/en/humble/Tutorials/Intermediate/Tf2/Writing-A-Tf2-Static-Broadcaster-Py.html> |
| URDF와 robot_state_publisher | Xacro/URDF 기반 로봇 TF 발행 | <https://docs.ros.org/en/humble/Tutorials/Intermediate/URDF/Using-URDF-with-Robot-State-Publisher-py.html> |
| ROS 2 Launch | Python launch, argument, include, remap 구성 | <https://docs.ros.org/en/humble/Tutorials/Intermediate/Launch/Launch-Main.html> |
| rosbag2 기록과 재생 | `/scan`, `/odom`, TF 등 재현 데이터 수집 | <https://docs.ros.org/en/humble/Tutorials/Beginner-CLI-Tools/Recording-And-Playing-Back-Data/Recording-And-Playing-Back-Data.html> |
| robot_localization Humble 소스 | EKF/UKF 구현, 설정 예제와 Humble 변경사항 확인 | <https://github.com/cra-ros-pkg/robot_localization/tree/humble-devel> |

---

## 2. Nav2 공식 문서

### 시작과 전체 구조

| 문서 | 용도 | URL |
| --- | --- | --- |
| Nav2 문서 홈 | Navigation2 공식 문서 시작점 | <https://docs.nav2.org/> |
| Getting Started | Nav2 설치와 기본 실행 흐름 | <https://docs.nav2.org/getting_started/index.html> |
| Navigation Concepts | planner, controller, BT, lifecycle, costmap 구조 | <https://docs.nav2.org/concepts/index.html> |
| Configuration Guide | Nav2 서버와 plugin 파라미터 전체 색인 | <https://docs.nav2.org/configuration/index.html> |
| Humble 소스 브랜치 | 최신 문서와 Humble 구현 차이를 확인할 공식 소스 | <https://github.com/ros-navigation/navigation2/tree/humble> |

### 로봇 입력과 상태 추정

| 문서 | 용도 | URL |
| --- | --- | --- |
| Transform 설정 | Nav2가 요구하는 `map`, `odom`, `base_link` TF 구성 | <https://docs.nav2.org/setup_guides/transformation/setup_transforms.html> |
| robot_localization으로 odometry smoothing | wheel odometry, IMU, VSLAM 융합과 `odom -> base_link` 발행 | <https://docs.nav2.org/setup_guides/odom/setup_robot_localization.html> |
| Robot Footprint 설정 | 원형/다각형 footprint와 collision 검사 범위 | <https://docs.nav2.org/setup_guides/footprint/setup_footprint.html> |
| Nav2 Tuning Guide | footprint, inflation, planner/controller 튜닝 원칙 | <https://docs.nav2.org/tuning/index.html> |

### 위치 추정, 지도와 costmap

| 문서 | 용도 | URL |
| --- | --- | --- |
| AMCL | 저장 지도 기반 2D localization 파라미터 | <https://docs.nav2.org/configuration/packages/configuring-amcl.html> |
| Map Server | map YAML 로딩과 map saver 설정 | <https://docs.nav2.org/configuration/packages/configuring-map-server.html> |
| Costmap 2D | global/local costmap와 layer 설정 | <https://docs.nav2.org/configuration/packages/configuring-costmaps.html> |
| Collision Monitor | costmap 외부의 stop/slowdown 안전 영역 구성 | <https://docs.nav2.org/configuration/packages/configuring-collision-monitor.html> |
| Collision Monitor 튜토리얼 | velocity smoother와 collision monitor의 명령 연결 순서 | <https://docs.nav2.org/tutorials/docs/using_collision_monitor.html> |

### 계획, 제어와 상태 관리

| 문서 | 용도 | URL |
| --- | --- | --- |
| Behavior-Tree Navigator | NavigateToPose와 BT navigator 설정 | <https://docs.nav2.org/configuration/packages/configuring-bt-navigator.html> |
| Planner Server | global planner plugin과 주기 설정 | <https://docs.nav2.org/configuration/packages/configuring-planner-server.html> |
| Controller Server | local controller, progress checker, goal checker 설정 | <https://docs.nav2.org/configuration/packages/configuring-controller-server.html> |
| DWB Controller | differential-drive 로봇의 DWB critic과 속도 파라미터 | <https://docs.nav2.org/configuration/packages/configuring-dwb-controller.html> |
| Smac Planner | Smac 2D/Hybrid/State Lattice planner 선택 | <https://docs.nav2.org/configuration/packages/configuring-smac-planner.html> |
| Velocity Smoother | 속도·가속도·감속·timeout 제한 | <https://docs.nav2.org/configuration/packages/configuring-velocity-smoother.html> |
| Lifecycle Manager | Nav2 lifecycle node 시작·종료와 bond 관리 | <https://docs.nav2.org/configuration/packages/configuring-lifecycle.html> |

---

## 3. NVIDIA Jetson 공식 문서

### JetPack과 Jetson Linux

| 문서 | 용도 | URL |
| --- | --- | --- |
| JetPack 6.2 | JetPack 6.2 구성요소와 지원 SDK 확인 | <https://developer.nvidia.com/embedded/jetpack-sdk-62> |
| Jetson Linux R36.4.4 Developer Guide | Jetson Orin NX의 OS, kernel, 장치 설정 기준 | <https://docs.nvidia.com/jetson/archives/r36.4.4/DeveloperGuide/index.html> |
| Jetson Linux R36.4.4 Release Notes | JetPack 6.2 대응 BSP 버전과 알려진 제한 확인 | <https://docs.nvidia.com/jetson/archives/r36.4.4/ReleaseNotes/Jetson_Linux_Release_Notes_r36.4.4.pdf> |
| SDK Manager | Jetson flash 및 SDK 설치 도구 | <https://docs.nvidia.com/sdk-manager/index.html> |
| Jetson Orin 전력·성능 관리 | `nvpmodel`, clock, thermal 및 전력 모드 확인 | <https://docs.nvidia.com/jetson/archives/r36.4.4/DeveloperGuide/SD/PlatformPowerAndPerformance/JetsonOrinNanoSeriesJetsonOrinNxSeriesAndJetsonAgxOrinSeries.html> |
| Jetson CAN | Orin CAN controller, SocketCAN 설정과 진단 | <https://docs.nvidia.com/jetson/archives/r36.4.4/DeveloperGuide/HR/ControllerAreaNetworkCan.html> |

### NVIDIA Container 환경

| 문서 | 용도 | URL |
| --- | --- | --- |
| NVIDIA Container Toolkit | GPU container runtime 개요 | <https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/> |
| Container Toolkit 설치 | Docker에서 NVIDIA runtime 설치·설정 | <https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html> |

---

## 4. Isaac ROS 공식 문서 — VICA 호환 버전 우선

다음 링크는 VICA의 ROS 2 Humble + JetPack 6.1/6.2 환경에 맞춘 `release-3.2` 문서다.

### 환경 구성과 RealSense

| 문서 | 용도 | URL |
| --- | --- | --- |
| Isaac ROS 3.2 Getting Started | Humble/JetPack 6.x 지원 조건과 전체 설정 순서 | <https://nvidia-isaac-ros.github.io/v/release-3.2/getting_started/index.html> |
| Developer Environment Setup | Isaac ROS Dev Docker 및 apt 환경 구성 | <https://nvidia-isaac-ros.github.io/v/release-3.2/getting_started/dev_env_setup.html> |
| Jetson SSD/Docker 저장공간 설정 | Isaac ROS workspace와 Docker 데이터를 SSD에 배치 | <https://nvidia-isaac-ros.github.io/v/release-3.2/getting_started/hardware_setup/compute/jetson_storage.html> |
| RealSense Setup | D455, librealsense, realsense-ros 호환 버전과 Docker 설정 | <https://nvidia-isaac-ros.github.io/v/release-3.2/getting_started/hardware_setup/sensors/realsense_setup.html> |

### Visual SLAM

| 문서 | 용도 | URL |
| --- | --- | --- |
| Isaac ROS Visual SLAM 패키지 | 설치, launch, topic, service, parameter 확인 | <https://nvidia-isaac-ros.github.io/v/release-3.2/repositories_and_packages/isaac_ros_visual_slam/isaac_ros_visual_slam/index.html> |
| cuVSLAM 개념 | Visual SLAM 좌표계, map 저장·불러오기와 localization 개념 | <https://nvidia-isaac-ros.github.io/v/release-3.2/concepts/visual_slam/cuvslam/index.html> |
| RealSense IMU VSLAM 튜토리얼 | RealSense stereo image와 IMU를 이용한 VSLAM 실행 | <https://nvidia-isaac-ros.github.io/v/release-3.2/concepts/visual_slam/cuvslam/tutorial_realsense.html> |
| NITROS | GPU zero-copy graph, type adaptation과 negotiation 이해 | <https://nvidia-isaac-ros.github.io/v/release-3.2/concepts/nitros/index.html> |

### nvblox와 Nav2 연동

| 문서 | 용도 | URL |
| --- | --- | --- |
| nvblox 개념 | depth 기반 3D reconstruction과 ESDF/occupancy 이해 | <https://nvidia-isaac-ros.github.io/v/release-3.2/concepts/scene_reconstruction/nvblox/index.html> |
| Isaac ROS nvblox 패키지 | RealSense 예제, topic, parameter와 Nav2 연동 확인 | <https://nvidia-isaac-ros.github.io/v/release-3.2/repositories_and_packages/isaac_ros_nvblox/isaac_ros_nvblox/index.html> |

### 최신 문서 확인용

최신 기능을 조사할 때만 아래 문서를 보고, 명령과 패키지를 Humble 환경에 그대로 복사하지 않는다.

| 문서 | 용도 | URL |
| --- | --- | --- |
| 최신 Isaac ROS 문서 | 현재 지원 버전과 최신 workflow 확인 | <https://nvidia-isaac-ros.github.io/> |
| Isaac ROS Release Notes | 릴리스별 ROS/JetPack 지원 변경 확인 | <https://nvidia-isaac-ros.github.io/releases/index.html> |

---

## 5. VICA 작업별 우선 참고 순서

| 작업 | 먼저 볼 문서 |
| --- | --- |
| TF 중복 또는 Nav2 transform timeout | ROS 2 tf2 → Nav2 Transform 설정 → VICA TF ownership |
| wheel odometry/EKF 수정 | Nav2 robot_localization → ROS 2 robot_localization → 현재 `ekf.yaml` |
| Nav2 parameter 수정 | Nav2 Configuration Guide → 대상 server/plugin → Humble 소스 브랜치 |
| `/cmd_vel` 안전 체인 수정 | Velocity Smoother → Collision Monitor → 현재 safety supervisor와 motor subscriber |
| RealSense D455 Docker 설정 | Isaac ROS 3.2 Getting Started → RealSense Setup |
| Visual SLAM TF 또는 odometry 수정 | Isaac ROS Visual SLAM → cuVSLAM 좌표계 → VICA TF ownership |
| nvblox costmap 연동 | nvblox 개념 → Isaac ROS nvblox 패키지 → Nav2 Costmap 2D |
| Jetson CAN 문제 | Jetson Linux R36.4.4 CAN → MDROBOT 매뉴얼 → 현재 CAN node |
| GPU 성능 또는 Docker 문제 | Jetson 전력·성능 → Container Toolkit → Isaac ROS Dev 환경 |

공식 문서의 예제는 참고 자료이며 VICA의 안전 정책보다 우선하지 않는다. 특히 Nav2 Collision Monitor만으로 하드웨어 E-stop이나 VICA safety supervisor를 대체하지 않는다.
