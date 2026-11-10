"""쇼핑리스트 Streamlit 앱 (진입점).

구성
- 순수 로직 함수: 리스트를 받아 새 리스트를 반환한다. Streamlit 없이 테스트 가능 (tests/test_logic.py).
- 콜백 함수: 위젯 이벤트에서 상태를 바꾸고 저장한다. 렌더링 도중에는 리스트를 수정하지 않는다.
- 렌더 함수: 화면만 그린다.
"""

import re
import time

import streamlit as st

from icons import get_icon
from models import MAX_QUANTITY, create_item, now_iso, validate_item
from storage import load_items, update_items


# ---------------------------------------------------------------------------
# 순수 로직
# ---------------------------------------------------------------------------

def add_item(items: list[dict], item: dict) -> list[dict]:
    return [*items, item]


def update_item(items: list[dict], item_id: str, name: str, quantity: int, memo: str) -> list[dict]:
    return [
        {
            **item,
            "name": name.strip(),
            "quantity": int(quantity),
            "memo": memo.strip(),
            "updated_at": now_iso(),
        }
        if item["id"] == item_id
        else item
        for item in items
    ]


def delete_item(items: list[dict], item_id: str) -> list[dict]:
    return [item for item in items if item["id"] != item_id]


def set_checked(items: list[dict], item_id: str, checked: bool) -> list[dict]:
    return [
        {**item, "checked": bool(checked), "updated_at": now_iso()} if item["id"] == item_id else item
        for item in items
    ]


def clear_checked(items: list[dict]) -> list[dict]:
    return [item for item in items if not item["checked"]]


def sort_items(items: list[dict]) -> list[dict]:
    """미완료 먼저, 완료는 아래. 같은 그룹 안에서는 created_at 순 (같으면 원래 순서 유지)."""
    return sorted(items, key=lambda item: (item["checked"], item["created_at"]))


def progress(items: list[dict]) -> tuple[int, int, float]:
    """(전체 개수, 완료 개수, 완료 비율 0~1)."""
    total = len(items)
    done = sum(1 for item in items if item["checked"])
    return total, done, (done / total if total else 0.0)


_MD_SPECIAL = re.compile(r"([\\`*_{}\[\]()#+\-.!|~<>$:])")


def escape_md(text: str) -> str:
    """사용자 입력이 마크다운으로 해석되지 않도록 특수문자를 이스케이프한다."""
    return _MD_SPECIAL.sub(r"\\\1", text)


def break_autolinks(text: str) -> str:
    """URL·이메일이 자동으로 링크가 되지 않게 보이지 않는 문자(U+200B)를 끼워 넣는다.

    마크다운 이스케이프만으로는 Streamlit의 자동 링크(http://, www., a@b.c)를 막지 못한다.
    """
    text = text.replace("://", ":\u200b//")
    text = re.sub(r"(?i)(www)\.", "\\1\u200b.", text)
    return text.replace("@", "\u200b@")


def safe_md(text: str) -> str:
    """사용자 입력을 st.markdown/st.toast 등에 넣을 때 쓴다. 서식·링크로 해석되지 않는다."""
    return escape_md(break_autolinks(text))


def find_item(items: list[dict], item_id: str) -> dict | None:
    return next((item for item in items if item["id"] == item_id), None)


# 수량 입력칸 설정. 정수(int) 위젯은 1.5를 말없이 1로 바꾸므로, 실수 위젯으로 받아
# validate_item에서 "정수로 입력" 안내를 보여준다. %g 형식이라 1.0은 "1"로 보인다.
QUANTITY_INPUT = {"min_value": 1.0, "max_value": float(MAX_QUANTITY), "step": 1.0, "format": "%g"}

DUPLICATE_SUBMIT_SECONDS = 1.0


def is_repeat_submit(last: tuple | None, signature: tuple, now: float) -> bool:
    """같은 입력이 짧은 시간 안에 다시 제출됐는지 (추가 버튼 더블클릭 방지)."""
    return last is not None and last[0] == signature and now - last[1] < DUPLICATE_SUBMIT_SECONDS


