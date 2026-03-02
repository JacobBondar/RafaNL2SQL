# Rafa NL2SQL System

Natural Language to SQL system for querying Oracle EBS (E-Business Suite) databases. Users ask questions in **Hebrew**, and the system returns formatted answers with data.

## Quick Start

### Run Streamlit Web App (Recommended)
```bash
streamlit run app.py
```

**Access URLs:**
- **Local:** http://localhost:8501
- **Network:** http://10.14.1.70:8501

### Run Console Version
```bash
python RafaNL2SQL.py
```
Type `יציאה` to exit.

---

## What Does This System Do?

1. User asks a question in Hebrew (e.g., "כמה מלאי יש של 346501?")
2. AI analyzes the question to identify:
   - **Intents**: מלאי (inventory), תנועות (transactions), מכירות (sales), רכש (procurement)
   - **Product names/IDs**: Items the user is asking about
   - **Groupings**: How to break down results (by warehouse, lot, organization)
   - **Filters**: Conditions like "expired items only"
3. System finds relevant Oracle Discoverer reports
4. Executes SQL queries with smart filtering
5. Returns aggregated results formatted in Hebrew

---

## File Structure

| File | Purpose |
|------|---------|
| `app.py` | **Streamlit web interface** - Chat UI, table display, CSV export |
| `RafaNL2SQL.py` | **Console interface** - Text-based chat loop |
| `AI_Communication.py` | Ollama AI integration - question analysis, Hebrew formatting |
| `OracleCommunication.py` | Oracle DB operations - queries, SQL filtering |
| `intent_handlers.py` | Handler functions for each intent type |
| `data_utils.py` | Data aggregation, filtering, column detection |
| `utils.py` | SQL validation, security checks |
| `config.py` | Constants - patterns, limits, mappings |
| `prompts.py` | AI prompt templates |
| `queries.py` | SQL query templates |
| `OracleConnection.py` | Oracle connection factory |

---

## Dependencies

Install required packages:
```bash
pip install oracledb ollama streamlit pandas
```

**Requirements:**
- Python 3.8+
- Oracle Client libraries (for oracledb)
- Ollama running locally with model `gpt-oss:20b`
- Access to Oracle EBS database

---

## Supported Intents

| Intent | Hebrew Keyword | What It Does |
|--------|----------------|--------------|
| Inventory | מלאי | Shows current stock quantities, grouped by product |
| Transactions | תנועות | Shows last 20 item movements (sorted by date) |
| Sales | מכירות | *Placeholder - not yet implemented* |
| Procurement | רכש | *Placeholder - not yet implemented* |

---

## Example Questions

```
כמה מלאי יש של 346501?
מה המלאי של HEDRIN?
תראה לי את התנועות של 346501
מה המלאי לפי מחסן?
כמה מלאי יש של 346501 לפי לוט?
```

---

## Configuration

Key settings in `config.py`:

| Setting | Value | Description |
|---------|-------|-------------|
| `OLLAMA_MODEL` | `gpt-oss:20b` | AI model for analysis |
| `MAX_ROWS_QUERY` | 5000 | Max rows per SQL query |
| `AI_FORMAT_MAX_ITEMS` | 30 | Items before switching to manual format |
| `EXCLUDED_ORGANIZATIONS` | RQC, RSF, RSP, RSR, RRD | Test orgs filtered from results |

---

## Architecture Overview

```
User Question (Hebrew)
    |
    v
AI Analysis (Ollama)
    -> intents, products, groupings, filters
    |
    v
Oracle Discoverer Metadata
    -> Find relevant reports
    |
    v
SQL Execution
    -> Filter by products (injection/wrapping)
    -> Apply organization filter
    |
    v
Intent Handler
    -> Aggregate data
    -> Format for display
    |
    v
AI Formatting
    -> Hebrew response
    |
    v
Display to User
    -> Text response
    -> Table (for large datasets)
    -> CSV export option
```

---

## Security Features

