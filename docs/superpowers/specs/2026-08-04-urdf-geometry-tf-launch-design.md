# URDF 기하 보정과 TF 실행 경로 정리 설계

작성일: 2026-08-04
대상 저장소: `vica_ros2_ws` (구현), `VICA-team-workspace` (본 문서)
관련 계약: `docs/vica_robot_bringup_manual.md` ②단계,
`vica_nvblox_bringup/test/test_slice_height_contract.py`,
`vica_nav2/test/test_footprint_contract.py`

## 1. 문제

세 갈래이고, 뿌리는 하나다 — **좌표 정본이 여러 곳에 손으로 복사되어 있다.**

### 1.1 URDF 기구학 좌표 오류 3건

`VICA.xacro`의 조인트 좌표가 CAD·현장 실측과 어긋난다.

| 항목 | URDF | 실제 | 오차 |
|---|---|---|---|
| 구동륜 간격 | 0.293 m | 0.364 m | **7.1 cm 좁음** (한쪽당 3.55 cm) |
| 캐스터 휠 y | ±0.0695 | ±0.0795 | 10 mm 안쪽 |
| 차체·라이다 메시 z | −0.044 | −0.041 | 3 mm |

실물 주행에는 영향이 없었다. 오도메트리가 URDF가 아니라 `wheel_base_m` 파라미터를
읽고, Nav2 footprint는 STL XY 투영 실측을 직접 쓰기 때문이다. 그러나 URDF를 읽는
소비자(시뮬레이터·MoveIt·`ros2_control`)에게는 즉시 문제가 된다.

RViz로는 발견할 수 없는 종류의 버그다. `visual` origin이 `joint` origin을 정확히
상쇄해(좌측 구동륜 joint `y +0.1465`, visual `y −0.1465`) 메시가 CAD 위치에 그대로
그려지고, 오차 방향이 회전축(Y)과 같아 바퀴를 굴려도 형상이 변하지 않는다.
**같은 이유로 수정 후에도 RViz로는 검증할 수 없다.**

### 1.2 센서 TF 정본이 둘이다

`scripts/run_tf_vica.sh`가 `static_transform_publisher`로 `base_link → laser_frame`,
`base_link → camera_link`를 발행한다. 그 좌표가 `before_VICA.xacro` 시절 값이다.

| 프레임 | `run_tf_vica.sh` | 현재 `VICA.xacro` |
|---|---|---|
| `laser_frame` | `0.00995, 0, 0.319` | `0.185, 0, 0.192` |
| `camera_link` | `0.105, 0, 0.265` | `0.28683, 0, 0.130` |

이 스크립트를 참조하는 문서·코드는 0건이고 기동 매뉴얼도 언급하지 않는다.
`/home/ji_w/ros2_ws`를 source하는데 이 장비에 없는 경로다. 폐기된 파일이지만
남아 있는 한 URDF와 다른 위치에 센서 TF를 발행할 위험이 있다.

### 1.3 실주행 TF 경로가 GUI에 묶여 있다

기동 매뉴얼 ②단계가 실주행에서 `display.launch.py`를 띄우라고 지시하며
"RViz 확인 용도만이 아니라 TF 트리의 필수 구성이므로 생략하지 않는다"고 못박는다.
그런데 그 launch는 조건 없이 `joint_state_publisher_gui`를 함께 띄운다.

결과적으로 `/joint_states`가 **사람이 만지는 슬라이더 값**으로 발행된다. 아무도
만지지 않으므로 항상 `0.0`이다. 로봇이 실제로 굴러가도 TF상 바퀴는 영원히 0도다.

- 헤드리스 환경에서는 Qt가 없어 노드가 뜨지 않고 TF 트리가 끊긴다
- 실주행 내내 GUI 프로세스가 상주한다
- 정보가 없는데 있는 척한다

### 1.4 계약 테스트가 좌표를 각자 하드코딩한다

