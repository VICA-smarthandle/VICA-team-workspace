# VICA 로봇 실행 매뉴얼

Jetson Orin NX 실기에서 VICA AMR을 콜드 스타트로 기동하는 절차다. 주행(ROS 2), 관리자
앱 브리지, 음성·LLM까지 한 번에 다룬다. 모든 경로는 작업공간 루트(`VICA-smarthandle/`)
기준 상대경로 또는 `~/` 홈 기준으로 쓴다.

이 문서는 **운영 절차**만 다룬다. 계약과 권한 판정은
`guideline/vica_architecture.md`와 `vica-voice-llm/docs/ros2-interface.md`,
승인 기준은 `GOVERNANCE.md`가 정본이다.

## 1. 실행 전 안전 조건

⑤ motor 이후 단계는 실제 바퀴를 움직인다. 다음을 모두 확인한 뒤에만 진행한다.

- 바퀴를 띄웠거나 주행 공간을 통제했다.
- 물리 E-stop 버튼과 즉시 전원 차단 수단이 손에 닿는다.
- 주변에 사람이 없고 CAN 배선이 고정되어 있다.

다음은 아직 종단 검증이 끝나지 않았다. 정상 동작을 전제로 무인 운전하지 않는다.

- Nav2 `/cmd_vel_req` → Safety → motor → CAN 종단 동작 `[미검증]`
- 중앙 래치·reset 오케스트레이션의 실제 장치 종단 동작 `[미검증]`
- 마이크·스피커를 포함한 음성 → Mission → E-stop 종단 동작 `[미검증]`
- 관리자 인증을 거친 앱 단일 reset `[TARGET]`

음성 긴급어는 **보조 수단**이다. 인식 실패·지연·소음이 있을 수 있으므로 물리 E-stop
버튼을 1차 정지 수단으로 유지한다.

## 2. 콜드 스타트 사전 점검

읽기 전용으로 현재 상태를 먼저 본다.

```bash
ip -br link show can1          # 링크 상태
ls -l /dev/rplidar             # LiDAR 심볼릭 링크
docker ps --format '{{.Names}}\t{{.Status}}'
ros2 node list                 # 이미 떠 있는 노드 확인
```

음성·LLM까지 쓸 때는 다음도 확인한다.

```bash
ls ~/VICA-smarthandle/vica-voice-llm/.venv/bin/python   # 가상환경
ls ~/VICA-smarthandle/vica-voice-llm/.env               # LLM 키 설정 (내용은 열지 않는다)
arecord -l                                              # 마이크 인식
aplay -l                                                # 스피커 인식
```

`.venv` 또는 `.env`가 없으면 §4를 먼저 수행한다. 이미 노드가 떠 있으면 중복 기동하지
말고 필요한 것만 재시작한다. 특히 실행 중인 `can1`을 임의로 down/up하지 않는다.

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

### 터미널 자동 배치 (Terminator)

터미널을 하나씩 열고 source하는 대신, 15칸을 한 번에 배치할 수 있다.

```bash
python3 ~/VICA-smarthandle/scripts/vica_terminator_layout.py   # 레이아웃 생성(최초 1회)
terminator -l vica                                             # 실행
```

생성기는 터미널별 rc 파일(`~/.config/vica-terminator/`)과 Terminator 레이아웃을 만든다.
기존 `~/.config/terminator/config`는 타임스탬프를 붙여 백업한다.

모든 칸이 `~/.bashrc` → ROS 2 → `vica_ros2_ws` source와 통신 환경변수 설정까지 마친
상태로 열린다. 음성 두 칸만 `vica-voice-llm`으로 이동한다.

| 열 | 터미널 |
| --- | --- |
| 1열 센서·안전 | display · lidar · safety · imu **(자동 실행)** / motor |
| 2열 Docker·주행 | d455 · nvblox · nav2 · mission · app |
| 3열 음성·조작 | llm+tts · stt · goto · reset · teleop |

- **자동 실행**은 바퀴를 움직이지 않는 4칸(display·lidar·safety·imu)뿐이다.
- 나머지 11칸은 명령을 `history`에 넣어두고 대기한다. **위 화살표 한 번 + Enter**로
  실행하며, 각 칸 상단에 단계 번호와 주의사항이 표시된다.
- 순서 의존성이 있는 단계(Docker 카메라 → nvblox → Nav2)와 바퀴가 도는 단계는 자동으로
  두지 않는다. §5의 순서를 사람이 통제한다.
