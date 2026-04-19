from __future__ import annotations

from polybot_v3.bot_state import is_paused, set_paused


def test_is_paused_default_false(tmp_path):
    path = tmp_path / "state.json"
    assert is_paused(path) is False


def test_set_and_read_paused(tmp_path):
    path = tmp_path / "state.json"
    set_paused(True, path)
    assert is_paused(path) is True
    set_paused(False, path)
    assert is_paused(path) is False


def test_is_paused_corrupt_file(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("not json")
    assert is_paused(path) is False
