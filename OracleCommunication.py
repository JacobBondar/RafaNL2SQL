from oracledb import Connection
from typing import Optional
import AI_Communication as Ai
import OracleConnection
import data_utils as du
import utils
import re
import queries
from config import KNOWN_DOCUMENTS_NAME, MAX_ROWS_QUERY

connection: Optional[Connection] = None


def connect_to_oracle():
    global connection
    connection = OracleConnection.create_connection()
    utils.check_valid(connection, "Error creating connection")


def get_data(wanted_documents, products=None):
    if connection is None:
        print("Error: No connection to Oracle inside get_data!")
        return [], []

    cursor = connection.cursor()
    all_results = []

    # --- Step 1: Get Item IDs from Master Table ---
    # Returns: None = no filter (query all), [] = not found (abort), [ids] = found
    target_item_ids = get_all_ids(products, cursor)
    if target_item_ids == []:  # Products specified but not found in DB
        cursor.close()
        return [], []
    # If target_item_ids is None → continue without product filter (query all)

    # --- Step 2: Iterate Reports ---
    for document in wanted_documents:
        run_document(document, target_item_ids, all_results, cursor, products)

    cursor.close()
    return all_results, target_item_ids


def run_document(document, target_item_ids, all_results, cursor, products):
    doc_name = document[1]
    obj_id = document[3]
    obj_name = document[4]
    sobj_ext_table = document[5]
    print("\n" + "=" * 60 + f"\nProcessing Report: {doc_name} (obj_name: {obj_name})\n" + "=" * 60)

    # Handle simple table
    if sobj_ext_table:
        base_sql, columns = deal_with_ext_table(sobj_ext_table, cursor)

    # Handle complex SQL (Chunks)
    else:
        base_sql, columns, valid = deal_with_non_ext_table(cursor, obj_id, obj_name)
        if not valid: return

    if base_sql: utils.run_security_context(cursor, base_sql)

    # --- Step 3: Create Alias Map (i123 -> ITEM_NO) ---
    alias_map = map_aliases_to_real_names(cursor, base_sql)

    final_query = base_sql

    # --- Step 4: Intelligent Filtering ---
    filtered_query = filtering_column(products, columns, alias_map, base_sql, target_item_ids, cursor)
    if filtered_query: final_query = filtered_query

    result_item = executing_final_sql(cursor, final_query, columns, alias_map, doc_name)
    if result_item:
        # === GLOBAL ENRICHMENT ===
        # Every result from DB gets checked: "Do you have an expire date?"
        # If yes - it gets a Y/N flag for free.
        enriched_data, enriched_cols = du.add_expire_flag(
            result_item['data'],
            result_item['columns']
        )
        result_item['data'] = enriched_data
        result_item['columns'] = enriched_cols

        all_results.append(result_item)


def deal_with_ext_table(sobj_ext_table, cursor):
    print("Found an existing table!")
    return queries.SELECT_ALL_TABLE.format(table_name=sobj_ext_table), get_columns_names(sobj_ext_table, cursor)


def deal_with_non_ext_table(cursor, obj_id, obj_name):
    print("Didn't find an existing table, looking for SQL query...")
    columns = []
    base_sql = get_known_sql(cursor, obj_id, obj_name)
    if not base_sql:
        print(f"No SQL found for Object: {obj_name}\n")
        return "", [], False

    try:
        # Get only the columns (empty table)
        temp_query = queries.SELECT_EMPTY_STRUCTURE.format(base_sql=base_sql)
        if utils.execute_safe_sql(cursor, temp_query):
            if cursor.description:
                columns = [col[0] for col in cursor.description]
    except Exception as e:
        print(f"Failed to fetch columns for complex SQL: {e}")
        return "", [], False

    return base_sql, columns, True


def create_readable_columns(alias_map, columns):
    # Create a READABLE list of columns for the AI
    # Translate i123 -> ITEM_NO using the map. If not in map, keep original.
    readable_columns = []
    for col in columns:
        readable_columns.append(alias_map.get(col.upper(), col))
    return readable_columns


