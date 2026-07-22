# VICA Team Workspace

VICA는 Jetson Orin NX와 ROS 2 Humble을 사용하는 실내 안내 AMR 프로젝트다. 이 저장소는
제품 코드 자체가 아니라 팀·AI 협업 기준, 통합 아키텍처, 시나리오, 공식 참고자료와
세 제품 저장소를 받기 위한 manifest를 관리한다.

## Workspace 구성

| 경로 | 역할 |
| --- | --- |
| `vica_ros2_ws/` | ROS 2, Nav2, SLAM, Mission, Safety, motor, 공용 인터페이스 |
| `vica-voice-llm/` | STT/TTS, 긴급어 감지, LLM 목적지 해석 |
| `VICA_Supervisor/` | Flutter 관리자 앱 |
| `guideline/` | 시나리오, 아키텍처, BT·파일 구조, 공식 URL |
| `source_file/` | 로컬 하드웨어 매뉴얼·도면 원본, 루트 Git 제외 |
| `devlog/` | 중요한 결정과 실기기 검증 기록 |

## 팀 Workspace 만들기

ROS 2 개발 환경에 `vcstool`이 준비되어 있다는 전제다.

```bash
git clone https://github.com/VICA-smarthandle/VICA-team-workspace.git VICA-smarthandle
cd VICA-smarthandle
vcs import . < workspace.repos
```

`workspace.repos`는 개발 branch를 받는다. 릴리스 배포에서는 검증된 tag 또는 commit SHA로
version을 고정해야 한다.

## 작업 시작

1. [`AGENTS.md`](AGENTS.md)를 읽는다.
2. [`GOVERNANCE.md`](GOVERNANCE.md)를 읽는다.
3. 작업 유형에 맞는 guideline 문서만 읽는다.
4. 변경할 제품 저장소의 branch, status와 diff를 확인한다.

핵심 문서:

- [동작 시나리오](guideline/vica_scenario.md)
- [통합 아키텍처](guideline/vica_architecture.md)
- [BT 및 폴더·파일 구조](guideline/bt와%20visual%20hierarchy%20of%20your%20folders%20and%20files.md)
- [공식 참고자료 URL](guideline/official_reference_urls.md)

`source_file/`은 저작권과 저장소 용량을 고려해 Git에서 제외한다. 팀원이 필요한 원본은
팀의 별도 공유 위치 또는 공식 URL에서 받고, 공식 URL 목록은 계속 Git으로 관리한다.

## 현재 배포 주의사항

- Nav2 `/cmd_vel` → Safety `/cmd_vel_req` 연결은 아직 `[GAP]`이다.
- `emergency_stop_node`의 중앙 E-stop 래치와 관리자 앱 단일 reset은 `[TARGET]`이다.
- motor node는 `/cmd_vel_safe`만 구독하며 별도 E-stop 래치를 두지 않는다.
- localization 정본은 `vica_ros2_ws/src/vica_localization/`이며 계약은
  `/wheel/odom + /imu/base_link → EKF → /odom`이다.
- 새 환경에서는 `ros-humble-robot-localization`과 `python3-can`을 설치한 뒤 localization을
  다시 빌드·테스트해야 한다.
- EKF 설정과 합성 입력 검증은 완료했지만 C5와 D455를 함께 사용한 실기 융합은 `[미검증]`이다.
- 개발 manifest는 `vica_ros2_ws/`의 `dev`를 받는다. 재현 가능한 릴리스에서는 이동하는
  branch 대신 검증된 commit SHA를 사용한다.

실제 motor/CAN, Nav2 Goal 또는 E-stop reset 시험은 물리 E-stop, 바퀴를 띄운 상태,
주변 통제와 즉시 전원 차단 수단을 확보한 뒤 수행한다.
