# VCC 컨트롤러 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Humble Nav2 컨트롤러 플러그인 `vica_vcc_controller::VccController`(VCC)를 만든다. 설정 한 줄로 RPP 와 갈아 끼울 수 있게 한다.

**Architecture:** ROS 를 모르는 순수 계산 라이브러리 `vcc_core` 와 얇은 nav2_core 어댑터 `.so` 로 나눈다. 모양은 `vica_nav2_bt_plugins` 와 같다.
- 한 주기의 흐름: 거리장 → 차선 고르기 → 상황 판단(주행/유턴/도착 정렬/대기) → 공용 출력단.
- 모든 판단은 gtest 로 먼저 고정한다.

**Tech Stack:** C++17, ROS 2 Humble(Nav2 1.1.20: nav2_core, nav2_costmap_2d, nav2_util, pluginlib), ament_cmake, gtest, pytest(계약 시험)

**Spec:** `docs/superpowers/specs/2026-09-24-vcc-controller-design.md` (루트 저장소). 코드는 `vica_ros2_ws` 저장소에 쓴다.

## Global Constraints

- 두 저장소 모두 브랜치 `feat/vica_customized_controller` 에서만 커밋한다. push 하지 않는다.
- 새 ROS 노드는 만들지 않는다. VCC 는 `controller_server` 안에서 돈다.
- 후진 명령은 없다. `v` 는 항상 `[0, 0.5]` 이다.
- 회전 명령은 `|w| ≤ 0.5` 로 좌우 대칭이다.
- 예외는 `nav2_core::PlannerException` 만 던진다(`std::runtime_error` 금지: failure_tolerance 를 건너뛴다).
- 몸통 충돌은 항상 footprint 전체로 검사한다. 판정은 local costmap 의 LETHAL(254) 기준이며 inflation 비용은 쓰지 않는다.
- NO_INFORMATION(255) 은 충돌로 보지 않는다(RPP 1.1.20 규칙).
- 바꾸지 않는 설정:
  - footprint·padding 0.05, inflation 0.55 / 3.5
  - goal checker 0.25 / 0.25 / 0.03 / 0.05 / stateful False
  - planner·route 설정
  - collision_monitor
  - velocity_smoother
  - failure_tolerance 10, controller_frequency 10
  - BT xml
- 빌드는 반드시 `colcon build --packages-select <pkg>` 로 한다(전체 빌드 금지: 다른 세션 설치본 소실 함정).
- ros2 CLI 를 `timeout` 으로 감싸지 않는다. `/dev/shm` 은 건드리지 않는다.
- 로봇을 움직이는 시험은 이 계획에 없다. 바퀴 띄운 시험과 실주행은 사용자가 한다(AGENTS.md §4).
- 주석·커밋 메시지는 한국어이며, 기존 문체(평서형 "~다")를 따른다. 커밋 끝에 다음 두 줄을 붙인다.
  ```
  Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01EQr7nT17VwBmqKhRyKscpi
  ```
- RPP 에서 가져온 코드(`transformGlobalPlan`, `circleSegmentIntersection`)가 들어간 파일은 Apache 2.0 저작권 머리말을 유지하고 "VICA 수정" 표시를 붙인다.

## Review Focus

1. **레일과 나란히 0.5~0.6 m 떨어진 저속 주행**: 유턴으로 들어가지 않고 곡선으로 합류해야 한다(요구 3). 조준점 각만 보면 66° 로 오판한다.
   → Task 10·11 에 "평행 이탈 시 Turn 금지" 시험을 넣는다.
2. **collision_monitor·예외로 실제 속도가 0 이 된 뒤 재출발**: 출력단이 옛 명령(0.4 m/s)에서 이어 가면 출발이 튄다.
   → Task 5 에 "측정 속도로 재동기화" 시험을 넣는다.
3. **도착 정렬 3회 실패 뒤 같은 goal 재시도**: 코어가 Hold 에 영원히 갇힐 수 있다.
   → Task 12 에 "0.5 s 넘게 호출이 끊기면 코어 초기화" 시험을 넣는다.
4. **초음파 한 번 튄 값**: 한 번만 가까이 찍힌 값은 무시해야 한다(요구 4 "너무 예민하지 않게").
   → Task 6 에 "연속 2회 불일치 거부" 시험을 넣는다.
5. **두 차선 점수가 거의 같을 때의 흔들림**: 차선이 매 주기 바뀌면 MPPI 식 비틀거림이 된다.
   → Task 7 에 "잡음 50주기 동안 전환 ≤ 1회" 시험을 넣는다.

## 파일 구조

```
vica_ros2_ws/src/vica_vcc_controller/
  package.xml
  CMakeLists.txt
  vcc_plugins.xml                         pluginlib 등록
  include/vica_vcc_controller/
    core/types.hpp                        Point2D·Pose2D·Twist2D·좌표 변환
    core/geometry.hpp                     footprint 부풀리기·다각형 거리·유턴 폭
    core/clearance.hpp                    LETHAL 거리장 + 몸 여유
    core/pure_pursuit.hpp                 조준점·곡률·차선 평행이동 경로
    core/speed_profile.hpp                코너 미리보기·근접·도착 감속
    core/output_stage.hpp                 공용 출력단(가감속·회전 한계)
    core/ultrasonic.hpp                   초음파 확인·호 점 변환
    core/lanes.hpp                        차선 13개 채점·줏대·복귀
    core/turn_planner.hpp                 유턴 방식 고르기
    core/align_planner.hpp                도착 한 번 회전·넘침 보정
    core/state_machine.hpp                상황 4개·전환표
    core/vcc_core.hpp                     한 주기 조립
    vcc_controller.hpp                    nav2_core::Controller 어댑터
  src/core/*.cpp                          (위 헤더 하나당 하나, types 제외)
  src/vcc_controller.cpp
  test/test_*.cpp                         core gtest + 플러그인 적재 시험
  test/bench_vcc_core.cpp                 젯슨 한 주기 시간 측정(실행 파일)
```

수정:

- `vica_ros2_ws/src/vica_nav2/config/nav2_params.yaml`
  - `FollowPath` 를 VCC 로 바꾸고, RPP 는 `FollowPathRPP` 로 보존한다.
  - range 층 4개를 끈다.
- `vica_ros2_ws/src/vica_nav2/package.xml`: `exec_depend vica_vcc_controller`
- `vica_ros2_ws/src/vica_nav2/test/test_nav2_params_contract.py`, `test_planner_contract.py`: VCC 분기를 추가한다.

공통 명령(모든 Task):

```bash
cd ~/VICA-smarthandle/vica_ros2_ws && source /opt/ros/humble/setup.bash
colcon build --packages-select vica_vcc_controller
colcon test --packages-select vica_vcc_controller --ctest-args -R <시험이름> ; colcon test-result --verbose --test-result-base build/vica_vcc_controller
```

---

### Task 1: 패키지 뼈대 + 기본 형·기하

**Files:**
- Create: `vica_ros2_ws/src/vica_vcc_controller/package.xml`
- Create: `vica_ros2_ws/src/vica_vcc_controller/CMakeLists.txt`
- Create: `vica_ros2_ws/src/vica_vcc_controller/include/vica_vcc_controller/core/types.hpp`
- Create: `vica_ros2_ws/src/vica_vcc_controller/include/vica_vcc_controller/core/geometry.hpp`
- Create: `vica_ros2_ws/src/vica_vcc_controller/src/core/geometry.cpp`
- Test: `vica_ros2_ws/src/vica_vcc_controller/test/test_geometry.cpp`

**Interfaces:**
- Produces:
  - `struct Point2D{double x,y;}`, `struct Pose2D{double x,y,yaw;}`, `struct Twist2D{double v,w;}`
  - `using Polygon = std::vector<Point2D>`, `using Path = std::vector<Pose2D>`
  - `double normalizeAngle(double)`
  - `Point2D toParent(const Pose2D&, const Point2D&)`, `Pose2D toParent(const Pose2D&, const Pose2D&)`, `Point2D toChild(const Pose2D&, const Point2D&)`
  - `Polygon padFootprint(const Polygon&, double)`, `double circumscribedRadius(const Polygon&)`, `Polygon densifyOutline(const Polygon&, double step)`
  - `bool pointInPolygon(const Point2D&, const Polygon&)`, `double signedDistanceToPolygon(const Point2D&, const Polygon&)`, `Polygon transformPolygon(const Pose2D&, const Polygon&)`
  - `std::pair<double,double> sweptLateralExtent(const Polygon& fp, double radius, double angle, int steps)`, `double uturnSweptWidth(const Polygon&, double radius, double angle, int steps)`
  - 모든 이름공간은 `vica_vcc_controller::core`

- [ ] **Step 1: 패키지 파일 작성**

`package.xml`:

```xml
<?xml version="1.0"?>
<?xml-model href="http://download.ros.org/schema/package_format3.xsd" schematypens="http://www.w3.org/2001/XMLSchema"?>
<package format="3">
  <name>vica_vcc_controller</name>
  <version>0.1.0</version>
  <description>
    VCC(VICA Customized Controller) — Nav2 FollowPath 컨트롤러 플러그인.
    레일 추종(RPP 식 조준) + 차선 13개 고르기(비켜 가기) + 상황 4개(주행/유턴/도착 정렬/대기).
    ROS 노드가 아니라 controller_server 가 여는 공유 라이브러리다.
    설계: VICA-smarthandle docs/superpowers/specs/2026-09-24-vcc-controller-design.md
  </description>
  <maintainer email="mjw41177@gmail.com">ji_w</maintainer>
  <license>Apache-2.0</license>

  <buildtool_depend>ament_cmake</buildtool_depend>
  <depend>rclcpp</depend>
  <depend>rclcpp_lifecycle</depend>
  <depend>pluginlib</depend>
  <depend>nav2_core</depend>
  <depend>nav2_costmap_2d</depend>
  <depend>nav2_util</depend>
  <depend>nav_msgs</depend>
  <depend>geometry_msgs</depend>
  <depend>sensor_msgs</depend>
  <depend>std_msgs</depend>
  <depend>tf2</depend>
  <depend>tf2_ros</depend>
  <depend>tf2_geometry_msgs</depend>

  <test_depend>ament_cmake_gtest</test_depend>

  <export>
    <build_type>ament_cmake</build_type>
    <nav2_core plugin="${prefix}/vcc_plugins.xml"/>
  </export>
</package>
```

`CMakeLists.txt` (이 Task 에서는 core 와 test_geometry 만, 이후 Task 가 줄을 더한다):

```cmake
cmake_minimum_required(VERSION 3.8)
project(vica_vcc_controller)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

find_package(ament_cmake REQUIRED)

# 순수 계산은 ROS 에 의존하지 않는다 — 시험이 노드·TF 없이 돈다(vica_nav2_bt_plugins 와 같은 모양).
add_library(vcc_core STATIC
  src/core/geometry.cpp
)
target_include_directories(vcc_core PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>)
target_compile_features(vcc_core PUBLIC cxx_std_17)
set_target_properties(vcc_core PROPERTIES POSITION_INDEPENDENT_CODE ON)

install(TARGETS vcc_core ARCHIVE DESTINATION lib LIBRARY DESTINATION lib RUNTIME DESTINATION bin)
install(DIRECTORY include/ DESTINATION include)

if(BUILD_TESTING)
  find_package(ament_cmake_gtest REQUIRED)
  ament_add_gtest(test_geometry test/test_geometry.cpp)
  target_link_libraries(test_geometry vcc_core)
endif()

ament_package()
```

- [ ] **Step 2: 실패하는 시험 작성** — `test/test_geometry.cpp`

```cpp
#include <gtest/gtest.h>
#include <cmath>
#include "vica_vcc_controller/core/geometry.hpp"

using namespace vica_vcc_controller::core;

namespace
{
// nav2_params.yaml local_costmap.footprint (2026-09-15 base_link 구동륜 축 이동 뒤 값)
const Polygon kFootprint{{0.151, 0.225}, {0.151, -0.225}, {-0.459, -0.225},
  {-0.569, -0.035}, {-0.569, 0.035}, {-0.459, 0.225}};
}  // namespace

TEST(Types, ToParentAndToChildAreInverse)
{
  const Pose2D frame{1.0, 2.0, 0.7};
  const Point2D p{0.3, -0.4};
  const Point2D back = toChild(frame, toParent(frame, p));
  EXPECT_NEAR(back.x, p.x, 1e-12);
  EXPECT_NEAR(back.y, p.y, 1e-12);
  EXPECT_NEAR(normalizeAngle(3.0 * M_PI), M_PI, 1e-12);
}

TEST(Geometry, PaddingFollowsNav2SignRule)
{
  const Polygon p = padFootprint(kFootprint, 0.05);
  EXPECT_NEAR(p[0].x, 0.201, 1e-9);
  EXPECT_NEAR(p[0].y, 0.275, 1e-9);
  EXPECT_NEAR(p[3].x, -0.619, 1e-9);
  EXPECT_NEAR(p[3].y, -0.085, 1e-9);
}

TEST(Geometry, CircumscribedRadiusMatchesInPlaceWidth)
{
  // 설계서 3.3: 제자리 회전 필요폭 1.250 m = 2 x 0.6248
  EXPECT_NEAR(circumscribedRadius(padFootprint(kFootprint, 0.05)), 0.6248, 0.001);
}

TEST(Geometry, UturnWidthTableOfSpec)
{
  // 설계서 3.3 표를 그대로 재현한다(몸 윤곽을 0.5도 간격으로 쓸어 계산)
  const Polygon fp = padFootprint(kFootprint, 0.05);
  EXPECT_NEAR(uturnSweptWidth(fp, 0.0, M_PI, 360), 0.965, 0.01);
  EXPECT_NEAR(uturnSweptWidth(fp, 0.1, M_PI, 360), 1.072, 0.01);
  EXPECT_NEAR(uturnSweptWidth(fp, 0.2, M_PI, 360), 1.212, 0.01);
  EXPECT_NEAR(uturnSweptWidth(fp, 0.5, M_PI, 360), 1.728, 0.01);
}

TEST(Geometry, SignedDistanceIsNegativeInside)
{
  const Polygon sq{{-1, -1}, {1, -1}, {1, 1}, {-1, 1}};
  EXPECT_NEAR(signedDistanceToPolygon({0.0, 0.0}, sq), -1.0, 1e-9);
  EXPECT_NEAR(signedDistanceToPolygon({2.0, 0.0}, sq), 1.0, 1e-9);
  EXPECT_TRUE(pointInPolygon({0.5, 0.5}, sq));
  EXPECT_FALSE(pointInPolygon({1.5, 0.5}, sq));
}
```

- [ ] **Step 3: 빌드해서 실패 확인**

Run: `colcon build --packages-select vica_vcc_controller`
Expected: FAIL — `vica_vcc_controller/core/geometry.hpp: No such file`

- [ ] **Step 4: 구현** — `core/types.hpp`

```cpp
#pragma once
#include <cmath>
#include <vector>

namespace vica_vcc_controller::core
{
struct Point2D { double x{0.0}; double y{0.0}; };
struct Pose2D { double x{0.0}; double y{0.0}; double yaw{0.0}; };
struct Twist2D { double v{0.0}; double w{0.0}; };
using Polygon = std::vector<Point2D>;
using Path = std::vector<Pose2D>;

inline double normalizeAngle(double a) { return std::atan2(std::sin(a), std::cos(a)); }

// frame 안의 좌표 p 를 frame 의 부모 좌표로 옮긴다.
inline Point2D toParent(const Pose2D & frame, const Point2D & p)
{
  const double c = std::cos(frame.yaw), s = std::sin(frame.yaw);
  return {frame.x + c * p.x - s * p.y, frame.y + s * p.x + c * p.y};
}
inline Pose2D toParent(const Pose2D & frame, const Pose2D & p)
{
  const Point2D q = toParent(frame, Point2D{p.x, p.y});
  return {q.x, q.y, normalizeAngle(frame.yaw + p.yaw)};
}
// 부모 좌표 p 를 frame 안의 좌표로 옮긴다.
inline Point2D toChild(const Pose2D & frame, const Point2D & p)
{
  const double dx = p.x - frame.x, dy = p.y - frame.y;
  const double c = std::cos(frame.yaw), s = std::sin(frame.yaw);
  return {c * dx + s * dy, -s * dx + c * dy};
}
}  // namespace vica_vcc_controller::core
```

`core/geometry.hpp`:

```cpp
#pragma once
#include <utility>
#include "vica_vcc_controller/core/types.hpp"

namespace vica_vcc_controller::core
{
// nav2_costmap_2d::padFootprint 와 같은 규칙: 각 꼭짓점을 부호 방향으로 padding 만큼 민다.
Polygon padFootprint(const Polygon & fp, double padding);
double circumscribedRadius(const Polygon & fp);
// 윤곽을 step 간격 점으로 바꾼다(꼭짓점 포함).
Polygon densifyOutline(const Polygon & fp, double step);
bool pointInPolygon(const Point2D & p, const Polygon & poly);
double pointToSegmentDistance(const Point2D & p, const Point2D & a, const Point2D & b);
// 다각형 윤곽까지 거리. 안쪽이면 음수.
double signedDistanceToPolygon(const Point2D & p, const Polygon & poly);
Polygon transformPolygon(const Pose2D & pose, const Polygon & poly);
// 왼쪽으로 반지름 radius(0 = 제자리) 호를 angle 만큼 돌 때 몸이 쓰는 옆(y) 범위 [lo, hi].
std::pair<double, double> sweptLateralExtent(
  const Polygon & fp, double radius, double angle, int steps);
double uturnSweptWidth(const Polygon & fp, double radius, double angle, int steps);
}  // namespace vica_vcc_controller::core
```

`src/core/geometry.cpp`:

```cpp
#include "vica_vcc_controller/core/geometry.hpp"

#include <algorithm>
#include <cmath>
#include <limits>

namespace vica_vcc_controller::core
{
namespace
{
double sign0(double v) { return v > 0.0 ? 1.0 : (v < 0.0 ? -1.0 : 0.0); }
}  // namespace

Polygon padFootprint(const Polygon & fp, double padding)
{
  Polygon out;
  out.reserve(fp.size());
  for (const auto & p : fp) {
    out.push_back({p.x + sign0(p.x) * padding, p.y + sign0(p.y) * padding});
  }
  return out;
}

double circumscribedRadius(const Polygon & fp)
{
  double r = 0.0;
  for (const auto & p : fp) {r = std::max(r, std::hypot(p.x, p.y));}
  return r;
}

Polygon densifyOutline(const Polygon & fp, double step)
{
  Polygon out;
  const size_t n = fp.size();
  for (size_t i = 0; i < n; ++i) {
    const Point2D & a = fp[i];
    const Point2D & b = fp[(i + 1) % n];
    const double len = std::hypot(b.x - a.x, b.y - a.y);
    const int k = std::max(1, static_cast<int>(std::ceil(len / step)));
    for (int j = 0; j < k; ++j) {
      const double t = static_cast<double>(j) / k;
      out.push_back({a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t});
    }
  }
  return out;
}

bool pointInPolygon(const Point2D & p, const Polygon & poly)
{
  bool inside = false;
  const size_t n = poly.size();
  for (size_t i = 0, j = n - 1; i < n; j = i++) {
    const Point2D & a = poly[i];
    const Point2D & b = poly[j];
    if (((a.y > p.y) != (b.y > p.y)) &&
      (p.x < (b.x - a.x) * (p.y - a.y) / (b.y - a.y) + a.x))
    {
      inside = !inside;
    }
  }
  return inside;
}

double pointToSegmentDistance(const Point2D & p, const Point2D & a, const Point2D & b)
{
  const double dx = b.x - a.x, dy = b.y - a.y;
  const double l2 = dx * dx + dy * dy;
  double t = l2 > 0.0 ? ((p.x - a.x) * dx + (p.y - a.y) * dy) / l2 : 0.0;
  t = std::clamp(t, 0.0, 1.0);
  return std::hypot(p.x - (a.x + t * dx), p.y - (a.y + t * dy));
}

double signedDistanceToPolygon(const Point2D & p, const Polygon & poly)
{
  double d = std::numeric_limits<double>::infinity();
  const size_t n = poly.size();
  for (size_t i = 0; i < n; ++i) {
    d = std::min(d, pointToSegmentDistance(p, poly[i], poly[(i + 1) % n]));
  }
  return pointInPolygon(p, poly) ? -d : d;
}

Polygon transformPolygon(const Pose2D & pose, const Polygon & poly)
{
  Polygon out;
  out.reserve(poly.size());
  for (const auto & p : poly) {out.push_back(toParent(pose, p));}
  return out;
}

std::pair<double, double> sweptLateralExtent(
  const Polygon & fp, double radius, double angle, int steps)
{
  const Polygon outline = densifyOutline(fp, 0.01);
  double lo = std::numeric_limits<double>::infinity();
  double hi = -lo;
  for (int i = 0; i <= steps; ++i) {
    const double th = angle * i / steps;
    const Pose2D pose{radius * std::sin(th), radius - radius * std::cos(th), th};
    for (const auto & q : outline) {
      const Point2D g = toParent(pose, q);
      lo = std::min(lo, g.y);
      hi = std::max(hi, g.y);
    }
  }
  return {lo, hi};
}

double uturnSweptWidth(const Polygon & fp, double radius, double angle, int steps)
{
  const auto [lo, hi] = sweptLateralExtent(fp, radius, angle, steps);
  return hi - lo;
}
}  // namespace vica_vcc_controller::core
```

- [ ] **Step 5: 빌드·시험 통과 확인**

Run: `colcon build --packages-select vica_vcc_controller && colcon test --packages-select vica_vcc_controller --ctest-args -R test_geometry; colcon test-result --verbose --test-result-base build/vica_vcc_controller`
Expected: `test_geometry` 5개 모두 PASS

- [ ] **Step 6: 커밋**

```bash
cd ~/VICA-smarthandle/vica_ros2_ws
git add src/vica_vcc_controller
git commit -m "feat(vcc): 자작 컨트롤러 VCC 패키지 뼈대와 기하 계산 — 유턴 폭 표 재현 시험 포함"
```
(커밋 본문 끝에 Global Constraints 의 두 줄을 붙인다. 이하 모든 커밋 같음.)

---

### Task 2: 거리장과 몸 여유 (`ClearanceGrid`, `ClearanceField`)

**Files:**
- Create: `include/vica_vcc_controller/core/clearance.hpp`, `src/core/clearance.cpp`
- Test: `test/test_clearance.cpp`
- Modify: `CMakeLists.txt` (vcc_core 에 `src/core/clearance.cpp` 추가, `test_clearance` 추가)

**Interfaces:**
- Consumes: Task 1 의 `Polygon`, `Pose2D`, `transformPolygon`, `densifyOutline`, `pointInPolygon`, `signedDistanceToPolygon`, `circumscribedRadius`
- Produces:
  - `class ClearanceGrid`
    - `reset(double ox, double oy, double res, int w, int h)`, `markLethal(int ix, int iy)`, `compute()`
    - `double distanceAt(double wx, double wy) const`: 빈 곳이나 창 밖이면 `kFarDistance` = 10.0
    - `bool worldToCell(double, double, int&, int&) const`, `bool lethalCell(int, int) const`
    - `double resolution() const`, `double originX() const`, `double originY() const`
  - `using ClearanceFn = std::function<double(const Pose2D &)>`
  - `class ClearanceField`
    - `setFootprint(const Polygon & padded, double outline_step = 0.05)`
    - `ClearanceGrid & grid()`
    - `setPoints(std::vector<Point2D> pts)`
    - `double clearance(const Pose2D & pose) const`: 그리드 좌표계 자세. 음수면 접촉.

- [ ] **Step 1: 실패하는 시험** — `test/test_clearance.cpp`

