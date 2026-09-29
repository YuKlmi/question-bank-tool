# -*- coding: utf-8 -*-
"""服务层 / 持久化端到端测试。

覆盖：导入、按文档分区、校对修正、答题判分、批注、错题本、收藏、
      手动补录（图片题）、导出、备份还原、RPC 契约。

测试隔离策略：模块级 fixture 只导入一次 PDF（解析 43 页较慢），
写操作一律走 `mut` fixture —— 它复制一份数据目录再开新 Store，
避免测试之间互相污染。
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from engine.models import AS_MANUAL, RS_PENDING_INPUT


@pytest.fixture(scope="module")
def base(tmp_path_factory, pdf_sample):
    """只解析一次，供只读测试与副本来源使用。"""
    from engine.service import Store

    s = Store(tmp_path_factory.mktemp("svcdata"))
    doc = s.import_document(str(pdf_sample))
    s.conn.commit()
    yield s, doc
    s.close()


@pytest.fixture
def read(base):
    """只读使用模块级数据。"""
    return base


@pytest.fixture
def mut(tmp_path, base):
    """写操作用副本，保证隔离。"""
    from engine.service import Store

    src_store, doc = base
    src_store.conn.commit()
    dst = tmp_path / "copy"
    shutil.copytree(src_store.data_dir, dst)
    s = Store(dst)
    yield s, s.get_document(doc["id"])
    s.close()


# ---------------- 导入与分区 ----------------

def test_import_creates_document(read):
    _, doc = read
    assert doc["id"] > 0
    assert doc["question_count"] == 135
    assert doc["orig_type"] == "pdf"
    assert doc["parse_report"]["answersMatched"] == 134
    assert doc["pending_input"] == 7
    assert doc["answered_count"] == 134


def test_documents_are_partitioned(tmp_path, pdf_sample, doc_sample):
    """核心原则：题目按文档分区，不同文档的题目不混在一起。"""
    from engine.service import Store

    s = Store(tmp_path / "multi")
    try:
        d1 = s.import_document(str(pdf_sample))
        d2 = s.import_document(str(doc_sample))

        q1 = s.list_questions(d1["id"], {"pageSize": 500})
        q2 = s.list_questions(d2["id"], {"pageSize": 500})
        assert q1["total"] == 135
        assert q1["total"] != q2["total"]

        # 每个文档的 seq 独立从 0 开始
        assert [i["seq"] for i in q1["items"]][:3] == [0, 1, 2]
        assert [i["seq"] for i in q2["items"]][:3] == [0, 1, 2]

        # 删除一个文档不影响另一个
        s.delete_document(d1["id"])
        assert s.list_questions(d1["id"], {})["total"] == 0
        assert s.list_questions(d2["id"], {})["total"] > 0
    finally:
        s.close()


# ---------------- 查询与筛选 ----------------

def test_list_questions_filters(read):
    s, doc = read
    did = doc["id"]

    assert s.list_questions(did, {"hasAnswer": True})["total"] == 134
    assert s.list_questions(did, {"hasAnswer": False})["total"] == 1

    pend = s.list_questions(did, {"reviewState": RS_PENDING_INPUT})
    assert pend["total"] == 7
    assert sorted(i["display_no"] for i in pend["items"]) == [1, 2, 3, 21, 22, 23, 24]

    assert s.list_questions(did, {"groupSeq": 1})["total"] > 0


def test_pagination(read):
    s, doc = read
    page1 = s.list_questions(doc["id"], {"page": 1, "pageSize": 10})
    page2 = s.list_questions(doc["id"], {"page": 2, "pageSize": 10})
    assert len(page1["items"]) == 10
    assert page1["items"][0]["id"] != page2["items"][0]["id"]


def test_keyword_search(read):
    s, doc = read
    assert s.list_questions(doc["id"], {"keyword": "热带雨林"})["total"] >= 1


def test_get_question_full_payload(read):
    s, doc = read
    q5 = next(i for i in s.list_questions(doc["id"], {"pageSize": 500})["items"]
              if i["display_no"] == 5)
    full = s.get_question(q5["id"])
    assert [o["label"] for o in full["options"]] == ["A", "B", "C", "D"]
    assert full["answer"] == ["C"]
    assert full["explanations"]
    assert full["annotations"] == []
    assert full["review"]["starred"] == 0


# ---------------- 校对与手动录入 ----------------

def test_update_question_marks_fixed(mut):
    s, doc = mut
    item = s.list_questions(doc["id"], {"pageSize": 500})["items"][100]
    updated = s.update_question(item["id"], {"stem": "修改后的题干"})
    assert updated["stem"] == "修改后的题干"
    assert updated["review_state"] == "fixed"


def test_manual_answer_not_overwritten_by_source(mut):
    """手动录入的答案优先级最高，重新解析也不能覆盖。"""
    s, doc = mut
    item = s.list_questions(doc["id"], {"pageSize": 500})["items"][10]
    s.set_answer(item["id"], "B", source=AS_MANUAL)
    got = s.get_question(item["id"])
    assert got["answer"] == ["B"]
    assert got["answer_source"] == AS_MANUAL


def test_manual_question_creation_for_image_question(mut):
    """图片题的核心流程：用户照原图手动补录题干与选项。"""
    s, doc = mut
    pend = s.list_questions(doc["id"], {"reviewState": RS_PENDING_INPUT})["items"]
    target = pend[0]
    img_ids = [i["id"] for i in s.list_images(doc["id"]) if i["question_id"] == target["id"]]
    assert img_ids, "图片题应已关联原图"

    created = s.update_question(target["id"], {
        "stem": "（手动录入）关于党风建设的创新，按时间先后顺序排列正确的是",
        "type": "single",
        "options": [{"label": "A", "content": "①③②④"}, {"label": "B", "content": "③②④①"},
                    {"label": "C", "content": "③①④②"}, {"label": "D", "content": "①③④②"}],
        "answer": "A",
    })
    assert created["stem"].startswith("（手动录入）")
    assert len(created["options"]) == 4
    assert created["answer"] == ["A"]
    assert created["review_state"] == "fixed"


def test_create_question_from_scratch(mut):
    """完全不依赖解析结果，手动新建一道题。"""
    s, doc = mut
    created = s.create_question(doc["id"], {
        "stem": "自建题目：1+1=?",
        "options": [{"label": "A", "content": "1"}, {"label": "B", "content": "2"}],
        "answer": "B",
    })
    assert created["stem"].startswith("自建题目")
    assert created["answer_source"] == AS_MANUAL
    assert s.list_questions(doc["id"], {})["total"] == 136


# ---------------- 答题与判分 ----------------

def test_submit_answer_correct_and_wrong(mut):
    s, doc = mut
    item = s.list_questions(doc["id"], {"hasAnswer": True, "pageSize": 5})["items"][0]
    q = s.get_question(item["id"])
    right = q["answer"][0]
    assert s.submit_answer(item["id"], right)["correct"] is True

    wrong = "B" if right != "B" else "C"
    assert s.submit_answer(item["id"], wrong)["correct"] is False


def test_wrong_answer_enters_wrongbook(mut):
    s, doc = mut
    item = s.list_questions(doc["id"], {"hasAnswer": True, "pageSize": 5})["items"][1]
    q = s.get_question(item["id"])
    wrong = "B" if q["answer"][0] != "B" else "C"
    s.submit_answer(item["id"], wrong)

    book = s.list_wrongbook(doc["id"])
    assert book["total"] >= 1
    assert any(i["id"] == item["id"] for i in book["items"])
    assert all(i["doc_name"] for i in book["items"])


def test_wrongbook_cross_document_filter(tmp_path, pdf_sample, doc_sample):
    """错题本跨文档汇总，但可按来源文档筛选。"""
    from engine.service import Store

    s = Store(tmp_path / "wb")
    try:
        d1 = s.import_document(str(pdf_sample))
        d2 = s.import_document(str(doc_sample))
        i1 = s.list_questions(d1["id"], {"hasAnswer": True, "pageSize": 3})["items"]
        q1 = s.get_question(i1[0]["id"])
        s.submit_answer(i1[0]["id"], "B" if q1["answer"][0] != "B" else "C")

        all_book = s.list_wrongbook()
        one_book = s.list_wrongbook(d1["id"])
        assert all_book["total"] >= one_book["total"] >= 1
        assert all(x["doc_id"] == d1["id"] for x in one_book["items"])
    finally:
        s.close()


def test_self_assess_essay(mut):
    s, doc = mut
    item = s.list_questions(doc["id"], {"pageSize": 5})["items"][0]
    assert s.self_assess(item["id"], "模糊")["level"] == "模糊"
    assert s.self_assess(item["id"], "不会")["review"]["in_wrongbook"] == 1


def test_practice_pick_modes(mut):
    s, doc = mut
    assert len(s.practice_pick(doc["id"], "sequence", limit=5)) == 5
    assert len(s.practice_pick(doc["id"], "random", limit=5)) == 5

    expected = s.list_questions(doc["id"], {"reviewState": RS_PENDING_INPUT})["total"]
    assert len(s.practice_pick(doc["id"], "pending", limit=50)) == expected


# ---------------- 收藏 / 标签 ----------------

def test_star_toggle(mut):
    s, doc = mut
    item = s.list_questions(doc["id"], {"pageSize": 5})["items"][2]
    assert s.toggle_star(item["id"])["starred"] == 1
    assert s.toggle_star(item["id"])["starred"] == 0


def test_tags(mut):
    s, doc = mut
    item = s.list_questions(doc["id"], {"pageSize": 5})["items"][3]
    assert s.set_tags(item["id"], ["重点", "易错"])["tags"] == ["重点", "易错"]


# ---------------- 批注 ----------------

def test_annotation_crud(mut):
    s, doc = mut
    item = s.list_questions(doc["id"], {"pageSize": 5})["items"][4]

    a = s.create_annotation(item["id"], "这题的关键是看时序", "note", "#f56c6c")
    assert a["id"] > 0
    assert len(s.list_annotations(item["id"])) == 1

    s.update_annotation(a["id"], "改写后的批注")
    assert s.list_annotations(item["id"])[0]["content"] == "改写后的批注"

    s.delete_annotation(a["id"])
    assert s.list_annotations(item["id"]) == []


def test_annotation_requires_existing_question(mut):
    s, _ = mut
    with pytest.raises(KeyError):
        s.create_annotation(999999, "不存在")


# ---------------- 导出 ----------------

def test_export_markdown(read):
    s, doc = read
    md = s.export_markdown(doc["id"])["content"]
    assert "**答案**" in md
    assert "热带雨林" in md


def test_export_csv(read, tmp_path):
    s, doc = read
    out = tmp_path / "export.csv"
    s.export_csv(doc["id"], str(out))
    assert out.exists()
    text = out.read_text(encoding="utf-8-sig")
    assert "题干" in text
    assert len(text.splitlines()) > 100


# ---------------- 备份 / 还原 ----------------

def test_backup_and_restore(mut):
    s, doc = mut
    b = s.backup()
    assert Path(b["path"]).exists()

    listing = s.list_backups()
    assert any(x["name"] == b["name"] for x in listing)
    assert all(x["db_file"] for x in listing)

    item = s.list_questions(doc["id"], {"pageSize": 5})["items"][0]
    s.update_question(item["id"], {"stem": "还原前被改坏的题干"})
    assert s.get_question(item["id"])["stem"] == "还原前被改坏的题干"

    s.restore(b["path"])
    assert s.get_question(item["id"])["stem"] != "还原前被改坏的题干"


def test_backup_survives_delete(tmp_path, pdf_sample):
    """删库后从备份还原，题目要回来（验证备份真的可用）。"""
    from engine.service import Store

    s = Store(tmp_path / "bk2")
    try:
        doc = s.import_document(str(pdf_sample))
        b = s.backup()
        s.delete_document(doc["id"])
        assert s.list_questions(doc["id"], {})["total"] == 0

        s.restore(b["path"])
        docs = s.list_documents()
        assert len(docs) == 1
        assert s.list_questions(docs[0]["id"], {})["total"] == 135
    finally:
        s.close()


# ---------------- 设置 ----------------

def test_settings(mut):
    s, _ = mut
    s.update_settings({"theme": "dark", "autoRemoveWrongAfter": 3})
    got = s.get_settings()
    assert got["theme"] == "dark"
    assert got["autoRemoveWrongAfter"] == 3


def test_templates_listed(read):
    s, _ = read
    ids = {t["id"] for t in s.templates()}
    assert {"pdf-consolidated", "docx-mixed"} <= ids


def test_original_comments_table_exists(read):
    """样例实测批注为 0，但接口必须存在（其他文档可能有）。"""
    s, doc = read
    n = s.conn.execute("SELECT COUNT(*) c FROM doc_comments WHERE doc_id=?", (doc["id"],)).fetchone()
    assert n["c"] >= 0


# ---------------- RPC 契约 ----------------

def test_rpc_routes_cover_service(tmp_path):
    from engine.rpc import build_routes
    from engine.service import Store

    s = Store(tmp_path / "rpcdata")
    try:
        routes = build_routes(s)
        for m in ["system.ping", "system.info", "doc.import", "doc.list", "doc.get",
                  "doc.delete", "doc.groups", "question.list", "question.get",
                  "question.update", "question.create", "practice.pick",
                  "practice.submit", "practice.selfAssess", "wrongbook.list",
                  "wrongbook.set", "review.star", "review.tags", "annotation.list",
                  "annotation.create", "annotation.update", "annotation.delete",
                  "image.list", "export.markdown", "export.csv", "settings.get",
                  "settings.update", "backup.create", "backup.list", "backup.restore",
                  "doc.reparse", "question.setAnswer", "question.delete"]:
            assert m in routes, f"缺少 RPC 方法: {m}"
    finally:
        s.close()


def test_rpc_parameterless_routes_are_callable(tmp_path):
    """回归：handle() 统一以 fn(params) 调用，零参路由会抛 TypeError。"""
    from engine.rpc import build_routes, handle
    from engine.service import Store

    s = Store(tmp_path / "arity")
    try:
        routes = build_routes(s)
        for m in ["system.ping", "system.info", "system.paths", "doc.list",
                  "settings.get", "backup.list"]:
            resp = handle(routes, {"id": 1, "method": m, "params": {}})
            assert resp["ok"] is True, f"{m} 调用失败: {resp.get('error')}"
    finally:
        s.close()


def test_no_route_has_arity_mismatch(tmp_path):
    """遍历所有路由：允许因缺参数报 KeyError，但不允许参数个数不匹配。"""
    from engine.rpc import build_routes, handle
    from engine.service import Store

    s = Store(tmp_path / "arity2")
    try:
        routes = build_routes(s)
        assert len(routes) >= 30
        for m in routes:
            resp = handle(routes, {"id": 1, "method": m, "params": {}})
            if not resp["ok"]:
                assert resp["error"]["type"] != "TypeError", \
                    f"{m} 参数契约不一致: {resp['error']['message']}"
    finally:
        s.close()


def test_rpc_handle_error_is_structured():
    from engine.rpc import handle

    def boom(_):
        raise ValueError("炸了")

    routes = {"boom": boom}
    resp = handle(routes, {"id": 7, "method": "boom", "params": {}})
    assert resp["id"] == 7 and resp["ok"] is False
    assert resp["error"]["type"] == "ValueError"
    assert "炸了" in resp["error"]["message"]

    missing = handle(routes, {"id": 8, "method": "nope"})
    assert missing["ok"] is False
    assert missing["error"]["type"] == "MethodNotFound"


def test_rpc_end_to_end_over_stdio(tmp_path, pdf_sample):
    """真跑一次子进程协议，验证 stdout 只承载 JSON（能被逐行解析）。"""
    import json
    import subprocess
    import sys

    repo_root = Path(__file__).resolve().parents[2]
    data_dir = tmp_path / "stdio"
    proc = subprocess.Popen(
        [sys.executable, "-m", "engine.rpc", "--data-dir", str(data_dir)],
        cwd=str(repo_root), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True, encoding="utf-8",
    )
    try:
        def call(method, params=None):
            proc.stdin.write(json.dumps({"id": 1, "method": method, "params": params or {}}) + "\n")
            proc.stdin.flush()
            return json.loads(proc.stdout.readline())

        assert call("system.ping")["result"]["pong"] is True
        assert call("doc.list")["result"] == []

        r = call("doc.import", {"path": str(pdf_sample)})
        assert r["ok"] is True, r
        assert r["result"]["question_count"] == 135
    finally:
        proc.stdin.close()
        proc.wait(timeout=30)
