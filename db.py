import sqlite3
from pathlib import Path
import os
from typing import Optional

DB_PATH = Path(os.getenv("DB_PATH", "counter.db"))


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
        CREATE TABLE IF NOT EXISTS milestone_hits (
            milestone INTEGER PRIMARY KEY
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS sale_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            message_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            username TEXT,
            display_name TEXT NOT NULL,
            sale_date TEXT NOT NULL,
            sale_code TEXT,
            text TEXT,
            source TEXT NOT NULL DEFAULT 'auto',
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(chat_id, message_id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS ignored_users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            display_name TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
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


def get_dashboard_message_id() -> int | None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT dashboard_message_id FROM settings WHERE id = 1")
    row = cur.fetchone()
    conn.close()
    return row["dashboard_message_id"] if row and row["dashboard_message_id"] else None


def get_chat_id() -> int | None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT chat_id FROM settings WHERE id = 1")
    row = cur.fetchone()
    conn.close()
    return row["chat_id"] if row and row["chat_id"] else None


def get_current_date() -> str | None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT current_date FROM settings WHERE id = 1")
    row = cur.fetchone()
    conn.close()
    return row["current_date"] if row else None


def reset_daily_counts(new_date: str):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        "UPDATE settings SET today_count = 0, current_date = ? WHERE id = 1",
        (new_date,)
    )
    cur.execute("DELETE FROM daily_user_counts")
    cur.execute("DELETE FROM milestone_hits")
    cur.execute("UPDATE sale_messages SET is_active = 0 WHERE sale_date != ?", (new_date,))

    conn.commit()
    conn.close()


def add_sale_message(
    chat_id: int,
    message_id: int,
    user_id: int,
    username: Optional[str],
    display_name: str,
    sale_date: str,
    sale_code: Optional[str],
    text: str,
    source: str = "auto",
):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO sale_messages (
            chat_id, message_id, user_id, username, display_name,
            sale_date, sale_code, text, source, is_active
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
        ON CONFLICT(chat_id, message_id) DO UPDATE SET
            user_id = excluded.user_id,
            username = excluded.username,
            display_name = excluded.display_name,
            sale_date = excluded.sale_date,
            sale_code = excluded.sale_code,
            text = excluded.text,
            source = excluded.source,
            is_active = 1,
            updated_at = CURRENT_TIMESTAMP
    """, (
        chat_id,
        message_id,
        user_id,
        username,
        display_name,
        sale_date,
        sale_code,
        text,
        source,
    ))

    conn.commit()
    conn.close()


def get_active_sale_by_message(chat_id: int, message_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT *
        FROM sale_messages
        WHERE chat_id = ?
          AND message_id = ?
          AND is_active = 1
    """, (chat_id, message_id))
    row = cur.fetchone()
    conn.close()
    return row


def get_active_sale_by_code(sale_date: str, sale_code: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT *
        FROM sale_messages
        WHERE sale_date = ?
          AND sale_code = ?
          AND is_active = 1
        LIMIT 1
    """, (sale_date, sale_code))
    row = cur.fetchone()
    conn.close()
    return row


def deactivate_sale_by_message(chat_id: int, message_id: int) -> bool:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE sale_messages
        SET is_active = 0,
            updated_at = CURRENT_TIMESTAMP
        WHERE chat_id = ?
          AND message_id = ?
          AND is_active = 1
    """, (chat_id, message_id))
    changed = cur.rowcount > 0
    conn.commit()
    conn.close()
    return changed


def deactivate_sale_by_code(sale_date: str, sale_code: str) -> bool:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE sale_messages
        SET is_active = 0,
            updated_at = CURRENT_TIMESTAMP
        WHERE sale_date = ?
          AND sale_code = ?
          AND is_active = 1
    """, (sale_date, sale_code))
    changed = cur.rowcount > 0
    conn.commit()
    conn.close()
    return changed


def rebuild_counts_from_sales(sale_date: str):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("DELETE FROM daily_user_counts")

    cur.execute("""
        INSERT INTO daily_user_counts (user_id, username, display_name, count)
        SELECT
            sm.user_id,
            MAX(sm.username),
            MAX(sm.display_name),
            COUNT(*) AS count
        FROM sale_messages sm
        LEFT JOIN ignored_users iu ON iu.user_id = sm.user_id
        WHERE sm.sale_date = ?
          AND sm.is_active = 1
          AND iu.user_id IS NULL
        GROUP BY sm.user_id
    """, (sale_date,))

    cur.execute("""
        UPDATE settings
        SET today_count = (
            SELECT COUNT(*)
            FROM sale_messages sm
            LEFT JOIN ignored_users iu ON iu.user_id = sm.user_id
            WHERE sm.sale_date = ?
              AND sm.is_active = 1
              AND iu.user_id IS NULL
        )
        WHERE id = 1
    """, (sale_date,))

    conn.commit()
    conn.close()


def get_today_total() -> int:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT today_count FROM settings WHERE id = 1")
    row = cur.fetchone()
    conn.close()
    return row["today_count"] if row else 0


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


def get_all_operator_counts():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT user_id, username, display_name, count
        FROM daily_user_counts
        ORDER BY count DESC, display_name ASC
    """)
    rows = cur.fetchall()
    conn.close()
    return rows


def has_milestone_been_hit(milestone: int) -> bool:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT 1 FROM milestone_hits WHERE milestone = ?",
        (milestone,)
    )
    row = cur.fetchone()
    conn.close()
    return row is not None


def mark_milestone_hit(milestone: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT OR IGNORE INTO milestone_hits (milestone) VALUES (?)",
        (milestone,)
    )
    conn.commit()
    conn.close()


def ignore_user(user_id: int, username: Optional[str], display_name: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO ignored_users (user_id, username, display_name)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            username = excluded.username,
            display_name = excluded.display_name
    """, (user_id, username, display_name))
    conn.commit()
    conn.close()


def unignore_user(user_id: int) -> bool:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM ignored_users WHERE user_id = ?", (user_id,))
    changed = cur.rowcount > 0
    conn.commit()
    conn.close()
    return changed


def is_user_ignored(user_id: int) -> bool:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM ignored_users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return row is not None


def get_ignored_users():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT user_id, username, display_name
        FROM ignored_users
        ORDER BY display_name ASC
    """)
    rows = cur.fetchall()
    conn.close()
    return rows
