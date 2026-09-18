import sqlite3
from pathlib import Path

import pytest

from database.schema import initialize_database
from services.classroom_service import (
    clear_history,
    get_classroom,
    load_history,
    rename_classroom,
    save_history,
)

CLASSROOM_SOURCE = (
    Path(__file__).parents[1] / "components" / "chat_classroom.py"
).read_text(encoding="utf-8")
LEARNING_VIEW_SOURCE = (
    Path(__file__).parents[1] / "components" / "learning_view.py"
).read_text(encoding="utf-8")


@pytest.fixture
def connection():
    database = sqlite3.connect(":memory:")
    database.row_factory = sqlite3.Row
    initialize_database(database)
    yield database
    database.close()


def test_classroom_history_persists_and_isolated(connection):
    history = [{"role": "user", "content": "Teach joins."},
               {"role": "assistant", "content": "A join combines rows."}]
    save_history(connection, "user-a", "session-1", history)
    assert load_history(connection, "user-a", "session-1") == history
    assert load_history(connection, "user-b", "session-1") == []
    assert load_history(connection, "user-a", "session-2") == []


def test_classroom_history_reloads_and_renames(connection):
    save_history(connection, "user-a", "test-1", [{"role": "assistant", "content": "Ready."}])
    rename_classroom(connection, "user-a", "test-1", "SQL Test Classroom")
    row = get_classroom(connection, "user-a", "test-1")
    assert row["title"] == "SQL Test Classroom"
    assert row["history_json"] == '[{"role":"assistant","content":"Ready."}]'


def test_clear_history_does_not_affect_other_classrooms(connection):
    save_history(connection, "user-a", "doubt", [{"role": "assistant", "content": "Answer"}])
    save_history(connection, "user-a", "other", [{"role": "assistant", "content": "Keep"}])
    clear_history(connection, "user-a", "doubt")
    assert load_history(connection, "user-a", "doubt") == []
    assert load_history(connection, "user-a", "other")[0]["content"] == "Keep"


def test_classroom_rejects_invalid_history(connection):
    with pytest.raises(ValueError):
        save_history(connection, "user-a", "x", [{"role": "system", "content": "no"}])


def test_test_and_interview_classrooms_are_isolated(connection):
    save_history(connection, "user-a", "test_1", [{"role": "assistant", "content": "Test"}])
    save_history(
        connection, "user-a", "interview_hr_session-1",
        [{"role": "assistant", "content": "HR"}],
    )
    save_history(
        connection, "user-a", "interview_technical_session-1",
        [{"role": "assistant", "content": "Technical"}],
    )
    assert load_history(connection, "user-a", "test_1")[0]["content"] == "Test"
    assert load_history(connection, "user-a", "interview_hr_session-1")[0]["content"] == "HR"
    assert load_history(connection, "user-a", "interview_technical_session-1")[0]["content"] == "Technical"


def test_latest_control_targets_history_scroll_container_without_page_scroll():
    assert "element.scrollHeight > element.clientHeight" in CLASSROOM_SOURCE
    assert "container.scrollTop = container.scrollHeight" in CLASSROOM_SOURCE
    assert "window.scrollY" not in CLASSROOM_SOURCE
    assert "button.dataset.latestWired" in CLASSROOM_SOURCE


def test_classroom_has_one_scrollable_history_region_and_compact_tail():
    assert 'key=f"{classroom_key}_history"' in CLASSROOM_SOURCE
    assert "height=600" in CLASSROOM_SOURCE
    assert CLASSROOM_SOURCE.count("overflow-y: auto") == 0
    assert "padding: 1.25rem clamp(1rem, 5vw, 5rem)" in CLASSROOM_SOURCE
    assert "min-height: 100%" not in CLASSROOM_SOURCE


def test_composer_is_a_real_flex_sibling_not_an_overlay():
    composer_styles = CLASSROOM_SOURCE.split(
        ".st-key-{classroom_key}_composer {{", 1
    )[1].split("        .st-key-{classroom_key}_composer [", 1)[0]
    assert "position: relative" in composer_styles
    assert "flex: 0 0 auto" in composer_styles
    assert "position: absolute" not in composer_styles
    assert "position: fixed" not in composer_styles
    assert "margin: .75rem 1rem 1rem" in composer_styles


