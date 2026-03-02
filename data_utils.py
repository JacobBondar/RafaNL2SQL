"""
Pure data transformation functions for NL2SQL system.

This module contains data processing logic without AI, database, or side effects.
Used by both AI_Communication and intent_handlers to avoid circular dependencies.
"""

from datetime import datetime
from config import (
    PRODUCT_PATTERNS, QUANTITY_PATTERNS, SUBINVENTORY_PATTERNS,
    LOCATOR_PATTERNS, LOT_PATTERNS, ORG_PATTERNS, UOM_PATTERNS,
    DESCRIPTION_PATTERNS, RELEVANT_COLUMN_PATTERNS, EXCLUDED_ORGANIZATIONS
)

def add_expire_flag(data, columns):
    """
    Adds a virtual 'EXPIRE_FLAG' column based on EXPIRE_DATE.
    If EXPIRE_DATE < today → 'Y' (expired), else → 'N'.
    Returns (enriched_data, enriched_columns).
    """
    if not data or not columns:
        return data, columns

    # Find EXPIRE_DATE column index
    expire_idx = -1
    for i, col in enumerate(columns):
        col_upper = col.upper()
        if 'EXPIR' in col_upper and 'DATE' in col_upper:
            expire_idx = i
            break

    # No expire date column found - return as-is
    if expire_idx == -1: return data, columns

    # Add new column
    enriched_columns = list(columns) + ['EXPIRE_FLAG']
    enriched_data = []
    today = datetime.now()

    for row in data:
        add_flag_row(row, expire_idx, today, enriched_data)

    return enriched_data, enriched_columns

def add_flag_row(row, expire_idx, today, enriched_data):
    row_list = list(row)  # Convert tuple to list
    expire_date = row[expire_idx] if expire_idx < len(row) else None

    # Calculate flag
    if expire_date and expire_date < today: flag = 'Y'
    else: flag = 'N'

    row_list.append(flag)
    enriched_data.append(tuple(row_list))

def find_column_index(columns, patterns):
    """
    Find the index of a column that matches any of the given patterns.
    Returns the first match index, or -1 if not found.
    """
    if not columns:
        return -1
    for idx, col in enumerate(columns):
        col_upper = col.upper()
        if col_upper.endswith("_ID") and "ID" not in str(patterns).upper():
            continue

        for pattern in patterns:
            if pattern in col_upper:
                return idx
    return -1

def parse_date_filter(date_filter):
    """
    Parse date_filter dict into datetime objects.
    Returns (date_start, date_end) tuple. Either can be None if parsing fails.

    IMPORTANT: For end dates, if only date is provided (no time), the time is set
    to 23:59:59 to include the entire day. This prevents filtering out transactions
    that occur after midnight on the end date.
    """
    if not date_filter:
        return None, None

    date_start = None
    date_end = None

    try:
        start_str = date_filter.get('start', '')
        end_str = date_filter.get('end', '')

        if start_str:
            date_start = _parse_datetime(start_str, is_end_date=False)
        if end_str:
            date_end = _parse_datetime(end_str, is_end_date=True)
    except Exception as e:
        print(f"Warning: Could not parse date_filter: {e}")

    return date_start, date_end


def _parse_datetime(date_str, is_end_date=False):
    """
    Parse a date/datetime string into a datetime object.

    Args:
        date_str: String in format "DD/MM/YYYY" or "DD/MM/YYYY HH:MM:SS"
        is_end_date: If True and no time provided, set time to 23:59:59

    Returns:
        datetime object or None if parsing fails
    """
    if not date_str:
        return None

    # Try full datetime format first (DD/MM/YYYY HH:MM:SS)
    try:
        return datetime.strptime(date_str, "%d/%m/%Y %H:%M:%S")
    except ValueError:
        pass

    # Try date-only format (DD/MM/YYYY)
    try:
        parsed = datetime.strptime(date_str.split()[0], "%d/%m/%Y")
        # For end dates, set time to end of day to include entire day
        if is_end_date:
            parsed = parsed.replace(hour=23, minute=59, second=59)
        return parsed
    except ValueError:
        pass

    return None

