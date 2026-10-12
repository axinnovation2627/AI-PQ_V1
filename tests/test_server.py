import json

import pymupdf
import pytest
from fastapi.testclient import TestClient

from pqweb.server import app

PAGE = {"쪽종류": "기술경력", "경력": [
    {"시작일": "2021.03.04", "종료일": "2021.05.04", "인정일": 17, "공사종류": "국도",
     "사업명": "국도35호선 삼척 갈전지구 외 5개소 절토사면 정밀안전점검용역", "발주자": "정선국토관리사무소"}]}


@pytest.fixture
def client(tmp_path):
    app.state.base = tmp_path
    app.state.run_async = False
    app.state.make_caller = lambda: (lambda img, prompt: json.dumps(PAGE, ensure_ascii=False))
    return TestClient(app)


def _pdf() -> bytes:
    doc = pymupdf.open()
    doc.new_page()
    return doc.tobytes()


def test_flow(client):
    assert client.get("/").status_code == 200
    assert client.get("/api/config").json()["gemini_ready"] is True
    r = client.post("/api/evaluations", files={"file": ("a.pdf", _pdf(), "application/pdf")},
                    data={"name": "홍o동", "org": "테스트", "role": "분야참여"})
    assert r.status_code == 200
    eid = r.json()["id"]
    st = client.get(f"/api/evaluations/{eid}").json()["status"]
    assert st["단계"] == "완료" and st["결과"]["건수"]["유사"] == 1
    x = client.get(f"/api/evaluations/{eid}/excel")
    assert x.status_code == 200 and x.content[:2] == b"PK"
    assert client.get("/api/evaluations").json()[0]["id"] == eid


def test_rejects_non_pdf_and_bad_role(client):
    assert client.post("/api/evaluations", files={"file": ("a.txt", b"hello", "text/plain")}).status_code == 400
    r = client.post("/api/evaluations", files={"file": ("a.pdf", _pdf(), "application/pdf")}, data={"role": "x"})
    assert r.status_code == 400


def test_retry_marks_waiting_before_job(client, monkeypatch):
    """화면이 옛 '완료' 상태를 읽고 새로고침을 멈추지 않도록, 작업 시작 전에 상태를 바꾼다."""
    r = client.post("/api/evaluations", files={"file": ("a.pdf", _pdf(), "application/pdf")})
    eid = r.json()["id"]
    from pqweb import pipeline
    seen = {}

    def fake_run(d, call, crit, workers=1, resume=False):
        seen["단계"] = json.loads((d / "status.json").read_text(encoding="utf-8"))["단계"]
        seen["resume"] = resume
        return {}

    monkeypatch.setattr(pipeline, "run", fake_run)
    assert client.post(f"/api/evaluations/{eid}/retry").status_code == 200
    assert seen == {"단계": "대기", "resume": True}


def test_screens_not_cached(client):
    r = client.get("/")
    assert r.headers["cache-control"] == "no-cache"
    assert "/static/app.js?v=" in r.text and "/static/style.css?v=" in r.text
    assert client.get("/static/app.js").headers["cache-control"] == "no-cache"


def test_unknown_eval_404(client):
    assert client.get("/api/evaluations/없음").status_code == 404
    assert client.get("/api/evaluations/../etc/excel").status_code == 404