def test_classroom_uses_explicit_header_history_composer_flex_regions():
    assert "flex-direction: column" in CLASSROOM_SOURCE
    assert "100dvh" not in CLASSROOM_SOURCE
    assert "position: sticky" not in CLASSROOM_SOURCE
    assert "overflow: hidden" not in CLASSROOM_SOURCE
    assert "flex: 0 0 auto" in CLASSROOM_SOURCE
    assert "position: absolute" not in CLASSROOM_SOURCE.split(
        ".st-key-{classroom_key}_composer {{", 1
    )[1].split("        .st-key-{classroom_key}_composer [", 1)[0]


def test_prompt_capture_precedes_generation_and_loading_is_not_persisted():
    capture_start = CLASSROOM_SOURCE.index("def _capture_prompt")
    generation_start = CLASSROOM_SOURCE.index("gateway.generate_advanced")
    assert capture_start < generation_start
    assert 'st.session_state[history_key].append({"role": "user"' in CLASSROOM_SOURCE
    assert 'st.session_state[pending_prompt_key] = prompt' in CLASSROOM_SOURCE
    assert 'st.session_state[history_key].append(\n                    {"role": "assistant"' in CLASSROOM_SOURCE
    assert 'st.caption("AI is thinking...")' in CLASSROOM_SOURCE
    assert "save_history(" in CLASSROOM_SOURCE
    assert "pending_prompt_key" in CLASSROOM_SOURCE


def test_submit_callback_clears_composer_by_rotating_generation_key():
    assert "on_click=_capture_prompt" in CLASSROOM_SOURCE
    assert "st.session_state[composer_generation_key] += 1" in CLASSROOM_SOURCE
    assert "st.columns([9, 1]" in CLASSROOM_SOURCE
    assert "st.markdown(message[\"content\"])" in CLASSROOM_SOURCE


def test_auto_scroll_preserves_user_position_and_targets_native_history():
    assert "scrollIntent[historySelector] = !awayFromLatest" in CLASSROOM_SOURCE
    assert "container.scrollTop = container.scrollHeight" in CLASSROOM_SOURCE
    assert "window.scrollTo" not in CLASSROOM_SOURCE
    assert "document.scrollTop" not in CLASSROOM_SOURCE


def test_generation_has_a_visible_state_machine_boundary():
    assert 'st.session_state[pending_phase_key] = "queued"' in CLASSROOM_SOURCE
    assert '== "queued"' in CLASSROOM_SOURCE
    assert 'st.session_state[pending_phase_key] = "generating"' in CLASSROOM_SOURCE
    assert '== "generating"' in CLASSROOM_SOURCE
    assert 'key=f"{classroom_key}_generation_tick"' in CLASSROOM_SOURCE


def test_latest_wiring_is_idempotent_and_finite():
    assert "window.__classroomScrollWiring" in CLASSROOM_SOURCE
    assert "container.addEventListener('scroll'" in CLASSROOM_SOURCE
    assert "button.dataset.latestWired" in CLASSROOM_SOURCE
    assert "new MutationObserver" in CLASSROOM_SOURCE
    assert "frame < 18" in CLASSROOM_SOURCE
    assert "attempts++ >= 24" in CLASSROOM_SOURCE
    assert CLASSROOM_SOURCE.count("addEventListener('scroll'") == 1
    assert CLASSROOM_SOURCE.count("addEventListener('click'") == 1
    assert "new MutationObserver" in CLASSROOM_SOURCE
    assert "visibility: hidden" in CLASSROOM_SOURCE


def test_latest_button_has_stable_scoped_floating_markup_and_center_position():
    assert '"↓ Latest"' in CLASSROOM_SOURCE
    assert 'latest.classList.add(\'shyam-academy-latest-control\')' in CLASSROOM_SOURCE
    assert 'latest.dataset.shyamAcademyLatest = \'true\'' in CLASSROOM_SOURCE
    assert ".shyam-academy-latest-control" in CLASSROOM_SOURCE
    assert "position: absolute" in CLASSROOM_SOURCE
    assert "height: 0" in CLASSROOM_SOURCE
    assert "min-height: 0" in CLASSROOM_SOURCE
    assert "z-index: 20" in CLASSROOM_SOURCE
    assert "historyRect.left - classroomRect.left" in CLASSROOM_SOURCE
    assert "historyRect.width / 2" in CLASSROOM_SOURCE
    assert "buttonWidth / 2" in CLASSROOM_SOURCE
    assert "latest.style.left" in CLASSROOM_SOURCE
    assert "left: 50%" not in CLASSROOM_SOURCE
    assert "window.innerWidth" not in CLASSROOM_SOURCE
    assert "document.body" not in CLASSROOM_SOURCE
    assert "historyRect.bottom - classroomRect.top" in CLASSROOM_SOURCE
    assert "latest.offsetHeight" in CLASSROOM_SOURCE
    assert "const safeGap = 28" in CLASSROOM_SOURCE
    assert "historyRect.height * .62" not in CLASSROOM_SOURCE
    assert "top: 52%" not in CLASSROOM_SOURCE


