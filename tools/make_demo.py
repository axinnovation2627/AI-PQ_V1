"""체험판(데모)용 가상 평가 만들기.

가상 기술인의 경력증명서 PDF를 그리고, Gemini 대신 미리 정한 판독 결과를 넣어
실제 처리 과정(쪽 이미지 → 조립 → 대조 → 규칙 판정 → 점수 → 엑셀)을 그대로 돌린다.
결과는 demo/evaluations/ 에 저장된다. 실제 인물·용역이 아니다.

    .venv\\Scripts\\python tools\\make_demo.py
"""
from __future__ import annotations

import json
import shutil
import sys
from collections import Counter
from pathlib import Path

import pymupdf as fitz

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pqweb import pipeline, review, store  # noqa: E402
from pqweb.criteria import load_criteria  # noqa: E402
from pqweb.models import CareerRow  # noqa: E402

FONT = Path(r"C:\Windows\Fonts\malgun.ttf")
OUT = ROOT / "demo" / "evaluations"
EVAL_ID = "20261001-090000_가상기술인"

NAME, GRADE = "가상기술인", "토목 특급"
INFO = {"성명": NAME, "등급": GRADE,
        "자격": ["토목기사 1996.05.20", "토질및기초기술사 2008.11.28"],
        "교육": ["2016.03.07~2016.03.18 정밀안전진단 교육(토목) 가상교육원"],
        "근무처": ["1993.03.02 ~ 2009.02.28 (주)다라건설(가상)", "2009.03.02 ~ 근무중 (주)가나엔지니어링(가상)"]}


def row(s, e, days, name, client, kind, job, role="참여기술자", pos="차장", summary=""):
    return {"이어짐": False, "시작일": s, "종료일": e, "인정일": days, "사업명": name, "발주자": client,
            "공사종류": kind, "직무분야": "토목", "전문분야": "토질·지질", "담당업무": job, "직위": pos,
            "공사개요": summary, "금액": "", "시설물종류": ""}


# 쪽마다 판정 규칙의 여러 경우가 한 번씩 나오도록 고른 가상 경력
TECH_P2 = [
    row("1994.03.02", "1994.11.30", 274, "○○군 절토사면 정밀안전점검", "○○군청", "절토사면", "안전점검", pos="대리"),
    row("1998.04.01", "1998.10.31", 214, "국도 ○호선 ○○지구 절토사면 정밀안전점검", "○○국토관리사무소", "절토사면", "안전점검"),
    row("2003.03.10", "2003.12.20", 286, "지방도 ○○○호선 옹벽 정밀안전진단", "○○도 도로관리사업소", "옹벽", "안전진단"),
    row("2006.05.01", "2006.12.15", 229, "○○고속도로 ○○구간 비탈면 성능평가", "한국도로공사", "도로사면", "성능평가", role="분야책임"),
    row("2008.02.11", "2008.09.30", 233, "○○시 시도 ○○로 옹벽 긴급안전점검", "○○시청", "옹벽", "안전점검"),
    row("2010.03.02", "2010.11.30", 274, "○○초등학교 배면 옹벽 정밀안전진단", "○○교육지원청", "옹벽", "안전진단"),
    row("2011.04.04", "2011.10.31", 211, "○○면 농어촌도로 절토사면 정밀안전점검", "○○군청", "절토사면", "안전점검"),
    row("2012.03.05", "2012.12.14", 285, "○○대교 정밀안전진단", "○○국토관리사무소", "교량", "안전진단"),
]
TECH_P3 = [
    row("2013.02.04", "2013.08.30", 208, "○○터널 정밀안전점검", "한국도로공사", "터널", "안전점검"),
    row("2014.03.03", "2014.12.31", 304, "○○지구 급경사지 붕괴위험지역 실태조사 및 점검", "○○시청", "사면", "조사"),
    row("2015.05.11", "2015.11.30", 204, "○○읍 절토사면 정밀안전점검", "○○군청", "절토사면", "안전점검", summary="L=320m 절토사면"),
    row("2016.04.01", "2016.12.20", 264, "국도 ○○호선 도로 확포장공사 실시설계", "○○국토관리사무소", "국도", "설계"),
    row("2018.03.12", "2018.10.31", 234, "지방도 ○○○호선 옹벽 정밀안전점검 및 정기안전점검", "○○도 도로관리사업소", "옹벽", "안전점검"),
    row("2020.02.03", "2020.12.18", 320, "○○하천 제방 정밀안전점검", "○○시청", "제방", "안전점검"),
    row("2022.03.07", "2022.12.23", 292, "국도 ○○호선 절토사면 정밀안전진단", "○○국도관리사무소", "절토사면", "안전진단", role="분야책임", pos="부장"),
    row("2025.03.04", "근무중", 220, "○○고속도로 비탈면 정밀안전점검", "한국도로공사", "도로사면", "안전점검", pos="부장"),
]
CM_P4 = [
    row("2019.03.04", "2019.12.27", 299, "국도 ○호선 절토사면 보강공사 건설사업관리", "○○국토관리사무소", "절토사면", "건설사업관리", pos="부장"),
]


