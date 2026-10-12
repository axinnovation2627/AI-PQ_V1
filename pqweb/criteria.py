"""평가기준 규칙 파일(YAML) 읽기·검사·저장·이력.

기준 파일은 사람이 화면(평가기준 편집 / 점수 편집)에서 고친다. 저장할 때마다 이전 파일을
criteria/backup/에 남기고, 형식이 틀린 값은 저장 전에 막는다.
"""
from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DEFAULT = ROOT / "criteria" / "2026_비탈면옹벽.yaml"
ROLES = ("사업책임", "분야책임", "분야참여")

# 화면이 편집하는 항목 구분
RULE_KEYS = ("이름", "기산일", "정의", "근거", "용역어휘", "용역제외어휘", "급경사지어휘", "대상어휘", "비대상어휘",
             "교량명정규식", "대상공사종류", "비대상공사종류", "개요대상어휘", "관련어휘", "유사어휘",
             "지방도약칭정규식", "고속노선정규식", "진단성능어휘", "정기어휘")
SCORE_KEYS = ("일수_연환산", "인정율", "배점")
WORD_LISTS = ("용역어휘", "용역제외어휘", "급경사지어휘", "대상어휘", "비대상어휘", "대상공사종류",
              "비대상공사종류", "개요대상어휘", "진단성능어휘", "정기어휘")
REGEXES = ("교량명정규식", "지방도약칭정규식", "고속노선정규식")


def load_criteria(path: str | Path = DEFAULT) -> dict:
    with open(path, encoding="utf-8") as f:
        crit = yaml.safe_load(f)
    validate(crit)
    return crit


def _words(v, where: str, allow_empty: bool = False) -> None:
    if not isinstance(v, list) or not all(isinstance(x, str) and x.strip() for x in v):
        raise ValueError(f"{where}: 글자 목록이어야 하고 빈 칸이 있으면 안 됩니다")
    if not v and not allow_empty:
        raise ValueError(f"{where}: 최소 1개 이상 있어야 합니다")


def _regex(v, where: str) -> None:
    try:
        re.compile(v)
    except (re.error, TypeError) as e:
        raise ValueError(f"{where}: 정규식 문법 오류 — {e}")


