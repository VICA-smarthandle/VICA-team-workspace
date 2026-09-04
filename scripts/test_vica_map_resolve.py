"""이름/id -> id 변환기와 번호 메뉴의 규약을 고정한다 (2026-09-04).

실행:  python3 -m pytest scripts/test_vica_map_resolve.py -q
"""
from __future__ import annotations

import json
import sys
import unicodedata
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import vica_map_pick as pick  # noqa: E402
import vica_map_resolve as resolver  # noqa: E402


def _map(maps_dir: Path, map_id: str, display: str | None = None) -> None:
    (maps_dir / f"{map_id}.yaml").write_text("resolution: 0.05\n", encoding="utf-8")
    if display:
        (maps_dir / f"{map_id}.meta.json").write_text(
            json.dumps({"map_id": map_id, "display_name": display}), encoding="utf-8"
        )


@pytest.fixture
def maps(tmp_path: Path) -> Path:
    _map(tmp_path, "vica_map_0903_d")
    _map(tmp_path, "map_0904_151230", "병원 2층")
    _map(tmp_path, "map_0904_160000", "로비")
    (tmp_path / "map_0904_151230_keepout.yaml").write_text("x", encoding="utf-8")
    (tmp_path / "CURRENT_MAP").write_text("vica_map_0903_d\n", encoding="utf-8")
    return tmp_path


def test_empty_query_reads_current_map(maps: Path) -> None:
    assert resolver.resolve("", maps) == ("vica_map_0903_d", "maps/CURRENT_MAP", "vica_map_0903_d")


def test_ascii_id_passes_through_unchanged(maps: Path) -> None:
    assert resolver.resolve("map_0904_151230", maps)[0] == "map_0904_151230"
    assert resolver.resolve("map_0904_151230", maps)[2] == "병원 2층"


def test_hangul_name_resolves_to_id_even_when_decomposed(maps: Path) -> None:
    # macOS/iOS 가 보내는 NFD 한글도 같은 지도여야 한다.
    decomposed = unicodedata.normalize("NFD", "병원 2층")
    assert decomposed != "병원 2층"
    assert resolver.resolve(decomposed, maps)[0] == "map_0904_151230"


def test_unknown_name_lists_available_maps(maps: Path) -> None:
    with pytest.raises(resolver.ResolveError) as caught:
        resolver.resolve("없는 지도", maps)
    assert caught.value.exit_code == resolver.EXIT_NOT_FOUND
    assert "병원 2층" in str(caught.value)


def test_duplicate_names_must_be_picked_by_id(maps: Path) -> None:
    _map(maps, "map_0905_000000", "병원 2층")
    with pytest.raises(resolver.ResolveError) as caught:
        resolver.resolve("병원 2층", maps)
    assert caught.value.exit_code == resolver.EXIT_AMBIGUOUS


def test_fallback_is_used_only_without_current_map(maps: Path) -> None:
    (maps / "CURRENT_MAP").unlink()
    assert resolver.resolve("", maps, fallback="vica_map_0903_d")[1].startswith("fallback")
    with pytest.raises(resolver.ResolveError):
        resolver.resolve("", maps)


def test_list_skips_keepout_and_marks_current(maps: Path) -> None:
    rows = resolver.list_maps(maps, destinations_root=maps / "no-such-root")
    ids = [row["map_id"] for row in rows]
    assert "map_0904_151230_keepout" not in ids
    assert {row["map_id"]: row["is_current"] for row in rows}["vica_map_0903_d"] is True
    assert all(row["has_destinations"] is False for row in rows)


def test_cli_prints_tab_separated_fields(maps: Path, capsys) -> None:
    assert resolver.main(["--maps-dir", str(maps), "로비"]) == 0
    assert capsys.readouterr().out.strip() == "map_0904_160000\t환경변수(이름)\t로비"


def test_pick_by_number_and_by_name_writes_current_map(maps: Path) -> None:
    rows = resolver.list_maps(maps, destinations_root=maps / "none")
    first = rows[0]["map_id"]
    assert pick.choose(rows, "1") == first
    assert pick.main(["--set", "병원 2층", "--yes", "--maps-dir", str(maps)]) == 0
    assert (maps / "CURRENT_MAP").read_text(encoding="utf-8") == "map_0904_151230\n"
    with pytest.raises(resolver.ResolveError):
        pick.choose(rows, "99")
