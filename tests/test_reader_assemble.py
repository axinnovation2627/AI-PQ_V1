import json

import pytest

from pqweb.assemble import assemble
from pqweb.models import CM
from pqweb.reader_gemini import ReadError, parse_response, read_page

PAGE_TECH = {
    "쪽종류": "기술경력",
    "경력": [
        {"이어짐": True, "사업명": "용역(1권역)", "공사개요": "옹벽 3개소"},
        {"시작일": "2020.03.11", "종료일": "2020.11.15", "인정일": "28일", "사업명": "2020년 1권역 비탈면",
         "발주자": "한국도로공사부산경남본부", "공사종류": "고속국도", "담당업무": "안전점검"},
    ],
}


def test_parse_response_strips_fence_and_normalizes():
    raw = "```json\n" + json.dumps(PAGE_TECH, ensure_ascii=False) + "\n```"
    d = parse_response(raw)
    assert d["쪽종류"] == "기술경력"
    assert d["경력"][1]["인정일"] == 28


def test_parse_response_ignores_trailing_text():
    """모델이 JSON 뒤에 글자를 덧붙이는 경우(p33 'Extra data' 실패)."""
    raw = json.dumps({"쪽종류": "기타"}, ensure_ascii=False) + "\n}\n추가 설명"
    assert parse_response(raw)["쪽종류"] == "기타"


def test_parse_response_fixes_known_field_names():
    """생각(thinking)을 끄면 '도로및공항'을 '도로및공황'으로 읽는 경우가 있다."""
    page = {"쪽종류": "기술경력", "경력": [
        {"시작일": "2020.01.01", "종료일": "2020.02.01", "인정일": 3, "사업명": "x",
         "전문분야": "도로및공황", "직무분야": "토목"},
        {"시작일": "2020.01.01", "종료일": "2020.02.01", "인정일": 3, "사업명": "y",
         "전문분야": "새로운분야", "직무분야": "토목"}]}
    rows = parse_response(json.dumps(page, ensure_ascii=False))["경력"]
    assert rows[0]["전문분야"] == "도로및공항"
    assert rows[1]["전문분야"] == "새로운분야"      # 목록에 없고 비슷하지도 않으면 그대로


def test_parse_response_rejects_bad_type():
    with pytest.raises(ReadError):
        parse_response('{"쪽종류": "모름"}')


def test_read_page_retries_then_succeeds(tmp_path):
    png = tmp_path / "p01.png"
    png.write_bytes(b"x")
    calls = []

    def fake(img, prompt):
        calls.append(1)
        return "not json" if len(calls) < 3 else json.dumps({"쪽종류": "기타"})

    raw, d = read_page(png, fake, retries=2)
    assert d["쪽종류"] == "기타" and len(calls) == 3


def test_read_page_gives_up(tmp_path):
    png = tmp_path / "p01.png"
    png.write_bytes(b"x")
    with pytest.raises(ReadError):
        read_page(png, lambda i, p: "nope", retries=2)


def test_assemble_merges_continuation_and_sections():
    pages = [
        (1, {"쪽종류": "인적사항", "인적사항": {"성명": "기술인A", "등급": "토목 특급", "근무처": ["2014.10.20~ (주)가나엔지니어링"]}}),
        (2, {"쪽종류": "기술경력", "경력": [
            {"시작일": "2020.03.06", "종료일": "2020.08.26", "인정일": 19, "사업명": "2020년 대전충남본부",
             "공사종류": "고속국도"}]}),
        (3, parse_response(json.dumps(PAGE_TECH, ensure_ascii=False))),
        (4, {"쪽종류": "건설사업관리감리", "경력": [
            {"시작일": "1998.09.04", "종료일": "1999.11.17", "인정일": 440, "사업명": "새터교 감리"}]}),
        (5, {"쪽종류": "분야별인정일", "공사종류별": [{"공사종류": "고속국도", "인정일": 47}], "합계": 487}),
    ]
    rows, info, totals = assemble(pages)
    assert info.성명 == "기술인A" and info.등급 == "토목 특급"
    assert [r.쪽 for r in rows] == [2, 3, 4]
    assert rows[0].사업명 == "2020년 대전충남본부 용역(1권역)"
    assert rows[0].공사개요 == "옹벽 3개소"
    assert rows[1].인정일 == 28
    assert rows[2].구분 == CM
    assert totals.공사종류별 == {"고속국도": 47} and totals.합계 == 487