```cpp
#include <gtest/gtest.h>
#include <cmath>
#include "vica_vcc_controller/core/clearance.hpp"
#include "vica_vcc_controller/core/geometry.hpp"

using namespace vica_vcc_controller::core;

namespace
{
const Polygon kFootprint{{0.151, 0.225}, {0.151, -0.225}, {-0.459, -0.225},
  {-0.569, -0.035}, {-0.569, 0.035}, {-0.459, 0.225}};

// 원점 중심 5 x 5 m, 0.05 m 격자
ClearanceField makeField()
{
  ClearanceField f;
  f.setFootprint(padFootprint(kFootprint, 0.05));
  f.grid().reset(-2.5, -2.5, 0.05, 100, 100);
  return f;
}
void markRectangle(ClearanceField & f, double x0, double x1, double y0, double y1)
{
  for (int ix = 0; ix < 100; ++ix) {
    for (int iy = 0; iy < 100; ++iy) {
      const double cx = -2.5 + (ix + 0.5) * 0.05, cy = -2.5 + (iy + 0.5) * 0.05;
      if (cx >= x0 && cx <= x1 && cy >= y0 && cy <= y1) {f.grid().markLethal(ix, iy);}
    }
  }
  f.grid().compute();
}
}  // namespace

TEST(Clearance, EmptyWorldIsFar)
{
  ClearanceField f = makeField();
  f.grid().compute();
  EXPECT_GT(f.clearance({0, 0, 0}), 5.0);
}

TEST(Clearance, WallBesideRobotMeasuresFromBodyEdge)
{
  // 셀 중심 y = 1.025 줄이 벽. 몸 옆면(padding 포함) y = 0.275.
  ClearanceField f = makeField();
  markRectangle(f, -2.5, 2.5, 1.0, 1.05);
  EXPECT_NEAR(f.clearance({0, 0, 0}), 1.025 - 0.275 - 0.025, 0.04);
  // 90도 돌면 앞면(0.201)이 벽을 본다
  EXPECT_NEAR(f.clearance({0, 0, M_PI / 2}), 1.025 - 0.201 - 0.025, 0.04);
}

TEST(Clearance, LethalInsideBodyIsContact)
{
  ClearanceField f = makeField();
  markRectangle(f, -0.1, 0.0, -0.05, 0.05);   // 몸 한가운데 작은 물체
  EXPECT_LT(f.clearance({0, 0, 0}), 0.0);
}

TEST(Clearance, InflationSizedGapHasNoBlindSpot)
{
  // backlog NAV2-B3: 벽에서 0.55~0.625 떨어진 띠는 inflation 비용 0 이라 비용 기반 검사가 몸통을 건너뛴다.
  // 몸 뒤쪽 모서리가 벽에 닿는 자세를 만들고, 중심은 벽에서 0.58 m 떨어뜨린다.
  ClearanceField f = makeField();
  markRectangle(f, -2.5, 2.5, 0.575, 0.625);  // 벽 셀 중심 ≈ 0.575~0.625
  // 90도 회전하면 뒤쪽 꼭짓점(-0.619)이 +y 쪽으로 간다 → 벽을 뚫는다
  EXPECT_LT(f.clearance({0, 0, -M_PI / 2}), 0.0);
}

TEST(Clearance, UltrasonicPointsCountAsObstacles)
{
  ClearanceField f = makeField();
  f.grid().compute();
  f.setPoints({{0.5, 0.0}});
  EXPECT_NEAR(f.clearance({0, 0, 0}), 0.5 - 0.201, 1e-6);
  f.setPoints({{0.0, 0.0}});
  EXPECT_LT(f.clearance({0, 0, 0}), 0.0);
}
```

- [ ] **Step 2: 실패 확인**

Run: `colcon build --packages-select vica_vcc_controller`
Expected: FAIL — `clearance.hpp: No such file`

- [ ] **Step 3: 구현** — `core/clearance.hpp`

```cpp
#pragma once
#include <cstdint>
#include <functional>
#include <vector>
#include "vica_vcc_controller/core/types.hpp"

namespace vica_vcc_controller::core
{
// local costmap 의 LETHAL 칸만 모아 만든 거리장. inflation 비용은 쓰지 않는다(설계서 3.4).
class ClearanceGrid
{
public:
  static constexpr double kFarDistance = 10.0;
  void reset(double origin_x, double origin_y, double resolution, int width, int height);
  void markLethal(int ix, int iy);
  // chamfer(1, sqrt2) 2-pass 거리 변환
  void compute();
  double distanceAt(double wx, double wy) const;
  bool worldToCell(double wx, double wy, int & ix, int & iy) const;
  bool lethalCell(int ix, int iy) const;
  double resolution() const {return res_;}
  double originX() const {return ox_;}
  double originY() const {return oy_;}

private:
  size_t idx(int x, int y) const {return static_cast<size_t>(y) * w_ + x;}
  double ox_{0.0}, oy_{0.0}, res_{0.05};
  int w_{0}, h_{0};
  std::vector<uint8_t> lethal_;
  std::vector<float> dist_;
};

using ClearanceFn = std::function<double(const Pose2D &)>;

// 몸(padding 포함 footprint) 전체와 장애물 사이의 최소 여유.
class ClearanceField
{
public:
  void setFootprint(const Polygon & padded, double outline_step = 0.05);
  ClearanceGrid & grid() {return grid_;}
  const ClearanceGrid & grid() const {return grid_;}
  // 초음파 점(그리드 좌표계)
  void setPoints(std::vector<Point2D> pts) {points_ = std::move(pts);}
  // pose 는 그리드 좌표계. 음수 = 몸 안에 장애물(접촉).
  double clearance(const Pose2D & pose) const;

private:
  Polygon footprint_;
  Polygon outline_;
  double radius_{0.0};
  ClearanceGrid grid_;
  std::vector<Point2D> points_;
};
}  // namespace vica_vcc_controller::core
```

`src/core/clearance.cpp`:

```cpp
#include "vica_vcc_controller/core/clearance.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include "vica_vcc_controller/core/geometry.hpp"

namespace vica_vcc_controller::core
{
namespace
{
constexpr float kFar = 1e6f;
}

void ClearanceGrid::reset(double ox, double oy, double res, int w, int h)
{
  ox_ = ox; oy_ = oy; res_ = res; w_ = w; h_ = h;
  lethal_.assign(static_cast<size_t>(w) * h, 0);
  dist_.assign(static_cast<size_t>(w) * h, kFar);
}

void ClearanceGrid::markLethal(int ix, int iy)
{
  if (ix < 0 || iy < 0 || ix >= w_ || iy >= h_) {return;}
  lethal_[idx(ix, iy)] = 1;
}

void ClearanceGrid::compute()
{
  const float a = 1.0f, b = std::sqrt(2.0f);
  for (size_t i = 0; i < dist_.size(); ++i) {dist_[i] = lethal_[i] ? 0.0f : kFar;}
  for (int y = 0; y < h_; ++y) {
    for (int x = 0; x < w_; ++x) {
      float & d = dist_[idx(x, y)];
      if (d == 0.0f) {continue;}
      if (x > 0) {d = std::min(d, dist_[idx(x - 1, y)] + a);}
      if (y > 0) {
        d = std::min(d, dist_[idx(x, y - 1)] + a);
        if (x > 0) {d = std::min(d, dist_[idx(x - 1, y - 1)] + b);}
        if (x < w_ - 1) {d = std::min(d, dist_[idx(x + 1, y - 1)] + b);}
      }
    }
  }
  for (int y = h_ - 1; y >= 0; --y) {
    for (int x = w_ - 1; x >= 0; --x) {
      float & d = dist_[idx(x, y)];
      if (d == 0.0f) {continue;}
      if (x < w_ - 1) {d = std::min(d, dist_[idx(x + 1, y)] + a);}
      if (y < h_ - 1) {
        d = std::min(d, dist_[idx(x, y + 1)] + a);
        if (x < w_ - 1) {d = std::min(d, dist_[idx(x + 1, y + 1)] + b);}
        if (x > 0) {d = std::min(d, dist_[idx(x - 1, y + 1)] + b);}
      }
    }
  }
}

bool ClearanceGrid::worldToCell(double wx, double wy, int & ix, int & iy) const
{
  ix = static_cast<int>(std::floor((wx - ox_) / res_));
  iy = static_cast<int>(std::floor((wy - oy_) / res_));
  return ix >= 0 && iy >= 0 && ix < w_ && iy < h_;
}

bool ClearanceGrid::lethalCell(int ix, int iy) const
{
  if (ix < 0 || iy < 0 || ix >= w_ || iy >= h_) {return false;}
  return lethal_[idx(ix, iy)] != 0;
}

double ClearanceGrid::distanceAt(double wx, double wy) const
{
  int ix, iy;
  if (!worldToCell(wx, wy, ix, iy)) {return kFarDistance;}
  const float d = dist_[idx(ix, iy)];
  if (d >= kFar) {return kFarDistance;}
  return static_cast<double>(d) * res_;
}

void ClearanceField::setFootprint(const Polygon & padded, double outline_step)
{
  footprint_ = padded;
  outline_ = densifyOutline(padded, outline_step);
  radius_ = circumscribedRadius(padded);
}

double ClearanceField::clearance(const Pose2D & pose) const
{
  const Polygon poly = transformPolygon(pose, footprint_);

  // 1. 몸 안에 LETHAL 칸 중심이 있으면 접촉
  double minx = poly[0].x, maxx = minx, miny = poly[0].y, maxy = miny;
  for (const auto & p : poly) {
    minx = std::min(minx, p.x); maxx = std::max(maxx, p.x);
    miny = std::min(miny, p.y); maxy = std::max(maxy, p.y);
  }
  int ix0, iy0, ix1, iy1;
  grid_.worldToCell(minx, miny, ix0, iy0);
  grid_.worldToCell(maxx, maxy, ix1, iy1);
  const double res = grid_.resolution();
  for (int ix = ix0; ix <= ix1; ++ix) {
    for (int iy = iy0; iy <= iy1; ++iy) {
      if (!grid_.lethalCell(ix, iy)) {continue;}
      const Point2D c{grid_.originX() + (ix + 0.5) * res, grid_.originY() + (iy + 0.5) * res};
      if (pointInPolygon(c, poly)) {return -1.0;}
    }
  }

  // 2. 윤곽 표본에서 가장 가까운 LETHAL 칸까지(칸 반 폭만큼 보수적으로 뺀다)
  double c = std::numeric_limits<double>::infinity();
  for (const auto & q : outline_) {
    const Point2D g = toParent(pose, q);
    c = std::min(c, grid_.distanceAt(g.x, g.y) - 0.5 * res);
  }

  // 3. 초음파 점
  for (const auto & p : points_) {
    if (std::hypot(p.x - pose.x, p.y - pose.y) > radius_ + 2.0) {continue;}
    c = std::min(c, signedDistanceToPolygon(p, poly));
  }
  return c;
}
}  // namespace vica_vcc_controller::core
```

`CMakeLists.txt` 수정:
- `add_library(vcc_core STATIC ...)` 목록에 `src/core/clearance.cpp` 를 추가한다.
- `if(BUILD_TESTING)` 안에 다음을 추가한다.

```cmake
  ament_add_gtest(test_clearance test/test_clearance.cpp)
  target_link_libraries(test_clearance vcc_core)
```

- [ ] **Step 4: 통과 확인**

Run: `colcon build --packages-select vica_vcc_controller && colcon test --packages-select vica_vcc_controller --ctest-args -R test_clearance; colcon test-result --verbose --test-result-base build/vica_vcc_controller`
Expected: 5개 PASS

- [ ] **Step 5: 커밋** — `git commit -m "feat(vcc): LETHAL 거리장과 몸 전체 여유 계산 — inflation 사각지대 없음을 시험으로 고정"`

---

### Task 3: 조준점·곡률·차선 경로 (`pure_pursuit`)

**Files:**
- Create: `include/vica_vcc_controller/core/pure_pursuit.hpp`, `src/core/pure_pursuit.cpp`
- Test: `test/test_pure_pursuit.cpp`
- Modify: `CMakeLists.txt` (소스·시험 추가)

**Interfaces:**
- Consumes: `Path`, `Pose2D`, `Point2D`
- Produces:
  - `struct LookaheadParams{double time=2.5, min_dist=0.6, max_dist=1.2;}`
  - `double lookaheadDistance(double v, const LookaheadParams&)`
  - `double pathLength(const Path&)`, `Path pathPrefix(const Path&, double length)`
  - `Point2D carrotOnPath(const Path& robot_frame_path, double L)`
  - `double carrotTangent(const Path&, double L)`: 조준점이 놓인 구간의 방향(rad)
  - `double curvatureTo(const Point2D&)`
  - `Path offsetPath(const Path&, double d_start, double d_end, double transition_len)`: 왼쪽이 + 이고, transition_len 동안 **일정 기울기**로 옮긴다.
    - smoothstep 은 가운데 기울기가 평균의 1.5배라, 손잡이 좌우 속도 상한(lane_rate)을 넘는다.

- [ ] **Step 1: 실패하는 시험** — `test/test_pure_pursuit.cpp`

```cpp
#include <gtest/gtest.h>
#include <cmath>
#include "vica_vcc_controller/core/pure_pursuit.hpp"

using namespace vica_vcc_controller::core;

namespace
{
Path straight(double y, double length = 3.0)
{
  Path p;
  for (double x = 0.0; x <= length + 1e-9; x += 0.05) {p.push_back({x, y, 0.0});}
  return p;
}
}  // namespace

TEST(PurePursuit, LookaheadIsClampedVelocityTimesTime)
{
  LookaheadParams lp;
  EXPECT_NEAR(lookaheadDistance(0.0, lp), 0.6, 1e-9);
  EXPECT_NEAR(lookaheadDistance(0.44, lp), 1.1, 1e-9);   // run36: 순항 0.44 m/s -> 1.10 m
  EXPECT_NEAR(lookaheadDistance(0.5, lp), 1.2, 1e-9);
}

TEST(PurePursuit, CarrotIsExactlyLookaheadAwayOnStraight)
{
  const Point2D c = carrotOnPath(straight(0.0), 1.0);
  EXPECT_NEAR(c.x, 1.0, 1e-6);
  EXPECT_NEAR(c.y, 0.0, 1e-6);
  EXPECT_NEAR(curvatureTo(c), 0.0, 1e-9);
}

TEST(PurePursuit, CarrotFallsBackToLastPoint)
{
  const Point2D c = carrotOnPath(straight(0.0, 0.3), 1.0);
  EXPECT_NEAR(c.x, 0.3, 1e-6);
}

TEST(PurePursuit, CurvatureTowardsOffsetRail)
{
  // 레일이 왼쪽 0.3 m -> 왼쪽(+)으로 도는 곡률
  const Point2D c = carrotOnPath(straight(0.3), 1.0);
  EXPECT_GT(curvatureTo(c), 0.0);
  EXPECT_NEAR(carrotTangent(straight(0.3), 1.0), 0.0, 1e-6);
}

TEST(PurePursuit, OffsetPathShiftsLinearlyToTheLeft)
{
  const Path base = straight(0.0);
  const Path p = offsetPath(base, 0.0, 0.3, 1.5);
  EXPECT_NEAR(p.front().y, 0.0, 1e-9);
  EXPECT_NEAR(p.back().y, 0.3, 1e-9);
  // 가운데(0.75 m)에서 절반
  const size_t mid = static_cast<size_t>(0.75 / 0.05);
  EXPECT_NEAR(p[mid].y, 0.15, 0.01);
  // 옆 이동이 단조 증가(되돌아가지 않음)
  for (size_t i = 1; i < p.size(); ++i) {EXPECT_GE(p[i].y + 1e-12, p[i - 1].y);}
}

TEST(PurePursuit, PrefixStopsAtLength)
{
  const Path p = pathPrefix(straight(0.0), 1.0);
  EXPECT_NEAR(pathLength(p), 1.0, 0.051);
}
```

- [ ] **Step 2: 실패 확인** — Run: `colcon build --packages-select vica_vcc_controller` / Expected: FAIL (헤더 없음)

- [ ] **Step 3: 구현** — `core/pure_pursuit.hpp`

```cpp
#pragma once
#include "vica_vcc_controller/core/types.hpp"

namespace vica_vcc_controller::core
{
struct LookaheadParams
{
  double time{2.5};      // nav2_params RPP lookahead_time
  double min_dist{0.6};  // run39
  double max_dist{1.2};  // run36
};

double lookaheadDistance(double v, const LookaheadParams & p);
double pathLength(const Path & path);
// 앞에서부터 length 를 막 넘는 점까지.
Path pathPrefix(const Path & path, double length);
// 로봇 좌표계(로봇 = 원점) 경로에서 거리 L 인 조준점. 없으면 마지막 점.
Point2D carrotOnPath(const Path & path, double L);
// 조준점이 놓인 구간의 방향. 레일 자체가 로봇과 얼마나 어긋났는지 본다(유턴 판정).
double carrotTangent(const Path & path, double L);
// 원점에서 조준점을 지나는 원호의 곡률(RPP 와 같은 식).
double curvatureTo(const Point2D & carrot);
// 경로를 왼쪽(+)으로 평행이동한다. 시작은 d_start, transition_len 뒤부터 d_end, 그 사이는 일정 기울기.
// (기울기 일정 = 옆 이동 속도 일정 -> 손잡이 좌우 속도 상한을 그대로 지킨다)
Path offsetPath(const Path & path, double d_start, double d_end, double transition_len);
}  // namespace vica_vcc_controller::core
```

`src/core/pure_pursuit.cpp`:

```cpp
// Copyright (c) 2020 Shrijit Singh
// Copyright (c) 2020 Samsung Research America
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.
//
// VICA 수정(2026-09-24): circleSegmentIntersection·조준점 찾기를 nav2_regulated_pure_pursuit_controller
// 1.1.20 에서 가져와 ROS 메시지 대신 core::Point2D 로 바꿨다. 나머지 함수는 VICA 작성.

#include "vica_vcc_controller/core/pure_pursuit.hpp"

#include <algorithm>
#include <cmath>

namespace vica_vcc_controller::core
{
namespace
{
// RPP circleSegmentIntersection 그대로(원점 중심 원과 선분의 교점, 선분 위의 점만).
Point2D circleSegmentIntersection(const Point2D & p1, const Point2D & p2, double r)
{
  const double x1 = p1.x, x2 = p2.x, y1 = p1.y, y2 = p2.y;
  const double dx = x2 - x1, dy = y2 - y1;
  const double dr2 = dx * dx + dy * dy;
  const double D = x1 * y2 - x2 * y1;
  const double d1 = x1 * x1 + y1 * y1;
  const double d2 = x2 * x2 + y2 * y2;
  const double dd = d2 - d1;
  const double sqrt_term = std::sqrt(std::max(0.0, r * r * dr2 - D * D));
  return {(D * dy + std::copysign(1.0, dd) * dx * sqrt_term) / dr2,
    (-D * dx + std::copysign(1.0, dd) * dy * sqrt_term) / dr2};
}

size_t carrotIndex(const Path & path, double L)
{
  for (size_t i = 0; i < path.size(); ++i) {
    if (std::hypot(path[i].x, path[i].y) >= L) {return i;}
  }
  return path.size();
}
}  // namespace

double lookaheadDistance(double v, const LookaheadParams & p)
{
  return std::clamp(std::abs(v) * p.time, p.min_dist, p.max_dist);
}

double pathLength(const Path & path)
{
  double s = 0.0;
  for (size_t i = 1; i < path.size(); ++i) {
    s += std::hypot(path[i].x - path[i - 1].x, path[i].y - path[i - 1].y);
  }
  return s;
}

Path pathPrefix(const Path & path, double length)
{
  Path out;
  double s = 0.0;
  for (size_t i = 0; i < path.size(); ++i) {
    if (i > 0) {s += std::hypot(path[i].x - path[i - 1].x, path[i].y - path[i - 1].y);}
    out.push_back(path[i]);
    if (s >= length) {break;}
  }
  return out;
}

Point2D carrotOnPath(const Path & path, double L)
{
  const size_t i = carrotIndex(path, L);
  if (i == path.size()) {return {path.back().x, path.back().y};}
  if (i == 0) {return {path[0].x, path[0].y};}
  return circleSegmentIntersection({path[i - 1].x, path[i - 1].y}, {path[i].x, path[i].y}, L);
}

double carrotTangent(const Path & path, double L)
{
  if (path.size() < 2) {return path.empty() ? 0.0 : path.front().yaw;}
  size_t i = carrotIndex(path, L);
  if (i == path.size()) {i = path.size() - 1;}
  if (i == 0) {i = 1;}
  return std::atan2(path[i].y - path[i - 1].y, path[i].x - path[i - 1].x);
}

double curvatureTo(const Point2D & c)
{
  const double d2 = c.x * c.x + c.y * c.y;
  return d2 > 1e-9 ? 2.0 * c.y / d2 : 0.0;
}

Path offsetPath(const Path & path, double d_start, double d_end, double transition_len)
{
  Path out;
  out.reserve(path.size());
  double s = 0.0;
  for (size_t i = 0; i < path.size(); ++i) {
    if (i > 0) {s += std::hypot(path[i].x - path[i - 1].x, path[i].y - path[i - 1].y);}
    const size_t a = i == 0 ? 0 : i - 1;
    const size_t b = std::min(i + 1, path.size() - 1);
    double tx = path[b].x - path[a].x, ty = path[b].y - path[a].y;
    double tn = std::hypot(tx, ty);
    if (tn < 1e-9) {tx = std::cos(path[i].yaw); ty = std::sin(path[i].yaw); tn = 1.0;}
    tx /= tn; ty /= tn;
    const double u = transition_len > 1e-9 ? std::clamp(s / transition_len, 0.0, 1.0) : 1.0;
    const double d = d_start + (d_end - d_start) * u;
    out.push_back({path[i].x - ty * d, path[i].y + tx * d, std::atan2(ty, tx)});
  }
  return out;
}
}  // namespace vica_vcc_controller::core
```

`CMakeLists.txt`: vcc_core 에 `src/core/pure_pursuit.cpp` 를 추가하고, `ament_add_gtest(test_pure_pursuit test/test_pure_pursuit.cpp)` + `target_link_libraries(test_pure_pursuit vcc_core)` 를 넣는다.

- [ ] **Step 4: 통과 확인** — Run: `... --ctest-args -R test_pure_pursuit` / Expected: 6개 PASS
- [ ] **Step 5: 커밋** — `git commit -m "feat(vcc): 조준점·곡률·차선 평행이동 경로 — RPP 교점 식 재사용(Apache 2.0 표기)"`

---

### Task 4: 속도 한계 (코너 미리보기·근접·도착)

**Files:**
- Create: `include/vica_vcc_controller/core/speed_profile.hpp`, `src/core/speed_profile.cpp`
- Test: `test/test_speed_profile.cpp`
- Modify: `CMakeLists.txt`

**Interfaces:**
- Consumes: `Path`
- Produces:
  - `struct SpeedParams{desired=0.5, min_speed=0.12, curve_min_radius=1.2, curve_decel=0.3, preview_dist=1.5, curve_sample=0.2, slow_clearance=0.35, approach_dist=0.6, approach_min=0.05;}`
  - `double curveLimitAt(double curvature, const SpeedParams&)`
  - `double curvePreviewLimit(const Path&, const SpeedParams&)`
  - `double clearanceLimit(double clearance, const SpeedParams&)`
  - `double approachLimit(double dist_to_end, double v, const SpeedParams&)`

- [ ] **Step 1: 실패하는 시험** — `test/test_speed_profile.cpp`

