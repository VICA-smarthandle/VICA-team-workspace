# 긴 복도·특징 없는 곳 매핑 — 점검표와 손댈 값

2026-08-15 작성. `vica_map_0812`(44 m 복도) 실패와 `vica_map_0815`(18×22 m 방)
성공을 실측으로 비교한 결과다. **복도 재시험은 아직 안 했다.**

항목 ID(`CM-1` 등)는 고정이다. 커밋 메시지·주석에서 그대로 참조한다.

---

## 1. 문제가 무엇인가

복도는 **어디서 봐도 똑같이 생겼다.** 그래서 스캔 정합이 고칠 수 있는 것과
없는 것이 갈린다.

| | 스캔으로 고칠 수 있나 | 왜 |
| --- | --- | --- |
| 좌우 위치 | **예** | 양옆 벽이 바로 알려 준다 |
| 각도 | **예** | 벽 방향이 알려 준다 |
| **앞뒤 위치** | **아니오** | 10 m 앞으로 밀어도 그림이 똑같다 |

좌우·각도 오차는 매 스캔 지워지는데 **앞뒤 오차만 아무도 안 지운다.** 오도메트리가
조금씩 틀리는 것이 그대로 쌓인다.

---

## 2. 측정된 사실

`constraint_builder_2d` 가 내는 `differs by translation` 이 이 문제의 온도계다.
"지금 위치가 loop closure 가 본 자리와 얼마나 다른가"이므로, 크면 그만큼 밀려
있었다는 뜻이다.

```
8/12 20:54  복도 44 m   구속조건 6894건   최대 7.01 m   1 m 초과 423건 (6.1%)
8/15 16:41  방 18x22 m  구속조건 8547건   최대 0.14 m   1 m 초과   0건 (0.0%)
```

`rotation` 은 두 회차 모두 0.031 / 0.023 으로 멀쩡했다. **회전은 맞는데 위치만
틀렸다** — 순수한 앞뒤 미끄러짐이다.

**주의**: 두 회차는 장소가 다르다. 8/15 의 개선이 우리 수정 때문인지 애초에 쉬운
곳이라서인지 **이 두 회차로는 못 가른다.** 같은 복도를 다시 그려 봐야 한다.

---

## 3. 시작 전 점검표

`bash scripts/vica_map_record.sh <이름> --check-only` 가 아래 대부분을 대신한다.

- [ ] **중복 실행 0** — `cartographer_node`·`ekf_node`·`encoder_feedback` 이 각
      1개. 두 벌이 돌면 `/odom` 발행자가 둘이 되어 회차가 통째로 무효다
      (2026-08-11 20:07 에 두 회차를 잃었다)
- [ ] **`/odom`·`/wheel/odom` 발행자 각 1**
- [ ] **자이로 보정** — `⑦ imu` 칸에 이 한 줄이 떠야 한다

      ```
      Gyro bias calibrated over 1000 samples: (...) Removed yaw drift of ... deg/hour
      ```

      `calibration aborted: motion detected` 면 그 칸만 내렸다 다시 띄운다.
      편향을 안 빼고 원본을 그대로 내보내는 상태다. **이건 회차의 유효/무효를
      가른다** — 2026-08-15 측정 편향이 **-85.0 deg/hour** 였고, 14.2분 주행이면
      **20도**다. ⑥ d455 를 켠 뒤 20초(50 Hz × 1000샘플) 완전 정지해야 모인다
- [ ] **bag 기록** — `bash scripts/vica_map_record.sh <이름>`.
      **저장에 실패하면 지도가 아예 안 남는다**(8/12 오전 6회가 그랬다). bag 이
      유일한 기록이고, 있으면 아래 축들을 재주행 없이 비교할 수 있다
- [ ] **복도에서 버려지는 반사 비율** — 아래 §5 CM-1 판단 근거

---

## 4. 주행 방법 — 비용 0, 효과 가장 큼

- **왕복한다.** 복도 끝까지 갔다가 **같은 길로** 돌아온다. 한 방향으로만 훑으면
  앞뒤 오차를 지울 기회가 없다
- **출발한 자리에서 끝낸다.** 가장 강한 loop closure 다
- **교차로·문 앞은 여러 번 지난다.** 특징이 있는 곳이 앞뒤 위치를 잡아 주는
  유일한 지점이다
- **속도**: 직진 0.3 m/s, 회전 0.4 rad/s 아래. 예측 탐색 창이 0.1 m 라
  0.5 m/s 면 스캔 사이 이동이 10 cm 로 창 경계에 닿는다