def inject_filter(base_sql, injection_info, target_item_ids, cursor):
    """
    Attempts to inject a filter into the SQL.
    - If WHERE exists: inject after anchor
    - If no WHERE: add WHERE clause before ORDER BY/GROUP BY or at end
    Returns the modified SQL if successful, or None if injection fails.
    """
    column = injection_info.get("column")
    anchor = injection_info.get("anchor")
    has_where = injection_info.get("has_where", True)

    if not column:
        print("Injection info missing column")
        return None

    if has_where and not anchor:
        print("Injection info missing anchor (required when WHERE exists)")
        return None

    ids_string = "', '".join(target_item_ids)
    if has_where:
        # Case A: Existing WHERE -> Must inject AND after anchor
        injected_sql = inject_filter_where(column, ids_string, anchor, base_sql)
        if not injected_sql: return None

    else:
        # Case B: No WHERE -> Start a new WHERE clause
        injected_sql = inject_filter_no_where(column, ids_string, anchor, base_sql)

    # Validate with existing utils functions
    if not utils.validate_read_only_sql(injected_sql):
        print("Injected SQL failed read-only validation\n")
        return None

    try:
        cursor.parse(injected_sql)
        print(f"Filter injected.\n")
        return injected_sql
    except Exception as e:
        print(f"Oracle parse failed: {e}")
        return None


def inject_filter_where(column, ids_string, anchor, base_sql):
    prefix = "AND"
    filter_clause = f" {prefix} {column} IN ('{ids_string}') AND ROWNUM <= {MAX_ROWS_QUERY}"

    # Validate anchor existence in string
    if anchor not in base_sql:
        match = re.search(re.escape(anchor), base_sql, re.IGNORECASE)
        if not match:
            print(f"Anchor '{anchor}' not found in SQL base.")
            return None
        anchor = match.group(0)

    return base_sql.replace(anchor, f"{anchor}\n{filter_clause}", 1)


def inject_filter_no_where(column, ids_string, anchor, base_sql):
    prefix = "WHERE"
    filter_clause = f" {prefix} {column} IN ('{ids_string}') AND ROWNUM <= {MAX_ROWS_QUERY}"

    if anchor:
        # AI gave us a table name to inject after
        if anchor not in base_sql:
            match = re.search(re.escape(anchor), base_sql, re.IGNORECASE)
            if match:
                anchor = match.group(0)

        if anchor and anchor in base_sql:
            return base_sql.replace(anchor, f"{anchor}\n{filter_clause}", 1)
        else:
            # Fallback: just append
            return f"{base_sql}\n{filter_clause}"
    else:
        # AI returned None for anchor -> Just append to the end of the SQL
        # (This solves your specific error!)
        return f"{base_sql}\n{filter_clause}"


def fallback_wrap_filter(base_sql, columns, alias_map, target_item_ids):
    """
    Original wrapping approach - used as fallback when injection fails.
    Wraps the SQL and filters on the outer query.
    If target_item_ids is None, returns query with only ROWNUM limit (no product filter).
    """
    # If no product filter needed (None), just add row limit
    if target_item_ids is None:
        print("No product filter - querying all items with row limit.")
        return f"SELECT * FROM ({base_sql}) WHERE ROWNUM <= {MAX_ROWS_QUERY}"

    print("Using fallback wrap filter approach!")

    # Create readable list for AI
    readable_columns = create_readable_columns(alias_map, columns)
    # Ask AI using the READABLE names
    chosen_readable = Ai.pick_filtering_column(readable_columns, "Item Number / SKU")

    if chosen_readable and chosen_readable != "UNKNOWN":
        result = wrap(chosen_readable, alias_map, columns, target_item_ids, base_sql)
        if result: return result
    else:
        print("AI could not identify Item Number column. Fetching all data.")

    return f"SELECT * FROM ({base_sql}) WHERE ROWNUM <= {MAX_ROWS_QUERY}"


def wrap(chosen_readable, alias_map, columns, target_item_ids, base_sql):
    print(f"AI successfully identified filtering column (Readable): {chosen_readable}")

    actual_sql_col = find_actual_col(alias_map, chosen_readable)

    # Fallback: Maybe AI returned the original technical name
    if not actual_sql_col and chosen_readable in columns:
        actual_sql_col = chosen_readable

    if actual_sql_col:
        return build_sql_filtered(base_sql, actual_sql_col, target_item_ids)
    else:
        print(f"Could not map '{chosen_readable}' back to a valid SQL column.")
    return None


