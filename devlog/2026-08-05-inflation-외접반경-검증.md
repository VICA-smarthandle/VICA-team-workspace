# 2026-08-05 · `inflation_radius` 0.55 대 외접반경 0.651 검증

Isaac Sim 시뮬레이션을 구축 중인 다른 세션에서 실물 파라미터 변경 권고가 왔다.
그 근거를 Humble Nav2 소스와 이 저장소의 실측 기록에 하나씩 대조한 기록이다.

**결론: 수치는 맞지만 메커니즘과 처방이 틀렸다. 실물 설정은 바꾸지 않는다.**

이 문서는 코드를 바꾸지 않는다. 나중에 controller를 교체하거나 같은 지적이 다시
올 때 재검증할 수 있도록 계산·명령·판단 근거만 남긴다.

> **기준 브랜치 주의.** 아래 실물 값은 전부 `vica_ros2_ws`의 **`dev`** 기준이다.
> 2026-08-05 현재 `vica_ros2_ws` 작업트리는 `feat/home-return`이 체크아웃돼 있고,
> 그쪽 `nav2_params.yaml`은 사각형 footprint·`inflation_radius` 0.45·SmacPlanner2D인
> 구버전이라 이 문서의 수치와 맞지 않는다. 계약 테스트 상한도 다르다
> (`dev` 0.70 / `feat/home-return` 0.50). 검증할 때는 먼저 브랜치를 확인할 것:
>
> ```bash
> cd /home/msk/VICA-smarthandle/vica_ros2_ws
> git show dev:src/vica_nav2/config/nav2_params.yaml | grep -n "inflation_radius:\|^\s*footprint:"
> ```

---

## 1. 받은 지적

> `inflation_radius`(0.55)가 `circumscribed_radius`(0.6506)보다 작다. Nav2가
> costmap potential field로 충돌 검사를 가속하지 못해 매번 6각형 footprint 전체를
> 검사하게 되고, 그래서 플래너·컨트롤러 응답이 늦어져 lifecycle bond 타임아웃 →
> Goal ABORTED로 이어졌다. 실물도 0.55 → 0.70으로 올려야 한다.
>
> 실물에서 안 터진 것은 DWB가 궤적 후보가 적고 footprint 검사가 가벼워 느려져도
> 버티기 때문이다. MPPI는 `batch_size 2000 × time_steps 56`을 20 Hz로 돌리고
> `CostCritic.consider_footprint: true`라 초당 200만 회 이상의 검사가 된다.

## 2. 맞는 것

| 주장 | 검증 |
| --- | --- |
| 외접반경 0.6506 m | 정확. `padFootprint`(부호 기반 0.05) 후 꼬리 꼭짓점 `(-0.595,-0.035)` → `(-0.645,-0.085)`, 거리 0.65058 |
| 내접반경 0.2775 m | 정확. `nav2_params.yaml` 주석의 "내접반경 0.277 m"와 일치 |
| 실물 `inflation_radius` 0.55 < 0.6506 | 사실. `dev`의 local·global 두 costmap 모두 0.55 |
| 실물 DWB + Lattice / nvblox 예제 MPPI + Hybrid | 사실 |
| MPPI `batch_size 2000` × `time_steps 56` | 사실. `carter_nav2.yaml:93`, `:91` |

이 수치가 새로 발견된 것은 아니다. `devlog/2026-08-02-주행테스트.md` 3.3절에
"육각형 외접반경 0.651 m / 사각형 0.675 m"로 이미 기록돼 있고, footprint를 육각형으로
바꾼 작업 자체가 외접반경을 줄이려던 것이었다.

## 3. 틀린 것

### 3.1 인용한 경고문은 이 상황에서 뜨지 않는다

Humble에는 별개의 경고가 둘 있고, 지적은 앞의 것을 인용했다.

**A** — `nav2_smac_planner/utils.hpp:93`

> **No inflation layer found in costmap configuration.** If this is an SE2-collision
> checking plugin, it cannot use costmap potential field to speed up collision checking
> by only checking the full footprint when robot is within possibly-inscribed radius of
> an obstacle. This may significantly slow down planning times!

같은 파일 `:70-101`의 `findCircumscribedCost`를 보면 이 경고는 `plugins` 목록을
순회해 `InflationLayer`를 **하나도 못 찾았을 때만** 발동한다. `inflation_radius`
값과 무관하다. VICA·Carter 설정 모두 `inflation_layer`를 포함하므로 뜰 수 없다.

**B** — `libnav2_smac_planner*.so` / `libmppi_critics.so`

> Inflation layer either not found **or inflation is not set sufficiently** for
> optimized non-circular collision checking capabilities. It is HIGHLY recommended to
> set the inflation radius to be at MINIMUM half of the robot's largest cross-section.

