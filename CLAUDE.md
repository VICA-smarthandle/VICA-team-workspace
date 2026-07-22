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

현재 중앙 E-stop 래치, 관리자 앱 단일 reset과 Nav2 `/cmd_vel` → `/cmd_vel_req`
연결은 `[GAP]/[TARGET]`이며 구현 완료로 표현하지 않는다. 항상 한국어로 응답한다.
