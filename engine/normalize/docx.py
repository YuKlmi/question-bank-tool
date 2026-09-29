# -*- coding: utf-8 -*-
"""DOCX 归一化。

产出「一段落一 Block」，保留段落样式（样例 A 的样式实测有 5 种且混用，
因此样式只作为弱线索，不能作为切题依据）。
图片按其在段落中的出现顺序插入块流，保证与正文的相对位置正确。
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import Dict, List, Tuple

from docx import Document
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

from ..imagestore import ImageStore, sniff_ext
from ..models import Block, ROLE_EXPLANATION


def _iter_body(doc: Document):
    """按文档真实顺序遍历段落与表格（doc.paragraphs 会丢掉表格与顺序）。"""
    body = doc.element.body
    for child in body.iterchildren():
        if child.tag == qn("w:p"):
            yield Paragraph(child, doc)
        elif child.tag == qn("w:tbl"):
            yield Table(child, doc)


# 命名空间：python-docx 的 nsmap 里没有 vml 前缀，这里统一用字面 URI
NS_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
NS_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_V = "urn:schemas-microsoft-com:vml"

TAG_DRAWING = f"{{{NS_W}}}drawing"
TAG_BLIP = f"{{{NS_A}}}blip"
TAG_VML_IMAGEDATA = f"{{{NS_V}}}imagedata"
ATTR_EMBED = f"{{{NS_R}}}embed"
ATTR_LINK = f"{{{NS_R}}}link"
ATTR_RID = f"{{{NS_R}}}id"
TAG_W_T = f"{{{NS_W}}}t"


def _paragraph_image_rids(par: Paragraph) -> List[str]:
    """段落内按顺序出现的图片关系 id（含浮动与内联）。"""
    rids: List[str] = []
    for drawing in par._element.iter(TAG_DRAWING):
        for blip in drawing.iter(TAG_BLIP):
            rid = blip.get(ATTR_EMBED) or blip.get(ATTR_LINK)
            if rid:
                rids.append(rid)
    # 旧式 VML 图片
    for imagedata in par._element.iter(TAG_VML_IMAGEDATA):
        rid = imagedata.get(ATTR_RID)
        if rid:
            rids.append(rid)
    return rids


def load(path: Path, store: ImageStore, doc_key: str = "") -> Tuple[List[Block], int]:
    doc = Document(str(path))
    blocks: List[Block] = []
    order = 0

    for element in _iter_body(doc):
        if isinstance(element, Table):
            rows = []
            for row in element.rows:
                rows.append(" | ".join(c.text.replace("\n", " ").strip() for c in row.cells))
            text = "\n".join(rows).strip()
            if text:
                blocks.append(Block(order=order, text=text, style="Table"))
                order += 1
            continue

        par = element
        # 段落内图片优先按出现顺序落盘
        images: List[Block] = []
        for rid in _paragraph_image_rids(par):
            try:
                part = par.part.related_parts[rid]
            except KeyError:
                continue
            blob = part.blob
            ext, _ = sniff_ext(blob, Path(part.partname).suffix.lstrip(".") or "png")
            rel = store.save(blob, ext, doc_key)
            images.append(Block(order=0, text="", is_image=True, image_path=rel))

        text = par.text.rstrip()
        if text:
            blocks.append(Block(order=order, text=text, style=par.style.name if par.style else None))
            order += 1
        for img in images:
            img.order = order
            blocks.append(img)
            order += 1

    for i, b in enumerate(blocks):
        b.order = i
    return blocks, 0


def read_comments(path: Path) -> List[Dict[str, str]]:
    """读取 Word 原始批注（word/comments.xml）。样例 A 实测为 0，但需支持。"""
    out: List[Dict[str, str]] = []
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        if "word/comments.xml" not in names:
            return out
        from lxml import etree

        root = etree.fromstring(z.read("word/comments.xml"))
        for comment in root.findall(f"{{{NS_W}}}comment"):
            texts = [t.text or "" for t in comment.iter(TAG_W_T)]
            out.append({
                "author": comment.get(f"{{{NS_W}}}author", ""),
                "text": "".join(texts).strip(),
                "scopeText": "",
            })
    return out


def embedded_images(path: Path) -> int:
    """统计 docx 包内图片数（用于解析报告）。"""
    with zipfile.ZipFile(path) as z:
        return len([n for n in z.namelist() if n.startswith("word/media/")])
