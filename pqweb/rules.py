"""가-2) 경력 판정 규칙.

행마다 단계 R0~R5를 차례로 적용하고, 처음 결론이 난 단계에서 멈춘다.
규칙 어휘와 근거 조항은 criteria YAML에 있고, 여기서는 해석만 한다.
규칙에 없는 표현은 추측하지 않고 '확인필요'로 남긴다.
"""
from __future__ import annotations

import re
from collections import Counter
from datetime import date

from .models import CM, CareerRow, Judgement


def _date(s: str) -> date | None:
    m = re.match(r"\s*(\d{4})\D(\d{1,2})\D(\d{1,2})", s or "")
    return date(int(m[1]), int(m[2]), int(m[3])) if m else None


def _has(text: str, words) -> str | None:
    for w in words:
        if w and w in (text or ""):
            return w
    return None


def _strip(text: str, words) -> str:
    for w in words:
        text = text.replace(w, "")
    return text


def _no(r: Judgement, rule: str, why: str, *flags: str) -> Judgement:
    r.인정여부, r.규칙, r.근거 = "불인정", rule, why
    r.확인필요.extend(flags)
    return r


def _service_axis(row: CareerRow, crit: dict):
    """② 용역유형. (키 '진단성능'|'점검'|None, 근거, 확인필요)"""
    name = row.사업명 or ""
    if row.구분 == CM:
        return None, "건설사업관리·감리 경력", None
    if _has(name, crit["급경사지어휘"]):
        return None, "급경사지 용역", "급경사지 용역: 시설물안전법 용역으로 확인되면 인정 가능"
    svc_name = _strip(name, crit["용역제외어휘"])
    hit = _has(svc_name, crit["용역어휘"])
    if not hit:
        return None, "사업명에 점검·진단·성능평가 없음", None
    dx = _has(svc_name, crit["진단성능어휘"])
    return ("진단성능", f"사업명 '{dx}'", None) if dx else ("점검", f"사업명 '{hit}'", None)


def _field_axis(row: CareerRow, crit: dict):
    """① 해당분야. (True|False|None, 근거, 확인필요 목록)"""
    name, kind = row.사업명 or "", row.공사종류 or ""
    bridge = re.search(crit["교량명정규식"], name)
    t = _has(name, crit["대상어휘"])
    nt = _has(name, crit["비대상어휘"]) or (bridge.group(0) if bridge else None)
    flags = []
    if t and not nt:
        return True, f"사업명 '{t}'", flags
    if nt and not t:
        return False, f"사업명 '{nt}'", flags
    if t and nt:
        flags.append(f"사업명에 대상('{t}')·비대상('{nt}') 어휘 혼재")
    kt, knt = _has(kind, crit["대상공사종류"]), _has(kind, crit["비대상공사종류"])
    if kt and not knt:
        return True, f"공사종류 '{kt}'", flags
    if knt:
        return False, f"공사종류 '{knt}'", flags
    if (ot := _has(row.공사개요, crit["개요대상어휘"])):
        return True, f"공사개요 '{ot}'", flags
    return None, "사업명·공사종류·공사개요로 확인 불가", flags


def _road_axis(row: CareerRow, crit: dict):
    """③ 도로유형. (당해분야 여부, 근거, 노선 미기재 여부)"""
    name = row.사업명 or ""
    rel = crit["관련어휘"]
    hit = _has(name, rel["사업명"]) or _has(row.발주자, rel["발주자"])
    if not hit:
        for pat in rel.get("사업명정규식", []):
            if (m := re.search(pat, name)):
                hit = m.group(0)
                break
    if hit:
        return False, f"'{hit}'", False
    sim = crit["유사어휘"]
    if _has(name, sim["사업명"]["고속국도"]) or re.search(crit["고속노선정규식"], name):
        return True, "고속국도", False
    if re.search(crit["지방도약칭정규식"], name):
        return True, "지방도", False
    for part, text in (("사업명", name), ("발주자", row.발주자)):
        for label, words in sim[part].items():
            if _has(text, words):
                return True, label, False
    return True, "노선 미기재", True


