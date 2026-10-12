import json

import pymupdf
import pytest

from pqweb import pipeline, reader_gemini
from pqweb.reader_gemini import ReadError, read_page
from pqweb.store import new_eval


class ApiErr(Exception):
    def __init__(self, code, msg="api"):
        super().__init__(f"{code} {msg}")
        self.code = code


@pytest.fixture
def png(tmp_path, monkeypatch):
    monkeypatch.setattr(reader_gemini, "_sleep", lambda s: None)
    p = tmp_path / "p01.png"
    p.write_bytes(b"x")
    return p


def test_transient_503_is_retried_with_backoff(png):
    seq = [ApiErr(503), ApiErr(503), json.dumps({"쪽종류": "기타"})]

    def call(img, prompt):
        x = seq.pop(0)
        if isinstance(x, Exception):
            raise x
        return x

    _, d = read_page(png, call)
    assert d["쪽종류"] == "기타" and seq == []


def test_fatal_404_stops_immediately(png):
    n = {"calls": 0}

    def call(img, prompt):
        n["calls"] += 1
        raise ApiErr(404, "model not found")

    with pytest.raises(ReadError) as e:
        read_page(png, call)
    assert e.value.fatal and n["calls"] == 1 and "404" in str(e.value)


def _pdf(n):
    doc = pymupdf.open()
    for _ in range(n):
        doc.new_page()
    return doc.tobytes()


def test_pipeline_aborts_on_fatal(tmp_path, crit, monkeypatch):
    monkeypatch.setattr(reader_gemini, "_sleep", lambda s: None)
    d = new_eval(_pdf(5), {"성명": "x"}, base=tmp_path)
    n = {"calls": 0}

    def call(img, prompt):
        n["calls"] += 1
        raise ApiErr(404, "model not found")

    st = pipeline.run(d, call, crit)
    assert st["단계"] == "오류" and "404" in st["오류"] and n["calls"] == 1


def test_pipeline_all_pages_failed_is_error(tmp_path, crit, monkeypatch):
    monkeypatch.setattr(reader_gemini, "_sleep", lambda s: None)
    d = new_eval(_pdf(3), {"성명": "x"}, base=tmp_path)
    st = pipeline.run(d, lambda i, p: "garbage", crit)
    assert st["단계"] == "오류" and "모든 쪽" in st["오류"] and st["실패쪽"] == [1, 2, 3]
