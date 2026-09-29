# -*- coding: utf-8 -*-
"""解析可行性与自动成功率实测。

目的：量化"题目划分"与"答案对照"的真实难度，用数据判断是否需要
引入大模型 API 兜底，而不是凭直觉决策。

只做度量，不产出题库数据。
"""
import re
from pathlib import Path
from collections import Counter

ROOT = Path(r"e:\code\新建文件夹")
SAMPLES = ROOT / "samples"
OUT = ROOT / "tools" / "out"
OUT.mkdir(parents=True, exist_ok=True)

PDF_PATH = SAMPLES / "行测题库及答案详解二.pdf"
DOCX_PATH = OUT / "sample_1.docx"

# 实测发现的噪声（页码、水印、广告）
NOISE = [
    re.compile(r"^\s*\d+\s*/\s*\d+\s*$"),
    re.compile(r"offertop"),
    re.compile(r"kaojiabo\.com"),
    re.compile(r"shop108498359"),
    re.compile(r"各类考试包过无忧"),
    re.compile(r"考佳卜资料网"),
    re.compile(r"淘宝店铺地址"),
]


def is_noise(s: str) -> bool:
    return any(p.search(s) for p in NOISE)


# ---------------- 样例 B：PDF（答案集中式） ----------------

Q_NO = re.compile(r"^\s*(\d{1,4})\s*[.．]\s*\S")          # 题目区题号
ANS = re.compile(r"^\s*(\d{1,4})\s*[.．]\s*解析：正确答案是\s*[（(\[]?\s*([A-D])")


def check_pdf():
    import pymupdf

    doc = pymupdf.open(PDF_PATH)
    pages = []
    for pno in range(doc.page_count):
        lines = []
        for block in doc[pno].get_text("dict")["blocks"]:
            if block["type"] != 0:
                continue
            for line in block["lines"]:
                t = "".join(sp["text"] for sp in line["spans"])
                if t.strip() and not is_noise(t):
                    lines.append(t)
        pages.append(lines)
    doc.close()

    # 答案分区起点：出现独立成行的"答案与解析"
    ans_start = None
    for i, lines in enumerate(pages):
        if any(l.strip() == "答案与解析" for l in lines):
            ans_start = i
            break

    q_nums, a_pairs = [], []
    for i, lines in enumerate(pages):
        for l in lines:
            if ans_start is not None and i >= ans_start:
                m = ANS.match(l)
                if m:
                    a_pairs.append((int(m.group(1)), m.group(2)))
            else:
                m = Q_NO.match(l)
                if m:
                    q_nums.append(int(m.group(1)))

    q_set = set(q_nums)
    a_dict = dict(a_pairs)

    lines = []
    lines.append("=" * 66)
    lines.append("样例 B：行测题库及答案详解二.pdf（答案集中式）")
    lines.append("=" * 66)
    lines.append(f"总页数              : {len(pages)}")
    lines.append(f"答案分区起始页      : 第 {ans_start + 1} 页" if ans_start is not None else "答案分区: 未识别")
    lines.append("")
    lines.append(f"题目区题号出现次数  : {len(q_nums)}")
    lines.append(f"题目区去重题号数    : {len(q_set)}")
    lines.append(f"题号范围            : {min(q_set)} ~ {max(q_set)}" if q_set else "")
    dups = [n for n, c in Counter(q_nums).items() if c > 1]
    lines.append(f"题号重复个数        : {len(dups)}  {sorted(dups)[:20]}")
    lines.append("")
    lines.append(f"答案条数            : {len(a_pairs)}")
    lines.append(f"答案去重题号数      : {len(a_dict)}")
    lines.append("")
    both = q_set & set(a_dict)
    lines.append(f"题号与答案匹配数    : {len(both)}")
    if q_set:
        lines.append(f"答案覆盖率          : {len(both) / len(q_set) * 100:.1f}%  (匹配数 / 题目去重题号数)")
    miss_ans = sorted(q_set - set(a_dict))
    miss_q = sorted(set(a_dict) - q_set)
    lines.append(f"有题无答案的题号    : {miss_ans[:30]}")
    lines.append(f"有答案无题的题号    : {miss_q[:30]}")

    (OUT / "feasibility_pdf.txt").write_text("\n".join(lines), encoding="utf-8")
    return lines


