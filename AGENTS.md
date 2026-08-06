# VICA AI 작업 지침

이 파일은 작업공간 루트 아래의 VICA 프로젝트에서 AI 코딩 에이전트가 따라야 할
실행 지침이다. 팀 협업·승인·배포의 최상위 기준은 `GOVERNANCE.md`다.

## 1. 필수 시작 절차

1. `GOVERNANCE.md`를 먼저 읽는다.
2. 작업 유형에 맞는 `guideline/` 문서를 읽는다.
3. 대상 저장소의 추가 `AGENTS.md`가 있으면 함께 읽는다.
4. 대상 저장소마다 현재 브랜치, `git status --short`, `git diff --check`, `git diff`를
   확인한다.
5. 미추적 파일은 `git status`와 필요한 경우 `git diff --no-index`로 확인한다.
6. 기존 변경을 삭제·reset·stash·덮어쓰기·임의 commit하지 않는다.

문서 선택:

| 작업 | 먼저 읽을 문서 |
| --- | --- |
| 서비스·앱·사용자 동작 | `guideline/vica_scenario.md` |
| ROS 계약·Safety·TF·아키텍처 | `guideline/vica_architecture.md` |
| BT·패키지·폴더·파일 | `guideline/bt와 visual hierarchy of your folders and files.md` |
| 외부 기술 자료 | `guideline/official_reference_urls.md` |

## 2. 응답과 수정 원칙

- 항상 한국어로 답한다.
- 결과와 핵심 위험을 먼저 말하고 근거를 뒤에 둔다.
- 진단 요청에는 명시적인 수정 요청이 없으면 파일을 변경하지 않는다.
- 구현 요청은 필요한 범위만 수정하고 관련 없는 리팩터링·포맷 변경을 섞지 않는다.
- 코드·설정·launch와 재현 결과만 현재 구현으로 판정한다.
- 확인하지 못한 내용은 `[미검증]`, 없는 연결은 `[GAP]`, 목표안은 `[TARGET]`으로 구분한다.
- 모든 공유 문서 경로는 작업공간 루트 기준 상대경로로 쓴다.
- secret, token, 실제 `.env`, 개인 경로를 코드·로그·문서에 남기지 않는다.

## 3. 저장소 경계

| 저장소 | 책임 |
| --- | --- |
| `vica_ros2_ws/` | ROS 2, Nav2, SLAM, TF, Mission, Safety, motor, 공용 메시지 |
| `vica-voice-llm/` | STT/TTS, 긴급어 감지, LLM 해석, 목적지 후보 |
| `VICA_Supervisor/` | Flutter 앱, 관리자 UI, rosbridge client |

각 저장소의 브랜치와 diff를 별도로 확인한다. `vica_ros2_ws/`는 하위 지침에 따라
`dev`에서만 수정한다. 다른 저장소에는 확인되지 않은 브랜치 정책을 만들지 않는다.

공용 메시지 정본은 `vica_ros2_ws/src/vica_interfaces/`다. 메시지, topic, service,
action, QoS 또는 JSON key를 바꿀 때 producer와 consumer를 세 저장소에서 모두 찾는다.

## 4. 권한과 안전 경계

```text
음성·LLM 또는 관리자 앱
        ↓ 요청·후보
Mission Manager
        ↓ 검증된 Goal
Nav2·승인된 명령원
        ↓ /cmd_vel_req
Safety Supervisor
        ↓ /cmd_vel_safe
motor adapter
        ↓ CAN
```

- LLM은 `/cmd_vel*`, Nav2 goal 또는 CAN frame을 직접 발행하지 않는다.
- 앱은 Mission·Safety를 우회하지 않는다.
- Mission Manager가 일반 운영 Goal의 단일 권한자가 되는 것을 목표로 한다.
- Safety Supervisor가 소프트웨어 주행 명령의 최종 승인 권한을 가진다.
- 긴급어는 LLM 추론 전에 `/vica/emergency` 전용 경로로 전달한다.
- 물리 버튼·앱·STT E-stop은 `emergency_stop_node`에서 통합하고 중앙 래치한다.
- `app_emergency_node`가 공개 reset을 오케스트레이션한다. Nav2 action status의 마지막
  상태가 활성 상태이면 전체 취소하고 요청 이후의 새 terminal 상태를 확인한다. 마지막
  상태가 terminal이면 취소 호출을 생략하며, Nav2가 미실행이거나 Goal이 한 번도 없어
  status 이력이 없으면 Goal 검사도 생략한다.
- `emergency_stop_node`는 중앙 래치 해제, `safety_supervisor_node`는 주행 재승인을 각각
  내부 서비스로만 제공한다.
- motor node에는 E-stop 래치·`/estop_state`·`/estop_reset`을 두지 않는다.
- 앱·STT의 `false`는 입력 해제일 뿐 래치 reset이 아니며 LLM/STT에는 reset 권한이 없다.
- E-stop 해제 뒤 이전 Goal을 자동 재개하지 않는다.
- reset은 위험 원인 해제 확인 후 로그인한 관리자가 앱에서 명시적으로 수행하는 목표다.
- 유지보수 `/safety_reset`은 영구 보존하되 앱과 같은 안전 검사를 거치며, 관리자 인증이
  구현되기 전에는 호출자 인증이 없는 `[GAP]`으로 취급한다.

