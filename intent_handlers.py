"""
Intent-specific processing logic using function dispatch pattern.

Each handler function processes data for a specific intent (inventory, transactions, sales, etc.)
and returns a standardized result dict for AI summarization.
"""

import data_utils as du
import AI_Communication as ai
from datetime import datetime
from config import GROUP_BY_KEYWORDS_HEBREW, GROUP_BY_MAPPING, EXCLUDED_ORGANIZATIONS

TRANSACTION_LENGTH = 20


def resolve_group_by(group_by_description, columns):
    """
    Resolves user's grouping description to actual column name(s).

    Hybrid approach:
    1. Fast path: Check GROUP_BY_KEYWORDS_HEBREW for known mappings
    2. Slow path: Use AI semantic matching for unknown descriptions

    Args:
        group_by_description: Raw Hebrew description (e.g., "מיקום", "סוג מכירה")
        columns: List of actual column names from the report

    Returns:
        Tuple of (group_by_key, column_name) where:
        - group_by_key is for GROUP_BY_MAPPING lookup (or None if AI-matched)
        - column_name is the actual column to group by (or None if no match)
    """

    # Fast path: check known mappings first
    known_key = GROUP_BY_KEYWORDS_HEBREW.get(group_by_description)
    if known_key:
        print(f"Fast path: '{group_by_description}' -> known mapping '{known_key}'")
        return known_key, None  # Use existing GROUP_BY_MAPPING logic

    # Slow path: use AI semantic matching
    print(f"Slow path: Using AI to match '{group_by_description}' against columns...")
    matched_column = ai.match_column_semantic(group_by_description, columns)

    if matched_column:
        print(f"AI matched '{group_by_description}' -> column '{matched_column}'")
        return None, matched_column  # Direct column name

    print(f"No match found for '{group_by_description}'")
    return None, None


def resolve_multiple_group_by(group_by_descriptions, columns):
    """
    Resolves multiple grouping descriptions to combined field list.

    Args:
        group_by_descriptions: List of Hebrew descriptions (e.g., ["אצווה", "מחסן"])
        columns: List of actual column names from the report

    Returns:
        Tuple of (combined_group_fields, direct_columns) where:
        - combined_group_fields: List of field keys from GROUP_BY_MAPPING (e.g., ['lot', 'sub'])
        - direct_columns: List of AI-matched column names for unknown descriptions
    """
    if not group_by_descriptions:
        return [], []

    combined_fields = []
    direct_columns = []

    for desc in group_by_descriptions:
        # Fast path: check known mappings first
        known_key = GROUP_BY_KEYWORDS_HEBREW.get(desc)
        if known_key:
            # Get fields from GROUP_BY_MAPPING (e.g., 'location' -> ['sub', 'loc'])
            fields = GROUP_BY_MAPPING.get(known_key, [])
            combined_fields.extend(fields)
            print(f"Fast path: '{desc}' -> known mapping '{known_key}' -> fields {fields}")
        else:
            # Slow path: use AI semantic matching
            print(f"Slow path: Using AI to match '{desc}' against columns...")
            matched_column = ai.match_column_semantic(desc, columns)
            if matched_column:
                direct_columns.append(matched_column)
                print(f"AI matched '{desc}' -> column '{matched_column}'")
            else:
                print(f"No match found for '{desc}'")

    return combined_fields, direct_columns


def process_inventory_logic(data_tables, searched_items, group_by_descriptions=None,
                            filter_condition=None, date_filter=None):
    """
    מלאי - Aggregates quantities, shows current stock.

    :param data_tables: List of dicts with 'doc_name', 'columns', 'data' keys
    :param searched_items: List of item IDs user asked about
    :param group_by_descriptions: List of Hebrew grouping descriptions (e.g., ["אצווה", "מחסן"])
    :param filter_condition: Dict with 'column_desc' and 'value' for filtering (e.g., {"column_desc": "פג תוקף", "value": "Y"})
    :param date_filter: Dict with 'start' and 'end' for date range filtering on EXPIRE_DATE
    :return: Dict with keys: 'type', 'data', 'count'
    """

    # DEBUG
    debug_inventory_logic(data_tables)

    # Get columns from first report (they should all have same structure)
    columns = data_tables[0].get('columns', []) if data_tables else []
    print(f"\nAvailable columns: {columns}\n")

    # Resolve group_by_descriptions to actual columns/fields
    # Returns: (combined_fields, direct_columns)
    # combined_fields: list of field keys like ['lot', 'sub'] from GROUP_BY_MAPPING
    # direct_columns: list of column names from AI semantic matching
    group_fields = []
    direct_columns = []

    if group_by_descriptions:
        group_fields, direct_columns = resolve_multiple_group_by(group_by_descriptions, columns)
        print(f"Resolved groupings: fields={group_fields}, direct_columns={direct_columns}")

    # Resolve filter_condition to actual column and value
    filter_column = None
    filter_value = None

    if filter_condition:
        filter_column, filter_value = get_filters(filter_condition, columns)

    # Log date_filter if present
    if date_filter:
        print(f"Date filter: start={date_filter.get('start')}, end={date_filter.get('end')}")

    # Pass resolved grouping, filtering, and date_filter to aggregation function
    aggregated = du.aggregate_by_product(
        data_tables,
        searched_items,
        group_by_fields=group_fields,
        group_by_columns=direct_columns,
        filter_column=filter_column,
        filter_value=filter_value,
        date_filter=date_filter
    )
    stats_text = du.format_aggregated_stats(aggregated)

    items_str = ", ".join(searched_items) if searched_items else "Items"
    hebrew_result = ai.format_inventory_hebrew(f"Check inventory for {items_str}", stats_text)

    return {
        'type': 'inventory',
        'data': hebrew_result,
        'count': len(aggregated.get('products', {})),
        'raw_data': aggregated.get('products', {}),
        'columns': columns
    }

