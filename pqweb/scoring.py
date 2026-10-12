"""환산일수·환산년수·참여형태별 경력 점수 (가-2 ①)."""
from __future__ import annotations

from .criteria import ROLES
from .models import Judgement, Score


def band(years: float, role: str, crit: dict) -> float:
    for th, pts in crit["배점"][role]:
        if years >= th:
            return float(pts)
    return float(crit["배점"][role][-1][1])


def score(judgements: list[Judgement], days: list[int], crit: dict) -> Score:
    s = Score()
    for j, d in zip(judgements, days):
        if j.인정여부 == "유사":
            s.유사_인정일 += d
            s.유사_환산일 += j.환산일수
        elif j.인정여부 == "관련":
            s.관련_인정일 += d
            s.관련_환산일 += j.환산일수
    s.유사_환산일 = round(s.유사_환산일, 2)
    s.관련_환산일 = round(s.관련_환산일, 2)
    s.환산년수 = round((s.유사_환산일 + s.관련_환산일) / crit["일수_연환산"], 4)
    s.점수 = {role: band(s.환산년수, role, crit) for role in ROLES}
    return s
