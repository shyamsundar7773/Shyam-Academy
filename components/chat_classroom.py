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
    surface = "#1f2937" if dark else "rgba(255,255,255,.86)"
    header_surface = "#1f2937" if dark else "rgba(255,255,255,.97)"
    composer_surface = "#1f2937" if dark else "rgba(255,255,255,.98)"
    text = "#e5edf5" if dark else "#1d2733"
    ai_surface = "#273449" if dark else "#f4f6f8"
    user_text = "#d9ecff" if dark else "#12304f"
    st.markdown(
        f"""
        <style>
        .st-key-{classroom_key} {{
            width: 100%;
            height: min(78vh, 900px);
            min-height: 620px;
            display: flex;
            flex-direction: column;
            position: relative;
            border: 1px solid {"rgba(203,213,225,.22)" if dark else "rgba(120,130,150,.18)"};
            border-radius: 1.25rem;
            background: {surface};
            color: {text};
            overflow: hidden;
            font-size: 1.02rem;
        }}
        .st-key-{classroom_key} > div:first-child {{
            position: sticky;
            top: 0;
            z-index: 3;
            background: {header_surface};
            border-bottom: 1px solid {"rgba(203,213,225,.22)" if dark else "rgba(120,130,150,.18)"};
            padding: .9rem 1.1rem .65rem;
        }}
        .st-key-{classroom_key} [data-testid="stVerticalBlock"] {{
            padding-left: 1.1rem;
            padding-right: 1.1rem;
        }}
        .st-key-edit_classroom_title-{classroom_key} button {{
            border: 0;
            background: transparent;
            padding: 0;
            font-size: 1.5rem;
            font-weight: 700;
            color: {text};
        }}
        .st-key-{classroom_key}_history {{
            flex: 1 1 auto;
            height: 100%;
            min-height: 0;
            overflow-y: auto;
            padding: 1.25rem clamp(1.25rem, 8vw, 7rem) 6.8rem;
            scroll-behavior: smooth;
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
            line-height: 1.58;
            font-size: 1.04rem;
        }}
        .st-key-{classroom_key}_history [class*="classroom-user"] {{
            background: {"#24496d" if dark else "#e5f1ff"};
            color: {user_text};
            margin-left: auto;
        }}
        .st-key-{classroom_key}_history [class*="classroom-ai"] {{
            background: {ai_surface};
            color: {text};
            margin-right: auto;
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
            font-size: .67rem;
            font-weight: 800;
        }}
        .st-key-{classroom_key}_history [class*="classroom-role"] {{
            font-weight: 700;
            font-size: .92rem;
            margin-bottom: .2rem;
        }}
        .st-key-{classroom_key}_composer {{
            position: absolute;
            left: 1rem;
            right: 1rem;
            bottom: 0;
            z-index: 3;
            background: {composer_surface};
            border: 1px solid {"rgba(203,213,225,.28)" if dark else "rgba(120,130,150,.25)"};
            border-radius: 1.15rem;
            box-shadow: 0 -8px 24px rgba(18, 31, 49, .08);
            padding: .75rem 1rem .9rem;
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
            font-size: 1.02rem !important;
        }}
        .st-key-{classroom_key}_send button {{
            min-height: 3.25rem;
            width: 3.25rem;
            border-radius: 999px;
            font-size: 1.35rem;
            font-weight: 700;
            background: #16b99a;
            border-color: #16b99a;
            color: #ffffff;
        }}
        .st-key-{classroom_key}_composer [class*="_send"] {{
            position: absolute;
            right: 1.45rem;
            bottom: .9rem;
            width: 3.25rem;
            z-index: 4;
        }}
        .st-key-{classroom_key}_latest {{
            position: absolute;
            left: 50%;
            bottom: 6.6rem;
            z-index: 2;
            pointer-events: none;
            transform: translateX(-50%);
        }}
        .st-key-{classroom_key}_latest button {{
            pointer-events: auto;
            border-radius: 999px;
            min-width: 2.8rem;
            width: 2.8rem;
            height: 2.8rem;
            padding: 0;
            font-size: 1.4rem;
            box-shadow: 0 4px 14px rgba(30, 45, 65, .18);
        }}
        .st-key-{classroom_key}_latest button p {{
            font-size: 0;
        }}
        .st-key-{classroom_key}_latest button p::after {{
            content: "↓";
            font-size: 1.4rem;
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
            const wire = () => {{
                const container = document.querySelector(historySelector);
                const latest = document.querySelector(latestSelector);
                if (!container || !latest) return false;
                const updateVisibility = () => {{
                    const awayFromLatest =
                        container.scrollHeight - container.clientHeight -
                        container.scrollTop > 24;
                    latest.style.visibility = awayFromLatest ? 'visible' : 'hidden';
                    latest.style.opacity = awayFromLatest ? '1' : '0';
                    latest.style.pointerEvents = awayFromLatest ? 'auto' : 'none';
                }};
                container.addEventListener('scroll', updateVisibility, {{ passive: true }});
                updateVisibility();
                if ({str(jump_to_latest).lower()}) {{
                    container.scrollTo({{
                        top: container.scrollHeight,
                        behavior: 'smooth'
                    }});
                    setTimeout(updateVisibility, 350);
                }}
                return true;
            }};
            if (!wire()) {{
                requestAnimationFrame(() => {{
                    if (!wire()) setTimeout(wire, 100);
                }});
            }}
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
        header, save_column, reset = st.columns([7, 1.5, 1], vertical_alignment="center")
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
            st.session_state[composer_generation_key] += 1
            st.rerun()
        if context_prompt:
            st.caption(context_prompt)

        with st.container(key=f"{classroom_key}_history"):
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
        with st.container(key=f"{classroom_key}_composer"):
            with st.form(f"shared_composer_{classroom_id}"):
                composer, send_column = st.columns([1, 0.001], vertical_alignment="bottom")
                with composer:
                    prompt = st.text_input(
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
                        send = st.form_submit_button("↑", type="primary", help="Send prompt")
        with st.container(key=f"{classroom_key}_latest"):
            latest = st.button(
                "↓", key=f"latest_{classroom_id}",
                help="Jump to the latest message",
            )
        if latest:
            st.session_state[f"{history_key}_jump_latest"] = True
            st.rerun()
        if send:
            if not prompt.strip():
                st.error("Enter a prompt before sending.")
            else:
                try:
                    response = gateway.generate_advanced(
                        context_type,
                        f"{context_prompt}\n\nUser request: {prompt.strip()}",
                    )
                    if not isinstance(response, str) or not response.strip():
                        raise AIProviderError("The AI returned an empty response.")
                    st.session_state[history_key].extend(
                        [{"role": "user", "content": prompt.strip()},
                         {"role": "assistant", "content": response.strip()}]
                    )
                    save_history(
                        connection, user_id, classroom_id,
                        st.session_state[history_key],
                        st.session_state[title_key],
                    )
                    st.session_state[composer_generation_key] += 1
                    st.session_state[f"{history_key}_jump_latest"] = True
                    st.rerun()
                except (ValueError, AIProviderError) as error:
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
        _wire_latest_control(
            f"{classroom_key}_history",
            f"{classroom_key}_latest",
            st.session_state.pop(f"{history_key}_jump_latest", False),
        )
    return st.session_state[history_key]
