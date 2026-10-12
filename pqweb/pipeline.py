"""판독 → 대조 → 판정 → 점수 → 엑셀. 진행 상황은 status.json에 기록한다."""
from __future__ import annotations

import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .assemble import assemble
from .crosscheck import check
from .excel_export import export
from .models import to_dict
from .pdf_pages import render_pages
from .reader_gemini import Caller, ReadError, parse_response, read_page
from .rules import judge_all
from .scoring import score
from .store import read_json, safe_name, write_json


def _status(d: Path, **kw) -> dict:
    st = read_json(d / "status.json", {}) | kw
    write_json(d / "status.json", st)
    return st


def run(d: Path, call: Caller, crit: dict, workers: int = 1, resume: bool = False) -> dict:
    """resume=True: 이미 판독된 쪽(raw/pNN.json)은 다시 읽지 않고 실패 쪽만 읽는다."""
    try:
        meta = read_json(d / "meta.json", {})
        _status(d, 단계="쪽변환", 오류="")
        pngs = sorted((d / "pages").glob("p*.png")) if resume else []
        if not pngs:
            pngs = render_pages(d / "source.pdf", d / "pages")
        _status(d, 단계="판독", 전체쪽=len(pngs), 완료쪽=0)

        (d / "raw").mkdir(exist_ok=True)
        pages, failed, errors = [], [], {}
        lock, stop = threading.Lock(), threading.Event()

        def work(i: int, png: Path):
            if stop.is_set():
                return
            done = d / "raw" / f"{png.stem}.json"
            try:
                if resume and done.exists():
                    parsed = parse_response(done.read_text(encoding="utf-8"))
                else:
                    raw, parsed = read_page(png, call)
                    done.write_text(raw, encoding="utf-8")
                    (d / "raw" / f"{png.stem}.error.txt").unlink(missing_ok=True)
                with lock:
                    pages.append((i, parsed))
            except ReadError as e:
                (d / "raw" / f"{png.stem}.error.txt").write_text(str(e), encoding="utf-8")
                with lock:
                    failed.append(i)
                    errors[i] = e
                if e.fatal:
                    stop.set()
            with lock:
                _status(d, 완료쪽=len(pages) + len(failed), 실패쪽=sorted(failed))

        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            list(pool.map(lambda a: work(*a), enumerate(pngs, 1)))

        fatal = next((f"p{i:02d} {e}" for i, e in sorted(errors.items()) if e.fatal), None)
        if fatal:
            return _status(d, 단계="오류", 실패쪽=sorted(failed), 오류=f"{fatal} — 판독을 중단했습니다.")
        if pngs and not pages:
            i, e = min(errors.items())
            return _status(d, 단계="오류", 오류=f"모든 쪽 판독 실패 — 첫 오류: p{i:02d} {e}")
        failed.sort()

        _status(d, 단계="판정")
        rows, info, totals = assemble(pages)
        rep = check(rows, totals, failed)
        js = judge_all(rows, crit)
        sc = score(js, [r.인정일 for r in rows], crit)
        write_json(d / "rows.json", {"rows": [to_dict(r) for r in rows], "info": to_dict(info),
                                     "totals": to_dict(totals)})
        write_json(d / "check.json", to_dict(rep))
        write_json(d / "judgements.json", {"judgements": [to_dict(j) for j in js], "score": to_dict(sc)})

        name = meta.get("성명") or info.성명
        xlsx = export(meta, info, rows, js, rep, crit, d / f"평가시트_{safe_name(name)}.xlsx")
        count = {k: sum(1 for j in js if j.인정여부 == k) for k in ("유사", "관련", "불인정")}
        result = {
            "건수": count, "확인필요": sum(1 for j in js if j.확인필요),
            "유사_인정일": sc.유사_인정일, "관련_인정일": sc.관련_인정일,
            "환산일수": round(sc.유사_환산일 + sc.관련_환산일, 1), "환산년수": round(sc.환산년수, 2),
            "점수": sc.점수, "대조": rep.대조, "대조가능": rep.대조가능, "판독정상": rep.정상,
            "형식오류": rep.형식오류, "등급": info.등급, "엑셀": xlsx.name,
        }
        return _status(d, 단계="완료", 결과=result)
    except Exception as e:
        (d / "error.log").write_text(traceback.format_exc(), encoding="utf-8")
        return _status(d, 단계="오류", 오류=str(e))
