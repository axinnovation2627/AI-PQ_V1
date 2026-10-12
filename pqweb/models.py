"""평가 데이터 구조. 모든 모듈이 이 형태로 주고받는다."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict

TECH = "기술경력"
CM = "건설사업관리·감리"


@dataclass
class CareerRow:
    시작일: str                 # "YYYY.MM.DD"
    종료일: str                 # "YYYY.MM.DD" 또는 "근무중"
    인정일: int
    사업명: str
    구분: str = TECH
    발주자: str = ""
    공사종류: str = ""
    직무분야: str = ""
    전문분야: str = ""
    담당업무: str = ""
    직위: str = ""
    공사개요: str = ""
    금액: str = ""
    시설물종류: str = ""
    쪽: int = 0

    @classmethod
    def from_dict(cls, d: dict) -> "CareerRow":
        known = {k: d[k] for k in cls.__dataclass_fields__ if k in d}
        for k in ("인정일", "쪽"):
            digits = "".join(ch for ch in str(known.get(k) or "") if ch.isdigit())
            known[k] = int(digits) if digits else 0
        for k, v in list(known.items()):
            if v is None:
                known[k] = ""
        return cls(**known)


@dataclass
class CertInfo:
    성명: str = ""
    등급: str = ""
    자격: list[str] = field(default_factory=list)
    교육: list[str] = field(default_factory=list)
    근무처: list[str] = field(default_factory=list)


@dataclass
class CertTotals:
    공사종류별: dict[str, int] = field(default_factory=dict)
    합계: int = 0


@dataclass
class Judgement:
    인정여부: str               # 유사 | 관련 | 불인정
    분야: str = "-"             # 성능평가·진단 | 정밀점검 | -
    인정율: float | None = None
    환산일수: float = 0.0
    근거: str = ""
    확인필요: list[str] = field(default_factory=list)
    규칙: str = ""              # 결정 단계 ID
    # 평가기준 정의의 세 축 (불인정 행도 AI가 본 값을 모두 기록)
    해당분야: str = ""          # 예: 비탈면·옹벽 / 교량·터널
    용역유형: str = ""          # 정밀안전진단·성능평가 | 정밀안전점검·긴급안전점검
    도로유형: str = ""          # 당해분야(도로법 제10조 도로) | 그 외 분야
    해당분야근거: str = ""
    용역유형근거: str = ""
    도로유형근거: str = ""


@dataclass
class Score:
    유사_인정일: int = 0
    관련_인정일: int = 0
    유사_환산일: float = 0.0
    관련_환산일: float = 0.0
    환산년수: float = 0.0
    점수: dict[str, float] = field(default_factory=dict)   # 참여형태 -> 점수


@dataclass
class CheckReport:
    형식오류: list[str] = field(default_factory=list)
    대조: list[dict] = field(default_factory=list)          # {공사종류, 판독, 증명서, 행수, 상태}
    대조가능: bool = True
    실패쪽: list[int] = field(default_factory=list)

    @property
    def 정상(self) -> bool:
        return (not self.형식오류 and not self.실패쪽 and self.대조가능
                and all(c["상태"] == "정상" for c in self.대조))


def to_dict(obj) -> dict:
    d = asdict(obj)
    if isinstance(obj, CheckReport):
        d["정상"] = obj.정상
    return d