```cpp
#include <gtest/gtest.h>
#include <cmath>
#include "vica_vcc_controller/core/speed_profile.hpp"

using namespace vica_vcc_controller::core;

namespace
{
// start 까지 직진한 뒤 반지름 R 로 왼쪽 90도
Path cornerPath(double start, double R)
{
  Path p;
  for (double x = 0.0; x < start; x += 0.05) {p.push_back({x, 0.0, 0.0});}
  for (double th = 0.0; th <= M_PI / 2 + 1e-9; th += 0.05 / R) {
    p.push_back({start + R * std::sin(th), R - R * std::cos(th), th});
  }
  return p;
}
}  // namespace

TEST(SpeedProfile, StraightKeepsDesired)
{
  Path p;
  for (double x = 0.0; x <= 3.0; x += 0.05) {p.push_back({x, 0.0, 0.0});}
  EXPECT_NEAR(curvePreviewLimit(p, SpeedParams{}), 0.5, 1e-6);
}

TEST(SpeedProfile, CornerIsAnticipatedNotSudden)
{
  // R 0.5 코너 한계 = 0.5 x 0.5/1.2 = 0.208 (RPP 곡률 감속과 같은 값)
  SpeedParams sp;
  EXPECT_NEAR(curveLimitAt(1.0 / 0.5, sp), 0.208, 0.002);
  // 0.2 m 앞 코너: sqrt(0.208^2 + 2*0.3*0.2) = 0.404 -> 미리 줄이기 시작
  EXPECT_NEAR(curvePreviewLimit(cornerPath(0.2, 0.5), sp), 0.404, 0.03);
  // 1.0 m 앞 코너: sqrt(0.043 + 0.6) = 0.80 > 0.5 -> 아직 안 줄인다
  EXPECT_NEAR(curvePreviewLimit(cornerPath(1.0, 0.5), sp), 0.5, 1e-6);
  // 완만한 R 2.0 코너는 줄이지 않는다
  EXPECT_NEAR(curvePreviewLimit(cornerPath(0.2, 2.0), sp), 0.5, 1e-6);
}

TEST(SpeedProfile, ClearanceSlowdownUsesMeasuredDistance)
{
  SpeedParams sp;
  EXPECT_NEAR(clearanceLimit(0.50, sp), 0.5, 1e-9);
  EXPECT_NEAR(clearanceLimit(0.175, sp), 0.25, 1e-9);
  EXPECT_NEAR(clearanceLimit(0.01, sp), 0.12, 1e-9);   // RPP regulated_linear_scaling_min_speed
}

TEST(SpeedProfile, ApproachMatchesCurrentRpp)
{
  SpeedParams sp;
  EXPECT_NEAR(approachLimit(1.0, 0.5, sp), 0.5, 1e-9);
  EXPECT_NEAR(approachLimit(0.3, 0.5, sp), 0.25, 1e-9);
  EXPECT_NEAR(approachLimit(0.01, 0.5, sp), 0.05, 1e-9);
}
```

- [ ] **Step 2: 실패 확인** — Expected: FAIL(헤더 없음)

- [ ] **Step 3: 구현** — `core/speed_profile.hpp`

```cpp
#pragma once
#include "vica_vcc_controller/core/types.hpp"

namespace vica_vcc_controller::core
{
struct SpeedParams
{
  double desired{0.5};           // desired_linear_vel
  double min_speed{0.12};        // RPP regulated_linear_scaling_min_speed
  double curve_min_radius{1.2};  // RPP regulated_linear_scaling_min_radius
  double curve_decel{0.3};       // 코너 미리 줄이기 감속(설계서 7절)
  double preview_dist{1.5};
  double curve_sample{0.2};      // 곡률을 잴 점 간격(레일 경로 0.05 m 잡음 회피)
  double slow_clearance{0.35};   // RPP cost_scaling_dist 와 같은 값, 단 직접 잰 거리
  double approach_dist{0.6};     // RPP approach_velocity_scaling_dist
  double approach_min{0.05};     // RPP min_approach_linear_velocity
};

double curveLimitAt(double curvature, const SpeedParams & p);
// 앞 preview_dist 안 곡선마다 "그 곡선 한계에 curve_decel 로 제때 닿는 속도"의 최소.
double curvePreviewLimit(const Path & path, const SpeedParams & p);
double clearanceLimit(double clearance, const SpeedParams & p);
double approachLimit(double dist_to_end, double v, const SpeedParams & p);
}  // namespace vica_vcc_controller::core
```

`src/core/speed_profile.cpp`:

```cpp
#include "vica_vcc_controller/core/speed_profile.hpp"

#include <algorithm>
#include <cmath>
#include <vector>

namespace vica_vcc_controller::core
{
double curveLimitAt(double k, const SpeedParams & p)
{
  const double r = 1.0 / std::max(std::abs(k), 1e-6);
  if (r >= p.curve_min_radius) {return p.desired;}
  return std::max(p.min_speed, p.desired * r / p.curve_min_radius);
}

double curvePreviewLimit(const Path & path, const SpeedParams & p)
{
  if (path.size() < 3) {return p.desired;}
  std::vector<Pose2D> pts{path.front()};
  std::vector<double> s{0.0};
  double acc = 0.0;
  for (size_t i = 1; i < path.size(); ++i) {
    acc += std::hypot(path[i].x - path[i - 1].x, path[i].y - path[i - 1].y);
    if (acc - s.back() >= p.curve_sample) {pts.push_back(path[i]); s.push_back(acc);}
    if (acc > p.preview_dist) {break;}
  }
  double limit = p.desired;
  for (size_t j = 1; j + 1 < pts.size(); ++j) {
    const double ax = pts[j].x - pts[j - 1].x, ay = pts[j].y - pts[j - 1].y;
    const double bx = pts[j + 1].x - pts[j].x, by = pts[j + 1].y - pts[j].y;
    const double cx = pts[j + 1].x - pts[j - 1].x, cy = pts[j + 1].y - pts[j - 1].y;
    const double la = std::hypot(ax, ay), lb = std::hypot(bx, by), lc = std::hypot(cx, cy);
    if (la * lb * lc < 1e-12) {continue;}
    const double k = 2.0 * std::abs(ax * by - ay * bx) / (la * lb * lc);   // Menger 곡률
    const double vl = curveLimitAt(k, p);
    limit = std::min(limit, std::sqrt(vl * vl + 2.0 * p.curve_decel * s[j]));
  }
  return limit;
}

double clearanceLimit(double c, const SpeedParams & p)
{
  if (c >= p.slow_clearance) {return p.desired;}
  return std::max(p.min_speed, p.desired * std::max(c, 0.0) / p.slow_clearance);
}

double approachLimit(double dist, double v, const SpeedParams & p)
{
  if (dist >= p.approach_dist) {return v;}
  return std::min(v, std::max(v * dist / p.approach_dist, p.approach_min));
}
}  // namespace vica_vcc_controller::core
```

`CMakeLists.txt`: 소스와 `test_speed_profile` 를 추가한다.

- [ ] **Step 4: 통과 확인** — Expected: 4개 PASS
- [ ] **Step 5: 커밋** — `git commit -m "feat(vcc): 코너 미리보기 감속·직접 거리 근접 감속·도착 감속"`

---

### Task 5: 공용 출력단 (`OutputStage`)

**Files:**
- Create: `include/vica_vcc_controller/core/output_stage.hpp`, `src/core/output_stage.cpp`
- Test: `test/test_output_stage.cpp`
- Modify: `CMakeLists.txt`

**Interfaces:**
- Consumes: `Twist2D`
- Produces:
  - `struct OutputParams{max_v=0.5, max_w=0.5, max_ang_accel=1.2, ramp_v1=0.25, ramp_a1=0.5, accel=0.143, max_decel=1.25, resync_margin=0.05;}`
  - `struct Desired{Twist2D cmd; double curvature=NAN; double radius=-1.0;}`
    - curvature 가 NaN 이 아니면 제한된 v 에서 w = v·κ 로 곡률을 지킨다.
    - radius > 0 이면 v ≤ |w|·R 로 호 반지름을 지킨다.
  - `class OutputStage{ void reset(); Twist2D apply(const Desired&, double measured_v, double dt); const Twist2D & last() const; }`

- [ ] **Step 1: 실패하는 시험** — `test/test_output_stage.cpp`

```cpp
#include <gtest/gtest.h>
#include <cmath>
#include "vica_vcc_controller/core/output_stage.hpp"

using namespace vica_vcc_controller::core;

TEST(OutputStage, StartRampHalfSpeedThenSlow)
{
  // 요구 8: 0 -> 0.25 약 0.5 s, 0.25 -> 0.5 는 1.5~2 s
  OutputStage o;
  double t = 0.0, t_half = -1.0, t_full = -1.0;
  for (int i = 0; i < 60; ++i) {
    t += 0.1;
    const Twist2D c = o.apply(Desired{{0.5, 0.0}}, o.last().v, 0.1);
    if (t_half < 0 && c.v >= 0.25 - 1e-9) {t_half = t;}
    if (t_full < 0 && c.v >= 0.5 - 1e-9) {t_full = t;}
  }
  EXPECT_GE(t_half, 0.4);
  EXPECT_LE(t_half, 0.6);
  EXPECT_GE(t_full - t_half, 1.5);
  EXPECT_LE(t_full - t_half, 2.0);
}

TEST(OutputStage, BrakingIsNeverSoftened)
{
  OutputStage o;
  for (int i = 0; i < 60; ++i) {o.apply(Desired{{0.5, 0.0}}, o.last().v, 0.1);}
  const Twist2D c = o.apply(Desired{{0.0, 0.0}}, 0.5, 0.1);
  EXPECT_NEAR(c.v, 0.5 - 0.125, 1e-9);   // smoother max_decel 1.25 와 같은 세기
}

TEST(OutputStage, ResyncsToMeasuredSpeedAfterExternalStop)
{
  // collision_monitor·예외로 실제 속도가 0 이 되면, 출발은 0 에서 다시 램프한다.
  OutputStage o;
  for (int i = 0; i < 60; ++i) {o.apply(Desired{{0.5, 0.0}}, o.last().v, 0.1);}
  const Twist2D c = o.apply(Desired{{0.5, 0.0}}, 0.0, 0.1);
  EXPECT_LE(c.v, 0.05 + 0.05 + 1e-9);
}

TEST(OutputStage, NoReverseAndSymmetricTurnLimit)
{
  OutputStage o;
  EXPECT_GE(o.apply(Desired{{-0.3, 0.0}}, 0.0, 0.1).v, 0.0);
  OutputStage a, b;
  for (int i = 0; i < 20; ++i) {a.apply(Desired{{0.0, 3.0}}, 0.0, 0.1); b.apply(Desired{{0.0, -3.0}}, 0.0, 0.1);}
  EXPECT_NEAR(a.last().w, 0.5, 1e-9);
  EXPECT_NEAR(b.last().w, -0.5, 1e-9);
}

TEST(OutputStage, AngularAccelIsLimited)
{
  OutputStage o;
  EXPECT_NEAR(o.apply(Desired{{0.0, 0.5}}, 0.0, 0.1).w, 0.12, 1e-9);   // 1.2 rad/s^2
}

TEST(OutputStage, CurvatureIsKeptWhileAccelerating)
{
  OutputStage o;
  Desired d{{0.5, 0.5}};
  d.curvature = 1.0;
  const Twist2D c = o.apply(d, 0.0, 0.1);
  EXPECT_NEAR(c.w, c.v * 1.0, 1e-9);
}

TEST(OutputStage, ArcRadiusIsKept)
{
  OutputStage o;
  Desired d{{0.5, 0.45}};
  d.radius = 0.2;
  for (int i = 0; i < 10; ++i) {o.apply(d, o.last().v, 0.1);}
  EXPECT_NEAR(o.last().v, std::abs(o.last().w) * 0.2, 1e-9);
}
```

- [ ] **Step 2: 실패 확인** — Expected: FAIL

- [ ] **Step 3: 구현** — `core/output_stage.hpp`

```cpp
#pragma once
#include <cmath>
#include "vica_vcc_controller/core/types.hpp"

namespace vica_vcc_controller::core
{
struct OutputParams
{
  double max_v{0.5};          // desired_linear_vel 상한, 후진 없음
  double max_w{0.5};          // velocity_smoother max_velocity[2]
  double max_ang_accel{1.2};  // RPP max_angular_accel
  double ramp_v1{0.25};       // 요구 8: 절반 속도까지 살짝
  double ramp_a1{0.5};        //   0 -> 0.25 를 0.5 s
  double accel{0.143};        //   0.25 -> 0.5 를 1.75 s, 코너 뒤 재가속도 같다
  double max_decel{1.25};     // velocity_smoother max_decel[0]. 제동은 완화하지 않는다
  double resync_margin{0.05};
};

struct Desired
{
  Twist2D cmd;
  double curvature{std::nan("")};
  double radius{-1.0};
};

// 모든 상황이 같은 한계를 거친다(설계서 7절). 상황이 바뀌어도 직전 명령에서 이어 간다.
class OutputStage
{
public:
  explicit OutputStage(OutputParams p = {}) : p_(p) {}
  void reset() {last_ = {};}
  Twist2D apply(const Desired & d, double measured_v, double dt);
  const Twist2D & last() const {return last_;}

private:
  OutputParams p_;
  Twist2D last_;
};
}  // namespace vica_vcc_controller::core
```

`src/core/output_stage.cpp`:

```cpp
#include "vica_vcc_controller/core/output_stage.hpp"

#include <algorithm>

namespace vica_vcc_controller::core
{
Twist2D OutputStage::apply(const Desired & d, double measured_v, double dt)
{
  // 실제로 멈췄거나 느려졌으면(collision_monitor 감속·예외 뒤 0 발행) 거기서부터 다시 올린다.
  last_.v = std::min(last_.v, std::max(0.0, measured_v) + p_.resync_margin);

  double v = std::clamp(d.cmd.v, 0.0, p_.max_v);
  if (v > last_.v) {
    const double a = last_.v < p_.ramp_v1 ? p_.ramp_a1 : p_.accel;
    v = std::min({v, last_.v + a * dt, last_.v < p_.ramp_v1 ? std::max(p_.ramp_v1, last_.v) : v});
  } else {
    v = std::max(v, last_.v - p_.max_decel * dt);
  }

  double w_target = std::isnan(d.curvature) ? d.cmd.w : v * d.curvature;
  w_target = std::clamp(w_target, -p_.max_w, p_.max_w);
  const double w = std::clamp(
    w_target, last_.w - p_.max_ang_accel * dt, last_.w + p_.max_ang_accel * dt);

  if (d.radius > 0.0) {v = std::min(v, std::abs(w) * d.radius);}
  last_ = {v, w};
  return last_;
}
}  // namespace vica_vcc_controller::core
```

`CMakeLists.txt`: 소스와 `test_output_stage` 를 추가한다.

- [ ] **Step 4: 통과 확인** — Expected: 7개 PASS
- [ ] **Step 5: 커밋** — `git commit -m "feat(vcc): 공용 출력단 — 출발 0.25 까지 0.5 s·이후 1.75 s, 제동 1.25 유지, 외부 정지 뒤 재동기화"`

---

### Task 6: 초음파 확인과 호 점 (`ultrasonic`)

**Files:**
- Create: `include/vica_vcc_controller/core/ultrasonic.hpp`, `src/core/ultrasonic.cpp`
- Test: `test/test_ultrasonic.cpp`
- Modify: `CMakeLists.txt`

**Interfaces:**
- Consumes: `Point2D`
- Produces:
  - `struct RangeReading{double range, min_range, max_range, fov, recv_time;}`
  - `class UltrasonicChannel{ void push(const RangeReading&); std::optional<RangeReading> confirmed(double now, double max_age, int count, double tol) const; }`
  - `std::vector<Point2D> rangeToArcPoints(double range, double fov, int n)`: 센서 좌표, x 가 앞

- [ ] **Step 1: 실패하는 시험** — `test/test_ultrasonic.cpp`

```cpp
#include <gtest/gtest.h>
#include <cmath>
#include "vica_vcc_controller/core/ultrasonic.hpp"

using namespace vica_vcc_controller::core;

namespace
{
RangeReading r(double range, double t) {return {range, 0.02, 1.5, 1.047, t};}
}

TEST(Ultrasonic, TwoConsistentFreshReadingsAreConfirmed)
{
  UltrasonicChannel ch;
  ch.push(r(0.80, 10.0));
  ch.push(r(0.85, 10.46));   // 2.19 Hz 간격
  const auto c = ch.confirmed(10.5, 1.0, 2, 0.15);
  ASSERT_TRUE(c.has_value());
  EXPECT_NEAR(c->range, 0.85, 1e-9);
}

TEST(Ultrasonic, SingleSpikeIsIgnored)
{
  UltrasonicChannel ch;
  ch.push(r(1.5, 10.0));      // 에코 없음(max_range)
  ch.push(r(0.40, 10.46));    // 한 번 튄 값
  EXPECT_FALSE(ch.confirmed(10.5, 1.0, 2, 0.15).has_value());
  UltrasonicChannel ch2;
  ch2.push(r(0.40, 10.0));
  ch2.push(r(0.80, 10.46));   // 0.4 m 차이
  EXPECT_FALSE(ch2.confirmed(10.5, 1.0, 2, 0.15).has_value());
}

TEST(Ultrasonic, StaleReadingsAreDropped)
{
  // run43: 지워지지 않는 표시가 정지 9회의 원인. 1 s 지난 값은 쓰지 않는다.
  UltrasonicChannel ch;
  ch.push(r(0.80, 10.0));
  ch.push(r(0.80, 10.46));
  EXPECT_FALSE(ch.confirmed(11.2, 1.0, 2, 0.15).has_value());
}

TEST(Ultrasonic, NoEchoIsNotAnObstacle)
{
  UltrasonicChannel ch;
  ch.push(r(1.5, 10.0));
  ch.push(r(1.5, 10.46));
  EXPECT_FALSE(ch.confirmed(10.5, 1.0, 2, 0.15).has_value());
}

TEST(Ultrasonic, ArcPointsSpanFieldOfView)
{
  const auto pts = rangeToArcPoints(1.0, 60.0 * M_PI / 180.0, 5);
  ASSERT_EQ(pts.size(), 5u);
  for (const auto & p : pts) {EXPECT_NEAR(std::hypot(p.x, p.y), 1.0, 1e-9);}
  EXPECT_NEAR(std::atan2(pts.front().y, pts.front().x), -M_PI / 6, 1e-9);
  EXPECT_NEAR(std::atan2(pts.back().y, pts.back().x), M_PI / 6, 1e-9);
}
```

- [ ] **Step 2: 실패 확인** — Expected: FAIL

- [ ] **Step 3: 구현** — `core/ultrasonic.hpp`

```cpp
#pragma once
#include <deque>
#include <optional>
#include <vector>
#include "vica_vcc_controller/core/types.hpp"

namespace vica_vcc_controller::core
{
struct RangeReading
{
  double range{0.0};
  double min_range{0.0};
  double max_range{0.0};
  double fov{0.0};
  double recv_time{0.0};   // 받은 시각(steady). stamp 가 아니다 — run44 stamp 지연으로 660회 무시된 교훈
};

class UltrasonicChannel
{
public:
  void push(const RangeReading & r);
  // 최근 count 개가 모두 max_age 안·유효 범위·서로 tol 안이면 최신 값.
  std::optional<RangeReading> confirmed(double now, double max_age, int count, double tol) const;

private:
  std::deque<RangeReading> hist_;
};

// 센서 좌표(x 앞)에서 거리 range, 폭 fov 의 호를 n 점으로.
std::vector<Point2D> rangeToArcPoints(double range, double fov, int n);
}  // namespace vica_vcc_controller::core
```

`src/core/ultrasonic.cpp`:

```cpp
#include "vica_vcc_controller/core/ultrasonic.hpp"

#include <algorithm>
#include <cmath>

namespace vica_vcc_controller::core
{
void UltrasonicChannel::push(const RangeReading & r)
{
  hist_.push_back(r);
  while (hist_.size() > 4) {hist_.pop_front();}
}

std::optional<RangeReading> UltrasonicChannel::confirmed(
  double now, double max_age, int count, double tol) const
{
  if (count < 1 || static_cast<int>(hist_.size()) < count) {return std::nullopt;}
  double lo = 1e9, hi = -1e9;
  for (int i = 0; i < count; ++i) {
    const RangeReading & r = hist_[hist_.size() - 1 - i];
    if (now - r.recv_time > max_age) {return std::nullopt;}
    // 드라이버는 에코 없음을 max_range 로 발행한다(user_guidance_driver_node US_CLEAR_MM)
    if (!(r.range > r.min_range && r.range < r.max_range - 1e-3)) {return std::nullopt;}
    lo = std::min(lo, r.range);
    hi = std::max(hi, r.range);
  }
  if (hi - lo > tol) {return std::nullopt;}
  return hist_.back();
}

std::vector<Point2D> rangeToArcPoints(double range, double fov, int n)
{
  std::vector<Point2D> pts;
  if (n < 1) {return pts;}
  for (int i = 0; i < n; ++i) {
    const double a = n == 1 ? 0.0 : -fov / 2.0 + fov * i / (n - 1);
    pts.push_back({range * std::cos(a), range * std::sin(a)});
  }
  return pts;
}
}  // namespace vica_vcc_controller::core
```

`CMakeLists.txt`: 소스와 `test_ultrasonic` 을 추가한다.

- [ ] **Step 4: 통과 확인** — Expected: 5개 PASS
- [ ] **Step 5: 커밋** — `git commit -m "feat(vcc): 초음파 확인 규칙 — 받은 지 1 s·연속 2회 일치·에코 없음 제외"`

---

### Task 7: 차선 고르기 (`LaneSelector`)

**Files:**
- Create: `include/vica_vcc_controller/core/lanes.hpp`, `src/core/lanes.cpp`
- Test: `test/test_lanes.cpp`
- Modify: `CMakeLists.txt`

**Interfaces:**
- Consumes:
  - `ClearanceFn`, `ClearanceField`(시험용), `padFootprint`
  - `offsetPath`, `pathPrefix`
- Produces:
  - `struct LaneParams{max_offset=0.6, step=0.1, horizon=1.5, sample_step=0.1, target_clearance=0.20, w_clear=10.0, w_rail=1.0, w_change=0.5, switch_margin=0.05, persist_cycles=3, lane_rate=0.10, return_clear_time=1.0, min_transition_speed=0.1; std::vector<double> shift_speeds{0.3,0.2,0.1};}`
  - `struct LaneScore{double offset, min_clearance, score; bool valid; double speed;}`: speed 는 이 차선으로 옮기는 동안 달릴 속도
  - `class LaneSelector`
    - `void reset()`
    - `void update(const Path&, double v, double now, double dt, const ClearanceFn&)`
    - `double offset() const`, `double target() const`, `bool blocked() const`
    - `double currentClearance() const`: 지금 목표 차선의 최소 여유
    - `double speedCap() const`: 차선을 옮기는 중이면 그 차선의 옮김 속도, 아니면 1e9
    - `const std::vector<LaneScore>& scores() const`
    - `Path lanePath(const Path&, double v) const`: 지금 offset 에서 target 으로 옮겨 가는 전체 경로

가중치 근거(설계서 11절 "시나리오로 정함"): 점수 = 10·(0.20 − c)⁺ + 1.0·|d| + 0.5·|d − 지금 목표|.

- 여유 10 cm 부족(1.0)이 레일에서 0.6 m 벗어나기(0.6)보다 무겁다. 이것이 "20 cm 확보 > 레일 가까움"이다.
- 차선 유지(0.5/m)는 레일 복귀(1.0/m)보다 가볍다. 그래서 장애물이 없으면 레일로 돌아온다.
- 동점이면 오른쪽(음수)을 고른다(우측 통행). 시험 `TieGoesRight` 로 고정한다.

옮기는 동안의 속도(계획서를 쓰며 찾은 빈틈):
- 옆 이동 상한 0.10 m/s 로 0.6 m 옮기려면 0.4 m/s 에서는 2.4 m 가 든다. 1.5 m 앞 물체를 못 비킨다.
- 그래서 차선마다 옮기는 속도를 [지금 속도, 0.3, 0.2, 0.1] 순으로 시험한다.
- 20 cm 여유가 나오는 **가장 빠른** 속도를 그 차선의 `speed` 로 삼는다. 끝내 20 cm 가 안 되면 여유가 가장 큰 속도를 쓴다.
- 주행은 차선을 옮기는 동안만 그 속도로 달린다(`speedCap`). MPPI 가 회피 때 부드럽게 줄이던 성질과 같다.
- 옆 간격(offset)은 시간이 아니라 **달린 거리**로 나아간다(기울기 = lane_rate / speed). 멈춰 있으면 옆으로 미끄러지지 않는다.

- [ ] **Step 1: 실패하는 시험** — `test/test_lanes.cpp`