`body_center_z`의 값 `-0.044`가 xacro 밖 네 곳에 손으로 적혀 있다.

| 위치 | 성격 |
|---|---|
| `test_slice_height_contract.py:21` `COLLISION_Z_OFFSET` | **계산에 실제 사용** |
| `test_footprint_contract.py:18` | 주석 (x/y만 쓰므로 계산 무관) |
| `vica_nvblox_overrides.yaml:17` | 주석 |
| `nav2_params.yaml:247` | 주석 |

첫 번째가 위험하다. `body_center_z`를 0.041로 고쳐도 테스트는 계속 `-0.044`로
계산한다. 로봇 최고점이 0.860 → 0.863 m로 바뀌는데 `esdf_slice_max_height`가 0.9라
여유가 있어 **테스트는 통과한다.** 깨지면 알아차리지만, 안 깨지므로 계약이 3 mm
낙관적으로 어긋난 채 남는다.

## 2. 목표

1. `VICA.xacro`를 좌표의 **단일 정본**으로 만든다.
2. URDF를 읽는 소비자가 정본을 직접 참조하게 한다 — 값을 복사하지 않는다.
3. 실주행 TF 경로를 GUI 의존에서 분리한다.
4. **주행 거동은 변하지 않는다.** 달라졌다면 무언가 잘못된 것이다.

## 3. 확정된 기준값

추정치는 쓰지 않는다. 두 출처만 사용한다.

### 3.1 현장 실측

| 항목 | 값 | 근거 |
|---|---|---|
| 구동륜 간격 | 0.364 m | **줄자 실측** (바퀴 중심 사이). CAD 0.3618과 2.2 mm 차이로 가장 근접하다 |
| `laser_frame` 절대 높이 | 0.382 m | `base_link_height 0.19 + laser_z 0.192` |
| `camera_link` 절대 높이 | 0.320 m | `0.19 + 0.130` |

#### 3.1.1 URDF의 0.364와 코드의 `wheel_base_m 0.37`은 다른 값이다 — 통일하지 말 것

세 숫자가 나란히 존재하며, **서로 다른 것을 재므로 같을 필요가 없다.**

| 값 | 무엇을 재나 | 사는 곳 |
|---|---|---|
| 0.3618 | CAD 도면상 바퀴 중심 간격 | 설계 |
| **0.364** | 실물 바퀴 중심 간격 (줄자 실측) | **URDF (기하)** |
| **0.370** | 오도메트리 유효 트레드 | **`wheel_base_m` (보정 상수)** |

차동구동에서 `wheel_base_m`은 자로 잰 거리가 아니라 **회전 시험으로 맞춘 보정
상수**다. 타이어 폭이 67.8 mm로 두껍고 접지면에서 미끄러지므로 로봇이 실제로 도는
반경은 바퀴 중심 간격과 다르다. 오도메트리만 6 mm 큰 현재 상태는 캘리브레이션
결과로 자연스럽다.

URDF는 **바퀴가 물리적으로 있는 자리**를 담는다. 시뮬레이터가 물리 바퀴를 놓는
좌표이자 TF가 "바퀴가 여기 있다"고 알리는 값이다. 여기에 보정 상수 0.370을 넣으면
실물에 없는 자리에 바퀴를 그리게 된다.

> **원본 artifact 문서의 처방은 절반만 맞다.** "URDF가 0.293이니 0.37로 고쳐라"에서
> 진단(0.293은 CAD와 7 cm 벌어져 명백히 틀림)은 옳지만, 처방은 부정확하다.
> URDF에 넣을 값은 오도메트리 보정 상수가 아니라 실측 기하값이다.

`wheel_base_m`을 0.364로 바꾸면 회전각이 1.65% 크게 계산되어 **주행 거동이 실제로
달라진다.** 이번 작업의 전제("거동은 바뀌지 않는다")와 정면으로 충돌하므로 건드리지
않는다.

