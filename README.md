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

## GitHub 저장소와 책임

VICA는 제품별 dependency와 배포 주기가 다르므로 하나의 monorepo로 합치지 않는다.
팀 워크스페이스가 공통 계약과 제품 저장소의 조합을 관리한다.

| 저장소 | 역할 | 현재 개발 기준 |
| --- | --- | --- |
| [VICA-team-workspace](https://github.com/VICA-smarthandle/VICA-team-workspace) | 팀 지침, 아키텍처, 시나리오, 공식 URL, 저장소 manifest | `main` |
| [vica_ros2_ws](https://github.com/VICA-smarthandle/vica_ros2_ws) | ROS 2, Nav2, SLAM, EKF, Safety, motor | 통합 `dev`, 안정 `main` |
| [vica-voice-llm](https://github.com/VICA-smarthandle/vica-voice-llm) | STT, TTS, 긴급어 감지, LLM | 현재 `main` |
| [VICA_Supervisor](https://github.com/myw411/VICA_Supervisor) | Flutter 관리자 앱과 rosbridge client | 현재 `main` |

최상위와 세 제품 디렉터리는 각각 별도 Git 저장소다. 최상위에서 실행한 `git status`에는
제품 저장소의 변경이 나오지 않으므로 항상 저장소별로 확인한다.

```bash
git status --short
git -C vica_ros2_ws status --short
git -C vica-voice-llm status --short
git -C VICA_Supervisor status --short
```

## Branch 정책

### 팀 워크스페이스

```text
main
└── agent/*, docs/* 또는 feature/*
```

`main`에는 팀이 현재 따라야 하는 확정 지침만 둔다. 일반 문서 변경도 branch와 Pull
Request를 사용하는 것을 기본으로 한다.

### ROS 저장소

```text
main       실제 로봇 검증을 통과한 안정 버전
dev        기능을 합쳐 검증하는 통합 개발 버전
feature/*  기능 개발
fix/*      오류 수정
docs/*     문서 변경
```

일반적인 병합 순서는 다음과 같다.

```text
feature/fix/docs branch
→ Pull Request
→ dev
→ 통합·실기 검증
→ Pull Request
→ main
```

### LLM과 앱 저장소

현재 개발 manifest는 두 저장소의 `main`을 사용한다. 별도 `dev` 정책이 합의되기 전에는
기능 branch에서 작업하고 PR로 `main`에 병합한다. 새 branch 정책을 도입할 때는
`workspace.repos`와 `GOVERNANCE.md`를 함께 갱신한다.

## 직접 push와 보호 원칙

- `main`에는 직접 push하지 않는다.
- 일반 작업은 기능 branch와 Pull Request를 사용한다.
- ROS `dev` 직접 push도 원칙적으로 사용하지 않는다.
- 최초 기준 배포나 긴급 복구처럼 팀 책임자가 명시적으로 승인한 경우에만 예외를 둔다.
- `git push --force`와 공유 branch history 재작성은 금지한다.
- GitHub `main`에는 PR 승인, 미해결 대화 차단, force push·branch 삭제 금지를 권장한다.
- CI가 추가되면 build/test를 필수 status check로 설정한다.

## 매일 작업을 시작하는 순서

먼저 변경이 남아 있지 않은지 확인한다.

```bash
git -C vica_ros2_ws status --short
git -C vica_ros2_ws diff --check
git -C vica_ros2_ws diff
```

작업공간이 깨끗할 때 최신 통합 branch를 받는다.

```bash
git -C vica_ros2_ws switch dev
git -C vica_ros2_ws pull --ff-only origin dev
```

기능 branch를 만든다.

```bash
git -C vica_ros2_ws switch -c feature/central-estop-latch
```

`pull --ff-only`는 예상하지 않은 자동 merge commit이 생기는 것을 방지한다. 로컬 변경이
남아 있으면 바로 pull하거나 reset하지 말고 먼저 변경 소유자와 범위를 확인한다.

## 작업 중 문서 확인

모든 작업은 다음 순서로 시작한다.

1. `AGENTS.md`
2. `GOVERNANCE.md`
3. 작업 유형에 맞는 guideline 한 개
4. 대상 저장소의 branch, status와 diff

공개 계약을 변경하면 코드만 수정하지 않는다.

| 변경 대상 | 함께 확인할 내용 |
| --- | --- |
| topic/service/action/message | 세 저장소의 producer와 consumer |
| TF ownership | 동일 transform의 중복 publisher |
| E-stop/reset | 중앙 래치, 관리자 권한, fail-safe |
| Nav2 Goal | Mission Manager와 시험 도구의 권한 |
| 앱 JSON | ROS producer와 Flutter parser |
| 패키지·폴더 구조 | BT·Visual Hierarchy 문서 |

## Stage와 commit 방법

여러 작업이 섞인 상태에서 `git add .` 또는 `git add -A`를 사용하지 않는다. commit 목적에
해당하는 파일만 명시적으로 stage한다.

```bash
git -C vica_ros2_ws add \
  src/vica_localization \
  src/encoder_feedback/encoder_feedback/encoder_feedback.py \
  src/encoder_feedback/package.xml

git -C vica_ros2_ws diff --cached
git -C vica_ros2_ws diff --cached --check
```

Commit 제목은 Conventional Commits 형식을 사용한다.

```text
<type>(<scope>): <summary>
```

| type | 용도 |
| --- | --- |
| `feat` | 새로운 기능 |
| `fix` | 오류 수정 |
| `refactor` | 동작 목적을 유지한 구조 변경 |
| `docs` | 문서 변경 |
| `test` | 테스트 추가·수정 |
| `build` | 빌드와 dependency |
| `chore` | 파일·설정 정리 |

예:

```text
feat(localization): add wheel and imu EKF bringup
fix(safety): reject reset while command is active
docs(ros2): update localization verification guide
chore(sensor): remove unused rear scan filter
```

한 commit에는 한 가지 목적만 담는다. localization, Safety, sensor 정리와 문서 변경을
가능하면 별도 commit으로 나눈다.

## Push와 Pull Request

작업 branch를 push한다.

```bash
git -C vica_ros2_ws push -u origin feature/central-estop-latch
```

ROS 기능 PR은 일반적으로 `dev`를 base branch로 선택한다.

```text
base: dev
compare: feature/central-estop-latch
```

PR 본문에는 다음 항목을 포함한다.

```markdown
## 변경 목적

변경이 필요한 이유

## 주요 변경

- 변경 파일과 동작
- topic/service/TF 변경

## Safety 영향

- 주행 명령, E-stop, reset, fail-safe 영향

## 검증

- 실행한 build/test와 결과
- 합성 입력 또는 실기 검증 결과

## 미검증 사항

- hardware나 dependency가 없어 확인하지 못한 항목

## Rollback

- 문제가 생겼을 때 되돌리는 방법
```

테스트가 완전히 통과하지 않아도 공유가 필요하면 Draft PR로 올리고 실패 원인과 미검증
항목을 명시한다. 일부 테스트 통과를 전체 검증 완료로 표현하지 않는다.

## 리뷰와 merge 기준

다음 변경은 최소 한 명 이상의 리뷰를 받고 작성자 혼자 안정 branch에 병합하지 않는다.

- motor와 CAN frame
- E-stop과 reset
- Safety Supervisor
- `/cmd_vel*` 연결
- TF ownership
- wheel radius, wheel base와 모터 방향
- 속도·가속도·timeout
- 공용 ROS 메시지와 앱 JSON 계약

리뷰어는 다음을 확인한다.

- 요청 범위 밖 파일이 섞이지 않았는가
- 기존 팀원의 변경을 덮어쓰지 않았는가
- 개인 절대경로, secret과 생성물이 포함되지 않았는가
- producer와 consumer가 함께 변경됐는가
- 실기 미검증 항목을 완료로 표현하지 않았는가
- 필요한 guideline과 devlog가 갱신됐는가

## 최소 테스트

ROS 패키지:

```bash
source /opt/ros/humble/setup.bash
colcon build --symlink-install --packages-select <package>
colcon test --packages-select <package>
colcon test-result --verbose
```

LLM 순수 로직:

```bash
pytest
```

Flutter 앱:

```bash
dart format --output=none --set-exit-if-changed lib
flutter analyze
flutter test
```

dependency 또는 hardware가 없어 실행하지 못한 검증은 성공으로 기록하지 않는다.

## 실제 로봇 변경의 검증 단계

다음 변경은 코드 리뷰와 빌드만으로 ROS `main`에 병합하지 않는다.

- Motor CAN 명령
- `/cmd_vel*`
- E-stop/reset
- wheel geometry와 모터 방향
- 속도·가속도·timeout
- Nav2 Goal과 장애물 안전 설정

검증 순서:

```text
정적 검사
→ 단위 테스트
→ 패키지 빌드
→ 모터 없는 합성 입력
→ 바퀴를 띄운 HIL
→ 제한 구역 저속 주행
→ main 병합
```

실기 조건과 결과는 `devlog/YYYY-MM-DD.md`에 남긴다.

## 여러 저장소를 함께 변경할 때

공용 계약 변경은 저장소 하나만 수정하지 않는다. 예를 들어 ROS 메시지나 JSON 상태를
변경하면 다음 순서로 영향 범위를 확인한다.

```text
vica_ros2_ws          메시지·topic 정본
vica-voice-llm        Python producer/consumer
VICA_Supervisor       rosbridge·JSON parser·UI
VICA-team-workspace   아키텍처·시나리오·배포 순서
```

저장소별 PR을 만들고 서로 링크한다. PR 설명에 호환성, 병합 순서와 rollback 방법을 적는다.

## GitHub에 포함하지 않는 파일

- `build/`, `install/`, `log/`
- `.env`, token, credential, private key
- 개인 절대경로가 들어간 설정과 로그
- 임시 rosbag과 대용량 생성물
- 저작권 또는 용량 문제가 있는 원본 PDF·도면
- `source_file/`

`source_file/` 원본은 공식 URL 또는 접근 권한이 확인된 별도 팀 공유 위치로 전달한다.

## 개발 manifest와 release

`workspace.repos`는 팀 개발용이므로 이동하는 branch를 사용한다.

```text
vica_ros2_ws: dev
vica-voice-llm: main
VICA_Supervisor: main
```

정식 릴리스는 branch 대신 검증된 commit SHA를 기록한 별도 manifest를 사용한다.

```text
workspace.repos          개발용 branch manifest
workspace.release.repos  배포용 commit SHA manifest
```

권장 릴리스 순서:

1. 세 제품 저장소의 검증 commit 확정
2. release manifest에 commit SHA 기록
3. 실기 검증 조건과 결과 기록
4. 팀 워크스페이스에 버전 tag 생성
5. GitHub Release에 변경사항과 미검증 항목 기록

## 문제가 생겼을 때

공유 작업공간에서는 다음 명령을 임의로 실행하지 않는다.

```bash
git reset --hard
git checkout -- .
git clean -fd
git push --force
```

먼저 현재 상태를 보존하고 확인한다.

```bash
git status --short
git diff
git diff --cached
```

충돌이나 잘못된 commit이 생기면 저장소, branch, commit hash와 diff를 팀에 공유한 뒤
복구 방법을 결정한다.

## 팀원용 10줄 요약

1. `VICA-team-workspace`를 clone하고 `workspace.repos`로 제품 저장소를 받는다.
2. 작업 전 `AGENTS.md`, `GOVERNANCE.md`와 관련 guideline을 읽는다.
3. 최상위와 제품 저장소의 `status`와 `diff`를 각각 확인한다.
4. 최신 기준 branch에서 기능 branch를 만든다.
5. 하나의 목적 단위로 파일을 stage하고 commit한다.
6. 일반 작업은 직접 push 대신 Pull Request를 사용한다.
7. ROS는 기능 branch → `dev` → 실기 검증 → `main` 순서로 병합한다.
8. 테스트 실패와 실기 미검증 항목을 PR에 정확히 적는다.
9. Safety·TF·인터페이스 변경은 코드와 guideline을 함께 갱신한다.
10. `main` force push와 사용자 변경을 지우는 reset·clean을 사용하지 않는다.
