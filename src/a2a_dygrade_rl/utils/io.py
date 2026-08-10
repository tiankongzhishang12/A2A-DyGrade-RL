"""文件型实验流水线的读写工具。"""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from typing import Any, Iterable

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - fallback exists for clean research workstations.
    yaml = None


def ensure_dir(path: str | Path) -> Path:
    target = Path(path)
    target.mkdir(parents=True, exist_ok=True)
    return target


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    with Path(path).open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_jsonl(path: str | Path, rows: Iterable[dict[str, Any]], overwrite: bool = False) -> Path:
    target = Path(path)
    if target.exists() and not overwrite:
        raise FileExistsError(f"输出已存在，若需覆盖请显式传入 overwrite: {target}")
    ensure_dir(target.parent)
    tmp = target.with_suffix(target.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    os.replace(tmp, target)
    return target


def read_yaml(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        text = handle.read()
    if yaml is not None:
        data = yaml.safe_load(text) or {}
    else:
        data = _read_simple_yaml(text)
    if not isinstance(data, dict):
        raise ValueError(f"YAML 顶层必须是对象: {path}")
    return data


def write_yaml(path: str | Path, data: dict[str, Any], overwrite: bool = False) -> Path:
    target = Path(path)
    if target.exists() and not overwrite:
        raise FileExistsError(f"输出已存在，若需覆盖请显式传入 overwrite: {target}")
    ensure_dir(target.parent)
    tmp = target.with_suffix(target.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        if yaml is not None:
            yaml.safe_dump(data, handle, allow_unicode=True, sort_keys=False)
        else:
            handle.write(_dump_simple_yaml(data))
    os.replace(tmp, target)
    return target


def write_csv(path: str | Path, rows: Iterable[dict[str, Any]], fieldnames: list[str], overwrite: bool = False) -> Path:
    target = Path(path)
    if target.exists() and not overwrite:
        raise FileExistsError(f"输出已存在，若需覆盖请显式传入 overwrite: {target}")
    ensure_dir(target.parent)
    tmp = target.with_suffix(target.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "") for name in fieldnames})
    os.replace(tmp, target)
    return target


def copy_config_snapshot(config_path: str | Path, run_id: str, output_root: str | Path = "outputs/runs") -> Path:
    config = read_yaml(config_path)
    target = Path(output_root) / run_id / "configs" / Path(config_path).name
    return write_yaml(target, config, overwrite=True)


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if value in {"true", "True"}:
        return True
    if value in {"false", "False"}:
        return False
    if value in {"null", "None", ""}:
        return None
    if value == "[]":
        return []
    if value == "{}":
        return {}
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def _read_simple_yaml(text: str) -> dict[str, Any]:
    root: dict[str, Any] = {}
    stack: list[tuple[int, Any]] = [(-1, root)]
    pending_key: list[tuple[int, dict[str, Any], str]] = []
    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        line = raw_line.strip()
        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if line.startswith("- "):
            value_text = line[2:].strip()
            if not isinstance(parent, list):
                if not pending_key:
                    raise ValueError("simple YAML 列表缺少父键")
                _, parent_map, key = pending_key.pop()
                new_list: list[Any] = []
                parent_map[key] = new_list
                stack.append((indent - 1, new_list))
                parent = new_list
            if ":" in value_text:
                key, value = value_text.split(":", 1)
                item: dict[str, Any] = {key.strip(): _parse_scalar(value)}
                parent.append(item)
                stack.append((indent, item))
            else:
                parent.append(_parse_scalar(value_text))
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if value:
            parent[key] = _parse_scalar(value)
        else:
            parent[key] = {}
            pending_key.append((indent, parent, key))
            stack.append((indent, parent[key]))
    return root


def _dump_simple_yaml(data: Any, indent: int = 0) -> str:
    lines: list[str] = []
    prefix = " " * indent
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, (dict, list)):
                lines.append(f"{prefix}{key}:")
                lines.append(_dump_simple_yaml(value, indent + 2).rstrip("\n"))
            else:
                lines.append(f"{prefix}{key}: {value}")
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                first = True
                for key, value in item.items():
                    marker = "- " if first else "  "
                    if isinstance(value, (dict, list)):
                        lines.append(f"{prefix}{marker}{key}:")
                        lines.append(_dump_simple_yaml(value, indent + 4).rstrip("\n"))
                    else:
                        lines.append(f"{prefix}{marker}{key}: {value}")
                    first = False
            else:
                lines.append(f"{prefix}- {item}")
    return "\n".join(lines) + "\n"


def read_csv(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_json(path: str | Path, data: Any, overwrite: bool = False) -> Path:
    target = Path(path)
    if target.exists() and not overwrite:
        raise FileExistsError(f"输出已存在，若需覆盖请显式传入 overwrite: {target}")
    ensure_dir(target.parent)
    tmp = target.with_suffix(target.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(data, handle, ensure_ascii=False, sort_keys=True, indent=2)
        handle.write("\n")
    os.replace(tmp, target)
    return target


def file_sha256(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    import hashlib

    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()
