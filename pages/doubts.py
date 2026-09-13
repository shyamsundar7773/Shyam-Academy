import streamlit as st
from auth.session import require_current_user

from ai.gateway import get_gateway
from components.chat_classroom import render_shared_classroom
from database.connection import get_connection
from services.module_service import (
    get_or_create_classroom_module,
    rename_classroom_module,
)
from services.doubt_service import save_doubt as persist_doubt

connection = get_connection()
user_id = require_current_user().user_id
st.title("Doubts")
st.caption("Ask questions and keep the explanation in your Doubts notes.")
classroom_id = f"doubt_general_{user_id}"
module = get_or_create_classroom_module(
    connection, user_id, classroom_id, "Doubt discussion", "Independent Doubts"
)

def save_doubt(title, history):
    persist_doubt(
        connection, user_id, classroom_id, title, history,
        module["module_id"],
    )

def update_doubt_title(title):
    rename_classroom_module(connection, user_id, module["module_id"], title)

render_shared_classroom(
    connection, user_id, classroom_id, "doubt",
    module["module_name"],
    f"Module: {module['module_name']}",
    get_gateway(), save_doubt, update_doubt_title,
)
