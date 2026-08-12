"""Dataset Semantic V2 loader、quarantine 与 manifest 公共契约。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from a2a_dygrade_rl.utils.io import file_sha256


QUARANTINE_FIELDS = [
    "dataset",
    "source_file",
    "source_record_id",
    "reason",
    "detail",
    "transform_version",
]


@dataclass
class DatasetLoadResult:
    dataset: str
    items: list[dict[str, Any]] = field(default_factory=list)
    quarantine: list[dict[str, Any]] = field(default_factory=list)
    resources: list[dict[str, Any]] = field(default_factory=list)
    source_files: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)

    def finalize(self) -> "DatasetLoadResult":
        self.summary = {
            **self.summary,
            "dataset": self.dataset,
            "accepted_item_count": len(self.items),
            "quarantine_count": len(self.quarantine),
            "resource_count": len(self.resources),
            "source_file_count": len(self.source_files),
        }
        return self

    def manifest_entry(self) -> dict[str, Any]:
        return {
            "dataset": self.dataset,
            "summary": dict(self.summary),
            "source_files": [dict(record) for record in self.source_files],
            "resource_ids": sorted(str(record.get("asset_id", "")) for record in self.resources),
        }


def quarantine_record(
    *,
    dataset: str,
    source_file: str,
    source_record_id: str,
    reason: str,
    detail: str = "",
    transform_version: str = "dataset_semantic_v2",
) -> dict[str, Any]:
    return {
        "dataset": str(dataset),
        "source_file": str(source_file),
        "source_record_id": str(source_record_id),
        "reason": str(reason),
        "detail": str(detail),
        "transform_version": str(transform_version),
    }


def source_file_record(path: str | Path, *, role: str) -> dict[str, Any]:
    source = Path(path)
    return {
        "path": str(source.as_posix()),
        "name": source.name,
        "role": str(role),
        "size_bytes": source.stat().st_size,
        "sha256": file_sha256(source),
    }