- **Read-only queries only** - INSERT, UPDATE, DELETE blocked
- **SQL injection prevention** - Forbidden keywords checked
- **Row limits** - Max 5000 rows per query
- **Test org filtering** - Non-production data excluded automatically

---

## Troubleshooting

### "Cannot connect to Oracle"
- Check Oracle client is installed
- Verify connection string in `OracleConnection.py`
- Ensure network access to database server

### "AI analysis failed"
- Check Ollama is running: `ollama list`
- Verify model exists: `ollama pull gpt-oss:20b`

### "No data found"
- Check product ID is correct
- Verify user has access to relevant Oracle reports
- Try a simpler query first

---

## For Future Developers

### Adding a New Intent

1. **Create handler function** in `intent_handlers.py`:
```python
def process_samples_logic(data_tables, searched_items, group_by_descriptions=None,
                          filter_condition=None, date_filter=None):
    # Your processing logic here
    return {'type': 'samples', 'data': '...', 'count': 0}
```

2. **Register in INTENT_HANDLERS dict** (same file):
```python
INTENT_HANDLERS['דגימות'] = process_samples_logic
```

3. **Add Hebrew name** in `config.py`:
```python
INTENT_NAMES_HEBREW['דגימות'] = 'דגימות'
```

---

### Column Detection Patterns

The system identifies columns using pattern matching in `config.py`:

| Pattern Type | Examples | Used For |
|--------------|----------|----------|
| `PRODUCT_PATTERNS` | ITEM_NO, SEGMENT1, SKU | Product identification |
| `QUANTITY_PATTERNS` | ONHAND, QTY, LOCT_ONHAND | Stock quantities |
| `SUBINVENTORY_PATTERNS` | SUBINVENTORY, SUB_INV | Warehouse sections |
| `LOCATOR_PATTERNS` | LOCATOR, LOCATION, RACK | Specific bin/rack |
| `LOT_PATTERNS` | LOT_NUMBER, BATCH_NO | Lot/batch numbers |
| `ORG_PATTERNS` | ORGANIZATION_CODE, ORGN_CODE | Organization filtering |

To add new patterns, edit the relevant list in `config.py`.

---

### SQL Filtering Strategies

The system uses two approaches to filter SQL queries (`OracleCommunication.py`):

**1. Injection (Preferred)**
- AI finds an anchor point in the SQL
- Injects `WHERE/AND` clause directly
- Faster, but requires identifying correct position

**2. Wrapping (Fallback)**
- Wraps entire SQL in outer `SELECT * FROM (...) WHERE filter`
- Always works, but less efficient
- Used automatically for UNION queries

---

### Oracle Tables Used

| Table | Purpose |
|-------|---------|
| `EUL4_US.eul5_documents` | Discoverer reports metadata |
| `EUL4_US.eul5_expressions` | Column alias to real name mapping |
| `EUL4_US.EUL5_SEGMENTS` | SQL chunks storage |
| `MTL_SYSTEM_ITEMS_B` | Product lookup (name to ID) |

---

### Group-By Resolution

Two-path approach in `intent_handlers.py`:

1. **Fast path**: Check `GROUP_BY_KEYWORDS_HEBREW` dict for known Hebrew terms
   - `מחסן` → subinventory
   - `לוט` / `אצווה` → lot
   - `מיקום` → location (subinventory + locator)
   - `ארגון` → organization

2. **Slow path**: AI semantic matching against actual column names (for unknown terms)

---

### Key Constants

| Constant | Location | Value | Purpose |
|----------|----------|-------|---------|
| `MAX_ROWS_QUERY` | config.py | 5000 | Prevent runaway queries |
| `AI_FORMAT_MAX_ITEMS` | config.py | 30 | Switch to manual formatting |
| `TABLE_THRESHOLD` | app.py | 30 | Show table instead of text |
| `TRANSACTION_LENGTH` | intent_handlers.py | 20 | Max transactions to show |
| `EXCLUDED_ORGANIZATIONS` | config.py | RQC,RSF,RSP,RSR,RRD | Test orgs to filter |