def is_date_in_range(date_value, date_start, date_end):
    """
    Check if a date value falls within the specified range.
    Returns True if in range, False otherwise.
    Handles datetime objects and None values gracefully.
    """
    if date_value is None:
        return False

    # Ensure date_value is a datetime
    if not hasattr(date_value, 'year'):
        return False  # Not a datetime object

    # Check range (inclusive)
    if date_start and date_value < date_start:
        return False
    if date_end and date_value > date_end:
        return False

    return True

def get_column_indices_patterns_only(columns):
    """
    Get column indices using pattern matching ONLY.
    Returns dict with indices for: product, qty, sub, loc, lot, org, uom, desc
    Uses -1 for columns that couldn't be found.
    """
    return {
        'product': find_column_index(columns, PRODUCT_PATTERNS),
        'qty': find_column_index(columns, QUANTITY_PATTERNS),
        'sub': find_column_index(columns, SUBINVENTORY_PATTERNS),
        'loc': find_column_index(columns, LOCATOR_PATTERNS),
        'lot': find_column_index(columns, LOT_PATTERNS),
        'org': find_column_index(columns, ORG_PATTERNS),
        'uom': find_column_index(columns, UOM_PATTERNS),
        'desc': find_column_index(columns, DESCRIPTION_PATTERNS)
    }

def filter_relevant_columns(columns, rows):
    """
    Filter columns and rows to only include relevant columns for AI summarization.
    Returns (filtered_columns, filtered_rows)
    """
    if not columns:
        return columns, rows

    # Find indices of relevant columns
    relevant_indices = []
    filtered_columns = []

    for idx, col in enumerate(columns):
        col_upper = col.upper()
        # Check if column matches any relevant pattern
        for pattern in RELEVANT_COLUMN_PATTERNS:
            if pattern in col_upper or col_upper in pattern:
                relevant_indices.append(idx)
                filtered_columns.append(col)
                break

    # If no relevant columns found, return original (fallback)
    if not relevant_indices:
        return columns, rows

    # Filter rows to only include relevant columns
    filtered_rows = []
    for row in rows:
        filtered_row = [row[i] for i in relevant_indices if i < len(row)]
        filtered_rows.append(filtered_row)

    return filtered_columns, filtered_rows

def build_group_key(product_id, row, indices, group_fields, direct_col_indices):
    """
    Build aggregation key as formatted string.
    Example: "346501 | WMS | LOT123"

    Args:
        product_id: The product identifier
        row: The data row
        indices: Column indices dict from get_column_indices_patterns_only
        group_fields: List of field keys from GROUP_BY_MAPPING (e.g., ['lot', 'sub'])
        direct_col_indices: List of column indices for AI-matched columns

    Returns:
        String key like "346501 | WMS | LOT123" or just product_id if no grouping
    """
    # No grouping at all
    if not group_fields and not direct_col_indices:
        return product_id

    key_parts = [product_id]

    # Mode 1: Known mapping fields (e.g., 'lot', 'sub' from GROUP_BY_MAPPING)
    if group_fields:
        for field in group_fields:
            idx = indices.get(field, -1)
            if idx != -1 and idx < len(row) and row[idx]:
                val = str(row[idx]).strip()
                if val:
                    key_parts.append(val)

    # Mode 2: Direct column indices (from AI semantic matching)
    if direct_col_indices:
        for col_idx in direct_col_indices:
            if col_idx != -1 and col_idx < len(row) and row[col_idx]:
                val = str(row[col_idx]).strip()
                if val:
                    key_parts.append(val)

    return " | ".join(key_parts)  # String key, not tuple!

def find_column_pos(wanted_columns, columns):
    col_idx = -1
    if wanted_columns:
        for i, col in enumerate(columns):
            if col.upper() == wanted_columns.upper():
                col_idx = i
                break
    return col_idx

def is_excluded_org(row, org_idx, excluded_orgs):
    """Check if row belongs to a test organization that should be excluded."""
    if org_idx == -1 or org_idx >= len(row):
        return False  # No org column - don't filter
    org_value = row[org_idx]
    if org_value is None:
        return False
    return str(org_value).strip().upper() in excluded_orgs

