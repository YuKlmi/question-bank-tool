# -*- coding: utf-8 -*-
"""样例 A（旧版 .doc）解析端到端回归 —— 对应里程碑 M6。

验收口径（AGENTS.md M6）：
    样例 A 答案回填 + 人工队列可用
重点验证：.doc → .docx 转换、行内多选项切分、答案歧义的分层处理。
"""
from __future__ import annotations

import pytest

from engine.models import AS_DOC, AS_DOC_INFERRED


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


def _find(doc_result, group_kw: str, display_no: int):
    for q in doc_result.questions:
        g = next((g for g in doc_result.groups if g.seq == q.group_seq), None)
        if g and group_kw in g.title and q.display_no == display_no:
            return q
    return None


def test_answers_backfilled_by_run_alignment(doc_result):
    """题号在大题组间重置时，按「题号递增段」对齐，段内按题号精确匹配。

    这条取代了早期的「就近推断」：分段对齐后，段内匹配是确定的，
    不需要也不应该再去猜相邻题。
    """
    r = doc_result.report
    assert r["answersMatched"] >= 30
    exact = [q for q in doc_result.questions if q.answer_source == AS_DOC]
    assert len(exact) >= 25, f"精确匹配应占多数，实际 {len(exact)}"
    inferred = [q for q in doc_result.questions if q.answer_source == AS_DOC_INFERRED]
    assert inferred == [], "分段对齐后不应再产生就近推断的答案"


def test_answer_alignment_not_shifted(doc_result):
    """抽查：答案必须与其解析正文对应，不能整体错位。"""
    q1 = _find(doc_result, "语言理解", 1)
    assert q1 is not None and q1.answers == ["B"]
    assert "莫衷一是" in q1.explanations[0].content

    q2 = _find(doc_result, "语言理解", 2)
    assert q2 is not None and q2.answers == ["C"]
    assert "规模化" in q2.explanations[0].content

    # 资料分析组的题 1（题号与语言理解组重复，最容易错位）
    mat = _find(doc_result, "统计表", 1)
    assert mat is not None and mat.answers == ["C"]
    assert "1720" in mat.explanations[0].content


def test_no_answer_question_flagged(doc_result):
    """源文档缺答案的问题不能被静默放过，要能在队列里看到。"""
    no_answer = [q for q in doc_result.questions if not q.answers]
    assert no_answer
    assert all(q.review_state == "pending" for q in no_answer)


def test_tables_and_plaintext_material_kept(doc_result):
    """资料分析题的材料（表格/文字）应进入题干，不能被丢弃。"""
    joined = "\n".join(q.stem for q in doc_result.questions)
    assert "教师" in joined or "统计表" in joined or "材料" in joined
