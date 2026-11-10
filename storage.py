"""데이터 저장/불러오기.

app.py는 load_items()와 update_items()만 사용한다.
저장소를 Google Sheets 등으로 바꿀 때는 이 파일만 고치면 된다.

여러 브라우저 탭(세션)이 같은 파일을 쓰므로, 변경은 항상
"잠금 → 최신 데이터 읽기 → 변경 → 저장" 순서로 한다(update_items).
세션이 들고 있던 오래된 목록으로 파일 전체를 덮어쓰면 다른 탭의 변경이 사라진다.
"""

import json
import os
import tempfile
import threading
from collections.abc import Callable
from pathlib import Path

from models import normalize_items

DATA_FILE = Path(__file__).parent / "data" / "items.json"

# Streamlit은 한 프로세스 안에서 세션마다 스레드를 쓰므로 프로세스 단위 잠금으로 충분하다.
_lock = threading.RLock()


def load_items() -> list[dict]:
    """저장된 아이템 목록을 반환한다. 파일이 없거나 깨져 있으면 빈 리스트."""
    try:
        with DATA_FILE.open(encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError, OSError):
        return []
    return normalize_items(data)


def save_items(items: list[dict]) -> None:
    """아이템 목록을 저장한다. 임시 파일에 쓴 뒤 교체해서 저장 도중 파일이 깨지지 않게 한다."""
    with _lock:
        DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=DATA_FILE.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(items, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, DATA_FILE)
        except BaseException:
            Path(tmp_path).unlink(missing_ok=True)
            raise


def update_items(change: Callable[[list[dict]], list[dict]]) -> list[dict]:
    """최신 목록에 change를 적용해 저장하고, 저장된 목록을 반환한다."""
    with _lock:
        items = change(load_items())
        save_items(items)
        return items
