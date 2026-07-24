# VICA 통합 동작 시나리오

작성 기준일: 2026-07-22
기준 작업공간: 이 문서가 포함된 작업공간 루트
기준 저장소: `vica_ros2_ws`, `vica-voice-llm`, `VICA_Supervisor`

## 1. 문서 목적

이 문서는 현재 작업공간에서 확인되는 VICA의 실제 구현과 앞으로 구현할 Smart Handle 안내 기능을 하나의 운용 시나리오로 정리한다.

상태 표기는 다음 의미로 사용한다.

| 상태 | 의미 |
| --- | --- |
| 현재 구현 | 관련 코드와 인터페이스가 현재 작업공간에 존재함 |
| 통합 필요 | 구성요소는 있으나 토픽, launch 또는 실제 장비 연결이 완성되지 않음 |
| 구현 목표 | 현재 코드에는 없으며 이 문서가 목표로 정의함 |
| 유지 요구사항 | 사용자가 유지하도록 확정한 앱 기능. 임의 삭제·변경 금지 |

## 2. 서비스 범위

VICA의 기본 서비스는 다음과 같다.

1. 사용자가 음성으로 목적지를 요청한다.
2. STT와 LLM이 발화를 해석한다.
3. 코드가 등록 목적지와 좌표를 검증한다.
4. 사용자가 목적지를 확인한다.
5. Mission Manager가 주행 허용 조건을 검사한다.
6. Nav2가 목적지까지 경로를 계획하고 주행한다.
7. 구현 목표인 Turn Guide가 경로의 다음 회전을 미리 판단한다.
8. 같은 회전 cue로 Smart Handle 서보와 좌·우 LED를 동작시킨다.
9. 목적지 도착 또는 긴급정지 시 안내 출력을 안전 상태로 복귀시킨다.

다음 기능은 현재 서비스 범위에서 제외한다.

- 예약
- 목적지 도착 후 사용자 대기
- 배터리 잔량에 따른 서비스 정책
- 신규 사용자 등록, 비밀번호 찾기, 복잡한 역할·권한 관리
- 사용자별 개인정보 및 이용 이력 관리
- 사람 자동 탐지·접근
- 일반 대화용 상시 wake word
- 앱 조이스틱·방향키 원격 수동 주행(teleop)


앱의 원격 목적지 요청은 제외하지 않는다. 로봇이 사용자를 안내 중이 아닐 때(IDLE)에 한해
운영자가 앱에서 목적지를 선택하면 Mission Manager를 거쳐 주행하는 방식으로 구현하며,
상세 조건은 10.5절(구현 목표)을 따른다.

## 3. 유지해야 하는 앱 기능

다음은 사용자가 유지하도록 확정한 기능이다.

- 로그인 화면과 기존 사용자 로그인 흐름
- 로봇 현재 위치
- 주행 중 상태
- 멈춤 또는 대기 상태
- 비상정지 상태
- 오류 상태와 오류 사유
- 기본 운영 로그

이 기능은 후속 구현에서 임의로 제거하거나 다른 기능으로 대체하지 않는다.

> 현재 확인한 `VICA_Supervisor` 소스는 앱 시작 시 `SupervisorShell`로 바로 진입하며 별도의 로그인 화면·인증 route는 발견되지 않았다. 로그인은 확정된 요구사항이지만 현재 소스에 구현이 없으므로 “구현 목표”로 분류한다. 구현 후에는 임의로 제거하지 않는다. 최신 로그인 소스가 별도 위치에 있다면 통합한다.

## 4. 전체 서비스 흐름

```text
사용자 발화
→ STT: /vica/user_text
→ 긴급어 선검사
→ LLM 의도 해석
→ VicaIntent: /vica/intent
→ 코드 기반 목적지 매칭
→ 사용자 확인
→ Mission Manager gate
→ NavigateToPose
→ Nav2 기본 BT
├─ 경로/속도 생성 → 안전 계층 → 모터
└─ Nav2 Path → Turn Guide → Smart Handle 서보 + 좌·우 LED  [구현 목표]
```

LLM은 목적지 후보와 대화 응답만 제안한다. LLM, STT, TTS 및 앱은 `/cmd_vel`, `/cmd_vel_safe`, Nav2 goal 또는 CAN frame을 직접 생성하지 않는다.

## 5. 안내 시작 전 준비 조건