현재 안전 경로는 종단 간 검증 완료 상태가 아니다. 특히 다음을 구현 완료로 표현하지
않는다.

- Nav2 `/cmd_vel_req` remap의 실제 Goal·Safety·motor 종단 동작
- `vica_safety` 중앙 래치·reset 오케스트레이션의 실제 장치 종단 동작
- 물리·앱·음성 E-stop launch의 CAN·Nav2·motor 연동 실기 결과
- 관리자 인증과 `/safety_reset` 유지보수 접근 통제
- CAN/센서/Smart Handle 단절에 대한 종단 fail-safe

## 5. 실기기 작업

motor/CAN launch, Nav2 goal, teleop, `/cmd_vel*` 발행, E-stop reset, `can1` 상태 변경,
속도·timeout·장애물 임계값 변경은 실제 바퀴를 움직이거나 안전성을 낮출 수 있다.

사용자가 명시적으로 요청하고 바퀴를 띄운 상태, 주변 통제, 물리 E-stop과 즉시 전원
차단 수단을 확인한 경우에만 수행한다. 읽기 전용 상태 확인을 우선하고 실행 중인
`can1`을 임의로 down/up하지 않는다.

CAN frame ID, byte order, 좌우 모터 매핑, wheel geometry는 `source_file/` 매뉴얼과
현재 코드·실측 근거 없이 변경하지 않는다. 입력 누락과 stale 상태는 정지로 처리한다.

## 6. ROS·TF 핵심 규칙

```text
map                         Cartographer 또는 AMCL
└── odom                    EKF
    └── base_footprint
        └── base_link       robot_state_publisher / URDF
            ├── laser_frame
            └── camera_link
```

- 같은 transform을 두 노드가 동시에 발행하지 않는다.
- 기본 2D SLAM은 Cartographer 2D다.
- SLAM 문제는 파라미터보다 timestamp, 주기, TF 중복, wheel geometry와 모터 방향을
  먼저 검증한다.
- Isaac ROS Docker는 `camera_link` 아래 내부 frame만 소유한다.
- encoder 원시 출력은 `/wheel/odom`, EKF 표준 출력은 `/odom`이다.
- EKF 설정과 bringup의 정본은 `vica_ros2_ws/src/vica_localization/`이다.
- D455 IMU의 `/imu/base_link` 입력과 실제 센서 융합은 실기 검증 전까지 `[미검증]`으로 표시한다.

## 7. 문서와 공식 자료

개발 자료는 `guideline/official_reference_urls.md`의 ROS 2 Humble, Nav2, NVIDIA,
Isaac ROS 공식 문서를 우선한다. 새 공식 URL을 추가하거나 큰 개발 방향을 바꿀 때는
먼저 사용자에게 guideline 갱신을 제안하고 승인 후 반영한다.

의미 있는 아키텍처·인터페이스·Safety 결정과 실기기 결과는
`devlog/YYYY-MM-DD.md`에 기록한다. 사소한 포맷·오탈자까지 기록하지 않는다.

## 8. 표준 작업 절차

1. 요청을 문서, 진단, 코드, 설정, 인터페이스, 실기기 작업으로 분류한다.
2. 관련 지침과 현재 branch/status/diff를 확인한다.
3. `rg`로 producer, consumer, launch, parameter와 데이터 경로를 찾는다.
4. 기대 동작, 현재 동작, 안전 영향과 최소 수정 범위를 정한다.
5. 공개 계약 변경은 영향 저장소와 문서를 함께 갱신한다.
6. 가장 작은 정적 검사·단위 테스트부터 실행한다.
7. diff를 다시 읽어 안전 우회, 절대경로, secret, 생성물, 사용자 변경 침범을 확인한다.
8. 결과, 변경 파일, 테스트, 미검증 사항과 다음 안전 절차를 보고한다.

## 9. 저장소별 최소 검증

ROS 2 패키지는 대상 package만 `colcon build/test`한다. 음성 순수 로직은 사용 가능한
가상환경에서 `pytest`를 실행한다. Flutter는 `dart format --output=none
--set-exit-if-changed lib`, `flutter analyze`와 존재하는 테스트를 실행한다.

환경·dependency·하드웨어가 없어 실행하지 못한 검증은 성공으로 쓰지 않는다.
dependency 설치, 외부 서비스 호출 또는 장치 실행이 필요하면 먼저 승인을 받는다.

## 10. 완료 보고

최종 답변에는 다음을 간결하게 포함한다.

1. 완료 결과 또는 확인된 원인
2. 변경 파일과 핵심 내용
3. 실행한 테스트와 결과
4. 실행하지 못한 검증과 이유
5. 남은 Safety 위험 또는 실기기 검증 절차

commit과 push는 사용자가 요청한 경우에만 수행한다.
