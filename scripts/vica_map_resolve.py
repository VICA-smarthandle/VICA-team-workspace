#!/usr/bin/env python3
"""지도 이름(한글 표시 이름 또는 영문 id)을 지도 id 로 바꾼다.

왜 있는가 (2026-09-04). 지도 이름을 한글로 적을 수 있게 하면서 "사람이 읽는 이름"과
"기계가 쓰는 id"를 갈랐다. 파일·yaml·URL·VICA_MAP_YAML 은 계속 영문 id 를 쓰고,
한글 이름은 maps/<id>.meta.json 에만 산다. 그래서 사람이 이름을 적는 자리
(VICA_MAP_ID 환경변수, goto/initpose, 번호 메뉴)에서 id 로 바꾸는 일이 필요한데,
그 일을 여기 한 곳이 한다 — 터미네이터 rc 템플릿, vica_goto.sh,
vica_set_initial_pose.sh, vica_map_pick.py 가 전부 이 파일을 부른다. 변환 규칙이
두 군데면 언젠가 어긋난다.

    python3 scripts/vica_map_resolve.py                    # CURRENT_MAP 의 id
    python3 scripts/vica_map_resolve.py '병원 2층'          # 이름 -> id
    python3 scripts/vica_map_resolve.py --display map_0904_151230
    python3 scripts/vica_map_resolve.py --list             # JSON, 최신순

출력(기본):  <id> TAB <출처> TAB <표시 이름>  — rc 가 IFS=$'\\t' 로 읽는다.
종료 코드:   0 성공 / 2 못 찾음 / 3 이름이 겹침 / 4 지도 폴더 없음
표준 라이브러리만 쓴다 — rc 가 부팅 때마다 부르므로 가벼워야 한다.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

EXIT_NOT_FOUND = 2
EXIT_AMBIGUOUS = 3
EXIT_NO_MAPS_DIR = 4


class ResolveError(Exception):
    """id 를 정하지 못했다. exit_code 로 종류를 구분한다."""

    def __init__(self, message: str, exit_code: int) -> None:
        super().__init__(message)
        self.exit_code = exit_code


def nfc(text: str | None) -> str:
    """한글을 NFC 로 고정한다. macOS 가 자모로 풀어(NFD) 보낸 이름도 같은 이름이 된다."""
    return unicodedata.normalize("NFC", text or "").strip()


def default_maps_dir() -> Path:
    workspace = os.environ.get("VICA_ROS_WS", "").strip()
    if workspace:
        return Path(workspace) / "maps"
    return Path(__file__).resolve().parent.parent / "vica_ros2_ws" / "maps"


def default_destinations_root() -> Path:
    return Path.home() / "vica_data" / "destinations"


def read_meta(maps_dir: Path, map_id: str) -> dict:
    path = maps_dir / f"{map_id}.meta.json"
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return document if isinstance(document, dict) else {}


def display_name_of(maps_dir: Path, map_id: str) -> str:
    name = read_meta(maps_dir, map_id).get("display_name")
    return nfc(name) if isinstance(name, str) and nfc(name) else map_id


def current_map_id(maps_dir: Path) -> str:
    try:
        return (maps_dir / "CURRENT_MAP").read_text(encoding="utf-8").splitlines()[0].strip()
    except (OSError, IndexError):
        return ""


def list_maps(maps_dir: Path, destinations_root: Path | None = None) -> list[dict]:
    """지도 목록(최신 저장순). yaml 이 있는 것만 지도로 친다 — Nav2 가 읽는 파일이다."""
    destinations_root = destinations_root or default_destinations_root()
    current = current_map_id(maps_dir)
    rows = []
    for yaml_path in maps_dir.glob("*.yaml"):
        map_id = yaml_path.stem
        if map_id.endswith("_keepout"):
            continue
        meta = read_meta(maps_dir, map_id)
        mtime = datetime.fromtimestamp(yaml_path.stat().st_mtime)
        saved_at = meta.get("saved_at") if isinstance(meta.get("saved_at"), str) else ""
        rows.append(
            {
                "map_id": map_id,
                "display_name": display_name_of(maps_dir, map_id),
                "saved_at": saved_at or mtime.isoformat(timespec="seconds"),
                "sort_key": mtime.timestamp(),
                "is_current": map_id == current,
                "has_destinations": (
                    destinations_root / map_id / "destinations.yaml"
                ).is_file(),
            }
        )
    rows.sort(key=lambda row: row["sort_key"], reverse=True)
    for row in rows:
        row.pop("sort_key")
    return rows


def resolve(query: str, maps_dir: Path, fallback: str = "") -> tuple[str, str, str]:
    """(id, 출처, 표시 이름) 을 돌려준다. 못 정하면 ResolveError."""
    if not maps_dir.is_dir():
        raise ResolveError(f"지도 폴더가 없습니다: {maps_dir}", EXIT_NO_MAPS_DIR)

    wanted = nfc(query)
    source = "환경변수"
    if not wanted:
        wanted = current_map_id(maps_dir)
        source = "maps/CURRENT_MAP"
        if not wanted and fallback:
            wanted, source = fallback, "fallback — CURRENT_MAP 이 없다"
        if not wanted:
            raise ResolveError(
                "현재 지도를 알 수 없습니다: maps/CURRENT_MAP 이 없고 VICA_MAP_ID 도 "
                "비어 있습니다. python3 scripts/vica_map_pick.py 로 고르세요.",
                EXIT_NOT_FOUND,
            )

    # 1) 영문 id 그대로 — 파일이 있으면 끝. 이 경로가 옛 동작과 같다.
    if (maps_dir / f"{wanted}.yaml").is_file():
        return wanted, source, display_name_of(maps_dir, wanted)

    # 2) 표시 이름(한글)으로 찾는다. 같은 이름이 둘이면 사람이 골라야 한다.
    matches = [row for row in list_maps(maps_dir) if nfc(row["display_name"]) == wanted]
    if len(matches) == 1:
        row = matches[0]
        return row["map_id"], f"{source}(이름)", row["display_name"]
    if matches:
        ids = ", ".join(row["map_id"] for row in matches)
        raise ResolveError(
            f"'{wanted}' 라는 이름의 지도가 {len(matches)}개입니다: {ids}\n"
            "       id 로 지정하세요: export VICA_MAP_ID=<id>",
            EXIT_AMBIGUOUS,
        )
    available = "\n".join(
        f"         {row['display_name']:<20s} {row['map_id']}" for row in list_maps(maps_dir)
    )
    raise ResolveError(
        f"'{wanted}' 지도를 찾지 못했습니다 ({source}). 쓸 수 있는 지도:\n{available}",
        EXIT_NOT_FOUND,
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="지도 이름/id -> id 변환기")
    parser.add_argument("query", nargs="?", default="", help="표시 이름 또는 id. 비우면 CURRENT_MAP")
    parser.add_argument("--maps-dir", type=Path, default=None, help="기본 $VICA_ROS_WS/maps")
    parser.add_argument("--destinations-root", type=Path, default=None)
    parser.add_argument("--fallback", default="", help="CURRENT_MAP 도 없을 때 쓸 id")
    parser.add_argument("--display", action="store_true", help="표시 이름만 출력")
    parser.add_argument("--list", action="store_true", help="지도 목록을 JSON 으로 출력")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    maps_dir = args.maps_dir or default_maps_dir()
    try:
        if args.list:
            if not maps_dir.is_dir():
                raise ResolveError(f"지도 폴더가 없습니다: {maps_dir}", EXIT_NO_MAPS_DIR)
            print(json.dumps(list_maps(maps_dir, args.destinations_root), ensure_ascii=False))
            return 0
        map_id, source, display = resolve(args.query, maps_dir, args.fallback)
    except ResolveError as error:
        print(f"[지도] {error}", file=sys.stderr)
        return error.exit_code
    if args.display:
        print(display)
    else:
        print(f"{map_id}\t{source}\t{display}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
