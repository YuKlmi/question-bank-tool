# -*- coding: utf-8 -*-
"""样例 C（EPI 综合能力测试 PDF）端到端回归。

这份样卷暴露了三类此前没覆盖的问题，本文件就是它们的回归护栏：
1. 卷首「注意事项」里的 `1. 监考老师宣布考试开始时…` 会被误判成题 1
2. 答案写法在同一份卷子里混用了 8 种，还存在「一行 10 个答案」的排法
3. 题号在题目区与答案区**都按大题组重置**，全局按题号匹配必然错位
"""
from __future__ import annotations

from pathlib import Path

import pytest

from engine.models import RS_PENDING_INPUT, SS_IMAGE

EPI_SAMPLE = (Path(__file__).resolve().parents[2] / "samples"
              / "招聘考试全真模拟EPI综合能力测试（二）.pdf")


@pytest.fixture(scope="module")
def epi_result():
    if not EPI_SAMPLE.exists():
        pytest.skip(f"缺少样例: {EPI_SAMPLE}")
    from engine.pipeline import parse
    import tempfile

    return parse(EPI_SAMPLE, Path(tempfile.mkdtemp(prefix="epi_")))


# ---------------- 卷首须知 ----------------

def test_exam_notice_not_parsed_as_question(epi_result):
    """「注意事项」区间必须整体排除，不能产出假题、也不能与正文题重号。"""
    joined = "\n".join(q.stem for q in epi_result.questions)
    assert "监考老师" not in joined
    assert "答题卡" not in joined
    assert "2B 铅笔" not in joined
    assert "请仔细阅读" not in joined


def test_no_fake_question_number_one(epi_result):
    """须知里那个 `1.` 被排除后，语言理解组的题 1 才是真正的第 1 题。"""
    first = epi_result.questions[0]
    assert first.display_no == 1
    assert first.stem.startswith("人生是一个容器")


# ---------------- 题目规模 ----------------

def test_question_count(epi_result):
    """语言理解 15 + 数学能力 20 + 判断推理 15 + 材料分析 10 = 60。"""
    assert len(epi_result.questions) == 60


def test_groups(epi_result):
    titles = [g.title for g in epi_result.groups]
    assert any("语言理解" in t for t in titles)
    assert any("数学能力" in t for t in titles)
    assert any("判断推理" in t for t in titles)
    assert any("材料分析" in t for t in titles)


def test_bracket_question_no_recognized(epi_result):
    """数字推理题用【16】这种题号，必须识别为第 16 题。"""
    q16 = next(q for q in epi_result.questions if q.display_no == 16)
    assert q16.stem.startswith("4，2，2，3，6")


def test_question_no_followed_by_digits(epi_result):
    """`2．1984 年消耗…` / `27.5 年前甲…` 不能被当成小数而漏掉。"""
    q2 = next(q for q in epi_result.questions
              if q.display_no == 2 and "天然气" in q.stem)
    assert q2.options and len(q2.options) == 4

    q27 = next((q for q in epi_result.questions
                if q.display_no == 27 and "甲" in q.stem), None)
    assert q27 is not None, "题号后紧跟数字的题被漏掉了"


def test_table_numbers_not_parsed_as_question(epi_result):
    """材料区表格里的 786.02 / 3120.84 之类不能变成题号。"""
    for q in epi_result.questions:
        assert not (q.stem.strip().startswith(".") or q.stem.strip()[:1].isdigit()
                    and "." in q.stem[:6] and len(q.stem) < 12), \
            f"疑似表格数值被当成题目: {q.stem[:20]!r}"


def test_five_options_supported(epi_result):
    """判断推理部分是 A–E 五个选项。"""
    q = next(q for q in epi_result.questions
             if q.display_no == 7 and len(q.options) == 5)
    assert [o.label for o in q.options] == ["A", "B", "C", "D", "E"]


def test_options_split_by_semicolon(epi_result):
    """`A、6；B、8；C、10；D、15；` 这种分号分隔也要切出 4 个选项。"""
    q16 = next(q for q in epi_result.questions if q.display_no == 16)
    assert [o.label for o in q16.options] == ["A", "B", "C", "D"]
    assert q16.options[3].content.rstrip("；;") == "15"


# ---------------- 答案区 ----------------

def test_answer_coverage_full(epi_result):
    """分段对齐后，60 道题应全部拿到答案。"""
    answered = [q for q in epi_result.questions if q.answers]
    assert len(answered) == 60
    r = epi_result.report
    assert r["answersMatched"] == 60
    assert r["answersConflict"] == 0
    assert r["answersUnmatched"] == 0


def test_answer_alignment_across_reset_sections(epi_result):
    """题号按大题组重置，答案仍要落到正确的那一道题上。"""
    def pick(group_kw: str, no: int):
        for q in epi_result.questions:
            g = next((g for g in epi_result.groups if g.seq == q.group_seq), None)
            if g and group_kw in g.title and q.display_no == no:
                return q
        return None

    # 语言理解 题1：解析讲“有限/勇气”，答案 C
    q = pick("语言理解", 1)
    assert q is not None and q.answers == ["C"]
    assert "有限" in q.explanations[0].content

    # 数学能力 题16：数字推理，答案是 D
    q = pick("数学能力", 16)
    assert q is not None and q.answers == ["D"]

    # 判断推理 题8：答案在「一行 10 个答案」的排布里，是 E
    q = pick("判断推理", 8)
    assert q is not None and q.answers == ["E"], "一行多答案的排布解析错位"

    # 材料分析第二组的题 6：换行式 `6.【答案】B。`
    q = pick("西部", 6)
    assert q is not None and q.answers == ["B"]
    assert "贵州" in q.explanations[0].content


def test_image_questions_placeholder(epi_result):
    """判断推理 1–5 的题面是整页图，应补出占位题并挂图。"""
    pend = [q for q in epi_result.questions if q.review_state == RS_PENDING_INPUT]
    assert len(pend) == 5
    for q in pend:
        assert q.stem_source == SS_IMAGE
        assert q.images, f"题 {q.display_no} 应挂上原图"
    # 这些题在答案区也有答案，必须已经回填
    assert all(q.answers for q in pend)
