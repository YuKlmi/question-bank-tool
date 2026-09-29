# -*- coding: utf-8 -*-
"""PDF 归一化。

产出「一行一 Block」的细粒度块流，并保留 page / bbox：
- 细粒度是切题的前提（题号、选项标记都出现在行首）
- bbox 是图片归属、原文定位的基础
- 按 (page, y0, x0) 排序可让正文与图片正确交错
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

import pymupdf

from ..imagestore import ImageStore, sniff_ext
from ..models import Block


def load(
    path: Path,
    store: ImageStore,
    doc_key: str = "",
    sort_blocks: bool = True,
) -> Tuple[List[Block], int]:
    doc = pymupdf.open(str(path))
    raw: List[Tuple[int, float, float, Block]] = []

    for pno in range(doc.page_count):
        page = doc[pno]
        page_no = pno + 1
        data = page.get_text("dict")

        for block in data.get("blocks", []):
            if block.get("type") == 1:
                # 图片块：抽出原图落盘
                blob = block.get("image")
                if not blob:
                    continue
                ext, _ = sniff_ext(blob, block.get("ext") or "png")
                rel = store.save(blob, ext, doc_key)
                bbox = tuple(block.get("bbox") or (0, 0, 0, 0))
                raw.append((
                    page_no, bbox[1], bbox[0],
                    Block(
                        order=0, text="", page=page_no, bbox=bbox,
                        is_image=True, image_path=rel,
                        image_size=(block.get("width"), block.get("height")),
                    ),
                ))
                continue

            # 文本块：拆成行
            for line in block.get("lines", []):
                text = "".join(sp.get("text", "") for sp in line.get("spans", []))
                if not text.strip():
                    continue
                bbox = tuple(line.get("bbox") or (0, 0, 0, 0))
                raw.append((
                    page_no, bbox[1], bbox[0],
                    Block(order=0, text=text.rstrip(), page=page_no, bbox=bbox),
                ))

    if sort_blocks:
        raw.sort(key=lambda item: (item[0], round(item[1], 1), round(item[2], 1)))

    blocks = [item[3] for item in raw]
    for i, b in enumerate(blocks):
        b.order = i

    page_count = doc.page_count
    doc.close()
    return blocks, page_count


def page_size(path: Path, page_no: int) -> Tuple[float, float]:
    """取某页尺寸，供界面做坐标映射（bbox → 页面百分比）。"""
    doc = pymupdf.open(str(path))
    try:
        rect = doc[page_no - 1].rect
        return rect.width, rect.height
    finally:
        doc.close()