```cpp
#include <gtest/gtest.h>
#include <cmath>
#include "vica_vcc_controller/core/clearance.hpp"
#include "vica_vcc_controller/core/geometry.hpp"
#include "vica_vcc_controller/core/lanes.hpp"

using namespace vica_vcc_controller::core;

namespace
{
const Polygon kFootprint{{0.151, 0.225}, {0.151, -0.225}, {-0.459, -0.225},
  {-0.569, -0.035}, {-0.569, 0.035}, {-0.459, 0.225}};

Path rail()
{
  Path p;
  for (double x = 0.0; x <= 3.0 + 1e-9; x += 0.05) {p.push_back({x, 0.0, 0.0});}
  return p;
}

struct World
{
  ClearanceField f;
  World()
  {
    f.setFootprint(padFootprint(kFootprint, 0.05));
    f.grid().reset(-2.5, -2.5, 0.05, 100, 100);
    f.grid().compute();
  }
  void box(double x0, double x1, double y0, double y1)
  {
    for (int ix = 0; ix < 100; ++ix) {
      for (int iy = 0; iy < 100; ++iy) {
        const double cx = -2.5 + (ix + 0.5) * 0.05, cy = -2.5 + (iy + 0.5) * 0.05;
        if (cx >= x0 && cx <= x1 && cy >= y0 && cy <= y1) {f.grid().markLethal(ix, iy);}
      }
    }
    f.grid().compute();
  }
  ClearanceFn fn() const {return [this](const Pose2D & p) {return f.clearance(p);};}
};

void run(LaneSelector & ls, const World & w, int cycles, double & now, double v = 0.4)
{
  for (int i = 0; i < cycles; ++i) {now += 0.1; ls.update(rail(), v, now, 0.1, w.fn());}
}
}  // namespace

TEST(Lanes, EmptyCorridorStaysOnRail)
{
  World w;
  LaneSelector ls;
  double now = 0.0;
  run(ls, w, 10, now);
  EXPECT_NEAR(ls.target(), 0.0, 1e-9);
  EXPECT_NEAR(ls.offset(), 0.0, 1e-9);
  EXPECT_FALSE(ls.blocked());
}

TEST(Lanes, PoleOnRailIsPassedWithTwentyCentimetres)
{
  // 10 cm 기둥이 레일 1.5 m 앞(avoid_horizon 끝에서 처음 보인 상황).
  // 필요한 옆 간격 = 0.05 + 0.275 + 0.20 = 0.525 -> 0.6 차선. 0.4 m/s 로는 못 옮겨 0.2 m/s 로 줄인다.
  World w;
  w.box(1.5, 1.6, -0.05, 0.05);
  LaneSelector ls;
  double now = 0.0;
  run(ls, w, 3, now);
  EXPECT_NEAR(std::abs(ls.target()), 0.6, 1e-9);
  const auto & s = ls.scores();
  for (const auto & sc : s) {
    if (std::abs(sc.offset - ls.target()) < 1e-9) {
      EXPECT_GE(sc.min_clearance, 0.2 - 0.03);
      EXPECT_NEAR(sc.speed, 0.2, 1e-9);
    }
  }
  EXPECT_NEAR(ls.speedCap(), 0.2, 1e-9);
}

TEST(Lanes, SwitchWaitsForPersistence)
{
  World w;
  w.box(1.5, 1.6, -0.05, 0.05);
  LaneSelector ls;
  double now = 0.0;
  run(ls, w, 2, now);
  EXPECT_NEAR(ls.target(), 0.0, 1e-9);   // 0.2 s 로는 아직
  run(ls, w, 1, now);
  EXPECT_NE(ls.target(), 0.0);           // 3주기(0.3 s)에 전환
}

TEST(Lanes, OffsetMovesAtLaneRate)
{
  // 옮김 속도(0.2)로 달리면 옆 이동은 정확히 lane_rate: 0.10 m/s x 0.1 s = 0.01 m
  World w;
  w.box(1.5, 1.6, -0.05, 0.05);
  LaneSelector ls;
  double now = 0.0;
  run(ls, w, 3, now, 0.2);
  const double before = ls.offset();
  run(ls, w, 1, now, 0.2);
  EXPECT_NEAR(std::abs(ls.offset() - before), 0.01, 1e-9);
  // 멈춰 있으면 옆으로 미끄러지지 않는다
  const double still = ls.offset();
  run(ls, w, 1, now, 0.0);
  EXPECT_NEAR(ls.offset(), still, 1e-12);
}

TEST(Lanes, ReturnsToRailOnlyAfterOneSecondClear)
{
  World w;
  w.box(1.5, 1.6, -0.05, 0.05);
  LaneSelector ls;
  double now = 0.0;
  run(ls, w, 3, now);
  ASSERT_NE(ls.target(), 0.0);
  World empty;
  run(ls, empty, 9, now);                 // 0.9 s
  EXPECT_NE(ls.target(), 0.0);
  run(ls, empty, 2, now);                 // 1.1 s
  EXPECT_NEAR(ls.target(), 0.0, 1e-9);
}

TEST(Lanes, NearlyEqualLanesDoNotFlipFlop)
{
  // 두 차선이 거의 같은 점수로 매 주기 번갈아 1등 — MPPI 식 비틀거림 방지(switch_margin)
  LaneSelector ls;
  double now = 0.0;
  int switches = 0;
  double last = ls.target();
  for (int i = 0; i < 50; ++i) {
    const double wobble = (i % 2 == 0) ? 0.01 : -0.01;
    ClearanceFn fn = [wobble](const Pose2D & p) {return 0.10 + wobble * (p.y > 0 ? 1 : -1);};
    now += 0.1;
    ls.update(rail(), 0.4, now, 0.1, fn);
    if (ls.target() != last) {++switches; last = ls.target();}
  }
  EXPECT_LE(switches, 1);
}

TEST(Lanes, FarObstacleBeyondHorizonIsIgnored)
{
  // 요구 1: 3~4 m 앞 사람에 반응하지 않는다. 2.2 m 앞 물체도 horizon 1.5 밖이다.
  World w;
  w.box(2.2, 2.4, -0.3, 0.3);
  LaneSelector ls;
  double now = 0.0;
  run(ls, w, 10, now);
  EXPECT_NEAR(ls.target(), 0.0, 1e-9);
}

TEST(Lanes, WallAcrossCorridorIsBlocked)
{
  World w;
  w.box(1.0, 1.1, -2.5, 2.5);
  LaneSelector ls;
  double now = 0.0;
  run(ls, w, 1, now);
  EXPECT_TRUE(ls.blocked());
}

TEST(Lanes, TieGoesRight)
{
  World w;
  w.box(1.5, 1.6, -0.05, 0.05);   // 좌우 대칭
  LaneSelector ls;
  double now = 0.0;
  run(ls, w, 3, now);
  EXPECT_LT(ls.target(), 0.0);
}
```

- [ ] **Step 2: 실패 확인** — Expected: FAIL

- [ ] **Step 3: 구현** — `core/lanes.hpp`

```cpp
#pragma once
#include <vector>
#include "vica_vcc_controller/core/clearance.hpp"
#include "vica_vcc_controller/core/types.hpp"

namespace vica_vcc_controller::core
{
struct LaneParams
{
  double max_offset{0.6};        // 요구 3: 0.5~0.6 m 이탈 허용
  double step{0.1};
  double horizon{1.5};           // 요구 1: 먼 물체 무시
  double sample_step{0.1};
  double target_clearance{0.20}; // 요구 4: 15~20 cm
  double w_clear{10.0};
  double w_rail{1.0};
  double w_change{0.5};
  double switch_margin{0.05};
  int persist_cycles{3};         // 0.3 s
  double lane_rate{0.10};        // m/s — 손잡이 0.115 m/s 탈락선(backlog §11)
  double return_clear_time{1.0};
  double min_transition_speed{0.1};
  std::vector<double> shift_speeds{0.3, 0.2, 0.1};   // 옮기는 동안 달릴 속도 후보(빠른 것부터)
};

struct LaneScore
{
  double offset{0.0};
  double min_clearance{0.0};
  double score{0.0};
  bool valid{false};
  double speed{0.0};       // 이 차선으로 옮기는 동안 달릴 속도
};

class LaneSelector
{
public:
  explicit LaneSelector(LaneParams p = {}) : p_(p) {}
  void reset();
  void update(const Path & path, double v, double now, double dt, const ClearanceFn & clearance);
  double offset() const {return offset_;}
  double target() const {return target_;}
  bool blocked() const {return blocked_;}
  double currentClearance() const {return current_clearance_;}
  double speedCap() const {return std::abs(target_ - offset_) > 0.01 ? target_speed_ : 1e9;}
  const std::vector<LaneScore> & scores() const {return scores_;}
  Path lanePath(const Path & path, double v) const;

private:
  Path candidatePath(const Path & path, double cand, double shift_speed) const;
  double minClearance(const Path & lane, const ClearanceFn & f) const;
  LaneScore evaluate(const Path & path, double v, double cand, const ClearanceFn & f) const;

  LaneParams p_;
  double offset_{0.0};
  double target_{0.0};
  double target_speed_{1e9};
  double pending_{0.0};
  int pending_count_{0};
  double pending_since_{-1.0};
  bool blocked_{false};
  double current_clearance_{1e9};
  std::vector<LaneScore> scores_;
};
}  // namespace vica_vcc_controller::core
```

`src/core/lanes.cpp`:

```cpp
#include "vica_vcc_controller/core/lanes.hpp"

#include <algorithm>
#include <cmath>
#include "vica_vcc_controller/core/pure_pursuit.hpp"

namespace vica_vcc_controller::core
{
namespace
{
bool same(double a, double b) {return std::abs(a - b) < 1e-6;}
}

void LaneSelector::reset()
{
  offset_ = target_ = pending_ = 0.0;
  target_speed_ = 1e9;
  pending_count_ = 0;
  pending_since_ = -1.0;
  blocked_ = false;
  current_clearance_ = 1e9;
  scores_.clear();
}

Path LaneSelector::candidatePath(const Path & path, double cand, double shift_speed) const
{
  // 옆 이동 속도 = lane_rate 가 되도록 옮김 거리를 정한다: 거리 = |옮길 양| x 달릴 속도 / lane_rate
  const double trans = std::abs(cand - offset_) * shift_speed / p_.lane_rate;
  return offsetPath(path, offset_, cand, trans);
}

Path LaneSelector::lanePath(const Path & path, double v) const
{
  const double sp = std::min(std::max(std::abs(v), p_.min_transition_speed), target_speed_);
  return candidatePath(path, target_, sp);
}

double LaneSelector::minClearance(const Path & lane, const ClearanceFn & f) const
{
  const Path lp = pathPrefix(lane, p_.horizon);
  double c = 1e9, last_s = -1e9, s = 0.0;
  for (size_t i = 0; i < lp.size(); ++i) {
    if (i > 0) {s += std::hypot(lp[i].x - lp[i - 1].x, lp[i].y - lp[i - 1].y);}
    if (i + 1 < lp.size() && s - last_s < p_.sample_step) {continue;}
    last_s = s;
    c = std::min(c, f(lp[i]));
  }
  return c;
}

LaneScore LaneSelector::evaluate(
  const Path & path, double v, double cand, const ClearanceFn & f) const
{
  const double v_ref = std::max(std::abs(v), p_.min_transition_speed);
  std::vector<double> speeds{v_ref};
  for (double sp : p_.shift_speeds) {
    if (sp < v_ref - 1e-9) {speeds.push_back(sp);}
  }
  LaneScore sc;
  sc.offset = cand;
  bool have = false;
  for (double sp : speeds) {
    const double c = minClearance(candidatePath(path, cand, sp), f);
    if (!have || c > sc.min_clearance + 1e-9) {sc.min_clearance = c; sc.speed = sp; have = true;}
    // 20 cm 가 나오는 가장 빠른 속도에서 멈춘다. 옮길 게 없으면 속도와 무관하다.
    if (c >= p_.target_clearance || same(cand, offset_)) {break;}
  }
  sc.valid = sc.min_clearance >= 0.0;
  sc.score = p_.w_clear * std::max(0.0, p_.target_clearance - sc.min_clearance) +
    p_.w_rail * std::abs(cand) + p_.w_change * std::abs(cand - target_);
  return sc;
}

void LaneSelector::update(
  const Path & path, double v, double now, double dt, const ClearanceFn & f)
{
  scores_.clear();
  const int n = static_cast<int>(std::round(p_.max_offset / p_.step));
  // 동점이면 먼저 나온 쪽 — 오른쪽(음수)부터 채점해 우측 통행을 고른다.
  for (int i = -n; i <= n; ++i) {scores_.push_back(evaluate(path, v, i * p_.step, f));}

  const LaneScore * best = nullptr;
  const LaneScore * cur = nullptr;
  for (const auto & s : scores_) {
    if (same(s.offset, target_)) {cur = &s;}
    if (!s.valid) {continue;}
    if (!best || s.score < best->score - 1e-9 ||
      (std::abs(s.score - best->score) <= 1e-9 && std::abs(s.offset) < std::abs(best->offset)))
    {
      best = &s;
    }
  }

  blocked_ = best == nullptr;
  if (!blocked_) {
    if (!cur || !cur->valid) {
      // 지금 차선이 막혔다 — 기다리지 않고 바로 옮긴다(안전).
      target_ = best->offset;
      pending_count_ = 0;
    } else if (!same(best->offset, target_) && best->score < cur->score - p_.switch_margin) {
      if (same(pending_, best->offset) && pending_count_ > 0) {
        ++pending_count_;
      } else {
        pending_ = best->offset;
        pending_count_ = 1;
        pending_since_ = now;
      }
      const bool inward = std::abs(best->offset) < std::abs(target_);
      const bool ready = inward ?
        (now - pending_since_ >= p_.return_clear_time - 1e-9) :
        (pending_count_ >= p_.persist_cycles);
      if (ready) {
        target_ = best->offset;
        pending_count_ = 0;
      }
    } else {
      pending_count_ = 0;
    }
  }

  current_clearance_ = 1e9;
  for (const auto & s : scores_) {
    if (same(s.offset, target_)) {current_clearance_ = s.min_clearance; target_speed_ = s.speed;}
  }

  // 옆 간격은 달린 거리만큼 나아간다(기울기 lane_rate / 옮김 속도). 옆 이동 속도는 lane_rate 를 넘지 않는다.
  const double slope = p_.lane_rate / std::max(target_speed_, 1e-3);
  const double step = std::min(slope * std::abs(v) * dt, p_.lane_rate * dt);
  offset_ += std::clamp(target_ - offset_, -step, step);
}
}  // namespace vica_vcc_controller::core
```

동점 규칙에 대한 설명(구현자는 읽고 넘어간다):

- `TieGoesRight` 는 좌우 대칭 장애물에서 −0.6 과 +0.6 이 같은 점수일 때 먼저 채점된 −0.6 이 남는 것을 확인한다.
- 위 비교식은 |offset| 이 같으면 교체하지 않는다. 그래서 오른쪽이 이긴다.

`CMakeLists.txt`: 소스와 `test_lanes` 를 추가한다.

- [ ] **Step 4: 통과 확인**

Expected: 9개 PASS.
- `PoleOnRailIsPassedWithTwentyCentimetres` 가 실패하면 여유 값을 출력해 본다: `for (auto & s : ls.scores()) printf(...)`.
- 여유 0.2 판정 허용폭(0.03)은 chamfer 오차 때문에 둔 것이다. 가중치를 바꾸지 말고 원인부터 확인한다.

- [ ] **Step 5: 커밋** — `git commit -m "feat(vcc): 차선 13개 고르기 — 20 cm 확보 > 레일 가까움 > 차선 유지, 0.3 s 줏대·1 s 복귀·옆 이동 0.10 m/s·옮기는 동안 감속"`

---

### Task 8: 유턴 방식 고르기 (`turn_planner`)

**Files:**
- Create: `include/vica_vcc_controller/core/turn_planner.hpp`, `src/core/turn_planner.cpp`
- Test: `test/test_turn_planner.cpp`
- Modify: `CMakeLists.txt`

**Interfaces:**
- Consumes: `ClearanceFn`, `sweptLateralExtent`, `padFootprint`, `densifyOutline`, `toParent`
- Produces:
  - `enum class TurnMode{Arc, Pivot, Blocked}`
  - `struct TurnPlan{TurnMode mode=Blocked; double radius=0; int direction=1; double min_clearance=0;}`
  - `struct TurnParams{std::vector<double> radii{0.2,0.1}; double clearance=0.05, arc_w=0.45, pivot_w=0.35, run_in_decel=0.3, sample_angle=0.05, both_sides_angle=170°;}`
  - `double simulateTurnClearance(double angle, double radius, int dir, double run_in, const ClearanceFn&, double sample_angle)`
  - `TurnPlan planTurn(double heading_error, double v_now, bool pivot_first, const ClearanceFn&, const TurnParams&)`
  - `Twist2D turnCommand(const TurnPlan&, const TurnParams&)`

값 근거:

- `arc_w` 0.45 는 DWB 시절 출발 U턴 실측값이다. |w| 0.42~0.47 로 "부드러웠다"(devlog 2026-09-17-route-0903d §5.4). 설계서 11절은 0.5 로 적었지만, 손잡이 끝 속도를 줄이려고 실측값을 쓴다. 설계서도 함께 고친다(Task 14).
- `pivot_w` 0.35 는 지금 RPP `rotate_to_heading_angular_vel` 이다.

- [ ] **Step 1: 실패하는 시험** — `test/test_turn_planner.cpp`

```cpp
#include <gtest/gtest.h>
#include <algorithm>
#include <cmath>
#include "vica_vcc_controller/core/geometry.hpp"
#include "vica_vcc_controller/core/turn_planner.hpp"

using namespace vica_vcc_controller::core;

namespace
{
const Polygon kFootprint{{0.151, 0.225}, {0.151, -0.225}, {-0.459, -0.225},
  {-0.569, -0.035}, {-0.569, 0.035}, {-0.459, 0.225}};
const Polygon kPadded = padFootprint(kFootprint, 0.05);

// y = lo, y = hi 두 벽 사이 복도. 여유 = 몸 윤곽에서 가까운 벽까지(정확한 해석식).
ClearanceFn corridor(double lo, double hi)
{
  const Polygon outline = densifyOutline(kPadded, 0.01);
  return [outline, lo, hi](const Pose2D & p) {
      double c = 1e9;
      for (const auto & q : outline) {
        const Point2D g = toParent(p, q);
        c = std::min({c, hi - g.y, g.y - lo});
      }
      return c;
    };
}
ClearanceFn open() {return [](const Pose2D &) {return 5.0;};}
}  // namespace

TEST(TurnPlanner, OpenSpaceUsesTwentyCentimetreArc)
{
  const TurnPlan t = planTurn(M_PI * 0.95, 0.0, false, open(), TurnParams{});
  EXPECT_EQ(t.mode, TurnMode::Arc);
  EXPECT_NEAR(t.radius, 0.2, 1e-9);
  EXPECT_EQ(t.direction, 1);
}

TEST(TurnPlanner, NarrowCorridorFallsBackToTenCentimetres)
{
  const auto [lo1, hi1] = sweptLateralExtent(kPadded, 0.1, M_PI * 0.95, 190);
  const TurnPlan t = planTurn(M_PI * 0.95, 0.0, false, corridor(lo1 - 0.06, hi1 + 0.06), TurnParams{});
  EXPECT_EQ(t.mode, TurnMode::Arc);
  EXPECT_NEAR(t.radius, 0.1, 1e-9);
}

TEST(TurnPlanner, TighterCorridorFallsBackToPivot)
{
  const auto [lo0, hi0] = sweptLateralExtent(kPadded, 0.0, M_PI * 0.95, 190);
  const TurnPlan t = planTurn(M_PI * 0.95, 0.0, false, corridor(lo0 - 0.06, hi0 + 0.06), TurnParams{});
  EXPECT_EQ(t.mode, TurnMode::Pivot);
}

TEST(TurnPlanner, NoRoomIsBlocked)
{
  const auto [lo0, hi0] = sweptLateralExtent(kPadded, 0.0, M_PI * 0.95, 190);
  const TurnPlan t = planTurn(M_PI * 0.95, 0.0, false, corridor(lo0 + 0.05, hi0 - 0.05), TurnParams{});
  EXPECT_EQ(t.mode, TurnMode::Blocked);
}

TEST(TurnPlanner, StationarySmallTurnPrefersPivot)
{
  // 사용자 확인: 정지 상태에서 60도 까지는 제자리
  const TurnPlan t = planTurn(0.8, 0.0, true, open(), TurnParams{});
  EXPECT_EQ(t.mode, TurnMode::Pivot);
}

TEST(TurnPlanner, NearHalfTurnPicksTheSideWithRoom)
{
  // 175도: 왼쪽으로 돌면 몸이 +y 로, 오른쪽이면 -y 로 쓴다. 왼쪽 벽을 가깝게 두면 오른쪽을 골라야 한다.
  const auto [lo, hi] = sweptLateralExtent(kPadded, 0.2, M_PI, 180);
  const double margin = 0.3;
  // 왼쪽 회전의 hi 는 막고(hi - 0.1), 오른쪽 회전이 쓰는 -hi 쪽은 넉넉히
  const TurnPlan t = planTurn(175.0 * M_PI / 180.0, 0.0, false,
      corridor(-hi - margin, hi - 0.1), TurnParams{});
  EXPECT_EQ(t.direction, -1);
  (void)lo;
}

TEST(TurnPlanner, ArcCommandKeepsRadius)
{
  TurnPlan t;
  t.mode = TurnMode::Arc; t.radius = 0.2; t.direction = -1;
  const Twist2D c = turnCommand(t, TurnParams{});
  EXPECT_NEAR(c.v, 0.45 * 0.2, 1e-9);
  EXPECT_NEAR(c.w, -0.45, 1e-9);
}
```

- [ ] **Step 2: 실패 확인** — Expected: FAIL

- [ ] **Step 3: 구현** — `core/turn_planner.hpp`

```cpp
#pragma once
#include <cmath>
#include <vector>
#include "vica_vcc_controller/core/clearance.hpp"
#include "vica_vcc_controller/core/types.hpp"

namespace vica_vcc_controller::core
{
enum class TurnMode { Arc, Pivot, Blocked };

struct TurnPlan
{
  TurnMode mode{TurnMode::Blocked};
  double radius{0.0};
  int direction{1};        // +1 왼쪽(반시계), -1 오른쪽
  double min_clearance{0.0};
};

struct TurnParams
{
  std::vector<double> radii{0.2, 0.1};   // 설계서 3.3: DWB 최소 ≈ 0.2, 0630 통로 1.3 m
  double clearance{0.05};
  double arc_w{0.45};                    // DWB U턴 실측 0.42~0.47(devlog 09-17 §5.4)
  double pivot_w{0.35};                  // RPP rotate_to_heading_angular_vel
  double run_in_decel{0.3};
  double sample_angle{0.05};
  double both_sides_angle{170.0 * M_PI / 180.0};
};

// 로봇 좌표계에서 run_in 만큼 직진한 뒤 dir 쪽으로 반지름 radius(0 = 제자리) 호를 angle 만큼.
double simulateTurnClearance(
  double angle, double radius, int dir, double run_in, const ClearanceFn & f, double sample_angle);
TurnPlan planTurn(
  double heading_error, double v_now, bool pivot_first, const ClearanceFn & f, const TurnParams & p);
Twist2D turnCommand(const TurnPlan & t, const TurnParams & p);
}  // namespace vica_vcc_controller::core
```

`src/core/turn_planner.cpp`:

```cpp
#include "vica_vcc_controller/core/turn_planner.hpp"

#include <algorithm>
#include <limits>
#include <utility>

namespace vica_vcc_controller::core
{
double simulateTurnClearance(
  double angle, double radius, int dir, double run_in, const ClearanceFn & f, double sample_angle)
{
  double c = std::numeric_limits<double>::infinity();
  for (double s = 0.0; s < run_in; s += 0.05) {c = std::min(c, f({s, 0.0, 0.0}));}
  const int n = std::max(1, static_cast<int>(std::ceil(angle / sample_angle)));
  for (int i = 0; i <= n; ++i) {
    const double th = angle * i / n;
    c = std::min(c, f({run_in + radius * std::sin(th), dir * radius * (1.0 - std::cos(th)), dir * th}));
  }
  return c;
}

TurnPlan planTurn(
  double heading, double v_now, bool pivot_first, const ClearanceFn & f, const TurnParams & p)
{
  const int pref = heading >= 0.0 ? 1 : -1;
  const double a = std::abs(heading);
  std::vector<std::pair<int, double>> dirs{{pref, a}};
  if (a >= p.both_sides_angle) {dirs.push_back({-pref, 2.0 * M_PI - a});}

  std::vector<double> order;
  if (pivot_first) {order.push_back(0.0);}
  for (double r : p.radii) {order.push_back(r);}
  if (!pivot_first) {order.push_back(0.0);}

  for (double R : order) {
    TurnPlan best;
    bool found = false;
    for (const auto & [dir, ang] : dirs) {
      const double w = R > 0.0 ? p.arc_w : p.pivot_w;
      const double v_turn = w * R;
      const double run_in = std::max(0.0, v_now * v_now - v_turn * v_turn) / (2.0 * p.run_in_decel);
      const double c = simulateTurnClearance(ang, R, dir, run_in, f, p.sample_angle);
      if (c >= p.clearance && (!found || c > best.min_clearance)) {
        best = {R > 0.0 ? TurnMode::Arc : TurnMode::Pivot, R, dir, c};
        found = true;
      }
    }
    if (found) {return best;}
  }
  return TurnPlan{};
}

Twist2D turnCommand(const TurnPlan & t, const TurnParams & p)
{
  switch (t.mode) {
    case TurnMode::Arc: return {p.arc_w * t.radius, t.direction * p.arc_w};
    case TurnMode::Pivot: return {0.0, t.direction * p.pivot_w};
    default: return {0.0, 0.0};
  }
}
}  // namespace vica_vcc_controller::core
```

