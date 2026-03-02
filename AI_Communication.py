import json
import datetime
import time
import prompts
from ollama import Client
import utils
from config import (
    OLLAMA_MODEL, INTENT_NAMES_HEBREW,
    AI_FORMAT_MAX_ITEMS, AI_FORMAT_MAX_CHARS
)

AI_RUN_TIME = {}


def get_ai_run_times():
    """Prints the dictionary of AI response times."""
    print("\n--- AI Run Times ---")
    total_time = 0
    for response, elapsed_time in AI_RUN_TIME.items():
        # Remove newlines and limit to 30 characters
        total_time += elapsed_time
        cleaned_key = response.replace('\n', ', ').strip()
        if len(cleaned_key) > 30:
            cleaned_key = cleaned_key[:27] + "..."
        print(f"{cleaned_key}: {elapsed_time:.2f}s")

    print(f"Total AI time: {total_time:.2f}s")


def send_to_ollama_raw(messages_list):
    """
    Generical function that takes care of communication and animation
    :param messages_list:
    :return: text list
    """

    response_content = None
    try:
        client = Client()
        # chat can run forever, maybe add time in the future to terminate the program
        start_time = time.time()
        with utils.StreamlitLoader("AI is thinking"):
            response = client.chat(
                model=OLLAMA_MODEL,
                messages=messages_list,
                options={'temperature': 0}
            )
        elapsed_time = time.time() - start_time
        response_content = response['message']['content']

        # DEBUGGING - store response with its execution time
        AI_RUN_TIME[response_content] = elapsed_time

    except Exception as e:
        print(f"\nConnection error with ollama: {e}")

    return response_content


def analyze_user_question(user_question, chat_history=None):
    """
    Function to analyze the user question.
    :param user_question:
    :param chat_history:
    :return: The analyzed question.
    """
    if chat_history is None: chat_history = []

    now = datetime.datetime.now()
    current_date_str = now.strftime("%d/%m/%Y %H:%M:%S")

    system_prompt = prompts.ANALYZE_USER.format(current_date_str=current_date_str)

    messages_for_analysis = [{'role': 'system', 'content': system_prompt}]
    if len(chat_history) > 0:
        # Skip the generic system prompt from main history
        messages_for_analysis.extend(chat_history[1:])
    messages_for_analysis.append({'role': 'user', 'content': user_question})

    content = send_to_ollama_raw(messages_for_analysis)
    if not content: return None

    return clean_ai(content,
                    f"AI has successfully analyzed the following question: '{user_question}'\n",
                    "Error parsing analyzed user question JSON:")


def format_large_dataset_manually(stats_text):
    """
    Fast Hebrew formatting without AI - for large datasets.
    Replaces English terms with Hebrew equivalents.
    Used when dataset exceeds AI_FORMAT_MAX_ITEMS or AI_FORMAT_MAX_CHARS.

    Output is markdown-compatible (uses double newlines for line breaks).
    """
    # Count items for header
    item_count = stats_text.count('- Product:')
    zero_stock = None

    # Build response header
    lines = [
        f"**להלן פירוט המלאי ({item_count} פריטים):**",
        ""
    ]

    for line in stats_text.split('\n'):
        zero_stock = translate_line(line, lines, zero_stock)

    if zero_stock:
        lines.append("")
        lines.append(f"⚠️ {zero_stock}")

    lines.append("")
    lines.append(f"*נוצר: {datetime.datetime.now().strftime('%d/%m/%Y %H:%M')}*")

    # Use double newlines for markdown paragraph breaks
    return "\n\n".join(lines)


def translate_line(line, lines, current_zero_stock):
    if not line.strip(): return current_zero_stock

    if "ZERO STOCK COUNT" in line:
        try:
            count = line.split(":")[1].strip().split(" ")[0]
            return f"ישנם {int(count)} מוצרים ללא מלאי!"
        except:
            return "ישנם מוצרים ללא מלאי!"

    # Translate BREAKDOWN headers
    if "BREAKDOWN BY" in line:
        group_name = line.replace("BREAKDOWN BY", "").replace(":", "").strip()
        hebrew_groups = {
            "LOCATION": "מיקום",
            "LOT": "אצווה",
            "ORG": "ארגון",
            "SUBINVENTORY": "מחסן",
            "EXPIRE_FLAG": "סטטוס תוקף",
            "LOT_STATUS": "סטטוס אצווה",
            "MULTIPLE COLUMNS": "פירוט משולב"
        }
        heb_name = hebrew_groups.get(group_name, group_name)
        lines.append(f"**חלוקה לפי {heb_name}:**")
        return current_zero_stock

    # Translate data lines - use markdown list syntax
    formatted = line\
        .replace("- Product:", "- **פריט")\
        .replace(", GroupBy: [", "** | ")\
        .replace("], Quantity:", " | כמות:")\
        .replace(", Variant:", " | סוג:")\
        .replace(", Quantity:", " | כמות:")\
        .replace(", Locations:", " | מיקומים:")\
        .replace(", Lots:", " | אצוות:")\
        .replace(", Orgs:", " | ארגונים:")\
        .replace(" EA", " יח'")\
        .replace(" N ", " תקין ")\
        .replace(" Y ", " פג תוקף ")\
        .replace(" Q ", " פסול ")\
        .replace(" A ", " זמין ")\
        .replace("(Not found in inventory)", "(לא קיים במלאי)") \
        .replace("N/A", "-")

    # Close bold tag if we opened one for product
    if formatted.startswith("- **פריט") and "**" not in formatted[10:]:
        # Find first pipe and close bold before it
        first_pipe = formatted.find(" | ")
        if first_pipe > 0:
            formatted = formatted[:first_pipe] + "**" + formatted[first_pipe:]

    lines.append(formatted)
    return current_zero_stock


