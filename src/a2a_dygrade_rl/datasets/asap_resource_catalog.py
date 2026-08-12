"""ASAP-SAS 官方 DOCX 说明、Prompt/Rubric 与原始图片资产解析。"""

from __future__ import annotations

import hashlib
import mimetypes
import posixpath
import re
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import Any
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile

from a2a_dygrade_rl.utils.io import ensure_dir, file_sha256, write_json


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
W = f"{{{W_NS}}}"
A = f"{{{A_NS}}}"
R = f"{{{R_NS}}}"
PKG_REL = f"{{{PKG_REL_NS}}}"

_PROMPT_START = re.compile(r"^(?:reading passage|prompt)[\s—–-]", re.IGNORECASE)
_RUBRIC_START = re.compile(
    r"^(?:scoring rubric\b|rubric for\b|reading for information scoring and rubric\b)",
    re.IGNORECASE,
)
_DATASET_NUMBER = re.compile(r"Data\s*Set\s*#\s*(\d+)", re.IGNORECASE)

_IMAGE_MIME = {
    ".jpeg": "image/jpeg",
    ".jpg": "image/jpeg",
    ".png": "image/png",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
    ".webp": "image/webp",
    ".emf": "image/emf",
    ".wmf": "image/wmf",
}


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _paragraph_text(element: ET.Element) -> str:
    return "".join(node.text or "" for node in element.iter(W + "t")).strip()


def _ordered_document_lines(document_xml: bytes) -> list[str]:
    root = ET.fromstring(document_xml)
    body = root.find(W + "body")
    if body is None:
        return []
    lines: list[str] = []
    for child in body:
        if child.tag == W + "p":
            text = _paragraph_text(child)
            if text:
                lines.append(text)
            continue
        if child.tag != W + "tbl":
            continue
        for row in child.findall(W + "tr"):
            cells: list[str] = []
            for cell in row.findall(W + "tc"):
                parts = [_paragraph_text(paragraph) for paragraph in cell.findall(".//" + W + "p")]
                cells.append(" ".join(part for part in parts if part).strip())
            text = " | ".join(cells).strip(" |")
            if text:
                lines.append(text)
    return lines


def _metadata_value(lines: list[str], key: str) -> str:
    prefix = key.strip().lower().rstrip(":")
    for line in lines[:20]:
        normalized = line.strip()
        lowered = normalized.lower()
        if not lowered.startswith(prefix):
            continue
        value = normalized[len(key.rstrip(':')) :].lstrip(" :|")
        if value:
            return value.strip()
        if "|" in normalized:
            return normalized.split("|", 1)[1].strip()
    return ""


def _split_prompt_rubric(lines: list[str]) -> tuple[str, str]:
    prompt_index = next((index for index, line in enumerate(lines) if _PROMPT_START.search(line.strip())), None)
    if prompt_index is None:
        raise ValueError("DOCX 中未找到 Prompt/Reading Passage 起始标记")
    rubric_index = next(
        (index for index in range(prompt_index + 1, len(lines)) if _RUBRIC_START.search(lines[index].strip())),
        None,
    )
    if rubric_index is None:
        raise ValueError("DOCX 中未找到正式 Rubric 起始标记")
    prompt = "\n".join(line.strip() for line in lines[prompt_index:rubric_index] if line.strip()).strip()
    rubric = "\n".join(line.strip() for line in lines[rubric_index:] if line.strip()).strip()
    if not prompt or not rubric:
        raise ValueError("DOCX Prompt 或 Rubric 解析为空")
    return prompt, rubric


def _relationship_targets(docx: ZipFile) -> list[str]:
    rel_path = "word/_rels/document.xml.rels"
    if rel_path not in docx.namelist():
        return []
    root = ET.fromstring(docx.read(rel_path))
    targets: list[str] = []
    for rel in root.findall(PKG_REL + "Relationship"):
        rel_type = str(rel.attrib.get("Type", ""))
        target = str(rel.attrib.get("Target", ""))
        if not rel_type.endswith("/image") or not target:
            continue
        normalized = posixpath.normpath(posixpath.join("word", target))
        if normalized.startswith("../") or normalized.startswith("/"):
            continue
        targets.append(normalized)
    return targets


def _mime_type(name: str) -> str:
    suffix = PurePosixPath(name).suffix.lower()
    return _IMAGE_MIME.get(suffix) or mimetypes.guess_type(name)[0] or "application/octet-stream"


def _safe_write_bytes(path: Path, payload: bytes, *, overwrite: bool) -> None:
    ensure_dir(path.parent)
    if path.exists() and not overwrite:
        if file_sha256(path) == _sha256_bytes(payload):
            return
        raise FileExistsError(f"资源文件已存在且内容不同: {path}")
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)


