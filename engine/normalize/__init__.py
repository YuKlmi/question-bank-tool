# -*- coding: utf-8 -*-
"""归一化层：把 .doc / .docx / .pdf 统一成 Block 块流。

对外只暴露 load_document()，调用方不需要关心来源格式。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

from ..imagestore import ImageStore
from ..models import Block

SUPPORTED = {".doc", ".docx", ".pdf"}


@dataclass
class NormResult:
    blocks: List[Block] = field(default_factory=list)
    page_count: int = 0
    orig_type: str = ""
    comments: List[Dict[str, str]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


def load_document(
    path: Path,
    store: ImageStore,
    doc_key: str = "",
    convert_dir: Path | None = None,
) -> NormResult:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED:
        raise ValueError(f"不支持的文件格式: {suffix}（支持 .doc/.docx/.pdf）")

    result = NormResult(orig_type=suffix.lstrip("."))

    if suffix == ".pdf":
        from . import pdf as pdf_norm

        blocks, pages = pdf_norm.load(path, store, doc_key)
        result.blocks = blocks
        result.page_count = pages
        return result

    if suffix == ".doc":
        from . import doc as doc_norm

        result.comments = doc_norm.read_doc_comments(path)
        converted = doc_norm.convert_to_docx(path, convert_dir)
        result.warnings.append(f"已通过 Word 转换: {converted.name}")
        path = converted

    from . import docx as docx_norm

    blocks, pages = docx_norm.load(path, store, doc_key)
    result.blocks = blocks
    result.page_count = pages
    if not result.comments:
        result.comments = docx_norm.read_comments(path)
    return result