### 3.2 CAD STL 실측

메시 6개가 하나의 공통 CAD 프레임에 있고, 그 원점은 `base_link + (0, 0, −0.041)`이다.

검산 — 각 메시가 놓이는 base_link 기준 z:

```
base_link    : −0.044                          ← 어긋남
left_wheel   : −0.125 + 0.084          = −0.041
right_wheel  : −0.125 + 0.084          = −0.041
caster steer : −0.0825 + 0.0415        = −0.041
caster wheel : −0.0825 −0.0655 + 0.107 = −0.041
laser_frame  :  0.192 + (−0.236)       = −0.044 ← 어긋남
```

메시 6개 중 4개가 이미 `−0.041`에 있다. **`base_link`와 `laser_frame`만 어긋나 있으며,
정답 오프셋은 `−0.041`이다.** 구동륜 메시 바닥도 이를 뒷받침한다 —
CAD `z −0.1490` → 절대 `0.19 − 0.041 − 0.149 = 0.000`, 정확히 지면이다.

| 메시 | CAD 중심 (X, Y) | 치수 |
|---|---|---|
| 구동륜 좌 | +0.154, +0.1814 | r 0.0650 · w 0.0678 |
| 구동륜 우 | +0.154, −0.1804 | r 0.0650 · w 0.0678 |
| 캐스터 steer | −0.2220, ±0.0845 | — |
| 캐스터 휠 | −0.2520, ±0.0795 | r 0.0375 · w 0.0400 |

## 4. 설계 원칙과 근거

| 결정 | 근거 |
|---|---|
| `VICA.xacro`의 property가 좌표 정본 | 오류 3건 전부 손으로 적은 상수에서 나왔다 |
| 소비자는 정본을 파싱해 읽는다 | 값 복사가 1.4의 어긋남을 만들었다 |
| 실주행 launch와 확인용 launch를 분리 | 실주행에 GUI·RViz가 딸려올 이유가 없다 |
| `joint_state_publisher`(비GUI) 사용 | 헤드리스 동작 + 바퀴 메시 유지를 동시에 만족 |
| `run_tf_vica.sh` 삭제 | 살려두면 이중 정본이 되어 같은 어긋남이 재발한다 |
| 캐스터 이름 변경은 보류 | USD 재import가 전제인데 Isaac이 이번 범위 밖이다 |
| 커밋을 성격별로 분리 | 좌표 변경과 구조 변경이 섞이면 원인을 가릴 수 없다 |
| 실물 코드는 수정하지 않는다 | `wheel_base_m 0.37`은 오도메트리 보정 상수이고 URDF의 0.364는 실측 기하다. 서로 다른 값이므로 통일 대상이 아니다 (3.1.1) |

### 4.1 한계 (명시)

이 작업은 URDF와 그 소비자만 다룬다. **주행 파이프라인은 URDF를 읽지 않으므로 수정
전후 거동이 동일해야 한다.** 오도메트리는 `wheel_base_m` 파라미터, Nav2 footprint는
`nav2_params.yaml`의 STL 실측 하드코딩, EKF·AMCL은 `base_footprint` 기준이다.

`camera_optical_frame`은 실물에서 당장 쓰이지 않는다. RealSense 드라이버가 자체
optical 프레임을 발행하기 때문이다. 정본을 하나로 유지하려고 미리 넣는다.

Isaac Sim 자산(USD, `add_drive_odom_graphs.py`)은 이 저장소·이 장비에 없어 검증할 수
없다. 9절에 인수인계 사항으로 남긴다.

## 5. 변경 상세

### 5.1 수정 A — 구동륜 Y (기구학, 우선순위 최상)

`visual`과 `collision`의 origin을 **함께** 수정한다(두 블록이 같은 값을 갖는다).

