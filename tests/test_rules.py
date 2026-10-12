from pqweb.rules import judge_row, judge_all


def j(row, crit, **kw):
    return judge_row(row(**kw), crit)


# ── 유사 ──
def test_expressway_performance_100(row, crit):
    r = j(row, crit, 사업명="2023년 충북본부 깎기비탈면 옹벽 안전점검 및 성능평가용역 1권역(진천,보은)",
          발주자="한국도로공사충북본부", 공사종류="고속국도", 담당업무="안전점검")
    assert (r.인정여부, r.인정율, r.분야) == ("유사", 1.0, "성능평가·진단")
    assert any("담당업무" in x for x in r.확인필요)   # 담당업무엔 성능평가 미명시


def test_national_road_inspection_50(row, crit):
    r = j(row, crit, 사업명="국도35호선 삼척 갈전지구 외 5개소 절토사면 정밀안전점검용역",
          발주자="정선국토관리사무소", 공사종류="국도")
    assert (r.인정여부, r.인정율) == ("유사", 0.5)
    assert r.확인필요 == []


def test_local_road_by_abbreviation(row, crit):
    r = j(row, crit, 사업명="지방도424호개수1옹벽외2개소정밀점검용역", 발주자="강원도도로관리사업소",
          공사종류="옹벽", 담당업무="정밀점검")
    assert (r.인정여부, r.인정율) == ("유사", 0.5)


def test_performance_in_job_no_flag(row, crit):
    r = j(row, crit, 사업명="2025년 대전충남본부 깎기비탈면 옹벽 정밀(정기)안전점검 및 성능평가 용역",
          발주자="한국도로공사대전충남본부", 담당업무="정밀안전점검,성능평가")
    assert (r.인정여부, r.인정율) == ("유사", 1.0)
    assert not any("담당업무" in x for x in r.확인필요)
    assert any("정기" in x for x in r.확인필요)


def test_unknown_route_assumed_similar_flagged(row, crit):
    r = j(row, crit, 사업명="덕송리콘크리트옹벽등4개소정밀점검용역", 발주자="정선군", 공사종류="옹벽")
    assert r.인정여부 == "유사"
    assert any("노선" in x for x in r.확인필요)


# ── 관련 ──
def test_school_retaining_wall_related(row, crit):
    r = j(row, crit, 사업명="인제초등학교부지경계옹벽정밀안전진단용역", 발주자="강원도교육청",
          공사종류="옹벽", 담당업무="정밀안전진단")
    assert (r.인정여부, r.인정율) == ("관련", 0.6)
    assert any("건축분야" in x for x in r.확인필요)


def test_industrial_complex_wall_related_30(row, crit):
    r = j(row, crit, 사업명="우천제2농공단지시특법시설물(보강토옹벽)정밀점검용역", 발주자="횡성군청",
          담당업무="정밀점검")
    assert (r.인정여부, r.인정율) == ("관련", 0.3)


# ── 불인정 ──
def test_bridge_not_target(row, crit):
    r = j(row, crit, 사업명="국도46호선 당림교 정밀안전진단 및 성능평가용역",
          발주자="홍천국토관리사무소", 공사종류="장대교량(100m이상)")
    assert r.인정여부 == "불인정" and r.규칙 == "R3"


def test_tunnel_not_target(row, crit):
    r = j(row, crit, 사업명="국도56호선 솔치재터널 외 3개소 정밀점검용역", 공사종류="터널")
    assert r.인정여부 == "불인정"


def test_design_not_service(row, crit):
    r = j(row, crit, 사업명="부안-변산우회도로건설공사실시설계용역", 담당업무="설계", 공사종류="도로")
    assert r.인정여부 == "불인정" and r.규칙 == "R2"


def test_cm_career_excluded(row, crit):
    r = j(row, crit, 사업명="국도35호선새터교신축공사전면책임감리용역", 구분="건설사업관리·감리")
    assert r.인정여부 == "불인정" and r.규칙 == "R1"


def test_ongoing_excluded(row, crit):
    r = j(row, crit, 사업명="2023~2025년 구조물 정밀안전점검 진단 및 성능평가 통합 용역", 종료일="근무중")
    assert r.인정여부 == "불인정" and r.규칙 == "R0"


def test_before_1995_excluded(row, crit):
    r = j(row, crit, 사업명="국도38호선절토사면 정밀점검용역", 시작일="1994.03.01", 종료일="1994.10.01")
    assert r.인정여부 == "불인정" and r.규칙 == "R0"


