# -*- coding: utf-8 -*-
"""解析引擎的数据模型。

设计要点（见 AGENTS.md）：
- 题目按文档分区：Question 必带 docId，任何查询都以 docId 为顶层作用域
- 主键用文档内顺序 seq，不用题号（题号会在大题组内重置）
- 解析结果必带置信度与校对状态，低置信一律进人工队列
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple

# ---------- 枚举取值的字面量约束 ----------

# 题型
QT_SINGLE = "single"          # 单选
QT_MULTI = "multi"            # 多选
QT_JUDGE = "judge"            # 判断
QT_BLANK = "blank"            # 填空
QT_ESSAY = "essay"            # 简答 / 主观

# 判分方式（由题型决定）
GM_AUTO = "auto"              # 全自动
GM_SEMI = "semi"              # 半自动（填空）
GM_SELF = "self"              # 自评（主观题）

QTYPE_TO_GRADE = {
    QT_SINGLE: GM_AUTO,
    QT_MULTI: GM_AUTO,
    QT_JUDGE: GM_AUTO,
    QT_BLANK: GM_SEMI,
    QT_ESSAY: GM_SELF,
}

# 答案来源（优先级递增：文档内嵌 < 外部文件 < 手动录入）
AS_DOC = "doc"
AS_DOC_INFERRED = "doc_inferred"   # 按就近位置推断的文档内答案，必须人工确认
AS_EXTERNAL = "external"
AS_MANUAL = "manual"
ANSWER_SOURCE_RANK = {AS_DOC: 1, AS_DOC_INFERRED: 2, AS_EXTERNAL: 3, AS_MANUAL: 4}

# 校对状态
RS_PENDING_INPUT = "pending_input"   # 题面是图片，待人工录入
RS_PENDING = "pending"               # 有内容待校对
RS_OK = "ok"                         # 自动通过
RS_FIXED = "fixed"                   # 人工已修正

# 题干来源
SS_TEXT = "text"
SS_IMAGE = "image"

# 图片角色
ROLE_STEM = "stem"
ROLE_OPTION = "option"
ROLE_EXPLANATION = "explanation"


@dataclass
class Block:
    """归一化后的最小文本块。

    PDF 保留 page/bbox 以便跨页拼接、图片归属与原文定位；
    docx 则用 style 辅助判断层次。
    """
    order: int
    text: str
    page: Optional[int] = None
    bbox: Optional[Tuple[float, float, float, float]] = None
    style: Optional[str] = None
    is_image: bool = False
    image_path: Optional[str] = None
    image_size: Optional[Tuple[int, int]] = None

    def __repr__(self) -> str:  # pragma: no cover - 调试用
        tag = "IMG" if self.is_image else self.text[:24].replace("\n", " ")
        return f"<Block #{self.order} p={self.page} {tag!r}>"


@dataclass
class ImageRef:
    """图片引用。抽出后落盘，filePath 为相对数据目录的路径。"""
    file_path: str
    role: str = ROLE_STEM
    seq: int = 0
    page: Optional[int] = None
    bbox: Optional[Tuple[float, float, float, float]] = None
    source: str = "pdf-xobject"          # pdf-xobject | docx-media
    width: Optional[int] = None
    height: Optional[int] = None


@dataclass
class Option:
    label: str
    seq: int
    content: str = ""
    image_path: Optional[str] = None


@dataclass
class Explanation:
    seq: int
    title: str = ""
    content: str = ""
    image_paths: List[str] = field(default_factory=list)


@dataclass
class Question:
    doc_id: int
    seq: int                       # 文档内顺序，稳定主键（非数据库 id）
    display_no: Optional[int] = None   # 原文题号，可能重复
    group_seq: Optional[int] = None    # 所属大题组在文档内的序号
    type: str = QT_SINGLE
    grade_mode: str = GM_AUTO
    stem: str = ""
    raw_text: str = ""
    stem_source: str = SS_TEXT
    options: List[Option] = field(default_factory=list)
    answers: List[str] = field(default_factory=list)
    explanations: List[Explanation] = field(default_factory=list)
    images: List[ImageRef] = field(default_factory=list)
    answer_source: Optional[str] = None
    confidence: float = 0.0
    review_state: str = RS_PENDING
    page_no: Optional[int] = None
    bbox: Optional[Tuple[float, float, float, float]] = None
    db_id: Optional[int] = None

    @property
    def is_image_stem(self) -> bool:
        return self.stem_source == SS_IMAGE


@dataclass
class Group:
    seq: int
    title: str
    raw_text: str = ""
    db_id: Optional[int] = None


@dataclass
class ParseResult:
    """一次解析的完整产物。"""
    doc_name: str
    orig_type: str                 # doc|docx|pdf
    page_count: Optional[int] = None
    groups: List[Group] = field(default_factory=list)
    questions: List[Question] = field(default_factory=list)
    template_id: str = ""
    report: Dict[str, Any] = field(default_factory=dict)

    def summary(self) -> Dict[str, Any]:
        return {
            "docName": self.doc_name,
            "origType": self.orig_type,
            "pageCount": self.page_count,
            "templateId": self.template_id,
            "groupCount": len(self.groups),
            "questionCount": len(self.questions),
            "answeredCount": sum(1 for q in self.questions if q.answers),
            "pendingInputCount": sum(
                1 for q in self.questions if q.review_state == RS_PENDING_INPUT
            ),
            "pendingReviewCount": sum(
                1 for q in self.questions if q.review_state == RS_PENDING
            ),
            "report": self.report,
        }


def to_dict(obj: Any) -> Any:
    """dataclass → 可 JSON 序列化的 dict（递归处理 tuple）。"""
    if isinstance(obj, tuple):
        return list(obj)
    if isinstance(obj, list):
        return [to_dict(i) for i in obj]
    if isinstance(obj, dict):
        return {k: to_dict(v) for k, v in obj.items()}
    if hasattr(obj, "__dataclass_fields__"):
        return {k: to_dict(v) for k, v in asdict(obj).items()}
    return obj
