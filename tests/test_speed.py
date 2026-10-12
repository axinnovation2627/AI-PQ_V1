import json
import threading
import time

import pymupdf
import pytest

from pqweb import pipeline, reader_gemini
from pqweb.reader_gemini import ReadError, chain_callers
from pqweb.store import new_eval


class ApiErr(Exception):
    def __init__(self, code):
        super().__init__(f"{code} err")
        self.code = code


def _raise(code):
    def f(img, prompt):
        raise ApiErr(code)
    return f


def test_thinking_unsupported_retries_without_it():
    calls = []

    def gen(thinking):
        calls.append(thinking)
        if thinking is not None:
            raise ApiErr(400)
        return "ok"

    assert reader_gemini._with_thinking_fallback(gen, 0) == "ok"
    assert calls == [0, None]


def test_chain_falls_back_on_overload():
    used = []
    ok = lambda img, prompt: used.append("b") or "ok"
    call = chain_callers([("a", _raise(503)), ("b", ok)])
    assert call(b"", "") == "ok" and used == ["b"]


def test_chain_skips_missing_model():
    call = chain_callers([("a", _raise(404)), ("b", lambda i, p: "ok")])
    assert call(b"", "") == "ok"


def test_chain_all_overloaded_raises_transient():
    call = chain_callers([("a", _raise(503)), ("b", _raise(503))])
    with pytest.raises(ApiErr) as e:
        call(b"", "")
    assert e.value.code == 503


def test_chain_moves_on_when_model_quota_exhausted():
    call = chain_callers([("a", _raise(429)), ("b", lambda i, p: "ok")])
    assert call(b"", "") == "ok"


def test_daily_quota_stops_immediately(tmp_path, monkeypatch):
    monkeypatch.setattr(reader_gemini, "_sleep", lambda s: pytest.fail("하루 한도는 기다리지 않는다"))
    png = tmp_path / "p01.png"
    png.write_bytes(b"x")

    class Quota(Exception):
        code = 429

        def __str__(self):
            return "429 RESOURCE_EXHAUSTED quotaId GenerateRequestsPerDayPerProjectPerModel-FreeTier"

    def call(img, prompt):
        raise Quota()

    with pytest.raises(ReadError) as e:
        reader_gemini.read_page(png, chain_callers([("a", call), ("b", call)]))
    assert e.value.fatal and "하루 사용량" in str(e.value)


def test_chain_all_missing_raises_fatal():
    call = chain_callers([("a", _raise(404)), ("b", _raise(404))])
    with pytest.raises(ApiErr) as e:
        call(b"", "")
    assert e.value.code == 404


def _pdf(n):
    doc = pymupdf.open()
    for _ in range(n):
        doc.new_page()
    return doc.tobytes()


def test_rerun_reads_only_missing_pages(tmp_path, crit, monkeypatch):
    d = new_eval(_pdf(3), {"성명": "x"}, base=tmp_path)
    seen, tries = [], {"p2": 0}

    def fake_read(png, call, retries=2):
        no = int(png.stem[1:])
        seen.append(no)
        if no == 2:
            tries["p2"] += 1
            if tries["p2"] == 1:
                raise ReadError("bad")
        page = {"쪽종류": "기술경력", "경력": [
            {"시작일": "2021.03.04", "종료일": "2021.05.04", "인정일": no, "공사종류": "국도",
             "사업명": f"국도35호선 절토사면 정밀안전점검용역 {no}", "발주자": "정선국토관리사무소"}]}
        text = json.dumps(page, ensure_ascii=False)
        return text, reader_gemini.parse_response(text)

    monkeypatch.setattr(pipeline, "read_page", fake_read)
    st = pipeline.run(d, None, crit)
    assert st["실패쪽"] == [2]
    seen.clear()
    st = pipeline.run(d, None, crit, resume=True)
    assert seen == [2] and st["실패쪽"] == [] and st["결과"]["건수"]["유사"] == 3
    assert not (d / "raw" / "p02.error.txt").exists()


def test_pipeline_reads_pages_in_parallel(tmp_path, crit, monkeypatch):
    d = new_eval(_pdf(8), {"성명": "x"}, base=tmp_path)
    active, peak, lock = [0], [0], threading.Lock()

    def fake_read(png, call, retries=2):
        with lock:
            active[0] += 1
            peak[0] = max(peak[0], active[0])
        time.sleep(0.05)
        with lock:
            active[0] -= 1
        no = int(png.stem[1:])
        if no == 5:
            raise ReadError("bad")
        page = {"쪽종류": "기술경력", "경력": [
            {"시작일": "2021.03.04", "종료일": "2021.05.04", "인정일": no, "공사종류": "국도", "이어짐": False,
             "사업명": f"국도35호선 절토사면 정밀안전점검용역 {no}", "발주자": "정선국토관리사무소"}]}
        return json.dumps(page), reader_gemini.parse_response(json.dumps(page, ensure_ascii=False))

    monkeypatch.setattr(pipeline, "read_page", fake_read)
    st = pipeline.run(d, lambda i, p: "", crit, workers=4)
    assert st["단계"] == "완료" and st["실패쪽"] == [5] and st["완료쪽"] == 8
    assert peak[0] > 1
    rows = json.loads((d / "rows.json").read_text(encoding="utf-8"))["rows"]
    assert [r["쪽"] for r in rows] == [1, 2, 3, 4, 6, 7, 8]      # 쪽 순서 유지
