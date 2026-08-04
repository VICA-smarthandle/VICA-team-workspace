# URDF 기하 보정과 TF 실행 경로 정리 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `VICA.xacro`를 로봇 좌표의 단일 정본으로 만들고, 실주행 TF 경로를 GUI 의존에서 분리한다.

**Architecture:** 좌표를 xacro property로 모으고, 그 값을 복사해 쓰던 계약 테스트가 정본을 직접 파싱하게 바꾼다. 실주행용 launch를 새로 만들어 `joint_state_publisher_gui`(Qt 필요)를 `joint_state_publisher`(Qt 불필요)로 교체하고, 옛 좌표를 발행하던 스크립트를 지운다.

**Tech Stack:** ROS 2 Humble, xacro, `robot_state_publisher`, `joint_state_publisher`, pytest, colcon

설계 근거: `docs/superpowers/specs/2026-08-04-urdf-geometry-tf-launch-design.md`

## Global Constraints

- **실물 코드는 수정하지 않는다.** `encoder_feedback.py`·`encoder.yaml`·`mdrobot_can_keyboard_knob_node.py`의 `wheel_base_m = 0.37`은 **오도메트리 유효 트레드**(회전 시험으로 맞춘 보정 상수)이고, URDF에 넣을 0.364는 **줄자로 잰 실측 기하**다. 서로 다른 것을 재는 값이므로 **통일 대상이 아니다.** 스펙 3.1.1절에 근거가 있다.
- **`wheel_base_m`을 0.364로 바꾸지 않는다.** 바꾸면 오도메트리 회전각이 1.65% 달라져 주행 거동이 변한다. 아래 "주행 거동은 바뀌면 안 된다"와 충돌한다.
- **주행 거동은 바뀌면 안 된다.** 실물 오도메트리는 URDF를 읽지 않는다. 달라졌다면 무언가 잘못된 것이다.
- **`left_wheel_joint`·`right_wheel_joint` 이름을 바꾸지 않는다.** Isaac Action Graph에 하드코딩되어 있다.
- **캐스터 이름 `front_*`를 `rear_*`로 바꾸지 않는다.** USD 재import가 전제이며 이번 범위 밖이다.
- **다음 파일은 건드리지 않는다:** `urdf/VICA.gazebo`, `urdf/before_VICA.xacro`, `urdf/VICA.trans`, `rviz/urdf.rviz`, `meshes/` 전체, `launch/display.launch`, `launch/controller.launch`, `launch/gazebo.launch`.
  `urdf.rviz`는 `feat/home-return` 브랜치가 이미 수정 중이라 손대면 불필요한 충돌이 생긴다.
- 커밋 메시지는 한국어 본문으로 쓰고 `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`로 끝낸다.
- 모든 pytest는 `vica_ros2_ws/src`에서 실행한다. 테스트가 `Path(__file__).parents[2]`로 소스 트리를 찾으므로 다른 위치에서 실행하면 경로를 잃는다.

---

## 시작 전 준비

`vica_ros2_ws` 본체는 `feat/home-return`을 체크아웃 중이다(홈 복귀 작업 진행 중, 미머지 커밋 2개). 그 작업을 건드리지 않기 위해 **worktree에서 작업한다.**

- [ ] **준비 1: 최신 상태 확인**

```bash
cd /home/msk/VICA-smarthandle/vica_ros2_ws
git fetch origin
git status -sb
```

기대: `feat/home-return`이 체크아웃되어 있고 작업트리가 깨끗하다.

- [ ] **준비 2: worktree 생성**

```bash
mkdir -p /mnt/ssd/workspaces/tmp
cd /home/msk/VICA-smarthandle/vica_ros2_ws
git worktree add -b fix/urdf-geometry /mnt/ssd/workspaces/tmp/urdf-geometry dev
cd /mnt/ssd/workspaces/tmp/urdf-geometry
git status -sb
```

기대: `## fix/urdf-geometry`, 작업트리 깨끗.

**이후 모든 Task는 `/mnt/ssd/workspaces/tmp/urdf-geometry`에서 수행한다.**
Task 7만 예외로 `/home/msk/VICA-smarthandle`에서 한다.

- [ ] **준비 3: 수정 전 기준 URDF 확보**

```bash
source /opt/ros/humble/setup.bash
cd /mnt/ssd/workspaces/tmp/urdf-geometry
xacro src/vica_description/urdf/VICA.xacro > /tmp/vica_before.urdf
grep -c "link name" /tmp/vica_before.urdf
```

기대: `10` (링크 10개).

---

## Task 1: 계약 테스트를 정본 참조로 바꾼다

`test_slice_height_contract.py`가 `COLLISION_Z_OFFSET = -0.044`를 하드코딩하고 있다. Task 2에서 `body_center_z`를 0.041로 고쳐도 이 테스트는 계속 `-0.044`로 계산해 **통과하면서 조용히 어긋난다.** 기하를 고치기 전에 먼저 정본을 읽게 만든다.

**Files:**
- Modify: `src/vica_nvblox_bringup/test/test_slice_height_contract.py:16-24, 52-63`

**Interfaces:**
- Produces: `_xacro_property(name: str) -> float` — `VICA.xacro`의 `<xacro:property>` 값을 float로 돌려준다. 없으면 `AssertionError`.

- [ ] **Step 1: 현재 테스트가 통과하는지 확인 (기준선)**

```bash
cd /mnt/ssd/workspaces/tmp/urdf-geometry/src
python3 -m pytest vica_nvblox_bringup/test/test_slice_height_contract.py -q
```

기대: `9 passed`

- [ ] **Step 2: 하드코딩 상수를 파서로 교체**