# ---------------- 样例 A：DOC（答案与题目混排） ----------------

DOC_Q_NO = re.compile(r"^\s*(\d{1,4})\s*[、.．]")

# 实测归纳出的 4 种答案写法（去重后）
DOC_ANS_PATTERNS = {
    "【解析】X 后置答案": re.compile(r"^\s*(\d{1,4})\s*[、.．]\s*【解析】\s*([A-D])(?![A-Za-z])"),
    "X【解析】 前置答案": re.compile(r"^\s*(\d{1,4})\s*[、.．]\s*([A-D])\s*【解析】"),
    "【答案】X 标记式": re.compile(r"^\s*(\d{1,4})\s*[、.．]\s*【答案】\s*([A-D])(?![A-Za-z])"),
    "X解析： 裸标记": re.compile(r"^\s*(\d{1,4})\s*[、.．]\s*([A-D])\s*解析"),
}


def check_doc():
    if not DOCX_PATH.exists():
        return ["样例 A 的 .docx 转换产物不存在，请先运行 tools/probe_samples.py"]

    from docx import Document

    d = Document(str(DOCX_PATH))
    paras = [p.text for p in d.paragraphs if p.text.strip()]

    q_nums = []
    for t in paras:
        m = DOC_Q_NO.match(t)
        if m:
            q_nums.append(int(m.group(1)))

    lines = []
    lines.append("")
    lines.append("=" * 66)
    lines.append("样例 A：行测知识模拟测试题（一）.doc（答案与题目混排）")
    lines.append("=" * 66)
    lines.append(f"非空段落数          : {len(paras)}")
    lines.append(f"疑似题号出现次数    : {len(q_nums)}")
    lines.append(f"题号去重个数        : {len(set(q_nums))}")
    lines.append(f"题号范围            : {min(q_nums)} ~ {max(q_nums)}")
    dups = sorted(n for n, c in Counter(q_nums).items() if c > 1)
    lines.append(f"题号重复个数        : {len(dups)}  {dups}")
    lines.append("")
    lines.append(f"题号重复率          : {(len(q_nums) - len(set(q_nums))) / len(q_nums) * 100:.1f}%  ({len(q_nums)} 次出现 / {len(set(q_nums))} 个不同题号)")
    lines.append("")
    lines.append("--- 各答案写法命中数（去重后） ---")
    total = set()
    all_hits = 0
    for name, pat in DOC_ANS_PATTERNS.items():
        hits = []
        for t in paras:
            m = pat.match(t)
            if m:
                hits.append(int(m.group(1)))
        total |= set(hits)
        all_hits += len(hits)
        lines.append(f"  {name:<18} : {len(hits):>4} 条")
    lines.append("")
    lines.append(f"答案命中总条数      : {all_hits}")
    lines.append(f"命中到的不同题号数  : {len(total)}")
    lines.append(f"命中题号范围        : {min(total)} ~ {max(total)}" if total else "")
    lines.append("")
    lines.append("⚠ 关键：该文档题号在 29 处重复（题号重置），同一题号属于不同大题组。")
    lines.append("   因此'命中题号数'无法直接换算成'命中题目数'——靠题号做答案对照")
    lines.append("   在这份文档上本质上是不确定问题，必须结合顺序位置+邻近回填。")

    (OUT / "feasibility_doc.txt").write_text("\n".join(lines), encoding="utf-8")
    return lines


if __name__ == "__main__":
    out = []
    out += check_pdf()
    out += check_doc()
    print("\n".join(out))
