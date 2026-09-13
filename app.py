import base64
import streamlit as st

from auth.session import get_current_user, sign_out
from database.connection import get_connection
from database.schema import initialize_database
from pages.auth import render_auth_screen
from services.appearance_service import (
    get_appearance, save_background, save_custom_background, save_theme,
)

st.set_page_config(
    page_title="Shyam Academy",
    page_icon=":material/school:",
    layout="wide",
)

connection = get_connection()
initialize_database(connection)
current_user = get_current_user()
if current_user is None:
    render_auth_screen()
    st.stop()

appearance = get_appearance(connection, current_user.user_id)
if st.session_state.get("appearance_user_id") != current_user.user_id:
    st.session_state.appearance_user_id = current_user.user_id
    st.session_state.academy_background = appearance["background"]
    st.session_state.academy_background_asset = appearance.get("asset_path")
    st.session_state.academy_theme = appearance.get("theme", "light")

backgrounds = {
    "paper": ("#f7f8fa", "#ffffff"),
    "blue": ("#eef5ff", "#12345b"),
    "green": ("#effaf4", "#174b35"),
    "lavender": ("#f7f1ff", "#3f2860"),
    "sand": ("#fff8ec", "#5a3b20"),
}
background_name = st.session_state.get("academy_background", "paper")
theme_name = st.session_state.get("academy_theme", "light")
sidebar_color = st.session_state.get("academy_sidebar_color", "#ffffff")
page_background, _ = backgrounds.get(background_name, backgrounds["paper"])
background_image = st.session_state.get("academy_background_asset")
if background_image and background_name == "custom":
    try:
        asset = base64.b64encode(open(background_image, "rb").read()).decode("ascii")
        mime = appearance.get("asset_mime") or "image/png"
        background_css = (
            f"background-image:url('data:{mime};base64,{asset}');"
            "background-size:cover;background-attachment:fixed;"
        )
    except OSError:
        background_css = f"background:{page_background};"
else:
    background_css = f"background:{page_background};"
theme_colors = {
    "light": {
        "app": "#f7f8fa", "surface": "#ffffff", "text": "#263238",
        "muted": "#5f6b75", "border": "rgba(120,130,150,.22)",
    },
    "dark": {
        "app": "#111827", "surface": "#1f2937", "text": "#e5edf5",
        "muted": "#aebdca", "border": "rgba(203,213,225,.22)",
    },
}[theme_name]
accent_colors = {
    "paper": "#64748b",
    "blue": "#2563eb",
    "green": "#16a34a",
    "lavender": "#7c3aed",
    "sand": "#b45309",
    "custom": "#2563eb",
}
accent = accent_colors.get(background_name, accent_colors["paper"])
base_background = theme_colors["app"]
if theme_name == "dark":
    background_css = f"background:{base_background};"
