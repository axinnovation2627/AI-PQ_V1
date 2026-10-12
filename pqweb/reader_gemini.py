"""경력증명서 쪽 이미지 → 구조화 JSON (Gemini).

`read_page`는 호출 함수(call)를 주입받는다. 실제 실행에서는 `gemini_caller`가 만든 함수를,
시험에서는 가짜 함수를 넣는다.
"""
from __future__ import annotations

import difflib
import json
import re
import time
from pathlib import Path
from typing import Callable

Caller = Callable[[bytes, str], str]
PAGE_TYPES = ("인적사항", "기술경력", "건설사업관리감리", "분야별인정일", "기타")
ROW_FIELDS = ("시작일", "종료일", "인정일", "사업명", "발주자", "공사종류", "직무분야", "전문분야",
              "담당업무", "직위", "공사개요", "금액", "시설물종류")


class ReadError(Exception):
    def __init__(self, msg: str, fatal: bool = False):
        super().__init__(msg)
        self.fatal = fatal      # 다시 시도해도 소용없는 오류(모델 없음·키 오류 등) → 전체 중단


TRANSIENT = {429, 500, 502, 503, 504}   # 잠시 뒤 다시 시도
FATAL = {400, 401, 403, 404}            # 설정 문제 — 즉시 중단
BACKOFF = (2, 4, 8, 16, 30)             # 일시 오류 재시도 대기(초)


def _sleep(sec: float) -> None:
    time.sleep(sec)


def _status_code(e: Exception) -> int | None:
    code = getattr(e, "code", None)
    if isinstance(code, int):
        return code
    m = re.match(r"\s*(\d{3})\b", str(e))
    return int(m[1]) if m else None


PROMPT = """이 이미지는 한국건설기술인협회 '건설기술인 경력증명서'의 한 쪽입니다.
보이는 내용만 그대로 옮겨 적으세요. 추측하거나 보정하지 마세요. 읽을 수 없는 칸은 빈 문자열("")로 두세요.

먼저 쪽 종류를 하나 고르세요.
- "인적사항": 인적사항·등급·국가기술자격·학력·교육훈련·근무처가 있는 쪽
- "기술경력": '1. 기술경력' 표가 있는 쪽
- "건설사업관리감리": '2. 건설사업관리 및 감리경력' 표가 있는 쪽
- "분야별인정일": '분야별 참여기간 인정일'(공사종류별 인정일수 현황) 표가 있는 쪽
- "기타": 그 밖의 쪽

아래 JSON 형식으로만 답하세요. 설명 문장은 쓰지 마세요.
{
  "쪽종류": "...",
  "인적사항": {"성명": "", "등급": "직무분야·등급(예: 토목 특급)", "자격": ["종목 합격일"], "교육": ["기간 과정명 기관"], "근무처": ["근무기간 상호"]},
  "경력": [
    {"이어짐": false, "시작일": "YYYY.MM.DD", "종료일": "YYYY.MM.DD 또는 근무중", "인정일": 숫자,
     "사업명": "", "발주자": "", "공사종류": "", "직무분야": "", "전문분야": "", "담당업무": "",
     "직위": "", "공사개요": "", "금액": "", "시설물종류": ""}
  ],
  "공사종류별": [{"공사종류": "", "인정일": 숫자}],
  "합계": 숫자
}
규칙:
- "경력"은 표의 위에서 아래 순서로, 참여기간(인정일) 칸 하나가 한 행입니다. 인정일은 괄호 안 숫자만 적으세요.
- 참여기간 칸 없이 앞 쪽에서 이어지는 칸(└→ 표시 등)은 "이어짐": true 로 하고 보이는 글자만 적으세요.
- 해당 없는 키는 빈 값으로 두세요(인적사항 쪽이 아니면 "인적사항": {}, 경력이 없으면 "경력": []).
- "공사종류별"과 "합계"는 '공사종류별 인정일수 현황' 표에서만 채우세요.
"""


# 경력증명서 전문분야·직무분야 정식 명칭 (판독 오타 보정용)
KNOWN_FIELDS = (
    "토목", "건축", "기계", "전기", "도시·교통", "조경", "안전관리", "환경", "건설지원",
    "도로및공항", "토목구조", "토질·지질", "토목시공", "토목품질관리", "측량및지형공간정보",
    "항만및해안", "철도·삭도", "수자원개발", "상하수도", "농어업토목", "토목시공", "교통",
    "도시계획", "건축구조", "건축시공", "건축품질관리", "건설안전", "품질관리",
)


def _fix_field(v: str) -> str:
    if not v or v in KNOWN_FIELDS:
        return v
    near = difflib.get_close_matches(v, KNOWN_FIELDS, n=1, cutoff=0.8)
    return near[0] if near else v


def _int(v) -> int:
    if isinstance(v, (int, float)):
        return int(v)
    digits = re.sub(r"[^\d]", "", str(v or ""))
    return int(digits) if digits else 0