def validate(crit: dict) -> None:
    """기준이 판정·점수 계산에 쓸 수 있는 형태인지 검사. 틀리면 무엇이 틀렸는지 ValueError."""
    if not isinstance(crit, dict):
        raise ValueError("기준 파일 형식이 아닙니다")
    missing = [k for k in RULE_KEYS + SCORE_KEYS if k not in crit]
    if missing:
        raise ValueError(f"빠진 항목: {', '.join(missing)}")
    if not re.fullmatch(r"\d{4}\.\d{2}\.\d{2}", str(crit["기산일"])):
        raise ValueError("기산일은 YYYY.MM.DD 형식이어야 합니다")
    try:
        datetime.strptime(str(crit["기산일"]), "%Y.%m.%d")
    except ValueError:
        raise ValueError("기산일이 없는 날짜입니다")
    if not str(crit["이름"]).strip():
        raise ValueError("기준 이름이 비어 있습니다")
    dfn = crit["정의"]
    try:
        names = [dfn["해당분야"], dfn["용역유형"]["진단성능"], dfn["용역유형"]["점검"],
                 dfn["도로유형"]["당해분야"], dfn["도로유형"]["그외분야"]]
    except (KeyError, TypeError):
        raise ValueError("정의(해당분야·용역유형·도로유형) 형식 오류")
    if not all(isinstance(x, str) and x.strip() for x in names):
        raise ValueError("정의: 해당분야·용역유형·도로유형 이름이 비어 있습니다")
    if not isinstance(crit["근거"], dict) or not all(isinstance(v, str) for v in crit["근거"].values()):
        raise ValueError("근거 문구 형식 오류")
    for k in WORD_LISTS:
        _words(crit[k], k, allow_empty=k in ("용역제외어휘", "급경사지어휘", "정기어휘"))
    for k in REGEXES:
        _regex(crit[k], k)
    rel = crit["관련어휘"]
    if not isinstance(rel, dict):
        raise ValueError("관련어휘 형식 오류")
    _words(rel.get("사업명", []), "관련어휘.사업명", allow_empty=True)
    _words(rel.get("발주자", []), "관련어휘.발주자", allow_empty=True)
    for i, pat in enumerate(rel.get("사업명정규식", []) or []):
        _regex(pat, f"관련어휘.사업명정규식[{i + 1}]")
    sim = crit["유사어휘"]
    if not isinstance(sim, dict) or not isinstance(sim.get("사업명"), dict) or not isinstance(sim.get("발주자"), dict):
        raise ValueError("유사어휘 형식 오류")
    for part in ("사업명", "발주자"):
        for label, words in sim[part].items():
            if not str(label).strip():
                raise ValueError(f"유사어휘.{part}: 도로 종류 이름이 비어 있습니다")
            _words(words, f"유사어휘.{part}.{label}", allow_empty=True)

    n = crit["일수_연환산"]
    if not isinstance(n, int) or isinstance(n, bool) or not 1 <= n <= 366:
        raise ValueError("일→년 환산일수는 1~366 사이 정수여야 합니다")
    rates = crit["인정율"]
    for g in ("유사", "관련"):
        for k in ("진단성능", "점검"):
            v = (rates.get(g) or {}).get(k)
            if not isinstance(v, (int, float)) or isinstance(v, bool) or not 0 <= v <= 1:
                raise ValueError(f"인정율 {g}·{k}는 0~100% 사이여야 합니다")
    bands = crit["배점"]
    for role in ROLES:
        rows = bands.get(role)
        if not isinstance(rows, list) or not rows:
            raise ValueError(f"배점표 {role}: 구간이 없습니다")
        prev = None
        for row in rows:
            if (not isinstance(row, list) or len(row) != 2
                    or not all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in row)):
                raise ValueError(f"배점표 {role}: [기준년수, 점수] 형식이어야 합니다")
            th, pts = row
            if th < 0 or pts < 0:
                raise ValueError(f"배점표 {role}: 음수는 쓸 수 없습니다")
            if prev is not None and th >= prev:
                raise ValueError(f"배점표 {role}: 기준년수는 위에서 아래로 줄어들어야 합니다")
            prev = th
        if rows[-1][0] != 0:
            raise ValueError(f"배점표 {role}: 마지막 구간은 0년(그 미만 전부)이어야 합니다")


BACKUP = DEFAULT.parent / "backup"


def save_criteria(crit: dict, path: Path = DEFAULT, note: str = "") -> Path | None:
    """검사 후 저장. 저장 전 파일을 backup/에 남기고 백업 경로를 돌려준다."""
    validate(crit)
    path = Path(path)
    backup_dir = path.parent / "backup"
    backup_dir.mkdir(exist_ok=True)
    saved = None
    if path.exists():
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")[:-3]
        tag = re.sub(r'[\\/:*?"<>|\s]+', "_", note.strip())[:30]
        saved = backup_dir / f"{path.stem}__{stamp}{'__' + tag if tag else ''}.yaml"
        shutil.copy2(path, saved)
    text = ("# 평가기준 — 화면(평가기준 편집 / 점수 편집)에서 저장됨. 이전 내용은 backup/ 폴더에 있음\n"
            + yaml.safe_dump(crit, allow_unicode=True, sort_keys=False, default_flow_style=None, width=4096))
    tmp = path.with_suffix(".yaml.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)
    return saved


def history(path: Path = DEFAULT) -> list[dict]:
    backup_dir = Path(path).parent / "backup"
    if not backup_dir.exists():
        return []
    out = []
    for f in sorted(backup_dir.glob(f"{Path(path).stem}__*.yaml"), reverse=True):
        parts = f.stem.split("__")
        when = datetime.strptime(parts[1][:15], "%Y%m%d-%H%M%S").strftime("%Y-%m-%d %H:%M:%S")
        out.append({"파일": f.name, "저장전시각": when, "메모": parts[2] if len(parts) > 2 else ""})
    return out


def restore(name: str, path: Path = DEFAULT) -> dict:
    backup_dir = Path(path).parent / "backup"
    f = backup_dir / name
    if "/" in name or "\\" in name or not f.is_file() or f.parent != backup_dir:
        raise ValueError("백업 파일을 찾을 수 없습니다")
    crit = yaml.safe_load(f.read_text(encoding="utf-8"))
    save_criteria(crit, path, note="되돌리기 전")
    return crit