이쪽이 값 부족을 지적하는 경고인데, 이것도 VICA 값에서는 뜨지 않는다(3.2 참조).

**시뮬 로그에서 실제로 A를 봤다면 원인은 0.55라는 값이 아니라 코스트맵 `plugins`
목록에서 `inflation_layer`가 빠진 것이다.** 진단 대상이 완전히 다르다.

### 3.2 `computeCost`는 `inflation_radius`를 참조하지 않는다

`nav2_costmap_2d/inflation_layer.hpp:148-162`:

```cpp
inline unsigned char computeCost(double distance) const {
  unsigned char cost = 0;
  if (distance == 0) cost = LETHAL_OBSTACLE;
  else if (distance * resolution_ <= inscribed_radius_) cost = INSCRIBED_INFLATED_OBSTACLE;
  else {
    double factor = exp(-1.0 * cost_scaling_factor_ * (distance * resolution_ - inscribed_radius_));
    cost = static_cast<unsigned char>((INSCRIBED_INFLATED_OBSTACLE - 1) * factor);
  }
  return cost;
}
```

`inscribed_radius_`와 `cost_scaling_factor_`만 쓴다. 따라서 `findCircumscribedCost`가
돌려주는 `possible_collision_cost`는 inflation이 0.55든 0.70이든 **항상 68**이다.

```
252 × exp(−3.5 × (0.6506 − 0.2775)) = 252 × 0.27091 = 68.3 → 68
```

68 ≥ 1이므로 경고 B도 발동하지 않는다.

### 3.3 증상의 방향이 반대다 — 느려지는 게 아니라 검사를 건너뛴다

Smac의 `GridCollisionChecker`는 로봇 중심 셀의 비용이 `possible_collision_cost`보다
**작으면 안전으로 단정하고 footprint 검사를 생략**한다. inflation이 바꾸는 것은
임계값이 아니라 **코스트맵이 그 임계값에 해당하는 거리까지 칠해지느냐**뿐이다.

| `inflation_radius` | 코스트맵이 끊기는 지점의 비용 | 68에 해당하는 거리 | 사각지대 |
| --- | --- | --- | --- |
| 0.55 | 0.55 m에서 **97 → 0** 절벽 | 0.6506 m | **폭 0.1006 m** |
| 0.651 이상 | 연속 | 0.6506 m | 없음 |

벽에서 0.55~0.6506 m 구간은 코스트맵 값이 0이라 `0 < 68` → 검사 생략. 그런데
꼬리는 0.6506까지 뻗는다. **더 느려지는 게 아니라 더 빨라지고, 대신 놓친다.**
성능 문제가 아니라 안전 문제이며, inflation을 올려 얻는 것은 속도가 아니라
이 사각지대의 제거다.

### 3.4 Goal ABORTED 인과 사슬이 성립하지 않는다

"검사 느려짐 → bond 타임아웃 → 노드 비활성화 → ABORTED"는 첫 고리(3.3)가 무너진다.
또한 이 저장소 devlog 전체에 bond timeout 기록이 없다.

### 3.5 `CostCritic`이 아니라 `ObstaclesCritic`

`carter_nav2.yaml:136`이 `ObstaclesCritic.consider_footprint: True`다. Humble의
`libmppi_critics.so`에 `mppi::critics::CostCritic` 클래스가 존재하기는 하나 이
설정에서 로드되지 않는다.

### 3.6 NVIDIA 원본 시뮬 설정에는 이 문제가 없다

`carter_nav2.yaml`은 `inflation_radius: 0.8`(`:190`, `:221`), footprint는 Carter
차체 사각형 `[[0.14,0.25],[0.14,-0.25],[-0.607,-0.25],[-0.607,0.25]]`(`:182`),
padding 0.03(`:172`). padding 적용 후 외접 ≈ 0.696 < 0.8이라 정상이다.
지적에 나온 "시뮬 inflation 0.55"는 원본이 아니라 VICA 값으로 바꾼 별도 파일이다.

### 3.7 실물에서 안 터진 진짜 이유

"DWB는 검사가 가벼워 느려져도 버틴다"가 아니다. **DWB에는 이 사각지대가 아예 없다.**

```
strings /opt/ros/humble/lib/libdwb_critics.so | grep -icE "circumscribed|possible_collision"
# → 0
```

DWB는 이 최적화 경로를 쓰지 않는다. `ObstacleFootprint` critic이 궤적 각 자세마다
footprint 변을 순회한다(`nav2_params.yaml` DWB critics 주석과 같은 근거). 즉
controller가 항상 전체 footprint를 검사하는 최종 방벽으로 작동한다.

## 4. 0.70 권고에 반대하는 이유