| 대상 | 현재 | 수정 |
|---|---|---|
| `left_wheel_joint` origin | `0.154 0.1465 -0.125` | `0.154 0.182 -0.125` |
| `right_wheel_joint` origin | `0.154 -0.1465 -0.125` | `0.154 -0.182 -0.125` |
| `left_wheel_1` visual+collision | `-0.154 -0.1465 0.084` | `-0.154 -0.182 0.084` |
| `right_wheel_1` visual+collision | `-0.154 0.1465 0.084` | `-0.154 0.182 0.084` |

visual을 joint의 반대값으로 유지하면 메시는 CAD 위치(좌 +0.1814, 우 −0.1804)에 그대로
남는다. 실측 반폭 0.182와의 차이는 좌 0.6 mm·우 1.6 mm로 CAD 공차 범위다.

### 5.2 수정 B — 캐스터 휠 Y

steer 조인트(`−0.222`, `±0.0845`)는 **정확하다.** 휠 조인트만 틀렸다.

| 대상 | 현재 | 수정 |
|---|---|---|
| `front_left_caster_wheel_joint` origin | `-0.03 -0.015 -0.0655` | `-0.03 -0.005 -0.0655` |
| `front_right_caster_wheel_joint` origin | `-0.03 0.015 -0.0655` | `-0.03 0.005 -0.0655` |
| `front_left_caster_wheel_1` visual+collision | `0.252 -0.0695 0.107` | `0.252 -0.0795 0.107` |
| `front_right_caster_wheel_1` visual+collision | `0.252 0.0695 0.107` | `0.252 0.0795 0.107` |

검산: steer `+0.0845` + wheel `−0.005` = `+0.0795` = CAD 값.

### 5.3 수정 C — 차체·라이다 메시 정렬 (3 mm)

| 대상 | 현재 | 수정 |
|---|---|---|
| `body_center_z` (property) | `0.044` | `0.041` |
| `laser_frame` visual+collision | `-0.185 -0.0 -0.236` | `-0.185 -0.0 -0.233` |
| `base_link` inertial origin z | `0.03206562657816282` | `0.03506562657816282` |

관성 원점은 메시와 동일하게 +3 mm 이동시켜 정합을 유지한다.

### 5.4 수정 D — `camera_optical_frame` 추가

`</robot>` 직전에 넣는다.

```xml
<!-- REP-103: +Z forward, +X right, +Y down -->
<link name="camera_optical_frame"/>
<joint name="camera_optical_joint" type="fixed">
  <origin xyz="0 0 0" rpy="-${pi/2} 0 -${pi/2}"/>
  <parent link="camera_link"/>
  <child  link="camera_optical_frame"/>
</joint>
```

`camera_color_optical_frame`·`camera_depth_optical_frame`은 **넣지 않는다.**
RealSense 드라이버가 동일 이름으로 발행하여 TF 중복 충돌이 발생한다.

### 5.5 수정 E — 좌표 상수 파라미터화

y 계열과 `body_center_z` 연동 z를 property로 묶는다.

```xml
<xacro:property name="wheel_separation" value="0.364"/>   <!-- 줄자 실측. wheel_base_m과 별개 (3.1.1) -->
<xacro:property name="wheel_y"          value="${wheel_separation / 2}"/>
<xacro:property name="caster_steer_y"   value="0.0845"/>
<xacro:property name="caster_y"         value="0.0795"/>
```

z 쪽은 `body_center_z`에 실제로 연동되는 곳만 수식으로 바꾼다. 3.2절 검산대로 구동륜·
캐스터 메시는 이미 `−0.041` 정합이므로 손댈 필요가 없다.

| 대상 | 수식 | 이유 |
|---|---|---|
| `base_link` visual+collision z | `-${body_center_z}` | 이미 수식 (유지) |
| `laser_frame` visual+collision z | `-${laser_z + body_center_z}` | 현재 하드코딩 `-0.236` |
| 구동륜·캐스터 visual z | **변경 없음** | 이미 `−0.041` 정합 |

