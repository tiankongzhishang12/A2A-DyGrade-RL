"""自托管多模态请求的 source asset 校验与确定性转换。"""

from __future__ import annotations

import base64
import binascii
import hashlib
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
SUPPORTED_SOURCE_MIME = {"image/jpeg", "image/tiff"}


@dataclass(frozen=True)
class PreparedAsset:
    asset_id: str
    source_path: Path
    source_mime_type: str
    source_byte_size: int
    source_sha256: str
    source_width: int
    source_height: int
    sent_mime_type: str
    sent_bytes: bytes
    sent_sha256: str
    sent_width: int
    sent_height: int
    transform: str
    source_uri: str

    def audit_dict(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "source_relative_path": self.source_path.as_posix(),
            "source_mime_type": self.source_mime_type,
            "source_byte_size": self.source_byte_size,
            "source_sha256": self.source_sha256,
            "source_width": self.source_width,
            "source_height": self.source_height,
            "sent_mime_type": self.sent_mime_type,
            "sent_byte_size": len(self.sent_bytes),
            "sent_sha256": self.sent_sha256,
            "sent_width": self.sent_width,
            "sent_height": self.sent_height,
            "transform": self.transform,
            "source_uri": self.source_uri,
        }

    def chat_content_block(self) -> dict[str, Any]:
        encoded = base64.b64encode(self.sent_bytes).decode("ascii")
        return {
            "type": "image_url",
            "image_url": {"url": f"data:{self.sent_mime_type};base64,{encoded}"},
        }


def prepare_source_assets(
    source_assets: list[dict[str, Any]] | None,
    *,
    prepared_root: str | Path,
) -> list[PreparedAsset]:
    root = Path(prepared_root).resolve()
    if not root.is_dir():
        raise ValueError(f"prepared_root 不存在或不是目录: {root}")
    prepared: list[PreparedAsset] = []
    for raw in source_assets or []:
        prepared.append(_prepare_one(dict(raw), root=root))
    return prepared


def _prepare_one(raw: dict[str, Any], *, root: Path) -> PreparedAsset:
    relative = str(raw.get("relative_path", "")).strip().replace("\\", "/")
    if not relative or Path(relative).is_absolute():
        raise ValueError("source asset relative_path 必须是非空相对路径")
    target = (root / relative).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"source asset 路径越过 prepared_root: {relative}") from exc
    if not target.is_file():
        raise FileNotFoundError(f"source asset 不存在: {relative}")

    source_bytes = target.read_bytes()
    expected_size = int(raw.get("byte_size", len(source_bytes)))
    if len(source_bytes) != expected_size:
        raise ValueError(f"source asset byte_size 不匹配: {relative}")
    actual_sha = hashlib.sha256(source_bytes).hexdigest()
    expected_sha = str(raw.get("sha256", "")).lower()
    if not expected_sha or actual_sha != expected_sha:
        raise ValueError(f"source asset sha256 不匹配: {relative}")

    source_mime = str(raw.get("mime_type", "")).lower().strip()
    if source_mime not in SUPPORTED_SOURCE_MIME:
        raise ValueError(f"不支持的 source asset MIME: {source_mime}")
    detected_mime = detect_image_mime(source_bytes)
    if detected_mime != source_mime:
        raise ValueError(
            f"source asset MIME与实际字节不匹配: declared={source_mime}, detected={detected_mime}"
        )

    if source_mime == "image/jpeg":
        width, height = jpeg_dimensions(source_bytes)
        sent = source_bytes
        sent_mime = "image/jpeg"
        transform = "identity"
    else:
        width, height, rgb = decode_tiff_rgb(source_bytes)
        sent = encode_png_rgb(width, height, rgb)
        sent_mime = "image/png"
        transform = "tiff_lzw_to_png_lossless"

    return PreparedAsset(
        asset_id=str(raw.get("asset_id", target.stem)),
        source_path=Path(relative),
        source_mime_type=source_mime,
        source_byte_size=len(source_bytes),
        source_sha256=actual_sha,
        source_width=width,
        source_height=height,
        sent_mime_type=sent_mime,
        sent_bytes=sent,
        sent_sha256=hashlib.sha256(sent).hexdigest(),
        sent_width=width,
        sent_height=height,
        transform=transform,
        source_uri=str(raw.get("source_uri", "")),
    )


