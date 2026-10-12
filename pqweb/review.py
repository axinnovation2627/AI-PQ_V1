"""평가위원 평가: 행 식별 키, 입력 검증, 저장.

행 키는 'p{쪽}-{쪽 안 순번}'이다. 실패 쪽 다시 읽기로 행이 늘어나도 기존 행의 키는 바뀌지 않아
이미 입력한 평가위원 판단이 엉뚱한 행으로 옮겨 가지 않는다.
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from .models import CareerRow
from .store import read_json, write_json

CHOICES = ("유사", "관련", "불인정")
EMPTY = {"평가위원": "", "rows": {}}


def row_keys(rows: list[CareerRow]) -> list[str]:
    seen: dict[int, int] = defaultdict(int)
    keys = []
    for r in rows:
        seen[r.쪽] += 1
        keys.append(f"p{r.쪽:02d}-{seen[r.쪽]}")
    return keys


def clean(body: dict, keys: list[str]) -> dict:
    """화면에서 받은 평가위원 입력을 검증한다. 잘못되면 ValueError."""
    valid = set(keys)
    out = {"평가위원": str(body.get("평가위원") or "").strip()[:40], "rows": {}}
    for k, v in (body.get("rows") or {}).items():
        if k not in valid:
            raise ValueError(f"없는 행: {k}")
        v = v or {}
        choice = v.get("인정여부") or ""
        if choice and choice not in CHOICES:
            raise ValueError(f"{k}: 인정여부는 {', '.join(CHOICES)} 중 하나")
        rate = v.get("인정율")
        if rate in ("", None):
            rate = None
        else:
            rate = float(rate)
            if not 0 <= rate <= 1:
                raise ValueError(f"{k}: 인정율은 0~1")
        reason = str(v.get("사유") or "").strip()[:500]
        if choice or rate is not None or reason:
            out["rows"][k] = {"인정여부": choice, "인정율": rate, "사유": reason}
    return out


def load(d: Path) -> dict:
    return read_json(d / "review.json", None) or {"평가위원": "", "rows": {}}


def save(d: Path, review: dict) -> None:
    write_json(d / "review.json", review)


def aligned(review: dict, keys: list[str]) -> list[dict | None]:
    """엑셀 행 순서에 맞춘 평가위원 입력 목록."""
    return [review["rows"].get(k) for k in keys]