def test_latest_wrapper_does_not_reserve_document_flow_space():
    latest_styles = CLASSROOM_SOURCE.split(
        ".st-key-{classroom_key}_latest {{", 1
    )[1].split("        .shyam-academy-latest-control {{", 1)[0]
    assert "position: absolute" in latest_styles
    assert "height: 0" in latest_styles
    assert "min-height: 0" in latest_styles
    assert "margin: 0" in latest_styles
    assert "padding: 0" in latest_styles
    assert "100vh" not in latest_styles
    assert "100dvh" not in latest_styles


def test_composer_is_final_in_root_flow_and_wiring_is_outside_root():
    latest_pos = CLASSROOM_SOURCE.index(
        'with st.container(key=f"{classroom_key}_latest"):'
    )
    composer_pos = CLASSROOM_SOURCE.index(
        'with st.container(key=f"{classroom_key}_composer"):'
    )
    wire_pos = CLASSROOM_SOURCE.index(
        '    _wire_latest_control('
    )
    root_end = CLASSROOM_SOURCE.index(
        '    if st.session_state.get(pending_phase_key) == "queued":',
        composer_pos,
    )
    assert latest_pos < composer_pos < root_end < wire_pos
    assert 'key=f"{classroom_key}_generation_tick"' in CLASSROOM_SOURCE
    assert CLASSROOM_SOURCE.index(
        'key=f"{classroom_key}_generation_tick"'
    ) < latest_pos
    assert "flex: 0 0 auto" in CLASSROOM_SOURCE
    assert "min-height: 100%" not in CLASSROOM_SOURCE
    assert "100vh" not in CLASSROOM_SOURCE
    assert "100dvh" not in CLASSROOM_SOURCE


def test_latest_visibility_and_click_remain_scoped_to_native_history():
    assert "current.scrollHeight - current.clientHeight" in CLASSROOM_SOURCE
    assert "current.scrollTop > 12" in CLASSROOM_SOURCE
    assert "document.querySelector(historySelector)" in CLASSROOM_SOURCE
    assert "scrollHistoryToLatest(" in CLASSROOM_SOURCE
    assert "event.preventDefault()" in CLASSROOM_SOURCE
    assert "st.rerun()" not in CLASSROOM_SOURCE[
        CLASSROOM_SOURCE.index("def _wire_latest_control"):
        CLASSROOM_SOURCE.index("def _start_pending_generation")
    ]


def test_new_content_forces_latest_scroll_even_after_manual_upward_scroll():
    assert "if ({str(jump_to_latest).lower()})" in CLASSROOM_SOURCE
    assert "scrollIntent[historySelector] = true" in CLASSROOM_SOURCE
    assert "scrollIntent[historySelector] !== false" not in CLASSROOM_SOURCE
    assert "element.scrollHeight > element.clientHeight" in CLASSROOM_SOURCE
    assert "current.scrollHeight - current.clientHeight" in CLASSROOM_SOURCE
    assert "cancelAnimationFrame" in CLASSROOM_SOURCE
    assert "disconnect()" in CLASSROOM_SOURCE


def test_obsolete_session_details_navigation_is_not_rendered():
    assert "Back to session details" not in LEARNING_VIEW_SOURCE
    assert "session_details.py" not in LEARNING_VIEW_SOURCE
    assert "render_shared_classroom(" in LEARNING_VIEW_SOURCE
    assert "latest_" in CLASSROOM_SOURCE
    assert "scrollHistoryToLatest" in CLASSROOM_SOURCE
    assert "shared_composer_" in CLASSROOM_SOURCE
    assert "Save Notes" in CLASSROOM_SOURCE
    assert "Reset" in CLASSROOM_SOURCE
    assert "edit_classroom_title_" in CLASSROOM_SOURCE