def get_filters(filter_condition, columns):
    filter_column = None
    filter_desc = filter_condition.get('column_desc')
    filter_value = filter_condition.get('value')

    if filter_desc and filter_value:
        # Try to resolve to actual column name
        filter_key, filter_col = resolve_group_by(filter_desc, columns)

        if filter_col:
            # Slow path returned actual column name
            filter_column = filter_col
        elif filter_key:
            # Fast path returned key like 'subinventory' - need to find actual column
            # Use GROUP_BY_MAPPING to get index field, then find column
            field_keys = GROUP_BY_MAPPING.get(filter_key, [])
            if field_keys:
                indices = du.get_column_indices_patterns_only(columns)
                first_field = field_keys[0]  # e.g., 'sub' for subinventory
                col_idx = indices.get(first_field, -1)
                if col_idx != -1 and col_idx < len(columns):
                    filter_column = columns[col_idx]

        print(f"Filter condition: column={filter_column}, value={filter_value}")
    return filter_column, filter_value

def debug_inventory_logic(data_tables):
    print("The inventory data:")
    row_count = 0
    max_rows_to_print = 20

    for data in data_tables:
        print(f"--- Table: {data.get('doc_name', 'Unknown')} ---")
        for d in data['data']:
            if row_count < max_rows_to_print:
                print(d)
                row_count += 1
            else:
                print("... (Stopping debug print after 20 rows)")
                return