원칙은 **"같은 수를 두 번 적지 않는다"**이다. 위 두 곳만 바꾸면 앞으로
`body_center_z` 하나로 전체 메시 정렬이 따라온다.

### 5.6 계약 테스트를 정본 참조로

`test_slice_height_contract.py`가 `VICA.xacro`에서 `body_center_z`와
`base_link_height`를 파싱해 쓰도록 바꾼다. 나머지 세 곳(주석)은 값을 갱신한다.

### 5.7 실주행 launch 분리

```
robot_state.launch.py   실주행 — robot_state_publisher + joint_state_publisher
display.launch.py       확인용 — 위 + joint_state_publisher_gui + rviz2 (현행 유지)
```

`display.launch.py`의 기본값을 바꾸면 매뉴얼과 팀 습관이 깨지므로 새 launch를 만든다.
기동 매뉴얼 ②단계를 `robot_state.launch.py`로 교체한다.

`joint_state_publisher_gui`는 `joint_state_publisher`를 의존성으로 포함하고 Qt 창만
얹은 래퍼다. 발행 로직이 동일하므로 `/joint_states` 내용과 발행량이 같다.
`source_list`·`rate`·`zeros` 등 파라미터도 그대로 쓸 수 있다.

**2026-08-04 노트북에서 `DISPLAY`를 지우고 검증했다** (기하 수정 전, 현행 URDF 기준).

```
/joint_state_publisher, /robot_state_publisher  기동 성공
/joint_states  name: [left_wheel_joint, right_wheel_joint,
                      front_left_caster_wheel_joint, front_right_caster_wheel_joint,
                      front_right_caster_steer_joint, front_left_caster_steer_joint]
               position: [0.0, 0.0, 0.0, ...]
base_link → left_wheel_1  Translation: [0.154, 0.146, -0.125]   ← 현행 0.1465
```

헤드리스에서 조인트 6개가 전부 잡히고 바퀴 TF가 정상 발행된다. 수정 후에는 같은
자리에 `0.182`가 나와야 한다(8.2절).

### 5.8 `run_tf_vica.sh` 삭제

git 이력에 남으므로 복구는 언제든 가능하다.

## 6. 영향 분석

### 6.1 TF 변화

| TF | 변화 | 읽는 곳 |
|---|---|---|
| `base_footprint → base_link` | **불변** (`0.19`) | — |
| `base_link → laser_frame` | **불변** (`0.185/0/0.192`) | `pose_bootstrap_node.py:298` |
| `base_link → camera_link` | **불변** | `vica_nvblox.launch.py:56` |
| `map → base_footprint` | **불변** | `robot_health_monitor:271`, `mission_manager:724` |
| `base_link → left/right_wheel_1` | y `±0.1465` → `±0.182` | **없음** |
| 캐스터 휠 | y `∓0.015` → `∓0.005` | **없음** |
| `camera_link → camera_optical_frame` | 신규 | 없음 (이름 사용처 0건) |

바퀴·캐스터 프레임을 참조하는 코드는 워크스페이스에 0건이다. TF lookup을 하는 노드
4곳은 전부 다른 프레임을 본다.

`/joint_states`는 **명령이 아니라 상태**다. 구동 경로
(`/cmd_vel_req` → Safety → `/cmd_vel_safe` → motor node → CAN)에 등장하지 않으므로,
5.7의 변경은 주행 기능과 원리적으로 무관하다.

### 6.2 이름 참조처 (이번엔 건드리지 않음)

캐스터 이름 변경을 보류했으므로 아래는 전부 현행 유지한다. 나중에 수정 F를 할 때
**artifact 문서의 영향 범위 표에 빠져 있는 항목**이므로 여기 기록해 둔다.

