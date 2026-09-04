#!/usr/bin/env python3
"""번호나 이름으로 지도를 골라 maps/CURRENT_MAP 에 적는다 (2026-09-04).

CURRENT_MAP 은 "로봇이 쓸 지도" 한 곳이다. 저장 스크립트가 저장 성공 때 갱신하고,
최신 지도가 아닌 것을 띄우고 싶을 때는 이 도구로 갱신한다. 터미네이터 rc·goto·
initpose·앱 목록의 '(현재)' 표시가 전부 같은 파일을 읽으므로 어긋나지 않는다.
터미널에서 한글을 치지 않아도 되게 번호로 고른다 (이름·id 도 된다).

    python3 scripts/vica_map_pick.py                       # 목록 보고 번호 입력
    python3 scripts/vica_map_pick.py --set '병원 2층'        # 바로 적기(확인 질문)
    python3 scripts/vica_map_pick.py --set map_0904_151230 --yes

이미 떠 있는 터미네이터 칸은 옛 지도를 들고 있다 — 칸을 다시 띄우거나 터미네이터를
다시 연다. 뜬 지 오래된 칸이 옛 지도로 달리는 사고가 이 프로젝트에 실제로 있었다
(2026-08-13, 칸마다 다른 지도).
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import vica_map_resolve as resolver  # noqa: E402


def format_rows(rows: list[dict]) -> list[str]:
    lines = []
    for index, row in enumerate(rows, start=1):
        name = row["display_name"]
        map_id = row["map_id"] if row["display_name"] != row["map_id"] else ""
        when = row["saved_at"][:16].replace("T", " ")
        flags = []
        if row["is_current"]:
            flags.append("현재")
        flags.append("목적지 있음" if row["has_destinations"] else "목적지 없음")
        lines.append(f"{index:>3}) {name:<22s} {map_id:<18s} {when}  {' · '.join(flags)}")
    return lines


def choose(rows: list[dict], answer: str) -> str:
    """번호면 그 줄의 id, 아니면 이름/id 그대로(변환기가 처리)."""
    answer = answer.strip()
    if answer.isdigit():
        index = int(answer)
        if not 1 <= index <= len(rows):
            raise resolver.ResolveError(f"번호는 1~{len(rows)} 사이여야 합니다.", 2)
        return rows[index - 1]["map_id"]
    return answer


def terminator_running() -> bool:
    try:
        return subprocess.run(["pgrep", "-x", "terminator"], capture_output=True).returncode == 0
    except OSError:
        return False


def write_current(maps_dir: Path, map_id: str) -> Path:
    path = maps_dir / "CURRENT_MAP"
    path.write_text(map_id + "\n", encoding="utf-8")  # vica_map_save.sh 와 같은 형식
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="지도를 골라 maps/CURRENT_MAP 에 적는다")
    parser.add_argument("--set", dest="query", default=None, help="이름·id·번호를 바로 지정")
    parser.add_argument("--yes", action="store_true", help="확인 질문 없이 적는다")
    parser.add_argument("--maps-dir", type=Path, default=None)
    parser.add_argument("--destinations-root", type=Path, default=None)
    args = parser.parse_args(argv)
    maps_dir = args.maps_dir or resolver.default_maps_dir()
    if not maps_dir.is_dir():
        print(f"[지도] 지도 폴더가 없습니다: {maps_dir}", file=sys.stderr)
        return resolver.EXIT_NO_MAPS_DIR

    rows = resolver.list_maps(maps_dir, args.destinations_root)
    if not rows:
        print(f"[지도] {maps_dir} 에 지도가 없습니다.", file=sys.stderr)
        return resolver.EXIT_NOT_FOUND

    if args.query is None:
        print(f"지도 목록 ({maps_dir}, 최신순):")
        print("\n".join(format_rows(rows)))
        try:
            answer = input("\n번호 또는 이름 (엔터 = 취소): ")
        except EOFError:
            answer = ""
        if not answer.strip():
            print("취소했습니다.")
            return 0
    else:
        answer = args.query

    try:
        map_id, _source, display = resolver.resolve(choose(rows, answer), maps_dir)
    except resolver.ResolveError as error:
        print(f"[지도] {error}", file=sys.stderr)
        return error.exit_code

    label = display if display == map_id else f"{display} ({map_id})"
    if not args.yes:
        try:
            confirm = input(f"maps/CURRENT_MAP 을 '{label}' 로 바꿉니다. 계속할까요? [y/N] ")
        except EOFError:
            confirm = ""
        if confirm.strip().lower() not in ("y", "yes"):
            print("취소했습니다.")
            return 0

    path = write_current(maps_dir, map_id)
    print(f"{path} -> {map_id}   ({label})")
    print("다음: terminator -l vica   (또는 vica_map 등 필요한 레이아웃)")
    if terminator_running():
        print("[주의] 터미네이터가 이미 떠 있습니다. 떠 있는 칸은 옛 지도를 들고 있으니")
        print("       칸을 다시 띄우거나 터미네이터를 다시 여세요.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
