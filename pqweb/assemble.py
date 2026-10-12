"""쪽별 판독 결과 → 경력 행 목록 + 인적사항 + 증명서 합계표."""
from __future__ import annotations

from .models import CM, TECH, CareerRow, CertInfo, CertTotals


def _join(a: str, b: str) -> str:
    return f"{a} {b}".strip() if b else a


def assemble(pages: list[tuple[int, dict]]) -> tuple[list[CareerRow], CertInfo, CertTotals]:
    rows: list[CareerRow] = []
    info = CertInfo()
    totals = CertTotals()
    for no, d in sorted(pages, key=lambda x: x[0]):
        kind = d.get("쪽종류")
        if kind == "인적사항":
            p = d.get("인적사항") or {}
            info.성명 = info.성명 or str(p.get("성명") or "")
            info.등급 = info.등급 or str(p.get("등급") or "")
            for key in ("자격", "교육", "근무처"):
                getattr(info, key).extend(str(x) for x in (p.get(key) or []) if x)
        elif kind in ("기술경력", "건설사업관리감리"):
            sect = TECH if kind == "기술경력" else CM
            for item in d.get("경력") or []:
                if item.get("이어짐"):
                    if rows:
                        prev = rows[-1]
                        prev.사업명 = _join(prev.사업명, item.get("사업명", ""))
                        prev.공사개요 = _join(prev.공사개요, item.get("공사개요", ""))
                    continue
                rows.append(CareerRow.from_dict({**item, "구분": sect, "쪽": no}))
        elif kind == "분야별인정일":
            for x in d.get("공사종류별") or []:
                if x["공사종류"]:
                    totals.공사종류별[x["공사종류"]] = totals.공사종류별.get(x["공사종류"], 0) + x["인정일"]
            totals.합계 = totals.합계 or d.get("합계", 0)
    return rows, info, totals
