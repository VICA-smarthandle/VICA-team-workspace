# 매핑 전용 Terminator 레이아웃과 지도 저장·변환 설계

작성일: 2026-08-12
대상 저장소: `VICA-team-workspace` (본 문서, `scripts/`)
작업 브랜치: `feat/terminator-map-layout`
관련 코드: `scripts/vica_terminator_layout.py`,
`vica_ros2_ws/src/vica_cartographer/launch/vica_slam_bringup.launch.py`,
`VICA_Supervisor/ros2/map_list_node.py`
관련 문서: `docs/vica_robot_bringup_manual.md` 5절, `AGENTS.md` 6절

## 1. 문제

주행은 `terminator -l vica_drive` 한 줄로 뜬다. 매핑만 그렇지 않다. 지금은 터미널을
손으로 여러 개 열어 순서대로 명령을 치고, 지도를 저장한 뒤 `pgm → png` 변환도 손으로
한다. 장소가 바뀌어 다시 매핑하는 상황이 반복되므로(2026-08-11 `vica_map_0810`) 주행과
같은 방식으로 묶는다.

두 번째 문제가 붙어 있다. 생성기가 지도 id를 **생성 시점에 문자열로 굳힌다.** 새 지도를
떠도 생성기를 다시 돌리지 않으면 조용히 옛 지도로 주행한다. 실제로 어긋나 있다 —
`DEFAULT_MAP_ID`는 `vica_map_0630`인데 현재 지도는 `vica_map_0810`이다.

### 1.1 매핑에 필요한 것과 아닌 것

| 구성 | 매핑에 필요한가 | 근거 |
| --- | --- | --- |
| `②` display | 필요 | `base_link → laser_frame` TF 공급원 |
| `③` lidar | 필요 | Cartographer 입력 `/scan` |
| `④` safety | 필요 | `⑤` motor보다 먼저 떠야 한다 |
| `⑤` motor | **필요** | `encoder_feedback`이 `request_position_feedback: False`로 뜬다. 피드백을 요청하는 쪽은 motor node다. 없으면 `/wheel/odom`이 안 나온다 |
| `⑥⑦` d455·imu | 필요 | EKF가 `imu0: /imu/base_link`를 융합한다(`ekf.yaml` 60행). 없으면 바퀴 오도메트리만 남아 회전 각도가 밀린다 |
| `⑧` nvblox | 불필요 | Cartographer는 `/scan`과 `/odom`만 본다 |
| `⑨` nav2 | **금지** | 아래 1.2 |
| `⑩⑪⑫⑬` mission·앱·음성 | 불필요 | 지도 작성에 관여하지 않는다 |

Cartographer 설정(`vica_2d.lua`)은 `use_odometry = true`, `use_imu_data = false`다. 즉
Cartographer 자신은 IMU를 직접 쓰지 않고, IMU는 EKF를 통해 `/odom` 품질로만 들어온다.

### 1.2 `slam` 칸과 `nav2` 칸은 상호 배타다

`nav2_map_test.launch.py`(97행)와 `vica_slam_bringup.launch.py`(58행)가 **둘 다**
`wheel_ekf.launch.py`를 include한다. 함께 띄우면 두 가지가 동시에 깨진다.

1. `/odom`과 `odom → base_footprint` TF가 이중 발행된다
2. AMCL과 Cartographer가 둘 다 `map → odom` TF를 발행한다 (`AGENTS.md` 6절 위반)

2026-08-01에 스택이 두 벌 돌아 하루를 잃은 것과 같은 종류의 사고다. 레이아웃에서
`nav2` 칸을 아예 빼고, `slam` 칸의 안내문에 명시한다.

### 1.3 앱이 요구하는 지도 형식

`map_list_node.py` 62행이 `vica_ros2_ws/maps/*.png`를 훑고, 같은 stem의 `.yaml`에서
`resolution`·`origin`을 읽는다. 앱은 `image_url: /maps/<이름>.png`로 HTTP 8000에서
이미지를 받는다.

`map_saver_cli`는 `.pgm`과 `.yaml`만 만든다. 따라서 **`.png` 한 벌을 같은 이름으로 더
만들어 옆에 두는 단계**가 반드시 필요하다. 기존 지도가 모두 그 형태다.

```
maps/vica_map_0810.pgm   400x306  ← Nav2 map_server가 읽는다 (yaml의 image: 필드)
maps/vica_map_0810.png   400x306  ← 앱이 읽는다 (map_list_node의 glob)
maps/vica_map_0810.yaml           ← 둘의 메타데이터
```

