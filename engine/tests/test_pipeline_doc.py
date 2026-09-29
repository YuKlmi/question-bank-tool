# -*- coding: utf-8 -*-
"""样例 A（旧版 .doc）解析端到端回归 —— 对应里程碑 M6。

验收口径（AGENTS.md M6）：
    样例 A 答案回填 + 人工队列可用
重点验证：.doc → .docx 转换、行内多选项切分、答案歧义的分层处理。
"""
from __future__ import annotations

import pytest

from engine.models import AS_DOC_INFERRED


@pytest.fixture(scope="module")
def doc_result(doc_sample, tmp_path_factory):
    from engine.pipeline import parse

    data_dir = tmp_path_factory.mktemp("docdata")
    return parse(doc_sample, data_dir)


def test_doc_converted_and_parsed(doc_result):
    """旧版 .doc 必须能经 Word 转换后解析出题目。"""
    assert doc_result.orig_type == "doc"
    assert len(doc_result.questions) >= 40
    assert doc_result.report["warnings"], "应记录「已通过 Word 转换」"


def test_groups_detected(doc_result):
    titles = [g.title for g in doc_result.groups]
    assert any("语言理解" in t for t in titles)
    assert any("数学能力" in t for t in titles)
    assert any("判断推理" in t for t in titles)


def test_inline_multi_options_split(doc_result):
    """样例 A 实测「一行 2~4 个选项」，必须全部切出来。"""
    q1 = next((q for q in doc_result.questions if q.display_no == 1), None)
    assert q1 is not None
    assert [o.label for o in q1.options] == ["A", "B", "C", "D"]
    assert q1.options[0].content == "莫衷一是　千变万化"


def test_stem_clean_of_options(doc_result):
    """切分后题干里不应残留选项标记。"""
    q1 = next(q for q in doc_result.questions if q.display_no == 1)
    assert "A.莫衷一是" not in q1.stem
    assert "千娇百媚" not in q1.stem


def test_answers_backfilled_with_proximity(doc_result):
    """题号重复导致歧义时，用「就近」收敛，且标记为待确认来源。"""
    r = doc_result.report
    assert r["answersMatched"] > 0
    inferred = [q for q in doc_result.questions if q.answer_source == AS_DOC_INFERRED]
    assert inferred, "样例 A 应产生就近推断的答案"
    for q in inferred:
        assert q.answers
        assert q.review_state == "pending", "就近推断的答案必须留在人工校对队列"


def test_no_answer_question_flagged(doc_result):
    """源文档缺答案的问题不能被静默放过，要能在队列里看到。"""
    no_answer = [q for q in doc_result.questions if not q.answers]
    assert no_answer
    assert all(q.review_state == "pending" for q in no_answer)


def test_tables_and_plaintext_material_kept(doc_result):
    """资料分析题的材料（表格/文字）应进入题干，不能被丢弃。"""
    joined = "\n".join(q.stem for q in doc_result.questions)
    assert "教师" in joined or "统计表" in joined or "材料" in joined