`CMakeLists.txt`: 소스와 `test_turn_planner` 를 추가한다.

- [ ] **Step 4: 통과 확인** — Expected: 7개 PASS
- [ ] **Step 5: 커밋** — `git commit -m "feat(vcc): 유턴 방식 고르기 — R 0.2 → 0.1 → 제자리 → 막힘, 몸 모양으로 가상 주행"`

---

### Task 9: 도착 정렬 (`AlignPlanner`)

**Files:**
- Create: `include/vica_vcc_controller/core/align_planner.hpp`, `src/core/align_planner.cpp`
- Test: `test/test_align_planner.cpp`
- Modify: `CMakeLists.txt`

**Interfaces:**
- Produces:
  - `struct AlignParams{w_max=0.35, alpha=1.2, motor_lag=0.35, settle=0.3, stopped_w=0.05, max_attempts=3, lag_min=0.0, lag_max=1.0;}`
  - `enum class AlignPhase{Idle, Rotating, Settling, Done, Failed}`
  - `class AlignPlanner`
    - `void reset()`
    - `double update(double yaw_error, double measured_w, double tol, double now, double dt)`
    - `AlignPhase phase() const`, `int attempts() const`, `double lagEstimate() const`

근거:

- 2026-09-24 이 계획을 쓸 때 파이썬으로 모사했다. 지연 모터(0.3/0.35/0.5 s 순수 지연 + 각가속 2.0)에서 20·45·90·145·−100·180° 가 모두 **1회에 오차 ≤ 5.4°** 였다.
- 시험은 같은 모형을 C++ 로 옮긴다.

- [ ] **Step 1: 실패하는 시험** — `test/test_align_planner.cpp`

```cpp
#include <gtest/gtest.h>
#include <algorithm>
#include <cmath>
#include <deque>
#include "vica_vcc_controller/core/align_planner.hpp"

using namespace vica_vcc_controller::core;

namespace
{
struct Result { AlignPhase phase; int attempts; double final_err; };

// 모터 모형: 명령이 delay 만큼 늦게 도착하고, 각가속 2.0 rad/s^2 로 따라간다(run41 지연 0.3~0.5 s).
Result simulate(double err0, double delay, double tol = 0.25, AlignParams ap = {})
{
  AlignPlanner a(ap);
  const double dt = 0.1;
  std::deque<double> q(static_cast<size_t>(std::round(delay / dt)), 0.0);
  double yaw = 0.0, w_act = 0.0;
  for (int k = 0; k < 600; ++k) {
    const double t = k * dt;
    const double cmd = a.update(err0 - yaw, w_act, tol, t, dt);
    q.push_back(cmd);
    const double c = q.front();
    q.pop_front();
    w_act += std::clamp(c - w_act, -2.0 * dt, 2.0 * dt);
    yaw += w_act * dt;
    if ((a.phase() == AlignPhase::Done || a.phase() == AlignPhase::Failed) && std::abs(w_act) < 1e-3) {
      break;
    }
  }
  return {a.phase(), a.attempts(), err0 - yaw};
}
}  // namespace

TEST(AlignPlanner, OneShotForTypicalErrorsAndLags)
{
  for (double deg : {20.0, 45.0, 90.0, 145.0, -100.0, 180.0}) {
    for (double delay : {0.3, 0.35, 0.5}) {
      const Result r = simulate(deg * M_PI / 180.0, delay);
      EXPECT_EQ(r.phase, AlignPhase::Done) << deg << " " << delay;
      EXPECT_EQ(r.attempts, 1) << deg << " " << delay;
      EXPECT_LE(std::abs(r.final_err), 6.0 * M_PI / 180.0) << deg << " " << delay;
    }
  }
}

TEST(AlignPlanner, AlreadyAlignedDoesNothing)
{
  AlignPlanner a;
  EXPECT_EQ(a.update(0.1, 0.0, 0.25, 0.0, 0.1), 0.0);
  EXPECT_EQ(a.phase(), AlignPhase::Done);
  EXPECT_EQ(a.attempts(), 0);
}

TEST(AlignPlanner, LearnsLagAndCorrectsWithinThreeAttempts)
{
  // 지연 1.0 s 인데 추정은 0.35 -> 첫 회 넘침. 두 번째부터 배운 값으로 끊는다.
  AlignParams ap;
  const Result r = simulate(M_PI / 2, 1.0, 0.25, ap);
  EXPECT_EQ(r.phase, AlignPhase::Done);
  EXPECT_LE(r.attempts, 3);
  EXPECT_LE(std::abs(r.final_err), 0.25);
}

TEST(AlignPlanner, FailsAfterMaxAttempts)
{
  // 허용오차를 비현실적으로 좁혀 매번 실패하게 한다.
  const Result r = simulate(M_PI / 2, 0.35, 0.001);
  EXPECT_EQ(r.phase, AlignPhase::Failed);
  EXPECT_EQ(r.attempts, 3);
}
```

- [ ] **Step 2: 실패 확인** — Expected: FAIL

- [ ] **Step 3: 구현** — `core/align_planner.hpp`

```cpp
#pragma once

namespace vica_vcc_controller::core
{
struct AlignParams
{
  double w_max{0.35};      // RPP rotate_to_heading_angular_vel (run41 되돌림)
  double alpha{1.2};       // RPP max_angular_accel
  double motor_lag{0.35};  // run41 모터 지연 0.3~0.5 s 에서 고름 [추정] — 회차마다 갱신
  double settle{0.3};
  double stopped_w{0.05};  // goal checker rot_stopped_velocity
  int max_attempts{3};     // 사용자 결정 2026-09-24
  double lag_min{0.0};
  double lag_max{1.0};
};

enum class AlignPhase { Idle, Rotating, Settling, Done, Failed };

// 남은 각만큼 한 번에 돌고, 멈춘 뒤 확인한다(설계서 5.3).
class AlignPlanner
{
public:
  explicit AlignPlanner(AlignParams p = {}) : p_(p), lag_(p.motor_lag) {}
  void reset();
  // yaw_error = 목표 - 현재(정규화). 반환 = 회전 명령.
  double update(double yaw_error, double measured_w, double tol, double now, double dt);
  AlignPhase phase() const {return phase_;}
  int attempts() const {return attempts_;}
  double lagEstimate() const {return lag_;}

private:
  void begin(double err);

  AlignParams p_;
  AlignPhase phase_{AlignPhase::Idle};
  double lag_;
  double dir_{1.0};
  double last_w_{0.0};
  double cut_err_{0.0};
  double cut_w_{0.0};
  double settle_since_{-1.0};
  int attempts_{0};
};
}  // namespace vica_vcc_controller::core
```

`src/core/align_planner.cpp`:

```cpp
#include "vica_vcc_controller/core/align_planner.hpp"

#include <algorithm>
#include <cmath>

namespace vica_vcc_controller::core
{
void AlignPlanner::reset()
{
  phase_ = AlignPhase::Idle;
  lag_ = p_.motor_lag;
  last_w_ = cut_err_ = cut_w_ = 0.0;
  settle_since_ = -1.0;
  attempts_ = 0;
}

void AlignPlanner::begin(double err)
{
  ++attempts_;
  dir_ = err >= 0.0 ? 1.0 : -1.0;
  last_w_ = 0.0;
  phase_ = AlignPhase::Rotating;
}

double AlignPlanner::update(double err, double measured_w, double tol, double now, double dt)
{
  switch (phase_) {
    case AlignPhase::Idle:
      if (std::abs(err) <= tol) {phase_ = AlignPhase::Done; return 0.0;}
      begin(err);
      [[fallthrough]];
    case AlignPhase::Rotating: {
        const double rem = dir_ * err;
        // 모터 지연만큼 일찍 끊는다 — run41 넘침 ±16~21° 의 원인이 지연 0.3~0.5 s 였다.
        if (rem <= 0.0 || rem <= std::abs(last_w_) * lag_) {
          cut_err_ = err;
          cut_w_ = last_w_;
          last_w_ = 0.0;
          settle_since_ = -1.0;
          phase_ = AlignPhase::Settling;
          return 0.0;
        }
        const double w = std::min(
          {p_.w_max, std::sqrt(2.0 * p_.alpha * rem), std::abs(last_w_) + p_.alpha * dt});
        last_w_ = dir_ * w;
        return last_w_;
      }
    case AlignPhase::Settling:
      if (std::abs(measured_w) >= p_.stopped_w) {settle_since_ = -1.0; return 0.0;}
      if (settle_since_ < 0.0) {settle_since_ = now;}
      if (now - settle_since_ < p_.settle - 1e-9) {return 0.0;}
      if (std::abs(cut_w_) > 0.05) {
        const double extra = dir_ * (cut_err_ - err);   // 끊은 뒤 더 돈 각
        lag_ = std::clamp(extra / std::abs(cut_w_), p_.lag_min, p_.lag_max);
      }
      if (std::abs(err) <= tol) {phase_ = AlignPhase::Done; return 0.0;}
      if (attempts_ >= p_.max_attempts) {phase_ = AlignPhase::Failed; return 0.0;}
      begin(err);
      return 0.0;
    case AlignPhase::Done:
      // 정렬 뒤 AMCL 재정렬 등으로 다시 벗어나면 남은 횟수 안에서만 다시 돈다.
      if (std::abs(err) > tol) {
        if (attempts_ >= p_.max_attempts) {phase_ = AlignPhase::Failed; return 0.0;}
        begin(err);
      }
      return 0.0;
    case AlignPhase::Failed:
    default:
      return 0.0;
  }
}
}  // namespace vica_vcc_controller::core
```

`CMakeLists.txt`: 소스와 `test_align_planner` 를 추가한다.

- [ ] **Step 4: 통과 확인**

Expected: 4개 PASS.
- `OneShotForTypicalErrorsAndLags` 가 실패하면 먼저 시험 모형이 계획서 근거의 파이썬 모사와 같은지 확인한다(지연 큐 길이, 각가속 2.0).
- 그다음에 `motor_lag` 을 본다. 값을 고쳐 억지로 맞추지 않는다.

- [ ] **Step 5: 커밋** — `git commit -m "feat(vcc): 도착 정렬 — 남은 각 한 번 회전, 모터 지연만큼 일찍 끊고 넘침으로 지연 학습, 최대 3회"`

---

### Task 10: 상황 전환 (`StateMachine`)

**Files:**
- Create: `include/vica_vcc_controller/core/state_machine.hpp`, `src/core/state_machine.cpp`
- Test: `test/test_state_machine.cpp`
- Modify: `CMakeLists.txt`

**Interfaces:**
- Produces:
  - `enum class State{Track, Turn, Align, Hold}`
  - `const char* stateName(State)`
  - `bool transitionAllowed(State from, State to)`
  - `struct StateParams{turn_enter_angle=1.047, turn_exit_angle=0.436, pivot_start_angle=0.611, align_exit_margin=0.10, min_state_time=0.5;}`
  - `struct StateInputs{now, stationary, heading_error, path_heading_error, dist_to_end, yaw_error_end, xy_tol, yaw_tol, lanes_blocked, turn_blocked, collision_imminent, align_failed;}`
  - `bool turnNeeded(const StateInputs&, const StateParams&)`
  - `class StateMachine{ void reset(); State update(const StateInputs&); State state() const; const char* reason() const; }`

유턴 판정(설계서 5.2 를 보완, Review Focus 1):

- 조준점 각 **과** 레일 방향 각이 **둘 다** 문턱을 넘어야 유턴이다.
- 레일과 나란히 0.55 m 떨어져 있으면, 느릴 때 조준점 각이 66° 가 되지만 레일 방향 각은 0° 다. 그러면 곡선으로 합류한다(요구 3).

- [ ] **Step 1: 실패하는 시험** — `test/test_state_machine.cpp`

```cpp
#include <gtest/gtest.h>
#include <cmath>
#include "vica_vcc_controller/core/state_machine.hpp"

using namespace vica_vcc_controller::core;

namespace
{
constexpr double kDeg = M_PI / 180.0;
StateInputs base(double now)
{
  StateInputs in;
  in.now = now;
  in.dist_to_end = 5.0;
  return in;
}
}  // namespace

TEST(StateMachine, TransitionTableEveryCell)
{
  const State all[] = {State::Track, State::Turn, State::Align, State::Hold};
  // 허용: 설계서 6.1 표
  const bool allowed[4][4] = {
    //            Track  Turn   Align  Hold
    /* Track */ {false, true,  true,  true},
    /* Turn  */ {true,  false, true,  true},
    /* Align */ {true,  false, false, true},
    /* Hold  */ {true,  false, false, false},
  };
  for (int i = 0; i < 4; ++i) {
    for (int j = 0; j < 4; ++j) {
      EXPECT_EQ(transitionAllowed(all[i], all[j]), allowed[i][j]) << i << "->" << j;
    }
  }
}

TEST(StateMachine, MovingUturnEntersAboveSixtyDegrees)
{
  StateMachine sm;
  StateInputs in = base(1.0);
  in.heading_error = 70 * kDeg; in.path_heading_error = 170 * kDeg;
  EXPECT_EQ(sm.update(in), State::Turn);
  StateMachine sm2;
  in.heading_error = 55 * kDeg;
  EXPECT_EQ(sm2.update(in), State::Track);
}

TEST(StateMachine, ParallelOffsetRailIsNotAUturn)
{
  // Review Focus 1: 레일과 나란히 0.55 m 떨어짐 -> 조준점 66도, 레일 방향 0도
  StateMachine sm;
  StateInputs in = base(1.0);
  in.heading_error = -66 * kDeg; in.path_heading_error = 0.0;
  EXPECT_EQ(sm.update(in), State::Track);
}

TEST(StateMachine, StationaryPivotFromThirtyFiveDegrees)
{
  StateMachine sm;
  StateInputs in = base(1.0);
  in.stationary = true; in.heading_error = 45 * kDeg; in.path_heading_error = 45 * kDeg;
  EXPECT_EQ(sm.update(in), State::Turn);
}

TEST(StateMachine, TurnHasHysteresis)
{
  StateMachine sm;
  StateInputs in = base(1.0);
  in.heading_error = 90 * kDeg; in.path_heading_error = 180 * kDeg;
  ASSERT_EQ(sm.update(in), State::Turn);
  in.now = 2.0; in.heading_error = 40 * kDeg;
  EXPECT_EQ(sm.update(in), State::Turn);    // 25도 밑이 아니면 유지
  in.now = 2.1; in.heading_error = 20 * kDeg;
  EXPECT_EQ(sm.update(in), State::Track);
}

TEST(StateMachine, MinimumStateTimeBlocksQuickFlip)
{
  StateMachine sm;
  StateInputs in = base(1.0);
  in.heading_error = 90 * kDeg; in.path_heading_error = 180 * kDeg;
  ASSERT_EQ(sm.update(in), State::Turn);
  in.now = 1.3; in.heading_error = 10 * kDeg;
  EXPECT_EQ(sm.update(in), State::Turn);    // 0.3 s < 0.5 s
  in.now = 1.6;
  EXPECT_EQ(sm.update(in), State::Track);
}

TEST(StateMachine, SafetyStopIsImmediateFromAnyState)
{
  StateMachine sm;
  StateInputs in = base(1.0);
  in.heading_error = 90 * kDeg; in.path_heading_error = 180 * kDeg;
  ASSERT_EQ(sm.update(in), State::Turn);
  in.now = 1.05; in.collision_imminent = true;
  EXPECT_EQ(sm.update(in), State::Hold);    // 최소 유지 시간 무시
}

TEST(StateMachine, ArrivalBeatsUturnAndCannotTurnAfterwards)
{
  StateMachine sm;
  StateInputs in = base(1.0);
  in.dist_to_end = 0.1; in.yaw_error_end = 120 * kDeg;
  in.heading_error = 170 * kDeg; in.path_heading_error = 170 * kDeg;
  EXPECT_EQ(sm.update(in), State::Align);
  in.now = 5.0;
  EXPECT_EQ(sm.update(in), State::Align);   // Align -> Turn 금지
}

TEST(StateMachine, AlignExitNeedsMargin)
{
  StateMachine sm;
  StateInputs in = base(1.0);
  in.dist_to_end = 0.1; in.yaw_error_end = 1.0;
  ASSERT_EQ(sm.update(in), State::Align);
  in.now = 2.0; in.dist_to_end = 0.30;
  EXPECT_EQ(sm.update(in), State::Align);   // 0.25 + 0.10 안
  in.now = 2.1; in.dist_to_end = 0.36;
  EXPECT_EQ(sm.update(in), State::Track);
}

TEST(StateMachine, AlignFailureHoldsUntilReset)
{
  StateMachine sm;
  StateInputs in = base(1.0);
  in.dist_to_end = 0.1; in.yaw_error_end = 1.0;
  ASSERT_EQ(sm.update(in), State::Align);
  in.now = 2.0; in.align_failed = true;
  EXPECT_EQ(sm.update(in), State::Hold);
  in.now = 5.0;
  EXPECT_EQ(sm.update(in), State::Hold);
  sm.reset();
  EXPECT_EQ(sm.state(), State::Track);
}

TEST(StateMachine, HoldReleasesWhenPathOpens)
{
  StateMachine sm;
  StateInputs in = base(1.0);
  in.lanes_blocked = true;
  ASSERT_EQ(sm.update(in), State::Hold);
  in.now = 1.2; in.lanes_blocked = false;
  EXPECT_EQ(sm.update(in), State::Hold);    // 최소 유지
  in.now = 1.6;
  EXPECT_EQ(sm.update(in), State::Track);
}

TEST(StateMachine, BlockedTurnGoesToHold)
{
  StateMachine sm;
  StateInputs in = base(1.0);
  in.heading_error = 90 * kDeg; in.path_heading_error = 180 * kDeg; in.turn_blocked = true;
  EXPECT_EQ(sm.update(in), State::Hold);
}
```

- [ ] **Step 2: 실패 확인** — Expected: FAIL

- [ ] **Step 3: 구현** — `core/state_machine.hpp`

```cpp
#pragma once

namespace vica_vcc_controller::core
{
enum class State { Track, Turn, Align, Hold };
const char * stateName(State s);
bool transitionAllowed(State from, State to);

struct StateParams
{
  double turn_enter_angle{1.047};   // 60도 (요구 2)
  double turn_exit_angle{0.436};    // 25도 (히스테리시스)
  double pivot_start_angle{0.611};  // 35도 (정지 출발, 사용자 확인)
  double align_exit_margin{0.10};   // 도착 0.25 로 들어가고 0.35 로 나온다
  double min_state_time{0.5};
};

struct StateInputs
{
  double now{0.0};
  bool stationary{false};
  double heading_error{0.0};       // 조준점 각
  double path_heading_error{0.0};  // 조준점 구간의 레일 방향 각
  double dist_to_end{1e9};
  double yaw_error_end{0.0};
  double xy_tol{0.25};
  double yaw_tol{0.25};
  bool lanes_blocked{false};
  bool turn_blocked{false};
  bool collision_imminent{false};
  bool align_failed{false};
};

bool turnNeeded(const StateInputs & in, const StateParams & p);

class StateMachine
{
public:
  explicit StateMachine(StateParams p = {}) : p_(p) {}
  void reset();
  State update(const StateInputs & in);
  State state() const {return s_;}
  const char * reason() const {return reason_;}

private:
  void go(State to, double now, const char * why);
  StateParams p_;
  State s_{State::Track};
  double entered_{-1e9};
  const char * reason_{"init"};
};
}  // namespace vica_vcc_controller::core
```

`src/core/state_machine.cpp`:

```cpp
#include "vica_vcc_controller/core/state_machine.hpp"

#include <cmath>

namespace vica_vcc_controller::core
{
const char * stateName(State s)
{
  switch (s) {
    case State::Track: return "TRACK";
    case State::Turn: return "TURN";
    case State::Align: return "ALIGN";
    case State::Hold: return "HOLD";
  }
  return "?";
}

bool transitionAllowed(State from, State to)
{
  if (from == to) {return false;}
  switch (from) {
    case State::Track: return true;
    case State::Turn: return true;
    case State::Align: return to == State::Track || to == State::Hold;
    case State::Hold: return to == State::Track;
  }
  return false;
}

bool turnNeeded(const StateInputs & in, const StateParams & p)
{
  const double th = in.stationary ? p.pivot_start_angle : p.turn_enter_angle;
  return std::abs(in.heading_error) > th && std::abs(in.path_heading_error) > th;
}

void StateMachine::reset()
{
  s_ = State::Track;
  entered_ = -1e9;
  reason_ = "reset";
}

void StateMachine::go(State to, double now, const char * why)
{
  if (!transitionAllowed(s_, to)) {return;}
  s_ = to;
  entered_ = now;
  reason_ = why;
}

State StateMachine::update(const StateInputs & in)
{
  const bool held = in.now - entered_ >= p_.min_state_time - 1e-9;
  const bool arrived = in.dist_to_end < in.xy_tol;
  const bool yaw_off = std::abs(in.yaw_error_end) > in.yaw_tol;

  // 우선순위 1: 안전 — 최소 유지 시간을 무시한다.
  if (in.collision_imminent) {
    if (s_ != State::Hold) {go(State::Hold, in.now, "collision_imminent");}
    return s_;
  }

  switch (s_) {
    case State::Track:
      if (in.lanes_blocked) {go(State::Hold, in.now, "lanes_blocked"); break;}
      if (arrived && yaw_off) {go(State::Align, in.now, "arrived_yaw_off"); break;}
      if (!held) {break;}
      if (!arrived && turnNeeded(in, p_)) {
        if (in.turn_blocked) {go(State::Hold, in.now, "turn_blocked");} else {
          go(State::Turn, in.now, "heading_error");
        }
      }
      break;
    case State::Turn:
      if (in.turn_blocked) {go(State::Hold, in.now, "turn_blocked"); break;}
      if (arrived) {
        go(yaw_off ? State::Align : State::Track, in.now, "arrived_during_turn");
        break;
      }
      if (!held) {break;}
      if (std::abs(in.heading_error) < p_.turn_exit_angle) {go(State::Track, in.now, "turn_done");}
      break;
    case State::Align:
      if (in.align_failed) {go(State::Hold, in.now, "align_failed"); break;}
      if (!held) {break;}
      if (in.dist_to_end > in.xy_tol + p_.align_exit_margin) {
        go(State::Track, in.now, "pushed_off_goal");
      }
      break;
    case State::Hold:
      if (!held) {break;}
      if (!in.lanes_blocked && !in.align_failed) {go(State::Track, in.now, "path_open");}
      break;
  }
  return s_;
}
}  // namespace vica_vcc_controller::core
```

참고 — 도착(`arrived_yaw_off`)은 최소 유지 시간 전에도 들어간다:

- 설계서 6.2 의 우선순위 "도착 > 유턴"을 지키기 위해서다.
- `ArrivalBeatsUturnAndCannotTurnAfterwards` 는 새로 만든 기계의 첫 update 에서 Align 이 나와야 한다.
- 새 기계의 `entered_` 는 −1e9 라서 어느 쪽이든 통과한다.
- 이 순서를 바꾸지 않는다.

`CMakeLists.txt`: 소스와 `test_state_machine` 을 추가한다.

