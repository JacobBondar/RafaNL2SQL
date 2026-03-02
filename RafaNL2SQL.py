# Global libraries imports
from pprint import pprint

# Local assistance files
import utils as ut
import OracleCommunication as oc
import AI_Communication as Ai
import intent_handlers as ih


def main():
    try:
        oc.connect_to_oracle()
    except Exception as e:
        print(f"Failed to connect to Oracle: {e}")
        return

    chat_history = [
        {
            'role': 'system',
            'content': 'You are a SQL expert. Context: The user is asking about general information in Oracle DB.'
                       'Answer professionally'
        }
    ]
    print("\nWelcome to Rafa! I'm ready for your questions.")

    while run(chat_history): pass

    print("Goodbye! See you again!")


def run(chat_history):
    print("=" * 60)
    user_input = input("What would you like to ask? (Type 'יציאה' to quit):\n>>")
    if user_input == 'יציאה': return False

    chat_history.append({'role': 'user', 'content': user_input})

    analysis, valid = analyze_request(user_input, chat_history)
    if not valid: return True

    # Handle chat/unknown intents (skip SQL processing)
    if handle_chat_intent(analysis, chat_history): return True

    # Process each intent separately using handler dispatch
    all_results = {}
    # Extract group_by from analysis (for inventory breakdowns)

    for intent in analysis['intents']:
        run_intent(intent, all_results, analysis)

    # Combine results and send to AI
    if not all_results:
        print("No data found for any intent!")
        return True

    ollama_answer = Ai.summarize_multi_intent(user_input, all_results)
    print(f"\nAnswer:\n{ollama_answer}\n")

    chat_history.append({'role': 'assistant', 'content': ollama_answer})

    Ai.get_ai_run_times()

    # Moving window
    if len(chat_history) > 10:
        chat_history = [chat_history[0]] + chat_history[-9:]
    return True


def run_intent(intent, all_results, analysis):
    if intent not in ih.INTENT_HANDLERS:
        print(f"Intent '{intent}' not supported yet, skipping...")
        return

    # Get documents for THIS specific intent only
    wanted_documents = oc.get_documents([intent])
    if not wanted_documents:
        print(f"No documents found for intent: {intent}")
        return

    # Get data for this intent
    data_tables, target_item_ids = oc.get_data(wanted_documents, analysis.get('product_names', []))
    if not data_tables:
        print(f"No data retrieved for intent: {intent}")
        return

    # Extract filter_condition and check for redundant filters
    filter_cond = analysis.get('filter_condition')
    product_names = analysis.get('product_names', [])

    # Prevent self-filtering: if filter value matches a product name, drop it
    filter_cond = drop_self_filter(filter_cond, product_names)

    # Call the handler function with group_by_descriptions (list), filter_condition, and date_filter
    handler_function = ih.INTENT_HANDLERS[intent]
    result = handler_function(
        data_tables,
        target_item_ids,
        analysis.get('group_by_descriptions', []),
        filter_cond,
        analysis.get('date_filter')
    )
    all_results[intent] = result

    print(f"Processed intent: {intent} ({result.get('count', 'N/A')} items)")


def drop_self_filter(filter_cond, product_names):
    if filter_cond and product_names:
        f_value = str(filter_cond.get('value', '')).strip().lower()
        for prod in product_names:
            if prod.lower() in f_value or f_value in prod.lower():
                print(f"Dropping redundant filter '{f_value}' - matches product search.")
                return None
    return filter_cond


def analyze_request(user_input, chat_history):
    print("\n" + "="*20 + "Analyzing your request" + "="*20)

    analysis = Ai.analyze_user_question(user_input, chat_history)
    if not ut.valid_analysis(analysis): return analysis, False

    pprint(analysis, sort_dicts=False)
    return analysis, True


def handle_chat_intent(analysis, chat_history):
    """
    Handle chat/unknown intents - returns True if handled (should skip SQL), False otherwise.
    Adds the response to chat_history for context preservation.
    """
    intents = analysis.get('intents', [])
    if 'chat' not in intents and 'unknown' not in intents:
        return False

    chat_reply = analysis.get('chat_reply')
    if chat_reply:
        print(f"\nRafa: {chat_reply}")
    else:
        # Fallback if AI didn't generate a reply
        chat_reply = "שלום! אני מערכת רפא. אנא שאל אותי שאלות על מלאי ומכירות."
        print(f"\nRafa: {chat_reply}")

    # Add to chat history so context is preserved
    chat_history.append({'role': 'assistant', 'content': chat_reply})
    print("=" * 60)
    return True


if __name__ == "__main__":
    main()