### 5.1 현재 필수 조건

1. 사용할 지도 YAML과 이미지가 준비되어 있다.
2. Nav2 map server와 AMCL이 활성화되어 있다.
3. `map → odom → base_footprint → base_link` TF가 유일한 authority로 연결된다.
4. `/scan`과 localization 결과가 최신 상태다.
5. 안내할 목적지가 등록되어 있다.
6. 목적지 pose가 `map` frame이며 `(0, 0)` placeholder가 아니다.
7. 목적지 좌표가 지도 경계 안에 있고 `calibrated=false`가 아니다.
8. Nav2 `NavigateToPose` action server가 준비되어 있다.
9. 중앙 래치된 `/emergency_stop`이 비활성이고 Safety가 재출발 허용 상태다.
10. STT, LLM, TTS, 긴급어 감시와 Mission Manager를 실행할 수 있다.

### 5.2 현재 통합 blocker

다음 항목이 해결되기 전에는 실제 바퀴 주행을 안전 통합 완료로 간주하지 않는다.

| blocker | 현재 상태 |
| --- | --- |
| 안전 명령 연결 | motor는 `/cmd_vel_safe`를 구독하도록 변경됐으나 build/runtime 검증이 필요함 |
| Nav2 안전 입력 | velocity smoother 최종 출력의 `/cmd_vel_req` remap은 구현, 실제 Goal·motor 종단 `[미검증]` |
| localization 의존성 | `vica_localization` 연결과 로컬 EKF 기동은 검증했으나 시스템에 `robot_localization`, `python3-can` 설치가 필요함 |
| wheel·IMU 실기 융합 | `/wheel/odom + /imu/base_link → EKF → /odom` 계약은 연결됐으나 C5와 D455 동시 실기 검증은 미완료 |
| Cartographer odometry | `odom_topic=/odom` 전달과 remap은 적용됐으나 Cartographer를 포함한 실기 runtime 검증이 필요함 |
| E-stop 중앙 래치 | `vica_safety` 코드·launch·단위 테스트 구현, 실제 F1·CAN 종단 `[미검증]` |
| reset 통합 | 앱·유지보수 공개 서비스와 Nav2 취소·2단계 내부 reset 구현, runtime `[미검증]` |
| TTS 통합 | Mission Manager는 `/vica/tts_request`를 발행하지만 TTS는 `/vica/intent`만 구독함 |
| 운영 voice launch | 개발용 RobotState·state-machine stub 두 개가 아직 포함됨 |

### 5.3 Smart Handle 구현 뒤 추가할 조건

1. `turn_guide_node`와 guidance driver가 실행 중이다.
2. 서보·LED·햅틱 장치 fault가 없다.
3. 서보는 중립 위치이고 LED는 기본 상태(직진 파란색 점멸 대기)다.
4. 실제 로봇 기준 서보와 LED의 좌·우 방향을 bench test로 확인했다.

서보·LED·햅틱은 핸들의 아두이노 나노가 제어하며, 생존신호(heartbeat) 프로토콜은
사용하지 않는다.

## 6. 정상 사용자 안내 시나리오

### 6.1 서비스 요청

상태: 음성 입력 현재 구현 / Smart Handle 준비 확인 구현 목표

1. VICA는 goal이 없는 정지 상태에서 요청을 기다린다.
2. 사용자는 로봇 가까이에서 push-to-talk 음성 입력을 시작한다.
3. VICA는 목적지를 말하도록 안내한다.
4. Smart Handle 통합 뒤에는 서보·LED·햅틱 장치 상태를 확인한다.
5. 시각장애인 안내 모드에서 필수 Handle 상태가 정상이 아니면 출발하지 않는다.

권장 안내:

> “안녕하세요. VICA입니다. 손잡이를 잡고 안내받고 싶은 장소를 말씀해 주세요.”

### 6.2 목적지 요청과 해석

상태: 현재 구현

1. `ros_stt_node`가 음성을 텍스트로 변환해 `/vica/user_text`로 발행한다.
2. `ros_node`가 텍스트와 `/vica/robot_state`를 이용해 의도를 해석한다.
3. LLM은 `destination_candidate`를 제안한다.
4. `destination_matcher.py`가 등록 목적지와 비교해 `matched_destination_id`를 결정한다.
5. 결과는 `VicaIntent`로 `/vica/intent`에 발행된다.

