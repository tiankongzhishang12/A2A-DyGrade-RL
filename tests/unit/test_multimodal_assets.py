from __future__ import annotations

import json
from pathlib import Path

import pytest

from a2a_dygrade_rl.utils.io import file_sha256
from a2a_dygrade_rl.utils.multimodal import PNG_SIGNATURE, png_dimensions, prepare_source_assets


ROOT = Path("data/processed/semantic_v2")


def _resources() -> list[dict]:
    return json.loads((ROOT / "resource_manifest.json").read_text(encoding="utf-8"))["resources"]


def test_all_formal_asap_assets_are_valid_and_deterministic():
    before = {row["relative_path"]: file_sha256(ROOT / row["relative_path"]) for row in _resources()}
    first = prepare_source_assets(_resources(), prepared_root=ROOT)
    second = prepare_source_assets(_resources(), prepared_root=ROOT)
    assert len(first) == 4
    assert [(row.sent_sha256, row.sent_width, row.sent_height) for row in first] == [
        (row.sent_sha256, row.sent_width, row.sent_height) for row in second
    ]
    assert sum(row.transform == "identity" for row in first) == 2
    tiffs = [row for row in first if row.source_mime_type == "image/tiff"]
    assert len(tiffs) == 2
    assert all(row.sent_mime_type == "image/png" and row.sent_bytes.startswith(PNG_SIGNATURE) for row in tiffs)
    assert all(png_dimensions(row.sent_bytes) == (row.source_width, row.source_height) for row in tiffs)
    after = {row["relative_path"]: file_sha256(ROOT / row["relative_path"]) for row in _resources()}
    assert before == after


def test_asset_path_escape_is_rejected(tmp_path: Path):
    root = tmp_path / "prepared"
    root.mkdir()
    outside = tmp_path / "outside.jpg"
    outside.write_bytes(b"fake")
    with pytest.raises(ValueError, match="越过 prepared_root"):
        prepare_source_assets(
            [{"asset_id": "x", "relative_path": "../outside.jpg", "sha256": file_sha256(outside), "mime_type": "image/jpeg", "byte_size": 4}],
            prepared_root=root,
        )


def test_asset_hash_and_size_mismatch_are_rejected(tmp_path: Path):
    root = tmp_path / "prepared"
    root.mkdir()
    asset = root / "a.jpg"
    asset.write_bytes(b"not-a-real-jpeg")
    with pytest.raises(ValueError, match="byte_size"):
        prepare_source_assets(
            [{"asset_id": "x", "relative_path": "a.jpg", "sha256": file_sha256(asset), "mime_type": "image/jpeg", "byte_size": 1}],
            prepared_root=root,
        )
    with pytest.raises(ValueError, match="sha256"):
        prepare_source_assets(
            [{"asset_id": "x", "relative_path": "a.jpg", "sha256": "0" * 64, "mime_type": "image/jpeg", "byte_size": len(asset.read_bytes())}],
            prepared_root=root,
        )

def test_declared_mime_must_match_actual_bytes(tmp_path: Path):
    root = tmp_path / "prepared"
    root.mkdir()
    official_jpeg = next(row for row in _resources() if row["mime_type"] == "image/jpeg")
    source = ROOT / official_jpeg["relative_path"]
    target = root / "asset.tiff"
    target.write_bytes(source.read_bytes())
    with pytest.raises(ValueError, match="MIME与实际字节不匹配"):
        prepare_source_assets(
            [{
                "asset_id": "x",
                "relative_path": "asset.tiff",
                "sha256": file_sha256(target),
                "mime_type": "image/tiff",
                "byte_size": target.stat().st_size,
            }],
            prepared_root=root,
        )