- `teleop` 칸은 `[TEST ONLY]`다. `/cmd_vel`을 `/cmd_vel_req`로 remap해 Safety를 거치며,
  Nav2 주행 중에는 명령이 충돌하므로 쓰지 않는다.

배치·자동 여부를 바꾸려면 스크립트의 `COLUMNS`만 고치고 다시 실행한다.

## 4. 음성·LLM 최초 1회 준비

이 절은 장비를 새로 세팅하거나 `.venv`를 다시 만들 때만 수행한다. 배경 설명은
`vica-voice-llm/docs/jetson-setup.md`를 함께 본다.

현재 `~/VICA-smarthandle/vica-voice-llm/.venv`는 다음 조합으로 구성되어 모듈 import까지
확인된 상태다(2026-07-26).

| 항목 | 값 |
| --- | --- |
| Python | 3.10.12 |
| STT | `faster-whisper 1.2.1` + `ctranslate2 4.4.0` (Jetson CUDA 빌드) |
| TTS | `supertonic 1.3.1` + `onnxruntime-gpu 1.24.0` (TensorRT·CUDA provider) |
| LLM | `langchain 1.3.14`, `langchain-ollama 1.1.0` |

### 4.1 시스템 패키지

```bash
sudo apt update
sudo apt install -y python3-venv python3-dev portaudio19-dev libportaudio2 espeak-ng ffmpeg
```

### 4.2 가상환경

```bash
cd ~/VICA-smarthandle/vica-voice-llm
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
```

> `requirements.txt`는 PC(Python 3.12) 기준으로 버전이 고정되어 있어 Jetson(ARM64,
> Python 3.10)에서는 그대로 설치되지 않는다. `networkx==3.6.1`처럼 Python 3.11 이상을
> 요구하는 핀이 있으면 resolver가 **아무것도 설치하지 않고 실패**한다. 해당 줄의
> `==버전`을 지워 핀을 완화하거나 핵심 패키지만 먼저 설치한다.

`rclpy`와 `vica_interfaces`는 venv에 설치하지 않는다. ROS 2와 `vica_ros2_ws`를 source한
터미널에서 `PYTHONPATH`로 주입되므로, **venv 파이썬은 반드시 source를 마친 터미널에서
실행**한다. venv는 시스템과 같은 Python 3.10으로 만든다.

### 4.3 GPU STT (ctranslate2)

pip의 ARM64 `ctranslate2` 휠은 CPU 전용이라 STT가 수 배 느려진다. Jetson CUDA 빌드는
`.venv/ct2lib/libctranslate2.so.4`에 두고, `src/stt.py`의 `_preload_cuda_ctranslate2()`가
`RTLD_GLOBAL`로 먼저 적재해 `LD_LIBRARY_PATH` 설정 없이 링크되게 한다.

이 코어 라이브러리는 pip로 재현되지 않는다. `.venv`를 다시 만들면 기존 `ct2lib`
디렉터리와 `site-packages/ctranslate2`를 함께 옮겨야 하며, 없으면 CUDA 재빌드가 필요하다
(`docs/jetson-setup.md`의 CTranslate2 빌드 절차, 약 10분).

검증:

```bash
.venv/bin/python -c "import ctranslate2; print(ctranslate2.get_cuda_device_count())"
```

`1` 이상이면 GPU STT 준비 완료다. `0`이거나 `libctranslate2.so.4` 오류가 나면 CPU로
동작하므로 발화 인식이 크게 느려진다.

### 4.4 GPU TTS (onnxruntime)

```bash
.venv/bin/pip install onnxruntime-gpu==1.24.0 \
  --index-url https://pypi.jetson-ai-lab.io/jp6/cu126
```

CPU용 `onnxruntime`이 이미 설치돼 있으면 **GPU 설치 전에 먼저 제거**한다. 두 패키지는
같은 `onnxruntime` 디렉터리를 공유해서, GPU를 설치한 뒤에 CPU를 제거하면 GPU 파일까지
지워진다. 그렇게 깨졌을 때는 `--force-reinstall`로 복구한다.

검증:

```bash
.venv/bin/python -c "import onnxruntime as ort; print(ort.get_available_providers())"
```

`TensorrtExecutionProvider`와 `CUDAExecutionProvider`가 보이면 준비 완료다. 실행 중
`GPU device discovery failed ... /sys/class/drm/card1` 경고는 Jetson에서 정상이며 무시한다.

