from __future__ import annotations

import json
from pathlib import Path

from polybot_v3.config import BOT_STATE_FILE


def is_paused(path: Path = BOT_STATE_FILE) -> bool:
    if not Path(path).exists():
        return False
    try:
        return bool(json.loads(Path(path).read_text()).get("paused", False))
    except (json.JSONDecodeError, OSError):
        return False


def set_paused(paused: bool, path: Path = BOT_STATE_FILE) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps({"paused": paused}))