def test_cutoff_flag_only_when_recognized(row, crit):
    r = j(row, crit, 사업명="오류제1구역주택개량재개발공사", 담당업무="감리/상주",
          시작일="1994.12.01", 종료일="1996.06.30")
    assert r.인정여부 == "불인정" and r.확인필요 == []
    r = j(row, crit, 사업명="국도38호선절토사면(2종)정밀점검용역", 발주자="정선국도유지건설사무소",
          시작일="1994.12.01", 종료일="1995.06.30")
    assert r.인정여부 == "유사" and any("기산일" in x for x in r.확인필요)


def test_steep_slope_flagged(row, crit):
    r = j(row, crit, 사업명="급경사지(덕두원지구,현암지구)안정성검토용역(정밀안전진단)")
    assert r.인정여부 == "불인정" and any("급경사지" in x for x in r.확인필요)


def test_seismic_evaluation_not_service(row, crit):
    r = j(row, crit, 사업명="국도46호선 고원통1교 등 4개소 내진성능평가용역", 공사종류="장대교량(100m이상)")
    assert r.인정여부 == "불인정"


def test_target_from_work_type_when_name_silent(row, crit):
    r = j(row, crit, 사업명="정선국도관내시설물정밀점검용역", 발주자="정선국토관리사무소", 공사종류="옹벽",
          담당업무="정밀점검")
    assert (r.인정여부, r.인정율) == ("유사", 0.5)


def test_target_unknown_flagged(row, crit):
    r = j(row, crit, 사업명="정선국도관내시설물정밀점검용역", 발주자="정선국토관리사무소", 공사종류="")
    assert r.인정여부 == "불인정" and any("해당분야 확인 불가" in x for x in r.확인필요)


# ── 부가 ──
def test_duplicate_rows_flagged(row, crit):
    a = row(사업명="2022년 강원본부 비탈면옹벽 정밀안전점검용역(1권역)", 발주자="한국도로공사강원본부",
            인정일=25, 시작일="2022.03.30", 종료일="2022.12.04")
    b = row(사업명="2022년 강원본부 비탈면옹벽 정밀안전점검용역(1권역)", 발주자="한국도로공사강원본부",
            인정일=25, 시작일="2022.03.30", 종료일="2022.12.04")
    res = judge_all([a, b], crit)
    assert all(any("2회" in x for x in r.확인필요) for r in res)


def test_converted_days(row, crit):
    r = j(row, crit, 사업명="국도38호선 정선문곡지구 외 6개소 옹벽 정밀안전점검용역", 발주자="정선국토관리사무소",
          인정일=17)
    assert r.환산일수 == 8.5
    assert "세부 1-나" in r.근거


# ── 세 축 정의: 해당분야 · 용역유형 · 도로유형 ──
def test_three_axes_similar(row, crit):
    r = j(row, crit, 사업명="2023년 충북본부 깎기비탈면 옹벽 안전점검 및 성능평가용역", 발주자="한국도로공사충북본부")
    assert (r.해당분야, r.도로유형, r.용역유형) == ("비탈면·옹벽", "당해분야", "정밀안전진단·성능평가")
    assert "해당분야: 비탈면·옹벽" in r.근거 and "도로유형: 당해분야" in r.근거 and "용역유형: 정밀안전진단·성능평가" in r.근거


def test_three_axes_related_inspection(row, crit):
    r = j(row, crit, 사업명="우천제2농공단지시특법시설물(보강토옹벽)정밀점검용역", 발주자="횡성군청")
    assert (r.인정여부, r.도로유형, r.용역유형, r.인정율) == ("관련", "그 외 분야", "정밀안전점검·긴급안전점검", 0.3)


def test_three_axes_not_field(row, crit):
    r = j(row, crit, 사업명="국도46호선 당림교 정밀안전진단 및 성능평가용역", 공사종류="장대교량(100m이상)")
    assert r.인정여부 == "불인정" and r.해당분야 == "아님" and "해당분야(비탈면·옹벽) 아님" in r.근거
    assert r.용역유형 == "정밀안전진단·성능평가" and r.도로유형 == "당해분야"


def test_axes_recorded_for_design_job(row, crit):
    r = j(row, crit, 사업명="부안-변산우회도로건설공사실시설계용역", 담당업무="설계", 공사종류="도로")
    assert r.인정여부 == "불인정" and r.용역유형 == "해당 없음" and "점검·진단·성능평가 없음" in r.용역유형근거