### 4.5 `.env` 설정

`.env.example`을 복사해 `.env`를 만들고 값만 채운다. `.env`는 Git에 올리지 않는다.

```bash
cd ~/VICA-smarthandle/vica-voice-llm
cp .env.example .env
chmod 600 .env
```

기본은 Ollama Cloud다. `OLLAMA_HOST`, `VICA_LLM_MODEL`, `OLLAMA_API_KEY` 세 줄을 채우면
되고, 오프라인이 필요하면 로컬 Ollama 주소로 바꾼다. STT 설정은 다음 값으로 고정한다.

```text
VICA_STT_MODEL=medium
VICA_STT_DEVICE=cuda
VICA_STT_COMPUTE=float16
```

`small`은 `식당`→`직당` 류의 오인식이 있어 `medium`을 채택했다. 임의로 낮추지 않는다.
`medium` 가중치는 최초 실행 시 자동으로 내려받는다(약 1.5 GB, 캐시는
`~/.cache/huggingface/hub`). 실측 기준 최초 1회 88초, 캐시 이후 로드 3초다. 네트워크가
없는 현장에서는 미리 한 번 로드해 캐시를 채워 둔다.

### 4.6 공용 메시지 빌드

음성 노드가 쓰는 `VicaIntent`, `RobotState`, `EmergencyEvent`의 정본은
`vica_ros2_ws/src/vica_interfaces/`다. 저장소 내부 사본은 두지 않는다.

```bash
cd ~/VICA-smarthandle/vica_ros2_ws
colcon build --packages-select vica_interfaces
source install/setup.bash
```

### 4.7 준비 상태 점검

노드를 띄우기 전에 import만으로 환경을 확인한다. 하드웨어를 건드리지 않는다.

```bash
source /opt/ros/humble/setup.bash
source ~/VICA-smarthandle/vica_ros2_ws/install/setup.bash
cd ~/VICA-smarthandle/vica-voice-llm
.venv/bin/python -c "
import rclpy
from vica_interfaces.msg import VicaIntent, RobotState, EmergencyEvent
import src.ros_node, src.ros_tts_node, src.ros_emergency_node, src.ros_stt_node
print('OK')
"
```

`OK`가 나오면 ⑫⑬을 실행할 수 있다. 실패 메시지는 §10 표에서 원인을 찾는다.

### 4.8 로봇 없이 먼저 확인

ROS와 로봇을 붙이기 전에 음성 파이프라인만 단독 검증하는 편이 안전하다.

```bash
cd ~/VICA-smarthandle/vica-voice-llm
.venv/bin/python -m src.main
```

## 5. 실행 순서

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
| ⑫ | 음성·LLM (LLM·TTS·긴급어 감시) | Host | **가능**(음성 요청 시) |
| ⑬ | STT push-to-talk | Host | **가능**(음성 요청 시) |

각 단계는 별도 터미널에서 계속 실행 상태로 둔다. ⑫⑬은 음성 없이 앱·CLI만 쓸 때는
생략할 수 있다.

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
| `emergency_stop_node` | 물리 버튼(CAN F1)·앱·음성 입력 통합, 중앙 래치 소유 |
| `safety_supervisor_node` | `/cmd_vel_req` 검사 후 `/cmd_vel_safe` 승인 |
| `app_emergency_node` | 공개 reset 오케스트레이션(`/app_estop_reset`, `/safety_reset`) |

음성 긴급어의 최종 도착지도 이 `emergency_stop_node`의 `/voice_emergency_stop`이다.

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

음성을 함께 쓸 때 Mission Manager는 다음 세 가지를 담당한다.

- `/vica/intent` 게이트 심사 후 Nav2 Goal 생성
- `/vica/robot_state` 1 Hz 발행(층·건물·이동 상태)
- 확정 안내 문구를 `/vica/tts_request`로 발행

⑫와 `map_id`가 다르면 서로 다른 목적지 catalog를 보게 되므로 반드시 같은 값을 쓴다.

### ⑪ Supervisor 앱 브리지 (Host)

```bash
ros2 launch ~/VICA-smarthandle/VICA_Supervisor/ros2/supervisor_bringup.launch.py \
  map_yaml:=$HOME/VICA-smarthandle/vica_ros2_ws/maps/vica_map_0630.yaml
```

