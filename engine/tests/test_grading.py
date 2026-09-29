# -*- coding: utf-8 -*-
"""判分逻辑单测（题型全谱系 → 三档判分）。"""
from __future__ import annotations

from engine.grading import (
    GM_AUTO, GM_SELF, GM_SEMI, grade_blank, grade_mode_of,
    infer_question_type, judge,
)
from engine.models import QT_BLANK, QT_ESSAY, QT_JUDGE, QT_MULTI, QT_SINGLE


def test_grade_mode_mapping():
    assert grade_mode_of(QT_SINGLE) == GM_AUTO
    assert grade_mode_of(QT_MULTI) == GM_AUTO
    assert grade_mode_of(QT_JUDGE) == GM_AUTO
    assert grade_mode_of(QT_BLANK) == GM_SEMI
    assert grade_mode_of(QT_ESSAY) == GM_SELF


def test_infer_type():
    assert infer_question_type("下列说法正确的是", 4) == QT_SINGLE
    assert infer_question_type("下列说法正确的是（多选）", 4) == QT_MULTI
    assert infer_question_type("判断：地球是圆的", 2) == QT_JUDGE
    assert infer_question_type("____是中国的首都", 0) == QT_BLANK
    assert infer_question_type("简述行测的备考思路", 0) == QT_ESSAY


def test_single_choice_judge():
    assert judge("A", ["A"], QT_SINGLE) is True
    assert judge("a", ["A"], QT_SINGLE) is True
    assert judge("ａ", ["A"], QT_SINGLE) is True      # 全角
    assert judge("（A）", ["A"], QT_SINGLE) is True     # 带括号
    assert judge("B", ["A"], QT_SINGLE) is False
    assert judge("", ["A"], QT_SINGLE) is False


def test_multi_choice_judge_requires_exact_set():
    assert judge("ABC", ["A", "B", "C"], QT_MULTI) is True
    assert judge("ACB", ["A", "B", "C"], QT_MULTI) is True
    assert judge("AB", ["A", "B", "C"], QT_MULTI) is False   # 漏选不算对
    assert judge("ABCD", ["A", "B", "C"], QT_MULTI) is False
    assert judge("", ["A", "B"], QT_MULTI) is False


def test_judge_question():
    assert judge("对", ["正确"], QT_JUDGE) is True
    assert judge("√", ["正确"], QT_JUDGE) is True
    assert judge("错", ["正确"], QT_JUDGE) is False
    assert judge("×", ["错误"], QT_JUDGE) is True


def test_blank_grading_multi_hole():
    ok, ratio = grade_blank("北京|上海", [["北京"], ["上海"]])
    assert ok is True and ratio == 1.0

    ok, ratio = grade_blank("北京，上海", [["北京"], ["上海"]])
    assert ok is True

    ok, ratio = grade_blank("北京|广州", [["北京"], ["上海"]])
    assert ok is False and ratio == 0.5

    # 容错：大小写、空格、全半角
    ok, _ = grade_blank(" abc ", [["ABC"]])
    assert ok is True


def test_blank_grading_synonyms():
    ok, _ = grade_blank("京", [["北京", "京"]])
    assert ok is True


def test_blank_grading_empty():
    ok, ratio = grade_blank("", [[]])
    assert ok is False and ratio == 0.0