st.markdown(
    f"""
    <style>
    html, body, [class*="css"] {{
        font-size: 1.12rem;
        font-weight: 500;
        line-height: 1.5;
    }}
    h1 {{ font-size: clamp(2rem, 3.2vw, 2.8rem); font-weight: 750; letter-spacing: -0.015em; }}
    h2 {{ font-size: clamp(1.55rem, 2.5vw, 2.15rem); font-weight: 700; letter-spacing: -0.012em; }}
    h3 {{ font-size: clamp(1.3rem, 2vw, 1.7rem); font-weight: 700; letter-spacing: -0.01em; }}
    h4, h5, h6 {{ font-weight: 650; }}
    [data-testid="stMarkdownContainer"] p,
    [data-testid="stCaptionContainer"],
    [data-testid="stWidgetLabel"] {{
        font-size: 1.04rem;
        font-weight: 500;
        line-height: 1.5;
    }}
    [data-testid="stButton"] button,
    [data-testid="stFormSubmitButton"] button {{
        min-height: 2.75rem;
        padding: .55rem 1rem;
        font-size: 1.02rem;
        font-weight: 650;
    }}
    [data-testid="stTextInput"] input,
    [data-testid="stTextArea"] textarea,
    [data-testid="stNumberInput"] input,
    [data-baseweb="select"] {{
        font-size: 1.04rem;
        font-weight: 500;
    }}
    [data-testid="stMarkdownContainer"] p, [data-testid="stCaptionContainer"] {{
        color: {theme_colors["text"]};
    }}
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] {{
        font-size: 1.05rem;
        font-weight: 650;
    }}
    [data-testid="stSidebar"] [data-testid="stRadio"] label,
    [data-testid="stSidebar"] [data-testid="stSelectbox"] {{
        font-size: 1.04rem;
        font-weight: 550;
    }}
    [data-testid="stAppViewContainer"] {{
        {background_css}; color: {theme_colors["text"]};
    }}
    [data-testid="stHeader"] {{ background: {theme_colors["app"]}; }}
    [data-testid="stSidebar"] {{
        background: {theme_colors["surface"]}; color: {theme_colors["text"]};
    }}
    [data-testid="stButton"] button,
    [data-testid="stFormSubmitButton"] button {{
        border-color: {accent};
        background: {theme_colors["surface"]};
        color: {theme_colors["text"]};
        transition: background .15s ease, border-color .15s ease, color .15s ease;
    }}
    [data-testid="stButton"] button:hover,
    [data-testid="stFormSubmitButton"] button:hover {{
        background: #15803d;
        border-color: #15803d;
        color: #ffffff;
    }}
    [data-testid="stButton"] button[kind="primary"],
    [data-testid="stFormSubmitButton"] button[kind="primary"] {{
        background: {accent}; color: #ffffff;
    }}
    [data-testid="stTextInput"] input,
    [data-testid="stTextArea"] textarea,
    [data-testid="stNumberInput"] input {{
        background: {theme_colors["surface"]}; color: {theme_colors["text"]};
        border-color: {theme_colors["border"]};
    }}
    [data-baseweb="select"] > div,
    [data-testid="stSelectbox"] [data-baseweb="select"] > div {{
        background: {theme_colors["surface"]}; color: {theme_colors["text"]};
        border-color: {theme_colors["border"]};
    }}
    [data-testid="stVerticalBlockBorderWrapper"] {{
        border-color: {theme_colors["border"]};
    }}
    [data-testid="stPopoverButton"] {{
        border-radius: 999px; min-width: 2.75rem; min-height: 2.75rem;
        font-weight: 700; background: {accent}; color: #ffffff;
        border: 1px solid {accent};
    }}
    .st-key-bg-paper button, .st-key-bg-blue button, .st-key-bg-green button,
    .st-key-bg-lavender button, .st-key-bg-sand button {{
        border-radius: 999px; min-width: 2.25rem; min-height: 2.25rem;
        padding: 0; font-size: .78rem; color: #ffffff;
        border: 2px solid rgba(255,255,255,.7);
    }}
    .st-key-bg-paper button {{ background: #64748b; }}
    .st-key-bg-blue button {{ background: #2563eb; }}
    .st-key-bg-green button {{ background: #16a34a; }}
    .st-key-bg-lavender button {{ background: #7c3aed; }}
    .st-key-bg-sand button {{ background: #b45309; }}
    .st-key-bg-paper button:hover, .st-key-bg-blue button:hover,
    .st-key-bg-green button:hover, .st-key-bg-lavender button:hover,
    .st-key-bg-sand button:hover {{ filter: brightness(1.15); }}
    .st-key-header_bg-paper button, .st-key-header_bg-blue button,
    .st-key-header_bg-green button, .st-key-header_bg-lavender button,
    .st-key-header_bg-sand button {{
        border-radius: 999px; min-height: 2.2rem; padding: 0 .3rem;
        color: #ffffff; border: 2px solid transparent; font-size: .62rem;
    }}
    .st-key-header_bg-paper button {{ background: #64748b; }}
    .st-key-header_bg-blue button {{ background: #2563eb; }}
    .st-key-header_bg-green button {{ background: #16a34a; }}
    .st-key-header_bg-lavender button {{ background: #7c3aed; }}
    .st-key-header_bg-sand button {{ background: #b45309; }}
    </style>
    """,
    unsafe_allow_html=True,
)

