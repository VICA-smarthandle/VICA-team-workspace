# VICA 협업·변경 거버넌스

이 문서는 VICA를 팀과 AI 에이전트가 함께 개발할 때 적용하는 최상위 협업 기준이다.
모든 경로는 작업공간 루트 기준 상대경로로 작성한다.

## 1. 적용 범위

VICA는 제품 코드와 배포 주기가 다른 세 Git 저장소를 분리해 운영한다.

| 저장소 | 책임 | 포함하지 않는 책임 |
| --- | --- | --- |
| `vica_ros2_ws/` | ROS 2, Nav2, SLAM, TF, Mission, Safety, motor, 공용 ROS 인터페이스 | LLM 추론, Flutter UI |
| `vica-voice-llm/` | STT/TTS, 긴급어 선감지, 자연어 해석, 목적지 후보 생성 | Nav2 goal·속도·CAN 직접 제어 |
| `VICA_Supervisor/` | Flutter 관리자 앱, 상태·지도·장소 UI, 관리 요청 | Safety 상태 머신·motor 직접 제어 |

`guideline/`, `devlog/`, `AGENTS.md`와 이 문서는 제품 저장소를 조정하는 기준 배포
자료다. 제품 코드를 한 저장소로 합치지 않고 계약과 배포 버전만 중앙에서 관리한다.
`source_file/` 원본은 로컬 참고자료로 유지하되 Git에서는 제외한다.

## 2. 기준 문서와 우선순위

문서가 충돌하면 다음 순서로 판단한다.

1. 실제 코드·설정·launch와 재현 가능한 실행 결과
2. 이 문서의 권한·승인·협업 규칙
3. `guideline/vica_architecture.md`의 인터페이스와 시스템 계약
4. `guideline/vica_scenario.md`의 제품 동작 요구사항
5. `guideline/bt와 visual hierarchy of your folders and files.md`의 BT·구조 안내
6. `guideline/official_reference_urls.md`의 공식 외부 문서
7. `devlog/`의 과거 작업 기록

문서의 `[TARGET]`, TODO, 설계안은 구현 완료를 의미하지 않는다. 문서와 코드가 다르면
코드를 현재 상태로 판정하고 문서 불일치를 같은 변경에서 바로잡는다.

## 3. AI와 작업을 시작하는 순서

모든 작업에서 `AGENTS.md`, 이 문서, 대상 저장소의 추가 지침을 먼저 읽는다. 그 뒤
작업 유형에 맞는 guideline만 읽어 불필요한 토큰 사용을 줄인다.

| 작업 | 추가로 읽을 문서 |
| --- | --- |
| 서비스 흐름·앱 기능·사용자 경험 | `guideline/vica_scenario.md` |
| topic/service/action/message·Safety·TF | `guideline/vica_architecture.md` |
| BT·패키지·폴더 구조 | `guideline/bt와 visual hierarchy of your folders and files.md` |
| 외부 기술 조사 | `guideline/official_reference_urls.md` |

작업 재개 전 대상 저장소마다 다음을 확인한다.

```bash
git -C <repository> branch --show-current
git -C <repository> status --short
git -C <repository> diff --check
git -C <repository> diff
```

미추적 파일은 일반 `git diff`에 나오지 않는다. `git status --short`로 먼저 확인하고,
필요한 단일 파일은 `git diff --no-index /dev/null <relative-file>`로 검토한다. 이 명령은
차이가 있으면 종료 코드 1을 반환하며 오류가 아니다. 확인을 위해 임의로 `git add`,
reset, stash 또는 commit하지 않는다.

## 4. 변경 권한과 승인

### 바로 수행할 수 있는 작업

- 사용자가 요청한 범위의 코드·설정·문서 변경
- 읽기 전용 진단과 최소 단위 테스트
- 같은 변경으로 발생한 오탈자, 상대경로, 문서 링크 정정
- 구현된 사실과 `[GAP]`·`[TARGET]` 상태의 정합화

### 먼저 승인이 필요한 작업

- 저장소 통합·분리, 패키지 이동 또는 이름 변경
- 공용 topic/service/action/message/JSON 계약 변경
- Safety 권한, E-stop/reset 정책 또는 Goal 권한자 변경
- 기본 SLAM·Nav2·TF ownership 변경
- 큰 기능 범위, 제품 시나리오 또는 개발 우선순위 변경
- 파일 삭제, 대규모 포맷 변경, dependency·환경 설치
- commit, tag, push, PR 생성 또는 실기기 구동

큰 방향 변경이 필요하면 AI는 먼저 영향받는 guideline 문서와 변경 이유를 제안한다.
팀 또는 사용자가 승인한 뒤 코드와 문서를 함께 반영한다.

