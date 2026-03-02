# Rafa NL2SQL Project

## User Context
- New to Oracle, first internship
- Provide detailed explanations when relevant

## Project Overview
Natural Language to SQL system for querying Oracle EBS (E-Business Suite) databases. Users ask questions in **Hebrew**, and the system:
1. Analyzes the question using AI (Ollama)
2. Identifies intents, product names, groupings, and filters
3. Finds relevant reports from Oracle Discoverer metadata
4. Executes SQL queries with smart filtering (injection or wrapping)
5. Aggregates and formats results in Hebrew

## File Structure

| File | Purpose |
|------|---------|
| `RafaNL2SQL.py` | **Main entry point** - console chat loop, orchestrates intent processing |
| `AI_Communication.py` | Ollama AI integration - question analysis, column matching, Hebrew formatting |
| `OracleCommunication.py` | Oracle DB operations - connecting, querying reports, SQL injection/wrapping |
| `intent_handlers.py` | **Intent dispatch** - handler functions for inventory, transactions, sales, procurement |
| `data_utils.py` | **Pure data functions** - aggregation, filtering, column detection (no AI/DB dependencies) |
| `utils.py` | Utilities - SQL validation, security checks, loading animation |
| `config.py` | Constants - model name, column patterns, SQL limits, group-by mappings |
| `prompts.py` | AI prompts - question analysis, column picking, Hebrew formatting |
| `queries.py` | SQL templates - report queries, column lookups, product search |
| `OracleConnection.py` | External module - contains `create_connection()` function |

## Dependencies
- `oracledb` - Oracle database connector
- `ollama` - Local LLM client (model: `gpt-oss:20b`)
- Standard libs: `json`, `datetime`, `threading`, `re`, `time`, `sys`

## Key Intents (Hebrew)
| Intent | Hebrew | Handler | Status |
|--------|--------|---------|--------|
| Inventory | `מלאי` | `process_inventory_logic` | Implemented |
| Transactions | `תנועות` | `process_transactions_logic` | Implemented |
| Sales | `מכירות` | `process_sales_logic` | Placeholder |
| Procurement | `רכש` | `process_procurement_logic` | Placeholder |
| Chat | `chat` | Handled in `RafaNL2SQL.py` | Implemented |
| Unknown | `unknown` | Handled in `RafaNL2SQL.py` | Implemented |

## Oracle Tables Used
| Table | Purpose |
|-------|---------|
| `EUL4_US.eul5_documents` | Discoverer reports metadata |
| `EUL4_US.eul5_elem_xrefs` | Element cross-references |
| `EUL4_US.eul5_expressions` | Report expressions (alias to real name mapping) |
| `EUL4_US.eul5_objs` | Objects/tables info |
| `EUL4_US.EUL5_SEGMENTS` | SQL chunks storage |
| `MTL_SYSTEM_ITEMS_B` | Master items table (product lookup) |

## Architecture

### Intent Handlers (`intent_handlers.py`)
Function dispatch pattern - no if/elif chains:

```python
INTENT_HANDLERS = {
    'מלאי': process_inventory_logic,      # Aggregates quantities by product
    'תנועות': process_transactions_logic, # Shows last 20 movements
    'מכירות': process_sales_logic,        # Placeholder
    'רכש': process_procurement_logic,     # Placeholder
}
```

### Data Flow
```
User Question (Hebrew)
    ↓
AI Analysis (analyze_user_question)
    → intents, product_names, group_by_descriptions, filter_condition, date_filter
    ↓
For each intent:
    ↓
    Get Documents (get_documents) → Oracle Discoverer metadata
    ↓
    Get Data (get_data):
        → Translate products to IDs (MTL_SYSTEM_ITEMS_B)
        → Build/retrieve SQL from chunks
        → Smart filtering: injection OR wrapping
        → Execute and enrich with EXPIRE_FLAG
    ↓
    Intent Handler (process_*_logic):
        → Aggregate by product (with grouping/filtering)
        → Format stats text
        → AI formats to Hebrew
    ↓
Combine Results (summarize_multi_intent)
    ↓
Hebrew Response to User
```

### SQL Filtering Strategy (`OracleCommunication.py`)
1. **Injection** (preferred): AI finds anchor point, injects `WHERE/AND` clause directly into base SQL
2. **Wrapping** (fallback): Wraps base SQL in outer SELECT with filter
3. **UNION safety**: Always uses wrapping for UNION queries

### Group-By Resolution (`intent_handlers.py`)
Two-path approach:
1. **Fast path**: Check `GROUP_BY_KEYWORDS_HEBREW` dict for known Hebrew terms
2. **Slow path**: AI semantic matching against actual column names

### Column Detection (`data_utils.py`)
Pattern-based matching defined in `config.py`:
- `PRODUCT_PATTERNS`: ITEM_NO, SEGMENT1, SKU...
- `QUANTITY_PATTERNS`: ONHAND, QTY, LOCT_ONHAND...
- `SUBINVENTORY_PATTERNS`: SUBINVENTORY, SUB_INV...
- `LOCATOR_PATTERNS`: LOCATOR, LOCATION...
- `LOT_PATTERNS`: LOT_NUMBER, BATCH_NO...

### Adding New Intents
```python
# 1. Add handler function in intent_handlers.py
def process_samples_logic(data_tables, searched_items, group_by_descriptions=None,
                          filter_condition=None, date_filter=None):
    # Your logic here
    return {'type': 'samples', 'data': '...', 'count': 0}

# 2. Register in INTENT_HANDLERS dict
INTENT_HANDLERS['דגימות'] = process_samples_logic

# 3. Add Hebrew name in config.py
INTENT_NAMES_HEBREW['דגימות'] = 'דגימות'
```