rosbridge WebSocket 9090, 지도 이미지 HTTP 8000, Destination Manager, Map List Node,
Status App Node를 함께 실행한다. `map_yaml`은 선택 항목이며 비우면 Nav2 map_server에서
자동 감지한다.

이 파일은 아직 앱 저장소에 있는 `[CURRENT]` 위치다. ROS 패키지로의 이동은 `[TARGET]`이다.

### ⑫ 음성·LLM (Host)

ROS 2와 `vica_ros2_ws`를 source한 터미널에서 실행한다. launch가 venv 파이썬으로 세
프로세스를 띄우므로 `.venv`를 activate할 필요는 없다.

```bash
source /opt/ros/humble/setup.bash
source ~/VICA-smarthandle/vica_ros2_ws/install/setup.bash
cd ~/VICA-smarthandle/vica-voice-llm
ros2 launch launch/vica_voice.launch.py map_id:=vica_map_0630
```

| 프로세스 | 역할 |
| --- | --- |
| `src.ros_node` | 하드 긴급어 선검사 → LLM 해석 → 목적지 검증 → `/vica/intent` |
| `src.ros_tts_node` | `/vica/tts_request` 우선순위 큐 재생, `/vica/tts_state` 발행 |
| `src.ros_emergency_node` | 상시 긴급어 감시 → `/vica/emergency` |

목적지 catalog는 `~/vica_data/destinations/<map_id>/destinations.yaml`을 읽으며
`authorization == public`인 항목만 LLM에 제공한다. 파일 변경은 다음 발화 전에 자동으로
다시 읽는다. 목적지 추가·삭제는 앱(`vica_destination_manager`)이 담당하고 음성
저장소는 목적지를 수정하지 않는다.

> **시작 로그를 반드시 확인한다.** `목적지 catalog가 없어 빈 목록을 사용합니다`
> WARN이 보이면 경로가 틀린 것이다. 이 상태에서도 노드는 정상적으로 뜨고 LLM이 대답까지
> 하지만, `matched_destination_id`가 비어 Mission gate에서 전부 차단되고 존재하지 않는
> 장소를 지어낸다. `map_id` 절단(`vica_map_06`)이 실제로 이 증상을 만든 적이 있다.

`ros_emergency_node`는 로봇이 말하는 동안 자가 오탐을 막기 위해 감시를 잠시 멈추고,
TTS 종료 신호가 없어도 제한 시간 뒤 자동 재개한다. 이 억제 구간이 긴급어 미검출로
이어질 수 있다 — `vica-voice-llm/docs/voice-improvement-backlog.md` 5번 참고.

### ⑬ STT push-to-talk (Host)

터미널 입력이 필요해 launch에 포함하지 않는다. 별도 터미널에서 실행한다.

```bash
source /opt/ros/humble/setup.bash
source ~/VICA-smarthandle/vica_ros2_ws/install/setup.bash
cd ~/VICA-smarthandle/vica-voice-llm
.venv/bin/python -m src.ros_stt_node
```

엔터 → 말하기 → 엔터로 한 번 녹음하고, 인식 문장을 `/vica/user_text`로 발행한다.
인식 결과가 비면 재발화 안내를 TTS로 내보낸다. 종료는 `Ctrl+C`다.

⑬의 push-to-talk와 무관하게 ⑫의 긴급어 감시는 상시 동작한다.

## 6. 음성 → 주행 종단 흐름

```text
마이크 ─ 일반 발화 ─→ ros_stt_node ─ /vica/user_text ─→ ros_node
                                                          │ LLM 해석 + 목적지 ID 검증
                                                          ├─ /vica/tts_request → ros_tts_node
                                                          └─ /vica/intent → Mission Manager
                                                                              │ gate 심사
                                                                              └→ Nav2
                                                                                 → /cmd_vel_req
                                                                                 → Safety Supervisor
                                                                                 → /cmd_vel_safe
                                                                                 → motor → CAN

마이크 ─ 긴급어 ──→ ros_emergency_node ─ /vica/emergency ─→ emergency_estop_bridge
                                                             → /voice_emergency_stop 펄스
                                                             → emergency_stop_node 중앙 래치
                                                             → /cmd_vel_safe = 0
```

Mission Manager의 gate는 첫 번째 실패 사유를 로그로 남긴다. 통과 조건은 다음과 같다.