- [ ] **Step 4: 통과 확인** — Expected: 12개 PASS
- [ ] **Step 5: 커밋** — `git commit -m "feat(vcc): 상황 4개 전환 — 전환표·60/25도 히스테리시스·0.5 s 유지·안전 즉시·평행 이탈은 유턴 아님"`

---

### Task 11: 한 주기 조립 (`VccCore`)

**Files:**
- Create: `include/vica_vcc_controller/core/vcc_core.hpp`, `src/core/vcc_core.cpp`
- Test: `test/test_vcc_core.cpp`
- Modify: `CMakeLists.txt`

**Interfaces:**
- Consumes: Task 1~10 의 모든 공개 이름
- Produces:
  - `struct CoreParams{Polygon footprint; LookaheadParams lookahead; SpeedParams speed; OutputParams output; LaneParams lane; TurnParams turn; AlignParams align; StateParams state; double stop_latency=0.3, stop_margin=0.05, stationary_speed=0.05, stationary_time=0.5;}`
  - `enum class Failure{None, CollisionAhead, Blocked, AlignFailed}`
  - `struct CoreInputs{double now, dt; Path path; Pose2D goal; Twist2D measured; double xy_tol, yaw_tol, speed_cap; ClearanceFn clearance;}`
    - path·goal 은 로봇 좌표계다.
  - `struct CoreOutput{Twist2D cmd; State state; double offset, target; bool lanes_blocked; TurnMode turn_mode; int align_attempts; Failure failure; const char* reason; Path lane_path;}`
  - `class VccCore{ void configure(const CoreParams&); void reset(); CoreOutput step(const CoreInputs&); }`

- [ ] **Step 1: 실패하는 시험** — `test/test_vcc_core.cpp`

```cpp
#include <gtest/gtest.h>
#include <cmath>
#include "vica_vcc_controller/core/clearance.hpp"
#include "vica_vcc_controller/core/geometry.hpp"
#include "vica_vcc_controller/core/vcc_core.hpp"

using namespace vica_vcc_controller::core;

namespace
{
const Polygon kFootprint{{0.151, 0.225}, {0.151, -0.225}, {-0.459, -0.225},
  {-0.569, -0.035}, {-0.569, 0.035}, {-0.459, 0.225}};

CoreParams params()
{
  CoreParams p;
  p.footprint = padFootprint(kFootprint, 0.05);
  return p;
}

Path line(double y0, double yaw, double length = 3.0)
{
  Path p;
  for (double s = 0.0; s <= length + 1e-9; s += 0.05) {
    p.push_back({s * std::cos(yaw), y0 + s * std::sin(yaw), yaw});
  }
  return p;
}

struct World
{
  ClearanceField f;
  World()
  {
    f.setFootprint(padFootprint(kFootprint, 0.05));
    f.grid().reset(-2.5, -2.5, 0.05, 100, 100);
    f.grid().compute();
  }
  void box(double x0, double x1, double y0, double y1)
  {
    for (int ix = 0; ix < 100; ++ix) {
      for (int iy = 0; iy < 100; ++iy) {
        const double cx = -2.5 + (ix + 0.5) * 0.05, cy = -2.5 + (iy + 0.5) * 0.05;
        if (cx >= x0 && cx <= x1 && cy >= y0 && cy <= y1) {f.grid().markLethal(ix, iy);}
      }
    }
    f.grid().compute();
  }
  ClearanceFn fn() const {return [this](const Pose2D & p) {return f.clearance(p);};}
};

CoreInputs inputs(const Path & path, const World & w, double now, double v, double w_meas = 0.0)
{
  CoreInputs in;
  in.now = now; in.dt = 0.1; in.path = path; in.goal = {10.0, 0.0, 0.0};
  in.measured = {v, w_meas}; in.speed_cap = 0.5; in.clearance = w.fn();
  return in;
}
}  // namespace

TEST(VccCore, StraightStartRampsWithoutTurning)
{
  VccCore c; c.configure(params());
  World w;
  double v = 0.0;
  CoreOutput out;
  for (int i = 0; i < 5; ++i) {out = c.step(inputs(line(0.0, 0.0), w, 0.1 * i, v)); v = out.cmd.v;}
  EXPECT_EQ(out.state, State::Track);
  EXPECT_NEAR(out.cmd.v, 0.25, 0.051);
  EXPECT_NEAR(out.cmd.w, 0.0, 1e-6);
  EXPECT_EQ(out.failure, Failure::None);
}

TEST(VccCore, ParallelOffsetRejoinsWithoutStopping)
{
  // 요구 3: 레일에서 0.55 m 떨어져도 멈추고 틀지 않고 곡선으로 합류
  VccCore c; c.configure(params());
  World w;
  double v = 0.3;
  for (int i = 0; i < 20; ++i) {
    const CoreOutput out = c.step(inputs(line(-0.55, 0.0), w, 0.1 * i, v));
    EXPECT_EQ(out.state, State::Track) << i;
    EXPECT_GT(out.cmd.v, 0.0) << i;
    EXPECT_LT(out.cmd.w, 0.0) << i;   // 오른쪽(레일 쪽)으로
    v = out.cmd.v;
  }
}

TEST(VccCore, UturnWhileMovingUsesArc)
{
  VccCore c; c.configure(params());
  World w;
  // 레일이 뒤쪽으로: 0.1 m 앞에서 되돌아온다
  Path back;
  for (double s = 0.0; s <= 0.1; s += 0.05) {back.push_back({s, 0.0, 0.0});}
  for (double s = 0.05; s <= 2.0; s += 0.05) {back.push_back({0.1 - s, 0.0, M_PI});}
  const CoreOutput out = c.step(inputs(back, w, 1.0, 0.3));
  EXPECT_EQ(out.state, State::Turn);
  EXPECT_EQ(out.turn_mode, TurnMode::Arc);
}

TEST(VccCore, PoleIsPassedWithoutHold)
{
  VccCore c; c.configure(params());
  World w;
  w.box(1.2, 1.3, -0.05, 0.05);
  double v = 0.4;
  for (int i = 0; i < 10; ++i) {
    const CoreOutput out = c.step(inputs(line(0.0, 0.0), w, 0.1 * i, v));
    EXPECT_NE(out.state, State::Hold) << i;
    v = out.cmd.v;
  }
}

TEST(VccCore, WallInsideStoppingDistanceIsCollisionAhead)
{
  VccCore c; c.configure(params());
  World w;
  w.box(0.35, 0.40, -2.5, 2.5);   // 몸 앞면 0.201 에서 0.15 m
  const CoreOutput out = c.step(inputs(line(0.0, 0.0), w, 1.0, 0.4));
  EXPECT_EQ(out.failure, Failure::CollisionAhead);
  EXPECT_EQ(out.cmd.v, 0.0);
  EXPECT_EQ(out.state, State::Hold);
}

TEST(VccCore, BlockedCorridorHoldsAndReportsBlockedWhenStopped)
{
  VccCore c; c.configure(params());
  World w;
  w.box(1.2, 1.3, -2.5, 2.5);
  const CoreOutput out = c.step(inputs(line(0.0, 0.0), w, 1.0, 0.0));
  EXPECT_EQ(out.state, State::Hold);
  EXPECT_EQ(out.failure, Failure::Blocked);
}

TEST(VccCore, ArrivalWithWrongYawRotatesInPlace)
{
  VccCore c; c.configure(params());
  World w;
  CoreInputs in = inputs(line(0.0, 0.0, 0.1), w, 1.0, 0.0);
  in.goal = {0.1, 0.0, M_PI / 2};
  const CoreOutput out = c.step(in);
  EXPECT_EQ(out.state, State::Align);
  EXPECT_EQ(out.cmd.v, 0.0);
  EXPECT_GT(out.cmd.w, 0.0);
}

TEST(VccCore, ArrivalWithGoodYawStops)
{
  VccCore c; c.configure(params());
  World w;
  CoreInputs in = inputs(line(0.0, 0.0, 0.1), w, 1.0, 0.0);
  in.goal = {0.1, 0.0, 0.1};
  const CoreOutput out = c.step(in);
  EXPECT_EQ(out.state, State::Track);
  EXPECT_EQ(out.cmd.v, 0.0);
}

TEST(VccCore, SpeedCapFromSpeedLimitIsRespected)
{
  VccCore c; c.configure(params());
  World w;
  CoreInputs in = inputs(line(0.0, 0.0), w, 1.0, 0.2);
  in.speed_cap = 0.2;
  double v = 0.2;
  CoreOutput out;
  for (int i = 0; i < 30; ++i) {in.now = 1.0 + 0.1 * i; in.measured.v = v; out = c.step(in); v = out.cmd.v;}
  EXPECT_LE(out.cmd.v, 0.2 + 1e-9);
}
```

- [ ] **Step 2: 실패 확인** — Expected: FAIL

- [ ] **Step 3: 구현** — `core/vcc_core.hpp`

```cpp
#pragma once
#include "vica_vcc_controller/core/align_planner.hpp"
#include "vica_vcc_controller/core/clearance.hpp"
#include "vica_vcc_controller/core/lanes.hpp"
#include "vica_vcc_controller/core/output_stage.hpp"
#include "vica_vcc_controller/core/pure_pursuit.hpp"
#include "vica_vcc_controller/core/speed_profile.hpp"
#include "vica_vcc_controller/core/state_machine.hpp"
#include "vica_vcc_controller/core/turn_planner.hpp"

namespace vica_vcc_controller::core
{
struct CoreParams
{
  Polygon footprint;             // padding 포함, 로봇 좌표계
  LookaheadParams lookahead;
  SpeedParams speed;
  OutputParams output;
  LaneParams lane;
  TurnParams turn;
  AlignParams align;
  StateParams state;
  double stop_latency{0.3};      // backlog D2: CAN·드라이버 지연 300 ms
  double stop_margin{0.05};
  double stationary_speed{0.05};
  double stationary_time{0.5};
};

enum class Failure { None, CollisionAhead, Blocked, AlignFailed };

struct CoreInputs
{
  double now{0.0};
  double dt{0.1};
  Path path;                     // 로봇 좌표계, 가까운 점부터
  Pose2D goal;                   // 경로 마지막 점(로봇 좌표계)
  Twist2D measured;
  double xy_tol{0.25};
  double yaw_tol{0.25};
  double speed_cap{0.5};
  ClearanceFn clearance;         // 로봇 좌표계 자세 -> 여유
};

struct CoreOutput
{
  Twist2D cmd;
  State state{State::Track};
  double offset{0.0};
  double target{0.0};
  bool lanes_blocked{false};
  TurnMode turn_mode{TurnMode::Blocked};
  int align_attempts{0};
  Failure failure{Failure::None};
  const char * reason{""};
  Path lane_path;
};

class VccCore
{
public:
  void configure(const CoreParams & p);
  void reset();
  CoreOutput step(const CoreInputs & in);

private:
  CoreParams p_;
  LaneSelector lanes_;
  OutputStage output_;
  AlignPlanner align_;
  StateMachine sm_;
  TurnPlan turn_;
  double stopped_since_{-1.0};
};
}  // namespace vica_vcc_controller::core
```

`src/core/vcc_core.cpp`:

```cpp
#include "vica_vcc_controller/core/vcc_core.hpp"

#include <algorithm>
#include <cmath>

namespace vica_vcc_controller::core
{
void VccCore::configure(const CoreParams & p)
{
  p_ = p;
  lanes_ = LaneSelector(p.lane);
  output_ = OutputStage(p.output);
  align_ = AlignPlanner(p.align);
  sm_ = StateMachine(p.state);
  reset();
}

void VccCore::reset()
{
  lanes_.reset();
  output_.reset();
  align_.reset();
  sm_.reset();
  turn_ = TurnPlan{};
  stopped_since_ = -1.0;
}

CoreOutput VccCore::step(const CoreInputs & in)
{
  CoreOutput out;
  const double v = in.measured.v;

  // 정지 판정(0.5 s 이상 거의 멈춤)
  if (std::abs(v) < p_.stationary_speed && std::abs(output_.last().v) < p_.stationary_speed) {
    if (stopped_since_ < 0.0) {stopped_since_ = in.now;}
  } else {
    stopped_since_ = -1.0;
  }
  const bool stationary = stopped_since_ >= 0.0 && in.now - stopped_since_ >= p_.stationary_time;

  // 차선
  lanes_.update(in.path, v, in.now, in.dt, in.clearance);
  const Path lane_path = lanes_.lanePath(in.path, v);
  const double L = lookaheadDistance(v, p_.lookahead);
  const Point2D carrot = carrotOnPath(lane_path, L);
  const double heading = std::atan2(carrot.y, carrot.x);
  const double path_heading = carrotTangent(lane_path, L);
  const double dist_end = std::hypot(in.goal.x, in.goal.y);
  const double yaw_err = normalizeAngle(in.goal.yaw);

  // 정지거리 안 몸통 접촉 — 주행 중에만(회전은 유턴 계획이 매 주기 다시 검사)
  bool imminent = false;
  if (sm_.state() == State::Track && v > p_.stationary_speed) {
    const double s_stop = v * v / (2.0 * p_.output.max_decel) + v * p_.stop_latency + p_.stop_margin;
    for (const auto & ps : pathPrefix(lane_path, s_stop)) {
      if (in.clearance(ps) < 0.0) {imminent = true; break;}
    }
  }

  StateInputs si;
  si.now = in.now;
  si.stationary = stationary;
  si.heading_error = heading;
  si.path_heading_error = path_heading;
  si.dist_to_end = dist_end;
  si.yaw_error_end = yaw_err;
  si.xy_tol = in.xy_tol;
  si.yaw_tol = in.yaw_tol;
  si.lanes_blocked = lanes_.blocked();
  si.collision_imminent = imminent;
  si.align_failed = align_.phase() == AlignPhase::Failed;

  // 유턴 계획은 필요할 때만(계산량 고정)
  const State s0 = sm_.state();
  const bool need = turnNeeded(si, p_.state);
  if (s0 == State::Turn || (need && (s0 == State::Track || s0 == State::Hold))) {
    const bool pivot_first = s0 == State::Turn ? turn_.mode == TurnMode::Pivot :
      (stationary && std::abs(heading) <= p_.state.turn_enter_angle);
    turn_ = planTurn(heading, v, pivot_first, in.clearance, p_.turn);
    si.turn_blocked = turn_.mode == TurnMode::Blocked;
  }

  const State s = sm_.update(si);
  if (s == State::Align && s0 != State::Align) {align_.reset();}

  Desired d;
  switch (s) {
    case State::Track: {
        SpeedParams sp = p_.speed;
        sp.desired = std::min(p_.speed.desired, in.speed_cap);
        double vdes = sp.desired;
        vdes = std::min(vdes, curvePreviewLimit(lane_path, sp));
        vdes = std::min(vdes, clearanceLimit(lanes_.currentClearance(), sp));
        vdes = std::min(vdes, lanes_.speedCap());   // 차선을 옮기는 동안의 속도
        vdes = approachLimit(dist_end, vdes, sp);
        if (dist_end < in.xy_tol) {vdes = 0.0;}   // 도착 반경 안에서는 멈춘다(RPP 도 같은 자리에서 회전으로 넘어간다)
        d.cmd = {vdes, 0.0};
        d.curvature = curvatureTo(carrot);
        break;
      }
    case State::Turn:
      d.cmd = turnCommand(turn_, p_.turn);
      if (turn_.mode == TurnMode::Arc) {d.radius = turn_.radius;}
      break;
    case State::Align:
      d.cmd = {0.0, align_.update(yaw_err, in.measured.w, in.yaw_tol, in.now, in.dt)};
      break;
    case State::Hold:
      d.cmd = {0.0, 0.0};
      break;
  }

  out.cmd = output_.apply(d, v, in.dt);
  out.state = s;
  out.offset = lanes_.offset();
  out.target = lanes_.target();
  out.lanes_blocked = lanes_.blocked();
  out.turn_mode = turn_.mode;
  out.align_attempts = align_.attempts();
  out.reason = sm_.reason();
  out.lane_path = lane_path;

  if (imminent) {
    out.failure = Failure::CollisionAhead;
    out.cmd = {0.0, 0.0};
    output_.reset();
  } else if (align_.phase() == AlignPhase::Failed) {
    out.failure = Failure::AlignFailed;
  } else if (s == State::Hold && std::abs(v) < p_.stationary_speed) {
    out.failure = Failure::Blocked;
  }
  return out;
}
}  // namespace vica_vcc_controller::core
```

`CMakeLists.txt`: 소스와 `test_vcc_core` 를 추가한다.

- [ ] **Step 4: 통과 확인**

Expected: 9개 PASS.
- `ParallelOffsetRejoinsWithoutStopping` 이 실패하면 먼저 `path_heading` 을 출력해 본다.
- 조준점이 경로 끝을 넘어 `carrotTangent` 가 이상한 구간을 가리키는지 확인한다.

- [ ] **Step 5: 커밋** — `git commit -m "feat(vcc): 한 주기 조립 — 거리·차선·상황·출력단을 잇고 실패 3종을 구분"`

---

### Task 12: Nav2 플러그인 어댑터 (`VccController`)

**Files:**
- Create: `include/vica_vcc_controller/vcc_controller.hpp`, `src/vcc_controller.cpp`, `vcc_plugins.xml`
- Test: `test/test_vcc_plugin.cpp`
- Modify: `CMakeLists.txt` (ROS 의존, `.so`, pluginlib export, 시험)

**Interfaces:**
- Consumes: `VccCore`, `CoreParams`, `ClearanceField`, `UltrasonicChannel`, `rangeToArcPoints`
- Produces:
  - plugin 클래스 `vica_vcc_controller::VccController : public nav2_core::Controller`
  - 발행 토픽 `vcc/state`(std_msgs/String), `vcc/lane_plan`(nav_msgs/Path)
  - 파라미터 `FollowPath.*` (Task 13 yaml 이 쓴다)
    - 목록: `desired_linear_vel, lookahead_time, min_lookahead_dist, max_lookahead_dist, transform_tolerance, max_angular_vel, max_angular_accel, max_linear_decel, start_ramp_speed, start_ramp_accel, linear_accel, min_speed, curve_min_radius, curve_decel, preview_dist, slow_clearance, approach_velocity_scaling_dist, min_approach_linear_velocity, lane_max_offset, lane_step, lane_shift_speeds, avoid_horizon, target_clearance, w_clear, w_rail, w_change, switch_margin, switch_persist_cycles, lane_rate, return_clear_time, turn_enter_angle, turn_exit_angle, pivot_start_angle, turn_radii, turn_clearance, turn_angular_vel, pivot_angular_vel, align_angular_vel, motor_lag, align_settle, align_max_attempts, min_state_time, clearance_window, reset_gap, ultrasonic_topics, us_max_age, us_confirm_count, us_confirm_tol, us_arc_points, publish_state`

스레드(설계서 16 "구독 스레드" 확정):

- Humble `controller_server` 는 action 실행을 별도 스레드에서 돌린다(`simple_action_server.hpp:203`, "spin up a new thread").
- 구독 콜백은 노드의 기본 executor 에서 돈다.
- 그래서 초음파 버퍼는 `std::mutex` 로 보호한다. `setPlan` 과 `computeVelocityCommands` 는 같은 실행 스레드에서 불린다.

- [ ] **Step 1: 실패하는 시험** — `test/test_vcc_plugin.cpp`

```cpp
#include <gtest/gtest.h>
#include <memory>
#include "geometry_msgs/msg/transform_stamped.hpp"
#include "nav2_costmap_2d/costmap_2d_ros.hpp"
#include "nav2_core/exceptions.hpp"
#include "rclcpp/rclcpp.hpp"
#include "rclcpp_lifecycle/lifecycle_node.hpp"
#include "tf2_ros/buffer.h"
#include "vica_vcc_controller/vcc_controller.hpp"

class VccPluginTest : public ::testing::Test
{
protected:
  static void SetUpTestSuite() {rclcpp::init(0, nullptr);}
  static void TearDownTestSuite() {rclcpp::shutdown();}
};

TEST_F(VccPluginTest, ConfigureDeclaresParametersAndLifecycleWorks)
{
  auto node = std::make_shared<rclcpp_lifecycle::LifecycleNode>("vcc_test_node");
  auto tf = std::make_shared<tf2_ros::Buffer>(node->get_clock());
  auto costmap = std::make_shared<nav2_costmap_2d::Costmap2DROS>("vcc_test_costmap");
  costmap->on_configure(rclcpp_lifecycle::State());

  auto ctrl = std::make_shared<vica_vcc_controller::VccController>();
  ctrl->configure(node, "FollowPath", tf, costmap);
  ctrl->activate();

  double lane_rate = 0.0;
  ASSERT_TRUE(node->get_parameter("FollowPath.lane_rate", lane_rate));
  EXPECT_NEAR(lane_rate, 0.10, 1e-9);
  std::vector<double> radii;
  ASSERT_TRUE(node->get_parameter("FollowPath.turn_radii", radii));
  EXPECT_EQ(radii.size(), 2u);

  ctrl->setSpeedLimit(50.0, true);
  ctrl->setSpeedLimit(nav2_costmap_2d::NO_SPEED_LIMIT, false);
  ctrl->deactivate();
  ctrl->cleanup();
}

TEST_F(VccPluginTest, EmptyPlanThrowsPlannerException)
{
  auto node = std::make_shared<rclcpp_lifecycle::LifecycleNode>("vcc_test_node2");
  auto tf = std::make_shared<tf2_ros::Buffer>(node->get_clock());
  auto costmap = std::make_shared<nav2_costmap_2d::Costmap2DROS>("vcc_test_costmap2");
  costmap->on_configure(rclcpp_lifecycle::State());
  auto ctrl = std::make_shared<vica_vcc_controller::VccController>();
  ctrl->configure(node, "FollowPath", tf, costmap);
  ctrl->activate();

  ctrl->setPlan(nav_msgs::msg::Path());
  geometry_msgs::msg::PoseStamped pose;
  pose.header.frame_id = "map";
  EXPECT_THROW(
    ctrl->computeVelocityCommands(pose, geometry_msgs::msg::Twist(), nullptr),
    nav2_core::PlannerException);
}

TEST_F(VccPluginTest, StraightPlanProducesForwardCommand)
{
  auto node = std::make_shared<rclcpp_lifecycle::LifecycleNode>("vcc_test_node3");
  auto tf = std::make_shared<tf2_ros::Buffer>(node->get_clock());
  auto costmap = std::make_shared<nav2_costmap_2d::Costmap2DROS>("vcc_test_costmap3");
  costmap->on_configure(rclcpp_lifecycle::State());

  // map -> base_link : (2.5, 2.5) 에 놓는다(기본 costmap 원점 0,0)
  geometry_msgs::msg::TransformStamped t;
  t.header.frame_id = "map";
  t.child_frame_id = "base_link";
  t.transform.translation.x = 2.5;
  t.transform.translation.y = 2.5;
  t.transform.rotation.w = 1.0;
  tf->setTransform(t, "test", true);

  auto ctrl = std::make_shared<vica_vcc_controller::VccController>();
  ctrl->configure(node, "FollowPath", tf, costmap);
  ctrl->activate();

  nav_msgs::msg::Path plan;
  plan.header.frame_id = "map";
  for (int i = 0; i <= 40; ++i) {
    geometry_msgs::msg::PoseStamped ps;
    ps.header.frame_id = "map";
    ps.pose.position.x = 2.5 + 0.05 * i;
    ps.pose.position.y = 2.5;
    ps.pose.orientation.w = 1.0;
    plan.poses.push_back(ps);
  }
  ctrl->setPlan(plan);
  geometry_msgs::msg::PoseStamped pose;
  pose.header.frame_id = "map";
  pose.pose.position.x = 2.5;
  pose.pose.position.y = 2.5;
  pose.pose.orientation.w = 1.0;
  const auto cmd = ctrl->computeVelocityCommands(pose, geometry_msgs::msg::Twist(), nullptr);
  EXPECT_GT(cmd.twist.linear.x, 0.0);
  EXPECT_LE(cmd.twist.linear.x, 0.25);
  EXPECT_NEAR(cmd.twist.angular.z, 0.0, 1e-3);
}
```

- [ ] **Step 2: 실패 확인** — Expected: FAIL(헤더 없음)

- [ ] **Step 3: 구현**

`vcc_plugins.xml`:

```xml
<library path="vica_vcc_controller">
  <class type="vica_vcc_controller::VccController" base_class_type="nav2_core::Controller">
    <description>VCC — 레일 추종 + 차선 고르기 + 상황 4개 (VICA 자작)</description>
  </class>
</library>
```