- **RViz 를 본다.** 지도가 툭 튀거나 벽이 갈라지면 **그 시각을 적어 둔다.**
  틀린 loop closure 가 들어간 순간이고, bag 에서 바로 찾을 수 있다

---

## 5. 손댈 값 — 우선순위대로

**한 번에 하나씩.** bag 이 있으면 `cartographer_offline_node` 로 재주행 없이
바꿔 가며 돌린다.

```bash
ros2 launch cartographer_ros offline_backpack_2d.launch.py \
    bag_filenames:=$HOME/vica_data/bags/<이름>
```

### CM-1 `max_range` 8.0 → 11.0 — 먼저 이것

```lua
TRAJECTORY_BUILDER_2D.max_range = 8.0   ->  11.0
TRAJECTORY_BUILDER_2D.missing_data_ray_length = 8.5  ->  11.5   -- 함께 올린다
```

**라이다는 12 m 를 보는데 8 m 에서 자르고 있다.** RPLIDAR 드라이버 신고값이
0.15~12.00 m 이고 실내 실측 최대 반사가 9.04 m 였다.

복도에서 앞뒤 위치를 알려 주는 것은 **멀리 있는 것들**이다 — 복도 끝, 문, 교차로.
8 m 에서 자르면 그걸 버리고 양옆 벽만 남는데, 양옆 벽은 앞뒤에 대해 아무 말도
하지 않는다.

- 위험: 계산량 증가. 원거리 점은 각해상도가 성겨(0.499도 → 11 m 에서 9.6 cm 간격)
  잡음이 섞인다
- 부수 효과: loop closure 점수 자체가 올라간다. **그래서 CM-3 보다 먼저 한다**
- 판정: `differs by translation` 최대값, 1 m 초과 건수

### CM-2 `ceres_scan_matcher.translation_weight` 10.0 → 40.0

```lua
TRAJECTORY_BUILDER_2D.ceres_scan_matcher.translation_weight = 10.0  ->  40.0
```

Ceres 정합은 두 가지를 저울질한다.

```
occupied_space_weight 10.0   "스캔이 지도에 얼마나 잘 맞는가"
translation_weight    10.0   "예측(오도메트리)에서 얼마나 벗어나지 않는가"
```

**복도에서는 앞의 항이 앞뒤 방향으로 아무 정보가 없다.** 어디에 놓아도 비용이
같으니 수치 잡음만으로 미끄러진다. `translation_weight` 를 올리면 "스캔이 말이
없으면 오도메트리를 믿는다"가 되어 그 미끄러짐이 억제된다.

- 위험: **오도메트리가 나쁘면 그 오차를 그대로 따라간다.** 자이로 보정과
  엔코더가 멀쩡하다는 전제가 필요하다. §3 점검표가 그래서 앞에 있다
- 이게 복도에 가장 직접적인 축일 수 있다. 다만 CM-1 이 정보를 늘리는 쪽이라
  부작용이 적어 순서를 뒤에 둔다

### CM-3 `constraint_builder.min_score` 0.62 → 0.70

```lua
POSE_GRAPH.constraint_builder.min_score = 0.62  ->  0.70
```

**8/12 에 3.83 m 를 밀어 넣은 매칭의 점수가 70.8%·71.3% 였다.** 복도에서는 3.8 m
떨어진 자리도 비슷하게 생겨서, 통과한 매칭이 **틀린 것**일 수 있다. 틀린 게
들어가면 고치는 게 아니라 지도를 찢는다.

- **위험이 크다.** 8/15 회차의 점수 중앙값이 71.5%, 최소 62.0% 였다. 0.72 이상으로
  올리면 정상 회차의 절반이 사라져 loop closure 자체가 줄고 드리프트가 남는다
- 그래서 **CM-1 로 점수를 먼저 끌어올린 뒤** 손댄다
- 판정: 1 m 초과 건수가 줄면서 **총 구속조건 수가 크게 줄지 않아야** 한다

### CM-4 `use_imu_data` false → true

```lua
TRAJECTORY_BUILDER_2D.use_imu_data = false  ->  true
```

지금 Cartographer 는 오도메트리 토픽 하나로만 다음 스캔 위치를 예측한다. IMU 를
직접 쓰면 회전 예측이 좋아진다.

**[함정] launch 에 `imu` remap 이 없다.** 켜면 Cartographer 가 기본 이름 `imu` 를
구독하는데 우리 토픽은 `/imu/base_link` 다. `vica_cartographer_2d.launch.py` 의
`remappings` 에 `('imu', '/imu/base_link')` 를 추가해야 한다. 안 하면 IMU 를
기다리다 아무것도 통합하지 않는다.

