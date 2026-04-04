import sqlite3
from pathlib import Path
from typing import Optional

DB_PATH = Path("counter.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            chat_id INTEGER,
            dashboard_message_id INTEGER,
            current_date TEXT,
            today_count INTEGER NOT NULL DEFAULT 0
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS daily_user_counts (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            display_name TEXT NOT NULL,
            count INTEGER NOT NULL DEFAULT 0
        )
    """)

    cur.execute("""
        INSERT OR IGNORE INTO settings (id, chat_id, dashboard_message_id, current_date, today_count)
        VALUES (1, NULL, NULL, NULL, 0)
    """)

    conn.commit()
    conn.close()


def get_settings():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM settings WHERE id = 1")
    row = cur.fetchone()
    conn.close()
    return row


def set_chat_id(chat_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE settings SET chat_id = ? WHERE id = 1", (chat_id,))
    conn.commit()
    conn.close()


def set_dashboard_message_id(message_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE settings SET dashboard_message_id = ? WHERE id = 1",
        (message_id,)
    )
    conn.commit()
    conn.close()


def set_current_date(date_str: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE settings SET current_date = ? WHERE id = 1", (date_str,))
    conn.commit()
    conn.close()


def get_today_count() -> int:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT today_count FROM settings WHERE id = 1")
    row = cur.fetchone()
    conn.close()
    return row["today_count"] if row else 0


def increment_today_count() -> int:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE settings
        SET today_count = today_count + 1
        WHERE id = 1
    """)
    conn.commit()

    cur.execute("SELECT today_count FROM settings WHERE id = 1")
    row = cur.fetchone()
    conn.close()
    return row["today_count"]


def reset_daily_counts(new_date: str):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("UPDATE settings SET today_count = 0, current_date = ? WHERE id = 1", (new_date,))
    cur.execute("DELETE FROM daily_user_counts")

    conn.commit()
    conn.close()


def increment_user_count(user_id: int, username: Optional[str], display_name: str):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO daily_user_counts (user_id, username, display_name, count)
        VALUES (?, ?, ?, 1)
        ON CONFLICT(user_id) DO UPDATE SET
            count = count + 1,
            username = excluded.username,
            display_name = excluded.display_name
    """, (user_id, username, display_name))

    conn.commit()
    conn.close()


def get_leaderboard(limit: int = 10):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT user_id, username, display_name, count
        FROM daily_user_counts
        ORDER BY count DESC, display_name ASC
        LIMIT ?
    """, (limit,))
    rows = cur.fetchall()
    conn.close()
    return rows