def is_filtered(row, product_idx, all_items, date_start, date_end, expire_date_idx,
                filter_col_idx, filter_value, org_idx=-1, excluded_orgs=None):
    # Filter out test organizations first
    if excluded_orgs and is_excluded_org(row, org_idx, excluded_orgs):
        return True

    current_item = str(row[product_idx]).strip()
    if all_items and current_item not in all_items: return True
    if not current_item or current_item.lower() == 'none': return True

    # Apply date_filter first (if specified) - filter by EXPIRE_DATE range
    if date_start or date_end:
        if expire_date_idx == -1: return True
        expire_date = row[expire_date_idx]
        if not is_date_in_range(expire_date, date_start, date_end): return True

    # Apply filter_condition if specified (e.g., only expired items)
    if filter_value and filter_col_idx != -1:
        cell_value = str(row[filter_col_idx]).strip().upper()
        target_value = str(filter_value).strip().upper()

        if cell_value != target_value: return True

    return False

def calc_values(product_stats, row, agg_key, qty_val, sub_val , loc_val , lot_val,
                org_val, uom_idx, desc_idx):
    # Initialize entry if needed
    if agg_key not in product_stats:
        product_stats[agg_key] = {
            'total_qty': 0,
            'locations': set(),
            'lots': set(),
            'orgs': set(),
            'uom': None,
            'description': None,
            'rows_count': 0
        }

    stats = product_stats[agg_key]
    stats['rows_count'] += 1
    stats['total_qty'] += qty_val

    # Store combined location (e.g., "ILCH-APP")
    full_location = f"{sub_val}-{loc_val}".strip('-')
    if full_location: stats['locations'].add(full_location)

    # Collect lot
    if lot_val: stats['lots'].add(lot_val)

    # Collect org
    if org_val: stats['orgs'].add(org_val)

    # Get UOM (take first non-null)
    if uom_idx != -1 and row[uom_idx] and not stats['uom']:
        stats['uom'] = str(row[uom_idx])

    # Get description (take first non-null)
    if desc_idx != -1 and row[desc_idx] and not stats['description']:
        stats['description'] = str(row[desc_idx])

def create_empty_items(product_stats, all_items):
    for requested_item in all_items:
        if requested_item in product_stats: continue

        product_stats[requested_item] = {
            'total_qty': 0,
            'locations': [],
            'lots': [],
            'orgs': [],
            'uom': 'N/A',
            'description': 'Not found in inventory',
            'rows_count': 0
        }

def handle_row(product_idx, row, indices, all_items, filter_value, seen_signatures,
               group_fields, product_stats, date_start, date_end, expire_date_idx,
               filter_col_idx, direct_col_indices):
    if product_idx >= len(row): return

    qty_idx = indices['qty'] if indices['qty'] < len(row) else -1
    sub_idx = indices['sub'] if indices['sub'] < len(row) else -1 # Subinventory (warehouse section)
    loc_idx = indices['loc'] if indices['loc'] < len(row) else -1 # Locator (specific bin/rack)
    lot_idx = indices['lot'] if indices['lot'] < len(row) else -1 # batch
    org_idx = indices['org'] if indices['org'] < len(row) else -1
    uom_idx = indices['uom'] if indices['uom'] < len(row) else -1
    desc_idx = indices['desc'] if indices['desc'] < len(row) else -1

    if is_filtered(row, product_idx, all_items, date_start, date_end, expire_date_idx,
        filter_col_idx, filter_value,
        org_idx=org_idx, excluded_orgs=EXCLUDED_ORGANIZATIONS): return

    # Extract values for dedup key
    current_item = str(row[product_idx]).strip()
    org_val = str(row[org_idx]).strip() if (org_idx != -1 and row[org_idx]) else ''
    lot_val = str(row[lot_idx]).strip() if (lot_idx != -1 and row[lot_idx]) else ''
    sub_val = str(row[sub_idx]).strip() if (sub_idx != -1 and row[sub_idx]) else ''
    loc_val = str(row[loc_idx]).strip() if (loc_idx != -1 and row[loc_idx]) else ''
    try:
        qty_val = float(row[qty_idx]) if (qty_idx != -1 and row[qty_idx]) else 0.0
    except:
        qty_val = 0.0

    # Build unique signature including quantity (duplicate rows have same qty)
    row_signature = (current_item, org_val, lot_val, sub_val, loc_val, qty_val)
    # Skip if we've already processed this exact row
    if row_signature in seen_signatures: return
    seen_signatures.add(row_signature)

    # Build the aggregation key (string format like "346501 | WMS | LOT123")
    agg_key = build_group_key(current_item, row, indices, group_fields, direct_col_indices)

    calc_values(product_stats, row, agg_key, qty_val, sub_val , loc_val , lot_val,
                org_val, uom_idx, desc_idx)