| 순서 | 조건 | 실패 사유 |
| --- | --- | --- |
| 1 | `intent == navigate` | `NOT_NAVIGATE` |
| 2 | `matched_destination_id != ""` | `NO_MATCHED_ID` |
| 3 | `need_confirm == false` | `NEED_CONFIRM` |
| 4 | `safety_flag == normal` | `SAFETY_FLAG` |
| 5 | E-stop 비활성 | `ESTOP_ACTIVE` |
| 6 | 등록된 목적지 | `UNKNOWN_DESTINATION` |
| 7 | `authorization == public` | `PRIVATE_DESTINATION` |
| 8 | `is_approachable == true` | `NOT_APPROACHABLE` |
| 9 | pose가 지도 범위 안 | `POSE_INVALID` |
| 10 | Nav2 준비됨 | Nav2 미준비 |

`destination_candidate`는 LLM이 제안하지만 `matched_destination_id`는 코드가 등록
목적지와 대조해 채운다. LLM이 만든 이름만으로는 절대 주행하지 않는다.

## 7. 기동 검증

주행 스택:

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

음성·LLM:

```bash
ros2 topic hz /vica/robot_state   # Mission Manager 1Hz
ros2 topic echo /vica/user_text   # ⑬에서 말한 문장
ros2 topic echo /vica/intent      # LLM 의도 후보
ros2 topic echo /vica/tts_request # "<priority>:<text>" 형식
ros2 topic echo /vica/emergency   # 긴급어 이벤트
```

목적지 주행 요청(CLI, 음성 없이 확인할 때):

```bash
python3 ~/VICA-smarthandle/VICA_Supervisor/ros2/vica_goto_goal.py \
  vica_map_0630 "목적지명"
```

이 스크립트는 Nav2 action을 직접 치지 않고 Mission Manager의
`/vica/mission/request_destination` service를 호출한 뒤 `/vica_goal_event` terminal
이벤트를 기다린다.

음성 종단 시험 순서와 오탐·mute 파라미터는 `vica-voice-llm/docs/voice-field-test.md`를
따른다. 바퀴를 띄운 상태에서 먼저 수행한다.

## 8. E-stop과 reset

정지 경로:

```text
물리 버튼(CAN F1) · 앱 · 음성 긴급어
→ emergency_stop_node (중앙 래치)
→ /emergency_stop
→ Mission Manager + Safety Supervisor
→ /cmd_vel_safe = 0
→ motor adapter
```

하드 긴급어는 `멈춰`, `정지`, `스탑`, `스톱`, `안돼`, `위험해` 6개다. `잠깐`, `천천히`,
`느리게`는 E-stop 키워드가 아니라 일반 발화로 처리한다.

- 앱·음성이 보내는 `false`는 해당 입력의 해제일 뿐 래치 reset이 아니다.
- LLM과 STT에는 reset 권한이 없다.
- E-stop 해제 뒤 이전 Goal을 자동 재개하지 않는다.
- 음성 긴급어는 LLM을 거치지 않는다. LLM이 죽어 있어도 긴급 경로는 동작해야 한다.

유지보수용 reset(모든 위험 원인을 직접 해제 확인한 뒤에만):

```bash
ros2 service call /safety_reset std_srvs/srv/Trigger "{}"
```

`app_emergency_node`가 이 요청을 받아 Nav2 Goal 상태 확인, 취소, 래치 해제, 주행
재승인까지 오케스트레이션한다. 현재 `Trigger` 계약에는 호출자 인증 정보가 없어
`[GAP]`이다. 로그인한 관리자가 앱 확인 팝업으로 수행하는 단일 reset이 `[TARGET]`이다.

## 9. 종료 순서

기동의 역순으로 내린다.

1. ⑬ → ⑫ 음성 노드 `Ctrl+C`
2. ⑪ → ⑩ → ⑨ 순으로 각 터미널에서 `Ctrl+C`
3. ⑧ → ⑥ Docker 프로세스 종료
4. ⑤ motor, ④ Safety, ③ LiDAR, ② TF 종료
5. CAN 링크 정리

```bash
sudo ip link set can1 down
```

motor를 Safety보다 먼저 내려야 승인되지 않은 명령이 남지 않는다. 음성 노드를 가장 먼저
내리는 이유는 마이크 입력이 남은 상태에서 Mission·Safety가 사라지는 상황을 막기 위해서다.

## 10. 자주 나는 문제

주행 스택:

| 증상 | 원인 | 조치 |
| --- | --- | --- |
| motor·encoder가 CAN 오류로 죽음 | `can1` DOWN 또는 bitrate 불일치 | ① 재확인, `ip -details link show can1` |
| `local_costmap`이 `configure`에서 실패 | Host에 `nvblox_nav2` plugin 없음 | `install/nvblox_nav2/lib/libnvblox_nav2.so`가 실제 파일을 가리키는지 확인 후 재빌드 |
| 장애물이 없는데 전 영역이 lethal | nvblox esdf slice 높이가 바닥을 잡음 | slice 높이 파라미터 확인, ⑧ 재시작 |
| `/odom`이 튀거나 TF 경고 | `wheel_ekf`를 ⑨와 중복 실행 | 중복 프로세스 종료 후 ⑨만 유지 |
| 앱이 연결 timeout | Jetson DHCP IP 변경 vs 앱 저장 IP 불일치 | `ip -br addr` 확인 후 앱 접속 주소 갱신 |
| 2D Goal에 `/cmd_vel_req`가 없음 | Nav2 미기동 또는 remap 누락 | ⑨ 로그와 `ros2 topic info /cmd_vel_req` 확인 |

음성·LLM:

| 증상 | 원인 | 조치 |
| --- | --- | --- |
| `ModuleNotFoundError: rclpy` | ROS 2를 source하지 않은 터미널에서 venv 파이썬 실행 | §3의 source 2줄을 먼저 실행 |
| `vica_interfaces` import 실패 | `vica_ros2_ws/install/setup.bash` 미source 또는 미빌드 | §4.6 재수행 |
| `pip install -r requirements.txt`가 통째로 실패 | PC 기준 버전 핀이 Python 3.10과 충돌 | §4.2의 핀 완화 |
| `libctranslate2.so.4: cannot open shared object file` | `.venv/ct2lib` 누락 또는 venv 재생성 | §4.3으로 라이브러리 복원 |
| `onnxruntime has no attribute __version__` | CPU·GPU 패키지가 같은 디렉터리에서 충돌 | §4.4의 `--force-reinstall` |
| LLM 응답이 없거나 인증 오류 | `.env`의 `OLLAMA_API_KEY`·`OLLAMA_HOST` 누락 | §4.3 확인, 오프라인이면 로컬 Ollama로 전환 |
| STT가 매우 느림 | CPU 폴백 | `.env`의 `VICA_STT_DEVICE=cuda`, `VICA_STT_COMPUTE=float16` 확인 |
| 모든 발화가 `matched=None`, 없는 장소를 지어냄 | `map_id` 오타·절단으로 catalog를 못 읽음 | ⑫ 시작 로그의 catalog WARN 확인. `vica_map_0630`을 끝까지 입력 |
| 목적지를 못 찾음 | ⑩과 ⑫의 `map_id` 불일치, 또는 목적지가 `public`이 아님 | 두 launch의 `map_id`를 맞추고 앱에서 권한 확인 |
| `/vica/intent`는 오는데 주행하지 않음 | gate 실패 | Mission Manager 로그의 실패 사유(§6 표) 확인 |
| 로봇 음성에 긴급어 감시가 반응 | 자가 오탐 | `/vica/tts_state` 발행 확인, `emergency_monitor.py`의 `max_mute_sec` 조정 |
| 요청은 오는데 소리가 없음 | 오디오 출력 장치 문제 | TTS 노드 로그의 `재생 실패`와 `aplay -l` 확인 |

## 11. 하지 말 것

- `/cmd_vel_safe` 또는 CAN frame을 도구·앱·LLM에서 직접 발행하지 않는다.
- Mission Manager를 우회해 `/navigate_to_pose`에 직접 Goal을 보내지 않는다.
- LLM에 이동·정지·속도 tool을 만들지 않는다(`move_robot`, `publish_cmd_vel`,
  `send_nav2_goal`, `stop_motor` 등).
- 긴급어 처리를 LLM 뒤로 옮기지 않는다. 하드 긴급어는 항상 LLM 이전에 판정한다.
- 음성·STT에 E-stop reset 권한을 주지 않는다.
- 실행 중인 `can1`을 임의로 down/up하지 않는다.
- CAN frame ID, byte order, 좌우 모터 매핑, wheel geometry를 매뉴얼·실측 근거 없이
  바꾸지 않는다.
- `.env`와 API 키를 commit하거나 로그·문서에 남기지 않는다.
- 시험용 직접 발행 도구를 운영 경로와 섞지 않는다. 필요하면 `[TEST ONLY]`로 구분한다.
