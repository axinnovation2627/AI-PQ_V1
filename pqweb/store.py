"""평가 1건 = 폴더 1개. DB 없이 JSON 파일로 보관한다."""
from __future__ import annotations

import json
import re
import time
from datetime import datetime
from pathlib import Path

from .criteria import ROOT

BASE = ROOT / "data" / "evaluations"


_RETRY_SLEEP = 0.05


def write_json(path: Path, data) -> None:
    """임시 파일에 쓴 뒤 바꿔 끼운다.

    Windows에서는 화면이 같은 파일을 읽는 순간 바꿔 끼우기가 PermissionError로 실패하므로
    잠깐씩 다시 시도하고, 끝내 안 되면 직접 덮어쓴다.
    """
    text = json.dumps(data, ensure_ascii=False, indent=2)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    for _ in range(20):
        try:
            tmp.replace(path)
            return
        except PermissionError:
            time.sleep(_RETRY_SLEEP)
    path.write_text(text, encoding="utf-8")
    tmp.unlink(missing_ok=True)


def read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def safe_name(s: str) -> str:
    return re.sub(r'[\\/:*?"<>|\s]+', "_", s.strip()) or "무명"


def new_eval(pdf: bytes, meta: dict, base: Path = BASE) -> Path:
    now = datetime.now()
    d = base / f"{now:%Y%m%d-%H%M%S}_{safe_name(meta.get('성명', ''))}"
    d.mkdir(parents=True, exist_ok=False)
    (d / "source.pdf").write_bytes(pdf)
    write_json(d / "meta.json", {**meta, "생성": f"{now:%Y-%m-%d %H:%M:%S}"})
    write_json(d / "status.json", {"단계": "대기", "완료쪽": 0, "전체쪽": 0, "실패쪽": [], "오류": ""})
    return d


def get_eval(eval_id: str, base: Path = BASE) -> Path | None:
    """평가 폴더. 경로 조작(../ 등)을 막기 위해 data 폴더 바로 아래 폴더만 허용한다.
    (성명에 괄호 등이 들어가도 열 수 있어야 하므로 글자 종류로 막지 않는다.)"""
    if not eval_id or eval_id in (".", "..") or any(c in eval_id for c in '/\\:'):
        return None
    d = base / eval_id
    try:
        ok = d.resolve().parent == base.resolve() and d.is_dir()
    except OSError:
        return None
    return d if ok else None


def list_evals(base: Path = BASE) -> list[dict]:
    if not base.exists():
        return []
    out = []
    for d in sorted(base.iterdir(), reverse=True):
        if d.is_dir():
            out.append({"id": d.name, "meta": read_json(d / "meta.json", {}),
                        "status": read_json(d / "status.json", {})})
    return out