pages = {
    "": [
        st.Page("pages/dashboard.py", title="Dashboard", icon=":material/dashboard:"),
        st.Page("pages/timetable.py", title="Timetable", icon=":material/calendar_month:"),
        st.Page("pages/ai_timetable_creator.py", title="AI Timetable Creator",
                url_path="ai-timetable-creator", icon=":material/auto_awesome:"),
        st.Page("pages/session_details.py", title="Session details", icon=":material/event:"),
        st.Page("pages/learning.py", title="Learning", icon=":material/school:"),
        st.Page("pages/progress.py", title="Progress", url_path="progress",
                icon=":material/insights:"),
    ],
    "Academy": [
        st.Page("pages/notes.py", title="My Notes", url_path="my-notes", icon=":material/description:"),
        st.Page("pages/full_notes.py", title="Full Notes", url_path="full-notes", icon=":material/article:"),
        st.Page("pages/attendance.py", title="Attendance", url_path="attendance", icon=":material/checklist:"),
        st.Page("pages/settings.py", title="Settings", url_path="settings",
                icon=":material/settings:"),
        st.Page("pages/notifications.py", title="Notifications", url_path="notifications",
                icon=":material/notifications:"),
    ],
    "Learning": [
        st.Page("pages/today_learning.py", title="Today Learning", url_path="today-learning"),
        st.Page("pages/level_1.py", title="Level 1", url_path="level-1"),
        st.Page("pages/level_2.py", title="Level 2", url_path="level-2"),
        st.Page("pages/problem_solving.py", title="Problem Solving", url_path="problem-solving"),
        st.Page("pages/doubts.py", title="Doubts", url_path="doubts"),
    ],
    "Tests": [
        st.Page("pages/tests.py", title="Tests", url_path="tests", icon=":material/quiz:"),
    ],
    "Interview": [
        st.Page("pages/interview_preparation.py", title="Interview Preparation", url_path="interview-preparation"),
        st.Page("pages/interview_room.py", title="Interview Room", url_path="interview-room"),
    ],
}

page = st.navigation(pages, position="sidebar")

with st.sidebar:
    st.markdown("## SHYAM ACADEMY")
    st.caption("Phase 12 · Advanced AI")
    st.caption("Appearance")
    selected_theme = st.toggle(
        "Dark theme",
        value=theme_name == "dark",
        key="academy_theme_toggle",
    )
    desired_theme = "dark" if selected_theme else "light"
    if desired_theme != theme_name:
        save_theme(connection, current_user.user_id, desired_theme)
        st.session_state.academy_theme = desired_theme
        st.rerun()
    bg_columns = st.columns(5)
    swatch_labels = {"paper": "P", "blue": "B", "green": "G", "lavender": "L", "sand": "S"}
    for column, name in zip(bg_columns, backgrounds):
        if column.button(
            swatch_labels[name], key=f"bg_{name}", help=f"{name.title()} background"
        ):
            appearance = save_background(connection, current_user.user_id, name)
            st.session_state.academy_background = appearance["background"]
            st.session_state.academy_background_asset = None
            st.rerun()

header_left, appearance_column, profile_column = st.columns([1, 0.12, 0.06])
with appearance_column:
    with st.popover(":material/palette:", help="Appearance controls"):
        st.caption("Appearance")
        header_theme = st.toggle(
            "Dark theme", value=theme_name == "dark", key="header_theme_toggle"
        )
        if ("dark" if header_theme else "light") != theme_name:
            save_theme(
                connection, current_user.user_id,
                "dark" if header_theme else "light",
            )
            st.session_state.academy_theme = "dark" if header_theme else "light"
            st.rerun()
        swatch_columns = st.columns(5)
        for column, name in zip(swatch_columns, backgrounds):
            if column.button(
                name.title(), key=f"header_bg_{name}",
                help=f"Use {name.title()} accent",
            ):
                selected = save_background(connection, current_user.user_id, name)
                st.session_state.academy_background = selected["background"]
                st.session_state.academy_background_asset = selected.get("asset_path")
                st.rerun()
        header_upload = st.file_uploader(
            "Custom image", type=["png", "jpg", "jpeg", "webp"],
            key="header_background_upload",
        )
        if header_upload is not None:
            selected = save_custom_background(
                connection, current_user.user_id, header_upload.getvalue(),
                header_upload.type or "image/png",
            )
            st.session_state.academy_background = selected["background"]
            st.session_state.academy_background_asset = selected["asset_path"]
            st.rerun()
with profile_column:
    email = st.session_state.get("firebase_email", "")
    initial = (email.split("@", 1)[0][:1] or "A").upper()
    with st.popover(initial, use_container_width=True):
        st.markdown("**Shyam Academy**")
        st.caption(email or "Authenticated account")
        if st.button("Logout", use_container_width=True):
            sign_out()
            st.rerun()

page.run()
