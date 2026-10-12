"""판독 결과 자동 검증: 형식 검사 + 증명서 '공사종류별 인정일수 현황'과 합계 대조.

증명서 주석: 참여기간이 중복되면 행마다 소수점 이하를 절삭하므로, 증명서 합계가 판독 합계보다
행 수 이내로 클 수 있다. 0 <= 증명서 - 판독 <= 행 수 이면 정상으로 본다.
"""
from __future__ import annotations

from collections import Counter, defaultdict

from .models import CareerRow, CertTotals, CheckReport
from .rules import _date


def check(rows: list[CareerRow], totals: CertTotals | None, failed_pages: list[int]) -> CheckReport:
    rep = CheckReport(실패쪽=sorted(failed_pages))
    for i, r in enumerate(rows, 1):
        s, e = _date(r.시작일), _date(r.종료일)
        where = f"{i}번째 행(p{r.쪽:02d} {r.사업명[:20]})"
        if s is None:
            rep.형식오류.append(f"{where}: 시작일 '{r.시작일}' 형식 오류")
        if e is None and r.종료일 != "근무중":
            rep.형식오류.append(f"{where}: 종료일 '{r.종료일}' 형식 오류")
        if s and e and s > e:
            rep.형식오류.append(f"{where}: 시작일이 종료일보다 늦음")
        if r.인정일 < 0:
            rep.형식오류.append(f"{where}: 인정일 음수")

    if not totals or not totals.공사종류별:
        rep.대조가능 = False
        return rep
    got: dict[str, int] = defaultdict(int)
    cnt: Counter = Counter()
    for r in rows:
        got[r.공사종류 or "기타(미기재)"] += r.인정일
        cnt[r.공사종류 or "기타(미기재)"] += 1
    for kind in sorted(set(got) | set(totals.공사종류별)):
        cert = totals.공사종류별.get(kind, 0)
        diff = cert - got.get(kind, 0)
        ok = 0 <= diff <= cnt[kind]
        rep.대조.append({"공사종류": kind, "판독": got.get(kind, 0), "증명서": cert,
                       "행수": cnt[kind], "상태": "정상" if ok else "판독 확인필요"})
    return rep