예시:

> 사용자: “407호로 안내해 줘.”
> VICA: “윤지영 교수님 사무실로 안내해드릴까요?”

### 6.3 재질문과 거절

상태: 기본 재질문·거절 현재 구현 / 동점 후보 분리는 보완 필요

다음 경우에는 Nav2 goal을 발행하지 않는다.

| 상황 | 처리 |
| --- | --- |
| 목적지가 없음 | 목적지를 다시 질문 |
| 등록되지 않은 목적지 | 안내할 수 없다고 응답 |
| 접근 불가 목적지 | `unavailable_reason` 안내 |
| 좌표가 `(0, 0)` | 위치 등록 필요 안내 |
| `calibrated=false` | 위치 보정 필요 안내 |
| 지도 밖 좌표 | Mission gate에서 차단 |
| Nav2 미준비 | 준비 중이라고 안내 |
| 주행 중 새 목적지 | 현재 임무 종료 또는 정지 후 다시 요청하도록 안내 |

현재 matcher는 최고 점수의 첫 목적지를 선택한다. 동점 후보 목록을 별도로 반환하는 기능은 아직 없다.

### 6.4 사용자 확인

상태: 현재 구현

1. 최초 목적지 요청은 `need_confirm=true`다.
2. 사용자가 긍정하면 같은 목적지를 `need_confirm=false`로 확정한다.
3. 사용자가 부정하면 목적지를 취소하고 새 요청을 받는다.
4. 확인이 30초 안에 끝나지 않으면 요청을 취소한다.

확인 전에는 Nav2 goal이 없어야 한다.

### 6.5 Mission Manager 출발 심사

상태: 현재 구현 / 실기기 통합 필요

Mission Manager는 다음 조건을 모두 검사한다.

1. `intent == navigate`
2. `matched_destination_id`가 비어 있지 않음
3. `need_confirm == false`
4. `safety_flag == normal`
5. E-stop 비활성
6. 현재 다른 goal로 주행 중이 아님
7. 목적지 ID가 실제 데이터에 존재함
8. `is_approachable == true`
9. pose가 유효하고 지도 경계 안임
10. Nav2 action server 준비 완료

조건이 통과된 경우에만 `BasicNavigator.goToPose()`를 호출한다.

### 6.6 Nav2 주행

상태: NavigateToPose 현재 구현 / 안전 명령 종단 연결 통합 필요

1. Mission Manager가 `map` frame의 goal을 한 번 전송한다.
2. Nav2는 저장 지도, AMCL, costmap, planner와 controller를 사용한다.
3. 현재 설정은 사용자 정의 BT XML이 아니라 Nav2 Humble 기본 NavigateToPose BT를 사용한다.
4. global planner는 Navfn, local controller는 DWB다.
5. local/global costmap은 `/scan`을 장애물 입력으로 사용한다.
6. Nav2의 속도 출력은 현재 `/cmd_vel` 경로다.
7. 목표 안전 구조에서는 최종 Nav2 명령을 `/cmd_vel_req`로 보내고, Safety Supervisor가 승인한 `/cmd_vel_safe`만 motor가 받아야 한다.

## 7. Smart Handle 회전 사전 안내

상태: 구현 목표

### 7.1 장치 역할

- 서보는 사용자의 손에 좌·우 회전 방향을 알리는 촉각 안내 장치다.
- LED는 좌·우 회전 시 해당 방향을 황색 점멸로, 직진 시 파란색 기본 점멸로 표시한다.
- 햅틱은 비상상황 발생 시 사용자에게 알리는 보조 신호다. 모터 정지를 보장하는 수단이 아니다. (구현 목표)
- 리코일 기반 보행 속도 추종은 현재 구현되어 있다. 스마트핸들의 가변저항값이 MDROBOT
  F1 I/O 모니터(CAN)를 통해 motor node에 전달되고, motor node가 knob 비율로 주행 속도를
  보정해 사용자 보행 속도에 맞춘다. F1 미수신 시 knob 0으로 처리되어 정지한다.
- 서보·LED·햅틱은 핸들의 아두이노 나노(Arduino Nano)가 제어한다. 생존신호(heartbeat)
  프로토콜은 사용하지 않는다.
