"""FastAPI 서버: 업로드 → 백그라운드 판독·판정 → 진행 조회 → 엑셀 다운로드."""
from __future__ import annotations

import os
import shutil
import tempfile
import threading
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Body, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from . import pipeline, review, store
from . import criteria as criteria_mod
from .criteria import ROLES, ROOT, load_criteria
from .excel_export import build_notes, current_workplace, export, reading_status
from .models import CareerRow, CertInfo, CheckReport, Judgement
from .reader_gemini import gemini_caller

load_dotenv(ROOT / ".env")
WEB = Path(__file__).parent / "web"

app = FastAPI(title="PQ 경력평가")
app.state.base = store.BASE
app.state.crit_path = criteria_mod.DEFAULT

# 체험판(PQ_DEMO=1): 가상 예시 평가만 보여 주고 PDF 업로드·Gemini 판독은 막는다.
# 서버리스 환경은 프로그램 폴더에 쓸 수 없으므로 예시 자료와 평가기준을 임시 폴더에 복사해 쓴다
# (평가위원 입력·기준 수정은 임시로만 저장되고, 서버가 다시 시작되면 처음 상태로 돌아간다).
DEMO = os.getenv("PQ_DEMO") == "1"
DEMO_MSG = "체험판에서는 PDF 업로드·판독을 할 수 없습니다. 예시 평가로 화면을 체험해 보세요."
if DEMO:
    _tmp = Path(tempfile.gettempdir()) / "pq-demo"
    if not (_tmp / "evaluations").exists():
        shutil.copytree(ROOT / "demo" / "evaluations", _tmp / "evaluations")
    (_tmp / "criteria").mkdir(parents=True, exist_ok=True)
    if not (_tmp / "criteria" / criteria_mod.DEFAULT.name).exists():
        shutil.copy2(criteria_mod.DEFAULT, _tmp / "criteria" / criteria_mod.DEFAULT.name)
    app.state.base = _tmp / "evaluations"
    app.state.crit_path = _tmp / "criteria" / criteria_mod.DEFAULT.name
app.state.crit = load_criteria(app.state.crit_path)


DEFAULT_MODELS = "gemini-3.5-flash,gemini-3.1-flash-lite,gemini-3.8-flash"


def _model() -> str:
    """앞 모델이 과부하면 뒤 모델로 넘어간다(쉼표로 구분)."""
    return os.getenv("GEMINI_MODEL") or DEFAULT_MODELS


def _thinking() -> int | None:
    """GEMINI_THINKING: 0=생각 끔(기본, 토큰 약 40% 절감), 숫자=생각 토큰 예산, 빈칸·default=모델 기본값."""
    v = (os.getenv("GEMINI_THINKING") or "0").strip().lower()
    if v in ("default", "기본"):
        return None
    try:
        return max(0, int(v))
    except ValueError:
        return 0


def _workers() -> int:
    try:
        return max(1, int(os.getenv("GEMINI_WORKERS") or 4))
    except ValueError:
        return 4


def _make_caller():
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise HTTPException(400, "GEMINI_API_KEY가 설정되지 않았습니다. .env 파일을 확인하세요.")
    return gemini_caller(key, _model(), thinking=_thinking())


app.state.make_caller = _make_caller
app.state.run_async = True


@app.get("/api/config")
def config():
    if DEMO:
        return {"gemini_ready": False, "demo": True, "model": "체험판(판독 없음)",
                "criteria": app.state.crit["이름"], "roles": list(ROLES)}
    return {"gemini_ready": bool(os.getenv("GEMINI_API_KEY")) or app.state.make_caller is not _make_caller,
            "model": _model(), "criteria": app.state.crit["이름"], "roles": list(ROLES), "demo": False}


@app.get("/api/evaluations")
def evaluations():
    return store.list_evals(app.state.base)


@app.post("/api/evaluations")
async def create(file: UploadFile = File(...), name: str = Form(""), org: str = Form(""),
                 role: str = Form("")):
    if DEMO:
        raise HTTPException(403, DEMO_MSG)
    data = await file.read()
    if not data.startswith(b"%PDF"):
        raise HTTPException(400, "PDF 파일이 아닙니다.")
    if role and role not in ROLES:
        raise HTTPException(400, f"참여형태는 {', '.join(ROLES)} 중 하나여야 합니다.")
    call = app.state.make_caller()
    meta = {"성명": name.strip(), "소속": org.strip(), "참여형태": role, "파일명": file.filename,
            "모델": _model(), "기준": app.state.crit["이름"]}
    d = store.new_eval(data, meta, base=app.state.base)
    job = lambda: pipeline.run(d, call, app.state.crit, workers=_workers())
    if app.state.run_async:
        threading.Thread(target=job, daemon=True).start()
    else:
        job()
    return {"id": d.name}


