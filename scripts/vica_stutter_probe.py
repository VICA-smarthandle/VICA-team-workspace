#!/usr/bin/env python3
"""주행 멈칫 채증 — cmd_vel 발행 끊김을 시각(epoch)과 함께 기록한다.

주행 중 잠깐씩 멈칫하는 원인이 음성(STT 버스트)인지 가리기 위한 상관
채증 도구다 (2026-09-01). "움직이던 중"의 끊김만 잡는다 — 목적지 도착
등 정상 정지(직전 속도 ~0)는 세지 않는다.

배선: /cmd_vel_req(Nav2 최종 요청)와 /cmd_vel_safe(Safety 승인)를 구독만
한다. 발행·리맵 없음 — 주행에 어떤 영향도 주지 않는다.

사용 (주행 전 터미널 하나 더):
    source /opt/ros/humble/setup.bash
    python3 scripts/vica_stutter_probe.py            # 기본 끊김 문턱 0.3초
    python3 scripts/vica_stutter_probe.py --gap 0.2
종료는 Ctrl+C — 요약(횟수·최장·상위 목록)을 출력한다.

상관 분석 (주행 후):
    끊김 줄의 [epoch] 를 웨이크워드 로그의 STT 계측 시각과 대조한다.
      grep "계측" ~/.ros/log/<웨이크워드>.log   # [1788…] … STT 3.61s
    끊김 epoch 가 STT 구간(계측 시각 - STT초 ~ 계측 시각)과 겹치면
    음성 경합이 유력하고, 안 겹치면 Nav2 쪽(재계획·costmap)을 본다.
  req 만 끊기면 Nav2(또는 그 위 CPU)가 범인, safe 만 끊기면 Safety 다.
"""
from __future__ import annotations

import argparse
import time
from datetime import datetime

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node

MOVING_V = 0.02   # m/s  — 이보다 빠르면 "움직이는 중"
MOVING_W = 0.05   # rad/s


class Watch:
    def __init__(self, topic: str, gap_sec: float) -> None:
        self.topic = topic
        self.gap_sec = gap_sec
        self.last_at: float | None = None
        self.last_moving = False
        self.gaps: list[tuple[float, float]] = []   # (시작 epoch, 길이)

    def on_msg(self, msg: Twist) -> None:
        now = time.time()
        if self.last_at is not None:
            dt = now - self.last_at
            if dt >= self.gap_sec and self.last_moving:
                self.gaps.append((self.last_at, dt))
                stamp = datetime.fromtimestamp(self.last_at).strftime("%H:%M:%S")
                print(f"[{self.last_at:.3f}] 끊김 {self.topic}: {dt:.2f}s "
                      f"(시작 {stamp}, 움직이던 중)", flush=True)
        self.last_at = now
        self.last_moving = (abs(msg.linear.x) > MOVING_V
                            or abs(msg.angular.z) > MOVING_W)


class StutterProbe(Node):
    def __init__(self, gap_sec: float) -> None:
        super().__init__("vica_stutter_probe")
        self.watches = [Watch("/cmd_vel_req", gap_sec),
                        Watch("/cmd_vel_safe", gap_sec)]
        for w in self.watches:
            self.create_subscription(Twist, w.topic, w.on_msg, 10)
        print(f"멈칫 채증 시작 — 문턱 {gap_sec}s, 대상: "
              f"{', '.join(w.topic for w in self.watches)} (Ctrl+C 로 요약)",
              flush=True)

    def summary(self) -> None:
        print("\n===== 요약 =====")
        for w in self.watches:
            if not w.gaps:
                print(f"{w.topic}: 끊김 0회")
                continue
            longest = sorted(w.gaps, key=lambda g: -g[1])[:5]
            print(f"{w.topic}: 끊김 {len(w.gaps)}회, "
                  f"최장 {longest[0][1]:.2f}s")
            for at, dt in longest:
                stamp = datetime.fromtimestamp(at).strftime("%H:%M:%S")
                print(f"  [{at:.3f}] {stamp} — {dt:.2f}s")
        print("STT 대조:  grep \"계측\" ~/.ros/log/<웨이크워드>.log")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gap", type=float, default=0.3,
                    help="끊김으로 볼 최소 공백(초), 기본 0.3")
    args = ap.parse_args()
    rclpy.init()
    node = StutterProbe(args.gap)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.summary()
        node.destroy_node()


if __name__ == "__main__":
    main()