`include/vica_vcc_controller/vcc_controller.hpp`:

```cpp
#pragma once
#include <memory>
#include <mutex>
#include <string>
#include <vector>

#include "geometry_msgs/msg/pose_stamped.hpp"
#include "geometry_msgs/msg/twist.hpp"
#include "geometry_msgs/msg/twist_stamped.hpp"
#include "nav2_core/controller.hpp"
#include "nav2_costmap_2d/costmap_2d_ros.hpp"
#include "nav_msgs/msg/path.hpp"
#include "rclcpp/rclcpp.hpp"
#include "rclcpp_lifecycle/lifecycle_node.hpp"
#include "rclcpp_lifecycle/lifecycle_publisher.hpp"
#include "sensor_msgs/msg/range.hpp"
#include "std_msgs/msg/string.hpp"
#include "tf2_ros/buffer.h"
#include "vica_vcc_controller/core/ultrasonic.hpp"
#include "vica_vcc_controller/core/vcc_core.hpp"

namespace vica_vcc_controller
{
class VccController : public nav2_core::Controller
{
public:
  VccController() = default;
  ~VccController() override = default;

  void configure(
    const rclcpp_lifecycle::LifecycleNode::WeakPtr & parent, std::string name,
    std::shared_ptr<tf2_ros::Buffer> tf,
    std::shared_ptr<nav2_costmap_2d::Costmap2DROS> costmap_ros) override;
  void cleanup() override;
  void activate() override;
  void deactivate() override;
  void setPlan(const nav_msgs::msg::Path & path) override;
  geometry_msgs::msg::TwistStamped computeVelocityCommands(
    const geometry_msgs::msg::PoseStamped & pose, const geometry_msgs::msg::Twist & velocity,
    nav2_core::GoalChecker * goal_checker) override;
  void setSpeedLimit(const double & speed_limit, const bool & percentage) override;

private:
  nav_msgs::msg::Path transformGlobalPlan(const geometry_msgs::msg::PoseStamped & pose);
  bool transformPose(
    const std::string & frame, const geometry_msgs::msg::PoseStamped & in,
    geometry_msgs::msg::PoseStamped & out) const;
  void fillClearance(const geometry_msgs::msg::PoseStamped & pose);
  void fillUltrasonic(double now);
  double steadyNow() const;

  rclcpp_lifecycle::LifecycleNode::WeakPtr node_;
  std::string name_;
  std::shared_ptr<tf2_ros::Buffer> tf_;
  std::shared_ptr<nav2_costmap_2d::Costmap2DROS> costmap_ros_;
  nav2_costmap_2d::Costmap2D * costmap_{nullptr};
  rclcpp::Logger logger_{rclcpp::get_logger("VccController")};
  rclcpp::Clock::SharedPtr clock_;
  rclcpp::Clock steady_{RCL_STEADY_TIME};

  core::CoreParams params_;
  core::VccCore core_;
  core::ClearanceField field_;
  nav_msgs::msg::Path global_plan_;
  double transform_tolerance_{0.2};
  double base_speed_{0.5};
  double speed_cap_{0.5};
  double clearance_window_{5.0};
  double reset_gap_{0.5};
  double last_compute_{-1.0};
  double last_goal_x_{1e9}, last_goal_y_{1e9};
  bool publish_state_{true};

  // 초음파(구독 콜백 스레드와 제어 스레드가 공유)
  std::mutex us_mutex_;
  std::vector<core::UltrasonicChannel> us_channels_;
  std::vector<std::string> us_frames_;
  std::vector<rclcpp::Subscription<sensor_msgs::msg::Range>::SharedPtr> us_subs_;
  double us_max_age_{1.0};
  int us_confirm_count_{2};
  double us_confirm_tol_{0.15};
  int us_arc_points_{7};

  std::shared_ptr<rclcpp_lifecycle::LifecyclePublisher<std_msgs::msg::String>> state_pub_;
  std::shared_ptr<rclcpp_lifecycle::LifecyclePublisher<nav_msgs::msg::Path>> lane_pub_;
};
}  // namespace vica_vcc_controller
```

`src/vcc_controller.cpp`:

```cpp
// Copyright (c) 2020 Shrijit Singh
// Copyright (c) 2020 Samsung Research America
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.
//
// VICA 수정(2026-09-24): transformGlobalPlan·transformPose·setSpeedLimit 은
// nav2_regulated_pure_pursuit_controller 1.1.20 에서 가져왔다. 나머지는 VICA 작성(VCC).

#include "vica_vcc_controller/vcc_controller.hpp"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <string>
#include <vector>

#include "nav2_core/exceptions.hpp"
#include "nav2_costmap_2d/cost_values.hpp"
#include "nav2_util/geometry_utils.hpp"
#include "nav2_util/node_utils.hpp"
#include "pluginlib/class_list_macros.hpp"
#include "tf2/utils.h"
#include "tf2_geometry_msgs/tf2_geometry_msgs.hpp"

using nav2_util::declare_parameter_if_not_declared;
using nav2_util::geometry_utils::euclidean_distance;

namespace vica_vcc_controller
{
namespace
{
core::Pose2D toPose2D(const geometry_msgs::msg::Pose & p)
{
  return {p.position.x, p.position.y, tf2::getYaw(p.orientation)};
}
}  // namespace

double VccController::steadyNow() const
{
  return steady_.now().seconds();
}

void VccController::configure(
  const rclcpp_lifecycle::LifecycleNode::WeakPtr & parent, std::string name,
  std::shared_ptr<tf2_ros::Buffer> tf, std::shared_ptr<nav2_costmap_2d::Costmap2DROS> costmap_ros)
{
  node_ = parent;
  auto node = parent.lock();
  if (!node) {throw nav2_core::PlannerException("vcc: unable to lock node");}
  name_ = name;
  tf_ = tf;
  costmap_ros_ = costmap_ros;
  costmap_ = costmap_ros->getCostmap();
  logger_ = node->get_logger();
  clock_ = node->get_clock();

  auto dp = [&](const std::string & n, auto def) {
      declare_parameter_if_not_declared(node, name_ + "." + n, rclcpp::ParameterValue(def));
      decltype(def) v = def;
      node->get_parameter(name_ + "." + n, v);
      return v;
    };

  core::CoreParams p;
  p.speed.desired = base_speed_ = speed_cap_ = dp("desired_linear_vel", 0.5);
  p.output.max_v = p.speed.desired;
  p.lookahead.time = dp("lookahead_time", 2.5);
  p.lookahead.min_dist = dp("min_lookahead_dist", 0.6);
  p.lookahead.max_dist = dp("max_lookahead_dist", 1.2);
  transform_tolerance_ = dp("transform_tolerance", 0.2);
  p.output.max_w = dp("max_angular_vel", 0.5);
  p.output.max_ang_accel = dp("max_angular_accel", 1.2);
  p.output.max_decel = dp("max_linear_decel", 1.25);
  p.output.ramp_v1 = dp("start_ramp_speed", 0.25);
  p.output.ramp_a1 = dp("start_ramp_accel", 0.5);
  p.output.accel = dp("linear_accel", 0.143);
  p.speed.min_speed = dp("min_speed", 0.12);
  p.speed.curve_min_radius = dp("curve_min_radius", 1.2);
  p.speed.curve_decel = dp("curve_decel", 0.3);
  p.speed.preview_dist = dp("preview_dist", 1.5);
  p.speed.slow_clearance = dp("slow_clearance", 0.35);
  p.speed.approach_dist = dp("approach_velocity_scaling_dist", 0.6);
  p.speed.approach_min = dp("min_approach_linear_velocity", 0.05);
  p.lane.max_offset = dp("lane_max_offset", 0.6);
  p.lane.step = dp("lane_step", 0.1);
  p.lane.shift_speeds = dp("lane_shift_speeds", std::vector<double>{0.3, 0.2, 0.1});
  p.lane.horizon = dp("avoid_horizon", 1.5);
  p.lane.target_clearance = dp("target_clearance", 0.20);
  p.lane.w_clear = dp("w_clear", 10.0);
  p.lane.w_rail = dp("w_rail", 1.0);
  p.lane.w_change = dp("w_change", 0.5);
  p.lane.switch_margin = dp("switch_margin", 0.05);
  p.lane.persist_cycles = dp("switch_persist_cycles", 3);
  p.lane.lane_rate = dp("lane_rate", 0.10);
  p.lane.return_clear_time = dp("return_clear_time", 1.0);
  p.state.turn_enter_angle = dp("turn_enter_angle", 1.047);
  p.state.turn_exit_angle = dp("turn_exit_angle", 0.436);
  p.state.pivot_start_angle = dp("pivot_start_angle", 0.611);
  p.state.min_state_time = dp("min_state_time", 0.5);
  p.turn.radii = dp("turn_radii", std::vector<double>{0.2, 0.1});
  p.turn.clearance = dp("turn_clearance", 0.05);
  p.turn.arc_w = dp("turn_angular_vel", 0.45);
  p.turn.pivot_w = dp("pivot_angular_vel", 0.35);
  p.align.w_max = dp("align_angular_vel", 0.35);
  p.align.alpha = p.output.max_ang_accel;
  p.align.motor_lag = dp("motor_lag", 0.35);
  p.align.settle = dp("align_settle", 0.3);
  p.align.max_attempts = dp("align_max_attempts", 3);
  clearance_window_ = dp("clearance_window", 5.0);
  reset_gap_ = dp("reset_gap", 0.5);
  us_max_age_ = dp("us_max_age", 1.0);
  us_confirm_count_ = dp("us_confirm_count", 2);
  us_confirm_tol_ = dp("us_confirm_tol", 0.15);
  us_arc_points_ = dp("us_arc_points", 7);
  publish_state_ = dp("publish_state", true);
  const std::vector<std::string> topics = dp(
    "ultrasonic_topics", std::vector<std::string>{
      "/ultrasonic/front_left", "/ultrasonic/front_right",
      "/ultrasonic/left_wheel", "/ultrasonic/right_wheel"});

  // costmap 이 이미 padding 을 넣은 footprint 를 준다(Costmap2DROS::getRobotFootprint).
  for (const auto & pt : costmap_ros_->getRobotFootprint()) {p.footprint.push_back({pt.x, pt.y});}
  params_ = p;
  core_.configure(params_);
  field_.setFootprint(params_.footprint);

  us_channels_.assign(topics.size(), core::UltrasonicChannel());
  us_frames_.assign(topics.size(), "");
  us_subs_.clear();
  for (size_t i = 0; i < topics.size(); ++i) {
    us_subs_.push_back(node->create_subscription<sensor_msgs::msg::Range>(
        topics[i], rclcpp::SensorDataQoS(),
        [this, i](sensor_msgs::msg::Range::ConstSharedPtr m) {
          std::lock_guard<std::mutex> lock(us_mutex_);
          us_channels_[i].push({m->range, m->min_range, m->max_range, m->field_of_view, steadyNow()});
          us_frames_[i] = m->header.frame_id;
        }));
  }

  state_pub_ = node->create_publisher<std_msgs::msg::String>("vcc/state", 10);
  lane_pub_ = node->create_publisher<nav_msgs::msg::Path>("vcc/lane_plan", 1);
  RCLCPP_INFO(logger_, "VCC configured: %zu ultrasonic topics, footprint %zu points",
    topics.size(), params_.footprint.size());
}

void VccController::cleanup()
{
  state_pub_.reset();
  lane_pub_.reset();
  us_subs_.clear();
  core_.reset();
}

void VccController::activate()
{
  state_pub_->on_activate();
  lane_pub_->on_activate();
  core_.reset();
  last_compute_ = -1.0;
}

void VccController::deactivate()
{
  state_pub_->on_deactivate();
  lane_pub_->on_deactivate();
  core_.reset();
}

void VccController::setPlan(const nav_msgs::msg::Path & path)
{
  global_plan_ = path;
  if (path.poses.empty()) {return;}
  // 새 goal: 경로 끝점이 0.5 m 넘게 옮겨지면 상황·차선·도착 횟수를 초기화한다(설계서 6.2 ⑤).
  const auto & e = path.poses.back().pose.position;
  if (std::hypot(e.x - last_goal_x_, e.y - last_goal_y_) > 0.5) {core_.reset();}
  last_goal_x_ = e.x;
  last_goal_y_ = e.y;
}

void VccController::setSpeedLimit(const double & speed_limit, const bool & percentage)
{
  if (speed_limit == nav2_costmap_2d::NO_SPEED_LIMIT) {
    speed_cap_ = base_speed_;
  } else if (percentage) {
    speed_cap_ = base_speed_ * speed_limit / 100.0;
  } else {
    speed_cap_ = speed_limit;
  }
}

bool VccController::transformPose(
  const std::string & frame, const geometry_msgs::msg::PoseStamped & in,
  geometry_msgs::msg::PoseStamped & out) const
{
  if (in.header.frame_id == frame) {out = in; return true;}
  try {
    tf_->transform(in, out, frame, tf2::durationFromSec(transform_tolerance_));
    out.header.frame_id = frame;
    return true;
  } catch (tf2::TransformException & ex) {
    RCLCPP_ERROR(logger_, "Exception in transformPose: %s", ex.what());
  }
  return false;
}

// RPP 1.1.20 transformGlobalPlan (global_path_pub_ 발행만 뺐다)
nav_msgs::msg::Path VccController::transformGlobalPlan(const geometry_msgs::msg::PoseStamped & pose)
{
  if (global_plan_.poses.empty()) {
    throw nav2_core::PlannerException("Received plan with zero length");
  }
  geometry_msgs::msg::PoseStamped robot_pose;
  if (!transformPose(global_plan_.header.frame_id, pose, robot_pose)) {
    throw nav2_core::PlannerException("Unable to transform robot pose into global plan's frame");
  }
  const double max_costmap_extent =
    std::max(costmap_->getSizeInMetersX(), costmap_->getSizeInMetersY()) / 2.0;

  auto closest_pose_upper_bound = nav2_util::geometry_utils::first_after_integrated_distance(
    global_plan_.poses.begin(), global_plan_.poses.end(), max_costmap_extent);
  auto transformation_begin = nav2_util::geometry_utils::min_by(
    global_plan_.poses.begin(), closest_pose_upper_bound,
    [&robot_pose](const geometry_msgs::msg::PoseStamped & ps) {
      return euclidean_distance(robot_pose, ps);
    });
  auto transformation_end = std::find_if(
    transformation_begin, global_plan_.poses.end(),
    [&](const auto & p) {return euclidean_distance(p, robot_pose) > max_costmap_extent;});

  nav_msgs::msg::Path transformed;
  for (auto it = transformation_begin; it != transformation_end; ++it) {
    geometry_msgs::msg::PoseStamped stamped, out;
    stamped.header.frame_id = global_plan_.header.frame_id;
    stamped.header.stamp = robot_pose.header.stamp;
    stamped.pose = it->pose;
    transformPose(costmap_ros_->getBaseFrameID(), stamped, out);
    out.pose.position.z = 0.0;
    transformed.poses.push_back(out);
  }
  transformed.header.frame_id = costmap_ros_->getBaseFrameID();
  transformed.header.stamp = robot_pose.header.stamp;
  global_plan_.poses.erase(begin(global_plan_.poses), transformation_begin);
  if (transformed.poses.empty()) {
    throw nav2_core::PlannerException("Resulting plan has 0 poses in it.");
  }
  return transformed;
}

void VccController::fillClearance(const geometry_msgs::msg::PoseStamped & pose)
{
  std::unique_lock<nav2_costmap_2d::Costmap2D::mutex_t> lock(*(costmap_->getMutex()));
  const double res = costmap_->getResolution();
  const int n = static_cast<int>(std::round(clearance_window_ / res));
  const double rx = pose.pose.position.x, ry = pose.pose.position.y;
  int mx0, my0;
  costmap_->worldToMapEnforceBounds(rx - clearance_window_ / 2.0, ry - clearance_window_ / 2.0, mx0, my0);
  double ox, oy;
  costmap_->mapToWorld(mx0, my0, ox, oy);   // 셀 중심
  auto & g = field_.grid();
  g.reset(ox - res / 2.0, oy - res / 2.0, res, n, n);
  const unsigned int sx = costmap_->getSizeInCellsX(), sy = costmap_->getSizeInCellsY();
  for (int iy = 0; iy < n; ++iy) {
    for (int ix = 0; ix < n; ++ix) {
      const unsigned int mx = mx0 + ix, my = my0 + iy;
      if (mx >= sx || my >= sy) {continue;}
      // LETHAL 만 본다. NO_INFORMATION 은 RPP 1.1.20 처럼 충돌로 보지 않는다.
      if (costmap_->getCost(mx, my) == nav2_costmap_2d::LETHAL_OBSTACLE) {g.markLethal(ix, iy);}
    }
  }
  g.compute();
}

void VccController::fillUltrasonic(double now)
{
  std::vector<core::Point2D> pts;
  const std::string global = costmap_ros_->getGlobalFrameID();
  std::lock_guard<std::mutex> lock(us_mutex_);
  for (size_t i = 0; i < us_channels_.size(); ++i) {
    const auto r = us_channels_[i].confirmed(now, us_max_age_, us_confirm_count_, us_confirm_tol_);
    if (!r || us_frames_[i].empty()) {continue;}
    geometry_msgs::msg::TransformStamped t;
    try {
      // 최신 TF 를 쓴다(stamp 기준 조회는 run44 에서 660회 무시를 낳았다).
      t = tf_->lookupTransform(global, us_frames_[i], tf2::TimePointZero);
    } catch (tf2::TransformException &) {
      continue;
    }
    const core::Pose2D sensor{t.transform.translation.x, t.transform.translation.y,
      tf2::getYaw(t.transform.rotation)};
    for (const auto & q : core::rangeToArcPoints(r->range, r->fov, us_arc_points_)) {
      pts.push_back(core::toParent(sensor, q));
    }
  }
  field_.setPoints(std::move(pts));
}

geometry_msgs::msg::TwistStamped VccController::computeVelocityCommands(
  const geometry_msgs::msg::PoseStamped & pose, const geometry_msgs::msg::Twist & velocity,
  nav2_core::GoalChecker * goal_checker)
{
  const double now = steadyNow();
  // 호출이 reset_gap 넘게 끊겼다 = 새 FollowPath 실행(BT 재시도 포함). 상황을 처음부터(Review Focus 3).
  const double dt = last_compute_ < 0.0 ? 0.1 : std::clamp(now - last_compute_, 0.02, 0.2);
  if (last_compute_ >= 0.0 && now - last_compute_ > reset_gap_) {core_.reset();}
  last_compute_ = now;

  double xy_tol = 0.25, yaw_tol = 0.25;
  if (goal_checker) {
    geometry_msgs::msg::Pose pt;
    geometry_msgs::msg::Twist vt;
    if (goal_checker->getTolerances(pt, vt)) {
      xy_tol = pt.position.x;
      yaw_tol = tf2::getYaw(pt.orientation);
    }
  }

  const nav_msgs::msg::Path transformed = transformGlobalPlan(pose);
  geometry_msgs::msg::PoseStamped goal_global = global_plan_.poses.back(), goal_robot;
  goal_global.header.frame_id = global_plan_.header.frame_id;
  goal_global.header.stamp = pose.header.stamp;
  if (!transformPose(costmap_ros_->getBaseFrameID(), goal_global, goal_robot)) {
    throw nav2_core::PlannerException("vcc: unable to transform goal");
  }

  fillClearance(pose);
  fillUltrasonic(now);

  core::CoreInputs in;
  in.now = now;
  in.dt = dt;
  for (const auto & ps : transformed.poses) {in.path.push_back(toPose2D(ps.pose));}
  in.goal = toPose2D(goal_robot.pose);
  in.measured = {velocity.linear.x, velocity.angular.z};
  in.xy_tol = xy_tol;
  in.yaw_tol = yaw_tol;
  in.speed_cap = speed_cap_;
  const core::Pose2D robot = toPose2D(pose.pose);   // costmap 전역 좌표계
  in.clearance = [this, robot](const core::Pose2D & p) {
      return field_.clearance(core::toParent(robot, p));
    };

  const core::CoreOutput out = core_.step(in);

  if (publish_state_ && state_pub_->is_activated()) {
    std_msgs::msg::String s;
    char buf[256];
    std::snprintf(buf, sizeof(buf),
      "state=%s reason=%s offset=%.2f target=%.2f blocked=%d turn=%d align=%d fail=%d v=%.3f w=%.3f",
      core::stateName(out.state), out.reason, out.offset, out.target, out.lanes_blocked ? 1 : 0,
      static_cast<int>(out.turn_mode), out.align_attempts, static_cast<int>(out.failure),
      out.cmd.v, out.cmd.w);
    s.data = buf;
    state_pub_->publish(s);
    nav_msgs::msg::Path lp;
    lp.header = transformed.header;
    for (const auto & q : out.lane_path) {
      geometry_msgs::msg::PoseStamped ps;
      ps.header = transformed.header;
      ps.pose.position.x = q.x;
      ps.pose.position.y = q.y;
      ps.pose.orientation.z = std::sin(q.yaw / 2.0);
      ps.pose.orientation.w = std::cos(q.yaw / 2.0);
      lp.poses.push_back(ps);
    }
    lane_pub_->publish(lp);
  }

  switch (out.failure) {
    case core::Failure::CollisionAhead:
      throw nav2_core::PlannerException("vcc: collision ahead");
    case core::Failure::Blocked:
      throw nav2_core::PlannerException("vcc: blocked");
    case core::Failure::AlignFailed:
      throw nav2_core::PlannerException("vcc: align failed");
    case core::Failure::None:
      break;
  }

  geometry_msgs::msg::TwistStamped cmd;
  cmd.header.frame_id = pose.header.frame_id;
  cmd.header.stamp = clock_->now();
  cmd.twist.linear.x = out.cmd.v;
  cmd.twist.angular.z = out.cmd.w;
  return cmd;
}
}  // namespace vica_vcc_controller

PLUGINLIB_EXPORT_CLASS(vica_vcc_controller::VccController, nav2_core::Controller)
```

`CMakeLists.txt` 전체 교체본(Task 1~12 누적):

```cmake
cmake_minimum_required(VERSION 3.8)
project(vica_vcc_controller)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(rclcpp_lifecycle REQUIRED)
find_package(pluginlib REQUIRED)
find_package(nav2_core REQUIRED)
find_package(nav2_costmap_2d REQUIRED)
find_package(nav2_util REQUIRED)
find_package(nav_msgs REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(std_msgs REQUIRED)
find_package(tf2 REQUIRED)
find_package(tf2_ros REQUIRED)
find_package(tf2_geometry_msgs REQUIRED)

# 순수 계산은 ROS 에 의존하지 않는다 — 시험이 노드·TF 없이 돈다(vica_nav2_bt_plugins 와 같은 모양).
add_library(vcc_core STATIC
  src/core/geometry.cpp
  src/core/clearance.cpp
  src/core/pure_pursuit.cpp
  src/core/speed_profile.cpp
  src/core/output_stage.cpp
  src/core/ultrasonic.cpp
  src/core/lanes.cpp
  src/core/turn_planner.cpp
  src/core/align_planner.cpp
  src/core/state_machine.cpp
  src/core/vcc_core.cpp
)
target_include_directories(vcc_core PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>)
target_compile_features(vcc_core PUBLIC cxx_std_17)
set_target_properties(vcc_core PROPERTIES POSITION_INDEPENDENT_CODE ON)

# controller_server 가 pluginlib 로 여는 .so. 이름이 vcc_plugins.xml 의 library path 다.
add_library(vica_vcc_controller SHARED src/vcc_controller.cpp)
target_link_libraries(vica_vcc_controller vcc_core)
ament_target_dependencies(vica_vcc_controller
  rclcpp rclcpp_lifecycle pluginlib nav2_core nav2_costmap_2d nav2_util nav_msgs
  geometry_msgs sensor_msgs std_msgs tf2 tf2_ros tf2_geometry_msgs)
target_compile_definitions(vica_vcc_controller PRIVATE PLUGINLIB__DISABLE_BOOST_FUNCTIONS)
pluginlib_export_plugin_description_file(nav2_core vcc_plugins.xml)

install(TARGETS vcc_core vica_vcc_controller
  ARCHIVE DESTINATION lib LIBRARY DESTINATION lib RUNTIME DESTINATION bin)
install(DIRECTORY include/ DESTINATION include)
install(FILES vcc_plugins.xml DESTINATION share/${PROJECT_NAME})

if(BUILD_TESTING)
  find_package(ament_cmake_gtest REQUIRED)
  foreach(t geometry clearance pure_pursuit speed_profile output_stage ultrasonic
      lanes turn_planner align_planner state_machine vcc_core)
    ament_add_gtest(test_${t} test/test_${t}.cpp)
    target_link_libraries(test_${t} vcc_core)
  endforeach()
  ament_add_gtest(test_vcc_plugin test/test_vcc_plugin.cpp)
  target_link_libraries(test_vcc_plugin vica_vcc_controller)
  ament_target_dependencies(test_vcc_plugin rclcpp rclcpp_lifecycle nav2_costmap_2d nav2_core tf2_ros)

  add_executable(bench_vcc_core test/bench_vcc_core.cpp)
  target_link_libraries(bench_vcc_core vcc_core)
  install(TARGETS bench_vcc_core RUNTIME DESTINATION lib/${PROJECT_NAME})
endif()

ament_export_include_directories(include)
ament_export_libraries(vica_vcc_controller)
ament_export_dependencies(rclcpp rclcpp_lifecycle nav2_core nav2_costmap_2d nav2_util pluginlib)
ament_package()
```

