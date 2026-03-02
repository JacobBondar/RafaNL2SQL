"""
SQLite database for storing user suggestions and feedback.
"""

import sqlite3
from datetime import datetime
from pathlib import Path

# Database file location (same directory as this file)
DB_PATH = Path(__file__).parent / "suggestions.db"

def init_db():
    """Initialize the database and create table if not exists."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS suggestions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            user_name TEXT,
            category TEXT,
            suggestion_text TEXT NOT NULL,
            status TEXT DEFAULT 'pending'
        )
    """)
    conn.commit()
    conn.close()

def add_suggestion(user_name: str, category: str, suggestion_text: str) -> bool:
    """
    Add a new suggestion to the database.

    Args:
        user_name: Name of the user (optional, can be empty)
        category: Category of the suggestion
        suggestion_text: The actual suggestion text

    Returns:
        True if successful, False otherwise
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            """INSERT INTO suggestions (timestamp, user_name, category, suggestion_text)
               VALUES (?, ?, ?, ?)""",
            (datetime.now().isoformat(), user_name or "אנונימי", category, suggestion_text)
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Error adding suggestion: {e}")
        return False

def get_all_suggestions() -> list:
    """
    Get all suggestions from the database.

    Returns:
        List of tuples: (id, timestamp, user_name, category, suggestion_text, status)
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.execute(
            "SELECT id, timestamp, user_name, category, suggestion_text, status FROM suggestions ORDER BY timestamp DESC"
        )
        results = cursor.fetchall()
        conn.close()
        return results
    except Exception as e:
        print(f"Error getting suggestions: {e}")
        return []

def update_suggestion_status(suggestion_id: int, new_status: str) -> bool:
    """
    Update the status of a suggestion.

    Args:
        suggestion_id: ID of the suggestion to update
        new_status: New status value

    Returns:
        True if successful, False otherwise
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "UPDATE suggestions SET status = ? WHERE id = ?",
            (new_status, suggestion_id)
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Error updating suggestion: {e}")
        return False

# No use for the function
def get_suggestions_by_status(status: str) -> list:
    """
    Get suggestions filtered by status.

    Args:
        status: Status to filter by (e.g., 'pending', 'reviewed', 'implemented')

    Returns:
        List of matching suggestions
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.execute(
            "SELECT id, timestamp, user_name, category, suggestion_text, status FROM suggestions WHERE status = ? ORDER BY timestamp DESC",
            (status,)
        )
        results = cursor.fetchall()
        conn.close()
        return results
    except Exception as e:
        print(f"Error getting suggestions by status: {e}")
        return []
