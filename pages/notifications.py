import streamlit as st
from auth.session import require_current_user

from database.connection import get_connection
from notifications import repository

connection = get_connection()
user_id = require_current_user().user_id
st.title("Notifications")
st.caption(f"{repository.count_unread(connection, user_id)} unread notification(s)")

for item in repository.list_notifications(connection, user_id):
    with st.container(border=True):
        st.markdown(f"**{item['title']}** · {item['status']}")
        st.write(item["body"])
        st.caption(f"{item['scheduled_at']} · {item['notification_type'] if 'notification_type' in item else item['type']}")
        if item["read_at"] is None and st.button("Mark as read", key=f"read_{item['notification_id']}"):
            repository.mark_read(connection, item["notification_id"], user_id)
            st.rerun()

if not repository.list_notifications(connection, user_id):
    st.info("No notifications yet.")