def handle_report(report, group_by_columns, filter_column, date_filter,
                  all_items, filter_value, seen_signatures, group_fields, product_stats,
                  empty_reports):
    """
    Process a single report, extracting and aggregating data.

    Args:
        report: Dict with 'columns', 'data', 'doc_name'
        group_by_columns: List of column names for AI-matched groupings
        filter_column: Column name to filter on
        date_filter: Dict with 'start' and 'end' for date range
        all_items: Set of item IDs to filter for
        filter_value: Value to filter for
        seen_signatures: Set to track unique rows (for deduplication)
        group_fields: List of field keys from GROUP_BY_MAPPING (e.g., ['lot', 'sub'])
        product_stats: Dict to accumulate results
        empty_reports: List to track reports with no data
    """
    columns = report.get('columns', [])
    data_rows = report.get('data', [])

    if not data_rows:
        doc_name = report.get('doc_name', 'Unknown Report')
        empty_reports.append(doc_name)
        return

    # Get column indices (pattern matching only)
    indices = get_column_indices_patterns_only(columns)

    # Convert group_by_columns (list of column names) to list of indices
    direct_col_indices = []
    if group_by_columns:
        for col_name in group_by_columns:
            col_idx = find_column_pos(col_name, columns)
            if col_idx != -1:
                direct_col_indices.append(col_idx)

    filter_col_idx = find_column_pos(filter_column, columns)

    # Find EXPIRE_DATE column index and parse date range
    expire_date_idx = find_column_index(columns, ['EXPIRE_DATE', 'EXPIRY_DATE', 'EXPIRATION_DATE'])
    date_start, date_end = parse_date_filter(date_filter)

    product_idx = indices['product']

    # If no product column found, skip this report
    if product_idx == -1: return

    for row in data_rows:
        handle_row(product_idx, row, indices, all_items, filter_value, seen_signatures,
               group_fields, product_stats, date_start, date_end, expire_date_idx,
               filter_col_idx, direct_col_indices)

def aggregate_by_product(data_results, filter_items=None, group_by_fields=None, group_by_columns=None,
                        filter_column=None, filter_value=None, date_filter=None):
    """
    Pre-compute product statistics in Python.
    Returns a dict: {key: {total_qty, locations, lots, orgs, uom, rows_count}}

    Key is a formatted string like "346501 | WMS | LOT123" when grouping is specified,
    or just product_id when no grouping.

    Supports two grouping modes (can be combined):
    - group_by_fields: List of field keys from GROUP_BY_MAPPING (e.g., ['lot', 'sub'])
    - group_by_columns: List of column names from AI semantic matching (e.g., ['EXPIRE_DATE'])

    Supports filtering:
    - filter_column: Column name to filter on (e.g., 'EXPIRE_FLAG')
    - filter_value: Value to filter for (e.g., 'Y' for expired)
    - date_filter: Dict with 'start' and 'end' for date range filtering on EXPIRE_DATE

    Deduplicates by (product, org, lot, subinventory, locator, qty) to ensure
    identical rows from duplicate reports are counted only once.
    """
    product_stats = {}
    seen_signatures = set()  # Track unique row signatures
    empty_reports = []  # Track reports with no data
    all_items = set(str(item).strip() for item in filter_items) if filter_items else None
    group_fields = group_by_fields if group_by_fields else []

    # Track if any grouping is active for format_aggregated_stats
    has_grouping = bool(group_fields or group_by_columns)

    for report in data_results:
        handle_report(report, group_by_columns, filter_column, date_filter,
                      all_items, filter_value, seen_signatures, group_fields, product_stats,
                      empty_reports)

    # Handle missing items (only when no grouping - can't know group values for missing items)
    if all_items and not group_fields and not group_by_columns:
        create_empty_items(product_stats, all_items)

    # Convert sets to lists for JSON serialization
    for key, stats in product_stats.items():
        stats['locations'] = list(stats['locations'])
        stats['lots'] = list(stats['lots'])
        stats['orgs'] = list(stats['orgs'])

    return {'products': product_stats, 'has_grouping': has_grouping, 'empty_reports': empty_reports}

