# -*- coding: utf-8 -*-
"""图片落盘与复用。

图片与数据库分离存储（设计原则），DB 里只存相对路径。
同一张图（按内容哈希）只落一次，避免重复导入时磁盘膨胀。
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Optional, Tuple


class ImageStore:
    def __init__(self, media_dir: Path):
        self.media_dir = Path(media_dir)
        self.media_dir.mkdir(parents=True, exist_ok=True)
        self._seen: dict[str, str] = {}

    def save(self, data: bytes, ext: str, doc_key: str = "") -> str:
        """写入图片，返回相对 media_dir 的路径（POSIX 风格）。"""
        digest = hashlib.sha1(data).hexdigest()[:20]
        ext = (ext or "png").lower().lstrip(".")
        if ext == "jpeg":
            ext = "jpg"
        rel = f"{doc_key}/{digest}.{ext}" if doc_key else f"{digest}.{ext}"

        cached = self._seen.get(digest)
        if cached:
            return cached

        target = self.media_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.write_bytes(data)
        self._seen[digest] = rel
        return rel

    def rename_scope(self, old_rel: str, doc_key: str) -> str:
        """把已落盘的图片移动到文档专属目录下（导入后才拿到 docId 时使用）。"""
        src = self.media_dir / old_rel
        if not src.exists():
            return old_rel
        name = src.name
        new_rel = f"{doc_key}/{name}"
        dst = self.media_dir / new_rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src != dst:
            dst.write_bytes(src.read_bytes())
            src.unlink()
        return new_rel

    @staticmethod
    def abs_path(media_dir: Path, rel: str) -> Optional[Path]:
        if not rel:
            return None
        p = Path(media_dir) / rel
        return p if p.exists() else None


def sniff_ext(data: bytes, fallback: str = "png") -> Tuple[str, bool]:
    """按文件头判断真实格式，返回 (扩展名, 是否识别成功)。"""
    if data[:3] == b"\xff\xd8\xff":
        return "jpg", True
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png", True
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif", True
    if data[:2] == b"BM":
        return "bmp", True
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp", True
    if data[:4] == b"II*\x00" or data[:4] == b"MM\x00*":
        return "tiff", True
    return fallback, False
