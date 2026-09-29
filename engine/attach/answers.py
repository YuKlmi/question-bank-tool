# -*- coding: utf-8 -*-
"""答案回填。

**核心难点（实测催生）**：同一份卷子里，题目区与答案区的题号**都会按大题组重置**。
例如某份 EPI 样卷：题目区是「1–15 / 21–35 / 6–15 / 1–10」，
答案区是「1–35 / 1–15 / 1–10」。此时全局按题号匹配必然错位。

因此采用**分段对齐**：
  1. 把题目按阅读顺序切成若干「题号递增段」（题号回退即新段）
  2. 把答案按出现顺序切成同样的递增段
  3. 第 k 段答案对齐到第 k 段题目（按题号重合度择优，容忍某段整体缺失）
  4. 段内再按题号一一对应

这样既解决了题号重置，也不会像「就近推断」那样把答案挂到隔壁题上。
段内仍匹配不上的，进人工队列，不猜。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..models import (
    AS_DOC, Explanation, Question, ROLE_EXPLANATION,
    RS_PENDING_INPUT, SS_IMAGE,
)


def _split_runs(items: Sequence[Any], number_of) -> List[List[Any]]:
    """按「编号回退」把序列切成若干递增段。

    递增段内部的编号允许有缺口（题面是图片时会缺号），
    只有出现回退才认为进入了新的大题组。
    """
    runs: List[List[Any]] = []
    cur: List[Any] = []
    prev: Optional[int] = None
    for it in items:
        n = number_of(it)
        if n is None:
            continue
        if prev is not None and n <= prev:
            if cur:
                runs.append(cur)
            cur = []
        cur.append(it)
        prev = n
    if cur:
        runs.append(cur)
    return runs


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
        "matchedInline": 0,
        "matchedProximity": 0,
        "conflict": 0,
        "createdSlot": 0,
        "unmatched": 0,
        "runPairs": 0,
    }

    if not questions or not answers:
        stats["needsConfirm"] = 0
        return stats

    # 统一走「题号递增段」对齐。
    #
    # 曾试过按「是否位于卷尾答案区」分两套策略，但实测样例 A 的答案
    # 同样是集中在卷尾成块的，只是没有「答案解析：」这类标题可作依据，
    # 于是被误判成「与题目交错」而整体错位。分段对齐对三种版式都成立。
    q_ordered = sorted(questions, key=lambda q: q_start.get(id(q), 0))
    q_runs = _split_runs(q_ordered, lambda q: q.display_no)
    a_runs = _split_runs(list(answers), lambda r: r.no)

    q_index: List[Dict[int, Question]] = []
    for run in q_runs:
        idx: Dict[int, Question] = {}
        for q in run:
            idx.setdefault(q.display_no, q)
        q_index.append(idx)

    # 全局题号是否唯一（决定能否为「有答案无题」补槽位）
    all_nos: Dict[int, int] = {}
    for q in questions:
        if q.display_no is not None:
            all_nos[q.display_no] = all_nos.get(q.display_no, 0) + 1
    number_unique = all(v == 1 for v in all_nos.values())

    pending_slots: List[AnswerRec] = []

    # 严格按「段序」对齐：第 k 段答案对应第 k 段题目。
    #
    # 试过用「交集最大」挑选题目段，结果在样例 A 上整体错位了一格：
    # 该卷「判断推理」组的题号是从 6 开始的（正文里没有 1–5，只有它们的答案），
    # 于是只有 1 个元素的答案段被"交集最大"吸引到了另一组，导致后续全部串位。
    # 段序对齐更忠实于版式事实；对不上的宁可进人工队列，也不能给出错误答案。
    for k, a_run in enumerate(a_runs):
        if k >= len(q_index):
            stats["unmatched"] += len(a_run)
            if number_unique and create_missing_slots:
                pending_slots.extend(a_run)
            continue

        stats["runPairs"] += 1
        index = q_index[k]

        for rec in a_run:  # type: ignore[assignment]
            target = index.get(rec.no)
            if target is not None:
                _apply(target, rec, AS_DOC)
                stats["matched"] += 1
                stats["matchedUnique"] += 1
            else:
                # 该段里没有对应题号（题面可能是图片、或该题编号缺失）。
                # 不猜、不就近凑，统一进人工队列。
                stats["conflict"] += 1

    # ---- 有答案但无题目槽位（题号全局唯一时才敢补）----
    if number_unique and create_missing_slots:
        # 这些槽位要排在所有已识别题目之后，否则会打乱阅读顺序切段
        max_order = max(q_start.values(), default=0)
        for i, rec in enumerate(pending_slots):
            if any(q.display_no == rec.no for q in questions):
                continue
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
            q_start[id(ph)] = max_order + 1 + i
            _apply(ph, rec, AS_DOC)
            questions.append(ph)
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
