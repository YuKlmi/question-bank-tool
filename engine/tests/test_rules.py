# -*- coding: utf-8 -*-
"""规则层单测：重点是行内多选项切分（实测最棘手的一环）。"""
from __future__ import annotations

import pytest

from engine.rules import Template


@pytest.fixture(scope="module")
def pdf_tpl() -> Template:
    return Template.by_id("pdf-consolidated")


@pytest.fixture(scope="module")
def doc_tpl() -> Template:
    return Template.by_id("docx-mixed")


# ---------------- 行内多选项切分 ----------------

def test_split_single_option_per_line_pdf(pdf_tpl: Template):
    """样例 B 的主流形态：一行一个选项，标记为 [A]。"""
    got = pdf_tpl.split_options("[A] 2010 年")
    assert got == [("A", "2010 年")]


def test_split_four_options_in_one_line_doc(doc_tpl: Template):
    """样例 A 实测：一行 4 个选项，且标记之间夹着选项内容。"""
    got = doc_tpl.split_options("A．1996            B．1997               C．1998              D．不清楚")
    assert [label for label, _ in got] == ["A", "B", "C", "D"]
    assert got[0][1] == "1996"
    assert got[3][1] == "不清楚"


def test_split_four_options_with_fullwidth_space(doc_tpl: Template):
    got = doc_tpl.split_options("A.程序化　配置　　 B.规模化　整合 C.规模化　配置　　 D.程序化　整合")
    assert [label for label, _ in got] == ["A", "B", "C", "D"]
    assert got[0][1] == "程序化　配置"
    assert got[3][1] == "程序化　整合"


def test_split_bracket_form_inline(doc_tpl: Template):
    got = doc_tpl.split_options("(A)每年使用图书馆的学生人数。 (B)今年图书馆的预算。")
    assert [label for label, _ in got] == ["A", "B"]


def test_split_rejects_letter_inside_text(doc_tpl: Template):
    """正文中的 "A." 不应被当成选项标记。"""
    assert doc_tpl.split_options("这种方法称为A.型结构，另有B.型") is None


def test_split_rejects_non_ascending(doc_tpl: Template):
    """字母不递增（重复）时只取第一个，不应误切。"""
    got = doc_tpl.split_options("A.甲　　A.乙")
    assert got is not None and len(got) == 1


def test_split_content_keeps_digits_with_fullwidth_dot(doc_tpl: Template):
    """全角点既做选项标记又做小数点，不能误切。"""
    got = doc_tpl.split_options("A．2∶1              B．2．1∶1          C．1．5∶1             D．不清楚")
    assert [label for label, _ in got] == ["A", "B", "C", "D"]
    assert got[1][1] == "2．1∶1"


def test_split_requires_first_mark_at_line_start(doc_tpl: Template):
    assert doc_tpl.split_options("前半句 A.选项内容") is None


# ---------------- 题号 ----------------

def test_match_question_no_variants(pdf_tpl: Template):
    assert pdf_tpl.match_question_no("4.  下列情形可能发生的是：（ ）")[0] == 4
    assert pdf_tpl.match_question_no("6.《人民日报》评论指出")[0] == 6
    assert pdf_tpl.match_question_no("7.下列法律谚语")[0] == 7
    assert pdf_tpl.match_question_no("没有题号的一行") is None


def test_match_question_no_bracket_form(doc_tpl: Template):
    no, rest = doc_tpl.match_question_no("【16】1，1, 2, 2, 3, 4, 3, 5, ( )")
    assert no == 16
    assert rest.startswith("1，1")


# ---------------- 答案 ----------------

def test_match_answer_consolidated(pdf_tpl: Template):
    no, ans, conf, rest = pdf_tpl.match_answer("1.  解析：正确答案是[D]。  ①项三大优良作风…")
    assert (no, ans) == (1, "D")
    assert conf > 0.9
    assert rest.lstrip().startswith("①项")


def test_match_answer_all_four_docx_forms(doc_tpl: Template):
    """样例 A 实测的 4 种答案写法都要能命中。"""
    cases = [
        ("2、【解析】C。“程序”，事情进行的", 2, "C"),
        ("9、B【解析】A句关联词语使用不当", 9, "B"),
        ("13．【答案】D。解析：新闻侵权", 13, "D"),
        ("21、B解析：9721-1027。", 21, "B"),
    ]
    for text, no, ans in cases:
        got = doc_tpl.match_answer(text)
        assert got is not None, text
        assert (got[0], got[1]) == (no, ans), text


def test_match_answer_must_not_treat_stem_as_answer(doc_tpl: Template):
    assert doc_tpl.match_answer("9、下列各句中，没有语病的一句是（    ）") is None
    assert doc_tpl.match_answer("12、 下边语句没有歧义的一句是( )。") is None


# ---------------- 噪声 / 分组 ----------------

def test_noise_rules(pdf_tpl: Template):
    assert pdf_tpl.is_noise("  12 / 43 ")
    assert pdf_tpl.is_noise("各类考试包过无忧上岸微信：offertop")
    assert pdf_tpl.is_noise("考佳卜资料网：http://www.kaojiabo.com")
    assert not pdf_tpl.is_noise("4.  下列情形可能发生的是：（ ）")


def test_group_title(pdf_tpl: Template):
    assert pdf_tpl.match_group_title("第一部分  常识判断") == "常识判断"
    assert pdf_tpl.match_group_title("第二部分 言语理解与表达") == "言语理解与表达"


def test_answer_section(pdf_tpl: Template):
    assert pdf_tpl.match_answer_section("答案与解析")
    assert not pdf_tpl.match_answer_section("这道题的答案是A")


def test_template_catalog_complete():
    ids = {t["id"] for t in Template.list_all()}
    assert {"pdf-consolidated", "docx-mixed"} <= ids