변환 도구는 Jetson에 이미 있다: `/usr/bin/convert`(ImageMagick), `/usr/bin/pnmtopng`,
Pillow 9.0.1.

## 2. 범위

**한다**

1. 레이아웃 `vica_map` 신설 (생성기에 프로파일 1개, 칸 2개 추가)
2. `scripts/vica_map_save.sh` 신설 — 저장 + `png` 변환 + 검증
3. 지도 id를 실행 시점에 읽도록 바꾼다 (`maps/CURRENT_MAP` 정본화)
4. `guard` 이름 15자 초과 3건 수정과 재발 방지 검사 (아래 7절)

**하지 않는다**

- 기존 4개 레이아웃의 **칸 구성** 변경 — 어떤 칸이 어느 열에 몇 개 들어가는지는
  건드리지 않는다. 개별 칸의 `guard`와 지도 id 참조 방식은 3·4번 항목에서 바뀐다
- Cartographer 파라미터(`vica_2d.lua`) 변경
- Nav2·Safety·motor 설정 변경
- 지도 파일 자체의 생성·삭제·이동

## 3. 레이아웃 `vica_map`

3열 14칸. 열은 왼쪽부터 기동 순서이고, 같은 열 안에서도 위에서 아래로 흐른다 —
기존 프로파일의 규칙을 그대로 따른다.

| 열 | 칸 | 모드 | 신규 |
| --- | --- | --- | --- |
| 1 (전원·센서) | `power` `can` `display` `lidar` `safety` | HOLD HOLD AUTO AUTO AUTO | |
| 2 (구동·인지·SLAM) | `motor` `d455` `imu` `slam` | HOLD HOLD AUTO HOLD | `slam` |
| 3 (그리기·저장) | `teleop` `rviz` `save` `check` `shell` | HOLD HOLD HOLD HOLD SHELL | `save` |

`Profile.basis`에 적을 근거:

> Cartographer는 `/scan`과 `/odom`만 본다(`vica_2d.lua`: `use_odometry = true`,
> `use_imu_data = false`). nvblox·Nav2·Mission·앱·음성은 지도 작성에 관여하지 않아
> 뺐다. `nav2`는 뺀 것이 아니라 **넣으면 안 되는 것**이다 — SLAM과 EKF·`map→odom`
> TF가 충돌한다. `motor`는 뺄 수 없다. 엔코더 피드백을 요청하는 쪽이 motor node다.

`rviz`는 매핑에서는 필수다. 지도가 자라는 것을 보지 않고는 어디를 더 돌아야 하는지
알 수 없다. 주행 프로파일에서 "무거우니 끄라"고 적은 것과 판단이 반대이므로, 칸
안내문에 그 차이를 적는다.

## 4. 신규 칸 `slam`

```python
"slam": Term(
    title="⑧ slam",
    note=(
        "[금지] nav2 칸과 함께 띄우지 말 것. 두 launch가 모두 wheel_ekf를 include해",
        "/odom 과 odom→base_footprint TF 가 이중 발행되고, AMCL 과 Cartographer 가",
        "둘 다 map→odom 을 내보내 위치가 통째로 깨진다.",
        "선행 조건은 ⑤ motor 다. encoder_feedback 은 피드백을 스스로 요청하지 않아",
        "motor node 가 없으면 /wheel/odom 이 나오지 않는다.",
        "RViz Fixed Frame 을 map 으로 두고 지도가 자라는 것을 보며 끌고 다닌다.",
    ),
    command="ros2 launch vica_cartographer vica_slam_bringup.launch.py",
    mode=HOLD,
    guard=("cartographer_no", "cartographer_oc", "ekf_node", "encoder_feedbac"),
),
```

`precheck`로 `ekf_node`·`amcl`이 이미 떠 있는지 읽기 전용으로 보여준다. `ros2` CLI를
쓰지 않고 프로세스 테이블을 본다 — 생성기 596행의 기존 판단을 따른다.

HOLD인 이유는 두 가지다. `⑤ motor` 뒤라는 순서 의존성이 있고, 잘못 눌러 Nav2와 겹치면
피해가 크다.

## 5. 신규 칸 `save`

```python
"save": Term(
    title="save",
    note=(
        "지도 저장 + 앱용 png 변환 + 검증을 한 번에 한다.",
        "이름을 바꾸려면 위 화살표로 꺼내 마지막 인자만 고친다.",
        "같은 이름이 이미 있으면 거부한다 — 어렵게 그린 지도를 덮어쓰지 않는다.",
        "성공하면 maps/CURRENT_MAP 이 갱신되어 다음 주행이 이 지도를 쓴다.",
    ),
    command="bash $VICA_ROOT/scripts/vica_map_save.sh vica_map_$(date +%m%d)",
    mode=HOLD,
),
```

