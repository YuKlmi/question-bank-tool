# -*- coding: utf-8 -*-
"""题型与判分的单元判定（避免在业务代码里散落字符串比较）。"""
from __future__ import annotations

from typing import List

from .models import (
    GM_AUTO, GM_SELF, GM_SEMI, QTYPE_TO_GRADE,
    QT_BLANK, QT_ESSAY, QT_JUDGE, QT_MULTI, QT_SINGLE,
)

_TRUE_WORDS = {"对", "正确", "是", "t", "true", "y", "yes", "√", "1"}
_FALSE_WORDS = {"错", "错误", "否", "f", "false", "n", "no", "×", "x", "0"}


def normalize_answer_token(raw: str) -> str:
    """答案比较用的归一化：去空白、全角转半角、统一大小写、去常见标点。"""
    if raw is None:
        return ""
    s = str(raw).strip()
    s = s.translate(_FULLWIDTH_MAP)
    # 去掉装饰性标点（括号、顿号、逗号、分号、空格）
    for ch in "（）()[]【】、,，;；:： \t\u3000":
        s = s.replace(ch, "")
    return s.upper()


_FULLWIDTH_MAP = str.maketrans(
    "ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ"
    "ａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ"
    "０１２３４５６７８９",
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "abcdefghijklmnopqrstuvwxyz"
    "0123456789",
)


def infer_question_type(stem: str, option_count: int) -> str:
    """从题干与选项数推断题型（启发式，拿不准时退回单选）。"""
    s = stem or ""
    if option_count == 0:
        if "____" in s or "＿＿" in s or "横线" in s:
            return QT_BLANK
        if any(k in s for k in ("简述", "说明理由", "请回答", "论述", "试述", "分析")):
            return QT_ESSAY
        return QT_ESSAY if len(s) > 120 else QT_BLANK
    if option_count == 2 and ("判断" in s or "是否正确" in s or "下列说法正确" in s):
        # 判断题常见的 A/B 或 对/错 两选项
        return QT_JUDGE
    if option_count == 2:
        return QT_JUDGE
    # 多选题的典型线索
    if "多选" in s or "多项" in s or "选出所有" in s:
        return QT_MULTI
    return QT_SINGLE


def grade_mode_of(qtype: str) -> str:
    return QTYPE_TO_GRADE.get(qtype, GM_AUTO)


def judge(user_answer: str, correct: List[str], qtype: str) -> bool:
    """客观题判分。填空与主观题不走这里。"""
    if qtype == QT_JUDGE:
        u = normalize_answer_token(user_answer).lower()
        c = normalize_answer_token("".join(correct)).lower()
        if u in _TRUE_WORDS and c in _TRUE_WORDS:
            return True
        if u in _FALSE_WORDS and c in _FALSE_WORDS:
            return True
        return u == c

    if qtype == QT_MULTI:
        u = set(normalize_answer_token(user_answer))
        c = set(normalize_answer_token("".join(correct)))
        return u == c and len(u) > 0

    # 单选 / 判断
    u = normalize_answer_token(user_answer)
    c = set(normalize_answer_token(x) for x in correct)
    return u in c


def grade_blank(user_answer: str, blanks: List[List[str]]) -> tuple[bool, float]:
    """填空题判分：每个空独立比对，返回 (是否全对, 得分率)。

    blanks 为每个空的候选答案列表（支持同义答案）。
    """
    if not blanks:
        return False, 0.0
    user_parts = split_blanks(user_answer, len(blanks))
    hit = 0
    for part, cands in zip(user_parts, blanks):
        u = normalize_answer_token(part).lower()
        if not u:
            continue
        if any(u == normalize_answer_token(c).lower() for c in cands):
            hit += 1
    ratio = hit / len(blanks)
    return hit == len(blanks), ratio


def split_blanks(raw: str, n: int) -> List[str]:
    """把用户的填空作答切成 n 段：优先按分隔符，否则按顺序切。"""
    if n <= 1:
        return [raw or ""]
    text = raw or ""
    for sep in ("|", "；", ";", "，", ","):
        if sep in text:
            parts = [p.strip() for p in text.split(sep)]
            if len(parts) == n:
                return parts
    return [text.strip()] + [""] * (n - 1)