## 5. 저장소 간 계약

공용 ROS 메시지의 정본은 `vica_ros2_ws/src/vica_interfaces/`다.

- LLM의 Pydantic 모델과 Flutter/rosbridge JSON은 정본 계약을 소비한다.
- `vica-voice-llm/ros2_ws/src/vica_interfaces/`는 현재 중복 사본이며 `[GAP]`으로 관리한다.
- 중복 사본을 독립 수정하지 않는다. 제거 또는 버전 고정 방식은 별도 승인 후 결정한다.
- producer와 consumer가 다른 저장소에 있으면 한쪽만 변경하지 않는다.
- 계약 변경 PR에는 영향 저장소, 호환성, 전환 순서와 rollback 방법을 적는다.

운영 권한 경계는 다음과 같다.

```text
LLM·앱 → 요청/후보
Mission Manager → 검증된 Goal 권한
Nav2 → /cmd_vel_req
Safety Supervisor → /cmd_vel_safe
motor adapter → CAN
```

LLM과 앱은 `/cmd_vel*`, Nav2 action 또는 CAN을 직접 발행하지 않는다. 시험 도구가 직접
발행하는 경우 운영 경로와 분리하고 문서에 `[TEST ONLY]`로 표시한다.

E-stop의 소프트웨어 권한은 다음처럼 단일화한다.

```text
물리 버튼(CAN F1) · 앱 · STT 긴급어
→ emergency_stop_node (입력 통합 + 중앙 래치)
→ /emergency_stop
→ Mission Manager + Safety Supervisor
→ /cmd_vel_safe=0
→ motor adapter
```

- E-stop 중앙 래치와 내부 래치 해제 권한은 `emergency_stop_node`가 소유한다.
- 공개 reset 절차(`/app_estop_reset`, 유지보수 `/safety_reset`)는
  `app_emergency_node`가 소유한다. Nav2 action status의 마지막 상태가 활성 상태이면
  전체 취소하고 요청 이후의 새 terminal 상태를 확인한다. 마지막 상태가 terminal이면
  취소 호출을 생략하며, Nav2가 미실행이거나 Goal이 한 번도 없어 status 이력이 없으면
  Goal 검사도 생략한다. 최종 READY까지 오케스트레이션한다.
- 주행 출력 재승인 권한은 `safety_supervisor_node`가 소유한다.
- motor node에는 별도 E-stop 래치, `/estop_state`, `/estop_reset`을 두지 않는다.
- 앱·STT에서 들어오는 `false`는 해당 입력의 해제만 뜻하며 중앙 래치를 해제하지 않는다.
- LLM과 STT에는 reset 권한이 없다.
- 모든 원인이 해제되고 정지 조건이 확인된 뒤, 로그인한 관리자가 앱 확인 팝업을 통해
  단일 reset을 요청하는 것이 목표다. 관리자 인증은 아직 `[GAP]`이다.
- `/safety_reset`은 영구 유지보수 인터페이스로 남기되 같은 오케스트레이션과 안전 검사를
  거치며, 현재 `Trigger` 계약에는 호출자 인증 정보가 없는 `[GAP]`이 있다.
- 물리 E-stop 전원·토크 차단 회로는 이 소프트웨어 래치와 별도로 유지한다.

## 6. 앱과 LLM 저장소 분리 원칙

LLM과 앱은 다음 이유로 별도 저장소를 유지한다.

- Python AI/audio 환경과 Flutter/Dart 환경의 dependency·빌드·배포 주기가 다르다.
- 앱 또는 모델 변경이 로봇 Safety 배포를 불필요하게 유발하지 않아야 한다.
- 저장소별 테스트와 담당자 ownership을 명확히 할 수 있다.

다만 `VICA_Supervisor/ros2/`의 로봇 측 보조 노드는 장기적으로
`vica_ros2_ws/src/vica_supervisor_bridge/` 같은 ROS 패키지로 이동하는 것을 목표로 한다.
이동 전까지는 현재 위치를 `[CURRENT]`, 이동안을 `[TARGET]`으로 구분하며 임의 이동하지
않는다.

## 7. 변경기록 자동화 기준

Git commit과 PR을 변경기록의 원천으로 사용한다. AI가 임의로 commit하거나 push하지
않으며 사용자의 명시적 요청이 있을 때만 수행한다.

권장 commit 제목 형식은 Conventional Commits다.

```text
<type>(<scope>): <summary>
```

