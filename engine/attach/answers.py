# -*- coding: utf-8 -*-
"""答案回填。

分层匹配，逐层降级，**每一层都要么可确定、要么明确标记待确认**：
  L1  (大题组, 题号) 唯一命中      → 直接回填，答案来源 doc
  L2  题号在全文唯一               → 直接回填（样例 B 属此类，题号 1–135 不重复）
  L3  题号有歧义但能按位置收敛     → **就近回填**：取「出现在该答案之前、
                                      且题号相同」的最后一道题，来源标
                                      doc_inferred，置信度压低，**必须人工确认**
  L4  以上都无法收敛               → 不回填，记冲突，进人工队列

L3 是实测催生的：样例 A 的答案紧跟在题目之后（而不是集中在文末），
且题号在大题组间重置（重复率 63.2%），单靠题号无法归属。
用「就近」这一版式事实收敛，比直接丢弃更有用；但绝不冒充确定结果。
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from ..models import (
    AS_DOC, AS_DOC_INFERRED, Explanation, Question, ROLE_EXPLANATION,
    RS_PENDING, RS_PENDING_INPUT, SS_IMAGE,
)


def backfill_answers(
    questions: List[Question],
    answers: List["object"],
    next_seq: int,
    doc_id: int,
    q_start: Optional[Dict[int, int]] = None,
    create_missing_slots: bool = True,
) -> Dict[str, int]:
    from .attacher import AnswerRec

    q_start = q_start or {}
    stats = {
        "matched": 0,
        "matchedUnique": 0,
        "matchedProximity": 0,
        "conflict": 0,
        "createdSlot": 0,
        "unmatched": 0,
    }

    by_gn: Dict[Tuple[Optional[int], int], List[Question]] = {}
    by_no: Dict[int, List[Question]] = {}
    for q in questions:
        if q.display_no is None:
            continue
        by_no.setdefault(q.display_no, []).append(q)
        by_gn.setdefault((q.group_seq, q.display_no), []).append(q)

    # 题号是否全文唯一（决定 L2 是否可用）
    number_unique = all(len(v) == 1 for v in by_no.values())

    pending_answers: List[AnswerRec] = []

    for rec in answers:  # type: ignore[assignment]
        target: Optional[Question] = None
        source = AS_DOC

        # L1：同大题组内唯一
        cands = by_gn.get((rec.group_seq, rec.no)) or []
        if len(cands) == 1:
            target = cands[0]
            stats["matchedUnique"] += 1

        # L2：题号全文唯一
        if target is None and number_unique:
            cands = by_no.get(rec.no) or []
            if len(cands) == 1:
                target = cands[0]
                stats["matchedUnique"] += 1

        # L3：就近回填（取该答案之前、题号相同的最后一题）
        if target is None:
            cands = [
                q for q in by_no.get(rec.no, [])
                if q_start.get(id(q), -1) < rec.order
            ]
            if cands:
                target = max(cands, key=lambda q: q_start.get(id(q), -1))
                source = AS_DOC_INFERRED
                stats["matchedProximity"] += 1

        if target is None:
            stats["conflict" if len(by_no.get(rec.no) or []) > 1 else "unmatched"] += 1
            if create_missing_slots and number_unique:
                pending_answers.append(rec)
            continue

        _apply(target, rec, source)
        stats["matched"] += 1

    # 有答案但无题目槽位（如样例 B 的题 135）→ 补位，避免答案丢失
    for rec in pending_answers:
        ph = Question(
            doc_id=doc_id,
            seq=next_seq,
            display_no=rec.no,
            stem="",
            raw_text="（原文未检出该题题面，仅回填了答案与解析）",
            stem_source=SS_IMAGE,
            review_state=RS_PENDING_INPUT,
        )
        next_seq += 1
        _apply(ph, rec, AS_DOC)
        questions.append(ph)
        by_no.setdefault(rec.no, []).append(ph)
        stats["createdSlot"] += 1

    stats["needsConfirm"] = stats["matchedProximity"]
    questions.sort(key=lambda x: (x.group_seq if x.group_seq is not None else -1,
                                  x.display_no if x.display_no is not None else 0,
                                  x.seq))
    for i, q in enumerate(questions):
        q.seq = i
    return stats


def _apply(q: Question, rec, source: str = AS_DOC) -> None:
    """把一条答案记录写进题目（含解析正文与解析配图）。"""
    if rec.answer and rec.answer not in q.answers:
        q.answers.append(rec.answer)
    # 手动录入优先级最高，不被文档解析覆盖
    if q.answer_source != "manual":
        q.answer_source = source
    if rec.matched_seq is None:
        rec.matched_seq = q.seq

    text = (rec.text or "").strip()
    if text or rec.images:
        exp = Explanation(seq=len(q.explanations), title="解析", content=text)
        for img in rec.images:
            img.role = ROLE_EXPLANATION
            q.images.append(img)
            exp.image_paths.append(img.file_path)
        q.explanations.append(exp)
