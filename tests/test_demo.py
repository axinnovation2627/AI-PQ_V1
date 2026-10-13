"""체험판(PQ_DEMO=1): 예시 평가를 임시 폴더에서 보여 주고, 업로드·판독은 막는다."""
import importlib
import sys

import pytest
from fastapi.testclient import TestClient

from pqweb.criteria import ROOT

DEMO_ID = "20261001-090000_가상기술인"


@pytest.fixture
def demo(monkeypatch, tmp_path):
    if not (ROOT / "demo" / "evaluations" / DEMO_ID).exists():
        pytest.skip("예시 자료 없음: tools/make_demo.py 실행")
    monkeypatch.setenv("PQ_DEMO", "1")
    monkeypatch.setenv("TMP", str(tmp_path))
    monkeypatch.setenv("TEMP", str(tmp_path))
    import tempfile
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    sys.modules.pop("pqweb.server", None)
    server = importlib.import_module("pqweb.server")
    yield server, TestClient(server.app), tmp_path
    sys.modules.pop("pqweb.server", None)


def test_demo_lists_example_and_blocks_upload(demo):
    server, c, tmp = demo
    assert c.get("/api/config").json()["demo"] is True
    ids = [e["id"] for e in c.get("/api/evaluations").json()]
    assert ids == [DEMO_ID]
    r = c.post("/api/evaluations", files={"file": ("a.pdf", b"%PDF-1.4", "application/pdf")})
    assert r.status_code == 403
    assert c.post(f"/api/evaluations/{DEMO_ID}/retry").status_code == 403


def test_demo_writes_only_to_temp(demo):
    server, c, tmp = demo
    assert str(server.app.state.base).startswith(str(tmp))
    assert str(server.app.state.crit_path).startswith(str(tmp))
    rows = c.get(f"/api/evaluations/{DEMO_ID}/rows").json()
    key = rows["rows"][0]["key"]
    assert c.put(f"/api/evaluations/{DEMO_ID}/review",
                 json={"평가위원": "t", "rows": {key: {"인정여부": "불인정"}}}).status_code == 200
    assert c.post(f"/api/evaluations/{DEMO_ID}/rejudge").status_code == 200
    assert c.get(f"/api/evaluations/{DEMO_ID}/excel?review=1").status_code == 200
    # 원본 예시 자료는 그대로
    orig = ROOT / "demo" / "evaluations" / DEMO_ID / "review.json"
    assert '"t"' not in orig.read_text(encoding="utf-8")
