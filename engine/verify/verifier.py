# -*- coding: utf-8 -*-
"""第 4 段：校验（Verify）。

职责：定置信度、定校对状态、跑一致性检查、产出解析报告。
任何异常都写进 report.issues，供界面提示与人工校对队列使用。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..models import (
    AS_DOC, AS_DOC_INFERRED, AS_MANUAL, GM_SELF, RS_OK, RS_PENDING,
    RS_PENDING_INPUT, SS_IMAGE,
)


def verify(
    questions: List,
    groups: List,
    event_counts: Dict[str, int],
    answer_stats: Dict[str, int],
    attach_stats: Dict[str, int],
    block_count: int,
    extra_warnings: Optional[List[str]] = None,
) -> Dict[str, Any]:
    issues: List[Dict[str, Any]] = []

    for q in questions:
        q.confidence = _score(q)
        q.review_state = _state(q)

        if q.stem_source == SS_IMAGE and not q.images:
            issues.append({
                "kind": "image_missing",
                "questionSeq": q.seq,
                "displayNo": q.display_no,
                "message": "判定为图片题面，但未关联到原图",
            })
        if q.type in ("single", "multi") and len(q.options) < 2:
            issues.append({
                "kind": "options_incomplete",
                "questionSeq": q.seq,
                "displayNo": q.display_no,
                "message": f"选项不完整（仅 {len(q.options)} 项）",
            })
        if not q.answers and q.review_state != RS_PENDING_INPUT:
            issues.append({
                "kind": "answer_missing",
                "questionSeq": q.seq,
                "displayNo": q.display_no,
                "message": "未匹配到答案",
            })

    answered = sum(1 for q in questions if q.answers)
    report: Dict[str, Any] = {
        "blockCount": block_count,
        "eventCounts": dict(event_counts),
        "groupCount": len(groups),
        "questionCount": len(questions),
        "answeredCount": answered,
        "answerCoverage": round(answered / len(questions), 3) if questions else 0.0,
        "pendingInputCount": sum(1 for q in questions if q.review_state == RS_PENDING_INPUT),
        "pendingReviewCount": sum(1 for q in questions if q.review_state == RS_PENDING),
        "okCount": sum(1 for q in questions if q.review_state == RS_OK),
        "answersTotal": answer_stats.get("matched", 0) + answer_stats.get("conflict", 0)
                        + answer_stats.get("unmatched", 0),
        "answersMatched": answer_stats.get("matched", 0),
        "answersConflict": answer_stats.get("conflict", 0),
        "answersUnmatched": answer_stats.get("unmatched", 0),
        "answersNeedsConfirm": answer_stats.get("needsConfirm", 0),
        "placeholderCount": attach_stats.get("placeholderCount", 0),
        "createdSlotCount": answer_stats.get("createdSlot", 0),
        "issues": issues,
        "warnings": list(extra_warnings or []),
    }

    # 数量一致性检查：答案数明显少于题目数时给出提示，但不阻断
    if report["answersTotal"] and report["questionCount"]:
        if report["answersTotal"] < report["questionCount"] * 0.5:
            report["warnings"].append(
                f"答案数（{report['answersTotal']}）不足题目数（{report['questionCount']}）的一半，"
                "可能是答案区未被识别，请检查规则模板"
            )
    if report["answersConflict"]:
        report["warnings"].append(
            f"{report['answersConflict']} 条答案因题号重复无法确定归属，已转人工队列"
        )
    return report


def _score(q) -> float:
    """置信度：由「答案可信度 + 结构完整度」共同决定。"""
    base = 0.5
    if q.answers:
        if q.answer_source == AS_DOC:
            base = 0.9
        elif q.answer_source == AS_DOC_INFERRED:
            # 就近推断的答案：故意压低，确保落进人工校对队列
            base = 0.65
        elif q.answer_source == AS_MANUAL:
            base = 0.95
        else:
            base = 0.8
    if len(q.options) >= 2:
        base += 0.08
    if len(q.options) >= 4:
        base += 0.02
    if not q.stem.strip():
        base -= 0.4
    if q.stem_source == SS_IMAGE:
        base = min(base, 0.4)
    return round(max(0.0, min(1.0, base)), 3)


def _state(q) -> str:
    if q.stem_source == SS_IMAGE and not q.stem.strip():
        return RS_PENDING_INPUT
    if q.grade_mode == GM_SELF:
        # 主观题只要有题干即可用，不要求有答案
        return RS_OK if q.stem.strip() and q.confidence >= 0.9 else RS_PENDING
    if q.confidence >= 0.9 and q.answers and len(q.options) >= 2:
        return RS_OK
    return RS_PENDING
