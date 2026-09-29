# -*- coding: utf-8 -*-
"""诊断 2：对照「答案区编号」与「题目区编号」，判断编号是否全局连续。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.annotate import markers  # noqa: E402
from engine.attach import attacher  # noqa: E402
from engine.imagestore import ImageStore  # noqa: E402
from engine.normalize import load_document  # noqa: E402
from engine.rules import Template  # noqa: E402

PDF = Path(sys.argv[1] if len(sys.argv) > 1 else
           r"e:\code\新建文件夹\samples\招聘考试全真模拟EPI综合能力测试（二）.pdf")
DATA = Path(r"e:\code\新建文件夹\tools\out\_diag2")

tpl = Template.by_id("pdf-consolidated")
norm = load_document(PDF, ImageStore(DATA / "media"), doc_key="d2")
events = markers.extract(norm.blocks, tpl)
att = attacher.attach(events, tpl)

print("=== 题目区：按大题组统计题号区间 ===")
for g in att.groups:
    qs = sorted(q.display_no for q in att.questions
                if q.group_seq == g.seq and q.display_no is not None)
    if not qs:
        continue
    print(f"  [{g.seq}] {g.title[:32]:<34} n={len(qs):>3}  题号 {min(qs)}–{max(qs)}")
    print(f"        全部: {qs}")

print("\n=== 答案区：编号序列 ===")
nums = [r.no for r in att.answers]
print(f"  条数={len(nums)}  范围 {min(nums)}–{max(nums)}")
print(f"  {nums}")

print("\n=== 逐题清单（前 60）===")
for q in att.questions[:60]:
    print(f"  seq={q.seq:>3} g={q.group_seq} 题{q.display_no:>4} "
          f"opts={len(q.options)} ans={q.answers} {q.stem[:38]!r}")

print("\n=== 材料分析相关组 ===")
for g in att.groups:
    if g.seq >= 2:
        qs = [q for q in att.questions if q.group_seq == g.seq]
        print(f"  [{g.seq}] {g.title[:30]} → 题号 {[q.display_no for q in qs]}")