- 서보는 로봇을 조향하지 않는다.
- guidance 계층은 `/cmd_vel`, `/cmd_vel_safe`, Nav2 goal을 발행하지 않는다.

### 7.2 회전 판단

단계적으로 구현한다. raw `/cmd_vel.angular.z`만으로는 결정하지 않는다.

1단계(우선 구현): EKF 융합 odometry의 yaw 변화량 기반

```text
EKF odometry (robot_localization 출력)
→ 최근 구간 yaw 변화량 누적
→ 임계값 이상 같은 방향으로 지속되면 LEFT / RIGHT 판단
→ debounce + hysteresis
→ 서보 구동 + 해당 방향 LED 점멸
→ yaw 변화량 수렴 시 서보 중립 + LED OFF
```

2단계(추후 확장): Nav2 global path look-ahead 기반 사전 예고

```text
Nav2 global path + 현재 TF
→ 일정 거리 앞 path heading과 현재 heading 차이 정규화
→ LEFT / RIGHT / NONE + PREPARE / NOW / COMPLETE cue
```

1단계는 회전이 시작된 뒤 표시되는 사후 감지이고, 회전 전 사전 예고는 2단계에서
제공한다. 짧은 자세 보정이나 장애물 회피로 인한 오동작을 막기 위해 두 단계 모두
최소 지속시간과 hysteresis를 적용한다. 회전 임계값(기존 45도 아이디어 등)은 YAML
parameter로 관리하고 사용자 시험으로 확정한다.

### 7.3 좌회전

아래 순서는 2단계(path 기반 사전 예고) 기준이다. 1단계에서는 PREPARE 없이
yaw 변화량으로 회전을 감지한 시점부터 LED·서보를 구동한다.

1. Turn Guide가 안정된 좌회전을 예측한다.
2. `LEFT, PREPARE` cue를 발행한다.
3. 왼쪽 LED가 황색으로 점멸한다.
4. Smart Handle 서보가 왼쪽 안내 위치로 이동한다.
5. 회전 직전 `LEFT, NOW`로 전환한다.
6. 로봇이 실제 좌회전을 수행한다.
7. 회전 완료 시 `COMPLETE`를 발행한다.
8. 왼쪽 LED를 끄고 서보를 중립으로 복귀시킨다.

### 7.4 우회전

좌회전과 동일한 순서로 오른쪽 LED와 서보 오른쪽 안내를 사용한다.

### 7.5 경로 재계획과 timeout

- cue에는 `sequence_id`와 `valid_until`을 둔다.
- 새 경로가 나오면 이전 sequence의 cue를 폐기한다.
- cue timeout, node 종료, Mission 정지·실패·도착 시 LED를 끄고 서보를 중립으로 복귀시킨다.
- E-stop은 모든 일반 회전 cue보다 우선한다.

## 8. 목적지 도착

상태: Mission 상태 로직 현재 구현 / TTS 연결 통합 필요

1. Nav2가 성공 결과를 반환한다.
2. Mission 상태가 `arrived`가 된다.
3. 활성 회전 cue를 취소한다.
4. 좌·우 LED를 끈다.
5. 서보를 중립으로 복귀시킨다.
6. 목적지별 `arrival_message` 또는 기본 도착 문구를 발행한다.
7. 짧은 dwell 뒤 `idle`로 돌아간다.

Mission 도착 문구는 현재 `/vica/tts_request`로 발행되지만 TTS subscriber 연결이 없어 실제 재생은 보장되지 않는다.

## 9. 긴급정지 시나리오

### 9.1 공통 우선순위

목표 구조:

```text
물리 버튼(CAN F1) · 앱 · STT 긴급어
→ emergency_stop_node 입력 통합
→ 중앙 E-stop latch
→ /emergency_stop=true
→ Nav2 goal 취소
→ Safety 출력 0 유지
→ motor가 /cmd_vel_safe=0 수신
→ 일반 Turn Guide cue 취소
→ 서보 중립
→ 비상 햅틱 알림
→ 양쪽 LED 비상 표시
→ 관리자 앱의 명시적 reset 전 재출발 금지
```

E-stop 래치는 `emergency_stop_node` 하나만 소유한다. motor node에는 별도 래치,
`/estop_state`, `/estop_reset`을 두지 않는다. 소프트웨어 E-stop은 인증된 물리
비상정지 회로를 대체하지 않는다.

### 9.2 음성 긴급정지