- 조건: IMU 주기가 스캔보다 빨라야 하고(현재 /scan 10~12 Hz, IMU 는 그보다 빠르다)
  중력 정렬이 맞아야 한다
- **다만 8/12 의 문제는 병진이었다.** 회전은 이미 0.031 로 멀쩡했으므로 이 축의
  기대값은 낮다. 순위를 뒤에 둔 이유다

### CM-5 `submaps.num_range_data` 기본 90 → 60

```lua
TRAJECTORY_BUILDER_2D.submaps.num_range_data = 60   -- 지금은 설정하지 않아 기본 90
```

submap 하나가 짧아지면 그 안에 쌓이는 왜곡이 줄고 구속조건이 많아진다.
대신 계산량과 메모리가 는다.

### CM-6 `POSE_GRAPH.optimize_every_n_nodes` 35 → 20

더 자주 최적화해서 큰 보정이 몰아서 오는 것을 줄인다. 계산량이 는다.

---

## 6. 판정 방법

Cartographer 노드 로그 한 줄이면 된다. bag 이 없어도 이건 남는다.

```bash
F=$(ls -1t ~/.ros/log/cartographer_node_*.log | head -1)
grep -oE "differs by translation [0-9.]+ rotation [0-9.]+ with score [0-9.]+%" "$F" |
python3 -c "
import sys,re,statistics
tr=[];sc=[]
for l in sys.stdin:
    m=re.search(r'translation ([\d.]+) rotation ([\d.]+) with score ([\d.]+)',l)
    if m: tr.append(float(m.group(1))); sc.append(float(m.group(3)))
big=[t for t in tr if t>1.0]
print(f'구속조건 {len(tr)}건  최대 {max(tr):.2f} m  1m초과 {len(big)}건 ({len(big)/len(tr)*100:.1f}%)')
print(f'score 중앙 {statistics.median(sc):.1f}%  최소 {min(sc):.1f}%')
"
```

**합격선**

| | |
| --- | --- |
| `translation` 최대 | **1 m 미만** |
| 1 m 초과 건수 | **0건** |
| 구속조건 수 | 축을 바꾼 뒤에도 **크게 줄지 않을 것**(CM-3 의 위험) |

지도 자체는 **벽이 한 줄로 찍혔는가**로 본다. 두 겹이면 실패다.

---

## 7. 함정

- **터미네이터는 config 를 프로세스 시작 때 한 번만 읽는다.** 레이아웃을 고친 뒤
  기존 창이 떠 있으면 새 `terminator -l vica_map` 이 DBus 로 그 프로세스에 붙어
  옛 config 를 쓴다. 창을 전부 닫고 다시 띄운다. `-u`(DBus 우회)는 쓰지 말 것 —
  두 번째 인스턴스가 생겨 스택이 두 벌 돈다
- **`vica_map` 레이아웃에서 IMU 를 빼지 말 것.** 2026-08-13~15 에 빠져 있었다.
  `ekf.yaml` 의 `imu0_config` 가 `vyaw` 를 true 로 융합하므로 IMU 는 EKF → `/odom`
  → Cartographer 로 그대로 닿는다. `use_imu_data = false` 는 "직접 구독하지
  않는다"는 뜻이지 "무관하다"는 뜻이 아니다
- **`odom_topic` 인자**는 2026-08-15 `733a322` 로 고쳤다. 그 전에는 launch 가
  `'/odom'` 을 하드코딩해서 명령줄 인자가 조용히 무시됐다
- **저장에 실패하면 지도가 안 남는다.** 8/12 오전 6회가 그랬고, 결국 원인을 화면
  캡쳐에서 찾았다. bag 을 남기면 이런 일이 없다

---

## 8. 닫힌 것 — 다시 열지 않는다

- **odom 소스(`/odom` vs `/wheel/odom`)가 8/12 실패의 원인이라는 가설** — 반증됐다.
  8/11~12 매핑 13회가 전부 EKF `/odom` 이었고 성공한 회차도 같은 값이다.
  `/wheel/odom` 은 아직 한 번도 시험된 적이 없으니, 시험하려면 그 축 하나만 바꾼다
- **`min_range` 0.15 → 0.25** — 완료(`cd7b84c`). 차체 프레임(로봇 중심 좌우
  13~14 cm, 0.22 m)이 지도에 들어오던 것을 막았다. 되돌리지 말 것.
  근거는 `devlog/2026-08-15-복구예산-collision-monitor-자동재시도.md` §9
