# -*- coding: utf-8 -*-
"""通用诊断：事件分布 + 答案记录 + 逐题对照。

用法：python tools/diag_doc.py <文档路径> [模板ID]
"""
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.annotate import markers  # noqa: E402
from engine.attach import attacher  # noqa: E402
from engine.imagestore import ImageStore  # noqa: E402
from engine.normalize import load_document  # noqa: E402
from engine.rules import Template  # noqa: E402

DOC = Path(sys.argv[1])
TPL = sys.argv[2] if len(sys.argv) > 2 else "docx-mixed"
DATA = Path(r"e:\code\新建文件夹\tools\out\_diagdoc")

tpl = Template.by_id(TPL)
norm = load_document(DOC, ImageStore(DATA / "media"), doc_key="d", convert_dir=DATA / "conv")
events = markers.extract(norm.blocks, tpl)

print("=== 事件分布 ===")
for k, v in Counter(e.kind for e in events).most_common():
    print(f"  {k:16} {v}")

print("\n=== answer_section 事件 ===")
for e in events:
    if e.kind == markers.K_ANSWER_SECTION:
        print(f"  order={e.order} text={e.text!r}")

att = attacher.attach(events, tpl)
print(f"\n=== 答案记录 {len(att.answers)} 条 ===")
for r in att.answers:
    zone = "答案区" if getattr(r, "in_zone", False) else "交错"
    print(f"  题{r.no:>3} → {r.answer or '?'}  order={r.order:>4} {zone}  {r.text[:44]!r}")

from engine.attach import answers as answer_backfill  # noqa: E402

nxt = max((q.seq for q in att.questions), default=-1) + 1
stats = answer_backfill.backfill_answers(att.questions, att.answers, nxt, 0, q_start=att.q_start)
print(f"\n=== 回填统计 ===\n  {stats}")

print("\n=== 各组题号分布（阅读顺序）===")
gt = {g.seq: g.title for g in att.groups}
for g in att.groups:
    qs = sorted([q for q in att.questions if q.group_seq == g.seq],
                key=lambda q: att.q_start.get(id(q), 0))
    if qs:
        print(f"  [{g.seq}] {g.title[:20]:<22} {[q.display_no for q in qs]}")

print("\n=== 答案的编号递增段 ===")
from engine.attach.answers import _split_runs  # noqa: E402

for i, run in enumerate(_split_runs(att.answers, lambda r: r.no)):
    print(f"  段{i}: {[(r.no, r.answer) for r in run]}")

print("\n=== 题目的编号递增段 ===")
for i, run in enumerate(_split_runs(
        sorted(att.questions, key=lambda q: att.q_start.get(id(q), 0)),
        lambda q: q.display_no)):
    print(f"  段{i}: g={run[0].group_seq} {[q.display_no for q in run]}")

print("\n=== 拿到答案的题（group标题, 题号, 答案）===")
withans = [q for q in att.questions if q.answers]
print(f"  共 {len(withans)} 道")
for q in withans[:40]:
    print(f"    [{gt.get(q.group_seq, '?')[:10]}] 题{q.display_no} → {q.answers} order={att.q_start.get(id(q))}")

print("\n=== 题目（阅读顺序）前 25 ===")
ordered = sorted(att.questions, key=lambda q: att.q_start.get(id(q), 0))
for q in ordered[:25]:
    print(f"  order={att.q_start.get(id(q)):>4} 题{q.display_no:>4} "
          f"g={q.group_seq} ans={q.answers} src={q.answer_source} {q.stem[:30]!r}")
