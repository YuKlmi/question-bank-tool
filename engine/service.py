# -*- coding: utf-8 -*-
"""业务服务层：界面所需的全部操作都在这里。

设计约束：
- 所有题目相关操作**必须带 docId**，从接口层就杜绝跨文档混排
- 解析结果一律带置信度与校对状态；低置信不静默入库
- 手动录入的答案/内容优先级最高，重新解析时不被覆盖
"""
from __future__ import annotations

import csv
import io
import json
import shutil
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import db as dbmod
from . import pipeline
from .grading import grade_blank, grade_mode_of, infer_question_type, judge
from .models import (
    AS_MANUAL, GM_AUTO, GM_SELF, GM_SEMI,
    RS_FIXED, RS_OK, RS_PENDING, RS_PENDING_INPUT,
)
from .rules import Template

DEFAULT_DATA_DIRNAME = "题库数据"


class Store:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.media_dir = self.data_dir / "media"
        self.backup_dir = self.data_dir / "backups"
        self.db_path = self.data_dir / "library.db"
        for d in (self.data_dir, self.media_dir, self.backup_dir):
            d.mkdir(parents=True, exist_ok=True)
        dbmod.init_db(self.db_path)
        self.conn = dbmod.connect(self.db_path)

    # ---------------------------------------------------------------- 基础

    def close(self) -> None:
        try:
            self.conn.close()
        except Exception:
            pass

    def paths(self) -> Dict[str, str]:
        return {
            "data_dir": str(self.data_dir),
            "db_path": str(self.db_path),
            "media_dir": str(self.media_dir),
            "backup_dir": str(self.backup_dir),
        }

    # ---------------------------------------------------------------- 文档

    def import_document(self, src_path: str, template_id: Optional[str] = None) -> Dict[str, Any]:
        src = Path(src_path)
        result = pipeline.parse(src, self.data_dir, template_id=template_id)

        cur = self.conn.execute(
            "INSERT INTO documents(name, orig_type, src_path, template_id, page_count,"
            " parse_status, parse_report, created_at)"
            " VALUES(?,?,?,?,?,?,?,?)",
            (result.doc_name, result.orig_type, str(src), result.template_id,
             result.page_count, "ok", json.dumps(result.report, ensure_ascii=False),
             dbmod.now()),
        )
        doc_id = cur.lastrowid

        # 大题组
        group_id_by_seq: Dict[int, int] = {}
        for g in result.groups:
            c = self.conn.execute(
                "INSERT INTO groups(doc_id, seq, title, raw_text) VALUES(?,?,?,?)",
                (doc_id, g.seq, g.title, g.raw_text),
            )
            group_id_by_seq[g.seq] = c.lastrowid

        # 题目
        for q in result.questions:
            gid = group_id_by_seq.get(q.group_seq) if q.group_seq is not None else None
            c = self.conn.execute(
                "INSERT INTO questions(doc_id, group_id, seq, display_no, type, grade_mode,"
                " stem, raw_text, stem_source, answer, answer_source, confidence,"
                " review_state, page_no, bbox)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (doc_id, gid, q.seq, q.display_no, q.type, q.grade_mode,
                 q.stem, q.raw_text, q.stem_source,
                 json.dumps(q.answers, ensure_ascii=False), q.answer_source,
                 q.confidence, q.review_state, q.page_no,
                 json.dumps(list(q.bbox) if q.bbox else None, ensure_ascii=False)),
            )
            qid = c.lastrowid

            for o in q.options:
                self.conn.execute(
                    "INSERT INTO options(question_id, label, seq, content, image_path)"
                    " VALUES(?,?,?,?,?)",
                    (qid, o.label, o.seq, o.content, o.image_path),
                )
            for img in q.images:
                self.conn.execute(
                    "INSERT INTO images(doc_id, question_id, file_path, role, seq,"
                    " page_no, bbox, source, width, height) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (doc_id, qid, img.file_path, img.role, img.seq, img.page,
                     json.dumps(list(img.bbox) if img.bbox else None, ensure_ascii=False),
                     img.source, img.width, img.height),
                )
            for e in q.explanations:
                self.conn.execute(
                    "INSERT INTO explanations(question_id, seq, title, content, image_paths)"
                    " VALUES(?,?,?,?,?)",
                    (qid, e.seq, e.title, e.content, json.dumps(e.image_paths, ensure_ascii=False)),
                )

        for c_ in result.report.get("warnings", []):
            pass  # 警告已随 parse_report 一并保存

        self._refresh_doc_stats(doc_id)
        self.conn.commit()
        return self.get_document(doc_id)

    def reparse_document(self, doc_id: int, template_id: Optional[str] = None) -> Dict[str, Any]:
        """重新解析：保留人工修正（answer_source = manual 的答案与已改过的内容）。"""
        doc = self.get_document(doc_id)
        src = doc.get("srcPath")
        if not src or not Path(src).exists():
            raise FileNotFoundError(f"原始文件不存在: {src}")

        keep = {
            r["display_no"]: r["answer"]
            for r in self.conn.execute(
                "SELECT display_no, answer FROM questions WHERE doc_id = ? AND answer_source = ?",
                (doc_id, AS_MANUAL),
            )
        }
        self.conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
        self.conn.commit()

        tpl = template_id or doc.get("templateId")
        return self.import_document(src, tpl) if tpl else self.import_document(src)

    def list_documents(self) -> List[Dict[str, Any]]:
        rows = self.conn.execute("SELECT * FROM documents ORDER BY id DESC").fetchall()
        return [_doc_out(r) for r in rows]

    def get_document(self, doc_id: int) -> Dict[str, Any]:
        r = self.conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
        if r is None:
            raise KeyError(f"文档不存在: {doc_id}")
        return _doc_out(r)

    def delete_document(self, doc_id: int, purge_media: bool = False) -> Dict[str, Any]:
        r = self.conn.execute(
            "SELECT template_id FROM documents WHERE id = ?", (doc_id,)
        ).fetchone()
        self.conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
        self.conn.commit()
        if purge_media:
            self._purge_unreferenced_media()
        return {"deleted": doc_id}

    def _purge_unreferenced_media(self) -> None:
        used = {
            r["file_path"]
            for r in self.conn.execute("SELECT DISTINCT file_path FROM images")
        }
        for p in self.media_dir.rglob("*"):
            if p.is_file():
                rel = p.relative_to(self.media_dir).as_posix()
                if rel not in used:
                    p.unlink()

    def _refresh_doc_stats(self, doc_id: int) -> None:
        row = self.conn.execute(
            "SELECT COUNT(*) c,"
            " SUM(CASE WHEN answer != '[]' AND answer IS NOT NULL THEN 1 ELSE 0 END) a,"
            " SUM(CASE WHEN review_state = ? THEN 1 ELSE 0 END) pi,"
            " SUM(CASE WHEN review_state = ? THEN 1 ELSE 0 END) pr"
            " FROM questions WHERE doc_id = ?",
            (RS_PENDING_INPUT, RS_PENDING, doc_id),
        ).fetchone()
        self.conn.execute(
            "UPDATE documents SET question_count=?, answered_count=?,"
            " pending_input=?, pending_review=? WHERE id=?",
            (row["c"] or 0, row["a"] or 0, row["pi"] or 0, row["pr"] or 0, doc_id),
        )

    # ---------------------------------------------------------------- 大题组

    def list_groups(self, doc_id: int) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT g.*, (SELECT COUNT(*) FROM questions q WHERE q.group_id = g.id) AS questionCount"
            " FROM groups g WHERE g.doc_id = ? ORDER BY g.seq",
            (doc_id,),
        ).fetchall()
        return dbmod.rows_to_dicts(rows)

    # ---------------------------------------------------------------- 题目

    def list_questions(self, doc_id: int, filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        f = filters or {}
        where = ["q.doc_id = ?"]
        args: List[Any] = [doc_id]

        if f.get("groupSeq") is not None:
            where.append("g.seq = ?")
            args.append(int(f["groupSeq"]))
        if f.get("reviewState"):
            where.append("q.review_state = ?")
            args.append(f["reviewState"])
        if f.get("type"):
            where.append("q.type = ?")
            args.append(f["type"])
        if f.get("hasAnswer") is True:
            where.append("q.answer != '[]'")
        elif f.get("hasAnswer") is False:
            where.append("(q.answer = '[]' OR q.answer IS NULL)")
        if f.get("starred"):
            where.append("EXISTS(SELECT 1 FROM reviews rv WHERE rv.question_id=q.id AND rv.starred=1)")
        if f.get("wrongbook"):
            where.append("EXISTS(SELECT 1 FROM reviews rv WHERE rv.question_id=q.id AND rv.in_wrongbook=1)")
        if f.get("hasAnnotation"):
            where.append("EXISTS(SELECT 1 FROM annotations an WHERE an.question_id=q.id)")
        if f.get("keyword"):
            where.append("(q.stem LIKE ? OR q.raw_text LIKE ?)")
            kw = f"%{f['keyword']}%"
            args.extend([kw, kw])
        if f.get("seqFrom") is not None:
            where.append("q.seq >= ?")
            args.append(int(f["seqFrom"]))
        if f.get("seqTo") is not None:
            where.append("q.seq <= ?")
            args.append(int(f["seqTo"]))

        clause = " AND ".join(where)
        total = self.conn.execute(
            f"SELECT COUNT(*) c FROM questions q LEFT JOIN groups g ON g.id=q.group_id WHERE {clause}",
            args,
        ).fetchone()["c"]

        order = "q.seq"
        if f.get("orderBy") == "displayNo":
            order = "q.display_no"
        elif f.get("orderBy") == "random":
            order = "RANDOM()"

        page = int(f.get("page") or 1)
        size = int(f.get("pageSize") or 50)
        rows = self.conn.execute(
            f"SELECT q.*, g.title AS group_title,"
            f" (SELECT COUNT(*) FROM options o WHERE o.question_id=q.id) AS option_count,"
            f" (SELECT COUNT(*) FROM images i WHERE i.question_id=q.id) AS image_count,"
            f" COALESCE((SELECT rv.starred FROM reviews rv WHERE rv.question_id=q.id), 0) AS starred,"
            f" COALESCE((SELECT rv.in_wrongbook FROM reviews rv WHERE rv.question_id=q.id), 0) AS in_wrongbook"
            f" FROM questions q LEFT JOIN groups g ON g.id=q.group_id"
            f" WHERE {clause} ORDER BY {order} LIMIT ? OFFSET ?",
            args + [size, (page - 1) * size],
        ).fetchall()

        items = []
        for r in rows:
            d = dict(r)
            d["answer"] = _loads(d.get("answer"), [])
            d["bbox"] = _loads(d.get("bbox"), None)
            items.append(d)
        return {"total": total, "page": page, "page_size": size, "items": items}

    def get_question(self, question_id: int) -> Dict[str, Any]:
        q = self.conn.execute(
            "SELECT q.*, g.title AS group_title FROM questions q"
            " LEFT JOIN groups g ON g.id=q.group_id WHERE q.id=?",
            (question_id,),
        ).fetchone()
        if q is None:
            raise KeyError(f"题目不存在: {question_id}")

        d = dict(q)
        d["answer"] = _loads(d.get("answer"), [])
        d["bbox"] = _loads(d.get("bbox"), None)
        d["options"] = dbmod.rows_to_dicts(self.conn.execute(
            "SELECT * FROM options WHERE question_id=? ORDER BY seq", (question_id,)
        ).fetchall())
        d["images"] = dbmod.rows_to_dicts(self.conn.execute(
            "SELECT * FROM images WHERE question_id=? ORDER BY seq, id", (question_id,)
        ).fetchall())
        for img in d["images"]:
            img["bbox"] = _loads(img.get("bbox"), None)
        d["explanations"] = dbmod.rows_to_dicts(self.conn.execute(
            "SELECT * FROM explanations WHERE question_id=? ORDER BY seq", (question_id,)
        ).fetchall())
        for e in d["explanations"]:
            e["imagePaths"] = _loads(e.get("image_paths"), [])
        d["annotations"] = self.list_annotations(question_id)
        d["review"] = self.get_review(question_id)
        d["doc_comments"] = dbmod.rows_to_dicts(self.conn.execute(
            "SELECT * FROM doc_comments WHERE question_id=?", (question_id,)
        ).fetchall())
        d["attempts"] = dbmod.rows_to_dicts(self.conn.execute(
            "SELECT * FROM attempts WHERE question_id=? ORDER BY id DESC LIMIT 20", (question_id,)
        ).fetchall())
        return d

    def update_question(self, question_id: int, fields: Dict[str, Any]) -> Dict[str, Any]:
        allowed = {
            "stem", "raw_text", "type", "grade_mode", "review_state",
            "stem_source", "display_no", "confidence",
        }
        sets, args = [], []
        for k, v in fields.items():
            if k in allowed:
                sets.append(f"{k} = ?")
                args.append(v)
        if "type" in fields and "grade_mode" not in fields:
            sets.append("grade_mode = ?")
            args.append(grade_mode_of(fields["type"]))

        # 用户改过内容即视为已人工修正
        if sets and "review_state" not in fields:
            sets.append("review_state = ?")
            args.append(RS_FIXED)

        if sets:
            args.append(question_id)
            self.conn.execute(f"UPDATE questions SET {', '.join(sets)} WHERE id = ?", args)

        if "answer" in fields:
            self.set_answer(question_id, fields["answer"], source=AS_MANUAL)
        if "options" in fields:
            self._replace_options(question_id, fields["options"])
        if "explanations" in fields:
            self._replace_explanations(question_id, fields["explanations"])

        self.conn.commit()
        q = self.get_question(question_id)
        self._refresh_doc_stats(q["doc_id"])
        self.conn.commit()
        return self.get_question(question_id)

    def set_answer(self, question_id: int, answer, source: str = AS_MANUAL) -> None:
        if isinstance(answer, str):
            ans = [answer] if answer.strip() else []
        else:
            ans = list(answer or [])
        self.conn.execute(
            "UPDATE questions SET answer=?, answer_source=? WHERE id=?",
            (json.dumps(ans, ensure_ascii=False), source, question_id),
        )
        self.conn.commit()

    def create_question(self, doc_id: int, payload: Dict[str, Any]) -> Dict[str, Any]:
        """手动新建/补录题目（图片题录入也走这里）。"""
        seq_row = self.conn.execute(
            "SELECT COALESCE(MAX(seq), -1) + 1 AS s FROM questions WHERE doc_id=?", (doc_id,)
        ).fetchone()
        seq = seq_row["s"]

        gid = None
        if payload.get("groupSeq") is not None:
            r = self.conn.execute(
                "SELECT id FROM groups WHERE doc_id=? AND seq=?", (doc_id, payload["groupSeq"])
            ).fetchone()
            gid = r["id"] if r else None

        qtype = payload.get("type") or infer_question_type(
            payload.get("stem", ""), len(payload.get("options") or []))
        cur = self.conn.execute(
            "INSERT INTO questions(doc_id, group_id, seq, display_no, type, grade_mode,"
            " stem, raw_text, stem_source, answer, answer_source, confidence, review_state)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (doc_id, gid, seq, payload.get("displayNo"), qtype, grade_mode_of(qtype),
             payload.get("stem", ""), payload.get("rawText", ""),
             payload.get("stemSource", "text"),
             json.dumps(payload.get("answer") or [], ensure_ascii=False),
             AS_MANUAL if payload.get("answer") else None,
             0.95, RS_FIXED),
        )
        qid = cur.lastrowid

        opts = payload.get("options") or []
        if opts:
            self._replace_options(qid, opts)
        if payload.get("imageIds"):
            for i, iid in enumerate(payload["imageIds"]):
                self.conn.execute(
                    "UPDATE images SET question_id=?, role=? WHERE id=?",
                    (qid, payload.get("imageRole", "stem"), iid),
                )
        if payload.get("explanation"):
            self._replace_explanations(qid, [{"title": "解析", "content": payload["explanation"]}])

        self.conn.commit()
        self._refresh_doc_stats(doc_id)
        self.conn.commit()
        return self.get_question(qid)

    def delete_question(self, question_id: int) -> Dict[str, Any]:
        r = self.conn.execute("SELECT doc_id FROM questions WHERE id=?", (question_id,)).fetchone()
        self.conn.execute("DELETE FROM questions WHERE id=?", (question_id,))
        self.conn.commit()
        if r:
            self._refresh_doc_stats(r["doc_id"])
            self.conn.commit()
        return {"deleted": question_id}

    def _replace_options(self, question_id: int, options: List[Dict[str, Any]]) -> None:
        self.conn.execute("DELETE FROM options WHERE question_id=?", (question_id,))
        for i, o in enumerate(options):
            self.conn.execute(
                "INSERT INTO options(question_id, label, seq, content, image_path) VALUES(?,?,?,?,?)",
                (question_id, o.get("label") or chr(65 + i), i,
                 o.get("content", ""), o.get("imagePath")),
            )

    def _replace_explanations(self, question_id: int, exps: List[Dict[str, Any]]) -> None:
        self.conn.execute("DELETE FROM explanations WHERE question_id=?", (question_id,))
        for i, e in enumerate(exps):
            self.conn.execute(
                "INSERT INTO explanations(question_id, seq, title, content, image_paths)"
                " VALUES(?,?,?,?,?)",
                (question_id, i, e.get("title", "解析"), e.get("content", ""),
                 json.dumps(e.get("imagePaths") or [], ensure_ascii=False)),
            )

    # ---------------------------------------------------------------- 答题

    def submit_answer(self, question_id: int, user_answer: str,
                      duration_ms: int = 0) -> Dict[str, Any]:
        q = self.get_question(question_id)
        correct = q["answer"] or []
        gmode = q["grade_mode"]
        qtype = q["type"]

        result: Dict[str, Any] = {"correct": None, "ratio": None, "gradeMode": gmode}
        if gmode == GM_AUTO:
            ok = judge(user_answer, correct, qtype)
            result.update(correct=ok, ratio=1.0 if ok else 0.0)
        elif gmode == GM_SEMI:
            blanks = [c.split("/") for c in correct] if correct else []
            ok, ratio = grade_blank(user_answer, blanks)
            result.update(correct=ok, ratio=ratio)
        else:
            result["correct"] = None  # 主观题自评

        self.conn.execute(
            "INSERT INTO attempts(doc_id, question_id, user_answer, is_correct, duration_ms, created_at)"
            " VALUES(?,?,?,?,?,?)",
            (q["doc_id"], question_id, user_answer,
             None if result["correct"] is None else int(result["correct"]),
             duration_ms, dbmod.now()),
        )
        self._touch_review(q["doc_id"], question_id, result["correct"])
        self.conn.commit()
        result["questionId"] = question_id
        return result

    def self_assess(self, question_id: int, level: str) -> Dict[str, Any]:
        """主观题自评：掌握 / 模糊 / 不会。按设计不参与正确率统计。"""
        q = self.get_question(question_id)
        self.conn.execute(
            "INSERT INTO attempts(doc_id, question_id, user_answer, is_correct, duration_ms, created_at)"
            " VALUES(?,?,?,?,?,?)",
            (q["doc_id"], question_id, f"[自评]{level}", None, 0, dbmod.now()),
        )
        r = self.ensure_review(q["doc_id"], question_id)
        if level == "不会":
            self.conn.execute(
                "UPDATE reviews SET in_wrongbook=1, wrong_count=wrong_count+1, last_wrong_at=?"
                " WHERE doc_id=? AND question_id=?",
                (dbmod.now(), q["doc_id"], question_id),
            )
        self.conn.commit()
        return {"questionId": question_id, "level": level, "review": self.get_review(question_id)}

    def _touch_review(self, doc_id: int, question_id: int, correct: Optional[bool]) -> None:
        self.ensure_review(doc_id, question_id)
        if correct is True:
            self.conn.execute(
                "UPDATE reviews SET correct_streak = correct_streak + 1,"
                " in_wrongbook = CASE WHEN correct_streak + 1 >= 2 THEN 0 ELSE in_wrongbook END"
                " WHERE doc_id=? AND question_id=?",
                (doc_id, question_id),
            )
        elif correct is False:
            self.conn.execute(
                "UPDATE reviews SET wrong_count = wrong_count + 1, correct_streak = 0,"
                " in_wrongbook = 1, last_wrong_at = ? WHERE doc_id=? AND question_id=?",
                (dbmod.now(), doc_id, question_id),
            )

    def practice_pick(self, doc_id: int, mode: str = "sequence",
                      filters: Optional[Dict[str, Any]] = None,
                      limit: int = 20) -> List[Dict[str, Any]]:
        """抽题。作用域默认限当前文档。"""
        f = dict(filters or {})
        if mode == "random":
            f["orderBy"] = "random"
        if mode == "wrong":
            f["wrongbook"] = True
        if mode == "starred":
            f["starred"] = True
        if mode == "pending":
            f["reviewState"] = RS_PENDING_INPUT
        f["page"] = 1
        f["pageSize"] = limit
        res = self.list_questions(doc_id, f)
        return [self.get_question(i["id"]) for i in res["items"]]

    # ---------------------------------------------------------------- 复习

    def ensure_review(self, doc_id: int, question_id: int) -> Dict[str, Any]:
        self.conn.execute(
            "INSERT OR IGNORE INTO reviews(doc_id, question_id, tags) VALUES(?,?, '[]')",
            (doc_id, question_id),
        )
        return self.get_review(question_id)

    def get_review(self, question_id: int) -> Dict[str, Any]:
        r = self.conn.execute(
            "SELECT * FROM reviews WHERE question_id=?", (question_id,)
        ).fetchone()
        if r is None:
            return {"starred": 0, "tags": [], "wrong_count": 0, "in_wrongbook": 0,
                    "correct_streak": 0, "next_review_at": None, "last_wrong_at": None}
        d = dict(r)
        d["tags"] = _loads(d.get("tags"), [])
        return d

    def toggle_star(self, question_id: int) -> Dict[str, Any]:
        q = self.conn.execute("SELECT doc_id FROM questions WHERE id=?", (question_id,)).fetchone()
        if q is None:
            raise KeyError(f"题目不存在: {question_id}")
        self.ensure_review(q["doc_id"], question_id)
        self.conn.execute(
            "UPDATE reviews SET starred = 1 - starred WHERE question_id=?", (question_id,)
        )
        self.conn.commit()
        return self.get_review(question_id)

    def set_tags(self, question_id: int, tags: List[str]) -> Dict[str, Any]:
        q = self.conn.execute("SELECT doc_id FROM questions WHERE id=?", (question_id,)).fetchone()
        self.ensure_review(q["doc_id"], question_id)
        self.conn.execute(
            "UPDATE reviews SET tags=? WHERE question_id=?",
            (json.dumps(tags, ensure_ascii=False), question_id),
        )
        self.conn.commit()
        return self.get_review(question_id)

    def set_wrongbook(self, question_id: int, in_book: bool) -> Dict[str, Any]:
        q = self.conn.execute("SELECT doc_id FROM questions WHERE id=?", (question_id,)).fetchone()
        self.ensure_review(q["doc_id"], question_id)
        self.conn.execute(
            "UPDATE reviews SET in_wrongbook=?, correct_streak=0 WHERE question_id=?",
            (1 if in_book else 0, question_id),
        )
        self.conn.commit()
        return self.get_review(question_id)

    def list_wrongbook(self, doc_id: Optional[int] = None,
                       page: int = 1, page_size: int = 50) -> Dict[str, Any]:
        """错题本：跨文档汇总，但每条都带来源文档，且可按文档筛选。"""
        where = ["rv.in_wrongbook = 1"]
        args: List[Any] = []
        if doc_id is not None:
            where.append("q.doc_id = ?")
            args.append(doc_id)
        clause = " AND ".join(where)
        total = self.conn.execute(
            f"SELECT COUNT(*) c FROM reviews rv JOIN questions q ON q.id=rv.question_id WHERE {clause}",
            args,
        ).fetchone()["c"]
        rows = self.conn.execute(
            f"SELECT q.id, q.doc_id, q.seq, q.display_no, q.type, q.stem, q.review_state,"
            f" d.name AS doc_name, rv.wrong_count, rv.last_wrong_at, rv.starred"
            f" FROM reviews rv JOIN questions q ON q.id=rv.question_id"
            f" JOIN documents d ON d.id = q.doc_id"
            f" WHERE {clause} ORDER BY rv.last_wrong_at DESC LIMIT ? OFFSET ?",
            args + [page_size, (page - 1) * page_size],
        ).fetchall()
        return {"total": total, "items": dbmod.rows_to_dicts(rows)}

    def list_starred(self, doc_id: Optional[int] = None, page: int = 1,
                     page_size: int = 50, tag: Optional[str] = None) -> Dict[str, Any]:
        """收藏 / 复习列表：跨文档汇总，可按来源文档与标签筛选。"""
        where = ["rv.starred = 1"]
        args: List[Any] = []
        if doc_id is not None:
            where.append("q.doc_id = ?")
            args.append(doc_id)
        if tag:
            where.append("rv.tags LIKE ?")
            args.append(f"%{tag}%")
        clause = " AND ".join(where)

        total = self.conn.execute(
            f"SELECT COUNT(*) c FROM reviews rv JOIN questions q ON q.id=rv.question_id WHERE {clause}",
            args,
        ).fetchone()["c"]
        rows = self.conn.execute(
            f"SELECT q.id, q.doc_id, q.seq, q.display_no, q.type, q.stem, q.review_state,"
            f" d.name AS doc_name, rv.tags, rv.wrong_count, rv.correct_streak"
            f" FROM reviews rv JOIN questions q ON q.id=rv.question_id"
            f" JOIN documents d ON d.id = q.doc_id"
            f" WHERE {clause} ORDER BY q.id DESC LIMIT ? OFFSET ?",
            args + [page_size, (page - 1) * page_size],
        ).fetchall()
        items = dbmod.rows_to_dicts(rows)
        for it in items:
            it["tags"] = _loads(it.get("tags"), [])
        return {"total": total, "items": items}

    def all_tags(self) -> List[str]:
        """已使用过的标签，供筛选下拉使用。"""
        tags = set()
        for row in self.conn.execute("SELECT tags FROM reviews WHERE tags != '[]' AND tags IS NOT NULL"):
            for t in _loads(row["tags"], []):
                if t:
                    tags.add(t)
        return sorted(tags)

    def stats(self, doc_id: Optional[int] = None) -> Dict[str, Any]:
        args: List[Any] = []
        clause = ""
        if doc_id is not None:
            clause = " WHERE q.doc_id = ?"
            args.append(doc_id)
        row = self.conn.execute(
            f"SELECT COUNT(*) total,"
            f" SUM(CASE WHEN a.is_correct = 1 THEN 1 ELSE 0 END) correct,"
            f" SUM(CASE WHEN a.is_correct = 0 THEN 1 ELSE 0 END) wrong"
            f" FROM attempts a JOIN questions q ON q.id=a.question_id{clause.replace('q.doc_id', 'q.doc_id')}",
            args,
        ).fetchone()
        total_att = (row["correct"] or 0) + (row["wrong"] or 0)
        return {
            "doc_id": doc_id,
            "attempt_total": row["total"] or 0,
            "graded_total": total_att,
            "correct": row["correct"] or 0,
            "wrong": row["wrong"] or 0,
            "accuracy": round((row["correct"] or 0) / total_att, 3) if total_att else 0.0,
        }

    # ---------------------------------------------------------------- 批注

    def list_annotations(self, question_id: int) -> List[Dict[str, Any]]:
        return dbmod.rows_to_dicts(self.conn.execute(
            "SELECT * FROM annotations WHERE question_id=? ORDER BY id", (question_id,)
        ).fetchall())

    def create_annotation(self, question_id: int, content: str, type_: str = "note",
                          color: Optional[str] = None,
                          anchor: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        q = self.conn.execute("SELECT doc_id FROM questions WHERE id=?", (question_id,)).fetchone()
        if q is None:
            raise KeyError(f"题目不存在: {question_id}")
        cur = self.conn.execute(
            "INSERT INTO annotations(doc_id, question_id, type, content, color, anchor,"
            " created_at, updated_at) VALUES(?,?,?,?,?,?,?,?)",
            (q["doc_id"], question_id, type_, content, color,
             json.dumps(anchor, ensure_ascii=False) if anchor else None,
             dbmod.now(), dbmod.now()),
        )
        self.conn.commit()
        r = self.conn.execute("SELECT * FROM annotations WHERE id=?", (cur.lastrowid,)).fetchone()
        return dict(r)

    def update_annotation(self, annotation_id: int, content: str,
                          color: Optional[str] = None) -> Dict[str, Any]:
        self.conn.execute(
            "UPDATE annotations SET content=?, color=COALESCE(?, color), updated_at=? WHERE id=?",
            (content, color, dbmod.now(), annotation_id),
        )
        self.conn.commit()
        r = self.conn.execute("SELECT * FROM annotations WHERE id=?", (annotation_id,)).fetchone()
        if r is None:
            raise KeyError(f"批注不存在: {annotation_id}")
        return dict(r)

    def delete_annotation(self, annotation_id: int) -> Dict[str, Any]:
        self.conn.execute("DELETE FROM annotations WHERE id=?", (annotation_id,))
        self.conn.commit()
        return {"deleted": annotation_id}

    # ---------------------------------------------------------------- 图片

    def list_images(self, doc_id: Optional[int] = None,
                    unassigned_only: bool = False) -> List[Dict[str, Any]]:
        where, args = [], []
        if doc_id is not None:
            where.append("doc_id = ?")
            args.append(doc_id)
        if unassigned_only:
            where.append("question_id IS NULL")
        clause = f"WHERE {' AND '.join(where)}" if where else ""
        rows = self.conn.execute(
            f"SELECT * FROM images {clause} ORDER BY id", args
        ).fetchall()
        out = dbmod.rows_to_dicts(rows)
        for d in out:
            d["bbox"] = _loads(d.get("bbox"), None)
        return out

    # ---------------------------------------------------------------- 导出

    def export_markdown(self, doc_id: int, out_path: Optional[str] = None) -> Dict[str, Any]:
        doc = self.get_document(doc_id)
        groups = {g["seq"]: g["title"] for g in self.list_groups(doc_id)}
        res = self.list_questions(doc_id, {"pageSize": 100000, "page": 1})
        buf = io.StringIO()
        buf.write(f"# {doc['name']}\n\n")
        cur_group = object()
        for it in res["items"]:
            if it.get("groupTitle") != cur_group:
                cur_group = it.get("groupTitle")
                if cur_group:
                    buf.write(f"\n## {cur_group}\n\n")
            q = self.get_question(it["id"])
            buf.write(f"### 第 {q.get('display_no') or q['seq'] + 1} 题\n\n")
            buf.write((q.get("stem") or "").strip() + "\n\n")
            for o in q.get("options") or []:
                buf.write(f"- {o['label']}. {o.get('content') or ''}\n")
            if q.get("answer"):
                buf.write(f"\n**答案**：{'、'.join(q['answer'])}\n")
            for e in q.get("explanations") or []:
                buf.write(f"\n**{e.get('title') or '解析'}**：{(e.get('content') or '').strip()}\n")
            for a in q.get("annotations") or []:
                buf.write(f"\n> 批注：{a.get('content')}\n")
            buf.write("\n---\n\n")
        text = buf.getvalue()
        if out_path:
            Path(out_path).write_text(text, encoding="utf-8")
        return {"path": out_path, "content": text if not out_path else None}

    def export_csv(self, doc_id: int, out_path: str) -> Dict[str, Any]:
        res = self.list_questions(doc_id, {"pageSize": 100000, "page": 1})
        with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["序号", "题号", "题型", "题干", "选项", "答案", "解析", "批注", "校对状态"])
            for it in res["items"]:
                q = self.get_question(it["id"])
                opts = " | ".join(f"{o['label']}.{o.get('content') or ''}" for o in q.get("options") or [])
                exps = " | ".join((e.get("content") or "").replace("\n", " ")
                                  for e in q.get("explanations") or [])
                anns = " | ".join(a.get("content") or "" for a in q.get("annotations") or [])
                w.writerow([q["seq"] + 1, q.get("display_no"), q.get("type"),
                            (q.get("stem") or "").replace("\n", " "), opts,
                            "/".join(q.get("answer") or []), exps, anns, q.get("review_state")])
        return {"path": out_path}

    # ---------------------------------------------------------------- 设置/备份

    def templates(self) -> List[Dict[str, str]]:
        return Template.list_all()

    def get_settings(self) -> Dict[str, Any]:
        return {
            "dataDir": str(self.data_dir),
            "theme": dbmod.get_setting(self.conn, "theme", "light"),
            "fontScale": dbmod.get_setting(self.conn, "fontScale", 1.0),
            "autoRemoveWrongAfter": dbmod.get_setting(self.conn, "autoRemoveWrongAfter", 2),
            "defaultTemplate": dbmod.get_setting(self.conn, "defaultTemplate", "pdf-consolidated"),
        }

    def update_settings(self, patch: Dict[str, Any]) -> Dict[str, Any]:
        for k in ("theme", "fontScale", "autoRemoveWrongAfter", "defaultTemplate"):
            if k in patch:
                dbmod.set_setting(self.conn, k, patch[k])
        return self.get_settings()

    def backup(self) -> Dict[str, Any]:
        target = dbmod.backup(self.data_dir, self.db_path, self.backup_dir)
        return {"path": str(target), "name": target.name}

    def list_backups(self) -> List[Dict[str, Any]]:
        return dbmod.list_backups(self.backup_dir)

    def restore(self, backup_path: str) -> Dict[str, Any]:
        dbmod.restore(Path(backup_path), self.data_dir, self.db_path)
        self.conn.close()
        self.conn = dbmod.connect(self.db_path)
        return {"restored": backup_path}


def _loads(value: Any, default: Any) -> Any:
    if value is None or value == "":
        return default
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return default


def _doc_out(row) -> Dict[str, Any]:
    """文档行对外输出：parse_report 解析成对象，其余保持 snake_case 与库一致。"""
    d = dict(row)
    d["parse_report"] = _loads(d.get("parse_report"), {})
    return d
