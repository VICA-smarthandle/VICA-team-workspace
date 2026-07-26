# VICA 로봇 실행 매뉴얼

Jetson Orin NX 실기에서 VICA AMR을 콜드 스타트로 기동하는 절차다. 모든 경로는
작업공간 루트(`VICA-smarthandle/`) 기준 상대경로 또는 `~/` 홈 기준으로 쓴다.

이 문서는 **운영 절차**만 다룬다. 계약과 권한 판정은
`guideline/vica_architecture.md`, 승인 기준은 `GOVERNANCE.md`가 정본이다.

## 1. 실행 전 안전 조건

⑤ motor 이후 단계는 실제 바퀴를 움직인다. 다음을 모두 확인한 뒤에만 진행한다.

- 바퀴를 띄웠거나 주행 공간을 통제했다.
- 물리 E-stop 버튼과 즉시 전원 차단 수단이 손에 닿는다.
- 주변에 사람이 없고 CAN 배선이 고정되어 있다.

다음은 아직 종단 검증이 끝나지 않았다. 정상 동작을 전제로 무인 운전하지 않는다.

- Nav2 `/cmd_vel_req` → Safety → motor → CAN 종단 동작 `[미검증]`
- 중앙 래치·reset 오케스트레이션의 실제 장치 종단 동작 `[미검증]`
- 관리자 인증을 거친 앱 단일 reset `[TARGET]`

## 2. 콜드 스타트 사전 점검

읽기 전용으로 현재 상태를 먼저 본다.

```bash
ip -br link show can1          # 링크 상태
ls -l /dev/rplidar             # LiDAR 심볼릭 링크
docker ps --format '{{.Names}}\t{{.Status}}'
ros2 node list                 # 이미 떠 있는 노드 확인
```

이미 노드가 떠 있으면 중복 기동하지 말고 필요한 것만 재시작한다. 특히 실행 중인
`can1`을 임의로 down/up하지 않는다.

## 3. 공통 터미널 준비

Host 터미널은 새로 열 때마다 다음을 실행한다.

```bash
source /opt/ros/humble/setup.bash
source ~/VICA-smarthandle/vica_ros2_ws/install/setup.bash
```

Docker(`vica_rs_container`) 안에서는 다음을 실행한다.

```bash
source /opt/ros/humble/setup.bash
source /workspaces/isaac_ros-dev/install/setup.bash
```

ROS 통신 환경은 모든 터미널에서 같아야 한다.

```bash
export ROS_DOMAIN_ID=7
export ROS_LOCALHOST_ONLY=0
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
```

개인 `~/.bashrc`에 이미 export되어 있으면 새 터미널에서 자동 적용된다. 개인
alias(`humble`, `can_set`, `vica_rs` 등)는 편의 수단일 뿐이므로 이 문서는 항상 원래
명령을 정본으로 적는다.

launch 인자에 경로를 넘길 때는 `$HOME`을 쓴다. `map:=~/경로` 형태는 셸이 틸데를
확장하지 않아 리터럴 `~`가 그대로 전달되고 지도 로딩이 실패한다.

## 4. 실행 순서 요약

| # | 단계 | 위치 | 바퀴 회전 |
| --- | --- | --- | --- |
| ① | CAN 링크 활성화 | Host | - |
| ② | URDF·TF·RViz | Host | - |
| ③ | LiDAR | Host | - |
| ④ | Safety | Host | - |
| ⑤ | motor adapter | Host | **가능** |
| ⑥ | D455 카메라 | Docker | - |
| ⑦ | IMU adapter | Host | - |
| ⑧ | nvblox | Docker | - |
| ⑨ | Nav2 + EKF + encoder | Host | **가능** |
| ⑩ | Mission Manager | Host | **가능** |
| ⑪ | Supervisor 앱 브리지 | Host | - |

각 단계는 별도 터미널에서 계속 실행 상태로 둔다.

### ① CAN 링크 활성화 (Host)

motor node와 `encoder_feedback`은 `can1`을 자동으로 UP하거나 bitrate를 바꾸지 않는다.
링크가 DOWN이면 ④의 물리 버튼 입력, ⑤ motor, ⑨의 encoder가 모두 실패한다.

```bash
sudo ip link set can1 down 2>/dev/null || true
sudo ip link set can1 type can bitrate 50000 berr-reporting on restart-ms 100
sudo ip link set can1 up
ip -details link show can1
```

bitrate 50 kbps는 MDROBOT 드라이버 설정값이다. 매뉴얼과 실측 근거 없이 바꾸지 않는다.

### ② URDF·TF·RViz (Host)

```bash
ros2 launch vica_description display.launch.py
```

`robot_state_publisher`가 `base_link → laser_frame`, `camera_link` TF를 발행한다. RViz
확인 용도만이 아니라 TF 트리의 필수 구성이므로 생략하지 않는다.

### ③ LiDAR (Host)

