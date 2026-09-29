# -*- coding: utf-8 -*-
"""第 3 段：回填（Attach）。

把标记事件按阅读顺序重放，组装成 Group / Question，并完成三件事：
1. 选项归属最近的前置题号锚点（跨页续行因此天然成立）
2. 图片归属：区分「题干配图」与「下一题的材料图」，并处理题面缺失的图片题
3. 答案按题号回填；题号有歧义时**不猜**，转人工队列

题号缺失的补位逻辑（实测催生）：
样例 B 的题 1–3、21–24 共 7 道题的题面被整段图片覆盖，文本层完全不存在。
这些题在答案区都有独立答案，因此必须补出对应数量的题目槽位，
否则答案无处回填。补位题标 pending_input，由用户照原图录入。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from ..annotate.markers import (
    Event, K_ANSWER, K_ANSWER_SECTION, K_EXPLANATION, K_GROUP,
    K_IMAGE, K_NOISE, K_OPTION, K_QUESTION, K_TEXT,
)
from ..models import (
    Explanation, Group, ImageRef, Option, Question,
    ROLE_EXPLANATION, ROLE_STEM, RS_OK, RS_PENDING, RS_PENDING_INPUT,
    SS_IMAGE, SS_TEXT,
)


@dataclass
class AnswerRec:
    """答案区的一条记录（含其解析正文与配图）。"""
    no: int
    answer: str
    confidence: float
    order: int
    text: str = ""
    images: List[ImageRef] = field(default_factory=list)
    group_seq: Optional[int] = None
    matched_seq: Optional[int] = None

    def append_text(self, line: str) -> None:
        self.text = f"{self.text}\n{line}" if self.text else line


@dataclass
class AttachResult:
    groups: List[Group]
    questions: List[Question]
    answers: List[AnswerRec]
    stats: Dict[str, int] = field(default_factory=dict)
    q_start: Dict[int, int] = field(default_factory=dict)   # id(Question) → 块流位置


def attach(events: List[Event], doc_id: int = 0) -> AttachResult:
    groups: List[Group] = []
    questions: List[Question] = []
    answers: List[AnswerRec] = []

    cur_group: Optional[Group] = None
    cur_q: Optional[Question] = None
    cur_answer: Optional[AnswerRec] = None
    mode = "question"                     # question | answer

    # 题目的瞬态信息（不改模型）
    last_opt_order: Dict[int, int] = {}
    opt_buf: Dict[int, Dict[str, str]] = {}
    opt_img_buf: Dict[int, Dict[str, str]] = {}
    # id(Question) → 该题在块流中的起始 / 最后位置，用于缺口图片归属
    q_start: Dict[int, int] = {}
    q_last: Dict[int, int] = {}

    orphan_images: List[Tuple[int, ImageRef]] = []   # 尚未归属的图片
    material_images: List[ImageRef] = []             # 疑似「下一题材料图」

    next_q_seq = 0
    next_group_seq = 0

    def close_question() -> None:
        nonlocal cur_q
        if cur_q is None:
            return
        seq = cur_q.seq
        labels = opt_buf.get(seq) or {}
        for i, label in enumerate(sorted(labels)):
            cur_q.options.append(Option(
                label=label, seq=i, content=labels[label],
                image_path=opt_img_buf.get(seq, {}).get(label),
            ))
        cur_q = None

    def new_question(no: Optional[int], stem: str, raw: str, ev: Optional[Event]) -> None:
        nonlocal cur_q, next_q_seq
        close_question()
        q = Question(
            doc_id=doc_id,
            seq=next_q_seq,
            display_no=no,
            group_seq=cur_group.seq if cur_group else None,
            stem=stem,
            raw_text=raw,
            page_no=ev.page if ev else None,
            bbox=ev.bbox if ev else None,
        )
        if material_images:
            q.images.extend(material_images)
            material_images.clear()
        next_q_seq += 1
        q_start[id(q)] = ev.order if ev else 0
        q_last[id(q)] = q_start[id(q)]
        opt_buf[q.seq] = {}
        opt_img_buf[q.seq] = {}
        questions.append(q)
        cur_q = q

    for ev in events:
        # ---------- 图片 ----------
        if ev.kind == K_IMAGE:
            img = ImageRef(
                file_path=ev.image_path or "",
                role=ROLE_STEM,
                seq=0,
                page=ev.page,
                bbox=ev.bbox,
                source="pdf-xobject",
                width=(ev.image_size or (None, None))[0],
                height=(ev.image_size or (None, None))[1],
            )
            if mode == "answer" and cur_answer is not None:
                img.role = ROLE_EXPLANATION
                cur_answer.images.append(img)
                continue
            if cur_q is None:
                orphan_images.append((ev.order, img))
                continue
            # 当前题选项已齐 → 该图更可能是「下一题的材料图」
            done_opts = len(opt_buf.get(cur_q.seq, {})) >= 2
            after_opts = ev.order > last_opt_order.get(cur_q.seq, -1)
            if done_opts and after_opts:
                material_images.append(img)
            else:
                cur_q.images.append(img)
                q_last[id(cur_q)] = ev.order
            continue

        # ---------- 噪声 ----------
        if ev.kind == K_NOISE:
            continue

        # ---------- 大题组 ----------
        if ev.kind == K_GROUP:
            close_question()
            cur_answer = None
            cur_group = Group(seq=next_group_seq, title=ev.rest, raw_text=ev.text)
            next_group_seq += 1
            groups.append(cur_group)
            mode = "question"
            continue

        # ---------- 答案分区标题 ----------
        if ev.kind == K_ANSWER_SECTION:
            close_question()
            mode = "answer"
            cur_answer = None
            continue

        # ---------- 答案行 ----------
        if ev.kind == K_ANSWER:
            close_question()
            mode = "answer"
            rec = AnswerRec(
                no=ev.question_no or 0,
                answer=ev.answer or "",
                confidence=ev.confidence,
                order=ev.order,
                text=ev.rest,
                group_seq=cur_group.seq if cur_group else None,
            )
            answers.append(rec)
            cur_answer = rec
            continue

        # ---------- 题号行 ----------
        if ev.kind == K_QUESTION:
            if mode == "answer" and cur_answer is not None:
                # 答案区里长得像题号的行，按解析正文处理，不新建题目
                tail = ev.text
                cur_answer.append_text(tail)
                continue
            new_question(ev.question_no, ev.rest, ev.text, ev)
            continue

        # ---------- 独立解析标记 ----------
        if ev.kind == K_EXPLANATION:
            tail = ev.text[len(ev.rest):].lstrip("：: 　").strip()
            if cur_answer is not None and tail:
                cur_answer.append_text(tail)
            elif cur_q is not None and tail:
                cur_q.stem = f"{cur_q.stem}\n{tail}" if cur_q.stem else tail
                q_last[id(cur_q)] = ev.order
            continue

        # ---------- 选项 ----------
        if ev.kind == K_OPTION:
            if mode == "question" and cur_q is not None:
                buf = opt_buf.setdefault(cur_q.seq, {})
                ibuf = opt_img_buf.setdefault(cur_q.seq, {})
                for label, content in ev.options:
                    if label in buf:
                        continue
                    buf[label] = content
                    ibuf[label] = ""
                last_opt_order[cur_q.seq] = ev.order
                q_last[id(cur_q)] = ev.order
            elif cur_answer is not None:
                cur_answer.append_text(ev.text)
            elif cur_q is not None:
                cur_q.stem = f"{cur_q.stem}\n{ev.text}" if cur_q.stem else ev.text
            continue

        # ---------- 普通正文 ----------
        if ev.kind == K_TEXT:
            if mode == "answer" and cur_answer is not None:
                cur_answer.append_text(ev.text)
            elif cur_q is not None:
                cur_q.stem = f"{cur_q.stem}\n{ev.text}" if cur_q.stem else ev.text
                q_last[id(cur_q)] = ev.order
            continue

    close_question()

    stats = _fill_number_gaps(
        questions, groups, orphan_images, doc_id, next_q_seq, q_start, q_last
    )
    return AttachResult(
        groups=groups, questions=questions, answers=answers,
        stats=stats, q_start=dict(q_start),
    )


# 判定为「整页级图片」的尺寸下限：这类图才可能承载成段的题面
_PAGE_SCALE_MIN_W = 300
_PAGE_SCALE_MIN_H = 150

# 一道题面图片最多可能吞掉多少道题。超过这个跨度就不再视为「图片吞题」，
# 而是题号本身不连续（例如大题组标题「根据以下资料，回答131~135题。」
# 与组内题号不一致的情形），此时不补位。
_MAX_GAP = 10


def _is_page_scale(img: ImageRef) -> bool:
    w = img.width or 0
    h = img.height or 0
    return w >= _PAGE_SCALE_MIN_W and h >= _PAGE_SCALE_MIN_H


def _take_images_in_range(
    orphan_images: List[Tuple[int, ImageRef]], lo: int, hi: int
) -> List[ImageRef]:
    """取出并移除落在 (lo, hi) 区间内的孤立图片。"""
    picked: List[ImageRef] = []
    for item in list(orphan_images):
        order, img = item
        if lo < order < hi:
            picked.append(img)
            orphan_images.remove(item)
    return picked


def _fill_number_gaps(
    questions: List[Question],
    groups: List[Group],
    orphan_images: List[Tuple[int, ImageRef]],
    doc_id: int,
    next_seq: int,
    q_start: Dict[int, int],
    q_last: Dict[int, int],
) -> Dict[str, int]:
    """按**阅读顺序**检测题号缺口并补出「图片题」槽位。

    实测场景（样例 B）：题 1–3 与 21–24 的题面被整段图片覆盖，文本层里
    根本没有这些题号。若不补位，答案区里这 7 条答案将无处回填。

    三点约束，缺一不可：
    1. 只在**连续递增段**内找缺口 —— 题号回退说明换了大题组，不是缺口
    2. 缺口跨度不得超过 _MAX_GAP —— 否则是题号体系本身不连续
    3. 缺口区间内必须存在**整页级图片** —— 补位的唯一理由就是有图吞了题
    """
    stats = {"placeholderCount": 0, "orphanImageCount": len(orphan_images)}
    if not questions:
        return stats

    ordered = sorted(questions, key=lambda x: q_start.get(id(x), 0))
    seq = next_seq
    prev: Optional[Question] = None
    prev_no = 0
    prev_last = -1

    for q in ordered:
        if q.display_no is None:
            continue
        gap = q.display_no - prev_no - 1
        if 0 < gap <= _MAX_GAP:
            hi = q_start.get(id(q), 0)
            imgs = [
                img for img in _take_images_in_range(orphan_images, prev_last, hi)
                if _is_page_scale(img)
            ]
            if imgs:
                for missing in range(prev_no + 1, q.display_no):
                    ph = Question(
                        doc_id=doc_id,
                        seq=seq,
                        display_no=missing,
                        group_seq=q.group_seq,
                        stem="",
                        raw_text="（题面为图片，文本层不存在；本图可能包含多道题）",
                        stem_source=SS_IMAGE,
                        review_state=RS_PENDING_INPUT,
                        page_no=q.page_no,
                    )
                    ph.images.extend(imgs)
                    questions.append(ph)
                    stats["placeholderCount"] += 1
                    seq += 1
        prev = q
        prev_no = q.display_no
        prev_last = q_last.get(id(q), prev_last)

    # 仍未归属的图片：挂给「块序在它之前、且最接近」的题目，避免静默丢弃
    for order, img in list(orphan_images):
        owner: Optional[Question] = None
        best = -1
        for q in questions:
            s = q_start.get(id(q))
            if s is None:
                continue
            if s <= order and s >= best:
                best = s
                owner = q
        if owner is not None:
            if not any(i.file_path == img.file_path for i in owner.images):
                owner.images.append(img)
            orphan_images.remove((order, img))

    questions.sort(key=lambda x: (x.group_seq if x.group_seq is not None else -1,
                                  x.display_no if x.display_no is not None else 0,
                                  x.seq))
    for i, q in enumerate(questions):
        q.seq = i
    stats["unassignedImageCount"] = len(orphan_images)
    return stats
