# -*- coding: utf-8 -*-
"""样例题库文档结构勘察脚本。

用途：在定义解析规则前，先摸清两份真实样例的实际结构
（段落样式、题号/选项/答案标记形态、图片、批注、表格、公式），
避免凭空编写正则。产出报告写入 tools/out/。
"""
import re
import json
import zipfile
from pathlib import Path
from collections import Counter

SAMPLES = Path(r"c:\Users\Administrator\.trae-cn\attachments\6abb6d2dcc6e890228deafe6")
PDF_PATH = SAMPLES / "35af2488-42cc-44b6-b906-fcb5a5f23932_489f43cb-41d4-4a8f-9e6d-56871c13d633_行测题库及答案详解二.pdf"
DOC_PATH = SAMPLES / "f3015b29-fdc6-4303-bca0-f4168a573ff1_b5f4bf4f-6f34-4549-a2c0-517cfc80da9c_行测知识模拟测试题（一） .doc"

OUT = Path(__file__).parent / "out"
OUT.mkdir(parents=True, exist_ok=True)

# 候选的题目结构标记，用于统计命中情况
PATTERNS = {
    "题号_数字点": re.compile(r"^\s*(\d{1,4})\s*[.、．]"),
    "题号_方括号": re.compile(r"^\s*[【\[]\s*(\d{1,4})\s*[】\]]"),
    "选项_字母点": re.compile(r"^\s*([A-D])\s*[.、．]"),
    "选项_括号字母": re.compile(r"^\s*[（(]\s*([A-D])\s*[）)]"),
    "答案行": re.compile(r"^\s*【?答案】?\s*[:：]?\s*"),
    "解析行": re.compile(r"^\s*【?解析】?\s*[:：]?"),
    "行测分类": re.compile(r"^\s*(言语理解|数量关系|判断推理|资料分析|常识判断)"),
}


def probe_pdf():
    import fitz

    doc = fitz.open(PDF_PATH)
    lines = [f"页数: {doc.page_count}", f"元数据: {doc.metadata}", ""]

    fonts = Counter()
    total_images = 0
    total_drawings = 0
    images_by_page = []

    # 全量文本按页收集，同时统计结构标记
    all_text_lines = []
    for pno in range(doc.page_count):
        page = doc[pno]
        d = page.get_text("dict")
        page_lines = []
        for block in d["blocks"]:
            if block["type"] == 0:  # 文本块
                for line in block["lines"]:
                    text = "".join(span["text"] for span in line["spans"])
                    page_lines.append(text)
                    for span in line["spans"]:
                        fonts[(span["font"], round(span["size"], 1))] += len(span["text"])
            else:  # 图片块
                total_images += 1
                page_lines.append(f"<<IMAGE bbox={[round(v) for v in block['bbox']]} w={block.get('width')} h={block.get('height')}>>")
        drawings = page.get_drawings()
        total_drawings += len(drawings)
        images_by_page.append((pno + 1, len(drawings)))
        all_text_lines.append((pno + 1, page_lines))

    lines.append(f"图片块总数: {total_images}")
    lines.append(f"矢量绘图对象总数: {total_drawings}  (公式/表格线的强信号)")
    lines.append("")
    lines.append("--- 字体直方图 (font, size) -> 字符数 前15 ---")
    for (font, size), cnt in fonts.most_common(15):
        lines.append(f"  {font} @ {size} : {cnt}")
    lines.append("")

    # 结构标记统计
    hits = Counter()
    samples = {}
    for pno, page_lines in all_text_lines:
        for ln in page_lines:
            s = ln.strip()
            if not s:
                continue
            for name, pat in PATTERNS.items():
                if pat.match(s):
                    hits[name] += 1
                    samples.setdefault(name, [])
                    if len(samples[name]) < 6:
                        samples[name].append(f"p{pno}: {s[:90]}")
    lines.append("--- 结构标记命中统计 ---")
    for name in PATTERNS:
        lines.append(f"  {name}: {hits[name]}")
    lines.append("")
    lines.append("--- 各标记真实样例 ---")
    for name, ex in samples.items():
        lines.append(f"[{name}]")
        for e in ex:
            lines.append(f"  {e}")
    lines.append("")

    # 按页输出纯文本，供人工判断排版与切题规则
    lines.append("=" * 70)
    lines.append("逐页文本（前 4 页）")
    lines.append("=" * 70)
    for pno, page_lines in all_text_lines[:4]:
        lines.append(f"\n########## PAGE {pno} ##########")
        for ln in page_lines:
            lines.append(ln)

    # 写出全文，便于后续用 Grep 检索
    full = []
    for pno, page_lines in all_text_lines:
        full.append(f"########## PAGE {pno} ##########")
        full.extend(page_lines)
    (OUT / "pdf_fulltext.txt").write_text("\n".join(full), encoding="utf-8")

    (OUT / "pdf_report.txt").write_text("\n".join(lines), encoding="utf-8")
    doc.close()