def format_aggregated_stats(aggregated_data):
    """
    Format the pre-computed stats into a simple text for AI.
    All numbers are already calculated - AI just needs to format in Hebrew.

    Keys are now formatted strings like "346501 | WMS | LOT123" when grouping is used.
    The key contains the product_id followed by group values separated by " | ".
    """
    products = aggregated_data.get('products', {})
    has_grouping = aggregated_data.get('has_grouping', False)
    empty_reports = aggregated_data.get('empty_reports', [])

    if not products:
        return "NO_DATA_FOUND"

    lines = []
    zero_stock_items = []  # Collect items with no stock

    # Add header to signal AI this is a breakdown
    if has_grouping:
        lines.append("BREAKDOWN BY MULTIPLE COLUMNS:")

    for key, stats in products.items():
        # Key is now a string like "346501 | WMS | PRD"
        # Split to get product_id and group values separately
        key_parts = str(key).split(' | ')
        product_id = key_parts[0]
        group_values = key_parts[1:] if len(key_parts) > 1 else []

        qty = stats.get('total_qty', 0)

        # Collect zero-stock items separately (don't list each one)
        if qty == 0:
            zero_stock_items.append(product_id)
            continue

        desc = f" ({stats['description']})" if stats.get('description') else ""
        uom = stats.get('uom') or "יחידות"

        # Format quantity nicely (no decimals if whole number)
        qty_str = f"{int(qty)}" if qty == int(qty) else f"{qty:.2f}"

        # Build line with explicit group values
        line = f"- Product: {product_id}{desc}"
        if group_values:
            # CRITICAL: Show ALL group values explicitly so AI doesn't drop any
            groups_str = " | ".join(group_values)
            line += f", GroupBy: [{groups_str}]"
        line += f", Quantity: {qty_str} {uom}"

        # Only add extra info if NOT doing a breakdown (avoid redundancy)
        if not has_grouping:
            if stats.get('locations'):
                line += f", Locations: {', '.join(stats['locations'])}"
            if stats.get('lots'):
                lots_list = stats['lots']
                if len(lots_list) <= 5:
                    line += f", Lots: {', '.join(lots_list)}"
                else:
                    line += f", Lots: {len(lots_list)} (Too many to list)"
            if stats.get('orgs'):
                line += f", Orgs: {', '.join(stats['orgs'])}"

        lines.append(line)

    # Add summary for zero-stock items instead of listing each one
    if zero_stock_items:
        # Deduplicate since same product might appear with different groupings
        unique_zero = list(set(zero_stock_items))
        lines.append(f"\nZERO STOCK COUNT: {len(unique_zero)} items have no stock")

    if empty_reports:
        lines.append("\nEmpty Reports (No data found in):")
        for report_name in empty_reports:
            lines.append(f"- {report_name}")

    return "\n".join(lines)

# Not usable, but it has great potential (If the user wants to see the data as is)
# def format_data_for_ai(data_results):
#     """
#     Convert the whole data to a readable format.
#     """
#     formatted_text = ""
#
#     for i, item in enumerate(data_results):
#         doc_name = item.get('doc_name', 'Unknown Report')
#         rows = item.get('data', [])
#         columns = item.get('columns', [])
#
#         # Filter to only relevant columns
#         columns, rows = filter_relevant_columns(columns, rows)
#
#         formatted_text += f"\n--- Report #{i + 1}: {doc_name} ---\n"
#
#         if columns:
#             formatted_text += f"Columns: {', '.join(columns)}\n"
#
#         if not rows:
#             formatted_text += "No data found in this report.\n"
#             continue
#
#         formatted_text += "Data Rows:\n"
#
#         for row in rows:
#             if columns and len(columns) == len(row):
#                 row_str = " | ".join([f"{col}: {val}" for col, val in zip(columns, row)])
#                 formatted_text += f"- {row_str}\n"
#             else:
#                 formatted_text += f"- {str(row)}\n"
#
#     return formatted_text