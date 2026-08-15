# VICA-smarthandle

Jetson Orin NX, ROS 2 Humble 기반 실내 안내 AMR 팀 workspace다.

작업 시작 순서:

1. `AGENTS.md`와 `GOVERNANCE.md`를 읽는다.
2. 작업 유형에 맞는 `guideline/` 문서만 추가로 읽는다.
3. 대상 저장소별 branch, `git status`, `git diff --check`, `git diff`를 확인한다.
4. 코드·설정·launch와 실행 결과를 현재 사실로 사용한다.

제품 저장소는 분리한다.

- `vica_ros2_ws/`: ROS 2, Nav2, Mission, Safety, motor, 공용 인터페이스
- `vica-voice-llm/`: STT/TTS, 긴급어 감지, LLM 목적지 해석
- `VICA_Supervisor/`: Flutter 관리자 앱

핵심 안전 기준:

- Nav2 최종 요청은 `/cmd_vel_req`, Safety 승인 출력은 `/cmd_vel_safe`다.
- motor node는 `/cmd_vel_safe`만 받고 E-stop 래치를 소유하지 않는다.
- 물리 버튼·앱·STT E-stop은 `emergency_stop_node`에서 통합·중앙 래치한다.
- 앱·STT의 `false`는 입력 해제일 뿐 reset이 아니다.
- reset은 모든 원인 해제 뒤 로그인한 관리자가 앱에서만 요청한다.
- LLM·앱은 Mission Manager, Safety 또는 CAN 경로를 우회하지 않는다.

위 세 항목은 2026-08-01~02 실기로 확인됐다. `[GAP]`에서 내린다.

- 중앙 E-stop 래치: `emergency_stop_node`의 `EmergencyLatch`. reset은 모든 원인이
  해제·fresh일 때만 승인한다(`try_reset`). 시험 `test_emergency_latch`,
  `test_reset_sequence`.
- 관리자 앱 단일 reset: `/app_estop_reset` → `reset_allowed`가 true인 상태
  (`ESTOP_RELEASED_WAIT_RESET`)에서만 통한다. bag 실측에서 "Safety reset 완료 …
  중앙 래치 해제" 확인.
- `/cmd_vel_req` 배선: 발행자 6(velocity_smoother + behavior_server) · 구독자 1
  (Safety), `/cmd_vel_safe` 발행자 1(Safety) · 구독자 1(motor). 2026-08-01 실측.

아직 `[미검증]`인 것은 `devlog/2026-08-02-주행테스트.md` 5절에 모아 둔다.

Nav2 로 진행할 일과 손대면 안 되는 축은 `docs/nav2_backlog.md`에 모아 둔다.
자율주행 설정을 바꾸기 전에 그 문서의 **§9 하지 말 것**을 먼저 읽는다. 항목 ID
(`NAV2-B1` 등)는 고정이므로 코드 주석·커밋 메시지에서 그대로 참조한다.

항상 한국어로 응답한다.

설명은 쉽고 간결하게, 비유를 들어서 한다. 사용자는 개발 입문자다 — 계층·원칙
같은 추상어를 나열하지 말고, 일상 비유 하나로 구조를 보여준 뒤 꼭 필요한
용어만 붙인다.