def detect_image_mime(data: bytes) -> str:
    if len(data) >= 3 and data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if len(data) >= 4 and data[:4] in {b"II*\x00", b"MM\x00*"}:
        return "image/tiff"
    raise ValueError("source asset字节不是受支持的JPEG或TIFF")


def jpeg_dimensions(data: bytes) -> tuple[int, int]:
    if len(data) < 4 or data[:2] != b"\xff\xd8":
        raise ValueError("非法 JPEG 文件头")
    index = 2
    while index + 4 <= len(data):
        if data[index] != 0xFF:
            index += 1
            continue
        while index < len(data) and data[index] == 0xFF:
            index += 1
        if index >= len(data):
            break
        marker = data[index]
        index += 1
        if marker in {0xD8, 0xD9} or 0xD0 <= marker <= 0xD7:
            continue
        if index + 2 > len(data):
            break
        length = struct.unpack(">H", data[index : index + 2])[0]
        if length < 2 or index + length > len(data):
            raise ValueError("JPEG segment 长度非法")
        if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
            if length < 7:
                raise ValueError("JPEG SOF segment 过短")
            height, width = struct.unpack(">HH", data[index + 3 : index + 7])
            if width <= 0 or height <= 0:
                raise ValueError("JPEG 尺寸非法")
            return width, height
        index += length
    raise ValueError("JPEG 缺少 SOF 尺寸标记")


def decode_tiff_rgb(data: bytes) -> tuple[int, int, bytes]:
    if len(data) < 8 or data[:2] not in {b"II", b"MM"}:
        raise ValueError("非法 TIFF 文件头")
    endian = "<" if data[:2] == b"II" else ">"
    magic, ifd_offset = struct.unpack_from(endian + "HI", data, 2)
    if magic != 42:
        raise ValueError("不支持的 TIFF magic")
    entries = _read_tiff_ifd(data, endian=endian, offset=ifd_offset)

    width = _single_int(entries, 256, endian=endian)
    height = _single_int(entries, 257, endian=endian)
    bits = _int_values(entries, 258, endian=endian)
    compression = _single_int(entries, 259, endian=endian)
    photometric = _single_int(entries, 262, endian=endian)
    strip_offsets = _int_values(entries, 273, endian=endian)
    samples_per_pixel = _single_int(entries, 277, endian=endian)
    rows_per_strip = _single_int(entries, 278, endian=endian)
    strip_byte_counts = _int_values(entries, 279, endian=endian)
    planar = _single_int(entries, 284, endian=endian, default=1)
    predictor = _single_int(entries, 317, endian=endian, default=1)

    if width <= 0 or height <= 0:
        raise ValueError("TIFF 尺寸非法")
    if bits != [8, 8, 8] or samples_per_pixel != 3 or photometric != 2 or planar != 1:
        raise ValueError("仅支持8-bit chunky RGB TIFF")
    if compression not in {1, 5}:
        raise ValueError(f"仅支持未压缩或LZW TIFF，实际compression={compression}")
    if predictor not in {1, 2}:
        raise ValueError(f"不支持的 TIFF predictor={predictor}")
    if len(strip_offsets) != len(strip_byte_counts) or not strip_offsets:
        raise ValueError("TIFF strip offsets/counts 不合法")

    row_bytes = width * samples_per_pixel
    output = bytearray()
    rows_done = 0
    for strip_index, (offset, byte_count) in enumerate(zip(strip_offsets, strip_byte_counts)):
        if offset < 0 or byte_count < 0 or offset + byte_count > len(data):
            raise ValueError("TIFF strip 超出文件范围")
        encoded = data[offset : offset + byte_count]
        rows = min(rows_per_strip, height - rows_done)
        expected = rows * row_bytes
        decoded = encoded if compression == 1 else _decode_tiff_lzw(encoded)
        if len(decoded) < expected:
            raise ValueError(f"TIFF strip {strip_index} 解码长度不足")
        strip = bytearray(decoded[:expected])
        if predictor == 2:
            for row in range(rows):
                base = row * row_bytes
                for pos in range(base + samples_per_pixel, base + row_bytes):
                    strip[pos] = (strip[pos] + strip[pos - samples_per_pixel]) & 0xFF
        output.extend(strip)
        rows_done += rows
    if rows_done != height or len(output) != width * height * 3:
        raise ValueError("TIFF strip 未覆盖完整图像")
    return width, height, bytes(output)


