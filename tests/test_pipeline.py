import json

import pymupdf

from pqweb import pipeline
from pqweb.store import list_evals, new_eval, read_json

PAGES = {
    1: {"쪽종류": "인적사항", "인적사항": {"성명": "홍o동", "등급": "토목 고급"}},
    2: {"쪽종류": "기술경력", "경력": [
        {"시작일": "2021.03.04", "종료일": "2021.05.04", "인정일": 17, "공사종류": "국도",
         "사업명": "국도35호선 삼척 갈전지구 외 5개소 절토사면 정밀안전점검용역", "발주자": "정선국토관리사무소"},
        {"시작일": "2022.03.29", "종료일": "2022.06.26", "인정일": 6, "공사종류": "장대교량(100m이상)",
         "사업명": "국도 38호선 연당2교(하) 등 9개 시설물 정밀안전점검용역"}]},
    3: None,   # 판독 실패 쪽
    4: {"쪽종류": "분야별인정일", "공사종류별": [{"공사종류": "국도", "인정일": 17},
                                         {"공사종류": "장대교량(100m이상)", "인정일": 6}], "합계": 23},
}


def _pdf(n=4) -> bytes:
    doc = pymupdf.open()
    for i in range(n):
        doc.new_page().insert_text((72, 72), f"page {i + 1}")
    return doc.tobytes()


def test_pipeline_end_to_end(tmp_path, crit):
    d = new_eval(_pdf(), {"성명": "홍o동", "소속": "테스트", "참여형태": "분야참여", "모델": "fake"},
                 base=tmp_path)
    # read_page는 쪽 순서대로 호출된다. 실패 쪽(None)은 1회 + 재시도 2회 = 3번 호출된다.
    state = {"page": 0, "tries": 0}

    def caller(img, prompt):
        if state["tries"] == 0:
            state["page"] += 1
        p = PAGES[state["page"]]
        if p is None:
            state["tries"] += 1
            if state["tries"] == 3:
                state["tries"] = 0
            return "garbage"
        state["tries"] = 0
        return json.dumps(p, ensure_ascii=False)

    st = pipeline.run(d, caller, crit)
    assert st["단계"] == "완료", st
    res = st["결과"]
    assert res["건수"] == {"유사": 1, "관련": 0, "불인정": 1}
    assert res["유사_인정일"] == 17 and res["환산일수"] == 8.5
    assert st["실패쪽"] == [3] and not res["판독정상"]
    assert (d / res["엑셀"]).exists()
    assert (d / "raw" / "p03.error.txt").exists()
    assert read_json(d / "rows.json")["info"]["등급"] == "토목 고급"
    assert list_evals(tmp_path)[0]["status"]["단계"] == "완료"


def test_pipeline_records_error(tmp_path, crit):
    d = new_eval(b"not a pdf", {"성명": "x"}, base=tmp_path)
    st = pipeline.run(d, lambda i, p: "{}", crit)
    assert st["단계"] == "오류" and (d / "error.log").exists()
