import json
import os
import sqlite3
from datetime import datetime, timezone


def _db_path():
    data_dir = os.getenv("DATA_DIR", "./data")
    os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, "lumiere_invoice_bot.sqlite3")


def connect():
    con = sqlite3.connect(_db_path())
    con.row_factory = sqlite3.Row
    return con


def init_db():
    with connect() as con:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_chat_id INTEGER NOT NULL,
                topic_id INTEGER NOT NULL,
                source_message_id INTEGER,
                preview_message_id INTEGER,
                order_no TEXT,
                customer TEXT NOT NULL,
                raw_text TEXT NOT NULL,
                items_json TEXT NOT NULL,
                payment_status TEXT DEFAULT 'Unpaid',
                payment_method TEXT DEFAULT '',
                status TEXT DEFAULT 'pending',
                invoice_no TEXT,
                created_at TEXT NOT NULL,
                created_by INTEGER
            );
            """
        )


def set_setting(key, value):
    with connect() as con:
        con.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, str(value)),
        )


def get_setting(key, default=None):
    with connect() as con:
        row = con.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def save_order_topic(chat_id, topic_id):
    set_setting("order_chat_id", chat_id)
    set_setting("order_topic_id", topic_id)


def save_invoice_topic(chat_id, topic_id):
    set_setting("invoice_chat_id", chat_id)
    set_setting("invoice_topic_id", topic_id)


def get_order_topic():
    # Backward compatibility with the previous /setup version.
    chat_id = get_setting("order_chat_id") or get_setting("chat_id")
    topic_id = get_setting("order_topic_id") or get_setting("topic_id")
    if not chat_id or not topic_id:
        return None
    return int(chat_id), int(topic_id)


def get_invoice_topic():
    chat_id = get_setting("invoice_chat_id")
    topic_id = get_setting("invoice_topic_id")
    if not chat_id or not topic_id:
        return None
    return int(chat_id), int(topic_id)


def source_message_exists(chat_id, topic_id, source_message_id):
    with connect() as con:
        row = con.execute(
            "SELECT 1 FROM orders WHERE telegram_chat_id=? AND topic_id=? AND source_message_id=? LIMIT 1",
            (chat_id, topic_id, source_message_id),
        ).fetchone()
    return bool(row)


def create_order(chat_id, topic_id, source_message_id, parsed, raw_text, created_by):
    now = datetime.now(timezone.utc).isoformat()
    with connect() as con:
        cur = con.execute(
            """
            INSERT INTO orders(
              telegram_chat_id, topic_id, source_message_id, order_no, customer,
              raw_text, items_json, payment_status, payment_method, created_at, created_by
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                chat_id, topic_id, source_message_id, parsed.get("order_no"),
                parsed["customer"], raw_text, json.dumps(parsed["items"]),
                parsed.get("payment_status", "Unpaid"), parsed.get("payment_method", ""),
                now, created_by,
            ),
        )
        return cur.lastrowid


def get_order(order_id):
    with connect() as con:
        row = con.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    if not row:
        return None
    d = dict(row)
    d["items"] = json.loads(d.pop("items_json"))
    return d


def mark_order(order_id, status, invoice_no=None):
    with connect() as con:
        if invoice_no is None:
            con.execute("UPDATE orders SET status=? WHERE id=?", (status, order_id))
        else:
            con.execute(
                "UPDATE orders SET status=?, invoice_no=? WHERE id=?",
                (status, invoice_no, order_id),
            )


def next_invoice_no(preferred=None):
    if preferred:
        return str(preferred)
    with connect() as con:
        row = con.execute("SELECT MAX(id) AS max_id FROM orders").fetchone()
    return str((row["max_id"] or 0))
