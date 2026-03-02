"""
Streamlit UI for Rafa NL2SQL System.
Provides a chat interface for querying Oracle EBS data in Hebrew.
"""

import streamlit as st
import pandas as pd

# Local imports
import OracleConnection
import OracleCommunication as oc
import AI_Communication as Ai
import intent_handlers as ih
import utils as ut

# --- Constants ---
TABLE_THRESHOLD = 30  # Show table for datasets with more items

def page_config():
    st.set_page_config(
        page_title="Rafa - מערכת מלאי",
        page_icon="📦",
        layout="wide",
        initial_sidebar_state="collapsed"
    )

    st.markdown("""
    <style>
        /* Make entire app RTL - moves sidebar to right */
        .stApp { direction: rtl; }

        /* Chat messages RTL */
        .stChatMessage { direction: rtl; text-align: right; }
        [data-testid="stChatMessageContent"] { direction: rtl; text-align: right; }

        /* Chat input RTL */
        .stChatInputContainer { direction: rtl; }
        .stChatInput input,
        .stChatInput textarea,
        [data-testid="stChatInput"] input,
        [data-testid="stChatInput"] textarea {
            direction: rtl;
            text-align: right;
        }

        /* General text RTL */
        .stMarkdown { direction: rtl; text-align: right; }
    </style>
    """, unsafe_allow_html=True)

# --- Oracle Connection Management ---
@st.cache_resource
def get_oracle_connection():
    """Create and cache Oracle connection."""
    try:
        connection = OracleConnection.create_connection()
        return connection
    except Exception as e:
        st.error(f"Failed to connect to Oracle: {e}")
        return None

def init_oracle_module(connection):
    """Initialize OracleCommunication module with connection."""
    oc.connection = connection

def state_initialization():
    if 'chat_history' not in st.session_state:
        st.session_state.chat_history = [
            {
                'role': 'system',
                'content': 'You are a SQL expert. Context: The user is asking about general information in Oracle DB. Answer professionally'
            }
        ]

    if 'messages' not in st.session_state:
        st.session_state.messages = []

# ===========================================================
# Helper Functions
# ===========================================================
def analyze_request(user_input, chat_history):
    """Analyze user input using AI."""
    analysis = Ai.analyze_user_question(user_input, chat_history)
    if not ut.valid_analysis(analysis):
        return None, False
    return analysis, True

def drop_self_filter(filter_cond, product_names):
    """Prevent self-filtering when filter value matches a product name."""
    if filter_cond and product_names:
        f_value = str(filter_cond.get('value', '')).strip().lower()
        for prod in product_names:
            if prod.lower() in f_value or f_value in prod.lower():
                return None
    return filter_cond

def process_intent(intent, analysis, connection):
    """Process a single intent and return results."""
    if intent not in ih.INTENT_HANDLERS:
        return None

    # Get documents for this intent
    wanted_documents = oc.get_documents([intent])
    if not wanted_documents:
        return None

    # Get data
    data_tables, target_item_ids = oc.get_data(wanted_documents, analysis.get('product_names', []))
    if not data_tables:
        return None

    # Get filter condition
    filter_cond = analysis.get('filter_condition')
    product_names = analysis.get('product_names', [])
    filter_cond = drop_self_filter(filter_cond, product_names)

    # Call handler
    handler_function = ih.INTENT_HANDLERS[intent]
    result = handler_function(
        data_tables,
        target_item_ids,
        analysis.get('group_by_descriptions', []),
        filter_cond,
        analysis.get('date_filter')
    )

    return result

def process_message(user_input, chat_history, connection):
    """
    Process a user message and return structured result.

    Returns:
        dict with keys:
        - 'text': Hebrew response text
        - 'raw_data': Raw data for table display
        - 'show_table': Whether to show as table
    """
    # Initialize Oracle module
    init_oracle_module(connection)

    # Analyze the question
    analysis, valid = analyze_request(user_input, chat_history)

    if not valid:
        return {
            'text': "לא הצלחתי להבין את השאלה. נסה שוב.",
            'raw_data': None,
            'show_table': False
        }

    # Handle chat/unknown intents
    intents = analysis.get('intents', [])
    if 'chat' in intents or 'unknown' in intents:
        chat_reply = analysis.get('chat_reply', "שלום! אני מערכת רפא. אנא שאל אותי שאלות על מלאי ומכירות.")
        return {
            'text': chat_reply,
            'raw_data': None,
            'show_table': False
        }

    # Process data intents
    all_results = {}
    all_raw_data = {}

    for intent in intents:
        result = process_intent(intent, analysis, connection)
        if result:
            all_results[intent] = result
            if result.get('raw_data'):
                all_raw_data[intent] = result['raw_data']

    if not all_results:
        return {
            'text': "לא נמצא מידע עבור השאלה שלך.",
            'raw_data': None,
            'show_table': False
        }

    # Combine results
    response_text = Ai.summarize_multi_intent(user_input, all_results)

    # Determine if we should show a table
    total_items = sum(r.get('count', 0) for r in all_results.values())
    show_table = total_items >= TABLE_THRESHOLD and all_raw_data

    return {
        'text': response_text,
        'raw_data': all_raw_data if show_table else None,
        'show_table': show_table
    }

