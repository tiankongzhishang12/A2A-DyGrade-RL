"""原始公开数据下载与授权文件检查。"""

from __future__ import annotations

import shutil
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from a2a_dygrade_rl.utils.io import ensure_dir, read_yaml


def download_sources(manifest_path: str | Path, overwrite: bool = False) -> list[dict[str, str]]:
    manifest = read_yaml(manifest_path)
    results: list[dict[str, str]] = []
    for source in manifest.get("sources", []):
        name = str(source["name"])
        target_dir = ensure_dir(source["target_dir"])
        urls = source.get("urls") or []
        if not urls:
            results.append({"name": name, "status": str(source.get("status", "manual")), "target_dir": str(target_dir), "message": str(source.get("note", ""))})
            continue
        for url in urls:
            if str(url).startswith("hf://"):
                results.append({"name": name, "status": "external_cli", "target_dir": str(target_dir), "message": f"请使用 Hugging Face CLI 下载: {url}"})
                continue
            filename = Path(urlparse(url).path).name
            if not filename:
                raise ValueError(f"URL 缺少文件名: {url}")
            target = target_dir / filename
            if target.exists() and not overwrite:
                results.append({"name": name, "status": "exists", "target_dir": str(target_dir), "message": str(target)})
                continue
            tmp = target.with_suffix(target.suffix + ".tmp")
            with urllib.request.urlopen(url) as response, tmp.open("wb") as handle:
                shutil.copyfileobj(response, handle)
            tmp.replace(target)
            results.append({"name": name, "status": "downloaded", "target_dir": str(target_dir), "message": str(target)})
    return results


def check_expected_files(manifest_path: str | Path) -> list[dict[str, str]]:
    manifest = read_yaml(manifest_path)
    results: list[dict[str, str]] = []
    for source in manifest.get("sources", []):
        target_dir = Path(source["target_dir"])
        patterns = source.get("expected_files") or ["*"]
        matches = []
        for pattern in patterns:
            matches.extend(target_dir.glob(pattern) if target_dir.exists() else [])
        results.append(
            {
                "name": str(source["name"]),
                "status": "ready" if matches else "missing",
                "target_dir": str(target_dir),
                "message": f"{len(matches)} file(s)",
            }
        )
    return results