| 파일 | `front_*caster` 참조 | artifact 문서 표 |
|---|---|---|
| `urdf/VICA.xacro` | 22곳 | 있음 |
| `urdf/VICA.gazebo` | 4곳 | **누락** |
| `urdf/before_VICA.xacro` | 22곳 | **누락** |
| `meshes/front_*_caster_*.stl` | 파일명 4개 | **누락** |
| `rviz/urdf.rviz` | 12줄 | 있음 |

`urdf.rviz`는 `feat/home-return`이 이미 수정 중이므로 이번에 건드리면 불필요한 충돌이
생긴다.

## 7. 커밋 구성

순서가 중요하다. 계약 테스트를 **먼저** 정본 참조로 바꿔야 기하를 고치는 순간 계약이
자동으로 따라온다.

| # | 커밋 | 검증 조건 |
|---|---|---|
| 1 | `test(nvblox): slice 계약이 VICA.xacro를 정본으로 읽게 한다` | 동작 무변화, 현재 값으로 통과 |
| 2 | `fix(urdf): 구동륜·캐스터 조인트 기하를 CAD·실측에 맞춘다` | A·B·C, 순수 좌표 |
| 3 | `refactor(urdf): 좌표 상수를 property로 묶는다` | **xacro 출력이 2번과 완전 동일** |
| 4 | `feat(urdf): camera_optical_frame을 추가한다` | 링크 11개 |
| 5 | `refactor(description): 실주행 TF launch를 GUI에서 분리한다` | 헤드리스 기동 |
| 6 | `chore(scripts): 옛 좌표의 run_tf_vica.sh를 지운다` | — |

3번의 검증은 순수 리팩터임을 증명한다. `diff`가 비어야 통과다.

## 8. 검증

노트북에서 전부 가능하다. 실기가 필요 없다.

### 8.1 문법·범위

```bash
xacro src/vica_description/urdf/VICA.xacro > /tmp/vica_after.urdf && echo "XACRO OK"
check_urdf /tmp/vica_after.urdf          # 링크 11개, 루트 base_footprint
diff /tmp/vica_before.urdf /tmp/vica_after.urdf
```

### 8.2 TF 수치 — 핵심

`robot_state.launch.py` 기동 후 `tf2_echo`로 대조한다. 캐스터 steer 각도 0 기준.

| `tf2_echo` | 기대 translation |
|---|---|
| `base_link → left_wheel_1` | `0.154, 0.182, -0.125` |
| `base_link → right_wheel_1` | `0.154, -0.182, -0.125` |
| `base_link → front_left_caster_wheel_1` | `-0.252, 0.0795, -0.148` |
| `base_footprint → laser_frame` | `0.185, 0.0, 0.382` |
| `base_footprint → camera_link` | `0.28683, 0.0, 0.320` |

**최종 확인:** 좌·우 구동륜 y 차이 = `0.182 − (−0.182)` = **0.364** = 줄자 실측값.
`wheel_base_m 0.37`과 일치하지 **않는 것이 정상이다** — 3.1.1절 참조.

### 8.3 계약 테스트

```bash
pytest src/vica_nvblox_bringup/test/test_slice_height_contract.py
pytest src/vica_nav2/test/test_footprint_contract.py
```

### 8.4 RViz 회귀 검사

수정 A·B는 RViz에서 **보이지 않는다.** RViz의 역할은 "메시를 실수로 옮기지
않았는지" 확인하는 회귀 검사다.

- 바퀴 4개가 차체 대비 이전과 같은 위치에 보인다 — 움직였다면 visual origin 수정 오류
- 바퀴가 지면에 닿아 있고 파묻히지 않는다
- `joint_state_publisher_gui`로 돌려도 축을 벗어나 흔들리지 않는다
- 차체·라이다가 이전보다 3 mm 위로 올라갔다
- `camera_optical_frame` 축이 `camera_link`와 다른 방향(전방 = 파랑 Z)을 가리킨다

### 8.5 launch

- `robot_state.launch.py`를 `DISPLAY` 없이 기동 → 노드 2개 정상
- `/joint_states`에 조인트 6개
- RViz를 별도로 붙였을 때 바퀴 메시가 보인다