def _read_tiff_ifd(data: bytes, *, endian: str, offset: int) -> dict[int, tuple[int, int, bytes]]:
    if offset < 0 or offset + 2 > len(data):
        raise ValueError("TIFF IFD offset 非法")
    count = struct.unpack_from(endian + "H", data, offset)[0]
    entries: dict[int, tuple[int, int, bytes]] = {}
    type_sizes = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 7: 1}
    for index in range(count):
        start = offset + 2 + index * 12
        if start + 12 > len(data):
            raise ValueError("TIFF IFD entry 越界")
        tag, value_type, value_count = struct.unpack_from(endian + "HHI", data, start)
        if value_type not in type_sizes:
            continue
        total = type_sizes[value_type] * value_count
        value_field = data[start + 8 : start + 12]
        if total <= 4:
            raw = value_field[:total]
        else:
            value_offset = struct.unpack(endian + "I", value_field)[0]
            if value_offset + total > len(data):
                raise ValueError(f"TIFF tag {tag} value 越界")
            raw = data[value_offset : value_offset + total]
        entries[tag] = (value_type, value_count, raw)
    return entries


def _int_values(
    entries: dict[int, tuple[int, int, bytes]],
    tag: int,
    *,
    endian: str,
) -> list[int]:
    if tag not in entries:
        raise ValueError(f"TIFF 缺少 tag {tag}")
    value_type, count, raw = entries[tag]
    if value_type == 3:
        return list(struct.unpack(endian + "H" * count, raw))
    if value_type == 4:
        return list(struct.unpack(endian + "I" * count, raw))
    raise ValueError(f"TIFF tag {tag} 不是整数类型")


def _single_int(
    entries: dict[int, tuple[int, int, bytes]],
    tag: int,
    *,
    endian: str,
    default: int | None = None,
) -> int:
    if tag not in entries:
        if default is not None:
            return default
        raise ValueError(f"TIFF 缺少 tag {tag}")
    values = _int_values(entries, tag, endian=endian)
    if len(values) != 1:
        raise ValueError(f"TIFF tag {tag} 必须为标量")
    return int(values[0])


def _decode_tiff_lzw(data: bytes) -> bytes:
    clear_code = 256
    eoi_code = 257
    dictionary: dict[int, bytes] = {index: bytes([index]) for index in range(256)}
    code_size = 9
    next_code = 258
    bit_position = 0
    previous: bytes | None = None
    output = bytearray()

    def read_code(width: int) -> int | None:
        nonlocal bit_position
        if bit_position + width > len(data) * 8:
            return None
        value = 0
        for _ in range(width):
            byte_index = bit_position // 8
            shift = 7 - (bit_position % 8)
            value = (value << 1) | ((data[byte_index] >> shift) & 1)
            bit_position += 1
        return value

    while True:
        code = read_code(code_size)
        if code is None:
            break
        if code == clear_code:
            dictionary = {index: bytes([index]) for index in range(256)}
            code_size = 9
            next_code = 258
            previous = None
            continue
        if code == eoi_code:
            break
        if code in dictionary:
            entry = dictionary[code]
        elif code == next_code and previous is not None:
            entry = previous + previous[:1]
        else:
            raise ValueError(f"TIFF LZW 非法code={code} next={next_code}")
        output.extend(entry)
        if previous is not None and next_code < 4096:
            dictionary[next_code] = previous + entry[:1]
            next_code += 1
            if code_size < 12 and next_code == (1 << code_size) - 1:
                code_size += 1
        previous = entry
    return bytes(output)


def encode_png_rgb(width: int, height: int, rgb: bytes) -> bytes:
    if width <= 0 or height <= 0 or len(rgb) != width * height * 3:
        raise ValueError("PNG RGB输入尺寸不一致")
    scanlines = b"".join(
        b"\x00" + rgb[row * width * 3 : (row + 1) * width * 3]
        for row in range(height)
    )
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return PNG_SIGNATURE + _png_chunk(b"IHDR", ihdr) + _png_chunk(b"IDAT", zlib.compress(scanlines, 9)) + _png_chunk(b"IEND", b"")


def png_dimensions(data: bytes) -> tuple[int, int]:
    if len(data) < 24 or not data.startswith(PNG_SIGNATURE) or data[12:16] != b"IHDR":
        raise ValueError("非法 PNG")
    return struct.unpack(">II", data[16:24])


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    crc = binascii.crc32(kind)
    crc = binascii.crc32(payload, crc) & 0xFFFFFFFF
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", crc)
