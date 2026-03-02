# config.py - Column patterns and constants for NL2SQL
# Add new patterns here when you encounter unrecognized column names

# --- AI Model ---
OLLAMA_MODEL = "gpt-oss:20b"

# --- AI Formatting Limits (to prevent hallucination on large datasets) ---
AI_FORMAT_MAX_ITEMS = 30      # Max products before switching to manual format
AI_FORMAT_MAX_CHARS = 1200    # Max stats_text length (~750 tokens)

# --- Query Limits ---
MAX_ROWS_QUERY = 5000         # Max rows per SQL query (prevents runaway queries)

# --- SQL Security ---
# Keywords that are forbidden in SQL queries (read-only enforcement)
FORBIDDEN_SQL_KEYWORDS = [
    # Data Manipulation
    "INSERT", "UPDATE", "DELETE", "MERGE",
    # Structure Manipulation
    "DROP", "CREATE", "ALTER", "TRUNCATE", "RENAME", "COMMENT",
    # Permissions
    "GRANT", "REVOKE",
    # Transaction Management
    "COMMIT", "ROLLBACK", "SAVEPOINT", "SET TRANSACTION",
    # Oracle Specifics
    "EXEC", "EXECUTE", "CALL",  # Running Procedures
    "DECLARE", "BEGIN",         # PL/SQL Blocks
    "LOCK",                     # Table Lock
    "FOR UPDATE"                # Rows Lock
]

# --- Column Identification Patterns ---
# These are used to identify columns by name (case-insensitive matching)

PRODUCT_PATTERNS = [
    'ITEM_NO', 'ITEM_NUMBER', 'SEGMENT1', 'ITEM_CODE', r'^ITEM$',
    'PART_NUMBER', 'SKU', 'PRODUCT_ID', 'MATERIAL'
    # Note: ITEM_ID removed - it's an internal Oracle key, not the user-visible SKU
]

QUANTITY_PATTERNS = [
    'LOCT_ONHAND', 'ONHAND', 'QUANTITY', 'QTY',
    'TRANSACTION_QUANTITY', 'PRIMARY_QUANTITY', 'AVAILABLE'
]

# Separated: SUBINVENTORY (warehouse section) vs LOCATOR (specific bin/rack)
SUBINVENTORY_PATTERNS = [
    'SUBINVENTORY', 'SUB_INV', 'SEC_INV', 'SUB_CODE'
]

LOCATOR_PATTERNS = [
    'LOCATOR', 'LOCATION', 'LOC_NAME', 'RACK'
    # Note: Removed 'BIN' - it matches 'SUBINVENTORY' (SU-BIN-VENTORY)
]

# Note: 'LOT' alone is too broad - matches LOT_ID which often contains NULL
LOT_PATTERNS = ['LOT_NUMBER', 'LOT_NO', 'BATCH_NO', 'BATCH_NUM']

ORG_PATTERNS = ['ORGANIZATION_CODE', 'ORGN_CODE', 'ORG_CODE', 'ORGANIZATION']

# Test organizations to exclude from results (non-operative data)
EXCLUDED_ORGANIZATIONS = {'RQC', 'RSF', 'RSP', 'RSR', 'RRD'}

UOM_PATTERNS = ['UOM', 'ITEM_UOM', 'UNIT', 'UNIT_OF_MEASURE']

DESCRIPTION_PATTERNS = ['DESCRIPTION', 'ITEM_DESC', 'DESC', 'ITEM_DESCRIPTION', 'NAME']

# --- Patterns for filter_relevant_columns (AI summarization) ---
RELEVANT_COLUMN_PATTERNS = [
    # Identifiers
    'ITEM_NUMBER', 'ITEM_NO', 'SEGMENT1', 'DESCRIPTION', 'ITEM_DESC',
    'ITEM_DESCRIPTION', 'LOT_NUMBER', 'LOT_NO',
    # Quantities
    'QUANTITY', 'QTY', 'ONHAND', 'LOCT_ONHAND', 'TRANSACTION_QUANTITY', 'PRIMARY_QUANTITY',
    # Location / Org
    'ORGANIZATION', 'ORGN_CODE', 'SUBINVENTORY', 'LOCATION', 'LOCATOR', 'ZONE', 'ORG_CODE',
    # Batch / Lot
    'LOT', 'BATCH', 'LPN', 'LICENSE_PLATE', 'STATUS', 'LOT_STATUS',
    # Dates
    'DATE', 'EXPIRY', 'EXPIRE', 'MANUFACTURE', 'CREATION',
    # Details
    'VENDOR', 'SUPPLIER', 'REV', 'REVISION', 'UOM', 'ITEM_UOM'
]

KNOWN_DOCUMENTS_NAME = [
    "xxuni_oh_quick_yak",           # Inventory
    "xxyak_item_transaction_quick"  # Transactions
]

INTENT_NAMES_HEBREW = {
    'מלאי': 'מלאי נוכחי',
    'תנועות': 'תנועות אחרונות',
    'מכירות': 'מכירות',
    'רכש': 'רכש'
}

# --- Group By Mapping ---
# Maps group_by values to index field names (used in aggregate_by_product)
# Can add here more groups. If you add one more, YOU HAVE TO teach the AI as well!
GROUP_BY_MAPPING = {
    'location': ['sub', 'loc'],      # לפי מיקום
    'lot': ['lot'],                   # לפי לוט
    'org': ['org'],                   # לפי ארגון
    'subinventory': ['sub'],          # לפי מחסן
    'item_no': ['product'],           # לפי מק"ט - maps to product column index
}

GROUP_BY_KEYWORDS_HEBREW = {
    # Location (מיקום)
    'מיקום': 'location',
    'מיקומים': 'location',       # Plural
    'לפי מיקום': 'location',
    'לפי מיקומים': 'location',   # Plural
    'איתור': 'location',
    # Subinventory (מחסן)
    'מחסן': 'subinventory',
    'מחסנים': 'subinventory',    # Plural - was missing!
    'לפי מחסן': 'subinventory',
    'לפי מחסנים': 'subinventory', # Plural
    'תת מחסן': 'subinventory',
    # Lot (לוט/אצווה)
    'לוט': 'lot',
    'לוטים': 'lot',
    'אצווה': 'lot',
    'אצוות': 'lot',
    'לפי לוט': 'lot',
    'לפי אצווה': 'lot',
    # Organization (ארגון)
    'ארגון': 'org',
    'ארגונים': 'org',
    'לפי ארגון': 'org',
    # Item number (מק"ט)
    'מק"ט': 'item_no',
    'מקט': 'item_no',
    'קט': 'item_no'
}