## Technical Details

### SQL Security (`utils.py`)
- **Read-only enforcement**: Only SELECT/WITH queries allowed
- **Forbidden keywords**: INSERT, UPDATE, DELETE, DROP, CREATE, EXEC, DECLARE, BEGIN, LOCK, FOR UPDATE
- **Validation order**: Read-only check → Oracle parse → Execute
- **Row limit**: 5000 rows max per query (`MAX_ROWS_QUERY`)

### Alias Mapping (`OracleCommunication.py`)
Discoverer SQL uses aliases like `i12345`. The system:
1. Extracts `i\d+` patterns from SQL
2. Queries `EUL5_EXPRESSIONS` to get real column names
3. Uses readable names for AI, technical names for SQL

### EBS Security Context
Some reports require `fnd_global.apps_initialize()` - detected and executed automatically via `run_security_context()`.

### AI Formatting Limits (`config.py`)
- `AI_FORMAT_MAX_ITEMS = 30` - Products before manual formatting
- `AI_FORMAT_MAX_CHARS = 1200` - Stats text length before manual formatting
- Large datasets use `format_large_dataset_manually()` instead of AI

### Chat History
- Maintains conversation context for pronoun resolution ("זה", "אותו", "שלו")
- Moving window of last 10 messages
- Products NOT carried forward unless explicit reference

## How to Run
```bash
python RafaNL2SQL.py
```
Type `יציאה` to exit.

## TODO

### In Progress
- [ ] **Streamlit UI** - Building web interface for broader access and feedback collection

### Bugs to Fix
- [ ] **תנועות handler not working properly** - Transactions intent needs debugging

### Next Up
- [ ] **Create CMD launch script** - Write a batch file (`.bat`) to run `streamlit run app.py` without opening the IDE

### Future Features
- [x] Date filtering - Implemented for transactions handler (filters by date range)
- [ ] Implement Sales Handler - Filter outbound transactions, sum by customer
- [ ] Implement Procurement Handler - Filter receipts, group by supplier
- [ ] Implement Samples Handler - Add דגימות intent support

---

## Streamlit UI Implementation Plan

### Overview
Convert the console-based chat application to a Streamlit web interface with:
1. Chat interface (replacing console input/output)
2. Suggestions page (for colleague feedback)
3. Interactive table display (for large datasets)

### New Files to Create

| File | Purpose |
|------|---------|
| `app.py` | Main Streamlit entry point with chat interface |
| `pages/1_Suggestions.py` | Suggestions form and admin view |
| `suggestions_db.py` | SQLite storage for suggestions |
| `.streamlit/config.toml` | Streamlit configuration |

### Existing Files to Modify

| File | Change |
|------|--------|
| `utils.py` | Add `StreamlitLoader` class (replaces threading-based `Loader`) |
| `intent_handlers.py` | Return `raw_data` dict for table display |
| `AI_Communication.py` | Use `StreamlitLoader` instead of `Loader` |

### Implementation Steps

#### Step 1: Add StreamlitLoader to `utils.py`
The current `Loader` class (lines 171-208) uses threading which breaks in Streamlit.
Add a new `StreamlitLoader` class that:
- Detects if running in Streamlit (`st.runtime.exists()`)
- Uses `st.spinner()` in Streamlit, falls back to `Loader` in console

#### Step 2: Create `app.py` (Main Chat Interface)
Key components:
- `st.session_state.chat_history` - Preserve AI context
- `st.session_state.messages` - Display history
- `@st.cache_resource` - Cache Oracle connection
- `st.spinner()` - Loading indicator during AI/DB calls
- `st.chat_input()` - User input
- `st.chat_message()` - Display messages
- `st.dataframe()` - Table display for large datasets

#### Step 3: Modify `intent_handlers.py` to Return Raw Data
Current return (lines 149-153):
```python
return {'type': 'inventory', 'data': hebrew_result, 'count': ...}
```
Add `raw_data` for table display:
```python
return {
    'type': 'inventory',
    'data': hebrew_result,
    'count': ...,
    'raw_data': aggregated.get('products', {})  # NEW
}
```

#### Step 4: Create Table Display Function
In `app.py`:
- Convert `raw_data` dict to pandas DataFrame
- Hebrew column headers (פריט, כמות, מיקום, אצווה)
- `st.dataframe()` with `use_container_width=True`
- CSV export button with `st.download_button()`

#### Step 5: Create Suggestions Feature

**`suggestions_db.py`**:
- SQLite database (file: `suggestions.db`)
- Table schema: id, timestamp, user_name, category, suggestion_text, status
- Functions: `init_db()`, `add_suggestion()`, `get_all_suggestions()`

**`pages/1_Suggestions.py`**:
- Form: name (optional), category dropdown, text area
- Categories: שיפור ביצועים, בקשה לדו"ח חדש, באג/תקלה, שיפור ממשק, אחר
- Admin view (password protected) to see all suggestions

### Technical Decisions

| Decision | Choice | Reason |
|----------|--------|--------|
| Suggestions storage | SQLite file | No Oracle schema changes, easy backup |
| Oracle connection | `@st.cache_resource` | Reuse connection across requests |
| Table threshold | >= 30 items | Show table for large datasets, text for small |
| Hebrew RTL | CSS in `app.py` | `direction: rtl; text-align: right;` |

### How to Run (After Implementation)
```bash
streamlit run app.py
```
Access at `http://localhost:8501`