def judge_row(row: CareerRow, crit: dict) -> Judgement:
    g, dfn = crit["근거"], crit["정의"]
    field = dfn["해당분야"]
    r = Judgement(인정여부="불인정")
    name = row.사업명 or ""

    # 세 축은 판정 결과와 상관없이 모두 기록한다(평가위원이 AI가 무엇을 봤는지 확인).
    svc, svc_why, svc_flag = _service_axis(row, crit)
    fld, fld_why, fld_flags = _field_axis(row, crit)
    is_main, road_why, road_unknown = _road_axis(row, crit)
    r.용역유형 = dfn["용역유형"][svc] if svc else "해당 없음"
    r.용역유형근거 = svc_why
    r.해당분야 = field if fld else ("아님" if fld is False else "확인 불가")
    r.해당분야근거 = fld_why
    r.도로유형 = ("당해분야 (가정)" if road_unknown else "당해분야") if is_main else "그 외 분야"
    r.도로유형근거 = road_why

    # R0 기간
    start, end = _date(row.시작일), _date(row.종료일)
    base = _date(crit["기산일"])
    if end is None:
        return _no(r, "R0", f"종료일 '{row.종료일}' — 준공되지 않은 용역 ({g['준공']})")
    if end < base:
        return _no(r, "R0", f"{crit['기산일']} 이전 경력 ({g['기산일']})")
    straddles = bool(start and start < base)   # 인정되는 경우에만 확인필요로 남긴다

    # R1 경력 구분
    if row.구분 == CM:
        return _no(r, "R1", "건설사업관리·감리 경력 — 점검·진단·성능평가 용역 아님")

    # R2 용역유형
    if svc is None:
        if svc_flag:
            return _no(r, "R2", "급경사지 용역 — 시설물안전법 제11~13조·40조 용역 여부 불명", svc_flag)
        return _no(r, "R2", f"용역유형 해당 없음 — 점검·진단·성능평가 용역 아님 ({g['용역']})")

    # R3 해당분야
    r.확인필요.extend(fld_flags)
    if fld is False:
        return _no(r, "R3", f"{fld_why} — 해당분야({field}) 아님")
    if fld is None:
        return _no(r, "R3", f"해당분야({field}) 여부를 사업명·공사종류·공사개요로 확인할 수 없음",
                   f"해당분야 확인 불가: {field} 대상인지 확인 필요")

    # R4 도로유형
    if is_main:
        grade = "유사"
        if road_unknown:
            r.확인필요.append("노선 미기재: 도로법 제10조 도로(시도·군도 등)면 유사, 면도·리도 등이면 관련")
            where = f"당해분야로 가정(노선 미기재) → 유사용역 ({g['유사']})"
        else:
            where = f"당해분야({road_why} — {dfn['도로유형']['당해분야']}) → 유사용역 ({g['유사']})"
    else:
        grade = "관련"
        where = f"그 외 분야({road_why} — {dfn['도로유형']['그외분야']}) → 관련용역 ({g['관련']})"
        r.확인필요.append("관련용역: 건축분야 제외 해당 여부 확인 필요(해당 시 불인정)")

    # R5 인정율 (사업명 기준)
    rates = crit["인정율"][grade]
    by_job = "진단성능" if _has(row.담당업무, crit["진단성능어휘"]) else "점검"
    r.인정여부 = grade
    r.인정율 = rates[svc]
    r.분야 = "성능평가·진단" if svc == "진단성능" else "정밀점검"
    r.환산일수 = round(row.인정일 * r.인정율, 2)
    r.규칙 = "R5"
    r.근거 = (f"해당분야: {field}({fld_why}) / 도로유형: {where} / "
              f"용역유형: {r.용역유형}(사업명 기준) → {int(r.인정율 * 100)}% (가-2 ③)")
    if by_job != svc:
        jr = int(rates[by_job] * 100)
        r.확인필요.append(f"담당업무 '{row.담당업무}' 기준이면 {jr}% — {g['명시']}")
    if straddles:
        r.확인필요.append(f"참여기간이 기산일({crit['기산일']})에 걸침 — 기산일 이후분만 인정 가능")
    if _has(name, crit["정기어휘"]):
        r.확인필요.append("사업명에 정기점검 포함 — 정기점검은 대상 용역 아님, 인정일 분리 근거 없음")
    return r


def judge_all(rows: list[CareerRow], crit: dict) -> list[Judgement]:
    res = [judge_row(row, crit) for row in rows]
    key = lambda x: (x.사업명.replace(" ", ""), x.시작일, x.종료일, x.인정일)
    dup = Counter(key(x) for x in rows)
    for row, j in zip(rows, res):
        if dup[key(row)] > 1 and j.인정여부 != "불인정":
            j.확인필요.append("같은 용역(사업명·기간·인정일 동일)이 경력증명서에 2회 이상 기재")
    for row, j in zip(rows, res):
        if row.쪽:
            j.근거 = f"[p{row.쪽:02d}] {j.근거}"
    return res
