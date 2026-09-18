import streamlit as st
from html import escape

from ai.gateway import AIProviderError
from services.classroom_service import (
    clear_history,
    get_classroom,
    load_history,
    rename_classroom,
    save_history,
)


def render_classroom_styles(classroom_key: str) -> None:
    dark = st.session_state.get("academy_theme", "light") == "dark"
    header_surface = "#1f2937" if dark else "rgba(255,255,255,.97)"
    composer_surface = "#1f2937" if dark else "rgba(255,255,255,.98)"
    text = "#e5edf5" if dark else "#1d2733"
    user_text = "#d9ecff" if dark else "#12304f"
    st.markdown(
        f"""
        <style>
        .st-key-{classroom_key} {{
            width: 100%;
            max-width: none;
            margin: 0;
            display: flex;
            flex-direction: column;
            position: relative;
            border: 0;
            border-radius: 0;
            background: transparent;
            color: {text};
            font-size: 1.12rem;
            font-weight: 500;
            line-height: 1.5;
        }}
        .st-key-{classroom_key}_header {{
            flex: 0 0 auto;
            z-index: 3;
            background: {header_surface};
            border-bottom: 1px solid {"rgba(203,213,225,.22)" if dark else "rgba(120,130,150,.18)"};
            padding: .9rem 1.1rem .65rem;
        }}
        .st-key-{classroom_key}_header > div[data-testid="stVerticalBlock"] {{
            min-height: 0;
        }}
        .st-key-{classroom_key} [data-testid="stVerticalBlock"] {{
            padding-left: 1.1rem;
            padding-right: 1.1rem;
        }}
        .st-key-edit_classroom_title-{classroom_key} button {{
            border: 0;
            background: transparent;
            padding: 0;
            font-size: 1.7rem;
            font-weight: 750;
            color: {text};
        }}
        .st-key-{classroom_key}_history {{
            padding: 1.25rem clamp(1rem, 5vw, 5rem);
            background: transparent;
        }}
        .st-key-{classroom_key}_history [data-testid="stVerticalBlock"] {{
            gap: .25rem;
        }}
        .st-key-{classroom_key}_history [class*="st-key-"] {{
            width: fit-content;
            max-width: min(72%, 52rem);
            margin: .7rem 0;
            padding: .85rem 1rem;
            border-radius: .9rem;
            line-height: 1.65;
            font-size: 1.12rem;
            font-weight: 500;
        }}
        .st-key-{classroom_key}_history [class*="classroom-ai"] {{
            background: transparent;
            color: {text};
            width: 100%;
            max-width: 100%;
            box-sizing: border-box;
            margin-right: auto;
            border-radius: 0;
            padding-left: .25rem;
            padding-right: .25rem;
        }}
        .st-key-{classroom_key}_history [class*="classroom-user"] {{
            background: {"#24496d" if dark else "#e5f1ff"};
            color: {user_text};
            width: fit-content;
            max-width: min(75%, 52rem);
            margin-left: auto;
        }}
        .st-key-{classroom_key}_history [class*="classroom-ai"]::before {{
            content: "✦";
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 1.65rem;
            height: 1.65rem;
            margin-right: .55rem;
            border-radius: .55rem;
            background: #16b99a;
            color: #ffffff;
            font-weight: 800;
        }}
        .st-key-{classroom_key}_history [class*="classroom-user"]::before {{
            content: "You";
            display: inline-flex;
            align-items: center;
            justify-content: center;
            min-width: 1.65rem;
            height: 1.65rem;
            margin-right: .55rem;
            border-radius: 999px;
            background: {"#2f6fa3" if dark else "#b9d9f5"};
            color: {"#ffffff" if dark else "#12304f"};
            font-size: .74rem;
            font-weight: 800;
        }}
        .st-key-{classroom_key}_history [class*="classroom-role"] {{
            font-weight: 700;
            font-size: 1rem;
            margin-bottom: .2rem;
        }}
        .st-key-{classroom_key}_composer {{
            position: relative;
            flex: 0 0 auto;
            margin: .75rem 1rem 1rem;
            z-index: 3;
            background: {composer_surface};
            border: 1px solid {"rgba(203,213,225,.28)" if dark else "rgba(120,130,150,.25)"};
            border-radius: 1.15rem;
            box-shadow: 0 -8px 24px rgba(18, 31, 49, .08);
            padding: .75rem 1rem .9rem;
        }}
        .st-key-{classroom_key}_composer [data-testid="stHorizontalBlock"] {{
            align-items: flex-end;
            gap: .65rem;
        }}
        .st-key-{classroom_key}_composer [data-testid="stHorizontalBlock"] > div {{
            min-width: 0;
        }}
        .st-key-{classroom_key}_composer::before {{
            content: "+";
            position: absolute;
            left: 1.35rem;
            bottom: 1.35rem;
            z-index: 4;
            width: 1.85rem;
            height: 1.85rem;
            border-radius: 999px;
            background: {"#273449" if dark else "#edf2f7"};
            color: {text};
            text-align: center;
            line-height: 1.75rem;
            font-size: 1.35rem;
        }}
        .st-key-{classroom_key}_composer [data-testid="stTextInput"] input {{
            min-height: 3.25rem;
            border-radius: 999px;
            padding-left: 3.35rem;
            padding-right: 4.75rem;
            background: {"#172235" if dark else "#ffffff"};
        }}
        .st-key-{classroom_key}_composer textarea {{
            font-size: 1.12rem !important;
            font-weight: 500 !important;
        }}
        .st-key-{classroom_key}_send button {{
            min-height: 3.25rem;
            width: 100%;
            min-width: 2.75rem;
            max-width: 3.25rem;
            border-radius: 999px;
            font-size: 1.45rem;
            font-weight: 750;
            background: #16b99a;
            border-color: #16b99a;
            color: #ffffff;
        }}
        .st-key-{classroom_key}_composer [class*="_send"] {{
            width: 100%;
            display: flex;
            justify-content: flex-end;
        }}
        .st-key-{classroom_key}_latest {{
            position: absolute;
            left: 0;
            top: 0;
            bottom: auto;
            z-index: 2;
            pointer-events: none;
            transform: none;
            width: 0;
            height: 0;
            min-height: 0;
            margin: 0;
            padding: 0;
            visibility: hidden;
            opacity: 0;
        }}
        .shyam-academy-latest-control {{
            position: absolute;
            z-index: 20;
        }}
        .shyam-academy-latest-control button {{
            pointer-events: auto;
            border-radius: 999px;
            min-width: 7rem;
            width: auto;
            height: 2.6rem;
            padding: 0 .95rem;
            font-size: .95rem;
            font-weight: 700;
            background: {"rgba(39,52,73,.94)" if dark else "rgba(255,255,255,.94)"};
            border: 1px solid {"rgba(203,213,225,.42)" if dark else "rgba(120,130,150,.3)"};
            box-shadow: 0 4px 14px rgba(30, 45, 65, .18);
        }}
        .st-key-{classroom_key}_generation_tick {{
            display: none !important;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def _wire_latest_control(
    history_dom_key: str, latest_dom_key: str, jump_to_latest: bool = False
) -> None:
    st.html(
        f"""
        <script>
        (() => {{
            const historySelector = '.st-key-{history_dom_key}';
            const latestSelector = '.st-key-{latest_dom_key}';
            const classroomSelector = historySelector.replace(/_history$/, '');
            const wiringStore = window.__classroomScrollWiring ||
                (window.__classroomScrollWiring = {{}});
            const findHistory = () => {{
                const root = document.querySelector(historySelector);
                if (!root) return null;
                root.dataset.classroomHistory = historySelector;
                const candidates = [
                    root,
                    ...root.querySelectorAll(
                        '[data-testid="stVerticalBlock"], [data-testid="stElementContainer"]'
                    ),
                ];
                const scrollCandidates = candidates.filter((element) => {{
                    const style = window.getComputedStyle(element);
                    return ['auto', 'scroll'].includes(style.overflowY) &&
                        element.scrollHeight > element.clientHeight;
                }});
                return scrollCandidates.sort((left, right) => {{
                    let leftDepth = 0;
                    let rightDepth = 0;
                    for (let node = left; node && node !== root; node = node.parentElement) {{
                        leftDepth += 1;
                    }}
                    for (let node = right; node && node !== root; node = node.parentElement) {{
                        rightDepth += 1;
                    }}
                    return rightDepth - leftDepth;
                }})[0] || null;
            }};
            const scrollHistoryToLatest = (root, updateVisibility) => {{
                const state = wiringStore[historySelector];
                if (!state) return;
                if (state.scrollObserver) state.scrollObserver.disconnect();
                let frame = 0;
                let settledFrames = 0;
                const settle = () => {{
                    const container = findHistory();
                    if (container) {{
                        container.scrollTop = container.scrollHeight;
                        updateVisibility(container);
                        const distance =
                            container.scrollHeight - container.clientHeight -
                            container.scrollTop;
                        settledFrames = distance <= 12 ? settledFrames + 1 : 0;
                    }}
                    frame += 1;
                    if (frame < 18 && settledFrames < 2) {{
                        state.scrollFrame = requestAnimationFrame(settle);
                    }} else if (state.scrollObserver) {{
                        state.scrollObserver.disconnect();
                        state.scrollObserver = null;
                    }}
                }};
                state.scrollObserver = new MutationObserver(() => {{
                    if (state.scrollFrame) cancelAnimationFrame(state.scrollFrame);
                    state.scrollFrame = requestAnimationFrame(settle);
                }});
                state.scrollObserver.observe(root, {{
                    childList: true,
                    subtree: true,
                    characterData: true,
                }});
                state.scrollFrame = requestAnimationFrame(settle);
            }};
            const scrollIntent = window.__classroomScrollIntent ||
                (window.__classroomScrollIntent = {{}});
            const wire = () => {{
                const container = findHistory();
                const latest = document.querySelector(latestSelector);
                const button = latest?.querySelector('button');
                if (!container || !latest || !button) return false;
                const previous = wiringStore[historySelector];
                if (previous && previous.container !== container) {{
                    previous.container.removeEventListener('scroll', previous.onScroll);
                    if (previous.scrollObserver) previous.scrollObserver.disconnect();
                    if (previous.scrollFrame) cancelAnimationFrame(previous.scrollFrame);
                    previous.onScroll = null;
                    previous.latest = null;
                }}
                const state = previous || {{
                    container,
                    onScroll: null,
                    latest: null,
                    scrollObserver: null,
                    scrollFrame: null,
                }};
                state.container = container;
                latest.classList.add('shyam-academy-latest-control');
                latest.dataset.shyamAcademyLatest = 'true';
                const positionLatest = () => {{
                    const classroom = document.querySelector(classroomSelector);
                    if (!classroom) return;
                    const classroomRect = classroom.getBoundingClientRect();
                    const historyRect = container.getBoundingClientRect();
                    const safeGap = 28;
                    const buttonWidth = latest.getBoundingClientRect().width;
                    latest.style.left =
                        `${{historyRect.left - classroomRect.left +
                            historyRect.width / 2 - buttonWidth / 2}}px`;
                    latest.style.top =
                        `${{historyRect.bottom - classroomRect.top -
                            latest.offsetHeight - safeGap}}px`;
                }};
                const updateVisibility = (current = container) => {{
                    const awayFromLatest =
                        current.scrollHeight - current.clientHeight -
                        current.scrollTop > 12;
                    scrollIntent[historySelector] = !awayFromLatest;
                    if (state.latest) {{
                        positionLatest();
                        state.latest.style.visibility = awayFromLatest ? 'visible' : 'hidden';
                        state.latest.style.opacity = awayFromLatest ? '1' : '0';
                        state.latest.style.pointerEvents = awayFromLatest ? 'auto' : 'none';
                    }}
                }};
                if (!state.onScroll || state.latest !== latest) {{
                    if (state.onScroll) {{
                        container.removeEventListener('scroll', state.onScroll);
                    }}
                    state.latest = latest;
                    state.onScroll = () => updateVisibility(state.container);
                    container.addEventListener('scroll', state.onScroll, {{ passive: true }});
                }}
                if (!button.dataset.latestWired) {{
                    button.dataset.latestWired = 'true';
                    button.addEventListener('click', (event) => {{
                        event.preventDefault();
                        event.stopPropagation();
                        scrollHistoryToLatest(
                            document.querySelector(historySelector),
                            (target) => updateVisibility(target),
                        );
                    }}, true);
                }}
                wiringStore[historySelector] = state;
                updateVisibility();
                if ({str(jump_to_latest).lower()}) {{
                    scrollIntent[historySelector] = true;
                    scrollHistoryToLatest(
                        document.querySelector(historySelector),
                        (target) => updateVisibility(target),
                    );
                }}
                return true;
            }};
            let attempts = 0;
            const retry = () => {{
                if (wire() || attempts++ >= 24) return;
                requestAnimationFrame(retry);
            }};
            retry();
        }})();
        </script>
        """,
        unsafe_allow_javascript=True,
    )


def _start_pending_generation(pending_phase_key: str) -> None:
    st.session_state[pending_phase_key] = "generating"


def _wire_generation_tick(classroom_key: str) -> None:
    st.html(
        f"""
        <script>
        (() => {{
            const selector = '.st-key-{classroom_key}_generation_tick button';
            const button = document.querySelector(selector);
            if (!button || button.dataset.generationTickWired) return;
            button.dataset.generationTickWired = 'true';
            requestAnimationFrame(() => button.click());
        }})();
        </script>
        """,
        unsafe_allow_javascript=True,
    )


def _save_title(
    connection,
    user_id: str,
    classroom_id: str,
    title_key: str,
    title_input_key: str,
    editing_title_key: str,
    title_change_handler=None,
) -> None:
    value = st.session_state[title_input_key].strip()
    if not value:
        st.session_state[title_input_key] = st.session_state[title_key]
        return
    rename_classroom(connection, user_id, classroom_id, value)
    if title_change_handler:
        title_change_handler(value)
    st.session_state[title_key] = value
    st.session_state[editing_title_key] = False


def _capture_prompt(
    history_key: str,
    prompt_key: str,
    pending_prompt_key: str,
    pending_phase_key: str,
    composer_generation_key: str,
) -> None:
    prompt = st.session_state[prompt_key].strip()
    if not prompt:
        st.session_state[f"{pending_prompt_key}_error"] = (
            "Enter a prompt before sending."
        )
        return
    st.session_state[history_key].append({"role": "user", "content": prompt})
    st.session_state[pending_prompt_key] = prompt
    st.session_state[pending_phase_key] = "queued"
    st.session_state[composer_generation_key] += 1
    st.session_state[f"{history_key}_jump_latest"] = True


def render_shared_classroom(
    connection,
    user_id: str,
    classroom_id: str,
    context_type: str,
    title: str,
    context_prompt: str,
    gateway,
    save_note_handler=None,
    title_change_handler=None,
) -> list[dict]:
    """Render the common conversation UI for learning, tests, and interviews."""
    stored = get_classroom(connection, user_id, classroom_id)
    history_key = f"shared_history_{classroom_id}"
    title_key = f"shared_title_{classroom_id}"
    reset_key = f"shared_reset_{classroom_id}"
    composer_generation_key = f"shared_composer_generation_{classroom_id}"
    pending_prompt_key = f"shared_pending_prompt_{classroom_id}"
    pending_phase_key = f"shared_pending_phase_{classroom_id}"
    auth_session_id = st.session_state.get("auth_session_id")
    auth_marker_key = f"{history_key}_auth_session"
    if history_key not in st.session_state:
        fresh_login = (
            auth_session_id
            and st.session_state.get(auth_marker_key) != auth_session_id
        )
        st.session_state[history_key] = (
            [] if fresh_login else load_history(connection, user_id, classroom_id)
        )
        if auth_session_id:
            st.session_state[auth_marker_key] = auth_session_id
    if title_key not in st.session_state:
        st.session_state[title_key] = (
            stored["title"] if stored and stored["title"] != classroom_id else title
        )
    st.session_state.setdefault(composer_generation_key, 0)
    editing_title_key = f"shared_editing_title_{classroom_id}"
    title_input_key = f"shared_title_input_{classroom_id}"

    classroom_key = f"shared_{classroom_id.replace('-', '_')}"
    render_classroom_styles(classroom_key)
    with st.container(key=classroom_key):
        with st.container(key=f"{classroom_key}_header"):
            header, save_column, reset = st.columns(
                [7, 1.5, 1], vertical_alignment="center"
            )
            save_requested = False
            with header:
                if st.session_state.get(editing_title_key):
                    st.text_input(
                        "Classroom title",
                        key=title_input_key,
                        label_visibility="collapsed",
                        on_change=lambda: _save_title(
                            connection, user_id, classroom_id, title_key,
                            title_input_key, editing_title_key, title_change_handler,
                        ),
                    )
                elif st.button(
                    st.session_state[title_key],
                    key=f"edit_classroom_title_{classroom_id}",
                    help="Edit classroom title",
                ):
                    st.session_state[title_input_key] = st.session_state[title_key]
                    st.session_state[editing_title_key] = True
                    st.rerun()
                st.caption(f"{context_type.replace('_', ' ').title()} classroom")
            with save_column:
                if save_note_handler:
                    save_requested = st.button(
                        "Save Notes", key=f"shared_save_note_{classroom_id}"
                    )
            with reset:
                reset_clicked = st.button(
                    "Reset", key=reset_key, help="Clear this active conversation"
                )
            if reset_clicked:
                clear_history(connection, user_id, classroom_id)
                st.session_state[history_key] = []
                st.session_state.pop(pending_prompt_key, None)
                st.session_state.pop(pending_phase_key, None)
                st.session_state[composer_generation_key] += 1
                st.rerun()
            if context_prompt:
                st.caption(context_prompt)

        with st.container(
            key=f"{classroom_key}_history",
            height=600,
            border=False,
        ):
            if not st.session_state[history_key]:
                st.info("Start the conversation with a question or prompt.")
            for message_index, message in enumerate(st.session_state[history_key]):
                role = "You" if message["role"] == "user" else "AI"
                style = "classroom-user" if message["role"] == "user" else "classroom-ai"
                with st.container(key=f"{classroom_key}_{style}_{message_index}"):
                    st.markdown(f"**{role}**")
                    if message["role"] == "user":
                        st.markdown(escape(message["content"]).replace("\n", "  \n"))
                    else:
                        st.markdown(message["content"])
            if st.session_state.get(pending_prompt_key):
                with st.container(key=f"{classroom_key}_classroom-loading"):
                    st.markdown("**AI**")
                    st.caption("AI is thinking...")
        if st.session_state.get(pending_phase_key) == "queued":
            with st.container(key=f"{classroom_key}_generation_tick"):
                st.button(
                    "Continue",
                    key=f"{classroom_key}_generation_tick_button",
                    on_click=_start_pending_generation,
                    args=(pending_phase_key,),
                )
        with st.container(key=f"{classroom_key}_latest"):
            st.button(
                "↓ Latest", key=f"latest_{classroom_id}",
                help="Jump to the latest message",
            )
        with st.container(key=f"{classroom_key}_composer"):
            with st.form(f"shared_composer_{classroom_id}"):
                composer, send_column = st.columns([9, 1], vertical_alignment="bottom")
                with composer:
                    st.text_input(
                        "Message",
                        key=(
                            f"shared_composer_value_{classroom_id}_"
                            f"{st.session_state[composer_generation_key]}"
                        ),
                        placeholder="Ask anything...",
                        label_visibility="collapsed",
                    )
                with send_column:
                    with st.container(key=f"{classroom_key}_send"):
                        st.form_submit_button(
                            "↑",
                            type="primary",
                            help="Send prompt",
                            on_click=_capture_prompt,
                            args=(
                                history_key,
                                f"shared_composer_value_{classroom_id}_"
                                f"{st.session_state[composer_generation_key]}",
                                pending_prompt_key,
                                pending_phase_key,
                                composer_generation_key,
                            ),
                        )

        if error := st.session_state.pop(f"{pending_prompt_key}_error", None):
            st.error(error)

        if (
            st.session_state.get(pending_phase_key) == "generating"
            and (pending_prompt := st.session_state.get(pending_prompt_key))
        ):
            try:
                response = gateway.generate_advanced(
                    context_type,
                    f"{context_prompt}\n\nUser request: {pending_prompt}",
                )
                if not isinstance(response, str) or not response.strip():
                    raise AIProviderError("The AI returned an empty response.")
                st.session_state[history_key].append(
                    {"role": "assistant", "content": response.strip()}
                )
                save_history(
                    connection, user_id, classroom_id,
                    st.session_state[history_key],
                    st.session_state[title_key],
                )
                st.session_state.pop(pending_prompt_key, None)
                st.session_state.pop(pending_phase_key, None)
                st.session_state[f"{history_key}_jump_latest"] = True
                st.rerun()
            except (ValueError, AIProviderError) as error:
                if (
                    st.session_state[history_key]
                    and st.session_state[history_key][-1]
                    == {"role": "user", "content": pending_prompt}
                ):
                    st.session_state[history_key].pop()
                st.session_state.pop(pending_prompt_key, None)
                st.session_state.pop(pending_phase_key, None)
                st.error(str(error))

        if save_requested:
            try:
                save_note_handler(
                    st.session_state[title_key],
                    st.session_state[history_key],
                )
            except ValueError as error:
                st.error(str(error))
            else:
                st.success("Saved to My Notes.")
    if st.session_state.get(pending_phase_key) == "queued":
        _wire_generation_tick(classroom_key)
    _wire_latest_control(
        f"{classroom_key}_history",
        f"{classroom_key}_latest",
        st.session_state.pop(f"{history_key}_jump_latest", False),
    )
    return st.session_state[history_key]
