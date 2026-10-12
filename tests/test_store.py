from pathlib import Path

from pqweb import store


def test_get_eval_allows_parentheses_but_blocks_traversal(tmp_path):
    (tmp_path / "20261007-103639_기술인B(Claude_판독)").mkdir()
    (tmp_path / "x").mkdir()
    assert store.get_eval("20261007-103639_기술인B(Claude_판독)", tmp_path) is not None
    for bad in ("..", "../x", "x/..", "..\\x", "C:x", "", "없음"):
        assert store.get_eval(bad, tmp_path / "x") is None or bad == ""


def test_new_eval_with_parentheses_name_is_reachable(tmp_path):
    d = store.new_eval(b"%PDF", {"성명": "홍길동(대리)"}, base=tmp_path)
    assert store.get_eval(d.name, tmp_path) == d


def test_write_json_retries_when_target_locked(tmp_path, monkeypatch):
    """Windows에서 다른 쪽이 파일을 읽는 중이면 replace가 PermissionError를 낸다."""
    target = tmp_path / "status.json"
    store.write_json(target, {"단계": "대기"})
    real = Path.replace
    fails = {"n": 2}

    def flaky(self, dst):
        if fails["n"] > 0:
            fails["n"] -= 1
            raise PermissionError(5, "액세스가 거부되었습니다")
        return real(self, dst)

    monkeypatch.setattr(Path, "replace", flaky)
    store.write_json(target, {"단계": "판독"})
    assert store.read_json(target)["단계"] == "판독"


def test_write_json_falls_back_to_direct_write(tmp_path, monkeypatch):
    target = tmp_path / "status.json"

    def always(self, dst):
        raise PermissionError(5, "액세스가 거부되었습니다")

    monkeypatch.setattr(Path, "replace", always)
    monkeypatch.setattr(store, "_RETRY_SLEEP", 0)
    store.write_json(target, {"단계": "완료"})
    assert store.read_json(target)["단계"] == "완료"
    assert not (tmp_path / "status.json.tmp").exists()