주요 type은 `feat`, `fix`, `docs`, `refactor`, `test`, `build`, `ci`, `chore`다. scope는
`ros2`, `safety`, `nav2`, `voice`, `app`, `guideline`, `governance`처럼 책임 영역을 쓴다.

`devlog/YYYY-MM-DD.md`에는 모든 사소한 수정이 아니라 다음 변경만 기록한다.

- 아키텍처·Safety·TF·인터페이스 결정
- 저장소 간 호환성 또는 배포 순서 변경
- 실기기 시험 결과와 재현 조건
- 중요한 장애 원인과 해결·rollback 방법

릴리스 `CHANGELOG.md`는 향후 tag 사이의 규격화된 commit/PR 기록에서 자동 생성한다.
자동화가 실제 CI에 추가되기 전에는 `[TARGET]`으로 표현하고 생성 완료로 기록하지 않는다.

### 변경기록 자동화 흐름 `[TARGET]`

```text
PR 생성
→ 변경 경로로 영향 저장소·문서 분류
→ commit 제목 규칙 검사
→ 저장소별 lint/test와 diff --check
→ Safety·interface·TF 변경이면 guideline 갱신 여부 검사
→ 사람의 승인과 merge
→ release tag 사이 commit에서 CHANGELOG 생성
```

- 문서 영향이 없으면 PR에 `docs-not-needed` 이유를 적고 무의미한 문서 수정을 만들지 않는다.
- Safety·E-stop·TF·공용 인터페이스 변경은 자동 검사 통과만으로 승인하지 않는다.
- AI 전용 로컬 skill이나 개인 설정은 팀의 필수 실행 조건으로 삼지 않는다. 반복 절차는
  저장소의 Markdown 지침과 CI 명령으로 표현해 Claude, Codex와 일반 개발자가 같은 기준을
  사용할 수 있게 한다.
- 자동화 스크립트나 CI 파일이 실제로 추가되기 전까지 위 흐름은 배포 목표이며, 현재
  작동 중인 자동화로 표현하지 않는다.

## 8. PR·교차검증 기준

PR 또는 배포 후보 검토에는 다음 내용을 포함한다.

- 변경 목적과 범위
- 영향받는 저장소와 공개 계약
- Safety·E-stop·TF·실기기 영향
- 수행한 테스트와 수행하지 못한 검증
- guideline/devlog 갱신 여부
- rollback 방법

Claude 또는 다른 LLM의 교차검증 결과는 참고 근거다. 최종 판정은 코드, 테스트, 공식
문서와 팀 검토를 기준으로 한다. 교차검증 결과가 다르면 근거 파일과 재현 명령을 남긴다.

## 9. 팀 workspace 배포 기준

루트 저장소는 거버넌스·guideline·공식 참고자료·개발 기록·manifest를 배포하는 조정
저장소다. 세 제품 저장소는 embedded repository로 커밋하지 않고 `workspace.repos`로
받는다.

개발 workspace 생성:

```bash
git clone https://github.com/VICA-smarthandle/VICA-team-workspace.git VICA-smarthandle
cd VICA-smarthandle
vcs import . < workspace.repos
```

`workspace.repos`는 팀 개발 branch를 가리키는 `[CURRENT]` manifest다. 재현 가능한 release
배포 시에는 branch 이름이 아니라 검증된 tag 또는 commit SHA로 version을 고정한다.

최초 기준 push와 각 release 전에 다음 항목을 확인해야 문서 diff와 배포 이력을 신뢰할
수 있다.

- 추적할 기준 문서와 manifest 범위
- `source_file/` 원본을 받을 팀의 별도 공유 위치와 접근 권한
- 생성물·로그·secret에 대한 `.gitignore`
- release manifest에 고정할 세 제품 저장소의 tag 또는 commit SHA

제품 저장소에 미커밋 또는 미push 변경이 있으면 manifest가 그 상태를 재현할 수 없다.
변경을 검토·push하고 release revision을 갱신하기 전에는 로컬 작업공간과 새 팀
workspace가 동일하다고 선언하지 않는다.

공식 URL 문서는 삭제하지 않는다. 비밀정보, 개인 절대경로, 로컬 `.env`, 빌드 생성물은
배포 문서와 commit에 포함하지 않는다.

`source_file/`의 하드웨어 매뉴얼과 도면은 기술 검증을 위해 로컬에 유지하지만 루트
`.gitignore`로 제외한다. 팀 공유는 private 저장소·공용 드라이브·공식 다운로드 URL 중
권한이 확인된 방식을 사용한다. 공식 URL은 `guideline/official_reference_urls.md`로 계속
추적하며 원본 파일을 임의 삭제하지 않는다.
