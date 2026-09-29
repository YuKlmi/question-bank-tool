# -*- coding: utf-8 -*-
"""引擎命令行入口（不依赖数据库，用于调试与回归）。

用法：
    python -m engine.cli parse samples/行测题库及答案详解二.pdf
    python -m engine.cli templates
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

from .models import to_dict
from .pipeline import parse
from .rules import Template


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="engine", description="题库解析引擎")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_parse = sub.add_parser("parse", help="解析文档并输出 JSON")
    p_parse.add_argument("path")
    p_parse.add_argument("--template", default=None)
    p_parse.add_argument("--data-dir", default=None)
    p_parse.add_argument("--limit", type=int, default=5, help="打印前 N 道题")
    p_parse.add_argument("--pending", type=int, default=0, help="打印前 N 道待人工校对的题")
    p_parse.add_argument("--json", action="store_true", help="输出完整 JSON")

    sub.add_parser("templates", help="列出内置规则模板")

    args = parser.parse_args(argv)

    if args.cmd == "templates":
        for t in Template.list_all():
            print(f"{t['id']:<18} {t['name']}")
            if t["description"]:
                print(f"{'':<18} {t['description']}")
        return 0

    if args.cmd == "parse":
        data_dir = Path(args.data_dir) if args.data_dir else Path(tempfile.mkdtemp(prefix="qtb_"))
        result = parse(Path(args.path), data_dir, template_id=args.template)
        if args.json:
            print(json.dumps(to_dict(result), ensure_ascii=False, indent=2))
            return 0

        s = result.summary()
        print(f"文档      : {s['docName']}  ({s['origType']}, {s['pageCount'] or '-'} 页)")
        print(f"模板      : {s['templateId']}")
        print(f"大题组    : {s['groupCount']}")
        for g in result.groups:
            n = sum(1 for q in result.questions if q.group_seq == g.seq)
            print(f"    [{g.seq}] {g.title}  ({n} 题)")
        print(f"题目      : {s['questionCount']}")
        print(f"已匹配答案: {s['answeredCount']}")
        print(f"待人工录入: {s['pendingInputCount']}")
        print(f"待人工校对: {s['pendingReviewCount']}")
        r = result.report
        print(f"答案匹配  : 命中 {r['answersMatched']} / 冲突 {r['answersConflict']} / 未匹配 {r['answersUnmatched']}")
        if r.get("answersNeedsConfirm"):
            print(f"            其中 {r['answersNeedsConfirm']} 条为就近推断，需人工确认")
        print(f"补位题    : 图片缺口 {r['placeholderCount']} + 答案无题 {r['createdSlotCount']}")
        if r["warnings"]:
            print("警告      :")
            for w in r["warnings"]:
                print(f"  - {w}")
        print()
        for q in result.questions[: args.limit]:
            opts = " ".join(f"{o.label}.{o.content[:14]}" for o in q.options)
            print(f"[{q.seq:>3}] 题{q.display_no} {q.type}/{q.grade_mode} "
                  f"conf={q.confidence} {q.review_state}")
            print(f"      题干: {q.stem[:70].replace(chr(10), ' / ')}")
            if opts:
                print(f"      选项: {opts}")
            print(f"      答案: {q.answers}  图片: {len(q.images)}")

        if args.pending:
            pend = [q for q in result.questions if q.review_state == "pending"]
            print(f"\n--- 待人工校对 {len(pend)} 道（前 {args.pending}）---")
            for q in pend[: args.pending]:
                print(f"[{q.seq:>3}] 题{q.display_no} conf={q.confidence} "
                      f"选项={len(q.options)} 答案={q.answers} 图={len(q.images)}")
                print(f"      题干: {q.stem[:70].replace(chr(10), ' / ')}")
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