def parse_response(raw: str) -> dict:
    text = (raw or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        # 첫 JSON 객체만 읽는다(모델이 뒤에 글자를 덧붙이는 경우가 있음)
        d, _ = json.JSONDecoder().raw_decode(text[text.find("{"):] if "{" in text else text)
    except json.JSONDecodeError as e:
        raise ReadError(f"JSON 해석 실패: {e}") from e
    if not isinstance(d, dict) or d.get("쪽종류") not in PAGE_TYPES:
        raise ReadError(f"쪽종류 오류: {d.get('쪽종류') if isinstance(d, dict) else d!r}")
    rows = d.get("경력") or []
    if not isinstance(rows, list):
        raise ReadError("경력 형식 오류")
    clean = []
    for item in rows:
        if not isinstance(item, dict):
            raise ReadError("경력 행 형식 오류")
        row = {k: str(item.get(k) or "").strip() for k in ROW_FIELDS}
        row["인정일"] = _int(item.get("인정일"))
        row["전문분야"] = _fix_field(row["전문분야"])
        row["직무분야"] = _fix_field(row["직무분야"])
        row["이어짐"] = bool(item.get("이어짐")) or not row["시작일"]
        clean.append(row)
    d["경력"] = clean
    d["공사종류별"] = [{"공사종류": str(x.get("공사종류", "")).strip(), "인정일": _int(x.get("인정일"))}
                   for x in (d.get("공사종류별") or []) if isinstance(x, dict)]
    d["합계"] = _int(d.get("합계"))
    d["인적사항"] = d.get("인적사항") if isinstance(d.get("인적사항"), dict) else {}
    return d


def _call_api(call: Caller, img: bytes) -> str:
    """API 호출. 일시 오류(429·5xx)는 대기 후 재시도, 설정 오류(4xx)는 fatal."""
    for wait in (*BACKOFF, None):
        try:
            return call(img, PROMPT)
        except Exception as e:
            code = _status_code(e)
            if code in FATAL:
                raise ReadError(f"호출 실패(설정 확인 필요): {e}", fatal=True) from e
            if code == 429 and "PerDay" in str(e):
                raise ReadError("Gemini 하루 사용량 한도 소진(모든 모델) — 내일 다시 시도하거나 "
                                f"결제가 연결된 프로젝트의 API 키를 사용하세요. 원문: {e}", fatal=True) from e
            if code in TRANSIENT and wait is not None:
                _sleep(wait)
                continue
            raise ReadError(f"호출 실패: {e}") from e
    raise ReadError("호출 실패: 재시도 초과")


def read_page(png: Path, call: Caller, retries: int = 2) -> tuple[str, dict]:
    """쪽 하나 판독. (원본 응답, 정리된 dict).

    응답 형식이 틀리면 retries번 더 판독한다. fatal 오류는 바로 올려보낸다.
    """
    img = Path(png).read_bytes()
    last: ReadError | None = None
    for _ in range(retries + 1):
        try:
            raw = _call_api(call, img)
            return raw, parse_response(raw)
        except ReadError as e:
            if e.fatal:
                raise
            last = e
    raise last or ReadError("알 수 없는 오류")


def chain_callers(callers: list[tuple[str, Caller]]) -> Caller:
    """모델 여러 개를 차례로 시도한다.

    과부하(5xx)나 없는 모델(404)이면 바로 다음 모델로 넘어간다. 한도 초과(429) 등은 그대로 올려보내
    `_call_api`의 대기 후 재시도를 탄다. 모두 실패하면, 하나라도 일시 오류였으면 일시 오류를 올린다.
    """
    def call(img: bytes, prompt: str) -> str:
        transient, quota, fatal = None, None, None
        for _, fn in callers:
            try:
                return fn(img, prompt)
            except Exception as e:
                code = _status_code(e)
                if code in FATAL:
                    fatal = fatal or e
                elif code == 429:            # 한도는 모델별 → 다음 모델로
                    quota = quota or e
                elif code in TRANSIENT:
                    transient = transient or e
                else:
                    raise
        raise transient or quota or fatal

    return call


def _with_thinking_fallback(gen: Callable[[int | None], str], thinking: int | None) -> str:
    """생각(thinking) 예산을 지정해 호출하고, 모델이 그 설정을 받지 않으면(400) 설정 없이 다시 호출."""
    if thinking is None:
        return gen(None)
    try:
        return gen(thinking)
    except Exception as e:
        if _status_code(e) == 400:
            return gen(None)
        raise


def gemini_caller(api_key: str, models: str | list[str], thinking: int | None = 0) -> Caller:
    """thinking: 생각 토큰 예산. 0이면 끔(토큰 약 40% 절감), None이면 모델 기본값."""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    names = [m.strip() for m in (models.split(",") if isinstance(models, str) else models) if m.strip()]

    def one(model: str) -> Caller:
        def call(img: bytes, prompt: str) -> str:
            def gen(budget: int | None) -> str:
                extra = {} if budget is None else {"thinking_config": types.ThinkingConfig(thinking_budget=budget)}
                resp = client.models.generate_content(
                    model=model,
                    contents=[types.Part.from_bytes(data=img, mime_type="image/png"), prompt],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json", temperature=0,
                        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                        **extra),
                )
                return resp.text or ""
            return _with_thinking_fallback(gen, thinking)
        return call

    return chain_callers([(m, one(m)) for m in names])
