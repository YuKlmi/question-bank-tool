# -*- coding: utf-8 -*-
"""第 2 段：标记（Annotate）。

对每个 Block 打标，**只做局部判断、不做上下文裁决**——
上下文归属全部交给第 3 段回填。这样切题规则与归属逻辑互不干扰，
也便于单独为标记层写测试。

这里承担两个实测催生的状态判断：
- **卷首须知**：样卷的「注意事项」里有 `1. 监考老师宣布考试开始时…`，
  与正文题号写法一致，不排除会产生假题并与正文题 1 重号
- **答案区**：进入「答案解析：」之后，题号行不再视为题目，而是**答案块的头**；
  答案字母可能出现在块内任意位置甚至下一行，必须交给回填段按块抽取
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from ..models import Block
from ..rules import Template, split_multi_answer

# 事件类型
K_NOISE = "noise"
K_GROUP = "group"
K_QUESTION = "question"
K_ANSWER = "answer"
K_ANSWER_HEAD = "answer_head"
K_ANSWER_GROUP = "answer_group"
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
    # 是否位于「答案解析：」之后的答案区。
    # 两种版式的匹配策略不同：答案区用分段对齐，与题目交错的用紧邻同号题。
    in_zone: bool = False

    @property
    def is_image(self) -> bool:
        return self.kind == K_IMAGE


def extract(blocks: List[Block], template: Template) -> List[Event]:
    events: List[Event] = []
    in_preamble = False
    answer_zone = False

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

        # ---------- 卷首须知（考试须知 / 注意事项）----------
        if in_preamble:
            # 遇到试卷开始标记或大题组标题即退出须知区间，并正常处理该行
            if not (template.is_preamble_end(s) or template.match_group_title(s)):
                events.append(Event(kind=K_NOISE, **base))
                continue
            in_preamble = False
        elif template.is_preamble_start(s):
            in_preamble = True
            events.append(Event(kind=K_NOISE, **base))
            continue

        # ---------- 噪声（页码 / 水印 / 广告）----------
        if template.is_noise(s):
            events.append(Event(kind=K_NOISE, **base))
            continue

        # ---------- 解析分区标题 ----------
        # 只在「首次进入答案区」时判定。若已在答案区内还继续判标题，
        # 会把答案块里的短行（恰好以「答案/解析」结尾）当成新标题吞掉，
        # 实测样例 C 的题 23 就是这样丢掉答案的。
        if not answer_zone and template.match_answer_section(s):
            answer_zone = True
            events.append(Event(kind=K_ANSWER_SECTION, **base))
            continue

        # ---------- 答案区 ----------
        if answer_zone:
            # 一行里挤了多个「题号+字母」答案对（实测样卷有 `6.C  7.A  8.E …`）
            multi = split_multi_answer(s)
            if multi:
                for no, letter in multi:
                    events.append(Event(
                        kind=K_ANSWER, question_no=no, answer=letter,
                        confidence=0.85, rest="", in_zone=True, **base,
                    ))
                continue

            # 答案区里的大题组标题：只更新分组上下文，不切回题目模式
            title = template.match_group_title(s)
            if title and not template.match_question_no(s):
                events.append(Event(kind=K_ANSWER_GROUP, rest=title, **base))
                continue

            qn = template.match_question_no(s)
            if qn:
                no, rest = qn
                # 快路径：整行同时含题号与答案字母
                ans = template.match_answer(s)
                if ans:
                    _, letter, conf, tail = ans
                    events.append(Event(
                        kind=K_ANSWER, question_no=no, answer=letter,
                        confidence=conf, rest=tail.strip(), in_zone=True, **base,
                    ))
                else:
                    # 慢路径：只切出题号，答案字母等回填段从块内容里抽
                    events.append(Event(
                        kind=K_ANSWER_HEAD, question_no=no, rest=rest.strip(),
                        in_zone=True, **base,
                    ))
                continue

            events.append(Event(kind=K_TEXT, **base))
            continue

        # ---------- 题目区 ----------

        # 1) 行级答案（部分文档答案与题目交错时的快路径）
        ans = template.match_answer(s)
        if ans:
            no, letter, conf, rest = ans
            events.append(Event(
                kind=K_ANSWER, question_no=no, answer=letter,
                confidence=conf, rest=rest.strip(), **base,
            ))
            continue

        # 2) 大题组标题
        title = template.match_group_title(s)
        if title:
            events.append(Event(kind=K_GROUP, rest=title, **base))
            continue

        # 3) 题号
        qn = template.match_question_no(s)
        if qn:
            no, rest = qn
            events.append(Event(kind=K_QUESTION, question_no=no, rest=rest.strip(), **base))
            continue

        # 4) 解析标记行
        head = template.match_explanation(s)
        if head:
            events.append(Event(kind=K_EXPLANATION, rest=head, **base))
            continue

        # 5) 选项（支持一行多选项）
        opts = template.split_options(s)
        if opts:
            events.append(Event(kind=K_OPTION, options=opts, **base))
            continue

        # 6) 普通正文（题干续行 或 解析正文）
        events.append(Event(kind=K_TEXT, **base))

    return events


def counts(events: List[Event]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for e in events:
        out[e.kind] = out.get(e.kind, 0) + 1
    return out
