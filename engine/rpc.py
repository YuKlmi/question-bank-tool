# -*- coding: utf-8 -*-
"""JSON-RPC 服务端（行分隔 JSON，走 stdin/stdout）。

Electron 主进程以子进程方式拉起它，通过 stdout 读响应。
**stdout 只用于协议输出**，所有日志一律走 stderr，否则会污染协议流。

请求： {"id": 1, "method": "doc.list", "params": {}}
响应： {"id": 1, "ok": true, "result": {...}}
       {"id": 1, "ok": false, "error": {"message": "...", "type": "..."}}

用法：
    python -m engine.rpc --data-dir "D:/题库数据"
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path
from typing import Any, Callable, Dict

from .service import DEFAULT_DATA_DIRNAME, Store


def build_routes(store: Store) -> Dict[str, Callable[..., Any]]:
    """界面可调用的全部方法。方法名即前端的 API 契约。

    约定：**所有路由都必须接受一个 params 字典参数**，
    这样 handle() 才能统一以 fn(params) 调用，不必做反射猜参数个数。
    """
    return {
        # 系统
        "system.ping": lambda p: {"pong": True},
        "system.info": lambda p: {
            "version": "0.1.0",
            "paths": store.paths(),
            "templates": store.templates(),
            "review_states": ["pending_input", "pending", "ok", "fixed"],
        },
        "system.paths": lambda p: store.paths(),

        # 文档
        "doc.import": lambda p: store.import_document(p["path"], p.get("templateId")),
        "doc.list": lambda p: store.list_documents(),
        "doc.get": lambda p: store.get_document(int(p["docId"])),
        "doc.delete": lambda p: store.delete_document(int(p["docId"]), bool(p.get("purgeMedia"))),
        "doc.reparse": lambda p: store.reparse_document(int(p["docId"]), p.get("templateId")),
        "doc.stats": lambda p: store.stats(p.get("docId")),
        "doc.groups": lambda p: store.list_groups(int(p["docId"])),

        # 题目
        "question.list": lambda p: store.list_questions(int(p["docId"]), p.get("filters")),
        "question.get": lambda p: store.get_question(int(p["questionId"])),
        "question.update": lambda p: store.update_question(int(p["questionId"]), p.get("fields") or {}),
        "question.create": lambda p: store.create_question(int(p["docId"]), p.get("payload") or {}),
        "question.delete": lambda p: store.delete_question(int(p["questionId"])),
        "question.setAnswer": lambda p: (store.set_answer(int(p["questionId"]), p.get("answer")),
                                        store.get_question(int(p["questionId"])))[1],

        # 答题
        "practice.pick": lambda p: store.practice_pick(
            int(p["docId"]), p.get("mode") or "sequence", p.get("filters"), int(p.get("limit") or 20)),
        "practice.submit": lambda p: store.submit_answer(
            int(p["questionId"]), p.get("userAnswer") or "", int(p.get("durationMs") or 0)),
        "practice.selfAssess": lambda p: store.self_assess(int(p["questionId"]), p.get("level") or "模糊"),

        # 错题本 / 收藏 / 复习
        "wrongbook.list": lambda p: store.list_wrongbook(p.get("docId"), int(p.get("page") or 1),
                                                         int(p.get("pageSize") or 50)),
        "wrongbook.set": lambda p: store.set_wrongbook(int(p["questionId"]), bool(p.get("inBook"))),
        "review.star": lambda p: store.toggle_star(int(p["questionId"])),
        "review.tags": lambda p: store.set_tags(int(p["questionId"]), p.get("tags") or []),
        "review.get": lambda p: store.get_review(int(p["questionId"])),
        "review.listStarred": lambda p: store.list_starred(
            p.get("docId"), int(p.get("page") or 1), int(p.get("pageSize") or 50), p.get("tag")),
        "review.allTags": lambda p: store.all_tags(),

        # 批注
        "annotation.list": lambda p: store.list_annotations(int(p["questionId"])),
        "annotation.create": lambda p: store.create_annotation(
            int(p["questionId"]), p.get("content") or "", p.get("type") or "note",
            p.get("color"), p.get("anchor")),
        "annotation.update": lambda p: store.update_annotation(
            int(p["annotationId"]), p.get("content") or "", p.get("color")),
        "annotation.delete": lambda p: store.delete_annotation(int(p["annotationId"])),

        # 图片
        "image.list": lambda p: store.list_images(p.get("docId"), bool(p.get("unassignedOnly"))),

        # 导出
        "export.markdown": lambda p: store.export_markdown(int(p["docId"]), p.get("outPath")),
        "export.csv": lambda p: store.export_csv(int(p["docId"]), p["outPath"]),

        # 设置 / 备份
        "settings.get": lambda p: store.get_settings(),
        "settings.update": lambda p: store.update_settings(p.get("patch") or {}),
        "backup.create": lambda p: store.backup(),
        "backup.list": lambda p: store.list_backups(),
        "backup.restore": lambda p: store.restore(p["backupPath"]),
    }


def handle(routes: Dict[str, Callable[..., Any]], req: Dict[str, Any]) -> Dict[str, Any]:
    rid = req.get("id")
    method = req.get("method")
    params = req.get("params") or {}
    fn = routes.get(method)
    if fn is None:
        return {"id": rid, "ok": False,
                "error": {"type": "MethodNotFound", "message": f"未知方法: {method}"}}
    try:
        result = fn(params)
        return {"id": rid, "ok": True, "result": result}
    except Exception as exc:  # noqa: BLE001 - 协议层需兜住所有异常
        print(f"[rpc] {method} 失败: {exc}", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
        return {"id": rid, "ok": False,
                "error": {"type": type(exc).__name__, "message": str(exc)}}


def default_data_dir() -> Path:
    return Path.home() / "Documents" / DEFAULT_DATA_DIRNAME


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="engine.rpc")
    parser.add_argument("--data-dir", default=None)
    args = parser.parse_args(argv)

    # Windows 下必须显式设成 UTF-8，否则中文会乱码甚至抛 UnicodeEncodeError
    for stream in (sys.stdout, sys.stderr, sys.stdin):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass

    data_dir = Path(args.data_dir) if args.data_dir else default_data_dir()
    store = Store(data_dir)
    routes = build_routes(store)
    print(f"[rpc] 就绪 dataDir={data_dir}", file=sys.stderr, flush=True)

    try:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                req = json.loads(line)
            except json.JSONDecodeError as exc:
                print(f"[rpc] 请求 JSON 解析失败: {exc}", file=sys.stderr, flush=True)
                continue

            if isinstance(req, list):        # 批量请求
                resp = [handle(routes, r) for r in req]
            else:
                resp = handle(routes, req)

            sys.stdout.write(json.dumps(resp, ensure_ascii=False, default=str) + "\n")
            sys.stdout.flush()
    except KeyboardInterrupt:
        pass
    finally:
        store.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