# ---------------------------------------------------------------------------
# 상태 / 콜백
# ---------------------------------------------------------------------------

def init_state() -> None:
    """세션 상태를 한 번만 초기화한다."""
    defaults = {
        "items": [],
        "editing_id": None,
        "add_error": None,
        "edit_error": None,
        "confirm_clear": False,
        "toast": None,
        "last_add": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def refresh_items() -> None:
    """매 실행마다 저장소의 최신 목록을 읽는다. 다른 탭에서 바뀐 내용이 반영된다."""
    ss = st.session_state
    ss["items"] = load_items()
    if ss["editing_id"] and find_item(ss["items"], ss["editing_id"]) is None:
        ss["editing_id"] = None
        ss["edit_error"] = None
        ss["toast"] = ss["toast"] or "수정 중이던 항목이 다른 곳에서 삭제됐어요."


def mutate(change) -> list[dict]:
    """최신 목록에 change를 적용해 저장한다. 콜백은 반드시 이 함수로만 데이터를 바꾼다.

    세션이 들고 있는 목록(st.session_state["items"])으로 저장하면
    다른 탭의 변경을 덮어쓰므로 사용하지 않는다.
    """
    items = update_items(change)
    st.session_state["items"] = items
    return items


def on_add() -> None:
    ss = st.session_state
    name, quantity, memo = ss["new_name"], ss["new_quantity"], ss["new_memo"] or ""
    error = validate_item(name, quantity)
    if error:
        ss["add_error"] = error
        return
    signature = (name.strip(), int(quantity), memo.strip())
    now = time.monotonic()
    if not is_repeat_submit(ss["last_add"], signature, now):
        mutate(lambda items: add_item(items, create_item(name, quantity, memo)))
    ss["last_add"] = (signature, now)
    ss["add_error"] = None
    # 입력 필드 초기화 (검증 실패 시에는 입력값을 남겨둔다)
    ss["new_name"], ss["new_quantity"], ss["new_memo"] = "", 1.0, ""


def on_start_edit(item_id: str) -> None:
    ss = st.session_state
    item = find_item(load_items(), item_id)
    if item is None:
        ss["toast"] = "이미 삭제된 항목이에요."
        return
    ss["editing_id"] = item_id
    ss["edit_error"] = None
    ss[f"edit_name_{item_id}"] = item["name"]
    ss[f"edit_quantity_{item_id}"] = float(item["quantity"])
    ss[f"edit_memo_{item_id}"] = item["memo"]


def on_save_edit(item_id: str) -> None:
    ss = st.session_state
    name = ss[f"edit_name_{item_id}"]
    quantity = ss[f"edit_quantity_{item_id}"]
    memo = ss[f"edit_memo_{item_id}"] or ""
    error = validate_item(name, quantity)
    if error:
        ss["edit_error"] = error
        return
    found = {}

    def change(items):
        found["ok"] = find_item(items, item_id) is not None
        return update_item(items, item_id, name, quantity, memo)

    mutate(change)
    ss["editing_id"] = None
    ss["edit_error"] = None
    if found["ok"]:
        ss["toast"] = f"'{safe_md(name.strip())}' 수정됨"
    else:
        ss["toast"] = "다른 곳에서 삭제된 항목이라 저장하지 않았어요."


def on_cancel_edit() -> None:
    st.session_state["editing_id"] = None
    st.session_state["edit_error"] = None


def on_delete(item_id: str) -> None:
    ss = st.session_state
    deleted = {}

    def change(items):
        deleted["item"] = find_item(items, item_id)
        return delete_item(items, item_id)

    mutate(change)
    if ss["editing_id"] == item_id:
        ss["editing_id"] = None
        ss["edit_error"] = None
    if deleted["item"]:
        ss["toast"] = f"'{safe_md(deleted['item']['name'])}' 삭제됨"


def on_toggle(item_id: str) -> None:
    checked = st.session_state[f"check_{item_id}"]
    mutate(lambda items: set_checked(items, item_id, checked))


def on_request_clear() -> None:
    st.session_state["confirm_clear"] = True


def on_confirm_clear() -> None:
    ss = st.session_state
    removed = {}

    def change(items):
        kept = clear_checked(items)
        removed["count"] = len(items) - len(kept)
        return kept

    items = mutate(change)
    if ss["editing_id"] and find_item(items, ss["editing_id"]) is None:
        ss["editing_id"] = None
    ss["confirm_clear"] = False
    ss["toast"] = f"완료 항목 {removed['count']}개 삭제됨"


def on_cancel_clear() -> None:
    st.session_state["confirm_clear"] = False


# ---------------------------------------------------------------------------
# 렌더링
# ---------------------------------------------------------------------------

# 최소한의 CSS. Streamlit 내부 클래스 대신, 컨테이너 key로 생기는 공식 클래스(st-key-<key>)만 사용한다.
CUSTOM_CSS = """
<style>
/* 띄어쓰기 없는 긴 이름이 카드 밖으로 넘치지 않게 줄바꿈 */
[class*="st-key-item_"] p { overflow-wrap: anywhere; }
/* 이름 영역이 좁은 화면에서 줄어들 수 있게 (flex 기본 min-width:auto 때문에 넘치는 것 방지) */
[class*="st-key-name_"] { min-width: 0; }
/* 수정/삭제 버튼: 글자는 화면에서 숨기고(아이콘만 표시) 스크린 리더에는 "수정"/"삭제"로 읽히게 */
[class*="st-key-editbtn_"] button p,
[class*="st-key-deletebtn_"] button p {
    position: absolute !important;
    width: 1px; height: 1px; margin: -1px; padding: 0;
    overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0;
}
/* 편집 중인 행 강조 */
.st-key-editing_row {
    background-color: #EAF5EC;
    border-color: #2E7D32 !important;
}
</style>
"""


def render_header() -> None:
    st.title("🛒 쇼핑리스트")
    total, done, ratio = progress(st.session_state["items"])
    st.markdown(f"전체 **{total}**개 · 완료 **{done}**개")
    st.progress(ratio, text=f"{round(ratio * 100)}%")
    if total and done == total:
        st.success("장보기 완료! 🎉")


def render_add_form() -> None:
    with st.form("add_form", clear_on_submit=False, enter_to_submit=True):
        # 모바일(375px)에서도 한 줄에 들어가도록 2줄 구성: [이름 | 추가] / [수량 | 메모]
        # 수량 입력칸은 +/- 버튼 때문에 최소 너비가 커서 이름·버튼과 같은 줄에 두면 잘린다.
        row1 = st.columns([4, 1], vertical_alignment="bottom", wrap=False)
        row1[0].text_input("아이템 이름", key="new_name", max_chars=50, placeholder="예: 우유")
        row1[1].form_submit_button("추가", on_click=on_add, type="primary", width="stretch")
        row2 = st.columns([1, 2], vertical_alignment="bottom", wrap=False)
        row2[0].number_input("수량", key="new_quantity", value=1.0, **QUANTITY_INPUT)
        row2[1].text_input("메모", key="new_memo", placeholder="선택 · 예: 저지방")
    if st.session_state["add_error"]:
        st.warning(st.session_state["add_error"], icon="⚠️")


def render_item_row(item: dict) -> None:
    item_id = item["id"]
    if st.session_state["editing_id"] == item_id:
        render_edit_row(item)
        return

    checked = item["checked"]
    name = safe_md(item["name"])
    # 다른 탭에서 체크 상태가 바뀌었을 수 있으므로 위젯 상태를 저장된 값에 맞춘다.
    # (value= 인자 대신 위젯 생성 전에 session_state를 지정해야 경고 없이 반영된다)
    st.session_state[f"check_{item_id}"] = checked
    with st.container(border=True, key=f"item_{item_id}"):
        with st.container(horizontal=True, vertical_alignment="center", gap="small", wrap=False):
            st.checkbox(
                name,
                key=f"check_{item_id}",
                on_change=on_toggle,
                args=(item_id,),
                label_visibility="collapsed",
            )
            with st.container(gap=None, key=f"name_{item_id}"):
                icon = get_icon(item["name"])
                st.markdown(f"{icon} :gray[~~{name}~~]" if checked else f"{icon} **{name}**")
                if item["memo"]:
                    st.caption(safe_md(item["memo"]))
            st.badge(f"x{item['quantity']}", color="gray" if checked else "green")
            st.button("수정", icon="✏️", key=f"editbtn_{item_id}", on_click=on_start_edit,
                      args=(item_id,), help="수정", type="tertiary")
            st.button("삭제", icon="🗑️", key=f"deletebtn_{item_id}", on_click=on_delete,
                      args=(item_id,), help="삭제", type="tertiary")


def render_edit_row(item: dict) -> None:
    item_id = item["id"]
    with st.container(border=True, key="editing_row"):
        st.caption("✏️ 아이템 수정 중")
        # form으로 감싸서 입력 칸에서 Enter를 누르면 저장되게 한다. (Enter는 첫 번째 제출 버튼 = 저장)
        with st.form(f"edit_form_{item_id}", border=False, enter_to_submit=True):
            cols = st.columns([5, 2.2])
            cols[0].text_input("아이템 이름", key=f"edit_name_{item_id}", max_chars=50)
            cols[1].number_input("수량", key=f"edit_quantity_{item_id}", **QUANTITY_INPUT)
            st.text_input("메모", key=f"edit_memo_{item_id}", placeholder="메모 (선택)")
            if st.session_state["edit_error"]:
                st.warning(st.session_state["edit_error"], icon="⚠️")
            with st.container(horizontal=True, gap="small"):
                st.form_submit_button("저장", key=f"save_{item_id}", on_click=on_save_edit,
                                      args=(item_id,), type="primary")
                st.form_submit_button("취소", key=f"cancel_{item_id}", on_click=on_cancel_edit)


def render_empty_state() -> None:
    with st.container(border=True):
        st.markdown("# 🧺", text_alignment="center", anchors=False)
        st.markdown("쇼핑리스트가 비어 있어요. 아이템을 추가해 보세요!", text_alignment="center")


def render_item_list() -> None:
    items = st.session_state["items"]
    if not items:
        render_empty_state()
        return

    sorted_items = sort_items(items)
    todo = [item for item in sorted_items if not item["checked"]]
    done = [item for item in sorted_items if item["checked"]]

    st.subheader(f"남은 항목 · {len(todo)}", anchor=False)
    if todo:
        for item in todo:
            render_item_row(item)
    else:
        st.caption("남은 항목이 없어요.")

    if done:
        with st.expander(f"완료한 항목 · {len(done)}", expanded=True, key="done_section"):
            for item in done:
                render_item_row(item)


def render_footer() -> None:
    items = st.session_state["items"]
    if not items:
        return
    checked_count = sum(1 for item in items if item["checked"])
    if checked_count == 0:
        st.session_state["confirm_clear"] = False

    if st.session_state["confirm_clear"]:
        st.warning(f"정말 완료 항목 {checked_count}개를 삭제할까요?", icon="🗑️")
        with st.container(horizontal=True, gap="small"):
            st.button("확인", key="confirm_clear_yes", on_click=on_confirm_clear, type="primary")
            st.button("취소", key="confirm_clear_no", on_click=on_cancel_clear)
    else:
        with st.container(horizontal=True, horizontal_alignment="center"):
            st.button(
                "완료 항목 모두 삭제",
                key="clear_checked",
                on_click=on_request_clear,
                disabled=checked_count == 0,
                icon=":material/delete_sweep:",
            )


def show_pending_toast() -> None:
    if st.session_state["toast"]:
        st.toast(st.session_state["toast"])
        st.session_state["toast"] = None


def main() -> None:
    st.set_page_config(page_title="쇼핑리스트", page_icon="🛒", layout="centered")
    st.html(CUSTOM_CSS)
    init_state()
    refresh_items()
    show_pending_toast()
    render_header()
    render_add_form()
    render_item_list()
    render_footer()


# streamlit run 시에만 화면을 그린다. 테스트에서 import할 때는 실행되지 않는다.
if __name__ == "__main__":
    main()
