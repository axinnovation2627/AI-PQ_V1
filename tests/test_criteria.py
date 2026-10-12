def test_criteria_loads(crit):
    assert crit["기산일"] == "1995.01.05"
    assert crit["배점"]["분야참여"][0] == [3, 1.5]
    assert crit["인정율"]["관련"]["점검"] == 0.3