`src/vica_nvblox_bringup/test/test_slice_height_contract.py`의 16~24행을 찾는다.

```python
# base_link.stl은 mm 단위이고 URDF에서 scale 0.001로 쓰인다.
STL_SCALE = 0.001
# URDF collision origin이 xyz="0 0 -0.044"라 STL z에서 이만큼 내려간 값이
# base_link 좌표다.
COLLISION_Z_OFFSET = -0.044
# base_footprint -> base_link (VICA.xacro base_link_height). 바닥 기준으로
# 환산하려면 이만큼 더한다. 실측 TF와도 일치한다.
BASE_LINK_HEIGHT = 0.19
```

아래로 바꾼다.

```python
# base_link.stl은 mm 단위이고 URDF에서 scale 0.001로 쓰인다.
STL_SCALE = 0.001
```

그리고 파일 상단 import에 `re`를 추가한다. 현재 import 블록은 이렇다.

```python
import struct
from pathlib import Path

import pytest
import yaml
```

아래로 바꾼다.

```python
import re
import struct
from pathlib import Path

import pytest
import yaml
```

- [ ] **Step 3: 파서 함수 추가**

`_repo_src()` 정의 바로 아래에 넣는다.

```python
def _xacro_property(name):
    """VICA.xacro의 xacro:property 값을 읽는다.

    좌표 정본은 URDF 하나다. 여기서 값을 복사해 두면 URDF가 바뀔 때 이 계약이
    조용히 어긋난다. 실제로 body_center_z가 0.044로 네 곳에 흩어져 있었다.
    """
    path = _repo_src() / 'vica_description' / 'urdf' / 'VICA.xacro'
    text = path.read_text(encoding='utf-8')
    match = re.search(
        rf'<xacro:property\s+name="{name}"\s+value="([^"]+)"',
        text,
    )
    assert match is not None, (
        f'VICA.xacro에서 xacro:property "{name}"을 찾지 못했다.'
        ' URDF 구조가 바뀌었다면 이 계약도 다시 봐야 한다'
    )
    return float(match.group(1))
```

- [ ] **Step 4: 계산부가 파서를 쓰게 수정**

`_robot_top_from_floor()`의 마지막 줄을 찾는다.

```python
    return max_z + COLLISION_Z_OFFSET + BASE_LINK_HEIGHT
```

아래로 바꾼다.

```python
    # collision origin이 xyz="0 0 -body_center_z"이므로 STL z에서 그만큼 내려간
    # 값이 base_link 좌표다. 바닥 기준으로 환산하려면 base_link_height를 더한다.
    return (
        max_z
        - _xacro_property('body_center_z')
        + _xacro_property('base_link_height')
    )
```

- [ ] **Step 5: 테스트 실행 — 동작이 변하지 않았는지 확인**

```bash
cd /mnt/ssd/workspaces/tmp/urdf-geometry/src
python3 -m pytest vica_nvblox_bringup/test/test_slice_height_contract.py -q
```

기대: `9 passed`. 아직 URDF를 고치지 않았으므로 `body_center_z`는 0.044이고 계산 결과가 이전과 같다.

- [ ] **Step 6: 파서가 실제로 정본을 읽는지 확인**

```bash
cd /mnt/ssd/workspaces/tmp/urdf-geometry/src
python3 -c "
import sys; sys.path.insert(0, 'vica_nvblox_bringup/test')
from test_slice_height_contract import _xacro_property, _robot_top_from_floor
print('body_center_z   :', _xacro_property('body_center_z'))
print('base_link_height:', _xacro_property('base_link_height'))
print('로봇 최고점      :', round(_robot_top_from_floor(), 4))
"
```

기대:
```
body_center_z   : 0.044
base_link_height: 0.19
로봇 최고점      : 0.86
```

- [ ] **Step 7: 커밋**

```bash
cd /mnt/ssd/workspaces/tmp/urdf-geometry
git add src/vica_nvblox_bringup/test/test_slice_height_contract.py
git diff --cached --check
git commit -m "$(cat <<'EOF'
test(nvblox): slice 계약이 VICA.xacro를 정본으로 읽게 한다

COLLISION_Z_OFFSET = -0.044가 URDF와 별개로 하드코딩되어 있었다. body_center_z를
고쳐도 이 테스트는 옛 값으로 계산해 통과하므로, 계약이 깨지지 않은 채 조용히
어긋난다. 값을 복사하는 대신 정본을 파싱한다.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: 구동륜·캐스터 조인트 기하를 CAD·실측에 맞춘다

수정 A·B·C를 좌표 숫자로 직접 적용한다. property화는 Task 3에서 한다 — 좌표 변경과 구조 변경을 한 커밋에 섞으면 무엇이 원인인지 가릴 수 없다.

**Files:**
- Modify: `src/vica_description/urdf/VICA.xacro` (7, 26, 52, 59, 73, 80, 94, 101, 115, 122, 178, 185, 204, 211, 218, 225행)
- Modify: `src/vica_nav2/test/test_footprint_contract.py:18-19` (주석)
- Modify: `src/vica_nav2/config/nav2_params.yaml:247` (주석)
- Modify: `src/vica_nvblox_bringup/config/vica_nvblox_overrides.yaml:16-17, 23` (주석)

- [ ] **Step 1: 수정 A — 구동륜 Y (joint)**

`VICA.xacro` 204행:
```xml
  <origin xyz="0.154 0.1465 -0.125" rpy="0 0 0"/>
```
→
```xml
  <origin xyz="0.154 0.182 -0.125" rpy="0 0 0"/>
```

211행:
```xml
  <origin xyz="0.154 -0.1465 -0.125" rpy="0 0 0"/>
```
→
```xml
  <origin xyz="0.154 -0.182 -0.125" rpy="0 0 0"/>