def format_inventory_hebrew(user_question, stats_text):
    """
    Formats inventory data into Hebrew.
    Hybrid Mode: Uses AI for small datasets, manual formatting for large datasets.
    Called by process_inventory_logic handler.
    """
    if not stats_text or stats_text == "NO_DATA_FOUND":
        return "לא נמצא מלאי עבור הפריטים המבוקשים."

    # Count items (lines starting with "- Product:")
    item_count = stats_text.count('- Product:')

    # Check if dataset is too large for AI
    if item_count > AI_FORMAT_MAX_ITEMS or len(stats_text) > AI_FORMAT_MAX_CHARS:
        print(f"Large dataset ({item_count} items, {len(stats_text)} chars). Using fast formatting.")
        return format_large_dataset_manually(stats_text)

    # --- Regular AI path for small datasets ---
    print(f"Small dataset ({item_count} items). Using AI formatting.")

    system_prompt = prompts.INVENTORY_HEBREW

    user_prompt = f"User question: {user_question}\n\nInventory Data:\n{stats_text}\n\nFormat in Hebrew:"

    return send_to_ollama_raw([
        {'role': 'system', 'content': system_prompt},
        {'role': 'user', 'content': user_prompt}
    ])


def format_transactions_hebrew(user_question, transactions_text):
    """
    Formats transactions data into Hebrew using AI.
    """
    if not transactions_text:
        return "לא נמצאו תנועות עבור הפריטים המבוקשים."

    system_prompt = prompts.TRANSACTION_HEBREW

    user_prompt = f"User question: {user_question}\n\nTransactions:\n{transactions_text}\n\nFormat in Hebrew:"

    return send_to_ollama_raw([
        {'role': 'system', 'content': system_prompt},
        {'role': 'user', 'content': user_prompt}
    ])


def pick_filtering_column(columns_list, search_intent):
    system_prompt = prompts.PICK_COLUMNS.format(columns_list=columns_list)

    user_prompt = f"Which column matches '{search_intent}'?"

    column_name = send_to_ollama_raw([
        {'role': 'system', 'content': system_prompt},
        {'role': 'user', 'content': user_prompt}
    ])

    return column_name.strip()


def match_column_semantic(description, columns_list):
    """
    Uses AI to find which column best matches the user's grouping description.
    """
    if not description or not columns_list:
        return None

    system_prompt = prompts.FIND_COLUMNS_GROUPING

    user_prompt = f"""Columns available: {columns_list}
                      User wants to group by: "{description}"
                      Which column matches?"""

    response = send_to_ollama_raw([
        {'role': 'system', 'content': system_prompt},
        {'role': 'user', 'content': user_prompt}
    ])

    if not response: return None

    result = response.strip().replace("'", "").replace('"', "")

    if result == "NO_MATCH": return None

    # Validate the response is actually in the columns list
    for col in columns_list:
        if col.upper() == result.upper():
            return col

    return None


def get_injection_point(sql_query):
    """
    Uses AI to find the best injection point for filtering in a complex SQL query.
    Returns a dict with 'column', 'anchor', and 'has_where'.
    Returns None on error.
    """

    system_prompt = prompts.FIND_INJECTION_POINT

    user_prompt = f"SQL Query:\n{sql_query}"

    messages = [
        {'role': 'system', 'content': system_prompt},
        {'role': 'user', 'content': user_prompt}
    ]

    print("AI looks for injection point...")
    response = send_to_ollama_raw(messages)

    if not response: return None

    return clean_ai(response,
                    "AI has successfully analyzed the injection point!",
                    "Error parsing injection point JSON:")


def clean_ai(response, success_message, error_message):
    try:
        if "```" in response:
            response = response.replace("```json", "").replace("```", "").strip()

        result = json.loads(response)
        if isinstance(result, list):
            if len(result) > 0:
                result = result[0]
            else:
                print("AI returned an empty list.")
                return None

        print(success_message)
        return result

    except Exception as e:
        print(f"{error_message} {e}")
        return None


def summarize_multi_intent(user_question, results_by_intent):
    """
    Since handlers now return formatted Hebrew text, we just combine them.
    Output is markdown-compatible.
    """

    parts = []

    for intent, result in results_by_intent.items():
        title = INTENT_NAMES_HEBREW.get(intent, intent)
        content = result.get('data', 'לא נמצא מידע')

        # Use markdown header for section title
        parts.append(f"### {title}\n\n{content}")

    return "\n\n---\n\n".join(parts)