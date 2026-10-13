"""Vercel 진입점: PQ 경력평가 웹을 체험판(PQ_DEMO=1)으로 실행한다."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("PQ_DEMO", "1")

from pqweb.server import app  # noqa: E402,F401
