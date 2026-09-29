# -*- coding: utf-8 -*-
"""诊断：打印标记事件分布、答案记录与题目题号的对应情况。"""
import sys
from collections import Counter
from pathlib import Path

# 允许以脚本方式直接运行（sys.path[0] 会是 tools/）
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.annotate import markers  # noqa: E402
from engine.attach import attacher  # noqa: E402
from engine.imagestore import ImageStore  # noqa: E402
from engine.normalize import load_document  # noqa: E402
from engine.rules import Template  # noqa: E402

PDF = Path(sys.argv[1] if len(sys.argv) > 1 else
           r"e:\code\新建文件夹\samples\招聘考试全真模拟EPI综合能力测试（二）.pdf")
DATA = Path(r"e:\code\新建文件夹\tools\out\_diag")

tpl = Template.by_id("pdf-consolidated")
store = ImageStore(DATA / "media")
norm = load_document(PDF, store, doc_key="diag")
events = markers.extract(norm.blocks, tpl)

print("=== 事件分布 ===")
for k, v in Counter(e.kind for e in events).most_common():
    print(f"  {k:16} {v}")

print("\n=== 答案区起点 ===")
for e in events:
    if e.kind == markers.K_ANSWER_SECTION:
        print(f"  order={e.order} page={e.page} text={e.text!r}")

print("\n=== 前 12 个答案相关事件 ===")
n = 0
for e in events:
    if e.kind in (markers.K_ANSWER, markers.K_ANSWER_HEAD, markers.K_ANSWER_GROUP, markers.K_ANSWER_SECTION):
        print(f"  [{e.order:>4}] {e.kind:14} no={e.question_no} ans={e.answer!r} text={e.text[:50]!r}")
        n += 1
        if n >= 12:
            break

att = attacher.attach(events, tpl)
print(f"\n=== 答案记录 {len(att.answers)} 条 ===")
for r in att.answers[:20]:
    print(f"  no={r.no:>4} ans={r.answer!r} conf={r.confidence} group={r.group_seq} text={r.text[:40]!r}")

nums = [q.display_no for q in att.questions if q.display_no is not None]
dups = [n_ for n_, c in Counter(nums).items() if c > 1]
print(f"\n=== 题目 {len(att.questions)} 道，题号去重 {len(set(nums))}，重复题号 {len(dups)}: {sorted(dups)[:25]}")

print("\n=== 大题组 ===")
for g in att.groups:
    cnt = sum(1 for q in att.questions if q.group_seq == g.seq)
    print(f"  [{g.seq}] {g.title[:40]} ({cnt} 题)")

print("\n=== 无答案的答案记录统计 ===")
print(f"  answerBlocksWithoutLetter = {att.stats.get('answerBlocksWithoutLetter')}")
print(f"  answerRecordCount = {att.stats.get('answerRecordCount')}")
