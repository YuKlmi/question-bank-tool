# -*- coding: utf-8 -*-
"""测试公共夹具。"""
from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLES = REPO_ROOT / "samples"

PDF_SAMPLE = SAMPLES / "行测题库及答案详解二.pdf"
DOC_SAMPLE = SAMPLES / "行测知识模拟测试题（一）.doc"


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(scope="session")
def pdf_sample() -> Path:
    if not PDF_SAMPLE.exists():
        pytest.skip(f"缺少样例: {PDF_SAMPLE}")
    return PDF_SAMPLE


@pytest.fixture(scope="session")
def doc_sample() -> Path:
    if not DOC_SAMPLE.exists():
        pytest.skip(f"缺少样例: {DOC_SAMPLE}")
    return DOC_SAMPLE


@pytest.fixture(scope="session")
def pdf_result(pdf_sample: Path, tmp_path_factory):
    """样例 B 的解析结果（会话级缓存，避免重复解析 43 页 PDF）。"""
    from engine.pipeline import parse

    data_dir = tmp_path_factory.mktemp("pdfdata")
    return parse(pdf_sample, data_dir)


@pytest.fixture
def store(tmp_path: Path):
    from engine.service import Store

    s = Store(tmp_path / "data")
    yield s
    s.close()
