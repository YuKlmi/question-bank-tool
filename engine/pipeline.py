# -*- coding: utf-8 -*-
"""解析流水线编排：归一化 → 标记 → 回填 → 校验。"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Optional

from .attach import answers as answer_backfill
from .attach import attacher
from .annotate import markers
from .grading import grade_mode_of, infer_question_type
from .imagestore import ImageStore
from .models import ParseResult
from .normalize import load_document
from .rules import Template
from .verify import verifier

# 按扩展名推断默认模板
DEFAULT_TEMPLATE_BY_EXT = {
    ".pdf": "pdf-consolidated",
    ".doc": "docx-mixed",
    ".docx": "docx-mixed",
}


def guess_template(path: Path) -> str:
    return DEFAULT_TEMPLATE_BY_EXT.get(Path(path).suffix.lower(), "pdf-consolidated")


def parse(
    path: Path,
    data_dir: Path,
    template_id: Optional[str] = None,
    doc_name: Optional[str] = None,
) -> ParseResult:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {path}")

    template_id = template_id or guess_template(path)
    template = Template.by_id(template_id)

    data_dir = Path(data_dir)
    store = ImageStore(data_dir / "media")
    # 用文件指纹做图片目录，重复导入不会产生新副本
    doc_key = _doc_key(path)

    norm = load_document(path, store, doc_key=doc_key,
                         convert_dir=data_dir / "_converted")

    # 第 2 段：标记
    events = markers.extract(norm.blocks, template)
    event_counts = markers.counts(events)

    # 第 3 段：回填
    att = attacher.attach(events, doc_id=0)
    answer_stats = answer_backfill.backfill_answers(
        att.questions, att.answers,
        next_seq=(max((q.seq for q in att.questions), default=-1) + 1),
        doc_id=0,
        q_start=att.q_start,
    )

    # 题型与判分方式（依赖选项，必须在回填之后）
    for q in att.questions:
        if not q.stem.strip() and not q.options:
            # 图片占位题：题型无从判断，等用户录入后再定
            continue
        q.type = infer_question_type(q.stem, len(q.options))
        q.grade_mode = grade_mode_of(q.type)

    # 第 4 段：校验
    report = verifier.verify(
        questions=att.questions,
        groups=att.groups,
        event_counts=event_counts,
        answer_stats=answer_stats,
        attach_stats=att.stats,
        block_count=len(norm.blocks),
        extra_warnings=norm.warnings,
    )

    result = ParseResult(
        doc_name=doc_name or path.name,
        orig_type=norm.orig_type,
        page_count=norm.page_count or None,
        groups=att.groups,
        questions=att.questions,
        template_id=template_id,
        report=report,
    )
    result.report["imageCount"] = sum(len(q.images) for q in att.questions)
    result.report["commentCount"] = len(norm.comments)
    return result


def _doc_key(path: Path) -> str:
    h = hashlib.sha1()
    h.update(path.name.encode("utf-8", "ignore"))
    st = path.stat()
    h.update(str(st.st_size).encode())
    return h.hexdigest()[:12]
