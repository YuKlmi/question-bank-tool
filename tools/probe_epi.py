# -*- coding: utf-8 -*-
"""针对新增样例（EPI 综合能力测试）的结构勘察。

重点确认三件事：
1. 卷首「考试须知」区间的文本形态（必须排除出题目）
2. 题目区的题号/选项标记形态
3. 卷尾「答案解析：」之后的答案区结构（题号如何与题目对应）
"""
import sys
from pathlib import Path

import pymupdf

PDF = Path(sys.argv[1] if len(sys.argv) > 1 else
           r"e:\code\新建文件夹\samples\招聘考试全真模拟EPI综合能力测试（二）.pdf")
OUT = Path(__file__).parent / "out"
OUT.mkdir(parents=True, exist_ok=True)

doc = pymupdf.open(str(PDF))
pages = []
for pno in range(doc.page_count):
    lines = []
    for block in doc[pno].get_text("dict")["blocks"]:
        if block["type"] == 1:
            b = block["bbox"]
            lines.append(f"<<IMAGE bbox={[round(v) for v in b]} {block.get('width')}x{block.get('height')}>>")
            continue
        for line in block["lines"]:
            t = "".join(sp["text"] for sp in line["spans"])
            if t.strip():
                lines.append(t.rstrip())
    pages.append(lines)
doc.close()

full = []
for i, lines in enumerate(pages):
    full.append(f"########## PAGE {i + 1} ##########")
    full.extend(lines)
(OUT / "epi_fulltext.txt").write_text("\n".join(full), encoding="utf-8")

print(f"页数: {len(pages)}")
print(f"全文行数: {sum(len(p) for p in pages)}")
img = sum(1 for p in pages for l in p if l.startswith("<<IMAGE"))
print(f"图片块: {img}")

# 关键锚点
import re
for i, lines in enumerate(pages):
    for l in lines:
        if re.search(r"考试须知|考生须知|注意事项|答案解析|答案与解析|参考答案", l):
            print(f"  p{i + 1}: {l.strip()[:70]}")
