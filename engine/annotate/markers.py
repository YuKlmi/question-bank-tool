# -*- coding: utf-8 -*-
"""第 2 段：标记（Annotate）。

对每个 Block 独立打标，**只做局部判断、不做上下文裁决**——
上下文归属全部交给第 3 段回填。这样切题规则与归属逻辑互不干扰，
也便于单独为标记层写测试。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from ..models import Block
from ..rules import Template

# 事件类型
K_NOISE = "noise"
K_GROUP = "group"
K_QUESTION = "question"
K_ANSWER = "answer"
K_ANSWER_SECTION = "answer_section"
K_EXPLANATION = "explanation"
K_OPTION = "option"
K_TEXT = "text"
K_IMAGE = "image"


@dataclass
class Event:
    kind: str
    order: int
    text: str = ""          # 原始行文本
    rest: str = ""          # 关键标记之后的剩余文本
    page: Optional[int] = None
    bbox: Any = None
    question_no: Optional[int] = None
    label: Optional[str] = None
    options: List[Tuple[str, str]] = field(default_factory=list)
    answer: Optional[str] = None
    confidence: float = 0.0
    image_path: Optional[str] = None
    image_size: Any = None
    style: Optional[str] = None

    @property
    def is_image(self) -> bool:
        return self.kind == K_IMAGE


def extract(blocks: List[Block], template: Template) -> List[Event]:
    events: List[Event] = []

    for b in blocks:
        if b.is_image:
            events.append(Event(
                kind=K_IMAGE, order=b.order, page=b.page, bbox=b.bbox,
                image_path=b.image_path, image_size=b.image_size,
            ))
            continue

        s = b.text.strip()
        if not s:
            continue

        base = dict(order=b.order, text=s, page=b.page, bbox=b.bbox, style=b.style)

        # 1) 噪声（页码 / 水印 / 广告）
        if template.is_noise(s):
            events.append(Event(kind=K_NOISE, **base))
            continue

        # 2) 答案（最具体的规则优先，样例 B 的「1. 解析：正确答案是[D]。」同时像题号行）
        ans = template.match_answer(s)
        if ans:
            no, letter, conf, rest = ans
            events.append(Event(
                kind=K_ANSWER, question_no=no, answer=letter,
                confidence=conf, rest=rest.strip(), **base,
            ))
            continue

        # 3) 解析分区标题（「答案与解析」）
        if template.match_answer_section(s):
            events.append(Event(kind=K_ANSWER_SECTION, **base))
            continue

        # 4) 大题组标题
        title = template.match_group_title(s)
        if title:
            events.append(Event(kind=K_GROUP, rest=title, **base))
            continue

        # 5) 题号
        qn = template.match_question_no(s)
        if qn:
            no, rest = qn
            events.append(Event(kind=K_QUESTION, question_no=no, rest=rest.strip(), **base))
            continue

        # 6) 解析标记行
        head = template.match_explanation(s)
        if head:
            events.append(Event(kind=K_EXPLANATION, rest=head, **base))
            continue

        # 7) 选项（支持一行多选项）
        opts = template.split_options(s)
        if opts:
            events.append(Event(kind=K_OPTION, options=opts, **base))
            continue

        # 8) 普通正文（题干续行 或 解析正文）
        events.append(Event(kind=K_TEXT, **base))

    return events


def counts(events: List[Event]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for e in events:
        out[e.kind] = out.get(e.kind, 0) + 1
    return out