(`bench_vcc_core.cpp` 는 Task 14 에서 만든다. 이 Task 에서는 `add_executable(bench_vcc_core ...)` 세 줄을 주석으로 두고, Task 14 에서 푼다.)

- [ ] **Step 4: 빌드·시험**

Run: `colcon build --packages-select vica_vcc_controller && colcon test --packages-select vica_vcc_controller; colcon test-result --verbose --test-result-base build/vica_vcc_controller`
Expected: 모든 core 시험 + `test_vcc_plugin` 3개 PASS

플러그인 등록 확인:

```bash
ls install/vica_vcc_controller/share/ament_index/resource_index/nav2_core__pluginlib__plugin/
grep -c VccController install/vica_vcc_controller/share/vica_vcc_controller/vcc_plugins.xml
```
Expected: `vica_vcc_controller` 파일이 있고, grep 결과는 `1` 이다.

- `test_vcc_plugin` 의 costmap 생성이 Humble 에서 다르게 동작해 실패할 수 있다(예: on_configure 인자).
- 그 경우 `/opt/ros/humble/include/nav2_costmap_2d/costmap_2d_ros.hpp` 의 생성자와 on_configure 시그니처를 읽고 맞춘다.
- 어떻게 맞췄는지는 커밋 메시지에 적는다.

- [ ] **Step 5: 커밋** — `git commit -m "feat(vcc): nav2_core::Controller 어댑터 — LETHAL 거리장·초음파 직접 구독·PlannerException 3종·/vcc/state"`

---

### Task 13: 설정 전환 + 초음파 층 끄기 + 계약 시험

**Files:**
- Modify: `vica_ros2_ws/src/vica_nav2/config/nav2_params.yaml:383-463` (FollowPath 블록), `:1521-1553` (range 층 4개)
- Modify: `vica_ros2_ws/src/vica_nav2/package.xml` (exec_depend)
- Modify: `vica_ros2_ws/src/vica_nav2/test/test_nav2_params_contract.py:18-81`
- Modify: `vica_ros2_ws/src/vica_nav2/test/test_planner_contract.py:170-205`

**Interfaces:**
- Consumes: Task 12 파라미터 이름 전체
- Produces: `FollowPath.plugin == "vica_vcc_controller::VccController"`, `FollowPathRPP` 블록(옛 RPP 그대로)

- [ ] **Step 1: 기존 시험 실패 목록을 기록한다(기존 표류와 구분)**

Run:
```bash
cd ~/VICA-smarthandle/vica_ros2_ws/src/vica_nav2 && source /opt/ros/humble/setup.bash
python3 -m pytest test -q -p no:cacheprovider 2>&1 | tail -20 > /tmp/claude-1000/vcc_nav2_before.txt; cat /tmp/claude-1000/vcc_nav2_before.txt
```
Expected: 결과를 파일로 남긴다. 메모리 기록상 nav2 시험 몇 개는 dev 에서도 실패한다(기존 표류). 이번 변경 뒤 **새로 생긴 실패만** 고친다.

- [ ] **Step 2: 계약 시험에 VCC 분기를 먼저 넣는다(실패 시험)**

`test_nav2_params_contract.py` 의 `_controller_limits` 에서 `if 'purepursuit' ...` **위에** 추가한다.

```python
    if 'vcc' in fp['plugin'].lower():
        # 2026-09-24 VCC 전환. VCC 는 자기 출력단에 한계를 갖는다(설계서 7절).
        # 직진 가속은 출발 램프의 앞 구간(start_ramp_accel)이 가장 세다.
        gc = controller['general_goal_checker']
        return {
            'plugin_family': 'vcc',
            'max_vel_x': fp['desired_linear_vel'],
            'min_vel_x': 0.0,   # 출력단이 v 를 [0, max] 로 자른다 — 후진 없음
            'max_vel_theta': fp['max_angular_vel'],
            'acc_lim_x': fp['start_ramp_accel'], 'decel_lim_x': -fp['max_linear_decel'],
            'acc_lim_theta': fp['max_angular_accel'], 'decel_lim_theta': -fp['max_angular_accel'],
            'xy_goal_tolerance': gc['xy_goal_tolerance'],
            'trans_stopped_velocity': gc['trans_stopped_velocity'],
        }
```

같은 파일 끝에 VCC 전용 계약을 추가한다.

```python
def test_vcc_limits_match_the_smoother():
    """VCC 출력단 한계가 velocity_smoother 와 어긋나면 한쪽이 다른 쪽 계획을 깎는다.

    회전 상한은 smoother 와 같고 좌우 대칭이어야 한다(손잡이 끝 0.62 m/s 문제, yaml 2567-2577).
    직선 제동은 smoother max_decel 과 같아야 한다 — 제동은 완화하지 않는다(yaml 2606-2612).
    """
    params = _load_params()
    fp = params['controller_server']['ros__parameters']['FollowPath']
    if 'vcc' not in fp['plugin'].lower():
        pytest.skip('VCC 가 활성 컨트롤러가 아니다')
    sm = params['velocity_smoother']['ros__parameters']
    assert fp['max_angular_vel'] <= sm['max_velocity'][2]
    assert sm['min_velocity'][2] == -sm['max_velocity'][2]
    assert fp['max_linear_decel'] == abs(sm['max_decel'][0])
    assert fp['desired_linear_vel'] <= sm['max_velocity'][0]
    # 차선 이동 속도는 손잡이 0.115 m/s 탈락선(backlog §11) 아래
    assert fp['lane_rate'] < 0.115


def test_rpp_is_preserved_for_one_line_rollback():
    params = _load_params()
    controller = params['controller_server']['ros__parameters']
    assert 'FollowPathRPP' in controller
    assert 'purepursuit' in controller['FollowPathRPP']['plugin'].lower().replace('_', '')
    assert controller['controller_plugins'] == ['FollowPath']
```

(`import pytest` 가 파일 머리에 없으면 추가한다.)

`test_planner_contract.py` 의 `test_planner_and_controller_use_the_same_collision_model` 에서 `if 'purepursuit' ...` **위에** 추가한다.

```python
    if 'vcc' in follow_path['plugin'].lower():
        # 2026-09-24 VCC. 몸 전체를 LETHAL 거리장과 매 주기 대조한다(끄는 설정이 없다).
        # 중심 셀 비용과 무관하므로 inflation 사각지대(NAV2-B3)도 없다.
        controller_sees_footprint = True
        assert planner_sees_footprint == controller_sees_footprint, (
            f'planner {active["plugin"]} 는 점 로봇으로 보는데 VCC 는 면으로 본다')
        return
```

Run: `python3 -m pytest test/test_nav2_params_contract.py -q -k "vcc or rpp_is_preserved"`
Expected: FAIL. `test_rpp_is_preserved_for_one_line_rollback` 이 `FollowPathRPP` 없음으로 실패하고, `test_vcc_limits_match_the_smoother` 는 SKIP 이다.

- [ ] **Step 3: yaml 수정**

(a) 지금 `FollowPath:` 블록(RPP, 401~463행)의 머리 줄 `    FollowPath:` 를 `    FollowPathRPP:` 로 바꾼다. 안의 값은 한 글자도 바꾸지 않는다. 그 바로 위에 주석 한 줄을 넣는다.

```yaml
    # [2026-09-24] VCC 전환으로 보존. 되돌리기: 이 이름을 FollowPath 로, 아래 VCC 블록을 FollowPathVCC 로.
```

(b) RPP 설명 주석 머리(지금 `FollowPath:` 위 약 383행의 `# ════` 줄) **바로 위**에 VCC 블록을 넣는다. RPP 설명 주석과 RPP 블록 사이에 끼우지 않는다.

```yaml
    # ══════════════════════════════════════════════════════════════════════
    # [2026-09-24] 자작 컨트롤러 VCC (vica_vcc_controller). 설계서:
    #   VICA-smarthandle docs/superpowers/specs/2026-09-24-vcc-controller-design.md
    # 평소 = RPP 식 레일 조준, 장애물 = 차선 13개 중 옮기기(0.10 m/s), 유턴 = R 0.2 -> 0.1 -> 제자리,
    # 도착 = 남은 각 한 번(모터 지연만큼 일찍 끊음, 최대 3회). 몸통 검사는 LETHAL 거리장 — inflation 과 무관.
    # 초음파는 이 플러그인이 /ultrasonic/* 를 직접 읽는다(1 s 안·연속 2회 일치). local costmap range 층은 끔.
    # [되돌리기] 이 블록 이름을 FollowPathVCC 로, FollowPathRPP 를 FollowPath 로. range 층 4개 enabled True.
    # ══════════════════════════════════════════════════════════════════════
    FollowPath:
      plugin: "vica_vcc_controller::VccController"
      desired_linear_vel: 0.5            # RPP 와 같은 물리 상한
      lookahead_time: 2.5                # RPP 값 — run36 직진 최고
      min_lookahead_dist: 0.6            # run39
      max_lookahead_dist: 1.2            # run36: 레일 노드 1 m 를 건너뛴다
      transform_tolerance: 0.2
      max_angular_vel: 0.5               # smoother max_velocity[2] 와 같음
      max_angular_accel: 1.2             # RPP 값
      max_linear_decel: 1.25             # smoother max_decel[0] — 제동 완화 금지
      start_ramp_speed: 0.25             # 요구 8: 절반까지 살짝(0.5 s)
      start_ramp_accel: 0.5
      linear_accel: 0.143                # 0.25 -> 0.5 를 1.75 s
      min_speed: 0.12                    # RPP regulated_linear_scaling_min_speed
      curve_min_radius: 1.2              # RPP regulated_linear_scaling_min_radius
      curve_decel: 0.3                   # 코너 미리 줄이기
      preview_dist: 1.5
      slow_clearance: 0.35               # RPP cost_scaling_dist 와 같은 값, 직접 잰 거리
      approach_velocity_scaling_dist: 0.6
      min_approach_linear_velocity: 0.05
      lane_max_offset: 0.6               # 요구 3
      lane_step: 0.1
      lane_shift_speeds: [0.3, 0.2, 0.1] # 차선 옮기는 동안 달릴 속도 후보 — 20 cm 가 나오는 가장 빠른 것
      avoid_horizon: 1.5                 # 요구 1: 먼 사람 무시
      target_clearance: 0.20             # 요구 4: 15~20 cm
      w_clear: 10.0                      # 가중치 근거: vica_vcc_controller test_lanes 시나리오
      w_rail: 1.0
      w_change: 0.5
      switch_margin: 0.05
      switch_persist_cycles: 3
      lane_rate: 0.10                    # 손잡이 0.115 m/s 탈락선 아래(backlog §11)
      return_clear_time: 1.0
      turn_enter_angle: 1.047            # 60도 (요구 2)
      turn_exit_angle: 0.436             # 25도
      pivot_start_angle: 0.611           # 35도 (정지 출발)
      turn_radii: [0.2, 0.1]             # DWB 최소 ≈ 0.2, 0630 통로 1.3 m
      turn_clearance: 0.05
      turn_angular_vel: 0.45             # DWB U턴 실측 0.42~0.47
      pivot_angular_vel: 0.35            # RPP rotate_to_heading_angular_vel
      align_angular_vel: 0.35
      motor_lag: 0.35                    # run41 지연 0.3~0.5 s [추정] — 매 정렬 실측으로 갱신
      align_settle: 0.3
      align_max_attempts: 3
      min_state_time: 0.5
      clearance_window: 5.0              # 1.5 m 앞 + 몸 0.62 m 를 덮는다(local costmap 6 m 안)
      reset_gap: 0.5
      ultrasonic_topics: ["/ultrasonic/front_left", "/ultrasonic/front_right",
                          "/ultrasonic/left_wheel", "/ultrasonic/right_wheel"]
      us_max_age: 1.0
      us_confirm_count: 2
      us_confirm_tol: 0.15
      us_arc_points: 7
      publish_state: true
```

(c) local costmap 의 `range_sensor_front_left`, `range_sensor_front_right`, `range_sensor_left_wheel`, `range_sensor_right_wheel` 네 블록에서 `enabled: True` 를 다음으로 바꾼다.

```yaml
        enabled: False   # 2026-09-24 VCC 가 초음파를 직접 읽는다(1 s 안 값만). 이 층의 지워지지 않는 표시가 run43 정지 9회의 원인
```
(뒤쪽 4개는 이미 False 이다. 건드리지 않는다.)

(d) `vica_nav2/package.xml` 의 `<exec_depend>vica_localization</exec_depend>` 다음 줄에 추가한다.

```xml
  <exec_depend>vica_vcc_controller</exec_depend>
```

- [ ] **Step 4: 계약 시험 통과 확인**

Run:
```bash
python3 -m pytest test -q -p no:cacheprovider 2>&1 | tail -20 > /tmp/claude-1000/vcc_nav2_after.txt
diff /tmp/claude-1000/vcc_nav2_before.txt /tmp/claude-1000/vcc_nav2_after.txt
```
Expected:
- 새로 추가한 시험 2개는 PASS 다.
- Step 1 목록에 없던 새 실패는 0 이다.
- 새 실패가 있으면 이유를 읽고 고친다. 기준을 느슨하게 하지 않는다.

- [ ] **Step 5: 커밋**

```bash
cd ~/VICA-smarthandle/vica_ros2_ws
git add src/vica_nav2/config/nav2_params.yaml src/vica_nav2/package.xml src/vica_nav2/test
git commit -m "feat(nav2): FollowPath 를 VCC 로, RPP 는 FollowPathRPP 로 보존·초음파 range 층 4개 끔·계약 시험 VCC 분기"
```

---

### Task 14: 젯슨 계산 시간·전체 빌드 확인·설계서 정정·요구 대조

**Files:**
- Create: `vica_ros2_ws/src/vica_vcc_controller/test/bench_vcc_core.cpp`
- Modify: `vica_ros2_ws/src/vica_vcc_controller/CMakeLists.txt` (bench 세 줄 주석 해제)
- Modify: `VICA-smarthandle/docs/superpowers/specs/2026-09-24-vcc-controller-design.md` (구현 중 바뀐 3곳)

- [ ] **Step 1: bench 작성** — `test/bench_vcc_core.cpp`

```cpp
// 젯슨에서 VCC 한 주기 계산 시간을 잰다. 로봇을 움직이지 않는다.
// 합격: p99 <= 19.1 ms (100 ms 주기의 19.1 % = 사용자 허용 DWB 수준, 설계서 9절)
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <vector>
#include "vica_vcc_controller/core/geometry.hpp"
#include "vica_vcc_controller/core/vcc_core.hpp"

using namespace vica_vcc_controller::core;

int main()
{
  const Polygon fp{{0.151, 0.225}, {0.151, -0.225}, {-0.459, -0.225},
    {-0.569, -0.035}, {-0.569, 0.035}, {-0.459, 0.225}};
  CoreParams p;
  p.footprint = padFootprint(fp, 0.05);
  VccCore core;
  core.configure(p);

  ClearanceField field;
  field.setFootprint(p.footprint);
  Path path;
  for (double x = 0.0; x <= 3.0; x += 0.05) {path.push_back({x, 0.0, 0.0});}

  std::vector<double> ms;
  double v = 0.4;
  for (int i = 0; i < 1000; ++i) {
    const auto t0 = std::chrono::steady_clock::now();
    // 매 주기 거리장을 새로 만든다(실제 플러그인과 같은 일)
    field.grid().reset(-2.5, -2.5, 0.05, 100, 100);
    for (int ix = 0; ix < 100; ++ix) {field.grid().markLethal(ix, 20); field.grid().markLethal(ix, 80);}
    for (int iy = 48; iy < 52; ++iy) {field.grid().markLethal(74 + (i % 5), iy);}   // 움직이는 기둥
    field.grid().compute();
    CoreInputs in;
    in.now = 0.1 * i; in.dt = 0.1; in.path = path; in.goal = {10, 0, 0};
    in.measured = {v, 0.0}; in.speed_cap = 0.5;
    in.clearance = [&field](const Pose2D & q) {return field.clearance(q);};
    const CoreOutput out = core.step(in);
    v = out.cmd.v;
    const auto t1 = std::chrono::steady_clock::now();
    ms.push_back(std::chrono::duration<double, std::milli>(t1 - t0).count());
  }
  std::sort(ms.begin(), ms.end());
  std::printf("VCC step ms: p50=%.2f p90=%.2f p99=%.2f max=%.2f\n",
    ms[500], ms[900], ms[990], ms.back());
  return ms[990] <= 19.1 ? 0 : 1;
}
```

`CMakeLists.txt` 에서 `bench_vcc_core` 세 줄의 주석을 푼다.

- [ ] **Step 2: 젯슨에서 bench 실행**

Run:
```bash
cd ~/VICA-smarthandle/vica_ros2_ws && source /opt/ros/humble/setup.bash
colcon build --packages-select vica_vcc_controller
./build/vica_vcc_controller/bench_vcc_core; echo exit=$?
```
Expected: `exit=0`, p99 ≤ 19.1 ms. 값을 커밋 메시지에 그대로 적는다.

- 넘으면 먼저 `avoid_horizon` 과 `lane_step` 을 줄이지 **말고** 사용자에게 수치를 보고한다.
- 계산량 예산은 사용자 지시 사항이다.

- [ ] **Step 3: 두 패키지 빌드와 전체 시험**

Run:
```bash
colcon build --packages-select vica_vcc_controller vica_nav2
colcon test --packages-select vica_vcc_controller; colcon test-result --verbose --test-result-base build/vica_vcc_controller
```
Expected: vica_vcc_controller 시험 전부 PASS.

- [ ] **Step 4: 설계서 정정**

구현 중 바뀐 3곳을 루트 저장소 설계서에 반영한다.

1. 5.2 들어가기: "조준점 각 |θ| > 60°" 를 다음으로 바꾼다. **"조준점 각과 조준점 구간의 레일 방향 각이 둘 다 60° 초과(정지 출발은 35°)"**. 근거: 레일과 나란히 0.55 m 떨어진 저속 주행에서 조준점 각만 보면 66° 로 유턴을 오판한다(요구 3 과 충돌).
2. 4.2 / 9절 거리장 창을 **3×3 m 에서 5×5 m(`clearance_window`)** 로 바꾼다. 근거: 앞 1.5 m + 몸 외접 0.625 m 를 덮으려면 반폭이 2.2 m 필요하다.
3. 11절 유턴 회전 속도를 **0.5 에서 `turn_angular_vel` 0.45 / `pivot_angular_vel` 0.35** 로 바꾼다. 근거: DWB U턴 실측 0.42~0.47(devlog 09-17 §5.4)과 RPP rotate_to_heading 0.35.
4. 11절 가중치 칸에 **w_clear 10 / w_rail 1 / w_change 0.5 / margin 0.05, 근거 = test_lanes 시나리오 9개** 를 적는다.
5. 5.1 ⑥ "S자" 를 다음으로 바꾼다. **"옆 이동 속도 일정(≤ lane_rate 0.10 m/s), 차선을 옮기는 동안은 20 cm 가 나오는 가장 빠른 속도(0.3/0.2/0.1)로 달림"**. 근거: smoothstep 은 가운데 옆 속도가 평균의 1.5배라 손잡이 상한을 넘는다. 0.4 m/s 그대로는 0.6 m 옮기는 데 2.4 m 가 들어 1.5 m 앞 물체를 못 비킨다.

- [ ] **Step 5: 요구 1~12 대조(요구 12)**

설계서 17절 표의 각 행에 대해 "구현 위치(파일:시험 이름)"를 채워 넣는다. 빈 행이 있으면 사용자에게 보고한다(임의로 채우지 않는다).

| 요구 | 구현·시험 |
|---|---|
| 직진 흔들림 | `pure_pursuit` + `test_vcc_core StraightStartRampsWithoutTurning` |
| 3~4 m 앞 사람 무시 | `lanes horizon` + `test_lanes FarObstacleBeyondHorizonIsIgnored` |
| 유턴 호 R 0.2/0.1/제자리 | `turn_planner` + `test_turn_planner` 4개 |
| 정지 출발 60° 까지 제자리 | `test_state_machine StationaryPivotFromThirtyFiveDegrees`, `test_turn_planner StationarySmallTurnPrefersPivot` |
| 코너 0.5~0.6 m 이탈 부드럽게 | `test_state_machine ParallelOffsetRailIsNotAUturn`, `test_vcc_core ParallelOffsetRejoinsWithoutStopping` |
| 코너 감속 부드럽게 | `test_speed_profile CornerIsAnticipatedNotSudden` |
| 초음파 15~20 cm 비켜 가기 | `test_lanes PoleOnRailIsPassedWithTwentyCentimetres`, `test_ultrasonic` 5개 |
| 도착 한 번에·최대 3회·허용오차 유지 | `test_align_planner` 4개, goal checker 값 불변(`test_nav2_params_contract`) |
| 회피 부드럽게·휘청 금지 | `test_lanes NearlyEqualLanesDoNotFlipFlop`, `OffsetMovesAtLaneRate` |
| 레일 복귀 부드럽게 | `test_lanes ReturnsToRailOnlyAfterOneSecondClear` |
| 출발 가속 | `test_output_stage StartRampHalfSpeedThenSlow`, `ResyncsToMeasuredSpeedAfterExternalStop` |
| collision_monitor 동일 | yaml diff 에 collision_monitor 변경 0 |
| 지킬 선 | `test_vcc_limits_match_the_smoother`, `test_planner_contract` VCC 분기, 후진 금지 `NoReverseAndSymmetricTurnLimit` |
| inflation 분리는 반영 안 함 | yaml diff 에 inflation 변경 0 |
| 계산량 DWB 이하 | bench p99 |
| 이름 vcc | 패키지·플러그인 이름 |

- [ ] **Step 6: 커밋(두 저장소)**

```bash
cd ~/VICA-smarthandle/vica_ros2_ws
git add src/vica_vcc_controller
git commit -m "test(vcc): 젯슨 한 주기 bench — p99 <측정값> ms (예산 19.1 ms)"
cd ~/VICA-smarthandle
git add docs/superpowers/specs/2026-09-24-vcc-controller-design.md
git commit -m "docs(nav2): VCC 설계서 구현 반영 — 유턴 판정에 레일 방향 추가·거리장 5 m·회전 0.45/0.35·가중치 근거·옮기는 동안 감속"
```

- [ ] **Step 7: 사용자에게 넘길 것(이 계획의 끝)**

로봇을 움직이는 시험은 하지 않는다. 사용자에게 다음을 보고하고 멈춘다.
- 빌드된 설치본으로 nav2 를 다시 띄워야 VCC 가 올라온다는 것. controller_server 로그에서 `VCC configured` 한 줄을 확인한다.
- 설계서 15절 시험 순서의 2단계(바퀴 띄운 시험)부터가 사용자 몫이라는 것.
- 되돌리는 방법: yaml 에서 `FollowPath` ↔ `FollowPathRPP` 이름을 맞바꾸고, range 층 4개를 `True` 로 되돌린다.