```bash
ros2 run rplidar_ros rplidar_node --ros-args \
  -p channel_type:=serial \
  -p serial_port:=/dev/rplidar \
  -p serial_baudrate:=115200 \
  -p frame_id:=laser_frame \
  -p angle_compensate:=true \
  -p inverted:=false \
  -p flip_x_axis:=true \
  -p scan_mode:=Express
```

`/scan`의 `frame_id`는 `laser_frame`이어야 ②의 TF와 정합한다.

### ④ Safety (Host)

motor보다 **먼저** 띄운다.

```bash
ros2 launch vica_safety safety_bringup.launch.py
```

세 노드가 함께 뜬다.

| 노드 | 역할 |
| --- | --- |
| `emergency_stop_node` | 물리 버튼(CAN F1)·앱·STT 입력 통합, 중앙 래치 소유 |
| `safety_supervisor_node` | `/cmd_vel_req` 검사 후 `/cmd_vel_safe` 승인 |
| `app_emergency_node` | 공개 reset 오케스트레이션(`/app_estop_reset`, `/safety_reset`) |

### ⑤ motor adapter (Host) — 바퀴가 돈다

```bash
ros2 launch mdrobot_can_control motor_bringup.launch.py
```

실행파일 이름은 `keyboard_knob`이지만 `/cmd_vel_safe`만 구독하는 CAN adapter다. E-stop
래치를 소유하지 않으며 `/cmd_vel_safe`가 일정 시간 끊기면 스스로 정지한다.

### ⑥ D455 카메라 (Docker)

```bash
docker exec -it vica_rs_container bash    # 컨테이너가 실행 중일 때
./run_d455.sh
```

컨테이너가 없으면 로컬 helper(`vica_rs`)로 새로 기동한다. 스크립트는 기존
`realsense2_camera`를 정리한 뒤 depth·color 640x480x30, gyro·accel, `align_depth`,
`unite_imu_method:=2`로 실행한다.

### ⑦ IMU adapter (Host)

```bash
ros2 run vica_sensor_adapters imu_base_link_adapter --ros-args \
  -p input_topic:=/camera/camera/imu \
  -p output_topic:=/imu/base_link \
  -p target_frame:=base_link
```

D455 IMU의 실제 센서 융합 품질은 `[미검증]` 상태다.

### ⑧ nvblox (Docker)

```bash
source /opt/ros/humble/setup.bash && source /workspaces/isaac_ros-dev/install/setup.bash
ros2 launch vica_nvblox_bringup vica_nvblox.launch.py
```

Nav2의 `local_costmap`이 `nvblox_layer`를 사용하므로 ⑨보다 먼저 띄운다.

### ⑨ Nav2 + EKF + encoder (Host)

```bash
ros2 launch vica_nav2 nav2_map_test.launch.py \
  map:=$HOME/VICA-smarthandle/vica_ros2_ws/maps/vica_map_0630.yaml
```

이 launch가 함께 수행하는 일은 다음과 같다.

- `wheel_ekf.launch.py` 포함(`start_localization` 기본 `true`) →
  `encoder_feedback`(`/wheel/odom`)과 `ekf_filter_node`(`/odom`, `odom → base_footprint`)
- `cmd_vel_smoothed → /cmd_vel_req` remap → 모든 주행 명령이 Safety를 거친다
- AMCL·map_server·planner·controller (`slam:=False`)

> **중복 금지**: `vica_localization/wheel_ekf.launch.py`를 따로 실행하지 않는다.
> `/odom`과 `odom → base_footprint` TF가 이중 발행되어 위치추정이 깨진다.

encoder를 이미 별도로 띄웠다면 `start_encoder:=false`로 넘긴다.

### ⑩ Mission Manager (Host)

```bash
ros2 launch vica_mission_manager mission_manager.launch.py \
  map_id:=vica_map_0630 \
  map_yaml:=$HOME/VICA-smarthandle/vica_ros2_ws/maps/vica_map_0630.yaml
```

`destination_storage_root`는 기본값이 `~/vica_data/destinations`라 생략할 수 있다.
`mission_manager`와 `emergency_estop_bridge`(긴급어 → 중앙 래치 트리거)가 함께 뜬다.
일반 운영 Goal의 단일 권한자는 Mission Manager다.

### ⑪ Supervisor 앱 브리지 (Host)

```bash
ros2 launch ~/VICA-smarthandle/VICA_Supervisor/ros2/supervisor_bringup.launch.py \
  map_yaml:=$HOME/VICA-smarthandle/vica_ros2_ws/maps/vica_map_0630.yaml
```

rosbridge WebSocket 9090, 지도 이미지 HTTP 8000, Destination Manager, Map List Node,
Status App Node를 함께 실행한다. `map_yaml`은 선택 항목이며 비우면 Nav2 map_server에서
자동 감지한다.