def convert_to_dataframe(raw_data):
    """Convert raw_data dict to pandas DataFrame."""
    if not raw_data:
        return None

    rows = []
    for intent, data in raw_data.items():
        if isinstance(data, dict):
            # Inventory format: {key: {total_qty, locations, lots, ...}}
            for key, stats in data.items():
                # Parse key (e.g., "346501 | WMS | LOT123")
                key_parts = str(key).split(' | ')
                product = key_parts[0]
                grouping = ' | '.join(key_parts[1:]) if len(key_parts) > 1 else ''

                rows.append({
                    'פריט': product,
                    'קיבוץ': grouping,
                    'כמות': stats.get('total_qty', 0),
                    'יחידה': stats.get('uom', 'יחידות'),
                    'מיקומים': ', '.join(stats.get('locations', [])[:3]),
                    'אצוות': ', '.join(stats.get('lots', [])[:3])
                })
        elif isinstance(data, list):
            # Transactions format: list of dicts
            for item in data:
                rows.append(item)

    if not rows:
        return None

    df = pd.DataFrame(rows)
    return df

# ===========================================================
# Main UI Functions
# ===========================================================
def display_chat_history():
    for msg in st.session_state.messages:
        with st.chat_message(msg['role']):
            st.markdown(msg['content'])
            # Show table if exists
            if msg.get('dataframe') is not None:
                st.dataframe(msg['dataframe'], use_container_width=True)

def manage_connection():
    st.title("📦 Rafa - מערכת מלאי חכמה")

    # Connect to Oracle
    connection = get_oracle_connection()

    if connection is None:
        st.error("לא ניתן להתחבר לבסיס הנתונים. בדוק את ההגדרות.")
        st.stop()
    return connection

def user_input(connection):
    if prompt := st.chat_input("שאל שאלה על מלאי, תנועות או מכירות..."):
        handle_user_input(prompt, connection)

def handle_user_input(prompt, connection):
    st.session_state.messages.append({'role': 'user', 'content': prompt})

    with st.chat_message('user'):
        st.markdown(prompt)

    # Process and respond
    with st.chat_message('assistant'):
        with st.spinner('מעבד את הבקשה...'):
            result = process_message(
                prompt,
                st.session_state.chat_history,
                connection
            )

        # Display response
        st.markdown(result['text'])

        # Show table for large datasets
        df = None
        if result.get('show_table') and result.get('raw_data'):
            df = convert_to_dataframe(result['raw_data'])
            if df is not None and not df.empty:
                st.dataframe(df, use_container_width=True)

                # Export button
                csv = df.to_csv(index=False, encoding='utf-8-sig')
                st.download_button(
                    label="📥 ייצוא ל-CSV",
                    data=csv,
                    file_name="rafa_export.csv",
                    mime="text/csv"
                )

        # Save to message history
        st.session_state.messages.append({
            'role': 'assistant',
            'content': result['text'],
            'dataframe': df
        })

    # Update chat history for AI context
    st.session_state.chat_history.append({'role': 'user', 'content': prompt})
    st.session_state.chat_history.append({'role': 'assistant', 'content': result['text']})

    # Moving window (keep last 10 messages)
    if len(st.session_state.chat_history) > 10:
        st.session_state.chat_history = [st.session_state.chat_history[0]] + st.session_state.chat_history[-9:]

def side_bar():
    with st.sidebar:
        st.markdown("### מידע")
        st.markdown("מערכת חכמה לשאילתות מלאי ומכירות")
        st.markdown("---")
        st.markdown("**דוגמאות לשאלות:**")
        st.markdown("- כמה מלאי יש של 346501?")
        st.markdown("- מה המלאי של HEDRIN לפי מספר מקט ולפי מחסן?")
        st.markdown("- תקבץ לי את 346501 לפי מספר חברה ותקבץ לפי מחסן")
        st.markdown("---")
        if st.button("🗑️ נקה היסטוריה"):
            st.session_state.messages = []
            st.session_state.chat_history = [st.session_state.chat_history[0]]
            st.rerun()

def run():
    page_config()
    state_initialization()
    connection = manage_connection()
    display_chat_history()
    user_input(connection)
    side_bar()

if __name__ == "__main__":
    run()