def find_actual_col(alias_map, chosen_readable):
    # Reverse Lookup: Translate back to Technical Name (i123) for SQL
    actual_sql_col = None

    # Check if the AI returned a mapped name (e.g. ITEM_NO)
    # We search for the key (i123) that has this value (ITEM_NO)

    for code, real_name in alias_map.items():
        if real_name == chosen_readable:
            actual_sql_col = code
            break
    return actual_sql_col


def build_sql_filtered(base_sql, actual_sql_col, target_item_ids):
    ids_string = "', '".join(target_item_ids)
    print(f"Filter applied on column (wrapped): {actual_sql_col}")

    return queries.FINAL_SQL.format(base_sql=base_sql, actual_sql_col=actual_sql_col,
                             ids_string=ids_string, MAX_ROWS_QUERY=MAX_ROWS_QUERY)


def filtering_column(products, columns, alias_map, base_sql, target_item_ids, cursor):
    """
    Main filtering function - tries injection first, falls back to wrapping.
    """
    print("\n" + "=" * 60 + f"\nTrying to identify the column for: {products}\n" + "=" * 60)

    # --- Try injection approach first ---
    if target_item_ids:
        # Skip injection for UNION queries - too risky (may only filter one part)
        if "UNION" in base_sql.upper():
            print("UNION detected - using fallback wrapper for safety.")
        else:
            injected_sql = optimize_sql(base_sql, target_item_ids, cursor)
            if injected_sql: return injected_sql

    # --- FALLBACK: wrapping approach ---
    return fallback_wrap_filter(base_sql, columns, alias_map, target_item_ids)


def optimize_sql(base_sql, target_item_ids, cursor):
    print("Attempting optimized filter injection...")
    injection_info = Ai.get_injection_point(base_sql)

    # Only need column - anchor is optional (null if no WHERE clause)
    if injection_info and injection_info.get("column"):
        has_where = injection_info.get("has_where", False)
        anchor = injection_info.get("anchor")
        print(f"AI found: column = {injection_info['column']}, has_where = {has_where}, anchor = "
              f"{anchor[:30] if anchor else 'None'}...")

        injected_sql = inject_filter(base_sql, injection_info, target_item_ids, cursor)

        if injected_sql:
            return injected_sql
        else:
            print("Injection failed, falling back to wrap approach.\n")
    return None


def executing_final_sql(cursor, final_query, columns, alias_map, doc_name):
    print("Executing Final SQL!")

    if utils.execute_safe_sql(cursor, final_query):
        try:
            data = cursor.fetchall()
            print(f"Rows returned: {len(data)}\n")

            # Use the actual description from the executed query if available
            raw_cols = [col[0] for col in cursor.description] if cursor.description else columns

            final_columns = []

            for col in raw_cols:
                final_columns.append(alias_map.get(col.upper(), col))

            if data:
                return {
                    "doc_name": doc_name,
                    "columns": final_columns,
                    "data": data
                }
        except Exception as e:
            print(f"Error during execution: {e}")
    return None


def get_all_ids(products, cursor):
    """
    Translates product names to Item IDs from Master Table.
    Returns:
        - None: No products specified (query ALL items - no filter needed)
        - []: Products specified but not found in DB (should abort)
        - [ids...]: Products found successfully
    """
    if not products:
        print("No specific products requested - will query all items.")
        return None  # None = "no filter", different from [] = "not found"

    print("\n" + "=" * 60 + "\nTranslating Product Names to Item IDs\n" + "=" * 60)
    target_item_ids = []
    for product in products:
        ids = get_product_numbers_from_db(cursor, product)
        target_item_ids.extend(ids)

    # remove duplicates
    target_item_ids = list(set(target_item_ids))

    if not target_item_ids:
        print(
            f"Could not find any valid Item IDs for product/s: {products}. Aborting data retrieval to save resources.")
        return []  # [] = products specified but not found
    return target_item_ids


