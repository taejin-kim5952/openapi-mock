"""Small JSON file store — what the mock must not forget when it restarts.

The BEAST mock holds the specs that were deployed to each gateway. Keeping those in memory made
the screens lie: the mock restarts (or the container is redeployed) and every API that was
deployed silently becomes "not deployed yet", so the test screen answers 404 and the deploy
screen shows "신규 배포" for an API that was already there. The state is small and rarely
written, so one JSON file is enough — no database, no extra dependency.

The file lives outside the image (`STATE_FILE`, a mounted volume in Docker). Without the volume
the state is lost on redeploy, which is exactly the problem this module exists to solve.

Writes are atomic: a temporary file in the same directory, then `os.replace`. A half-written
file would be worse than no file, because it comes back as "nothing was ever deployed".

Any failure to read or write is logged and swallowed. A mock that cannot persist is still
useful; a mock that refuses to start is not.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)

_lock = threading.Lock()


def _path() -> Path:
    return Path(get_settings().state_file)


def load(section: str, default: Any) -> Any:
    """Read one section. Returns `default` when the file, the section, or the disk is unusable."""
    path = _path()
    if not path.exists():
        return default
    try:
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
        value = data.get(section, default)
        logger.info("[state] %s 읽음: %s", section, path)
        return value
    except (OSError, ValueError) as e:
        logger.warning("[state] %s 를 읽지 못해 빈 상태로 시작합니다: %s", path, e)
        return default


def save(section: str, value: Any) -> None:
    """Replace one section and write the whole file atomically."""
    path = _path()
    with _lock:
        data: dict[str, Any] = {}
        if path.exists():
            try:
                with path.open(encoding="utf-8") as f:
                    data = json.load(f)
            except (OSError, ValueError):
                # 깨진 파일은 덮어쓴다. 지금 들고 있는 값이 더 최신이다.
                data = {}
        data[section] = value
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".state-", suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                os.replace(tmp, path)
            except BaseException:
                Path(tmp).unlink(missing_ok=True)
                raise
        except OSError as e:
            logger.warning("[state] %s 에 쓰지 못했습니다 (이번 기동에서만 유지됩니다): %s", path, e)
