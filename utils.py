import re
import sys
import time
import threading
from config import FORBIDDEN_SQL_KEYWORDS

def check_valid(value, error_msg = "The value is not valid"):
    if not value:
        print(error_msg)
        raise Exception(error_msg)

def valid_analysis(analysis):
    if not analysis:
        print("Error with ollama, couldn't analyze the question, please try asking again!")
        return False

    intents = analysis.get('intents', [])
    if not intents:
        print("Couldn't find intent for your question, please try asking again!")
        return False

    # Chat and unknown intents are always valid (no product_names required)
    if 'chat' in intents or 'unknown' in intents:
        return True

    # Data intents are valid even without product_names (might query all)
    return True

def print_document(index, document):
    print(f"Index: {index}")
    print(f"ID:          {document[0]}")
    print(f"Name:        {document[1]}")
    print(f"Desc:        {document[2]}")
    print(f"Object ID:   {document[3]}")
    print(f"Object Name: {document[4]}")
    print(f"Table Name:  {document[5]}")
    print("="*60 + "\n")

def get_wanted_reports(reports_object):
    selected_reports = []
    while True:
        try:
            user_choice = input("Enter indexes of reports you would like to get: ")
            indexes = []
            for x in user_choice.split():
                if x.isdigit():
                    val = int(x)
                    if val not in indexes:
                        indexes.append(val)

            for idx in indexes:
                if 0 <= idx < len(reports_object):
                    selected_reports.append(reports_object[idx])
                else:
                    print(f"Index {idx} is out of range!, skipping...")

            if len(selected_reports) == 0:
                print("No reports were chosen, try again!\n")
                continue
            break

        except ValueError:
            print("Incorrect input, enter only digits!")

    print("\n" + "="*60 + "\nSelected Reports\n" + "="*60 + "\n")
    for index, report in enumerate(selected_reports): print_document(index, report)
    return selected_reports

def validate_read_only_sql(sql_query):
    if not sql_query: return False
    clean_sql_no_comments = remove_sql_comments(sql_query)
    clean_sql = clean_sql_no_comments.strip().upper()

    if not (clean_sql.startswith("SELECT") or clean_sql.startswith("WITH")):
        print(f"Query must start with SELECT or WITH. Started with: {clean_sql[:10]}...\n")
        return False

    for keyword in FORBIDDEN_SQL_KEYWORDS:
        pattern = r'\b' + keyword + r'\b'

        if re.search(pattern, clean_sql):
            print(f"Forbidden keyword in the SQL detected: '{keyword}'")
            return False
    return True

def execute_safe_sql(cursor, sql_query, **params):
    try:
        # 1. Logic check (Read-only validation) - check BEFORE sending to Oracle
        if not validate_read_only_sql(sql_query):
            raise Exception("Not a valid SQL query!")
        # 2. Parse check (Oracle syntax validation)
        cursor.parse(sql_query)

    except Exception as e:
        print(f"SQL Execution Error: {e}")
        return False

    # 3. Execution
    with StreamlitLoader("Executing the query"):
        cursor.execute(sql_query, **params)
    return True

def unwrap_discoverer_sql(sql_query):
    if not sql_query: return sql_query

    clean_sql = sql_query.strip()
    clean_sql = re.sub(r'\)\s+[a-zA-Z0-9_]+\s*$', ')', clean_sql)

    if clean_sql.startswith("(") and clean_sql.endswith(")"):
        return clean_sql[1:-1].strip()

    return clean_sql

def remove_sql_comments(sql):
    """
    Deleting comments for SQL queries.
    """
    if not sql: return sql

    pattern = r"('(''|[^'])*')|(--[^\r\n]*)|(/\*[\s\S]*?\*/)"
    regex = re.compile(pattern)

    def _replacer(match):
        if match.group(1):
            return match.group(1)
        return " "

    clean_sql = regex.sub(_replacer, sql)
    return "\n".join([line for line in clean_sql.splitlines() if line.strip()])

def run_security_context(cursor, sql_text):
    """
    Check if the documents needs verification (Apps Initialize).
    If it does, runs the function to Oracle
    """
    # We are looking for something like:
    # begin fnd_global.apps_initialize(0,21592,551); end;
    match = re.search(r'begin\s+fnd_global\.apps_initialize.*?end;', sql_text, re.IGNORECASE)

    if match:
        context_sql = match.group(0)
        print(f"Setting Security Context (Logging in as EBS User)...")

        try:
            cursor.execute(context_sql)
            print("Context set successfully.")
        except Exception as e:
            print(f"Failed to set context: {e}")


# =============================================================================
# DEPRECATED FUNCTIONS - Kept for reference, replaced by DB-based approach
# =============================================================================

def map_aliases_to_real_names_regex(sql_query):
    """
    DEPRECATED: Replaced by map_aliases_to_real_names() in OracleCommunication.py
    which queries EUL5_EXPRESSIONS table directly using exp_id.

    Old approach: Scans the SQL with regex to extract 'column AS i12345' patterns.
    """
    if not sql_query: return {}

    clean_sql = sql_query.replace("\n", " ").strip()
    pattern = r"([\w\.]+)\s+AS\s+(i\d+)"

    matches = re.findall(pattern, clean_sql, re.IGNORECASE)
    alias_map = {alias.upper(): real_name.upper() for real_name, alias in matches}
    return alias_map

class Loader:
    """
    A generic context manager for loading animations with a timer.
    Usage:
        with Loader("AI is thinking"):
            do_something()
    """

    def __init__(self, text="Processing"):
        self.text = text
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._animate)
        self.start_time = None

    def _animate(self):
        chars = [".  ", ".. ", "...", "   "]
        i = 0

        while not self.stop_event.is_set():
            elapsed = time.time() - self.start_time

            sys.stdout.write(f'\r{self.text}{chars[i % len(chars)]} ({elapsed:.1f}s)')
            sys.stdout.flush()

            time.sleep(0.5)
            i += 1

    def __enter__(self):
        self.start_time = time.time()
        self.thread.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop_event.set()
        self.thread.join()

        sys.stdout.write('\r' + ' ' * (len(self.text) + 20) + '\r')
        sys.stdout.flush()

class StreamlitLoader:
    """
    Context manager that uses st.spinner() in Streamlit, falls back to Loader in console.
    This allows the same code to work in both environments.
    """
    def __init__(self, text="Processing"):
        self.text = text
        self._is_streamlit = self._check_streamlit()
        self._ctx = None

    def _check_streamlit(self):
        try:
            import streamlit as st
            return st.runtime.exists()
        except:
            return False

    def __enter__(self):
        if self._is_streamlit:
            import streamlit as st
            self._ctx = st.spinner(self.text)
            return self._ctx.__enter__()
        else:
            self._ctx = Loader(self.text)
            return self._ctx.__enter__()

    def __exit__(self, *args):
        if self._ctx:
            return self._ctx.__exit__(*args)
        return None