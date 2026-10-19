import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from app.detectors import RawIssue
from app.engine import build_metrics_map, run_engine
from app.fixes import AI_ENHANCED_CODES, fix_text, suggested_fix
from app.ingest import parse_ads, parse_listings, parse_reviews
from app.metrics import AdRow, ListingMetrics, ListingRow, ReviewRow


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_ai_enabled(conn: sqlite3.Connection) -> bool:
    row = conn.execute("SELECT value FROM settings WHERE key = 'ai_enabled'").fetchone()
    return row is not None and row["value"] == "true"


def set_ai_enabled(conn: sqlite3.Connection, enabled: bool) -> None:
    conn.execute(
        "INSERT INTO settings (key, value) VALUES ('ai_enabled', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        ("true" if enabled else "false",),
    )
    conn.commit()


def latest_snapshot(conn: sqlite3.Connection) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM snapshots ORDER BY id DESC LIMIT 1").fetchone()


def _insert_listings(conn: sqlite3.Connection, rows: list[ListingRow]) -> None:
    conn.executemany(
        "INSERT INTO listings (snapshot_date, brand, sku, platform, title, bullet_count, "
        "image_count, price, mrp, stock, rating, review_count, buybox_owner, category, "
        "status, units_sold_7d) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            (
                r.snapshot_date, r.brand, r.sku, r.platform, r.title, r.bullet_count,
                r.image_count, r.price, r.mrp, r.stock, r.rating, r.review_count,
                r.buybox_owner, r.category, r.status, r.units_sold_7d,
            )
            for r in rows
        ],
    )


def _insert_ads(conn: sqlite3.Connection, rows: list[AdRow]) -> None:
    conn.executemany(
        "INSERT INTO ads (date, sku, platform, spend, clicks, orders, sales) VALUES (?,?,?,?,?,?,?)",
        [(r.date, r.sku, r.platform, r.spend, r.clicks, r.orders, r.sales) for r in rows],
    )


def _insert_reviews(conn: sqlite3.Connection, rows: list[ReviewRow]) -> None:
    conn.executemany(
        "INSERT INTO reviews (sku, platform, review_date, stars, text) VALUES (?,?,?,?,?)",
        [(r.sku, r.platform, r.review_date, r.stars, r.text) for r in rows],
    )


def load_listings_from_db(conn: sqlite3.Connection) -> list[ListingRow]:
    rows = conn.execute("SELECT * FROM listings").fetchall()
    return [
        ListingRow(
            snapshot_date=r["snapshot_date"], brand=r["brand"], sku=r["sku"],
            platform=r["platform"], title=r["title"], bullet_count=r["bullet_count"],
            image_count=r["image_count"], price=r["price"], mrp=r["mrp"], stock=r["stock"],
            rating=r["rating"], review_count=r["review_count"], buybox_owner=r["buybox_owner"],
            category=r["category"], status=r["status"], units_sold_7d=r["units_sold_7d"],
        )
        for r in rows
    ]


def load_ads_from_db(conn: sqlite3.Connection) -> list[AdRow]:
    rows = conn.execute("SELECT * FROM ads").fetchall()
    return [
        AdRow(date=r["date"], sku=r["sku"], platform=r["platform"], spend=r["spend"],
              clicks=r["clicks"], orders=r["orders"], sales=r["sales"])
        for r in rows
    ]


def load_reviews_from_db(conn: sqlite3.Connection) -> list[ReviewRow]:
    rows = conn.execute("SELECT * FROM reviews").fetchall()
    return [
        ReviewRow(sku=r["sku"], platform=r["platform"], review_date=r["review_date"],
                   stars=r["stars"], text=r["text"])
        for r in rows
    ]


def _park_live_decisions(conn: sqlite3.Connection) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO carried_decisions "
        "(sku, platform, issue_code, action, message_text, edited, created_at) "
        "SELECT i.sku, i.platform, i.issue_code, d.action, d.message_text, d.edited, d.created_at "
        "FROM decisions d JOIN issues i ON i.id = d.issue_id WHERE d.undone_at IS NULL"
    )


def _reattach_carried_decisions(conn: sqlite3.Connection) -> None:
    """A decision survives a re-audit only if the same issue still fires on the same
    listing; decisions on issues that have since resolved are dropped."""
    conn.execute(
        "INSERT INTO decisions (issue_id, action, message_text, edited, created_at) "
        "SELECT i.id, c.action, c.message_text, c.edited, c.created_at FROM carried_decisions c "
        "JOIN issues i ON i.sku = c.sku AND i.platform = c.platform AND i.issue_code = c.issue_code"
    )
    conn.execute("DELETE FROM carried_decisions")


def _error_label(slot: str, file_name: str) -> str:
    return file_name if file_name.lower().startswith(slot) else f"{slot.capitalize()} file '{file_name}'"


def ingest_csvs(
    conn: sqlite3.Connection, listings_path: Path, ads_path: Path, reviews_path: Path, file_names: dict | None = None
) -> dict:
    """Replaces all data with the three files (CSV or spreadsheet) and opens a new snapshot
    in 'uploaded' state. Issues are not computed here — that is run_audit, a separate step
    the AM triggers. Live decisions are parked so the audit can re-attach them to issues
    that still fire. `file_names` are the names as uploaded, used in errors and the UI."""
    names = {slot: (file_names or {}).get(slot) or f"{slot}.csv" for slot in ("listings", "ads", "reviews")}
    listings = parse_listings(listings_path, _error_label("listings", names["listings"]))
    ads = parse_ads(ads_path, _error_label("ads", names["ads"]))
    reviews = parse_reviews(reviews_path, _error_label("reviews", names["reviews"]))

    try:
        _park_live_decisions(conn)
        conn.execute("DELETE FROM decisions")
        conn.execute("DELETE FROM issues")
        conn.execute("DELETE FROM listings")
        conn.execute("DELETE FROM ads")
        conn.execute("DELETE FROM reviews")
        _insert_listings(conn, listings)
        _insert_ads(conn, ads)
        _insert_reviews(conn, reviews)
        conn.execute(
            "INSERT INTO snapshots (status, uploaded_at, listings_rows, ads_rows, reviews_rows, file_names_json) "
            "VALUES ('uploaded', ?, ?, ?, ?, ?)",
            (_now(), len(listings), len(ads), len(reviews), json.dumps(names)),
        )
        conn.commit()
    except sqlite3.Error:
        conn.rollback()
        raise
    return {"listings": len(listings), "ads": len(ads), "reviews": len(reviews)}


