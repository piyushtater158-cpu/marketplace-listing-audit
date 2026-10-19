import os
import sqlite3
from pathlib import Path

DB_PATH = Path(os.environ.get("DB_PATH", Path(__file__).resolve().parent.parent / "data" / "app.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS listings (
    snapshot_date TEXT NOT NULL,
    brand TEXT NOT NULL,
    sku TEXT NOT NULL,
    platform TEXT NOT NULL,
    title TEXT NOT NULL,
    bullet_count INTEGER NOT NULL,
    image_count INTEGER NOT NULL,
    price REAL NOT NULL,
    mrp REAL NOT NULL,
    stock INTEGER NOT NULL,
    rating REAL NOT NULL,
    review_count INTEGER NOT NULL,
    buybox_owner TEXT NOT NULL,
    category TEXT NOT NULL,
    status TEXT NOT NULL,
    units_sold_7d REAL NOT NULL,
    PRIMARY KEY (snapshot_date, sku, platform)
);

CREATE TABLE IF NOT EXISTS ads (
    date TEXT NOT NULL,
    sku TEXT NOT NULL,
    platform TEXT NOT NULL,
    spend REAL NOT NULL,
    clicks INTEGER NOT NULL,
    orders INTEGER NOT NULL,
    sales REAL NOT NULL,
    PRIMARY KEY (date, sku, platform)
);

CREATE TABLE IF NOT EXISTS reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sku TEXT NOT NULL,
    platform TEXT NOT NULL,
    review_date TEXT NOT NULL,
    stars INTEGER NOT NULL,
    text TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS issues (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sku TEXT NOT NULL,
    platform TEXT NOT NULL,
    brand TEXT NOT NULL,
    issue_code TEXT NOT NULL,
    severity TEXT NOT NULL,
    impact_inr REAL NOT NULL,
    evidence_json TEXT NOT NULL,
    suggested_fix TEXT NOT NULL,
    fix_json TEXT NOT NULL DEFAULT '{}',
    impact_calc_text TEXT NOT NULL DEFAULT '',
    ai_generated INTEGER NOT NULL DEFAULT 0,
    computed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    issue_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    message_text TEXT,
    edited INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    undone_at TEXT,
    FOREIGN KEY (issue_id) REFERENCES issues(id)
);

-- Decisions waiting to be re-attached by the next audit. An upload clears the issues
-- table, so live decisions park here keyed by listing and issue code.
CREATE TABLE IF NOT EXISTS carried_decisions (
    sku TEXT NOT NULL,
    platform TEXT NOT NULL,
    issue_code TEXT NOT NULL,
    action TEXT NOT NULL,
    message_text TEXT,
    edited INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    PRIMARY KEY (sku, platform, issue_code)
);

CREATE TABLE IF NOT EXISTS snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    status TEXT NOT NULL,
    uploaded_at TEXT NOT NULL,
    audited_at TEXT,
    listings_rows INTEGER NOT NULL,
    ads_rows INTEGER NOT NULL,
    reviews_rows INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

# Columns added after the first schema shipped; CREATE TABLE IF NOT EXISTS won't add them
# to a database file created by an older build.
_ADDED_COLUMNS = [
    ("issues", "fix_json", "TEXT NOT NULL DEFAULT '{}'"),
    ("issues", "impact_calc_text", "TEXT NOT NULL DEFAULT ''"),
    ("decisions", "undone_at", "TEXT"),
]


def get_connection(db_path: Path | str | None = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path else DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    for table, column, decl in _ADDED_COLUMNS:
        existing = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        if column not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
    conn.execute(
        "INSERT OR IGNORE INTO settings (key, value) VALUES ('ai_enabled', 'true')"
    )
    conn.commit()


def clear_ingested_data(conn: sqlite3.Connection) -> None:
    for table in ("decisions", "carried_decisions", "issues", "listings", "ads", "reviews", "snapshots"):
        conn.execute(f"DELETE FROM {table}")
    conn.commit()