상태: 긴급어 전달·중앙 래치 코드 구현 / 실기기 종단 검증 필요

현재 하드 정지 키워드:

```text
멈춰, 정지, 스탑, 스톱, 안돼, 위험해
```

1. `ros_emergency_node`가 LLM 전에 긴급어를 감지한다.
2. `/vica/emergency`를 발행한다.
3. Mission Manager가 goal을 취소한다.
4. `emergency_estop_bridge`가 `/voice_emergency_stop` 펄스를 발행한다.
5. `emergency_stop_node`가 첫 `true`를 중앙 래치하고 `/emergency_stop=true`를 유지한다.
6. Safety가 `/cmd_vel_safe=0`을 유지한다.

`잠깐`, `천천히`, `느리게`는 음성 감지 목록에 있지만 현재 hard-stop bridge가 무시한다. 감속·일시정지 구현 전에는 보장된 정지 명령으로 안내하지 않는다.

음성 경로의 `false`는 입력 펄스 종료일 뿐 중앙 래치 해제가 아니다. STT와 LLM에는
reset 권한을 부여하지 않는다.

### 9.3 앱 긴급정지

상태: activate·중앙 래치·reset 코드 통합 / 앱·Nav2·motor runtime 검증 필요

1. 로그인한 운영자가 앱 비상정지 버튼을 누른다.
2. 앱이 `/app_estop_activate` 서비스를 호출한다.
3. `app_emergency_node`가 `/app_emergency_stop=true`를 발행한다.
4. 활성 Nav2 goal을 취소한다.
5. `/app_estop_state`로 앱 상태를 주기 발행한다.
6. 앱은 비상정지 overlay와 결과 로그를 표시한다.

`app_emergency_node`는 `ros2 launch vica_safety safety_bringup.launch.py`에 포함된다.

앱의 `/app_emergency_stop=false`는 앱 입력 원인의 해제만 뜻하며 중앙 래치를 해제하지
않는다.

### 9.4 물리 긴급정지

상태: CAN F1 판독·중앙 래치·기본 Safety launch 구현 / 실기 검증 필요

`emergency_stop_node`는 `input_mode=can_f1`일 때 MDROBOT F1 입력 비트를 직접 읽어
`/emergency_stop` 입력 상태에 포함한다. 물리 입력 byte/mask/active value는 실제 장비에서
검증해야 한다.

`vica_safety/safety_bringup.launch.py`는 `input_mode=can_f1`, `can_iface=can1`, CAN ID
`0x701`을 사용한다. 물리 상태를 앱·음성 입력과 함께 래치한 단일
`/emergency_stop` 상태를 Mission, Safety와 앱에 전달한다. 실제 byte/mask와 timeout
동작은 `[미검증]`이다.

### 9.5 긴급정지 해제

목표 구조:

1. 앱 또는 유지보수 터미널이 공개 reset을 요청한다. 로그인 관리자 UI는 `[TARGET]`이다.
2. 앱 구현 시 위험 원인 확인과 해제 여부를 팝업으로 재확인한다.
3. 물리 버튼, 앱 입력과 음성 입력이 모두 비활성인지 확인한다.
4. 물리 입력 상태가 fresh한지 확인한다.
5. Nav2 action server 실행 여부와 `/cmd_vel_req` 정지 조건을 확인한다.
6. Nav2가 실행 중이면 fresh status의 활성 Goal만 전체 취소하고, 처음부터 미실행이면 Goal
   검사를 생략한다. 이전 status가 stale이면 reset을 거부한다.
7. fresh `/emergency_stop=false` 확인 뒤 Supervisor 내부 reset과 `READY_TO_GO`를 확인한다.
8. 서보는 중립, LED는 일반 OFF 상태를 유지한다.
9. 이전 goal은 자동 재개하지 않고 새 목적지 요청을 기다린다.

Flutter는 `/app_estop_reset`, 유지보수 터미널은 영구 `/safety_reset`을 사용하며 두 서비스는
같은 콜백과 안전 검사를 거친다. 물리 버튼 해제와 앱·STT의 `false`는 reset 조건일 뿐
reset 명령이 아니다. 관리자 인증과 유지보수 호출자 접근 통제는 `[GAP]`이다.

## 10. 앱 운용 시나리오

### 10.1 로그인

상태: 구현 목표 (요구사항 확정 · 구현 후 임의 제거 금지)