def run_audit(conn: sqlite3.Connection, cfg: dict, allow_ai: bool = True) -> int:
    count = recompute_issues_full(conn, cfg, allow_ai)
    snap = latest_snapshot(conn)
    if snap is not None:
        conn.execute(
            "UPDATE snapshots SET status = 'audited', audited_at = ? WHERE id = ?", (_now(), snap["id"])
        )
        conn.commit()
    return count


def recompute_issues_full(conn: sqlite3.Connection, cfg: dict, allow_ai: bool = True) -> int:
    """allow_ai=False writes template text only, so the audit never waits on the network;
    the API then fills AI drafts in afterwards with refresh_ai_dependent_text."""
    listings = load_listings_from_db(conn)
    ads = load_ads_from_db(conn)
    reviews = load_reviews_from_db(conn)

    metrics_map, issues = run_engine(listings, ads, reviews)
    ai_enabled = allow_ai and get_ai_enabled(conn)
    now = _now()

    fixes = _fixes_parallel(
        [(RawIssue(i.code, i.evidence), metrics_map[(i.sku, i.platform)]) for i in issues],
        cfg,
        _ai_slots([(i.code, i.impact_inr) for i in issues], cfg, ai_enabled),
    )

    _park_live_decisions(conn)
    conn.execute("DELETE FROM decisions")
    conn.execute("DELETE FROM issues")

    rows = []
    for issue, (fix, ai_generated) in zip(issues, fixes):
        rows.append(
            (
                issue.sku, issue.platform, issue.brand, issue.code, issue.severity,
                issue.impact_inr, json.dumps(issue.evidence), fix_text(fix), json.dumps(fix),
                issue.impact_calc_text, 1 if ai_generated else 0, now,
            )
        )

    conn.executemany(
        "INSERT INTO issues (sku, platform, brand, issue_code, severity, impact_inr, "
        "evidence_json, suggested_fix, fix_json, impact_calc_text, ai_generated, computed_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )
    _reattach_carried_decisions(conn)
    conn.commit()
    return len(rows)


def refresh_ai_dependent_text(conn: sqlite3.Connection, cfg: dict) -> int:
    """Called when the AI toggle flips. Updates fix text in place for the AI-enhanced
    issue codes only — preserves issue ids (and any decisions against them) rather than
    a full recompute, since nothing about the underlying data changed."""
    rows = conn.execute(
        "SELECT id, sku, platform, issue_code, impact_inr, evidence_json FROM issues "
        "WHERE issue_code IN ({})".format(",".join("?" * len(AI_ENHANCED_CODES))),
        tuple(AI_ENHANCED_CODES),
    ).fetchall()
    if not rows:
        return 0

    metrics_map = build_metrics_map(
        load_listings_from_db(conn), load_ads_from_db(conn), load_reviews_from_db(conn)
    )
    ai_enabled = get_ai_enabled(conn)

    targets = [r for r in rows if (r["sku"], r["platform"]) in metrics_map]
    fixes = _fixes_parallel(
        [
            (RawIssue(r["issue_code"], json.loads(r["evidence_json"])), metrics_map[(r["sku"], r["platform"])])
            for r in targets
        ],
        cfg,
        _ai_slots([(r["issue_code"], r["impact_inr"]) for r in targets], cfg, ai_enabled),
    )
    if get_ai_enabled(conn) != ai_enabled:
        return 0  # the toggle flipped while drafts were generating; that request rewrites the text
    for row, (fix, ai_generated) in zip(targets, fixes):
        conn.execute(
            "UPDATE issues SET suggested_fix = ?, fix_json = ?, ai_generated = ? WHERE id = ?",
            (fix_text(fix), json.dumps(fix), 1 if ai_generated else 0, row["id"]),
        )
    conn.commit()
    return len(targets)


def _ai_slots(codes_and_impacts: list[tuple[str, float]], cfg: dict, ai_enabled: bool) -> set[int]:
    """Indices of the issues that get an AI draft this run: the highest-impact
    AI-enhanced ones, up to ai.max_fixes_per_run. Everything else uses its template."""
    if not ai_enabled:
        return set()
    eligible = [i for i, (code, _) in enumerate(codes_and_impacts) if code in AI_ENHANCED_CODES]
    eligible.sort(key=lambda i: codes_and_impacts[i][1], reverse=True)
    return set(eligible[: cfg["ai"]["max_fixes_per_run"]])


def _fixes_parallel(items: list[tuple[RawIssue, ListingMetrics]], cfg: dict, ai_slots: set[int]) -> list[tuple[dict, bool]]:
    """Each AI draft is one network round trip, so those run concurrently; template
    fixes are local and run inline."""
    if not ai_slots:
        return [suggested_fix(raw, m, cfg, False) for raw, m in items]
    with ThreadPoolExecutor(max_workers=4) as pool:
        return list(
            pool.map(lambda idx_item: suggested_fix(*idx_item[1], cfg, idx_item[0] in ai_slots), enumerate(items))
        )