- `src/vica_nav2/test/test_footprint_contract.py`의
  `assert inflation_radius <= CORRIDOR_HALF_WIDTH_MEDIAN`에서 그 상한이 **정확히
  0.70**이다. 맵 실측 통로 반폭의 중앙값이라, 0.70이면 통로 절반에서 비용 0인
  중앙선이 사라진다. 테스트 메시지가 그 경계를 "우회가 아니라 전면 정체"로 규정한다.
  0.70은 이 assert를 `<=`로 아슬아슬하게 통과할 뿐, 경계가 뜻하는 상태 그 자체다.
- 0.55에서 이미 실측됐다(2026-08-02 run1233): 1.0 m 통로 중앙 비용 115 → planner가
  통로 자체를 우회 → 이동 거리 +24 %.
- 0.55는 "로봇이 최단으로 통과하는가"가 아니라 "**뒤에서 핸들을 잡은 사람이 안전하게
  따라오는가**"라는 기준으로 재판정해 확정한 값이다.
- 설정에 되돌릴 조건이 명시돼 있다 — "꼭 지나야 하는 목적지가 우회로 없는 좁은 통로
  안에 있을 때". 0.70은 그 위험을 크게 키운다.

## 5. 실제로 남는 문제와 판단

planner(Lattice)가 벽에서 0.55~0.651 사이를 지나는 경로를 낼 수 있고, 그 구간은
코스트맵 값이 0이라 회피 유인조차 없다. 사각지대를 없애려면 `inflation_radius ≥
0.651` 외에 방법이 없다 — `footprint_padding`을 footprint에 직접 녹여도 외접반경은
그대로다.

**판단: 값을 바꾸지 않는다.** 사각지대는 DWB의 `ObstacleFootprint`가 막고 있고,
0.651로 올리면 통로 반폭 중앙값 0.70 m에 육박해 통로 회피가 지금보다 심해진다.
검증된 주행 특성을 이론상의 사각지대 때문에 흔들 이유가 없다.

**다만 전제가 하나 붙는다.** 사각지대를 막는 것은 DWB뿐이므로, **controller를
MPPI 등 potential-field 최적화를 쓰는 것으로 바꾸는 순간 방벽이 사라진다.**
MPPI의 `ObstaclesCritic`은 `consider_footprint`를 켜도 같은
`possible_collision_cost`로 조기 탈출한다. controller를 바꾸려면 **그 전에**
`inflation_radius`를 0.651 이상으로 올려야 한다.

## 6. 재현 명령

```bash
# 외접·내접반경과 possible_collision_cost
python3 - <<'PY'
import math
fp = [(0.305, 0.2275), (0.305, -0.2275), (-0.305, -0.2275),
      (-0.595, -0.035), (-0.595, 0.035), (-0.305, 0.2275)]
sgn = lambda v: (v > 0) - (v < 0)
p = [(x + sgn(x) * 0.05, y + sgn(y) * 0.05) for x, y in fp]   # padFootprint
circ = max(math.hypot(x, y) for x, y in p)

def seg_dist(a, b):
    (ax, ay), (bx, by) = a, b
    dx, dy = bx - ax, by - ay
    t = max(0, min(1, -(ax * dx + ay * dy) / (dx * dx + dy * dy)))
    return math.hypot(ax + t * dx, ay + t * dy)

insc = min(seg_dist(p[i], p[(i + 1) % len(p)]) for i in range(len(p)))
cost = lambda d: 253 if d <= insc else int(252 * math.exp(-3.5 * (d - insc)))
print(f'외접 {circ:.4f}  내접 {insc:.4f}  possible_collision_cost {cost(circ)}')
for infl in (0.55, 0.651, 0.70):
    print(f'  inflation {infl}: 경계 비용 {cost(infl)}, 사각지대 {max(0, circ - infl):.4f} m')
PY
# → 외접 0.6506  내접 0.2775  possible_collision_cost 68
#      inflation 0.55: 경계 비용 97, 사각지대 0.1006 m

# 경고 A의 실제 발동 조건 (inflation layer 부재 시에만)
sed -n '70,101p' /opt/ros/humble/include/nav2_smac_planner/utils.hpp

# computeCost가 inflation_radius를 안 보는 것
sed -n '148,162p' /opt/ros/humble/include/nav2_costmap_2d/nav2_costmap_2d/inflation_layer.hpp

# 경고 A와 B를 구분해 보기
for f in /opt/ros/humble/lib/libnav2_smac_planner*.so /opt/ros/humble/lib/libmppi_critics.so; do
  strings "$f" | grep -E "No inflation layer found|inflation is not set sufficiently"
done

# DWB는 이 최적화 경로를 쓰지 않는다
strings /opt/ros/humble/lib/libdwb_critics.so | grep -icE "circumscribed|possible_collision"   # → 0
```

