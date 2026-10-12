import copy
import json
import shutil

import pymupdf
import pytest
from fastapi.testclient import TestClient

from pqweb import criteria as C
from pqweb.server import app

PAGE = {"쪽종류": "기술경력", "경력": [
    {"시작일": "2021.03.04", "종료일": "2021.05.04", "인정일": 20, "공사종류": "",
     "사업명": "국도38호선 법면 정밀점검용역", "발주자": "정선국토관리사무소"}]}


@pytest.fixture
def client(tmp_path, monkeypatch):
    cfile = tmp_path / "crit" / "2026_비탈면옹벽.yaml"
    cfile.parent.mkdir()
    shutil.copy(C.DEFAULT, cfile)
    monkeypatch.setattr(app.state, "crit_path", cfile, raising=False)
    monkeypatch.setattr(app.state, "crit", C.load_criteria(cfile))
    monkeypatch.setenv("GEMINI_WORKERS", "1")
    app.state.base = tmp_path / "data"
    app.state.run_async = False
    app.state.make_caller = lambda: (lambda img, prompt: json.dumps(PAGE, ensure_ascii=False))
    return TestClient(app)


def test_get_criteria(client):
    d = client.get("/api/criteria").json()
    assert set(d["규칙"]) >= {"대상어휘", "유사어휘", "근거"} and set(d["점수"]) == {"일수_연환산", "인정율", "배점"}
    assert d["파일"] == "2026_비탈면옹벽.yaml"


def test_save_rules_and_rejudge(client):
    doc = client.post("/api/evaluations", files={"file": ("a.pdf", pymupdf.open().tobytes() if False else _pdf(), "application/pdf")}).json()
    eid = doc["id"]
    st = client.get(f"/api/evaluations/{eid}").json()["status"]
    assert st["결과"]["건수"]["유사"] == 0                       # '법면'은 아직 대상 어휘 아님

    rules = client.get("/api/criteria").json()["규칙"]
    rules["대상어휘"].append("법면")
    r = client.put("/api/criteria/rules", json={"값": rules, "메모": "법면 추가"})
    assert r.status_code == 200, r.text
    assert "법면" in app.state.crit["대상어휘"]
    assert client.get("/api/criteria/history").json()[0]["메모"] == "법면_추가"

    assert client.post(f"/api/evaluations/{eid}/rejudge").status_code == 200
    st = client.get(f"/api/evaluations/{eid}").json()["status"]
    assert st["결과"]["건수"]["유사"] == 1 and st["결과"]["환산일수"] == 10.0


def test_save_scores_validates(client):
    scores = client.get("/api/criteria").json()["점수"]
    bad = copy.deepcopy(scores)
    bad["배점"]["분야참여"][0][0] = 0.1
    r = client.put("/api/criteria/scores", json={"값": bad})
    assert r.status_code == 400 and "줄어들어야" in r.json()["detail"]
    scores["인정율"]["유사"]["점검"] = 0.4
    assert client.put("/api/criteria/scores", json={"값": scores}).status_code == 200
    assert app.state.crit["인정율"]["유사"]["점검"] == 0.4


def test_rules_endpoint_ignores_score_keys(client):
    rules = client.get("/api/criteria").json()["규칙"]
    rules["배점"] = {"사업책임": [[0, 99]]}
    client.put("/api/criteria/rules", json={"값": rules})
    assert app.state.crit["배점"]["사업책임"][0] == [6, 8.0]


def test_restore(client):
    rules = client.get("/api/criteria").json()["규칙"]
    rules["대상어휘"].append("법면")
    client.put("/api/criteria/rules", json={"값": rules})
    name = client.get("/api/criteria/history").json()[0]["파일"]
    assert client.post("/api/criteria/restore", json={"파일": name}).status_code == 200
    assert "법면" not in app.state.crit["대상어휘"]


def _pdf():
    doc = pymupdf.open()
    doc.new_page()
    return doc.tobytes()
