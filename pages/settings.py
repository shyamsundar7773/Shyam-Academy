import streamlit as st
from auth.session import require_current_user

from auth.firebase import get_firebase_configuration
from config.provider_config import get_provider_configuration, masked_credential, provider_status
from database.connection import get_connection
from notifications import repository
from database.repositories import routine_repository
from ai.settings import get_settings as get_ai_settings, save_settings as save_ai_settings

st.title("Settings")
st.caption("Secure configuration status. Secrets are never displayed or stored here.")
connection = get_connection()
user_id = require_current_user().user_id
current_user = require_current_user()

provider = get_provider_configuration()
st.subheader("AI provider")
st.write(f"Provider: **{provider.provider}**")
st.write(f"Model: **{provider.model}**")
st.write(f"Account reference: **{provider.account_reference or 'Not configured'}**")
st.write(f"Credential: **{masked_credential()}**")
st.write(f"Runtime status: **{provider_status()}**")
st.info("Provider credentials are read from the runtime environment or secret manager.")

st.subheader("Advanced AI")
ai_settings = get_ai_settings(connection, user_id)
with st.form("advanced_ai_settings"):
    ai_enabled = st.checkbox("Advanced AI enabled", value=ai_settings["enabled"])
    ai_provider = st.text_input("Preferred provider (optional)", value=ai_settings["preferred_provider"])
    ai_model = st.text_input("Preferred model (optional)", value=ai_settings["preferred_model"])
    voice_input = st.selectbox(
        "Voice input provider", ["not_configured", "mock"],
        index=0 if ai_settings["voice_input_provider"] != "mock" else 1,
    )
    voice_output = st.selectbox(
        "Voice output provider", ["not_configured", "mock"],
        index=0 if ai_settings["voice_output_provider"] != "mock" else 1,
    )
    save_ai = st.form_submit_button("Save Advanced AI settings")
if save_ai:
    save_ai_settings(connection, user_id, {
        "enabled": ai_enabled, "preferred_provider": ai_provider,
        "preferred_model": ai_model, "voice_input_provider": voice_input,
        "voice_output_provider": voice_output,
    })
    st.success("Advanced AI settings saved.")
    st.rerun()

firebase = get_firebase_configuration()
st.subheader("Firebase authentication")
st.write(f"Project: **{firebase.project_id or 'Not configured'}**")
st.write(f"Web authentication configuration: **{'Available' if firebase.enabled else 'Not configured'}**")
st.info("Firebase UID is verified server-side before it is used as the application identity.")

st.subheader("Notifications")
preferences = repository.get_preferences(connection, user_id)
with st.form("notification_preferences"):
    enabled = st.checkbox("Notifications enabled", value=preferences["notifications_enabled"])
    session_reminders = st.checkbox("Session reminders", value=preferences["session_reminders"])
    session_start = st.checkbox("Session start notifications", value=preferences["session_start"])
    missed = st.checkbox("Missed-session notifications", value=preferences["missed_session"])
    test_reminders = st.checkbox("Test reminders", value=preferences["test_reminders"])
    interview_reminders = st.checkbox("Interview reminders", value=preferences["interview_reminders"])
    mentor_recommendations = st.checkbox(
        "Mentor recommendations", value=preferences["mentor_recommendations"]
    )
    desktop = st.checkbox("Desktop delivery boundary", value=preferences["desktop_enabled"])
    android = st.checkbox("Android delivery boundary", value=preferences["android_enabled"])
    timezone = st.text_input("Timezone", value=preferences["timezone"])
    quiet_start = st.text_input("Quiet hours start", value=preferences["quiet_start"])
    quiet_end = st.text_input("Quiet hours end", value=preferences["quiet_end"])
    offset = st.number_input(
        "Reminder offset (minutes)", min_value=0, max_value=1440,
        value=int(preferences["reminder_offset_minutes"]),
    )
    save = st.form_submit_button("Save notification settings", type="primary")
if save:
    try:
        repository.save_preferences(connection, user_id, {
            "notifications_enabled": enabled, "session_reminders": session_reminders,
            "session_start": session_start, "missed_session": missed,
            "test_reminders": test_reminders, "interview_reminders": interview_reminders,
            "mentor_recommendations": mentor_recommendations, "desktop_enabled": desktop,
            "android_enabled": android, "timezone": timezone.strip(),
            "quiet_start": quiet_start.strip(), "quiet_end": quiet_end.strip(),
            "reminder_offset_minutes": int(offset),
        })
    except ValueError as error:
        st.error(str(error))
    else:
        st.success("Notification settings saved.")
        st.rerun()

st.subheader("Routine preferences")
routine_preferences = routine_repository.get_preference(connection, user_id)
with st.form("routine_preferences"):
    routine_enabled = st.checkbox("Routine reminders enabled", value=bool(routine_preferences["enabled"]))
    routine_offset = st.number_input(
        "Routine reminder lead time (minutes)", min_value=0, max_value=1440,
        value=int(routine_preferences["reminder_minutes"]),
    )
    save_routines = st.form_submit_button("Save routine settings")
if save_routines:
    routine_repository.set_preference(
        connection, user_id, routine_enabled, int(routine_offset)
    )
    st.success("Routine settings saved.")