def page_specs():
    allrows = TECH_P2 + TECH_P3 + CM_P4
    kinds = Counter()
    for r in allrows:
        kinds[r["공사종류"]] += r["인정일"]
    totals = [{"공사종류": k, "인정일": v} for k, v in kinds.items()]
    empty = {"인적사항": {}, "경력": [], "공사종류별": [], "합계": 0}
    return [
        {**empty, "쪽종류": "인적사항", "인적사항": INFO},
        {**empty, "쪽종류": "기술경력", "경력": TECH_P2},
        {**empty, "쪽종류": "기술경력", "경력": TECH_P3},
        {**empty, "쪽종류": "건설사업관리감리", "경력": CM_P4},
        {**empty, "쪽종류": "분야별인정일", "공사종류별": totals, "합계": sum(kinds.values())},
    ]


def draw_pdf(specs) -> bytes:
    doc = fitz.open()
    gray, ink, line = (0.45, 0.45, 0.45), (0.1, 0.1, 0.12), (0.6, 0.6, 0.6)
    for no, sp in enumerate(specs, 1):
        pg = doc.new_page(width=595, height=842)
        pg.insert_font(fontname="kr", fontfile=str(FONT))
        pg.insert_text((150, 560), "가상 예시 자료", fontname="kr", fontsize=48, color=(0.93, 0.93, 0.93),
                       morph=(fitz.Point(297, 421), fitz.Matrix(-30)))
        t = lambda x, y, s, size=9, color=ink: pg.insert_text((x, y), s, fontname="kr", fontsize=size, color=color)
        t(40, 50, "건설기술인 경력증명서 (가상 예시 자료)", 15)
        t(40, 68, "※ 체험판용으로 만든 가상 자료입니다. 실제 인물·용역이 아닙니다.", 8.5, gray)
        t(500, 50, f"{no} / {len(specs)}", 9, gray)
        pg.draw_line((40, 78), (555, 78), color=ink, width=1.2)
        y = 100
        kind = sp["쪽종류"]
        if kind == "인적사항":
            t(40, y, "인적사항", 12); y += 22
            for k in ("성명", "등급"):
                t(48, y, f"{k}: {sp['인적사항'][k]}", 10); y += 18
            for k in ("자격", "교육", "근무처"):
                y += 8; t(40, y, k, 11); y += 18
                for v in sp["인적사항"][k]:
                    t(56, y, v, 9.5); y += 16
        elif kind in ("기술경력", "건설사업관리감리"):
            t(40, y, "1. 기술경력" if kind == "기술경력" else "2. 건설사업관리 및 감리경력", 12); y += 14
            pg.draw_line((40, y), (555, y), color=line, width=0.6); y += 16
            for r in sp["경력"]:
                t(44, y, f"{r['시작일']} ~ {r['종료일']}  ({r['인정일']}일)", 9.5)
                t(44, y + 15, r["사업명"], 10.5)
                t(44, y + 30, f"발주자 {r['발주자']}  ·  공사종류 {r['공사종류']}  ·  {r['직무분야']}/{r['전문분야']}"
                              f"  ·  담당업무 {r['담당업무']}  ·  직위 {r['직위']}", 8.5, gray)
                if r["공사개요"]:
                    t(44, y + 43, f"공사개요 {r['공사개요']}", 8.5, gray); y += 12
                y += 44
                pg.draw_line((40, y), (555, y), color=line, width=0.6); y += 16
        else:
            t(40, y, "분야별 참여기간 인정일 (공사종류별 인정일수 현황)", 12); y += 24
            for x in sp["공사종류별"]:
                t(56, y, x["공사종류"], 10); t(300, y, f"{x['인정일']:,}일", 10); y += 18
            pg.draw_line((40, y), (555, y), color=ink, width=0.8); y += 18
            t(56, y, "합계", 10.5); t(300, y, f"{sp['합계']:,}일", 10.5)
    doc.subset_fonts()
    return doc.tobytes(garbage=4, deflate=True)


def main():
    crit = load_criteria()
    specs = page_specs()
    if (OUT / EVAL_ID).exists():
        shutil.rmtree(OUT / EVAL_ID)
    OUT.mkdir(parents=True, exist_ok=True)
    meta = {"성명": NAME, "소속": "(주)가나엔지니어링(가상)", "참여형태": "분야책임",
            "파일명": "가상_경력증명서.pdf", "모델": "체험판 — 판독 결과를 미리 넣은 가상 자료", "기준": crit["이름"]}
    d = store.new_eval(draw_pdf(specs), meta, base=OUT)
    d = d.rename(OUT / EVAL_ID)
    store.write_json(d / "meta.json", {**meta, "생성": "2026-10-01 09:00:00"})

    answers = iter(json.dumps(sp, ensure_ascii=False) for sp in specs)
    out = pipeline.run(d, lambda img, prompt: next(answers), crit, workers=1)
    assert out["단계"] == "완료", out
    (d / "source.pdf").unlink()

    rows = [CareerRow.from_dict(r) for r in store.read_json(d / "rows.json")["rows"]]
    keys = review.row_keys(rows)
    sample = {"평가위원": "체험용", "rows": {
        keys[1]: {"인정여부": "유사", "인정율": 0.5, "사유": ""},
        keys[10]: {"인정여부": "유사", "인정율": 0.5, "사유": "노선 확인 결과 군도(도로법 제10조) — AI 가정과 같음"},
    }}
    review.save(d, review.clean(sample, keys))
    r = out["결과"]
    print(d.name, r["건수"], "환산", r["환산년수"], "년", "판독정상", r["판독정상"], r["점수"])


if __name__ == "__main__":
    main()