1. 앱 실행 시 로그인 화면을 표시한다.
2. 기존 사용자 정보로 로그인한다.
3. 실패 시 운영 화면 진입을 차단하고 재입력 안내를 표시한다.
4. 성공 시 대시보드로 이동한다.
5. 로그아웃 시 로그인 화면으로 돌아간다.

신규 회원가입과 복잡한 권한 관리는 추가하지 않는다.

### 10.2 상태 확인

상태: 현재 구현

| 표시 | 실제 입력 |
| --- | --- |
| 현재 위치·방향 | `/robot_status`의 `x`, `y`, `yaw`, `current_location`, `map_id` |
| 운행 | `/robot_status.status == moving` |
| 대기·멈춤 | `/robot_status.status == waiting` |
| 오류 | `/robot_status.status == error`와 `error_reason` |
| 비상정지(현재 앱 입력) | `/app_estop_state.active == true` |
| 비상정지(목표 실제 상태) | 중앙 래치된 `/emergency_stop` 또는 동등한 통합 상태 |

현재 UI 라벨은 `moving=운행`, `waiting=대기`, `error=오류`다. 사용자 요구 표현인 “주행 중/멈춤”은 이 상태와 매핑한다.
현재 `/app_estop_state`는 앱 자체 입력 상태라 물리·음성으로 래치된 전체 E-stop을 보장하지
않는다. 배포 전 앱 표시를 중앙 상태와 연결해야 한다.

### 10.3 로그

상태: 기본 로그 현재 구현

현재 앱 로그에 포함되는 대표 이벤트:

- ROS 연결·재연결·연결 실패
- 지도 및 장소 목록 요청·수신
- 장소 저장·삭제 요청
- Nav2 상태 unavailable/available 알림
- 진단 오류
- 앱 비상정지 요청·성공·실패·해제

현재 코드가 모든 `moving ↔ waiting` 전이를 자동 기록하는 것은 아니다. 해당 이력이 필요하면 별도 상태 전이 로그를 추가하되 기존 로그 기능을 유지한다.

### 10.4 지도와 장소 관리

상태: 코드 구현 / runtime 통합 미검증

1. 앱이 지도 목록과 이미지를 조회한다.
2. 지도 위에서 장소 위치와 방향을 선택한다.
3. `/save_location`으로 JSON 요청을 보낸다.
4. `vica_destination_manager`가
   `~/vica_data/destinations/<map_id>/destinations.yaml`에 원자적으로 저장한다.
5. 잘못된 장소는 `/delete_location_request`로 삭제한다.

목적지 ID는 UUID v4다. 기존 `locations.json`은 이관하지 않고 빈 catalog에서 시작한다.
저장·삭제 뒤 Mission Manager reload service를 호출하며, 음성 노드는 같은 YAML의 변경
시각을 확인해 다음 발화 전에 public 목적지를 다시 읽는다.

### 10.5 원격 목적지 요청

상태: 코드 구현 / Nav2·실기 runtime 미검증

로봇이 사용자를 안내 중이 아닐 때(IDLE) 로그인한 운영자가 앱에서 저장된 장소를 선택해
원격으로 주행을 요청한다. 조이스틱·방향키 방식의 수동 teleop은 구현하지 않는다.

```text
앱 장소 선택
→ `/vica/mission/request_destination` (`RequestDestination`)
→ Mission Manager gate (6.5절 10조건 동일 적용)
→ NavigateToPose
→ Nav2 → 안전 계층 → motor
```

원칙:

1. 앱은 NavigateToPose를 직접 발행하지 않는다. goal 발행자는 Mission Manager 하나다.
   `vica_goto_goal.py`도 같은 Mission service를 호출하는 테스트·유지보수 client다.
2. 사용자 안내 세션이 활성이거나 Smart Handle 사용자 접촉이 감지되면(IN_USE) 원격 요청을 거부한다.
3. 주행 중 새 goal 요청은 Mission Manager의 `busy_navigating` gate가 거부한다.
   이 거부 로직은 현재 `mission_logic.py`에 구현되어 있다("지금 이동 중입니다" 안내).
4. E-stop은 최우선이며 해제 후 자동 재개는 없다.
5. 원격 요청도 실제 바퀴가 움직이는 기능이므로 안전 배선 blocker(5.2절) 해결과
   HIL 검증 후에만 활성화한다.

