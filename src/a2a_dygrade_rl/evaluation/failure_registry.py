"""失败结果注册与不可删除的 JSONL 持久化。"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from a2a_dygrade_rl.utils.io import write_jsonl


@dataclass(frozen=True)
class FailureRecord:
    run_id: str
    stage: str
    entity_id: str
    status: str
    reason: str
    split: str = ""
    budget_id: str = ""
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class FailureRegistry:
    def __init__(self) -> None:
        self._records: list[FailureRecord] = []

    @property
    def records(self) -> tuple[FailureRecord, ...]:
        return tuple(self._records)

    def add(self, record: FailureRecord) -> None:
        if not record.reason.strip():
            raise ValueError("失败记录必须包含 reason")
        self._records.append(record)

    def write(self, path: str | Path, *, overwrite: bool = False) -> Path:
        return write_jsonl(path, (record.to_dict() for record in self._records), overwrite=overwrite)
