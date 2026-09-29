# -*- coding: utf-8 -*-
"""规则模板：把切题 / 选项 / 答案 / 噪声的规则外置成 YAML。

设计原则 4：规则与代码分离。新增题库只需加一个 YAML，不改代码。
所有正则约定第 1 个捕获组为关键值，答案规则的第 2 个捕获组为答案字母。
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import yaml


def _template_dir() -> Path:
    """定位模板目录，兼容源码运行与 PyInstaller 打包运行。"""
    here = Path(__file__).resolve().parent / "templates"
    if here.is_dir():
        return here
    # 打包后资源被解到 _MEIPASS 下（--add-data 的落点）
    bundled = getattr(sys, "_MEIPASS", None)
    if bundled:
        cand = Path(bundled) / "engine" / "templates"
        if cand.is_dir():
            return cand
        cand = Path(bundled) / "templates"
        if cand.is_dir():
            return cand
    return here


TEMPLATE_DIR = _template_dir()

_LABEL_ORDER = {"A": 0, "B": 1, "C": 2, "D": 3, "E": 4}

# 选项字母与括号的中英文写法（实测样卷用到了全角 ［］）
LABELS = "ABCDE"
BRACKET_OPEN = r"[\[［（(【]"
BRACKET_CLOSE = r"[\]］）)】]"

# 一行里出现多个「题号 + 字母」答案对（实测样卷有 `6.C   7.A   8.E …` 这种排法）
MULTI_ANSWER_PAIR = re.compile(
    rf"(\d{{1,4}})\s*[.．、]\s*[\[［（(【]?\s*([{LABELS}])\s*[\]］）)】]?(?![A-Za-z0-9])"
)


_OPTION_SEPARATORS = " \t\u3000；;，,）)】］"


def _is_option_separator(ch: str) -> bool:
    """裸选项标记前面的字符是否可视为选项边界。"""
    return ch in _OPTION_SEPARATORS


# 材料区/表格里的纯数值行（如 786.02 / 3120.84 / 72．10 / 34.6），不能当题号。
# 注意只排除「整行就是一个数」的情况：`27.5 年前甲…` 与 `2．1984 年消耗…`
# 都只是题号后面紧跟数字，必须仍识别为第 27、2 题。
_NUMERIC_ONLY = re.compile(r"^\d{1,6}([.,．]\d+)?\s*[%％]?$")


def is_numeric_only(text: str) -> bool:
    return bool(_NUMERIC_ONLY.match(text.strip()))


def split_multi_answer(text: str) -> Optional[List[Tuple[int, str]]]:
    """把一行里的多个「题号+字母」答案对切出来。

    返回 None 表示不是多答案行（少于 2 对），交给其它规则处理。
    """
    pairs: List[Tuple[int, str]] = []
    for m in MULTI_ANSWER_PAIR.finditer(text):
        no = int(m.group(1))
        letter = m.group(2)
        # 相邻配对必须紧挨着（中间只允许空白），否则可能是正文里的巧合
        if pairs:
            gap = text[pairs[-1][2]:m.start()]
            if gap.strip():
                break
        pairs.append((no, letter, m.end()))
    if len(pairs) < 2:
        return None
    return [(no, letter) for no, letter, _ in pairs]


@dataclass
class AnswerRule:
    pattern: re.Pattern
    confidence: float


@dataclass
class LetterRule:
    """从「答案区块内容」里抽取答案字母的规则。

    为什么需要它：实测样卷在同一份文件里混用了至少 8 种答案写法，
    且存在「题号与答案字母不在同一行」的情况（如 `10、` 换行后 `B【解析】`）。
    逐行匹配无法处理，必须先把答案区按题号切块，再从块内容里抽字母。
    """
    pattern: re.Pattern
    confidence: float


@dataclass
class Template:
    id: str
    name: str
    description: str = ""
    question_no: List[re.Pattern] = field(default_factory=list)
    option_mark: List[re.Pattern] = field(default_factory=list)
    answer_rules: List[AnswerRule] = field(default_factory=list)
    answer_letter_rules: List[LetterRule] = field(default_factory=list)
    explanation: List[re.Pattern] = field(default_factory=list)
    answer_section: List[re.Pattern] = field(default_factory=list)
    group_title: List[re.Pattern] = field(default_factory=list)
    noise: List[re.Pattern] = field(default_factory=list)
    preamble_start: List[re.Pattern] = field(default_factory=list)
    preamble_end: List[re.Pattern] = field(default_factory=list)
    defaults: Dict = field(default_factory=dict)

    # ---------- 加载 ----------

    @classmethod
    def load(cls, path: Path) -> "Template":
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        rules = []
        for item in (raw.get("answer") or {}).get("rules") or []:
            rules.append(
                AnswerRule(
                    pattern=re.compile(item["pattern"]),
                    confidence=float(item.get("confidence", 0.8)),
                )
            )
        letter_rules = []
        for item in (raw.get("answer_letter") or {}).get("rules") or []:
            letter_rules.append(
                LetterRule(
                    pattern=re.compile(item["pattern"]),
                    confidence=float(item.get("confidence", 0.6)),
                )
            )
        return cls(
            id=raw["id"],
            name=raw.get("name", raw["id"]),
            description=raw.get("description", ""),
            question_no=[re.compile(p) for p in (raw.get("question_no") or {}).get("patterns", [])],
            option_mark=[re.compile(p) for p in (raw.get("option_mark") or [])],
            answer_rules=rules,
            answer_letter_rules=letter_rules,
            explanation=[re.compile(p) for p in (raw.get("explanation") or {}).get("patterns", [])],
            answer_section=[re.compile(p) for p in (raw.get("answer_section") or {}).get("patterns", [])],
            group_title=[re.compile(p) for p in (raw.get("group_title") or {}).get("patterns", [])],
            noise=[re.compile(p) for p in (raw.get("noise") or [])],
            preamble_start=[re.compile(p) for p in (raw.get("preamble") or {}).get("start", [])],
            preamble_end=[re.compile(p) for p in (raw.get("preamble") or {}).get("end", [])],
            defaults=raw.get("defaults") or {},
        )

    @classmethod
    def by_id(cls, template_id: str) -> "Template":
        path = TEMPLATE_DIR / f"{template_id}.yaml"
        if not path.exists():
            raise FileNotFoundError(f"模板不存在: {template_id}")
        return cls.load(path)

    @classmethod
    def list_all(cls) -> List[Dict[str, str]]:
        items = []
        for path in sorted(TEMPLATE_DIR.glob("*.yaml")):
            t = cls.load(path)
            items.append({
                "id": t.id,
                "name": t.name,
                "description": t.description,
            })
        return items

    # ---------- 匹配 ----------

    def is_noise(self, text: str) -> bool:
        s = text.strip()
        if not s:
            return True
        return any(p.search(s) for p in self.noise)

    def match_question_no(self, text: str) -> Optional[Tuple[int, str]]:
        """返回 (题号, 去掉题号后的剩余文本)。

        先排除表格里的纯数值行——这类行（`786.02`、`72．10`）看起来
        完全符合「数字+点」，但它们不是题号。
        """
        if is_numeric_only(text):
            return None
        for pat in self.question_no:
            m = pat.match(text)
            if m:
                try:
                    no = int(m.group(1))
                except (ValueError, IndexError):
                    continue
                return no, text[m.end():]
        return None

    def match_answer(self, text: str) -> Optional[Tuple[int, str, float, str]]:
        """返回 (题号, 答案字母, 置信度, 标记之后的剩余文本)。

        剩余文本即解析正文的起始部分（如「解析：正确答案是[D]。①项…」后面的内容）。
        """
        for rule in self.answer_rules:
            m = rule.pattern.match(text)
            if m and m.lastindex and m.lastindex >= 2:
                try:
                    no = int(m.group(1))
                except ValueError:
                    continue
                ans = m.group(2)
                if ans in _LABEL_ORDER:
                    return no, ans, rule.confidence, text[m.end():]
        return None

    def match_explanation(self, text: str) -> Optional[str]:
        """若该行是「解析」标记行，返回解析小标题（如「解析一」）。"""
        s = text.strip()
        for pat in self.explanation:
            if pat.match(s):
                head = re.split(r"[：:]", s, maxsplit=1)[0]
                return head or "解析"
        return None

    def match_answer_section(self, text: str) -> bool:
        """是否是「答案与解析」这类分区标题（用于切换解析上下文）。"""
        s = text.strip()
        if len(s) > 20:
            return False
        return any(p.match(s) for p in self.answer_section)

    # ---------- 卷首须知（必须排除出题目） ----------

    def is_preamble_start(self, text: str) -> bool:
        """是否进入「考试须知 / 注意事项」区间。

        实测样卷的须知里有 `1. 监考老师宣布考试开始时…`，
        与正文题号写法一致，若不排除会产生一道假题并与正文题 1 重号。
        """
        s = text.strip()
        return any(p.match(s) for p in self.preamble_start)

    def is_preamble_end(self, text: str) -> bool:
        s = text.strip()
        return any(p.match(s) for p in self.preamble_end)

    # ---------- 答案字母抽取（区块级） ----------

    def extract_answer_letter(self, content: str) -> Optional[Tuple[str, float]]:
        """从答案区块内容中抽取答案字母，按规则优先级返回第一个命中。

        内容可能形如：`【解析】C 。由第二句…` / `解析：本题答案选A。` /
        `B解析：9721-1027。` / `D` / `分析:选D，…`
        """
        text = (content or "").strip()
        if not text:
            return None
        for rule in self.answer_letter_rules:
            m = rule.pattern.search(text)
            if m and m.group(1) in _LABEL_ORDER:
                return m.group(1), rule.confidence
        return None

    def match_group_title(self, text: str) -> Optional[str]:
        s = text.strip()
        for pat in self.group_title:
            m = pat.match(s)
            if m:
                # 取最后一个捕获组作为标题正文
                title = m.group(m.lastindex) if m.lastindex else m.group(0)
                return title.strip()
        return None

    # ---------- 选项切分（核心） ----------

    def split_options(self, text: str) -> Optional[List[Tuple[str, str]]]:
        """把一行切成若干 (选项字母, 内容)。

        实测样例 A 存在「一行 2~4 个选项」的排版，因此不能按行切分，
        必须按行内标记位置切分。且标记之间夹着的是**选项内容**，不是空白。

        判定规则：
        1. 首个标记必须位于行首（允许前导空白），避免把正文里的 "A." 当选项
        2. 字母严格递增（A→B→C→D）且互不重叠
        3. 方括号式标记（[A] / （A）/ 【A】）本身足够明确，直接采信；
           裸标记（A. / A、）容易与正文混淆，要求其前一个字符是空白
           或分句符（实测样卷有 `A、6；B、8；C、10；D、15；` 这种分号分隔）
        """
        s = text.strip()
        if not s:
            return None

        # 收集候选标记：字母 -> (起点, 结束点, 是否方括号式)
        candidates: List[Tuple[int, int, str, bool]] = []
        for pat in self.option_mark:
            for m in pat.finditer(s):
                label = m.group(1)
                if label not in _LABEL_ORDER:
                    continue
                bracketed = m.group(0).lstrip()[:1] in "[［（(【"
                candidates.append((m.start(), m.end(), label, bracketed))
        if not candidates:
            return None

        candidates.sort(key=lambda c: (c[0], c[1]))

        chosen: List[Tuple[int, int, str, bool]] = []
        for start, end, label, bracketed in candidates:
            if not chosen:
                # 首个标记必须在行首
                if s[:start].strip():
                    continue
                chosen.append((start, end, label, bracketed))
                continue
            _, prev_end, prev_label, _ = chosen[-1]
            if start < prev_end:
                continue
            if _LABEL_ORDER[label] <= _LABEL_ORDER[prev_label]:
                continue
            if not bracketed and start > 0 and not _is_option_separator(s[start - 1]):
                # 裸标记前必须是空白或分句符，否则很可能只是正文里的 "A."
                continue
            chosen.append((start, end, label, bracketed))

        if not chosen:
            return None

        out: List[Tuple[str, str]] = []
        for i, (start, end, label, _) in enumerate(chosen):
            stop = chosen[i + 1][0] if i + 1 < len(chosen) else len(s)
            content = s[end:stop].strip()
            out.append((label, content))
        return out