## 11. 실패와 통신 이상

| 상황 | 동작 |
| --- | --- |
| Nav2 action server 미준비 | goal 발행 금지, 준비 중 안내 |
| goal 실패·취소 | Mission `failed`, 새 요청 전까지 재출발 금지 |
| `/cmd_vel_req` timeout | Safety 출력 0 |
| `/emergency_stop` stale | Safety `FAULT`, 출력 0 |
| rosbridge 단절 | 앱은 실패 표시·재연결, 로봇 안전 계층은 독립 유지 |
| Turn Guide timeout | LED 기본 상태, 서보 중립 |
| guidance driver 종료 | 출력 안전 상태 복귀 — 하드웨어 설계로 확정 필요(LED 소등·서보 무토크) |
| 서보 fault | 서보 disable, 중립 시도, fault 표시 |
| LED fault | diagnostics 발행, 운용 정책에 따라 안내 중단 |
| 햅틱 fault | diagnostics 발행, 모터 E-stop 경로에는 영향 없음 |

## 12. 통합 검증 시나리오

### A. 정상 목적지

- 확인 전 goal 0개
- 확인 후 정확한 pose의 goal 1개
- 주행 성공 뒤 도착 상태

### B. 잘못된 목적지

- 미등록, 접근 불가, `(0, 0)`, 지도 밖 좌표 모두 goal 0개

### C. 음성 E-stop

- LLM을 기다리지 않고 `/vica/emergency → /voice_emergency_stop → /emergency_stop`
- 음성 펄스가 false로 돌아가도 `emergency_stop_node` 중앙 래치 유지
- goal 취소와 `/cmd_vel_safe=0` 확인

### D. 앱 E-stop

- service 성공과 `/app_estop_state` 일치
- 앱 입력 false만으로 중앙 래치가 풀리지 않음
- rosbridge 단절 시 성공으로 표시하지 않음

### E. reset

- 물리 입력 active, stale 입력, 비영 속도 명령에서는 reset 거부
- 앱 또는 유지보수 요청 후 중앙 E-stop 래치와 Supervisor reset 모두 완료
- 관리자 인증 미구현 `[GAP]`을 운영 승인으로 대체하지 않음
- 이전 goal 자동 재개 없음

### F. 앱 로그인·상태·로그

- 정상·실패 로그인 흐름
- 현재 위치, 운행, 대기, 비상정지, 오류 표시
- 연결·오류·E-stop 이벤트 로그

### G. 좌·우 사전 안내

- 실제 회전 전에 같은 방향 LED와 서보 동시 동작
- 직선과 짧은 자세 보정에서는 cue 없음
- 완료 후 LED OFF와 서보 중립

### H. 재계획·timeout

- 이전 sequence cue 폐기
- 좌우 신호 채터링 방지
- timeout 시 장치 안전 상태 복귀

## 13. 구현 우선순위

1. Nav2 `/cmd_vel_req`부터 Safety·motor까지 바퀴를 띄운 HIL 종단 검증
2. motor의 `/cmd_vel_safe` 단일 입력을 build/runtime에서 검증
3. `vica_safety` 중앙 래치와 reset 오케스트레이션 package build/test
4. 실제 운용 launch에서 물리 CAN F1·앱·음성·유지보수 reset 종단 검증
5. `robot_localization`, `python3-can` 설치 후 localization 전체 build/test
6. C5 `/wheel/odom`과 D455 `/imu/base_link`를 사용한 EKF·Cartographer 실기 검증
7. voice 운영 launch에서 개발 stub 제거 또는 선택 argument화
8. TTS가 `/vica/tts_request`를 구독하도록 우선순위 큐 구현
9. Mission 상세 상태를 `/robot_status`에 통합
10. 지도별 `destinations.yaml` 저장·reload·음성 검색의 runtime 통합 검증
11. `TurnGuide`, `SmartHandleState`, `SafetyState` 계약 정의
12. Turn Guide와 서보·LED driver 구현
13. bench test → 바퀴를 띄운 HIL → 제한 구역 저속 주행 순서로 검증

실제 바퀴가 움직이는 검증은 하드웨어 E-stop, 주변 통제, 바퀴를 띄운 상태와 즉시 전원 차단 수단을 먼저 확보한 뒤 수행한다.
