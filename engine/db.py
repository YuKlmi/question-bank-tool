# -*- coding: utf-8 -*-
"""SQLite 持久化层。

架构说明（已回写 AGENTS.md）：数据库由 **Python 标准库 sqlite3** 托管，
而不是设计初稿里的 Node better-sqlite3。原因：
- better-sqlite3 是原生模块，Electron 下需 electron-rebuild，ABI 极易出问题
- 已有 Python sidecar，用它托管可做到**零原生依赖、零编译**
- 备份/还原就退化成「拷文件」，实现与验证都简单可靠

分区原则：所有题目数据以 doc_id 为顶层作用域，查询默认带 doc_id 过滤，
从数据层杜绝不同文档的题目混排。
"""
from __future__ import annotations

import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS documents (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  name           TEXT NOT NULL,
  orig_type      TEXT NOT NULL,
  src_path       TEXT,
  template_id    TEXT,
  page_count     INTEGER,
  question_count INTEGER DEFAULT 0,
  answered_count INTEGER DEFAULT 0,
  pending_input  INTEGER DEFAULT 0,
  pending_review INTEGER DEFAULT 0,
  parse_status   TEXT DEFAULT 'ok',
  parse_report   TEXT,
  created_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS groups (
  id       INTEGER PRIMARY KEY AUTOINCREMENT,
  doc_id   INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  seq      INTEGER NOT NULL,
  title    TEXT,
  raw_text TEXT,
  UNIQUE(doc_id, seq)
);

CREATE TABLE IF NOT EXISTS questions (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  doc_id        INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  group_id      INTEGER REFERENCES groups(id) ON DELETE SET NULL,
  seq           INTEGER NOT NULL,
  display_no    INTEGER,
  type          TEXT NOT NULL DEFAULT 'single',
  grade_mode    TEXT NOT NULL DEFAULT 'auto',
  stem          TEXT DEFAULT '',
  raw_text      TEXT DEFAULT '',
  stem_source   TEXT DEFAULT 'text',
  answer        TEXT DEFAULT '[]',
  answer_source TEXT,
  confidence    REAL DEFAULT 0,
  review_state  TEXT DEFAULT 'pending',
  page_no       INTEGER,
  bbox          TEXT,
  UNIQUE(doc_id, seq)
);
CREATE INDEX IF NOT EXISTS idx_q_doc  ON questions(doc_id, seq);
CREATE INDEX IF NOT EXISTS idx_q_grp  ON questions(group_id);

CREATE TABLE IF NOT EXISTS options (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  question_id INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
  label       TEXT,
  seq         INTEGER,
  content     TEXT DEFAULT '',
  image_path  TEXT
);
CREATE INDEX IF NOT EXISTS idx_opt_q ON options(question_id);

CREATE TABLE IF NOT EXISTS images (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  doc_id      INTEGER NOT NULL,
  question_id INTEGER REFERENCES questions(id) ON DELETE CASCADE,
  file_path   TEXT NOT NULL,
  role        TEXT DEFAULT 'stem',
  seq         INTEGER DEFAULT 0,
  page_no     INTEGER,
  bbox        TEXT,
  source      TEXT,
  width       INTEGER,
  height      INTEGER
);
CREATE INDEX IF NOT EXISTS idx_img_q ON images(question_id);

CREATE TABLE IF NOT EXISTS explanations (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  question_id INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
  seq         INTEGER,
  title       TEXT,
  content     TEXT,
  image_paths TEXT
);
CREATE INDEX IF NOT EXISTS idx_exp_q ON explanations(question_id);

CREATE TABLE IF NOT EXISTS doc_comments (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  doc_id       INTEGER NOT NULL,
  question_id  INTEGER,
  author       TEXT,
  scope_text   TEXT,
  comment_text TEXT
);

CREATE TABLE IF NOT EXISTS annotations (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  doc_id      INTEGER NOT NULL,
  question_id INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
  type        TEXT DEFAULT 'note',
  content     TEXT DEFAULT '',
  color       TEXT,
  anchor      TEXT,
  created_at  TEXT,
  updated_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_ann_q ON annotations(question_id);

CREATE TABLE IF NOT EXISTS attempts (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  doc_id      INTEGER NOT NULL,
  question_id INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
  user_answer TEXT,
  is_correct  INTEGER,
  duration_ms INTEGER,
  created_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_att_q   ON attempts(question_id);
CREATE INDEX IF NOT EXISTS idx_att_doc ON attempts(doc_id);

CREATE TABLE IF NOT EXISTS reviews (
  doc_id         INTEGER NOT NULL,
  question_id    INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
  starred        INTEGER DEFAULT 0,
  tags           TEXT DEFAULT '[]',
  wrong_count    INTEGER DEFAULT 0,
  last_wrong_at  TEXT,
  correct_streak INTEGER DEFAULT 0,
  next_review_at TEXT,
  in_wrongbook   INTEGER DEFAULT 0,
  PRIMARY KEY (doc_id, question_id)
);
CREATE INDEX IF NOT EXISTS idx_rev_wrong ON reviews(in_wrongbook);

-- 答题进度：doc_id 直接作主键，一份文档只留一条，天然实现"分文档各存各的"。
-- 抽题结果与作答草稿都是会话态，形状随界面走，故整存成 JSON。
CREATE TABLE IF NOT EXISTS practice_progress (
  doc_id       INTEGER PRIMARY KEY REFERENCES documents(id) ON DELETE CASCADE,
  question_ids TEXT NOT NULL DEFAULT '[]',
  cursor       INTEGER NOT NULL DEFAULT 0,
  drafts       TEXT NOT NULL DEFAULT '{}',
  mode         TEXT DEFAULT 'sequence',
  limit_n      INTEGER DEFAULT 0,
  updated_at   TEXT
);

CREATE TABLE IF NOT EXISTS settings (
  key   TEXT PRIMARY KEY,
  value TEXT
);
"""


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def connect(db_path: Path) -> sqlite3.Connection:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: Path) -> None:
    conn = connect(db_path)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def rows_to_dicts(rows: List[sqlite3.Row]) -> List[Dict[str, Any]]:
    return [dict(r) for r in rows]


# ---------- 设置项 ----------

def get_setting(conn: sqlite3.Connection, key: str, default: Any = None) -> Any:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    if row is None:
        return default
    try:
        return json.loads(row["value"])
    except (json.JSONDecodeError, TypeError):
        return row["value"]


def set_setting(conn: sqlite3.Connection, key: str, value: Any) -> None:
    conn.execute(
        "INSERT INTO settings(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, json.dumps(value, ensure_ascii=False)),
    )
    conn.commit()


# ---------- 备份 / 还原 ----------

DB_FILENAME = "library.db"


def find_db_file(folder: Path) -> Optional[Path]:
    """在备份目录里定位数据库文件（兼容历史命名）。"""
    folder = Path(folder)
    preferred = folder / DB_FILENAME
    if preferred.exists():
        return preferred
    for pattern in ("*.db", "*.sqlite", "*.sqlite3"):
        found = sorted(folder.glob(pattern))
        if found:
            return found[0]
    return None


def backup(data_dir: Path, db_path: Path, dest_dir: Path) -> Path:
    """把数据库与图片一起打包成一个目录（单机场景下比 zip 更好增量）。"""
    data_dir, db_path, dest_dir = Path(data_dir), Path(db_path), Path(dest_dir)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = dest_dir / f"backup_{stamp}"
    target.mkdir(parents=True, exist_ok=True)

    # 用 SQLite 官方 backup API，保证一致性（不要直接拷正在写入的文件）
    src = connect(db_path)
    dst = sqlite3.connect(str(target / DB_FILENAME))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()

    media = data_dir / "media"
    if media.exists():
        shutil.copytree(media, target / "media", dirs_exist_ok=True)
    return target


def list_backups(dest_dir: Path) -> List[Dict[str, Any]]:
    dest_dir = Path(dest_dir)
    if not dest_dir.exists():
        return []
    out = []
    for p in sorted(dest_dir.glob("backup_*"), reverse=True):
        if not p.is_dir():
            continue
        db = find_db_file(p)
        size = sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
        out.append({
            "name": p.name,
            "path": str(p),
            "created_at": datetime.fromtimestamp(
                p.stat().st_mtime).isoformat(timespec="seconds"),
            "db_file": db.name if db else None,
            "size_bytes": size,
        })
    return out


def restore(backup_dir: Path, data_dir: Path, db_path: Path) -> None:
    """还原前先把当前数据另存一份，避免误操作无法回退。"""
    backup_dir, data_dir, db_path = Path(backup_dir), Path(data_dir), Path(db_path)
    if not backup_dir.exists():
        raise FileNotFoundError(f"备份不存在: {backup_dir}")

    src_db = find_db_file(backup_dir)
    if src_db is None:
        raise FileNotFoundError(f"备份目录里没有数据库文件: {backup_dir}")

    # 先备份当前库再覆盖，保证可回退
    if db_path.exists():
        safety = data_dir / f"before_restore_{datetime.now():%Y%m%d_%H%M%S}.db"
        shutil.copy2(db_path, safety)

    # 连同 -wal/-shm 一起清掉，避免旧日志把还原结果拉回去
    for suffix in ("-wal", "-shm"):
        stale = Path(str(db_path) + suffix)
        if stale.exists():
            stale.unlink()

    shutil.copy2(src_db, db_path)

    src_media = backup_dir / "media"
    if src_media.exists():
        shutil.copytree(src_media, data_dir / "media", dirs_exist_ok=True)
