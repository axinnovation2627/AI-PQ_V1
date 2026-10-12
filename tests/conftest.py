import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pqweb.criteria import load_criteria  # noqa: E402
from pqweb.models import CareerRow  # noqa: E402


@pytest.fixture(scope="session")
def crit():
    return load_criteria()


@pytest.fixture
def row():
    def make(사업명, 담당업무="안전점검", 발주자="", 공사종류="", 시작일="2020.03.01",
             종료일="2020.10.01", 인정일=20, 구분="기술경력", 공사개요="", 쪽=1):
        return CareerRow(시작일=시작일, 종료일=종료일, 인정일=인정일, 사업명=사업명, 구분=구분,
                         발주자=발주자, 공사종류=공사종류, 담당업무=담당업무, 공사개요=공사개요, 쪽=쪽)
    return make