```

- [ ] **Step 2: 수정 A — 구동륜 Y (visual + collision)**

`left_wheel_1`의 visual(52행)과 collision(59행), 두 곳 모두:
```xml
      <origin xyz="-0.154 -0.1465 0.084" rpy="0 0 0"/>
```
→
```xml
      <origin xyz="-0.154 -0.182 0.084" rpy="0 0 0"/>
```

`right_wheel_1`의 visual(73행)과 collision(80행), 두 곳 모두:
```xml
      <origin xyz="-0.154 0.1465 0.084" rpy="0 0 0"/>
```
→
```xml
      <origin xyz="-0.154 0.182 0.084" rpy="0 0 0"/>
```

visual을 joint의 반대값으로 유지하면 메시는 CAD 위치(좌 +0.1814, 우 −0.1804)에 그대로
남는다. 실측 반폭 0.182와의 차이는 좌 0.6 mm·우 1.6 mm로 CAD 공차 범위다.

- [ ] **Step 3: 수정 B — 캐스터 휠 Y (joint)**

218행:
```xml
  <origin xyz="-0.03 -0.015 -0.0655" rpy="0 0 0"/>
```
→
```xml
  <origin xyz="-0.03 -0.005 -0.0655" rpy="0 0 0"/>
```

225행:
```xml
  <origin xyz="-0.03 0.015 -0.0655" rpy="0 0 0"/>
```
→
```xml
  <origin xyz="-0.03 0.005 -0.0655" rpy="0 0 0"/>
```

steer 조인트(`-0.222`, `±0.0845`)는 정확하므로 건드리지 않는다.

- [ ] **Step 4: 수정 B — 캐스터 휠 Y (visual + collision)**

`front_left_caster_wheel_1`의 visual(94행)과 collision(101행), 두 곳 모두:
```xml
      <origin xyz="0.252 -0.0695 0.107" rpy="0 0 0"/>
```
→
```xml
      <origin xyz="0.252 -0.0795 0.107" rpy="0 0 0"/>
```

`front_right_caster_wheel_1`의 visual(115행)과 collision(122행), 두 곳 모두:
```xml
      <origin xyz="0.252 0.0695 0.107" rpy="0 0 0"/>
```
→
```xml
      <origin xyz="0.252 0.0795 0.107" rpy="0 0 0"/>
```

- [ ] **Step 5: 수정 C — body_center_z와 라이다 메시**

7행:
```xml
<xacro:property name="body_center_z" value="0.044" />
```
→
```xml
<xacro:property name="body_center_z" value="0.041" />
```

`laser_frame`의 visual(178행)과 collision(185행), 두 곳 모두:
```xml
      <origin xyz="-0.185 -0.0 -0.236" rpy="0 0 0"/>
```
→
```xml
      <origin xyz="-0.185 -0.0 -0.233" rpy="0 0 0"/>
```

26행 `base_link` inertial origin의 z만 +3 mm:
```xml
    <origin xyz="0.004031215194176557 3.002726997808124e-17 0.03206562657816282" rpy="0 0 0"/>
```
→
```xml
    <origin xyz="0.004031215194176557 3.002726997808124e-17 0.03506562657816282" rpy="0 0 0"/>
```

구동륜·캐스터 메시 z는 이미 `-0.041` 정합이므로 건드리지 않는다.

- [ ] **Step 6: 다른 파일의 주석 3곳 갱신**

`-0.044`가 주석으로 세 곳에 더 있다. 기하를 바꾸는 순간 거짓이 되므로 같은 커밋에서 고친다.
(계산에 쓰이는 `test_slice_height_contract.py`는 Task 1에서 이미 처리했다.)

**(1) `src/vica_nav2/test/test_footprint_contract.py` 18~19행**

```python
# URDF의 collision origin이 xyz="0 0 -0.044"로 z만 오프셋이므로
# STL의 x/y는 base_link 좌표와 직접 대응한다.
```
→
```python
# URDF의 collision origin이 xyz="0 0 -body_center_z"로 z만 오프셋이므로
# STL의 x/y는 base_link 좌표와 직접 대응한다. z 값이 바뀌어도 이 대응은 유지된다.
```

**(2) `src/vica_nav2/config/nav2_params.yaml` 247행**

```yaml
        # URDF collision origin이 z만 오프셋(xyz="0 0 -0.044")이라 STL x/y는 base_link
```
→
```yaml
        # URDF collision origin이 z만 오프셋(xyz="0 0 -body_center_z")이라 STL x/y는 base_link