@app.post("/api/evaluations/{eval_id}/rejudge")
def rejudge(eval_id: str):
    """판독은 그대로 두고 현재 평가기준으로 판정·점수·엑셀만 다시 만든다(Gemini 호출 없음)."""
    d = _dir(eval_id)
    st = store.read_json(d / "status.json", {})
    if st.get("단계") != "완료":
        raise HTTPException(409, "판독이 끝난 평가만 다시 판정할 수 있습니다.")
    if not store.read_json(d / "rows.json", {}).get("rows"):
        raise HTTPException(409, "판독된 경력이 없어 다시 판정할 수 없습니다. [재시도]로 다시 판독하세요.")
    meta = store.read_json(d / "meta.json", {})
    store.write_json(d / "meta.json", {**meta, "기준": app.state.crit["이름"]})

    def no_api(img, prompt):
        raise RuntimeError("다시 판정에서는 판독(Gemini)을 하지 않습니다")

    out = pipeline.run(d, no_api, app.state.crit, workers=1, resume=True)
    if out.get("단계") != "완료":
        raise HTTPException(500, out.get("오류") or "다시 판정 실패")
    return {"id": eval_id, "결과": out["결과"]}


# ── 평가기준 편집 / 점수 편집 ──
def _split(crit: dict) -> dict:
    return {"규칙": {k: crit[k] for k in criteria_mod.RULE_KEYS},
            "점수": {k: crit[k] for k in criteria_mod.SCORE_KEYS}}


@app.get("/api/criteria")
def get_criteria():
    return {"파일": app.state.crit_path.name, **_split(app.state.crit)}


def _save_part(keys: tuple, body: dict):
    vals = body.get("값")
    if not isinstance(vals, dict):
        raise HTTPException(400, "값이 없습니다")
    new = {**app.state.crit, **{k: vals[k] for k in keys if k in vals}}
    try:
        criteria_mod.save_criteria(new, app.state.crit_path, note=str(body.get("메모") or ""))
    except ValueError as e:
        raise HTTPException(400, str(e))
    app.state.crit = load_criteria(app.state.crit_path)
    return {"저장": True, **_split(app.state.crit)}


@app.put("/api/criteria/rules")
def save_rules(body: dict = Body(...)):
    return _save_part(criteria_mod.RULE_KEYS, body)


@app.put("/api/criteria/scores")
def save_scores(body: dict = Body(...)):
    return _save_part(criteria_mod.SCORE_KEYS, body)


@app.get("/api/criteria/history")
def criteria_history():
    return criteria_mod.history(app.state.crit_path)


@app.post("/api/criteria/restore")
def criteria_restore(body: dict = Body(...)):
    try:
        criteria_mod.restore(str(body.get("파일") or ""), app.state.crit_path)
    except ValueError as e:
        raise HTTPException(400, str(e))
    app.state.crit = load_criteria(app.state.crit_path)
    return _split(app.state.crit)


@app.post("/api/evaluations/{eval_id}/retry")
def retry(eval_id: str):
    """판독 실패 쪽만 다시 읽고 판정·엑셀을 새로 만든다."""
    if DEMO:
        raise HTTPException(403, DEMO_MSG)
    d = _dir(eval_id)
    st = store.read_json(d / "status.json", {})
    if st.get("단계") not in ("완료", "오류"):
        raise HTTPException(409, "아직 처리 중입니다.")
    call = app.state.make_caller()
    store.write_json(d / "status.json", {**st, "단계": "대기", "오류": ""})
    job = lambda: pipeline.run(d, call, app.state.crit, workers=_workers(), resume=True)
    if app.state.run_async:
        threading.Thread(target=job, daemon=True).start()
    else:
        job()
    return {"id": eval_id}


def _dir(eval_id: str) -> Path:
    d = store.get_eval(eval_id, app.state.base)
    if not d:
        raise HTTPException(404, "평가를 찾을 수 없습니다.")
    return d


@app.get("/api/evaluations/{eval_id}")
def evaluation(eval_id: str):
    d = _dir(eval_id)
    return {"id": eval_id, "meta": store.read_json(d / "meta.json", {}),
            "status": store.read_json(d / "status.json", {})}


XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _loaded(d: Path):
    """저장된 판독·판정 결과를 객체로 되살린다."""
    rows_json = store.read_json(d / "rows.json")
    js_json = store.read_json(d / "judgements.json")
    if not rows_json or not js_json:
        raise HTTPException(409, "아직 AI 평가가 끝나지 않았습니다.")
    rows = [CareerRow.from_dict(r) for r in rows_json["rows"]]
    js = [Judgement(**j) for j in js_json["judgements"]]
    info = CertInfo(**rows_json["info"])
    chk = store.read_json(d / "check.json", {})
    chk.pop("정상", None)
    return rows, js, info, CheckReport(**chk)


