#!/usr/bin/env python3
"""주행 중 자원 사용 기록기 — CPU·GPU·RAM 전체와 프로세스별 사용량을 초 단위로 남긴다.

사용법 (별도 터미널에서):

    python3 scripts/vica_usage_recorder.py          # 기본 1초 간격
    python3 scripts/vica_usage_recorder.py --interval 2

끝낼 때는 Ctrl+C. 기록은 ~/vica_data/usage/usage_<시각>.jsonl 에 쌓인다.
주행 시작·종료 시각을 메모해 두면, 나중에 그 구간만 잘라 정리할 수 있다.

전체 수치는 tegrastats(젯슨 공식)에서, 프로세스별은 ps 에서 읽는다.
"""
from __future__ import annotations

import argparse
import datetime
import json
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

OUT_DIR = Path.home() / "vica_data" / "usage"
TOP_N = 12          # 기록할 상위 프로세스 수 (CPU 기준 정렬)

RAM_RE = re.compile(r"RAM (\d+)/(\d+)MB")
SWAP_RE = re.compile(r"SWAP (\d+)/(\d+)MB")
CPU_RE = re.compile(r"CPU \[([^\]]+)\]")
GPU_RE = re.compile(r"GR3D_FREQ (\d+)%")


def parse_tegrastats(line: str) -> dict:
    out = {}
    if m := RAM_RE.search(line):
        out["ram_mb"], out["ram_total_mb"] = int(m.group(1)), int(m.group(2))
    if m := SWAP_RE.search(line):
        out["swap_mb"] = int(m.group(1))
    if m := CPU_RE.search(line):
        cores = [int(c.split("%")[0]) for c in m.group(1).split(",")
                 if "%" in c]
        out["cpu_cores"] = cores
        out["cpu_avg"] = round(sum(cores) / max(1, len(cores)), 1)
    if m := GPU_RE.search(line):
        out["gpu"] = int(m.group(1))
    return out


def top_processes() -> list[dict]:
    ps = subprocess.run(
        ["ps", "-eo", "pid,pcpu,rss,comm,args", "--sort=-pcpu"],
        capture_output=True, text=True).stdout.splitlines()[1:]
    rows = []
    for line in ps[:TOP_N * 2]:
        parts = line.split(None, 4)
        if len(parts) < 5:
            continue
        pid, pcpu, rss, comm, args = parts
        # ros 노드는 comm 이 전부 python3 라 구분이 안 된다 — args 에서 이름을 찾는다
        name = comm
        for token in args.split():
            if "ros_" in token or "_node" in token or token.endswith(".py"):
                name = token.rsplit("/", 1)[-1][:28]
                break
        rows.append({"pid": int(pid), "cpu": float(pcpu),
                     "rss_mb": round(int(rss) / 1024), "name": name})
        if len(rows) >= TOP_N:
            break
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--interval", type=float, default=1.0, help="샘플 간격(초)")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = OUT_DIR / f"usage_{stamp}.jsonl"

    tegra = subprocess.Popen(
        ["tegrastats", "--interval", str(int(args.interval * 1000))],
        stdout=subprocess.PIPE, text=True)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))

    print(f"기록 시작 → {out_path}")
    print("주행 시작·종료 시각을 메모해 두세요. 끝낼 때 Ctrl+C.")
    n = 0
    try:
        with open(out_path, "a") as f:
            for line in tegra.stdout:
                sample = {"t": time.time(),
                          "hms": datetime.datetime.now().strftime("%H:%M:%S")}
                sample.update(parse_tegrastats(line))
                sample["top"] = top_processes()
                f.write(json.dumps(sample, ensure_ascii=False) + "\n")
                f.flush()
                n += 1
                worst = sample["top"][0] if sample["top"] else {}
                print(f"\r{sample['hms']}  CPU {sample.get('cpu_avg', '?'):>5}%"
                      f"  GPU {sample.get('gpu', '?'):>3}%"
                      f"  RAM {sample.get('ram_mb', 0) / 1024:.1f}"
                      f"/{sample.get('ram_total_mb', 0) / 1024:.0f}GB"
                      f"  1위 {worst.get('name', '-')}"
                      f" {worst.get('cpu', 0):.0f}%   ", end="")
    except KeyboardInterrupt:
        pass
    finally:
        tegra.terminate()
        print(f"\n기록 종료 — {n}샘플, {out_path}")


if __name__ == "__main__":
    main()