### 8.6 완료 기준

- `check_urdf` 통과, `diff`에 의도하지 않은 변경 없음
- 모든 `tf2_echo` 기대값 일치
- 좌우 구동륜 y 차이 = 0.364
- 커밋 3의 순수 리팩터 `diff`가 비어 있다
- 계약 테스트 전부 통과
- `colcon build --packages-select vica_description` 성공
- 기동 매뉴얼 ②단계가 갱신되어 있다

## 9. 범위 밖 · 인수인계

### 9.1 Isaac 이식

이 작업 완료 후 Isaac 워크스페이스에 **좌표만** 이식한다. 아래는 Isaac 전용으로 유지한다.

- primitive collision (box / cylinder) — 실물은 STL 메시 유지
- 구동륜 `dynamics` · `limit`
- 캐스터 collision 반지름 **0.042** — CAD상 캐스터가 4.5 mm 떠 있어 접지 보정이
  필요하다. 0.0375를 그대로 쓰면 PhysX가 로봇을 뒤로 0.635° 기울여 세운다
- `add_drive_odom_graphs.py`의 `WHEEL_DISTANCE`: `0.293` → **`0.364`**

**마지막 항목을 빠뜨리면 수정 A가 무의미해진다.** USD와 컨트롤러가 모두 0.364여야 한다.
시뮬레이터는 물리 엔진이 바퀴를 직접 굴리므로 실물의 보정 상수 0.37이 아니라 기하값을
쓴다. 실물과 값이 다른 이유는 3.1.1절에 있다.

`left_wheel_joint`·`right_wheel_joint`는 Isaac Action Graph에 하드코딩되어 있으므로
**절대 이름을 바꾸지 않는다.**

### 9.2 캐스터 이름 변경 (수정 F)

캐스터 링크·조인트가 전부 `front_`로 시작하지만 좌표상 모두 차체 뒤쪽이다
(캐스터 `−0.252`, 구동륜 `+0.154`). CAD 부품명을 그대로 export한 흔적이다.

USD의 prim·조인트 이름은 import 시점의 URDF 이름으로 고정되므로, **USD 재import와 같은
세션에서 처리한다.** 기하 수정으로 어차피 재import하므로 그때가 적기다.
영향 범위는 6.2절에 정리해 두었다.

### 9.3 엔코더 기반 `/joint_states`

현재 `/joint_states`는 기본값 0으로만 채워진다. `encoder_feedback`이 이미 CAN에서
tick을 읽으므로(`ticks_per_rev = 61.2`) 실제 바퀴 각도를 만들 재료는 있다.

`joint_state_publisher`의 `source_list` 파라미터를 쓰면 부분 발행자가 아는 관절만
채우고 나머지는 자동 보충된다 — 캐스터 4개는 센서가 없어도 문제가 되지 않는다.

```
encoder_feedback → /wheel_joint_states (구동륜 2개)
                        ↓ source_list
              joint_state_publisher → /joint_states (6개 전부)
```

**지금은 하지 않는다.** 바퀴 TF의 소비자가 0건이라 부하만 늘기 때문이다. Isaac과
실물을 나란히 대조하거나 `ros2_control`로 전환할 때 launch에 `source_list` 한 줄을
추가하면 된다. 이번 5.7의 구조가 그대로 발판이 된다.

### 9.4 ROS 1 잔재 파일

`vica_description/launch/`에 ROS 1 문법 파일이 남아 있다 — `display.launch`,
`controller.launch`, `gazebo.launch`(`type=`, `pkg="rviz"`). ROS 2에서 실행되지 않는다.
`urdf/VICA.trans`도 인코딩이 깨진 CAD export 잔재이며 어디서도 include되지 않는다.

동작에 영향이 없어 이번 범위에서 제외한다. 패키지 정리를 할 때 함께 다룬다.