def process_transactions_logic(data_tables, searched_items, group_by=None,
                               filter_condition=None, date_filter=None):
    """
    תנועות - Shows chronological list (last 20 movements).
    Sorts 5000 rows in Python to ensure accurate latest data.

    :param data_tables: List of dicts with 'doc_name', 'columns', 'data' keys
    :param searched_items: List of item IDs user asked about
    :param group_by: Not used for transactions (signature match for dispatch)
    :param filter_condition: Not used for transactions (signature match for dispatch)
    :param date_filter: Dict with 'start' and 'end' for date range filtering
    :return: Dict with keys: 'type', 'data', 'count'
    """

    transactions = []

    # Parse date filter once (outside the loop)
    date_start, date_end = du.parse_date_filter(date_filter)
    if date_filter:
        print(f"Date filter active: {date_start} to {date_end}")

    # DEBUG: Print sample of transaction data
    print("\n=== DEBUG: Transaction Data Sample ===")
    for report in data_tables:
        print(f"Report: {report.get('doc_name', 'Unknown')}")
        print(f"Columns: {report.get('columns', [])}")
        sample_rows = report.get('data', [])[:5]  # First 5 rows
        for i, row in enumerate(sample_rows):
            print(f"  Row {i}: {row}")
    print("=== END DEBUG ===\n")

    for report in data_tables:
        columns = report.get('columns', [])
        rows = report.get('data', [])

        # Find column indices using data_utils

        indices = du.get_column_indices_patterns_only(columns)
        date_idx = du.find_column_index(columns, ['DATE', 'TRANSACTION_DATE', 'GL_DATE', 'TRANS_DATE'])
        type_idx = du.find_column_index(columns, ['SOURCE', 'TRANSACTION_TYPE', 'TYPE', 'DOC_TYPE'])

        if date_idx == -1 and len(columns) > 1 and 'SOURCE' in columns[0].upper():
            date_idx = 1

        product_idx = indices.get('product', -1)
        qty_idx = indices.get('qty', -1)
        sub_idx = indices.get('sub', -1)
        loc_idx = indices.get('loc', -1)
        lot_idx = indices.get('lot', -1)

        for row in rows:
            if product_idx == -1 or product_idx >= len(row):
                continue

            item_id = str(row[product_idx]).strip()

            # Skip test organizations
            org_idx = indices.get('org', -1)
            if du.is_excluded_org(row, org_idx, EXCLUDED_ORGANIZATIONS):
                continue

            # Filter by date range if specified
            if date_start or date_end:
                raw_date = row[date_idx] if date_idx != -1 and date_idx < len(row) else None
                if raw_date is None:
                    continue  # Skip rows without dates when filtering

                # Parse the date (handle both datetime objects and strings)
                if hasattr(raw_date, 'year'):
                    row_date = raw_date
                else:
                    # Try to parse string date
                    row_date = None
                    date_str = str(raw_date).strip()
                    for fmt in ["%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y %H:%M:%S"]:
                        try:
                            row_date = datetime.strptime(date_str.split()[0], fmt.split()[0])
                            break
                        except:
                            pass
                    if row_date is None:
                        continue  # Can't parse date, skip row

                # Apply date range filter
                if date_start and row_date < date_start:
                    continue
                if date_end and row_date > date_end:
                    continue

            transaction = {
                'date': row[date_idx] if date_idx != -1 and date_idx < len(row) else None,
                'type': row[type_idx] if type_idx != -1 and type_idx < len(row) else 'Unknown',
                'item': item_id,
                'qty': row[qty_idx] if qty_idx != -1 and qty_idx < len(row) else 0,
                'subinventory': row[sub_idx] if sub_idx != -1 and sub_idx < len(row) else '',
                'locator': row[loc_idx] if loc_idx != -1 and loc_idx < len(row) else '',
                'lot': row[lot_idx] if lot_idx != -1 and lot_idx < len(row) else ''
            }
            transactions.append(transaction)

    def smart_parse_date(t):
        raw_date = t.get('date')
        if not raw_date: return datetime.min

        if hasattr(raw_date, 'year'): return raw_date

        s_date = str(raw_date).strip()
        try: return datetime.strptime(s_date, "%d/%m/%Y")
        except: pass
        try: return datetime.strptime(s_date, "%Y-%m-%d")
        except: pass
        try: return datetime.strptime(s_date, "%d-%m-%Y")
        except: pass

        return datetime.min

    # Sort by date DESC, take last 20
    transactions.sort(key=smart_parse_date, reverse=True)
    transactions = transactions[:TRANSACTION_LENGTH]

    # Format for AI
    lines = []
    for t in transactions:
        raw_date = t['date']
        if raw_date:
            if hasattr(raw_date, 'strftime'):
                date_str = raw_date.strftime('%Y-%m-%d')
            else:
                date_str = str(raw_date)[:10]
        else:
            date_str = 'Unknown Date'

        location = f"{t['subinventory']}-{t['locator']}".strip('-')
        lines.append(
            f"- {date_str}: {t['type']}, Item {t['item']}, "
            f"Qty {t['qty']}, Location {location}, Lot {t['lot']}"
        )

    transactions_text_english = "\n".join(lines)
    items_str = ", ".join(searched_items) if searched_items else "Items"
    hebrew_result = ai.format_transactions_hebrew(f"Show transactions for {items_str}", transactions_text_english)

    return {
        'type': 'transactions',
        'data': hebrew_result,
        'count': len(transactions),
        'raw_data': transactions
    }

def process_sales_logic(data_tables, searched_items, group_by=None, filter_condition=None, date_filter=None):
    """
    מכירות - PLACEHOLDER for future sales logic.

    Args:
        data_tables: List of dicts with 'doc_name', 'columns', 'data' keys
        searched_items: List of item IDs user asked about
        group_by: Not used yet (signature match for dispatch)
        filter_condition: Not used yet (signature match for dispatch)
        date_filter: Not used yet (signature match for dispatch)

    Returns:
        Dict with keys: 'type', 'data', 'count'
    """
    return {
        'type': 'sales',
        'data': 'Sales logic not implemented yet',
        'count': 0
    }

def process_procurement_logic(data_tables, searched_items, group_by=None, filter_condition=None, date_filter=None):
    """
    רכש - PLACEHOLDER for future procurement logic.

    Args:
        data_tables: List of dicts with 'doc_name', 'columns', 'data' keys
        searched_items: List of item IDs user asked about
        group_by: Not used yet (signature match for dispatch)
        filter_condition: Not used yet (signature match for dispatch)

    Returns:
        Dict with keys: 'type', 'data', 'count'
    """
    return {
        'type': 'procurement',
        'data': 'Procurement logic not implemented yet',
        'count': 0
    }

# The magic dictionary - function dispatch
# Maps intent keywords to handler functions
INTENT_HANDLERS = {
    'מלאי': process_inventory_logic,
    'תנועות': process_transactions_logic,
    'מכירות': process_sales_logic,
    'רכש': process_procurement_logic,
}