def _extract_assets(
    docx: ZipFile,
    *,
    essay_set: str,
    docx_name: str,
    archive_name: str,
    resources_root: Path | None,
    overwrite: bool,
) -> list[dict[str, Any]]:
    if resources_root is None:
        return []
    targets = _relationship_targets(docx)
    if not targets:
        targets = sorted(name for name in docx.namelist() if name.startswith("word/media/"))
    unique_targets = list(dict.fromkeys(targets))
    assets: list[dict[str, Any]] = []
    prepared_root = resources_root.parent
    for index, member in enumerate(unique_targets, start=1):
        if member not in docx.namelist():
            raise ValueError(f"DOCX 图片关系指向不存在成员: {docx_name}!/{member}")
        payload = docx.read(member)
        suffix = PurePosixPath(member).suffix.lower() or ".bin"
        target = resources_root / "asap_sas" / "assets" / f"essay_set_{int(essay_set):02d}_image_{index:02d}{suffix}"
        _safe_write_bytes(target, payload, overwrite=overwrite)
        digest = _sha256_bytes(payload)
        try:
            relative_path = target.relative_to(prepared_root).as_posix()
        except ValueError as exc:  # pragma: no cover - caller contract prevents this.
            raise ValueError(f"资源路径不在 prepared root 内: {target}") from exc
        assets.append(
            {
                "asset_id": f"asap_sas_set_{int(essay_set):02d}_image_{index:02d}_{digest[:12]}",
                "relative_path": relative_path,
                "sha256": digest,
                "mime_type": _mime_type(member),
                "source_uri": f"zip://{archive_name}!/{docx_name}!/{member}",
                "original_filename": PurePosixPath(member).name,
                "byte_size": len(payload),
                "essay_set": essay_set,
            }
        )
    return assets


def build_asap_resource_catalog(
    raw_root: str | Path,
    *,
    resources_root: str | Path | None,
    required_essay_sets: list[str] | tuple[str, ...] | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    """解析 Data_Set_Descriptions.zip，必要时原样落盘图片并返回目录。"""

    root = Path(raw_root)
    archive_path = root / "Data_Set_Descriptions.zip"
    required = tuple(str(value) for value in (required_essay_sets or [str(index) for index in range(1, 11)]))
    target_root = Path(resources_root) if resources_root is not None else None
    catalog: dict[str, Any] = {
        "schema_version": "asap_resource_catalog_v2",
        "source_archive": {
            "name": archive_path.name,
            "path": archive_path.as_posix(),
            "sha256": "",
            "size_bytes": 0,
        },
        "required_essay_sets": list(required),
        "essay_sets": {},
        "issues": [],
    }
    if not archive_path.exists():
        catalog["issues"].append({"reason": "missing_description_archive", "detail": str(archive_path)})
        return catalog
    catalog["source_archive"].update(sha256=file_sha256(archive_path), size_bytes=archive_path.stat().st_size)
    try:
        with ZipFile(archive_path) as outer:
            for docx_name in sorted(outer.namelist()):
                match = _DATASET_NUMBER.search(docx_name)
                if match is None or not docx_name.lower().endswith(".docx"):
                    continue
                essay_set = str(int(match.group(1)))
                try:
                    docx_payload = outer.read(docx_name)
                    with ZipFile(BytesIO(docx_payload)) as docx:
                        document_path = "word/document.xml"
                        if document_path not in docx.namelist():
                            raise ValueError("DOCX 缺少 word/document.xml")
                        lines = _ordered_document_lines(docx.read(document_path))
                        prompt, rubric = _split_prompt_rubric(lines)
                        assets = _extract_assets(
                            docx,
                            essay_set=essay_set,
                            docx_name=docx_name,
                            archive_name=archive_path.name,
                            resources_root=target_root,
                            overwrite=overwrite,
                        )
                        catalog["essay_sets"][essay_set] = {
                            "essay_set": essay_set,
                            "docx_name": docx_name,
                            "document_sha256": _sha256_bytes(docx_payload),
                            "subject": _metadata_value(lines, "Subject") or "unknown",
                            "rubric_range": _metadata_value(lines, "Rubric range"),
                            "prompt": prompt,
                            "rubric": rubric,
                            "source_assets": assets,
                        }
                except (BadZipFile, ET.ParseError, KeyError, ValueError) as exc:
                    catalog["issues"].append(
                        {"essay_set": essay_set, "docx_name": docx_name, "reason": "description_parse_failed", "detail": str(exc)}
                    )
    except BadZipFile as exc:
        catalog["issues"].append({"reason": "invalid_description_archive", "detail": str(exc)})
        return catalog

    for essay_set in required:
        if essay_set not in catalog["essay_sets"]:
            catalog["issues"].append(
                {"essay_set": essay_set, "reason": "missing_required_essay_set_description", "detail": archive_path.name}
            )

    catalog["resource_count"] = sum(
        len(record.get("source_assets", [])) for record in catalog["essay_sets"].values()
    )
    if target_root is not None:
        catalog_path = target_root / "asap_sas" / "resource_catalog.json"
        write_json(catalog_path, catalog, overwrite=overwrite)
        catalog["catalog_path"] = catalog_path.relative_to(target_root.parent).as_posix()
        catalog["catalog_sha256"] = file_sha256(catalog_path)
    return catalog