"""Simple SQLite storage for user credentials and trade history."""
import sqlite3
import json
import os
import time
import hashlib

DB_PATH = os.path.join(os.path.dirname(__file__), "edgex_agent.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            tg_user_id INTEGER PRIMARY KEY,
            account_id TEXT,
            stark_private_key TEXT,
            ai_api_key TEXT,
            ai_base_url TEXT,
            ai_model TEXT,
            personality TEXT DEFAULT 'pro',
            created_at REAL
        )
    """)
    try:
        c.execute("ALTER TABLE users ADD COLUMN personality TEXT DEFAULT 'pro'")
    except Exception:
        pass
    c.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tg_user_id INTEGER,
            order_id TEXT,
            contract_id TEXT,
            side TEXT,
            size TEXT,
            price TEXT,
            status TEXT,
            pnl TEXT DEFAULT '0',
            thesis TEXT,
            created_at REAL,
            updated_at REAL
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS ai_usage (
            tg_user_id INTEGER,
            date TEXT,
            count INTEGER DEFAULT 0,
            PRIMARY KEY (tg_user_id, date)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tg_user_id INTEGER,
            tg_username TEXT,
            tg_first_name TEXT,
            message TEXT,
            status TEXT DEFAULT 'new',
            admin_reply TEXT,
            created_at REAL,
            resolved_at REAL
        )
    """)
    # Memory system tables
    c.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tg_user_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            metadata TEXT DEFAULT '{}',
            created_at REAL NOT NULL
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_conv_user_time ON conversations(tg_user_id, created_at DESC)")
    c.execute("""
        CREATE TABLE IF NOT EXISTS memory_summaries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tg_user_id INTEGER NOT NULL,
            summary TEXT NOT NULL,
            keywords TEXT DEFAULT '',
            turn_count INTEGER DEFAULT 0,
            period_start REAL,
            period_end REAL,
            created_at REAL NOT NULL
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_memsumm_user ON memory_summaries(tg_user_id, created_at DESC)")
    c.execute("""
        CREATE TABLE IF NOT EXISTS user_preferences (
            tg_user_id INTEGER PRIMARY KEY,
            preferences TEXT DEFAULT '{}',
            updated_at REAL
        )
    """)
    conn.commit()
    conn.close()


def save_feedback(tg_user_id: int, tg_username: str, tg_first_name: str, message: str):
    conn = get_conn()
    conn.execute(
        "INSERT INTO feedback (tg_user_id, tg_username, tg_first_name, message, created_at) VALUES (?, ?, ?, ?, ?)",
        (tg_user_id, tg_username or "", tg_first_name or "", message, time.time()),
    )
    conn.commit()
    conn.close()


def get_all_feedback(status_filter: str = None):
    conn = get_conn()
    if status_filter:
        rows = conn.execute("SELECT * FROM feedback WHERE status = ? ORDER BY created_at DESC", (status_filter,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM feedback ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_feedback(feedback_id: int, status: str, admin_reply: str = None):
    conn = get_conn()
    if admin_reply:
        conn.execute("UPDATE feedback SET status = ?, admin_reply = ?, resolved_at = ? WHERE id = ?",
                     (status, admin_reply, time.time(), feedback_id))
    else:
        conn.execute("UPDATE feedback SET status = ? WHERE id = ?", (status, feedback_id))
    conn.commit()
    conn.close()


def get_feedback_by_id(feedback_id: int):
    conn = get_conn()
    row = conn.execute("SELECT * FROM feedback WHERE id = ?", (feedback_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_ai_usage_today(tg_user_id: int) -> int:
    import datetime
    today = datetime.date.today().isoformat()
    conn = get_conn()
    row = conn.execute("SELECT count FROM ai_usage WHERE tg_user_id = ? AND date = ?", (tg_user_id, today)).fetchone()
    conn.close()
    return row["count"] if row else 0


def increment_ai_usage(tg_user_id: int):
    import datetime
    today = datetime.date.today().isoformat()
    conn = get_conn()
    conn.execute(
        "INSERT INTO ai_usage (tg_user_id, date, count) VALUES (?, ?, 1) "
        "ON CONFLICT(tg_user_id, date) DO UPDATE SET count = count + 1",
        (tg_user_id, today),
    )
    conn.commit()
    conn.close()


def save_user(tg_user_id: int, account_id: str, stark_private_key: str):
    conn = get_conn()
    existing = conn.execute("SELECT * FROM users WHERE tg_user_id = ?", (tg_user_id,)).fetchone()
    if existing:
        conn.execute(
            "UPDATE users SET account_id = ?, stark_private_key = ? WHERE tg_user_id = ?",
            (account_id, stark_private_key, tg_user_id),
        )
    else:
        conn.execute(
            "INSERT INTO users (tg_user_id, account_id, stark_private_key, created_at) VALUES (?, ?, ?, ?)",
            (tg_user_id, account_id, stark_private_key, time.time()),
        )
    conn.commit()
    conn.close()


def get_user(tg_user_id: int):
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE tg_user_id = ?", (tg_user_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def save_trade(tg_user_id: int, order_id: str, contract_id: str, side: str, size: str, price: str, thesis: str):
    conn = get_conn()
    now = time.time()
    conn.execute(
        "INSERT INTO trades (tg_user_id, order_id, contract_id, side, size, price, status, thesis, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (tg_user_id, order_id, contract_id, side, size, price, "OPEN", thesis, now, now),
    )
    conn.commit()
    conn.close()


def update_trade_status(order_id: str, status: str, pnl: str = "0"):
    conn = get_conn()
    conn.execute(
        "UPDATE trades SET status = ?, pnl = ?, updated_at = ? WHERE order_id = ?",
        (status, pnl, time.time(), order_id),
    )
    conn.commit()
    conn.close()


def get_user_trades(tg_user_id: int, limit: int = 10):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM trades WHERE tg_user_id = ? ORDER BY created_at DESC LIMIT ?",
        (tg_user_id, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_open_trades(tg_user_id: int):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM trades WHERE tg_user_id = ? AND status = 'OPEN' ORDER BY created_at DESC",
        (tg_user_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Memory system ──

def save_conversation(tg_user_id: int, role: str, content: str, metadata: dict = None):
    conn = get_conn()
    conn.execute(
        "INSERT INTO conversations (tg_user_id, role, content, metadata, created_at) VALUES (?, ?, ?, ?, ?)",
        (tg_user_id, role, content, json.dumps(metadata or {}), time.time()),
    )
    conn.commit()
    conn.close()


def get_recent_conversations(tg_user_id: int, limit: int = 20) -> list:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM conversations WHERE tg_user_id = ? ORDER BY created_at DESC LIMIT ?",
        (tg_user_id, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in reversed(rows)]


def get_conversation_count(tg_user_id: int) -> int:
    conn = get_conn()
    row = conn.execute(
        "SELECT COUNT(*) as c FROM conversations WHERE tg_user_id = ?",
        (tg_user_id,),
    ).fetchone()
    conn.close()
    return row["c"] if row else 0


def get_conversations_since(tg_user_id: int, since_ts: float) -> list:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM conversations WHERE tg_user_id = ? AND created_at > ? ORDER BY created_at ASC",
        (tg_user_id, since_ts),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_old_conversations(tg_user_id: int, keep_recent: int = 200):
    """Delete oldest conversations beyond keep_recent for a user."""
    conn = get_conn()
    conn.execute(
        "DELETE FROM conversations WHERE tg_user_id = ? AND id NOT IN "
        "(SELECT id FROM conversations WHERE tg_user_id = ? ORDER BY created_at DESC LIMIT ?)",
        (tg_user_id, tg_user_id, keep_recent),
    )
    conn.commit()
    conn.close()


def save_memory_summary(tg_user_id: int, summary: str, keywords: str,
                         turn_count: int, period_start: float, period_end: float):
    conn = get_conn()
    conn.execute(
        "INSERT INTO memory_summaries (tg_user_id, summary, keywords, turn_count, period_start, period_end, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (tg_user_id, summary, keywords, turn_count, period_start, period_end, time.time()),
    )
    conn.commit()
    conn.close()


def get_memory_summaries(tg_user_id: int, limit: int = 10) -> list:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM memory_summaries WHERE tg_user_id = ? ORDER BY created_at DESC LIMIT ?",
        (tg_user_id, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in reversed(rows)]


def search_conversations(tg_user_id: int, keyword: str, limit: int = 10) -> list:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM conversations WHERE tg_user_id = ? AND content LIKE ? ORDER BY created_at DESC LIMIT ?",
        (tg_user_id, f"%{keyword}%", limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def search_memory_summaries(tg_user_id: int, keyword: str, limit: int = 5) -> list:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM memory_summaries WHERE tg_user_id = ? AND (summary LIKE ? OR keywords LIKE ?) "
        "ORDER BY created_at DESC LIMIT ?",
        (tg_user_id, f"%{keyword}%", f"%{keyword}%", limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_user_preferences(tg_user_id: int) -> dict:
    conn = get_conn()
    row = conn.execute(
        "SELECT preferences FROM user_preferences WHERE tg_user_id = ?",
        (tg_user_id,),
    ).fetchone()
    conn.close()
    if row:
        try:
            return json.loads(row["preferences"])
        except (json.JSONDecodeError, TypeError):
            pass
    return {}


def save_user_preferences(tg_user_id: int, prefs: dict):
    conn = get_conn()
    conn.execute(
        "INSERT INTO user_preferences (tg_user_id, preferences, updated_at) VALUES (?, ?, ?) "
        "ON CONFLICT(tg_user_id) DO UPDATE SET preferences = ?, updated_at = ?",
        (tg_user_id, json.dumps(prefs), time.time(), json.dumps(prefs), time.time()),
    )
    conn.commit()
    conn.close()


def clear_user_memory(tg_user_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM conversations WHERE tg_user_id = ?", (tg_user_id,))
    conn.execute("DELETE FROM memory_summaries WHERE tg_user_id = ?", (tg_user_id,))
    conn.execute("DELETE FROM user_preferences WHERE tg_user_id = ?", (tg_user_id,))
    conn.commit()
    conn.close()


def get_memory_stats(tg_user_id: int) -> dict:
    conn = get_conn()
    conv_count = conn.execute(
        "SELECT COUNT(*) as c FROM conversations WHERE tg_user_id = ?", (tg_user_id,)
    ).fetchone()
    summ_count = conn.execute(
        "SELECT COUNT(*) as c FROM memory_summaries WHERE tg_user_id = ?", (tg_user_id,)
    ).fetchone()
    oldest = conn.execute(
        "SELECT MIN(created_at) as t FROM conversations WHERE tg_user_id = ?", (tg_user_id,)
    ).fetchone()
    conn.close()
    return {
        "conversations": conv_count["c"] if conv_count else 0,
        "summaries": summ_count["c"] if summ_count else 0,
        "oldest_ts": oldest["t"] if oldest and oldest["t"] else None,
    }
