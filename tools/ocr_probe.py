# -*- coding: utf-8 -*-
"""OCR 试跑：在样例的"图片题面"上实测识别效果。

用途：验证 OCR 引擎可用性与识别质量，结论记录在 AGENTS.md；
本脚本用于后续回归复测。

输入：tools/render_page.py 导出的 *_embedded*.png
输出：识别文本写入 tools/out/ocr_<tag>_<图片名>.txt

用法：
    python tools/ocr_probe.py                # 自动选择可用引擎
    python tools/ocr_probe.py rapidocr       # 新版 rapidocr（PP-OCRv6）
    python tools/ocr_probe.py onnxruntime    # 旧版 rapidocr-onnxruntime（PP-OCRv3）
"""
import sys
import time
from pathlib import Path

OUT = Path(__file__).parent / "out"


def make_engine(which: str):
    """返回 (引擎描述, tag, 调用函数)。"""
    if which in ("rapidocr", "auto"):
        try:
            from rapidocr import RapidOCR

            engine = RapidOCR()

            def infer(p):
                out = engine(str(p))
                if not out.txts:
                    return []
                return list(zip(out.boxes, out.txts, out.scores))

            return "rapidocr (PP-OCRv6)", "v6", infer
        except ImportError as e:
            if which == "rapidocr":
                raise
            print(f"[跳过] rapidocr 不可用: {e}")

    if which in ("onnxruntime", "auto"):
        from rapidocr_onnxruntime import RapidOCR as OldOCR

        engine = OldOCR()

        def infer(p):
            res, _ = engine(str(p))
            return [(r[0], r[1], float(r[2])) for r in (res or [])]

        return "rapidocr-onnxruntime (PP-OCRv3)", "v3", infer

    raise SystemExit(f"未知引擎: {which}")


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "auto"
    desc, tag, infer = make_engine(which)
    print(f"引擎: {desc}\n")

    targets = [t for t in sorted(OUT.glob("*_embedded*.png")) if "_2x" not in t.name]
    if not targets:
        print("未找到嵌入图，请先运行 tools/render_page.py")
        return

    for p in targets:
        t0 = time.time()
        rows = infer(p)
        dt = time.time() - t0
        scores = [r[2] for r in rows]
        avg = sum(scores) / len(scores) if scores else 0.0
        low = sum(1 for s in scores if s < 0.9)
        print(f"{p.name}: 行数={len(rows)} 耗时={dt:.2f}s 平均置信度={avg:.3f} 低置信行={low}")
        dest = OUT / f"ocr_{tag}_{p.stem}.txt"
        dest.write_text("\n".join(r[1] for r in rows), encoding="utf-8")
        print(f"  -> {dest.name}\n")


if __name__ == "__main__":
    main()