이 파일은 아직 앱 저장소에 있는 `[CURRENT]` 위치다. ROS 패키지로의 이동은 `[TARGET]`이다.

## 5. 기동 검증

```bash
ros2 topic hz /scan                              # LiDAR
ros2 topic hz /odom                              # EKF 출력, 발행자 1개인지 확인
ros2 topic hz /nvblox_node/static_map_slice      # 9Hz 부근이면 nvblox 정상
ros2 lifecycle get /local_costmap/local_costmap  # active [3]
ros2 node list | grep -E "safety|emergency"      # Safety 3노드
```

주행 경로 확인은 RViz의 2D Goal 또는 목적지 요청으로 한다.

```bash
ros2 topic echo /cmd_vel_req      # Nav2 최종 요청
ros2 topic echo /cmd_vel_safe     # Safety 승인 출력
```

목적지 주행 요청(CLI):

```bash
python3 ~/VICA-smarthandle/VICA_Supervisor/ros2/vica_goto_goal.py \
  vica_map_0630 "목적지명"
```

이 스크립트는 Nav2 action을 직접 치지 않고 Mission Manager의
`/vica/mission/request_destination` service를 호출한 뒤 `/vica_goal_event` terminal
이벤트를 기다린다.

## 6. E-stop과 reset

정지 경로:

```text
물리 버튼(CAN F1) · 앱 · STT 긴급어
→ emergency_stop_node (중앙 래치)
→ /emergency_stop
→ Mission Manager + Safety Supervisor
→ /cmd_vel_safe = 0
→ motor adapter
```

- 앱·STT가 보내는 `false`는 해당 입력의 해제일 뿐 래치 reset이 아니다.
- LLM과 STT에는 reset 권한이 없다.
- E-stop 해제 뒤 이전 Goal을 자동 재개하지 않는다.

유지보수용 reset(모든 위험 원인을 직접 해제 확인한 뒤에만):

```bash
ros2 service call /safety_reset std_srvs/srv/Trigger "{}"
```

`app_emergency_node`가 이 요청을 받아 Nav2 Goal 상태 확인, 취소, 래치 해제, 주행
재승인까지 오케스트레이션한다. 현재 `Trigger` 계약에는 호출자 인증 정보가 없어
`[GAP]`이다. 로그인한 관리자가 앱 확인 팝업으로 수행하는 단일 reset이 `[TARGET]`이다.

## 7. 종료 순서

기동의 역순으로 내린다.

1. ⑪ → ⑩ → ⑨ 순으로 각 터미널에서 `Ctrl+C`
2. ⑧ → ⑥ Docker 프로세스 종료
3. ⑤ motor, ④ Safety, ③ LiDAR, ② TF 종료
4. CAN 링크 정리

```bash
sudo ip link set can1 down
```

motor를 Safety보다 먼저 내려야 승인되지 않은 명령이 남지 않는다.

## 8. 자주 나는 문제

| 증상 | 원인 | 조치 |
| --- | --- | --- |
| motor·encoder가 CAN 오류로 죽음 | `can1` DOWN 또는 bitrate 불일치 | ① 재확인, `ip -details link show can1` |
| `local_costmap`이 `configure`에서 실패 | Host에 `nvblox_nav2` plugin 없음 | `install/nvblox_nav2/lib/libnvblox_nav2.so`가 실제 파일을 가리키는지 확인 후 재빌드 |
| 장애물이 없는데 전 영역이 lethal | nvblox esdf slice 높이가 바닥을 잡음 | slice 높이 파라미터 확인, ⑧ 재시작 |
| `/odom`이 튀거나 TF 경고 | `wheel_ekf`를 ⑨와 중복 실행 | 중복 프로세스 종료 후 ⑨만 유지 |
| 앱이 연결 timeout | Jetson DHCP IP 변경 vs 앱 저장 IP 불일치 | `ip -br addr` 확인 후 앱 접속 주소 갱신 |
| Goal이 거부됨 | 지도 불일치, 비 IDLE, E-stop 래치, Nav2 미준비 | Mission Manager 로그의 거부 사유 확인 |
| 2D Goal에 `/cmd_vel_req`가 없음 | Nav2 미기동 또는 remap 누락 | ⑨ 로그와 `ros2 topic info /cmd_vel_req` 확인 |

## 9. 하지 말 것

- `/cmd_vel_safe` 또는 CAN frame을 도구·앱·LLM에서 직접 발행하지 않는다.
- Mission Manager를 우회해 `/navigate_to_pose`에 직접 Goal을 보내지 않는다.
- 실행 중인 `can1`을 임의로 down/up하지 않는다.
- CAN frame ID, byte order, 좌우 모터 매핑, wheel geometry를 매뉴얼·실측 근거 없이
  바꾸지 않는다.
- 시험용 직접 발행 도구를 운영 경로와 섞지 않는다. 필요하면 `[TEST ONLY]`로 구분한다.