def doc_to_docx():
    """用本机 Word COM 把 .doc 精确转换为 .docx（保留样式/表格/图片/批注）。"""
    import win32com.client as win32

    out_docx = OUT / "sample_1.docx"
    word = win32.Dispatch("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    try:
        d = word.Documents.Open(str(DOC_PATH), ReadOnly=True, AddToRecentFiles=False)
        d.SaveAs2(str(out_docx), FileFormat=16)  # wdFormatXMLDocument
        comment_count = d.Comments.Count
        comments = []
        for i in range(1, comment_count + 1):
            c = d.Comments(i)
            try:
                scope = c.Scope.Text
            except Exception:
                scope = ""
            comments.append({
                "author": c.Author,
                "scope": scope[:120],
                "text": c.Range.Text[:200],
            })
        revisions = d.Revisions.Count
        d.Close(SaveChanges=0)
    finally:
        word.Quit()
    return out_docx, comment_count, comments, revisions


def probe_docx(docx_path, comment_count, comments, revisions):
    from docx import Document

    doc = Document(str(docx_path))
    lines = []
    lines.append(f"段落总数: {len(doc.paragraphs)}")
    lines.append(f"表格总数: {len(doc.tables)}")
    lines.append(f"批注数: {comment_count}")
    lines.append(f"修订标记数: {revisions}")
    lines.append("")

    if comments:
        lines.append("--- 批注内容 ---")
        for c in comments:
            lines.append(f"  [{c['author']}] 作用域={c['scope']!r} 批注={c['text']!r}")
        lines.append("")

    styles = Counter(p.style.name for p in doc.paragraphs)
    lines.append("--- 段落样式直方图 ---")
    for name, cnt in styles.most_common(20):
        lines.append(f"  {name}: {cnt}")
    lines.append("")

    # 统计行内图片
    img_count = 0
    for rel in doc.part.rels.values():
        if "image" in rel.reltype:
            img_count += 1
    lines.append(f"文档内图片关系数: {img_count}")
    lines.append("")

    # docx 包内结构（看是否有 comments.xml 等）
    with zipfile.ZipFile(docx_path) as z:
        names = z.namelist()
        lines.append("--- docx 包内条目 ---")
        for n in names:
            lines.append(f"  {n}")
        media = [n for n in names if n.startswith("word/media/")]
        lines.append(f"word/media 图片文件数: {len(media)}")
    lines.append("")

    # 结构标记统计
    hits = Counter()
    samples = {}
    for p in doc.paragraphs:
        s = p.text.strip()
        if not s:
            continue
        for name, pat in PATTERNS.items():
            if pat.match(s):
                hits[name] += 1
                samples.setdefault(name, [])
                if len(samples[name]) < 8:
                    samples[name].append(s[:100])
    lines.append("--- 结构标记命中统计 ---")
    for name in PATTERNS:
        lines.append(f"  {name}: {hits[name]}")
    lines.append("")
    lines.append("--- 各标记真实样例 ---")
    for name, ex in samples.items():
        lines.append(f"[{name}]")
        for e in ex:
            lines.append(f"  {e}")
    lines.append("")

    lines.append("=" * 70)
    lines.append("前 90 个非空段落（含样式，表示段落层级）")
    lines.append("=" * 70)
    shown = 0
    for i, p in enumerate(doc.paragraphs):
        s = p.text.strip()
        if not s:
            continue
        lines.append(f"[{i:04d}][{p.style.name}] {s[:160]}")
        shown += 1
        if shown >= 90:
            break

    (OUT / "doc_report.txt").write_text("\n".join(lines), encoding="utf-8")

    # 全文写出，便于 Grep 检索答案/解析标记
    full = []
    for i, p in enumerate(doc.paragraphs):
        s = p.text
        if s.strip():
            full.append(f"[{p.style.name}] {s}")
    for ti, t in enumerate(doc.tables):
        full.append(f"##### TABLE {ti} #####")
        for row in t.rows:
            full.append(" | ".join(c.text.replace("\n", " ") for c in row.cells))
    (OUT / "doc_fulltext.txt").write_text("\n".join(full), encoding="utf-8")


if __name__ == "__main__":
    print("== PDF 勘察 ==")
    probe_pdf()
    print("PDF 完成 ->", OUT / "pdf_report.txt")

    print("== DOC 转换 ==")
    docx_path, ccount, comments, revs = doc_to_docx()
    print(f"转换完成: {docx_path}, 批注={ccount}, 修订={revs}")

    print("== DOCX 勘察 ==")
    probe_docx(docx_path, ccount, comments, revs)
    print("DOC 完成 ->", OUT / "doc_report.txt")
