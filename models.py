"""쇼핑리스트 아이템 생성/검증/정규화."""

import uuid
from datetime import datetime

MAX_NAME_LENGTH = 50
MAX_QUANTITY = 999


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def create_item(name: str, quantity: int = 1, memo: str = "") -> dict:
    """PRD 5장 데이터 모델에 맞는 아이템 dict를 만든다. 검증은 하지 않는다."""
    timestamp = now_iso()
    return {
        "id": str(uuid.uuid4()),
        "name": name.strip(),
        "quantity": int(quantity),
        "memo": memo.strip(),
        "checked": False,
        "created_at": timestamp,
        "updated_at": timestamp,
    }


def validate_item(name: str, quantity) -> str | None:
    """입력값이 올바르면 None, 아니면 사용자에게 보여줄 에러 메시지를 반환한다."""
    if name is None or not name.strip():
        return "아이템 이름을 입력해 주세요."
    if len(name.strip()) > MAX_NAME_LENGTH:
        return f"아이템 이름은 {MAX_NAME_LENGTH}자 이하로 입력해 주세요."
    if isinstance(quantity, bool) or not isinstance(quantity, (int, float)):
        return "수량은 숫자로 입력해 주세요."
    if quantity != int(quantity) or not 1 <= quantity <= MAX_QUANTITY:
        return f"수량은 1~{MAX_QUANTITY} 사이의 정수로 입력해 주세요."
    return None


def _to_quantity(value) -> int:
    if isinstance(value, bool):
        return 1
    if isinstance(value, str):
        value = value.strip()
        if not value.isdigit():
            return 1
        value = int(value)
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if not isinstance(value, int):
        return 1
    return min(max(value, 1), MAX_QUANTITY)


def normalize_item(raw) -> dict | None:
    """저장소에서 읽은 값을 데이터 모델 형태로 맞춘다. 쓸 수 없는 값이면 None.

    직접 편집했거나 다른 저장소에서 옮겨온 데이터 때문에 앱이 멈추지 않게 한다.
    - 이름이 없거나 문자열이 아니면 버린다.
    - 나머지 필드는 타입이 틀리면 기본값으로 바꾼다.
    """
    if not isinstance(raw, dict):
        return None
    name = raw.get("name")
    if not isinstance(name, str) or not name.strip():
        return None

    item_id = raw.get("id")
    memo = raw.get("memo")
    created_at = raw.get("created_at")
    updated_at = raw.get("updated_at")
    created_at = created_at if isinstance(created_at, str) else ""
    return {
        "id": item_id if isinstance(item_id, str) and item_id else str(uuid.uuid4()),
        "name": name.strip(),
        "quantity": _to_quantity(raw.get("quantity")),
        "memo": memo.strip() if isinstance(memo, str) else "",
        "checked": raw.get("checked") is True,
        "created_at": created_at,
        "updated_at": updated_at if isinstance(updated_at, str) else created_at,
    }


def normalize_items(data) -> list[dict]:
    """목록 전체를 정규화한다. id가 겹치면(위젯 key 충돌 방지) 새 id를 준다."""
    if not isinstance(data, list):
        return []
    items, seen = [], set()
    for raw in data:
        item = normalize_item(raw)
        if item is None:
            continue
        if item["id"] in seen:
            item["id"] = str(uuid.uuid4())
        seen.add(item["id"])
        items.append(item)
    return items
