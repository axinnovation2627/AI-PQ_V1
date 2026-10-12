from pqweb.crosscheck import check
from pqweb.models import CareerRow, CertTotals, Judgement
from pqweb.scoring import band, score


def test_band_edges(crit):
    assert band(3.0, "분야참여", crit) == 1.5
    assert band(2.99, "분야참여", crit) == 1.35
    assert band(0.4, "분야참여", crit) == 0.9
    assert band(6.0, "사업책임", crit) == 8.0
    assert band(4.9, "분야책임", crit) == 2.7


def test_score_sums(crit):
    js = [Judgement("유사", 인정율=1.0, 환산일수=365.0), Judgement("유사", 인정율=0.5, 환산일수=182.5),
          Judgement("관련", 인정율=0.6, 환산일수=182.5), Judgement("불인정")]
    days = [365, 365, 304, 100]
    s = score(js, days, crit)
    assert s.유사_인정일 == 730 and s.관련_인정일 == 304
    assert s.환산년수 == 2.0
    assert s.점수 == {"사업책임": 4.8, "분야책임": 2.1, "분야참여": 1.35}


def _row(kind, days, s="2020.01.01", e="2020.02.01"):
    return CareerRow(시작일=s, 종료일=e, 인정일=days, 사업명="x", 공사종류=kind)


def test_crosscheck_tolerance():
    rows = [_row("교량", 10), _row("교량", 10), _row("국도", 50)]
    rep = check(rows, CertTotals({"교량": 21, "국도": 50}, 71), failed_pages=[])
    assert rep.정상
    rep = check(rows, CertTotals({"교량": 23, "국도": 49}, 72), failed_pages=[])
    bad = {c["공사종류"]: c["상태"] for c in rep.대조}
    assert bad == {"교량": "판독 확인필요", "국도": "판독 확인필요"}


def test_crosscheck_format_and_missing_totals():
    rows = [_row("교량", 5, s="2020.05.01", e="2020.01.01"), _row("교량", -1)]
    rep = check(rows, None, failed_pages=[7])
    assert not rep.대조가능 and rep.실패쪽 == [7] and len(rep.형식오류) == 2 and not rep.정상