```

**(3) `src/vica_nvblox_bringup/config/vica_nvblox_overrides.yaml` 16~17행**

```yaml
#   로봇 최고점 0.86 m : base_link.stl 실측 z 상한 0.714(STL 로컬)에 collision
#                        origin -0.044와 base_footprint->base_link +0.190을 적용한 값
```
→
```yaml
#   로봇 최고점 0.863 m: base_link.stl 실측 z 상한 0.714(STL 로컬)에 collision
#                        origin -0.041과 base_footprint->base_link +0.190을 적용한 값
```

같은 파일 23행의 `0.9는 로봇 최고점(0.86)에 4 cm 여유를 둔 값이다`도 함께 고친다.

```yaml
# 0.9는 로봇 최고점(0.86)에 4 cm 여유를 둔 값이다. 천장·문틀 상단보다 충분히
```
→
```yaml
# 0.9는 로봇 최고점(0.863)에 3.7 cm 여유를 둔 값이다. 천장·문틀 상단보다 충분히
```

- [ ] **Step 7: xacro 문법과 변경 범위 확인**

```bash
source /opt/ros/humble/setup.bash
cd /mnt/ssd/workspaces/tmp/urdf-geometry
xacro src/vica_description/urdf/VICA.xacro > /tmp/vica_geom.urdf && echo "XACRO OK"
check_urdf /tmp/vica_geom.urdf | head -3
diff /tmp/vica_before.urdf /tmp/vica_geom.urdf
```

기대: `XACRO OK`, `robot name is: VICA`, diff에 **16줄만** 바뀜(origin 14개 + inertial 1개 + body_center_z가 전개된 base_link origin 2개).
의도하지 않은 줄이 바뀌었다면 되돌린다.

- [ ] **Step 8: TF 수치 검증 — 이 Task의 핵심**

수정 A·B는 RViz에서 보이지 않는다. 판정은 `tf2_echo` 수치로만 한다.

터미널 1:
```bash
source /opt/ros/humble/setup.bash
export ROS_DOMAIN_ID=91
export ROS_LOCALHOST_ONLY=1
cd /mnt/ssd/workspaces/tmp/urdf-geometry
ros2 run robot_state_publisher robot_state_publisher /tmp/vica_geom.urdf &
ros2 run joint_state_publisher joint_state_publisher \
  --ros-args --params-file <(python3 -c "
import sys
print('joint_state_publisher:')
print('  ros__parameters:')
print('    source_list: []')
") &
```

`joint_state_publisher`에 robot_description을 넘기기 어려우면 아래 launch로 대신한다.

```bash
cat > /tmp/probe.launch.py <<'EOF'
import os
from launch import LaunchDescription
from launch.substitutions import Command, FindExecutable
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue

MODEL = "/mnt/ssd/workspaces/tmp/urdf-geometry/src/vica_description/urdf/VICA.xacro"


def generate_launch_description():
    robot_description = {
        "robot_description": ParameterValue(
            Command([FindExecutable(name="xacro"), " ", MODEL]), value_type=str
        )
    }
    return LaunchDescription([
        Node(package="robot_state_publisher", executable="robot_state_publisher",
             parameters=[robot_description], output="screen"),
        Node(package="joint_state_publisher", executable="joint_state_publisher",
             parameters=[robot_description], output="screen"),
    ])
EOF
ros2 launch /tmp/probe.launch.py
```

터미널 2에서 대조한다. 캐스터 steer 각도 0 기준.

```bash
source /opt/ros/humble/setup.bash
export ROS_DOMAIN_ID=91
export ROS_LOCALHOST_ONLY=1
for pair in "base_link left_wheel_1" "base_link right_wheel_1" \
            "base_link front_left_caster_wheel_1" \
            "base_footprint laser_frame" "base_footprint camera_link"; do
  echo "=== $pair ==="
  timeout 4 ros2 run tf2_ros tf2_echo $pair 2>/dev/null | grep -m1 -A1 Translation
done
```

기대값:

| 프레임 쌍 | 기대 translation |
|---|---|
| `base_link → left_wheel_1` | `0.154, 0.182, -0.125` |
| `base_link → right_wheel_1` | `0.154, -0.182, -0.125` |
| `base_link → front_left_caster_wheel_1` | `-0.252, 0.0795, -0.148` |
| `base_footprint → laser_frame` | `0.185, 0.0, 0.382` |
| `base_footprint → camera_link` | `0.28683, 0.0, 0.320` |

**최종 확인:** 좌·우 구동륜 y 차이 = `0.182 − (−0.182)` = **0.364** = 줄자 실측값.
`wheel_base_m 0.37`과 **일치하지 않는 것이 정상이다** — 스펙 3.1.1절.

끝나면 노드를 정리한다.
```bash
pkill -f "robot_state_publisher|joint_state_publisher"
```

- [ ] **Step 9: 계약 테스트 재실행**

```bash
cd /mnt/ssd/workspaces/tmp/urdf-geometry/src
python3 -m pytest vica_nvblox_bringup/test/test_slice_height_contract.py vica_nav2/test/test_footprint_contract.py -q
```

기대: 전부 통과. Task 1 덕분에 로봇 최고점이 0.860 → 0.863으로 자동 갱신되고, `esdf_slice_max_height 0.9`가 여전히 이를 덮는다.

- [ ] **Step 10: 커밋**

```bash
cd /mnt/ssd/workspaces/tmp/urdf-geometry
git add src/vica_description/urdf/VICA.xacro \
        src/vica_nav2/test/test_footprint_contract.py \
        src/vica_nav2/config/nav2_params.yaml \
        src/vica_nvblox_bringup/config/vica_nvblox_overrides.yaml
git diff --cached --check
git commit -m "$(cat <<'EOF'
fix(urdf): 구동륜·캐스터 조인트 기하를 CAD·실측에 맞춘다

구동륜 간격이 0.293으로 적혀 있었다. 줄자 실측은 0.364이고 CAD 0.3618과도 2.2 mm
안에서 맞는다. 캐스터 휠은 10 mm 안쪽, 차체·라이다 메시는 3 mm 어긋나 있었다.

wheel_base_m 0.37은 그대로 둔다. 그건 회전 시험으로 맞춘 오도메트리 보정 상수라
실측 기하와 같을 필요가 없다.

-0.044를 인용하던 주석 세 곳을 같은 커밋에서 고친다. 나눠 두면 그 사이에 거짓
주석이 남는다.

visual origin이 joint origin을 정확히 상쇄해 RViz에서는 정상으로 보였고, 오차
방향이 회전축과 같아 바퀴를 굴려도 드러나지 않았다. 실물 오도메트리는 URDF를
읽지 않으므로 주행 거동은 변하지 않는다.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: 좌표 상수를 property로 묶는다

오류 3건이 전부 손으로 적은 좌표 상수에서 나왔다. 같은 수를 두 번 적지 않게 만든다.
**이 Task는 xacro 출력을 바꾸면 안 된다.** 순수 리팩터임을 diff로 증명한다.

**Files:**
- Modify: `src/vica_description/urdf/VICA.xacro`

**Interfaces:**
- Produces: xacro property `wheel_separation`, `wheel_y`, `caster_steer_y`, `caster_y`, `caster_wheel_dy`

- [ ] **Step 1: 기준 산출물 저장**

```bash
source /opt/ros/humble/setup.bash
cd /mnt/ssd/workspaces/tmp/urdf-geometry
xacro src/vica_description/urdf/VICA.xacro > /tmp/vica_geom.urdf
echo "기준 저장 완료"
```

- [ ] **Step 2: property 블록 추가**

`VICA.xacro`의 14행(`camera_z` property) 다음, `<link name="base_footprint"/>` 앞에 넣는다.

```xml
<!-- Drive wheel / caster geometry. Single source for every y coordinate. -->
<!-- 줄자 실측(바퀴 중심 사이). CAD 0.3618과 2.2 mm 차이.
     encoder.yaml의 wheel_base_m 0.37은 회전 시험으로 맞춘 오도메트리 보정 상수라
     이 값과 다르다. 통일 대상이 아니다 — 스펙 3.1.1절. -->
<xacro:property name="wheel_separation" value="0.364" />
<xacro:property name="wheel_y" value="${wheel_separation / 2}" />
<!-- CAD 실측: steer ±0.0845, wheel ±0.0795 -->
<xacro:property name="caster_steer_y" value="0.0845" />
<xacro:property name="caster_y" value="0.0795" />
<!-- steer 링크 기준 wheel 조인트의 y. round()는 부동소수점 꼬리를 자른다. -->
<xacro:property name="caster_wheel_dy" value="${round(caster_y - caster_steer_y, 6)}" />
```

- [ ] **Step 3: 구동륜 좌표를 property로 치환**

joint origin 두 곳:
```xml
  <origin xyz="0.154 0.182 -0.125" rpy="0 0 0"/>     →  <origin xyz="0.154 ${wheel_y} -0.125" rpy="0 0 0"/>
  <origin xyz="0.154 -0.182 -0.125" rpy="0 0 0"/>    →  <origin xyz="0.154 ${-wheel_y} -0.125" rpy="0 0 0"/>
```

`left_wheel_1` visual + collision (두 곳):
```xml
      <origin xyz="-0.154 -0.182 0.084" rpy="0 0 0"/>  →  <origin xyz="-0.154 ${-wheel_y} 0.084" rpy="0 0 0"/>
```

`right_wheel_1` visual + collision (두 곳):
```xml
      <origin xyz="-0.154 0.182 0.084" rpy="0 0 0"/>   →  <origin xyz="-0.154 ${wheel_y} 0.084" rpy="0 0 0"/>
```

`wheel_separation / 2 = 0.182`는 부동소수점 꼬리 없이 전개된다(검증 완료). 캐스터와
달리 `round()`가 필요 없다.

- [ ] **Step 4: 캐스터 좌표를 property로 치환**

캐스터 휠 joint origin 두 곳:
```xml
  <origin xyz="-0.03 -0.005 -0.0655" rpy="0 0 0"/>  →  <origin xyz="-0.03 ${caster_wheel_dy} -0.0655" rpy="0 0 0"/>
  <origin xyz="-0.03 0.005 -0.0655" rpy="0 0 0"/>   →  <origin xyz="-0.03 ${-caster_wheel_dy} -0.0655" rpy="0 0 0"/>
```

캐스터 휠 visual + collision (각 두 곳):
```xml
      <origin xyz="0.252 -0.0795 0.107" rpy="0 0 0"/>  →  <origin xyz="0.252 ${-caster_y} 0.107" rpy="0 0 0"/>
      <origin xyz="0.252 0.0795 0.107" rpy="0 0 0"/>   →  <origin xyz="0.252 ${caster_y} 0.107" rpy="0 0 0"/>
```

캐스터 steer joint origin 두 곳:
```xml
  <origin xyz="-0.222 -0.0845 -0.0825" rpy="0 0 0"/>  →  <origin xyz="-0.222 ${-caster_steer_y} -0.0825" rpy="0 0 0"/>
  <origin xyz="-0.222 0.0845 -0.0825" rpy="0 0 0"/>   →  <origin xyz="-0.222 ${caster_steer_y} -0.0825" rpy="0 0 0"/>
```

캐스터 steer visual + collision (각 두 곳):
```xml
      <origin xyz="0.222 0.0845 0.0415" rpy="0 0 0"/>   →  <origin xyz="0.222 ${caster_steer_y} 0.0415" rpy="0 0 0"/>
      <origin xyz="0.222 -0.0845 0.0415" rpy="0 0 0"/>  →  <origin xyz="0.222 ${-caster_steer_y} 0.0415" rpy="0 0 0"/>
```

- [ ] **Step 5: 라이다 메시 z를 수식으로**

`laser_frame` visual + collision (두 곳):
```xml
      <origin xyz="-0.185 -0.0 -0.233" rpy="0 0 0"/>
```
→
```xml
      <origin xyz="-0.185 -0.0 ${-(laser_z + body_center_z)}" rpy="0 0 0"/>
```

이제 `body_center_z`를 바꾸면 차체와 라이다 메시가 함께 따라온다.

- [ ] **Step 6: 순수 리팩터 검증 — 이 Task의 핵심**

```bash
source /opt/ros/humble/setup.bash
cd /mnt/ssd/workspaces/tmp/urdf-geometry
xacro src/vica_description/urdf/VICA.xacro > /tmp/vica_prop.urdf && echo "XACRO OK"
diff /tmp/vica_geom.urdf /tmp/vica_prop.urdf && echo "=== 순수 리팩터 확인: 출력 동일 ==="
```

기대: `diff` 출력이 **비어 있다.** 무언가 출력되면 좌표를 건드린 것이므로 되돌린다.

부동소수점 꼬리(`-0.0050000000000000044` 같은 값)가 보이면 `round()`가 빠진 것이다.

- [ ] **Step 7: 계약 테스트 재실행**

```bash
cd /mnt/ssd/workspaces/tmp/urdf-geometry/src
python3 -m pytest vica_nvblox_bringup/test/test_slice_height_contract.py vica_nav2/test/test_footprint_contract.py -q
```

기대: 전부 통과.

- [ ] **Step 8: 커밋**

```bash
cd /mnt/ssd/workspaces/tmp/urdf-geometry
git add src/vica_description/urdf/VICA.xacro
git diff --cached --check
git commit -m "$(cat <<'EOF'
refactor(urdf): 좌표 상수를 property로 묶는다

이번 오류 3건이 전부 손으로 적은 좌표 상수에서 나왔다. y 계열을 property 하나로
모으고 라이다 메시 z를 body_center_z 수식으로 바꿔, 같은 수를 두 번 적지 않게
한다. xacro 출력은 직전 커밋과 완전히 동일하다.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: camera_optical_frame을 추가한다

실물은 RealSense 드라이버가 optical 프레임을 자체 발행하므로 당장 필요하지 않다. Isaac에는 드라이버가 없어 URDF가 제공해야 하므로, 정본을 하나로 유지하려고 미리 넣는다.

**Files:**
- Modify: `src/vica_description/urdf/VICA.xacro` (`</robot>` 직전)

- [ ] **Step 1: 링크와 조인트 추가**

`VICA.xacro`의 `</robot>` 바로 앞에 넣는다.

```xml
<!-- REP-103: +Z forward, +X right, +Y down -->
<!-- 실물은 RealSense 드라이버가 자체 발행하지만, Isaac에는 드라이버가 없어
     URDF가 제공해야 한다. 정본을 하나로 유지하려고 여기에 둔다. -->
<link name="camera_optical_frame"/>
<joint name="camera_optical_joint" type="fixed">
  <origin xyz="0 0 0" rpy="-${pi/2} 0 -${pi/2}"/>
  <parent link="camera_link"/>
  <child  link="camera_optical_frame"/>
</joint>
```

`camera_color_optical_frame`·`camera_depth_optical_frame`은 **넣지 않는다.** RealSense 드라이버가 동일 이름으로 발행해 TF 중복 충돌이 난다.

- [ ] **Step 2: 링크 수와 문법 확인**

```bash
source /opt/ros/humble/setup.bash
cd /mnt/ssd/workspaces/tmp/urdf-geometry
xacro src/vica_description/urdf/VICA.xacro > /tmp/vica_optical.urdf && echo "XACRO OK"
check_urdf /tmp/vica_optical.urdf | head -3
grep -c "<link name" /tmp/vica_optical.urdf
```

기대: `XACRO OK`, `robot name is: VICA`, 링크 수 **11**.

- [ ] **Step 3: 회전이 REP-103대로인지 확인**

```bash
source /opt/ros/humble/setup.bash
export ROS_DOMAIN_ID=91
export ROS_LOCALHOST_ONLY=1
ros2 run robot_state_publisher robot_state_publisher /tmp/vica_optical.urdf &
sleep 4
timeout 4 ros2 run tf2_ros tf2_echo camera_link camera_optical_frame 2>/dev/null | grep -m1 -A4 "Translation"
pkill -f robot_state_publisher
```

기대: translation `[0.000, 0.000, 0.000]`, RPY(degree) `[-90.000, 0.000, -90.000]`.

- [ ] **Step 4: 커밋**

```bash
cd /mnt/ssd/workspaces/tmp/urdf-geometry
git add src/vica_description/urdf/VICA.xacro
git diff --cached --check
git commit -m "$(cat <<'EOF'
feat(urdf): camera_optical_frame을 추가한다

실물은 RealSense 드라이버가 optical 프레임을 발행하지만 Isaac에는 드라이버가
없다. 정본을 하나로 유지하려고 URDF가 제공한다. RealSense 기본 이름
(camera_color_optical_frame 등)은 TF 중복 충돌을 피하려고 쓰지 않는다.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: 실주행 TF launch를 GUI에서 분리한다

기동 매뉴얼 ②단계가 실주행에서 `display.launch.py`를 띄우는데, 이 launch는 `joint_state_publisher_gui`를 조건 없이 함께 띄운다. Qt가 필요해 헤드리스에서는 TF 트리가 통째로 끊긴다.

`display.launch.py`의 기본값을 바꾸면 매뉴얼과 팀 습관이 깨지므로, 실주행용 launch를 새로 만든다.

**Files:**
- Create: `src/vica_description/launch/robot_state.launch.py`
- 참고(수정 없음): `src/vica_description/launch/display.launch.py`

**Interfaces:**
- Consumes: `src/vica_description/urdf/VICA.xacro` (Task 2~4의 결과)
- Produces: launch 파일 `robot_state.launch.py` — launch 인자 `model` (기본값 = 패키지 share의 `urdf/VICA.xacro`)

- [ ] **Step 1: 새 launch 파일 작성**

`src/vica_description/launch/robot_state.launch.py`를 만든다.

```python
"""실주행용 TF 발행. GUI에 의존하지 않는다.

display.launch.py는 joint_state_publisher_gui(Qt)와 RViz를 함께 띄우므로
헤드리스 환경에서 뜨지 않는다. 그런데 기동 매뉴얼은 이 launch를 TF 트리의 필수
구성으로 지정한다. 실주행 경로를 GUI에서 떼어내려고 이 파일을 둔다.

joint_state_publisher_gui는 joint_state_publisher를 의존성으로 포함하고 Qt 창만
얹은 래퍼다. 발행 로직이 같으므로 /joint_states 내용과 발행량은 동일하다.
바뀌는 것은 슬라이더 창이 사라지는 것뿐이고, RViz에서 바퀴 메시는 그대로 보인다.

나중에 엔코더 기반 각도를 넣을 때는 joint_state_publisher의 source_list 파라미터에
부분 발행 토픽을 더하면 된다. 캐스터 4개는 센서가 없어도 기본값으로 자동 보충된다.
"""
import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import Command, FindExecutable, LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    pkg_share = get_package_share_directory("vica_description")
    default_model = os.path.join(pkg_share, "urdf", "VICA.xacro")

    model = LaunchConfiguration("model")

    robot_description = {
        "robot_description": ParameterValue(
            Command([
                FindExecutable(name="xacro"),
                " ",
                model,
            ]),
            value_type=str,
        )
    }

    return LaunchDescription([
        DeclareLaunchArgument("model", default_value=default_model),
        Node(
            package="robot_state_publisher",
            executable="robot_state_publisher",
            parameters=[robot_description],
            output="screen",
        ),
        Node(
            package="joint_state_publisher",
            executable="joint_state_publisher",
            parameters=[robot_description],
            output="screen",
        ),
    ])
```

`package.xml`에 `joint_state_publisher`가 이미 `exec_depend`로 들어 있으므로 의존성 추가는 필요 없다.
`CMakeLists.txt`도 `launch` 디렉터리 전체를 설치하므로 수정할 필요가 없다.

- [ ] **Step 2: 빌드**

```bash
source /opt/ros/humble/setup.bash
cd /mnt/ssd/workspaces/tmp/urdf-geometry
colcon build --packages-select vica_description
```

기대: `Summary: 1 package finished`

- [ ] **Step 3: 헤드리스 기동 검증 — 이 Task의 핵심**

```bash
source /opt/ros/humble/setup.bash
cd /mnt/ssd/workspaces/tmp/urdf-geometry
source install/setup.bash
export ROS_DOMAIN_ID=91
export ROS_LOCALHOST_ONLY=1
unset DISPLAY                      # 헤드리스 조건 강제

ros2 launch vica_description robot_state.launch.py &
sleep 8

echo "=== 노드 ==="
ros2 node list

echo "=== /joint_states ==="
timeout 5 ros2 topic echo /joint_states --once | head -14

echo "=== 바퀴 TF ==="
timeout 4 ros2 run tf2_ros tf2_echo base_link left_wheel_1 2>/dev/null | grep -m1 -A1 Translation

pkill -f "robot_state_publisher|joint_state_publisher"
```

기대:
- 노드 `/joint_state_publisher`와 `/robot_state_publisher`가 **DISPLAY 없이** 뜬다
- `/joint_states`의 `name`에 조인트 6개가 모두 있다
- `base_link → left_wheel_1` translation이 `0.154, 0.182, -0.125`

- [ ] **Step 4: display.launch.py가 그대로 동작하는지 확인**

`display.launch.py`는 수정하지 않았지만, 회귀가 없는지 확인한다. **이 단계는 화면이 있는 환경에서 한다.**

```bash
source /opt/ros/humble/setup.bash
cd /mnt/ssd/workspaces/tmp/urdf-geometry
source install/setup.bash
export ROS_DOMAIN_ID=91
ros2 launch vica_description display.launch.py
```

RViz 회귀 검사 항목:
- 바퀴 4개가 차체 대비 이전과 같은 위치에 보인다 — 움직였다면 visual origin 수정 오류
- 바퀴가 지면에 닿아 있고 파묻히지 않는다
- `joint_state_publisher_gui` 슬라이더로 바퀴·캐스터를 돌려도 축을 벗어나 흔들리지 않는다
- 차체·라이다가 이전보다 3 mm 위로 올라갔다(미세함)
- `camera_optical_frame` 축이 `camera_link`와 다른 방향(전방 = 파랑 Z)을 가리킨다

확인 후 Ctrl+C로 종료한다.

- [ ] **Step 5: 커밋**

```bash
cd /mnt/ssd/workspaces/tmp/urdf-geometry
git add src/vica_description/launch/robot_state.launch.py
git diff --cached --check
git commit -m "$(cat <<'EOF'
refactor(description): 실주행 TF launch를 GUI에서 분리한다

기동 매뉴얼 ②단계가 실주행에서 display.launch.py를 띄우는데, 이 launch는
joint_state_publisher_gui(Qt)를 조건 없이 함께 올린다. 헤드리스에서는 뜨지 않아
TF 트리가 통째로 끊긴다.

joint_state_publisher_gui는 joint_state_publisher에 Qt 창만 얹은 래퍼라 발행
로직이 같다. 창만 빠지고 RViz의 바퀴 메시는 그대로다. display.launch.py는
확인용으로 현행 유지한다.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: 옛 좌표의 run_tf_vica.sh를 지운다

`scripts/run_tf_vica.sh`가 `static_transform_publisher`로 `laser_frame`(`0.00995, 0, 0.319`)과 `camera_link`(`0.105, 0, 0.265`)를 발행한다. 이는 `before_VICA.xacro` 시절 값이며 현재 URDF(`0.185, 0, 0.192` / `0.28683, 0, 0.130`)와 다르다. 살려두면 이중 정본이 되어 같은 어긋남이 재발한다.

**Files:**
- Delete: `scripts/run_tf_vica.sh`

- [ ] **Step 1: 참조가 없는지 다시 확인**

```bash
cd /mnt/ssd/workspaces/tmp/urdf-geometry
grep -rn "run_tf_vica" . --include="*.md" --include="*.py" --include="*.sh" --include="*.yaml" --include="*.xml" 2>/dev/null
grep -rn "run_tf_vica" /home/msk/VICA-smarthandle/docs /home/msk/VICA-smarthandle/guideline /home/msk/VICA-smarthandle/devlog /home/msk/VICA-smarthandle/README.md 2>/dev/null
```

기대: **출력 없음.** 무언가 나오면 삭제를 멈추고 해당 참조를 먼저 처리한다.

- [ ] **Step 2: 삭제**

```bash
cd /mnt/ssd/workspaces/tmp/urdf-geometry
git rm scripts/run_tf_vica.sh
```

- [ ] **Step 3: 커밋**

```bash
cd /mnt/ssd/workspaces/tmp/urdf-geometry
git commit -m "$(cat <<'EOF'
chore(scripts): 옛 좌표의 run_tf_vica.sh를 지운다

before_VICA.xacro 시절 좌표(laser 0.00995/0.319, camera 0.105/0.265)로 static TF를
발행한다. 현재 URDF는 0.185/0.192, 0.28683/0.130이다. 참조하는 문서·코드가 없고
기동 매뉴얼도 언급하지 않으며, 존재하지 않는 /home/ji_w/ros2_ws를 source한다.

살려두면 URDF와 이중 정본이 되어 같은 어긋남이 재발한다. git 이력에 남는다.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: 기동 매뉴얼 ②단계를 갱신한다

**이 Task만 `/home/msk/VICA-smarthandle`(workspace 저장소)에서 한다.** 브랜치는 이미 만들어 둔 `docs/urdf-geometry`다.

**Files:**
- Modify: `docs/vica_robot_bringup_manual.md:329-336`

- [ ] **Step 1: 브랜치 확인**

```bash
cd /home/msk/VICA-smarthandle
git status -sb
```

기대: `## docs/urdf-geometry`. 아니면 `git switch docs/urdf-geometry`.

- [ ] **Step 2: ②단계 교체**

`docs/vica_robot_bringup_manual.md`의 아래 부분을 찾는다.

````markdown
```bash
ros2 launch vica_description display.launch.py
```

`robot_state_publisher`가 `base_link → laser_frame`, `camera_link` TF를 발행한다. RViz
확인 용도만이 아니라 TF 트리의 필수 구성이므로 생략하지 않는다.
````

아래로 바꾼다.

````markdown
```bash
ros2 launch vica_description robot_state.launch.py
```

`robot_state_publisher`가 `base_link → laser_frame`, `camera_link` TF를 발행한다. RViz
확인 용도만이 아니라 TF 트리의 필수 구성이므로 생략하지 않는다.

이 launch는 화면이 없어도 뜬다. RViz까지 함께 보려면 `display.launch.py`를 쓴다 —
`joint_state_publisher_gui`(Qt 슬라이더)와 RViz가 딸려오므로 화면이 있는 환경에서만
동작한다.

```bash
ros2 launch vica_description display.launch.py   # 확인용
```
````

- [ ] **Step 3: 커밋**

```bash
cd /home/msk/VICA-smarthandle
git add docs/vica_robot_bringup_manual.md
git diff --cached --check
git commit -m "$(cat <<'EOF'
docs(bringup): ②단계를 GUI 없는 robot_state.launch.py로 바꾼다

display.launch.py는 joint_state_publisher_gui(Qt)를 함께 띄워 헤드리스에서 뜨지
않는다. 매뉴얼이 이 launch를 TF 트리의 필수 구성으로 지정하므로, 실주행 경로는
화면 없이 동작하는 launch를 가리켜야 한다.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

## 완료 기준

전부 확인한 뒤 사용자에게 보고한다.

- [ ] `xacro` 성공, `check_urdf` 링크 **11개**, 루트 `base_footprint`
- [ ] `diff /tmp/vica_before.urdf` 결과에 의도하지 않은 변경 없음
- [ ] `tf2_echo` 기대값 5개 전부 일치
- [ ] 좌·우 구동륜 y 차이 = **0.364** (`wheel_base_m 0.37`과 다른 것이 정상)
- [ ] Task 3의 순수 리팩터 `diff`가 비어 있음
- [ ] `pytest` — slice·footprint 계약 테스트 전부 통과
- [ ] `colcon build --packages-select vica_description` 성공
- [ ] `robot_state.launch.py`가 `DISPLAY` 없이 기동, `/joint_states`에 조인트 6개
- [ ] RViz 회귀 검사 5항목 통과
- [ ] 커밋 6개(`vica_ros2_ws`) + 1개(workspace)가 성격별로 분리되어 있음

**머지하지 않는다.** 메모리 규칙에 따라 노트북 단위 테스트 통과는 머지 근거가 아니며, 머지 시점은 사용자가 판정한다.

## 이번에 하지 않는 것

스펙 9절에 근거가 있다. 실행자가 임의로 확장하지 않는다.

- 캐스터 이름 `front_*` → `rear_*` (USD 재import와 같은 세션에서)
- Isaac 이식 (`WHEEL_DISTANCE` 0.293 → 0.364 포함)
- 엔코더 기반 `/joint_states` (`source_list`)
- ROS 1 잔재 파일 정리 (`display.launch`, `controller.launch`, `gazebo.launch`, `VICA.trans`)
- `VICA.gazebo`, `before_VICA.xacro`, `urdf.rviz`, `meshes/` 수정
