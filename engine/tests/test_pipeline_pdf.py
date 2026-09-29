# -*- coding: utf-8 -*-
"""样例 B（PDF）解析端到端回归 —— 对应里程碑 M2 的验收标准。

验收口径（AGENTS.md M2）：
    解析出 135 题、134 条答案命中、7 道图片题标 pending_input 单列
"""
from __future__ import annotations

from engine.models import RS_PENDING_INPUT, SS_IMAGE


def test_question_count(pdf_result):
    """题号 1–135 全部要有槽位（含被图片吞掉的 7 道）。"""
    assert len(pdf_result.questions) == 135


def test_answer_coverage(pdf_result):
    """135 题中 134 题回填到答案；题 78 源文档本身就没有答案。"""
    answered = [q for q in pdf_result.questions if q.answers]
    assert len(answered) == 134

    missing = [q.display_no for q in pdf_result.questions if not q.answers]
    assert missing == [78], "唯一无答案的应是源文档就缺失的题 78"


def test_image_questions_marked_pending_input(pdf_result):
    """题面为图片的 7 道题必须标 pending_input 并挂上原图。"""
    pend = [q for q in pdf_result.questions if q.review_state == RS_PENDING_INPUT]
    assert len(pend) == 7
    assert sorted(q.display_no for q in pend) == [1, 2, 3, 21, 22, 23, 24]
    for q in pend:
        assert q.stem_source == SS_IMAGE
        assert q.stem == ""
        assert q.images, f"题 {q.display_no} 应挂有原图"
        assert q.answers, f"题 {q.display_no} 应从答案区回填到答案"


def test_image_question_answers_match_source(pdf_result):
    """这 7 道题在答案区有独立答案，必须各自回填正确。"""
    got = {
        q.display_no: q.answers[0]
        for q in pdf_result.questions
        if q.display_no in (1, 2, 3, 21, 22, 23, 24)
    }
    assert got == {1: "D", 2: "B", 3: "A", 21: "C", 22: "B", 23: "D", 24: "A"}


def test_answer_stats(pdf_result):
    r = pdf_result.report
    assert r["answersMatched"] == 134
    assert r["answersConflict"] == 0
    assert r["answersUnmatched"] == 0
    assert r["placeholderCount"] == 7


def test_groups_detected(pdf_result):
    titles = [g.title for g in pdf_result.groups]
    assert "常识判断" in titles
    assert "言语理解与表达" in titles
    assert "数量关系" in titles
    assert "判断推理" in titles
    assert len(pdf_result.groups) >= 5


def test_cross_page_option_completed(pdf_result):
    """题 5 的 D 选项被切到下一页，必须跨页拼回来。"""
    q5 = next(q for q in pdf_result.questions if q.display_no == 5)
    labels = [o.label for o in q5.options]
    assert labels == ["A", "B", "C", "D"]
    assert q5.options[3].content == "③①⑤④②"
    assert q5.answers == ["C"]


def test_noise_filtered_out(pdf_result):
    """页码与水印不能进入题干。"""
    joined = "\n".join(q.stem for q in pdf_result.questions)
    assert "offertop" not in joined
    assert "考佳卜资料网" not in joined
    assert "shop108498359" not in joined
    assert "43 / 43" not in joined


def test_stem_not_polluted_by_answer_section_header(pdf_result):
    """「答案与解析」这个分区标题不应混进任何题干。"""
    for q in pdf_result.questions:
        assert "答案与解析" not in (q.stem or "")


def test_explanation_attached(pdf_result):
    """有答案的题应带解析正文。"""
    q1 = next(q for q in pdf_result.questions if q.display_no == 4)
    assert q1.explanations
    assert "佛教" in q1.explanations[0].content


def test_explanation_images_attached(pdf_result):
    """解析区的示意图要挂到解析上（样例 B 第 64/66/67 题）。"""
    with_img = [q for q in pdf_result.questions if q.images and q.answers and not q.images[0].role == "stem"]
    assert with_img, "应存在带解析配图的题目"


def test_confidence_and_review_state(pdf_result):
    """高置信题自动通过，低置信题进人工队列，不允许全部无条件通过。"""
    ok = [q for q in pdf_result.questions if q.review_state == "ok"]
    pending = [q for q in pdf_result.questions if q.review_state == "pending"]
    assert len(ok) >= 120
    assert len(pending) <= 5
    for q in ok:
        assert q.answers and len(q.options) >= 2