def get_documents(intent):
    if connection is None:
        raise Exception("No connection to Oracle")
    cursor = connection.cursor()
    reports_object = get_reports_objects(cursor, intent)
    cursor.close()

    if reports_object is None:
        print("Could not get any reports!")
        return None

    object_name_idx = 4
    # Priority 1: Check for known documents
    known_docs = [
        report for report in reports_object if report[object_name_idx] in KNOWN_DOCUMENTS_NAME
    ]

    if known_docs:
        print(f"\nAuto-selecting {len(known_docs)} known document(s): {[d[object_name_idx] for d in known_docs]}")
        return known_docs

    # Priority 2: Only 1 report found
    if len(reports_object) == 1:
        print(f"\nOnly one report found: '{reports_object[0][object_name_idx]}'. Auto-selecting it.")
        return [reports_object[0]]

    # Priority 3: Multiple reports, let user choose
    if len(reports_object) > 1:
        print(
            "\n" + "=" * 60 + f"\nThere are {len(reports_object)} reports found, please choose what report you want!\n" + "=" * 60 + "\n")
        for index, report in enumerate(reports_object): utils.print_document(index, report)
        return utils.get_wanted_reports(reports_object)

    return []


def get_reports_objects(cursor, intent):
    """
    Looks where the data is, doesn't retrieve the data itself
    :param cursor:
    :param intent:
    :return: List of report objects as tuples
    """

    # Build bind variable placeholders dynamically to prevent SQL injection
    bind_names = [f":intent{i}" for i in range(len(intent))]
    like_conditions = " OR ".join([f"LOWER(d.doc_description) LIKE {name}" for name in bind_names])

    query = queries.ALL_REPORTS.format(like_conditions=like_conditions)

    bind_dict = {f"intent{i}": f"%{kw}%" for i, kw in enumerate(intent)}

    if not utils.execute_safe_sql(cursor, query, **bind_dict): return None
    info = cursor.fetchall()

    if not info:
        print("Did not find any data!")
        return None

    return info


def get_columns_names(table_name, cursor):
    query = queries.COLUMN_NAMES

    if utils.execute_safe_sql(cursor, query, table_name=table_name):
        columns_names = [row[0] for row in cursor.fetchall()]
        print(f"Column Names: {columns_names}")
        return columns_names

    print("Failed to retrieve columns (Validation or DB Error).")
    return []


def get_known_sql(cursor, obj_id, obj_name):
    """
    Looks where the seg_chunks are. Then merges all the chunks, and then retrieves the
     whole existing SQL.
    :param cursor:
    :param obj_id:
    :param obj_name:
    :return:
    """
    query = queries.GET_CHUNKS

    if not utils.execute_safe_sql(cursor, query, obj_id=obj_id): return None
    chunks = cursor.fetchall()

    if not chunks:
        print("No segments found! No SQL was found!")
        return None

    print(f"An existing SQL was found for obj_name({obj_name})!")
    sql_combined = []
    for row in chunks:
        sql_combined.extend([chunk for chunk in row if chunk])

    full_sql = "".join(sql_combined)
    return utils.unwrap_discoverer_sql(full_sql)


def map_aliases_to_real_names(cursor, sql_query):
    """
    Finds all i* aliases in SQL and looks up real names from EUL5_EXPRESSIONS.
    Returns a dictionary mapping aliases to real column names.
    """
    if not sql_query: return {}

    # Find all i12345 patterns
    aliases = re.findall(r'\bi(\d+)\b', sql_query)
    unique_ids = list(set(aliases))
    if not unique_ids: return {}
    ids_str = ", ".join(unique_ids)

    query = queries.GET_REAL_NAMES.format(ids_str=ids_str)

    utils.execute_safe_sql(cursor, query)
    results = cursor.fetchall()

    return create_map(results)


def create_map(results):
    alias_map = {}
    for row in results:
        exp_id = str(row[0])
        real_name = row[1].upper().replace(' ', '_')
        alias_map[f'I{exp_id}'] = real_name

    return alias_map


def get_product_numbers_from_db(cursor, product):
    print(f"- Checking Master Table for: '{product}'")

    query = queries.GET_PRODUCTS_NAMES

    term_pattern = f"%{product.upper()}%"

    try:
        # Utilizing the safe execution wrapper
        if not utils.execute_safe_sql(cursor, query, term=term_pattern):
            print("Did not find any item numbers!")
            return []

        results = [row[0] for row in cursor.fetchall()]

        if results:
            print(f"Found {len(results)} matching Item Numbers: {results[:5]}" + ("..." if len(results) > 5 else ""))
        else:
            print(f"No items found in Master Table for '{product}'")

        return results

    except Exception as e:
        print(f"Error querying Master Table: {e}")
        return []