@app.get("/api/evaluations/{eval_id}/rows")
def rows_for_review(eval_id: str):
    """평가위원 평가 화면용: 경력 행 + AI 판정 + 저장된 평가위원 입력."""
    d = _dir(eval_id)
    rows, js, info, chk = _loaded(d)
    meta = store.read_json(d / "meta.json", {})
    keys = review.row_keys(rows)
    out = []
    for k, r, j in zip(keys, rows, js):
        out.append({"key": k, "쪽": r.쪽, "사업명": r.사업명, "공사개요": r.공사개요, "시작일": r.시작일,
                    "종료일": r.종료일, "인정일": r.인정일, "발주자": r.발주자, "공사종류": r.공사종류,
                    "직무분야": r.직무분야, "전문분야": r.전문분야, "담당업무": r.담당업무,
                    "ai": {"인정여부": j.인정여부, "인정율": j.인정율, "분야": j.분야, "근거": j.근거,
                           "해당분야": j.해당분야, "용역유형": j.용역유형, "도로유형": j.도로유형,
                           "해당분야근거": j.해당분야근거, "용역유형근거": j.용역유형근거, "도로유형근거": j.도로유형근거,
                           "확인필요": j.확인필요}})
    general = {"참여형태": meta.get("참여형태") or "", "성명": meta.get("성명") or info.성명,
               "소속": meta.get("소속", ""), "등급": info.등급, "현근무처": current_workplace(info.근무처),
               "판독": reading_status(chk) or "정상(합계 대조 일치)", "판독정상": not reading_status(chk)}
    return {"rows": out, "review": review.load(d), "배점": app.state.crit["배점"], "인정율": app.state.crit["인정율"],
            "일수_연환산": app.state.crit["일수_연환산"], "일반": general,
            "메모": build_notes(meta, js, chk, app.state.crit)}


@app.put("/api/evaluations/{eval_id}/review")
def save_review(eval_id: str, body: dict = Body(...)):
    d = _dir(eval_id)
    rows, _, _, _ = _loaded(d)
    try:
        cleaned = review.clean(body, review.row_keys(rows))
    except (ValueError, TypeError) as e:
        raise HTTPException(400, str(e))
    review.save(d, cleaned)
    return {"저장": len(cleaned["rows"])}


@app.get("/api/evaluations/{eval_id}/pages/{page}")
def page_image(eval_id: str, page: int):
    p = _dir(eval_id) / "pages" / f"p{page:02d}.png"
    if not p.exists():
        raise HTTPException(404, "쪽 이미지가 없습니다.")
    return FileResponse(p, media_type="image/png")


@app.get("/api/evaluations/{eval_id}/excel")
def excel(eval_id: str, review_: int = Query(0, alias="review")):
    """review=1이면 평가위원 입력을 반영한 평가시트를 새로 만들어 내려준다."""
    d = _dir(eval_id)
    if review_:
        rows, js, info, chk = _loaded(d)
        rv = review.load(d)
        meta = store.read_json(d / "meta.json", {})
        name = store.safe_name(meta.get("성명") or info.성명)
        out = export(meta, info, rows, js, chk, app.state.crit, d / f"평가시트_{name}_평가위원반영.xlsx",
                     review=review.aligned(rv, review.row_keys(rows)), reviewer=rv["평가위원"])
        return FileResponse(out, filename=out.name, media_type=XLSX)
    name = (store.read_json(d / "status.json", {}).get("결과") or {}).get("엑셀")
    if not name or not (d / name).exists():
        raise HTTPException(404, "엑셀이 아직 없습니다.")
    return FileResponse(d / name, filename=name, media_type=XLSX)


@app.middleware("http")
async def no_cache_for_screens(request, call_next):
    """화면 파일을 브라우저가 묵혀 두면 업데이트 후에도 옛 화면이 뜬다."""
    resp = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/static/"):
        resp.headers["Cache-Control"] = "no-cache"
    return resp


app.mount("/static", StaticFiles(directory=WEB), name="static")


@app.get("/about")
def about():
    """2쪽 설명자료 (site/index.html)."""
    p = ROOT / "site" / "index.html"
    if not p.exists():
        raise HTTPException(404, "설명자료가 없습니다.")
    return HTMLResponse(p.read_text(encoding="utf-8"))


@app.get("/")
def index():
    """스크립트·스타일 주소에 수정시각을 붙여, 파일이 바뀌면 브라우저가 반드시 새로 받게 한다."""
    html = (WEB / "index.html").read_text(encoding="utf-8")
    for name in ("app.js", "review.js", "criteria.js", "style.css"):
        ver = int((WEB / name).stat().st_mtime)
        html = html.replace(f"/static/{name}", f"/static/{name}?v={ver}")
    return HTMLResponse(html)