## 7. 시뮬 장비에서 확인할 것

VICA용 Isaac Sim nav2 설정은 이 노트북에 없다. 확인한 범위는 다음과 같다.

- 육각 footprint(`-0.595`)를 쓰는 파일은 워크스페이스 전체에 둘뿐 —
  `/mnt/ssd/workspaces/tmp/urdf-geometry/src/vica_nav2/config/nav2_params.yaml`,
  `devlog/2026-08-02-주행테스트.md`
- `isaac_ros-dev`에서 `inflation_radius`를 가진 파일은 `carter_nav2.yaml` 하나, 값 0.8
- `isaac_ros-dev` 하위 git 저장소 로그에 관련 커밋 없음, 2026-08-02 이후 수정된 yaml 없음

시뮬 설정이 있는 장비에서 다음을 확인해야 3.1의 결론이 닫힌다.

1. **시뮬 nav2 yaml의 두 costmap `plugins` 목록에 `inflation_layer`가 실제로
   들어 있는가.** 로그에서 본 경고가 A였다면 이것이 진짜 원인이다.
   빠져 있다면 `inflation_radius`를 아무리 올려도 증상은 그대로다.
2. **Goal ABORTED 시점의 `/rosout`에 bond timeout·lifecycle 전이 로그가 있는가.**
   없다면 ABORTED 원인은 다른 곳이다.
3. **MPPI를 쓰는 한 시뮬에서는 `inflation_radius ≥ 외접반경`이 필요하다.**
   시뮬 맵에는 실물 통로 폭(반폭 중앙값 0.70 m) 제약이 없으므로 시뮬에서만 올리는
   것은 타당하다. **단 그 값을 실물로 역수입하지 않는다** — 4절의 근거가 실물에만
   적용되기 때문이다.

## 8. 나중에 필요하면 적용할 것 (지금은 적용하지 않음)

controller를 DWB에서 바꾸기로 결정하는 순간, 5절의 전제가 깨진다. 그때 이 전제를
코드가 지키게 하려면 `test_footprint_contract.py`에 아래를 넣으면 된다. 기존
`_load_params()` / `_footprint()` 헬퍼를 그대로 쓴다.

```python
def _padded_footprint(costmap_name):
    """nav2_costmap_2d의 padFootprint와 같은 규칙으로 padding을 적용한다."""
    params = _load_params()
    padding = params[costmap_name][costmap_name]['ros__parameters']['footprint_padding']

    def _sign(value):
        return (value > 0) - (value < 0)

    return [
        (x + _sign(x) * padding, y + _sign(y) * padding)
        for x, y in _footprint(costmap_name)
    ]


def _circumscribed_radius(costmap_name):
    return max(math.hypot(x, y) for x, y in _padded_footprint(costmap_name))


FOOTPRINT_CHECKING_CONTROLLER = 'dwb_core::DWBLocalPlanner'
FOOTPRINT_CHECKING_CRITIC = 'ObstacleFootprint'


@pytest.mark.parametrize('costmap', ['local_costmap', 'global_costmap'])
def test_short_inflation_requires_a_footprint_checking_controller(costmap):
    params = _load_params()
    inflation_radius = (
        params[costmap][costmap]['ros__parameters']['inflation_layer']['inflation_radius']
    )
    circumscribed = _circumscribed_radius(costmap)
    if inflation_radius >= circumscribed:
        return  # 사각지대가 없다. controller 종류를 제한할 이유가 없다.

    follow_path = params['controller_server']['ros__parameters']['FollowPath']
    gap = (
        f'{costmap} inflation_radius {inflation_radius}가 외접반경'
        f' {circumscribed:.4f} m보다 짧아, 그 사이 구간에서 planner가'
        ' footprint 검사를 건너뛴다.'
    )
    assert follow_path['plugin'] == FOOTPRINT_CHECKING_CONTROLLER, (
        f'{gap} 이를 막는 것은 DWB의 {FOOTPRINT_CHECKING_CRITIC} critic뿐이다.'
        f' controller를 바꾸려면 먼저 inflation_radius를 {circumscribed:.4f}'
        ' 이상으로 올려라'
    )
    assert FOOTPRINT_CHECKING_CRITIC in follow_path['critics'], (
        f'{gap} DWB critics에 {FOOTPRINT_CHECKING_CRITIC}가 없어 사각지대를'
        ' 막는 것이 아무것도 없다'
    )
```

`import math`가 필요하다. 현재 설정(0.55 + DWB + `ObstacleFootprint`)에서 통과하고,
controller를 MPPI로 바꾸거나 `ObstacleFootprint`를 빼면 실패한다.
