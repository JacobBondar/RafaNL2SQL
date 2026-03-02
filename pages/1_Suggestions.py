"""
Suggestions and Feedback page for Rafa NL2SQL System.
Allows users to submit feedback and admins to view all suggestions.
"""

import streamlit as st
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from suggestions_db import init_db, add_suggestion, get_all_suggestions, update_suggestion_status

# ===========================================================
# Helper Functions
# ===========================================================
def show_admin_view(suggestions):
    st.markdown(f"**סה\"כ {len(suggestions)} הצעות:**")

    for s in suggestions:
        suggestion_id, timestamp, name, cat, text, status = s

        # Format timestamp
        date_str = timestamp[:10] if timestamp else "לא ידוע"

        # Status badge
        status_emoji = {
            'pending': '🟡',
            'reviewed': '👀',
            'implemented': '✅',
            'rejected': '❌'
        }.get(status, '⚪')

        with st.expander(f"{status_emoji} {cat} - {date_str} ({name})"):
            st.markdown(f"**מאת:** {name}")
            st.markdown(f"**תאריך:** {timestamp}")
            st.markdown(f"**קטגוריה:** {cat}")
            st.markdown(f"**סטטוס נוכחי:** {status}")
            st.info(text)

            st.markdown("---")
            st.markdown("**ניהול סטטוס:**")

            col1, col2, col3, col4 = st.columns(4)

            if col1.button("✅ בוצע", key=f"btn_done_{suggestion_id}"):
                update_suggestion_status(suggestion_id, "implemented")
                st.rerun()

            if col2.button("👀 בטיפול", key=f"btn_review_{suggestion_id}"):
                update_suggestion_status(suggestion_id, "reviewed")
                st.rerun()

            if col3.button("❌ דחה", key=f"btn_reject_{suggestion_id}"):
                update_suggestion_status(suggestion_id, "rejected")
                st.rerun()

            if col4.button("נקה סטטוס", key=f"btn_reset_{suggestion_id}"):
                update_suggestion_status(suggestion_id, "pending")
                st.rerun()

# ===========================================================
# Main UI Functions
# ===========================================================
def page_config():
    st.set_page_config(
        page_title="הצעות ומשוב - Rafa",
        page_icon="💡",
        layout="wide"
    )

    # --- RTL CSS for Hebrew ---
    st.markdown("""
    <style>
        .stApp { direction: rtl; }
        .stTextInput > div > div > input { direction: rtl; text-align: right; }
        .stTextArea > div > div > textarea { direction: rtl; text-align: right; }
        .stSelectbox > div > div { direction: rtl; }
        .stMarkdown { direction: rtl; text-align: right; }
    </style>
    """, unsafe_allow_html=True)

def main_content():
    st.title("💡 הצעות ומשוב")
    st.markdown("עזרו לנו לשפר את המערכת! שלחו הצעות, דיווחי באגים או בקשות לתכונות חדשות.")
    st.markdown("---")

def suggestion_form():
    st.subheader("שליחת הצעה חדשה")

    with st.form("suggestion_form", clear_on_submit=True):
        col1, col2 = st.columns([1, 2])

        with col1:
            user_name = st.text_input("שם (אופציונלי)", placeholder="השם שלך")

        with col2:
            category = st.selectbox("קטגוריה", [
                "בקשה לדו\"ח חדש",
                "שיפור ביצועים",
                "באג / תקלה",
                "שיפור ממשק",
                "שאלה על המערכת",
                "אחר"
            ])

        suggestion_text = st.text_area(
            "ההצעה שלך",
            height=150,
            placeholder="תאר את ההצעה, הבעיה או הבקשה שלך..."
        )

        submitted = st.form_submit_button("📤 שלח הצעה", use_container_width=True)

        if submitted:
            if suggestion_text.strip():
                success = add_suggestion(user_name, category, suggestion_text)
                if success:
                    st.success("✅ ההצעה נשלחה בהצלחה! תודה על המשוב!")
                else:
                    st.error("❌ אירעה שגיאה בשליחת ההצעה. נסה שוב.")
            else:
                st.warning("⚠️ נא להזין טקסט להצעה")

    st.markdown("---")

def admin_view():
    st.subheader("צפייה בהצעות (מנהלים)")

    show_admin = st.checkbox("הצג הצעות קיימות")

    if show_admin:
        # password = st.text_input("סיסמת מנהל", type="password")
        #
        # if password != "rafa2026":
        #     st.error("סיסמה שגויה")
        #     return

        suggestions = get_all_suggestions()

        if not suggestions:
            st.info("אין הצעות עדיין")

        if suggestions:
            show_admin_view(suggestions)

def side_bar():
    with st.sidebar:
        st.markdown("### קטגוריות")
        st.markdown("""
        - **בקשה לדו"ח חדש** - דו"חות או נתונים חדשים
        - **שיפור ביצועים** - המערכת איטית
        - **באג / תקלה** - משהו לא עובד
        - **שיפור ממשק** - עיצוב ונוחות
        - **שאלה** - עזרה בשימוש
        - **אחר** - כל דבר אחר
        """)

def run():
    page_config()
    init_db()
    main_content()
    suggestion_form()
    admin_view()
    side_bar()

run()