HOLD이므로 `history`에 들어가고, 사람이 위 화살표로 꺼내 이름을 확인·수정한 뒤 Enter를
누른다. 날짜로 미리 채워 두되 확정은 사람이 한다.

## 6. `scripts/vica_map_save.sh`

`scripts/vica_drive_record.sh`, `vica_goto.sh`와 같은 자리다. 인자는 지도 이름 하나다.

```
vica_map_save.sh <지도이름>
```

### 6.1 단계

| 단계 | 하는 일 | 실패하면 |
| --- | --- | --- |
| 1 | 인자 검증 — 이름이 없거나 `[A-Za-z0-9_-]` 밖의 문자면 거부 | 사용법 출력 후 종료 |
| 2 | 덮어쓰기 방지 — `maps/<이름>.{pgm,png,yaml}` 중 하나라도 있으면 거부 | 존재하는 파일 목록 출력 후 종료 |
| 3 | 사전 점검 — `pgrep -x cartographer_oc`로 SLAM 기동 확인 | "SLAM이 떠 있지 않다" 출력 후 종료 |
| 4 | `ros2 run nav2_map_server map_saver_cli -f <maps>/<이름>` | 종료 코드 그대로 전달 |
| 5 | `convert <이름>.pgm <이름>.png` | 변환 실패 출력 후 종료 (pgm·yaml은 남긴다) |
| 6 | 검증 출력 (6.2) | 불일치를 경고로 출력 |
| 7 | `maps/CURRENT_MAP`에 `<이름>` 기록 | 실패해도 지도는 남으므로 경고만 |

3단계를 4단계 앞에 두는 이유는 `map_saver_cli`가 SLAM 없이도 timeout까지 기다린 뒤
빈 손으로 끝나기 때문이다. 사람이 그 대기를 "저장 중"으로 오해할 여지를 없앤다.

### 6.2 검증 출력

- 세 파일(`.pgm` `.png` `.yaml`)이 모두 생겼는가
- `.pgm`과 `.png`의 픽셀 크기가 같은가 (Pillow로 읽는다)
- `.yaml`의 `resolution`·`origin` 값
- 앱이 보게 될 경로 `/maps/<이름>.png`
- `CURRENT_MAP`의 새 값

### 6.3 다음 단계 안내

성공 시 마지막에 출력한다.

```
다음 주행부터 이 지도를 씁니다. 생성기를 다시 돌릴 필요는 없습니다.
확인:  cat vica_ros2_ws/maps/CURRENT_MAP
되돌리기:  export VICA_MAP_ID=<옛 이름>   (터미널을 띄우기 전에)
```

## 7. 지도 id를 실행 시점에 읽는다

### 7.1 지금의 문제

