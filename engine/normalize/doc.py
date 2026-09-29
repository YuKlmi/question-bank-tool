# -*- coding: utf-8 -*-
"""旧版 .doc 转换。

样例 A 实测为 OLE 二进制 .doc，python-docx 无法直接读。
本机装有 Microsoft Word，走 COM 转换精度最高（保留样式/表格/图片/批注）。
找不到 Word 时抛出明确的错误而不是静默降级。
"""
from __future__ import annotations

import tempfile
from pathlib import Path

WD_FORMAT_XML_DOCUMENT = 16  # wdFormatXMLDocument (.docx)


class WordUnavailableError(RuntimeError):
    pass


def convert_to_docx(src: Path, out_dir: Path | None = None) -> Path:
    """把 .doc 转成 .docx，返回转换后文件路径。"""
    # Word 用自己的工作目录解析相对路径，必须传绝对路径
    src = Path(src).resolve()
    try:
        import pythoncom
        import win32com.client as win32
    except ImportError as exc:  # pragma: no cover - 环境相关
        raise WordUnavailableError(
            "未安装 pywin32，无法转换 .doc。请安装 pywin32，"
            "或把文档另存为 .docx 后重试。"
        ) from exc

    out_dir = Path(out_dir) if out_dir else Path(tempfile.mkdtemp(prefix="qtb_"))
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / (src.stem + ".docx")

    pythoncom.CoInitialize()
    word = None
    try:
        word = win32.Dispatch("Word.Application")
    except Exception as exc:
        pythoncom.CoUninitialize()
        raise WordUnavailableError(
            "无法启动 Microsoft Word，.doc 转换失败。"
            "请在装有 Word 的机器上使用，或先把文档另存为 .docx。"
        ) from exc

    word.Visible = False
    word.DisplayAlerts = 0
    try:
        doc = word.Documents.Open(str(src), ReadOnly=True, AddToRecentFiles=False)
        doc.SaveAs2(str(target), FileFormat=WD_FORMAT_XML_DOCUMENT)
        doc.Close(SaveChanges=0)
    finally:
        try:
            word.Quit()
        except Exception:
            pass
        pythoncom.CoUninitialize()

    if not target.exists():
        raise WordUnavailableError("Word 转换未产出文件")
    return target


def read_doc_comments(src: Path) -> list[dict]:
    """直接从句柄读 .doc 的批注（转换前的原始信息）。"""
    src = Path(src).resolve()
    try:
        import pythoncom
        import win32com.client as win32
    except ImportError:  # pragma: no cover
        return []

    pythoncom.CoInitialize()
    word = None
    out: list[dict] = []
    try:
        word = win32.Dispatch("Word.Application")
        word.Visible = False
        word.DisplayAlerts = 0
        doc = word.Documents.Open(str(src), ReadOnly=True, AddToRecentFiles=False)
        for i in range(1, doc.Comments.Count + 1):
            c = doc.Comments(i)
            try:
                scope = c.Scope.Text
            except Exception:
                scope = ""
            out.append({
                "author": c.Author,
                "scopeText": (scope or "")[:200],
                "text": (c.Range.Text or "")[:500],
            })
        doc.Close(SaveChanges=0)
    except Exception:
        return out
    finally:
        try:
            if word is not None:
                word.Quit()
        except Exception:
            pass
        pythoncom.CoUninitialize()
    return out
