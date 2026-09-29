# -*- coding: utf-8 -*-
"""把 PDF 指定页渲染为 PNG，并导出页内嵌入的原始图片。

用于人工核对版面结构，以及确认"题面以图片嵌入"这类情况的实际内容。

用法：python tools/render_page.py <pdf路径> <页码...>
输出到 tools/out/
"""
import sys
from pathlib import Path

import pymupdf

OUT = Path(__file__).parent / "out"
OUT.mkdir(parents=True, exist_ok=True)


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return
    pdf = Path(sys.argv[1])
    doc = pymupdf.open(pdf)
    for arg in sys.argv[2:]:
        pno = int(arg) - 1
        page = doc[pno]
        pix = page.get_pixmap(dpi=110)
        target = OUT / f"{pdf.stem}_p{pno + 1}.png"
        pix.save(target)
        # 同时输出该页图片块，便于判断内容是否被图片承载
        imgs = [b for b in page.get_text("dict")["blocks"] if b["type"] == 1]
        print(f"p{pno + 1} -> {target}  图片块={len(imgs)}")
        for b in imgs:
            print(f"    bbox={[round(v) for v in b['bbox']]} {b.get('width')}x{b.get('height')}")

        # 导出嵌入的原始图片（native 分辨率），用于判断 OCR 可行性
        for idx, info in enumerate(page.get_images(full=True)):
            xref = info[0]
            raw = doc.extract_image(xref)
            ext = raw["ext"]
            t = OUT / f"{pdf.stem}_p{pno + 1}_embedded{idx + 1}.{ext}"
            t.write_bytes(raw["image"])
            print(f"    嵌入图{idx + 1}: xref={xref} {raw['width']}x{raw['height']} {ext} -> {t.name}")
    doc.close()



if __name__ == "__main__":
    main()