`build_terms(map_id)`가 `⑨ nav2`·`⑩ mission`·`⑫ llm` 세 칸의 명령 문자열에 지도 id를
직접 박는다. 워크스페이스 경로는 `$VICA_ROS_WS`로 남겨 실행 시점에 펼치면서(생성기
117행 주석: *"생성 시점 경로를 굳혀버리면 워크스페이스를 옮겼을 때 조용히 옛 지도를
읽는다"*) 지도 이름만 같은 원칙에서 빠져 있다.

### 7.2 설계

우선순위 3단으로 rc가 실행 시점에 정한다.

```
$VICA_MAP_ID (환경변수)  →  maps/CURRENT_MAP 파일  →  생성 시점 기본값(--map-id)
```

`ROS_BLOCK`에 추가할 내용:

```bash
# 지도 id. 파일 하나를 정본으로 두고 실행 시점에 읽는다. 생성 시점에 굳히면
# 새 지도를 떠도 생성기를 다시 돌리기 전까지 조용히 옛 지도로 주행한다.
if [ -z "${VICA_MAP_ID:-}" ]; then
  if [ -r "$VICA_ROS_WS/maps/CURRENT_MAP" ]; then
    VICA_MAP_ID="$(tr -d ' \t\n\r' < "$VICA_ROS_WS/maps/CURRENT_MAP")"
  fi
fi
export VICA_MAP_ID="${VICA_MAP_ID:-{fallback_map_id}}"
```

`{fallback_map_id}`는 생성기가 rc를 만들 때 `--map-id` 값으로 채운다. 나머지는 실행
시점에 정해진다.

세 칸의 명령에서 `{map_id}`를 `$VICA_MAP_ID`로 바꾼다. 예:

```
ros2 launch vica_nav2 nav2_map_test.launch.py map:=$VICA_ROS_WS/maps/$VICA_MAP_ID.yaml
```

**`⑨⑩⑫` 세 칸은 머리말에 현재 값을 출력한다.** 눈으로 확인되지 않으면 조용히
어긋나는 문제가 그대로 남는다.

```
지금 가리키는 지도: vica_map_0812   (출처: maps/CURRENT_MAP)
```

`--map-id`는 그대로 남긴다. 파일도 환경변수도 없을 때의 폴백이다. 기본값은
`vica_map_0630` → `vica_map_0810`으로 바꾼다. 현재 지도와 맞춘다.

`CURRENT_MAP` 파일이 가리키는 지도가 실제로 없으면 `⑨` 칸의 precheck에서 경고한다.
Nav2가 map 파일을 못 찾고 죽는 것보다 먼저 보이게 한다.

### 7.3 `CURRENT_MAP` 파일

- 위치: `vica_ros2_ws/maps/CURRENT_MAP`
- 내용: 지도 이름 한 줄 (`vica_map_0812`). 확장자·경로 없음
- Git: `vica_ros2_ws`는 별도 저장소다. 이 파일의 추적 여부는 그 저장소 담당자가
  정한다. 본 설계는 파일을 만들고 읽기만 한다

## 8. 범위 안에서 발견한 결함 — `guard` 이름 3건

`vica_running()`은 `pgrep -x`로 comm을 본다. Linux comm은 15자에서 잘린다(이 Jetson에서
`at-spi2-registr`, `evolution-addre` 등으로 확인). 16자로 적힌 guard는 **영원히 매칭되지
않아 중복 실행 방지가 꺼져 있다.**

| 칸 | 현재 값 | 길이 | 고칠 값 |
| --- | --- | --- | --- |
| `motor` | `mdrobot_can_keyb` | 16 | `mdrobot_can_ke` |
| `mission` | `vica_mission_man` | 16 | `vica_mission_ma` |
| `app` | `rosbridge_websoc` | 16 | `rosbridge_webso` |

`motor`는 이번 `vica_map` 레이아웃에 들어가는 칸이므로 범위 안이다. 나머지 둘은 같은
한 줄 수정이라 함께 고친다.

재발 방지로 `main()`의 기존 칸 이름 검사 옆에 길이 검사를 넣는다.

```python
for name in term.guard:
    if len(name) > 15:
        raise SystemExit(f"guard 이름이 15자를 넘는다: {key} -> {name}")
```

`mdrobot_can_ke`는 실제 comm을 실기에서 확인하기 전까지 `[미검증]`이다. 검증 절차는
9절에 둔다.

## 9. 검증

### 9.1 장비 없이 (노트북·Jetson 공통)

| 대상 | 명령 | 기대 |
| --- | --- | --- |
| 생성기 문법·구성 | `python3 scripts/vica_terminator_layout.py --list` | `map` 프로파일이 14칸으로 출력 |
| config 미변경 확인 | `python3 scripts/vica_terminator_layout.py --dry-run` | 쓰기 없이 계획만 출력 |
| guard 길이 검사 | 위 두 명령 중 하나 | 15자 초과 시 즉시 중단 |
| 저장 스크립트 문법 | `bash -n scripts/vica_map_save.sh` | 무출력 |
| 인자 검증 | `bash scripts/vica_map_save.sh` | 사용법 출력, 종료 코드 비0 |
| 덮어쓰기 거부 | `bash scripts/vica_map_save.sh vica_map_0810` | 거부, 지도 파일 무변경 |
| SLAM 미기동 거부 | `bash scripts/vica_map_save.sh vica_map_test1` | 3단계에서 중단, 파일 생성 없음 |

### 9.2 Jetson 실기 (사용자 승인 후)

이 절은 바퀴가 도는 작업을 포함한다. `AGENTS.md` 5절에 따라 사용자가 명시적으로
요청하고 바퀴를 띄운 상태에서만 수행한다.

1. `terminator -l vica_map` — 14칸이 뜨고 AUTO 칸만 실행되는지
2. `⑤ motor` 기동 후 `ros2 topic hz /wheel/odom` — 값이 나오는지
3. `⑧ slam` 기동 후 `ros2 topic hz /map`, RViz에서 지도가 자라는지
4. `ps -eo comm= | grep -i mdrobot` — 8절의 `mdrobot_can_ke` 실제 comm 확인
5. `motor` 칸을 두 번 눌러 guard가 중복을 막는지
6. `save` 칸으로 저장 → 세 파일과 `CURRENT_MAP` 확인
7. 터미네이터를 닫고 `terminator -l vica_drive` — `⑨` 칸 머리말이 새 지도를 가리키는지
8. 앱에서 지도 목록 동기화 → 새 지도가 보이고 캔버스에 그려지는지

7·8번이 이 설계의 진짜 성공 기준이다. 매핑에서 주행·앱까지 사람이 이름을 옮겨 적는
단계가 남아 있지 않아야 한다.

## 10. 남는 위험

- `mdrobot_can_ke`를 포함한 guard 3건은 실기에서 확인 전까지 `[미검증]`이다. 틀리면
  중복 방지가 여전히 꺼진 채로 남는다 — 지금보다 나빠지지는 않는다
- `slam` 칸과 `nav2` 칸의 배타 관계는 **문서와 안내문으로만** 막는다. 두 레이아웃을
  동시에 띄우면 여전히 충돌한다. 프로세스 수준 차단은 이 설계 범위 밖이다
- `CURRENT_MAP`은 `vica_ros2_ws` 저장소 안에 생긴다. 그 저장소의 브랜치를 바꾸면 값이
  달라지거나 사라질 수 있다. 없으면 `--map-id` 폴백으로 내려간다

## 11. 구현 결과 (2026-08-13)

설계대로 간 것이 대부분이지만 네 군데가 달라졌다. 이 절이 코드와 맞는 서술이고,
위쪽 본문은 8월 12일 시점의 설계 기록으로 남긴다.

**① 칸 수가 14 → 13이다.** `⑥ d455`·`⑦ imu`를 뺐다. 1.1절이 "EKF가 IMU를 융합하므로
필요"라고 적었는데, 실제로 띄울 때 `odom_topic:=/wheel/odom`을 넘기기로 정하면서 IMU가
지도에 닿는 유일한 통로가 끊겼다. `/imu/base_link`의 구독자는 `ekf.yaml` 하나뿐이고
Cartographer는 `use_imu_data = false`다. 그래서 두 칸은 CPU만 쓰고 지도에 기여하지
않는다. 12칸이 됐다가 아래 ②로 한 칸이 늘어 13칸이다.

**② `reset` 칸을 넣었다.** 설계가 빠뜨린 것이다. 중앙 E-stop 래치는 기동 직후 latched로
시작하고 `/motor/can_ok`가 원인의 하나다(`emergency_stop_node.py` 151행). 풀지 않으면
`teleop`을 눌러도 `/cmd_vel_safe`가 나가지 않아 로봇을 끌 수 없다 — 지도 작성 자체가
시작되지 않는다. `④ safety` → `⑤ motor` 다음에 와야 통과한다.

**③ 지도 id를 읽는 칸이 3개가 아니라 6개다.** 7절은 `⑨ nav2`·`⑩ mission`·`⑫ llm`만
꼽았다. 실제로는 `⑪ app`·`initpose`·`goto`도 지도에 매여 있었다. 특히
`vica_set_initial_pose.sh`는 `vica_map_0630`을 파일 안에 박아 두고 있어서, 0810 지도로
주행하면서 0630의 좌표를 초기 위치로 찍고 있었다. 이름이 양쪽 catalog에 다 있으면
오류도 나지 않는다 — 로봇이 엉뚱한 곳에 있다고 믿은 채 출발할 뿐이다.
`vica_goto.sh`는 이미 `VICA_MAP_ID`를 보고 있었으나 폴백이 `vica_map_0630` 고정이라
터미네이터 밖에서 단독 실행하면 같은 사고가 났다. 둘 다 `CURRENT_MAP`을 읽게 고쳤다.

**④ 목적지 catalog 유무를 함께 검사한다.** 설계에는 지도 파일 존재 검사만 있었다.
목적지는 `~/vica_data/destinations/<map_id>/destinations.yaml`로 지도마다 갈리는데,
**방금 그린 지도는 예외 없이 이 파일이 없다.** 그 상태에서 Mission Manager는 정상으로
뜬 채 모든 목적지 요청을 막으므로, 화면상 아무 이상이 없어 원인을 찾기 어렵다.
지도를 쓰는 여섯 칸이 시작할 때 지도·catalog를 함께 보고 없으면 경고한다.

`map_saver_cli`의 제한시간도 기본값 2초에서 120초로 올렸다. 2026-08-12 실기에서 노드
16개가 뜬 상태로 정확히 2.002초에 잘렸는데, 같은 순간 `/map`은 882x334로 정상이었다.
이 값은 "저장에 걸리는 시간"이 아니라 "포기하기까지 기다리는 시간"이라 크게 잡아도
정상일 때는 느려지지 않는다.

9.2절의 실기 검증은 그대로 남는다. 1번의 "14칸"만 13칸으로 읽는다.
