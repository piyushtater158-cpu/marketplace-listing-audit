import json
import math
import os
import re
import sqlite3
import tempfile
import threading
from collections import Counter, defaultdict
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from app.ai import ai_available, cluster_complaints, detect_language, summarize_brand_week, translate_reviews
from app.config import load_config
from app.db import clear_ingested_data, get_connection, init_db
from app.engine import build_metrics_map
from app.impact import cap_listing_total
from app.ingest import ACCEPTED, SPREADSHEET_SUFFIXES, TEXT_SUFFIXES, CsvValidationError
from app.metrics import ListingMetrics, ListingRow
from app.pipeline import (
    get_ai_enabled,
    ingest_csvs,
    latest_snapshot,
    load_ads_from_db,
    load_listings_from_db,
    load_reviews_from_db,
    refresh_ai_dependent_text,
    run_audit,
    set_ai_enabled,
)
from app.present import ISSUE_LABELS, RECIPIENTS, RULE_IDS, compose_message, evidence_points, inr
from app.schemas import (
    AiSettingIn,
    AiSettingOut,
    AuditResultOut,
    BrandReportOut,
    ComplaintThemeOut,
    DecisionIn,
    DecisionOut,
    FixOut,
    IssueOut,
    ListingSnapshotOut,
    PlatformDetailOut,
    PortfolioCell,
    PortfolioOut,
    ReviewOut,
    SkuDetailOut,
    SnapshotOut,
    SnapshotRow,
    UploadResultOut,
)

SEED_DIR = Path(os.environ.get("SEED_DIR", Path(__file__).resolve().parent.parent / "seed"))
PLATFORMS = ["Amazon", "Flipkart"]
SEVERITIES = ["critical", "high", "medium", "low"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


_ai_fill_lock = threading.Lock()


def _fill_ai_drafts() -> None:
    with _ai_fill_lock:
        conn = get_connection()
        try:
            refresh_ai_dependent_text(conn, load_config())
        finally:
            conn.close()


def _fill_ai_drafts_in_background() -> None:
    """AI drafts replace template text a few seconds after an audit. Free models can be
    slow or rate-limited, so no request (or server startup) waits on them."""
    if ai_available(load_config()):
        threading.Thread(target=_fill_ai_drafts, daemon=True).start()


def _bootstrap(conn: sqlite3.Connection) -> bool:
    """First boot loads and audits the seed, returning True. A database from an older
    build that has data but no snapshot row gets one, so the overview knows it is audited."""
    if conn.execute("SELECT COUNT(*) FROM listings").fetchone()[0] == 0:
        ingest_csvs(conn, SEED_DIR / "listings.csv", SEED_DIR / "ads.csv", SEED_DIR / "reviews.csv")
        run_audit(conn, load_config(), allow_ai=False)
        return True
    if latest_snapshot(conn) is None:
        counts = [conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("listings", "ads", "reviews")]
        conn.execute(
            "INSERT INTO snapshots (status, uploaded_at, audited_at, listings_rows, ads_rows, reviews_rows) "
            "VALUES ('audited', ?, ?, ?, ?, ?)",
            (_now(), _now(), *counts),
        )
        conn.commit()
    return False


@asynccontextmanager
async def lifespan(_app: FastAPI):
    conn = get_connection()
    try:
        init_db(conn)
        audited = _bootstrap(conn)
    finally:
        conn.close()
    if audited:
        _fill_ai_drafts_in_background()
    yield


app = FastAPI(title="Marketplace Listing Audit API", version="0.2.0", lifespan=lifespan)


def db():
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()


# ---- metrics cache: the engine's per-listing metrics only change when data is
# re-ingested, so reads reuse one computation keyed on the latest snapshot. ----

_metrics_cache: dict = {"stamp": None, "value": None}


def _metrics_map(conn: sqlite3.Connection) -> dict[tuple[str, str], ListingMetrics]:
    snap = latest_snapshot(conn)
    stamp = (snap["id"], snap["uploaded_at"]) if snap else None
    if _metrics_cache["stamp"] != stamp:
        _metrics_cache["value"] = build_metrics_map(
            load_listings_from_db(conn), load_ads_from_db(conn), load_reviews_from_db(conn)
        )
        _metrics_cache["stamp"] = stamp
    return _metrics_cache["value"]


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _brand_order(conn: sqlite3.Connection) -> list[str]:
    cfg_brands = list(load_config()["brands"].keys())
    present = {r["brand"] for r in conn.execute("SELECT DISTINCT brand FROM listings")}
    if not present:
        return cfg_brands
    return [b for b in cfg_brands if b in present] + sorted(present - set(cfg_brands))


def _resolve_brand(conn: sqlite3.Connection, value: str) -> str | None:
    return next((b for b in _brand_order(conn) if _slug(b) == _slug(value)), None)


def _resolve_platform(value: str) -> str | None:
    return next((p for p in PLATFORMS if p.lower() == value.lower()), None)


def _snapshot_out(row: sqlite3.Row | None) -> SnapshotOut | None:
    if row is None:
        return None
    return SnapshotOut(
        id=row["id"],
        status=row["status"],
        uploaded_at=row["uploaded_at"],
        audited_at=row["audited_at"],
        row_counts={"listings": row["listings_rows"], "ads": row["ads_rows"], "reviews": row["reviews_rows"]},
        file_names=json.loads(row["file_names_json"] or "{}"),
    )


ISSUE_SELECT = (
    "SELECT i.*, d.id AS decision_id, d.action AS decision, d.created_at AS decided_at FROM issues i "
    "LEFT JOIN decisions d ON d.issue_id = i.id AND d.undone_at IS NULL"
)
QUEUE_ORDER = " ORDER BY (i.severity = 'critical') DESC, i.impact_inr DESC, i.id"


def _status(decision: str | None) -> str:
    if decision is None:
        return "open"
    return "dismissed" if decision == "dismiss" else "approved"


def _issue_out(row: sqlite3.Row) -> IssueOut:
    evidence = json.loads(row["evidence_json"])
    code = row["issue_code"]
    fix = json.loads(row["fix_json"] or "{}") or {"kind": "message", "text": row["suggested_fix"]}
    fix.setdefault("recipient", RECIPIENTS.get(code, "internal"))
    fix.setdefault("source", "ai" if row["ai_generated"] else "rule")
    label = ISSUE_LABELS.get(code, code)
    if code == "lost_buybox" and row["platform"] != "Amazon":
        label = "Featured-seller slot lost"
    return IssueOut(
        id=row["id"],
        rule_id=RULE_IDS.get(code, code.upper()),
        sku=row["sku"],
        platform=row["platform"],
        brand=row["brand"],
        brand_slug=_slug(row["brand"]),
        issue_code=code,
        issue_label=label,
        severity=row["severity"],
        impact_inr=row["impact_inr"],
        impact_calc_text=row["impact_calc_text"],
        evidence=evidence,
        evidence_points=evidence_points(code, row["platform"], evidence),
        fix=FixOut(**fix),
        suggested_fix=row["suggested_fix"],
        ai_generated=bool(row["ai_generated"]),
        recipient=RECIPIENTS.get(code, "internal"),
        status=_status(row["decision"]),
        detected_at=row["computed_at"],
        decided_at=row["decided_at"],
    )


def _capped_by_listing(conn: sqlite3.Connection, rows: list[sqlite3.Row]) -> dict[tuple[str, str], float]:
    metrics_map = _metrics_map(conn)
    by_listing: dict[tuple[str, str], list[float]] = defaultdict(list)
    for r in rows:
        by_listing[(r["sku"], r["platform"])].append(r["impact_inr"])
    return {
        key: round(cap_listing_total(impacts, metrics_map[key]), 2)
        for key, impacts in by_listing.items()
        if key in metrics_map
    }


# ---- reads ----


@app.get("/api/health")
def health() -> dict:
    return {"ok": True}


@app.get("/api/brands")
def brands(conn: sqlite3.Connection = Depends(db)) -> list[dict]:
    cfg_brands = load_config()["brands"]
    return [
        {"name": b, "slug": _slug(b), "category": cfg_brands.get(b, {}).get("category", "")}
        for b in _brand_order(conn)
    ]


@app.get("/api/portfolio", response_model=PortfolioOut)
def portfolio(conn: sqlite3.Connection = Depends(db)) -> PortfolioOut:
    all_rows = conn.execute(ISSUE_SELECT).fetchall()
    rows = [r for r in all_rows if r["decision"] is None]
    capped = _capped_by_listing(conn, rows)
    brand_list = _brand_order(conn)
    cfg_brands = load_config()["brands"]

    listing_counts = Counter(
        (r["brand"], r["platform"])
        for r in conn.execute("SELECT DISTINCT brand, sku, platform FROM listings")
    )
    brand_of = {(r["sku"], r["platform"]): r["brand"] for r in rows}

    cells = []
    for brand in brand_list:
        for platform in PLATFORMS:
            cell_rows = [r for r in rows if r["brand"] == brand and r["platform"] == platform]
            counts = Counter(r["severity"] for r in cell_rows)
            cell_loss = sum(
                v for (sku, p), v in capped.items() if p == platform and brand_of[(sku, p)] == brand
            )
            cells.append(
                PortfolioCell(
                    brand=brand,
                    brand_slug=_slug(brand),
                    category=cfg_brands.get(brand, {}).get("category", ""),
                    platform=platform,
                    listing_count=listing_counts.get((brand, platform), 0),
                    issue_count=len(cell_rows),
                    severity_counts={s: counts.get(s, 0) for s in SEVERITIES},
                    capped_daily_loss_inr=round(cell_loss, 2),
                )
            )

    totals = Counter(r["severity"] for r in rows)
    approved = [r for r in all_rows if r["decision"] in ("approve", "approve_edited")]
    oldest = {s: min((r["computed_at"] for r in rows if r["severity"] == s), default=None) for s in SEVERITIES}
    return PortfolioOut(
        snapshot=_snapshot_out(latest_snapshot(conn)),
        brands=brand_list,
        platforms=PLATFORMS,
        cells=cells,
        total_daily_loss_inr=round(sum(capped.values()), 2),
        uncapped_daily_loss_inr=round(sum(r["impact_inr"] for r in rows), 2),
        severity_counts={s: totals.get(s, 0) for s in SEVERITIES},
        oldest_open_at=oldest,
        open_issue_count=len(rows),
        flagged_listing_count=len(capped),
        listing_count=sum(listing_counts.values()),
        approved_count=len(approved),
        dismissed_count=sum(1 for r in all_rows if r["decision"] == "dismiss"),
        approved_impact_inr=round(sum(r["impact_inr"] for r in approved), 2),
        has_data=sum(listing_counts.values()) > 0,
        ai_enabled=get_ai_enabled(conn),
        ai_available=ai_available(load_config()),
    )


@app.get("/api/issues", response_model=list[IssueOut])
def issues(
    status: str = Query("open", pattern="^(open|all)$"),
    brand: str | None = None,
    platform: str | None = None,
    severity: str | None = Query(None, pattern="^(critical|high|medium|low)$"),
    conn: sqlite3.Connection = Depends(db),
) -> list[IssueOut]:
    clauses, params = [], []
    if status == "open":
        clauses.append("d.id IS NULL")
    if brand:
        match = _resolve_brand(conn, brand)
        if match is None:
            return []
        clauses.append("i.brand = ?")
        params.append(match)
    if platform:
        match = _resolve_platform(platform)
        if match is None:
            return []
        clauses.append("i.platform = ?")
        params.append(match)
    if severity:
        clauses.append("i.severity = ?")
        params.append(severity)
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(f"{ISSUE_SELECT}{where}{QUEUE_ORDER}", params).fetchall()
    return [_issue_out(r) for r in rows]


@app.get("/api/issues/{issue_id}", response_model=IssueOut)
def issue_detail(issue_id: int, conn: sqlite3.Connection = Depends(db)) -> IssueOut:
    row = conn.execute(f"{ISSUE_SELECT} WHERE i.id = ?", (issue_id,)).fetchone()
    if row is None:
        raise HTTPException(404, f"Issue {issue_id} not found")
    return _issue_out(row)


def _listing_out(r: ListingRow) -> ListingSnapshotOut:
    return ListingSnapshotOut(
        snapshot_date=r.snapshot_date,
        title=r.title,
        price=r.price,
        mrp=r.mrp,
        stock=r.stock,
        rating=r.rating,
        review_count=r.review_count,
        status=r.status,
        buybox_owner=r.buybox_owner,
        image_count=r.image_count,
        bullet_count=r.bullet_count,
    )


# field -> (label, formatter, issue codes that make a change in it "bad")
_SNAPSHOT_FIELDS = [
    ("price", "Price", inr, {"price_mismatch", "price_above_mrp", "price_shock"}),
    ("mrp", "MRP", inr, {"price_above_mrp"}),
    ("stock", "Stock", lambda v: f"{v:.0f}", {"oos_ads_live", "low_stock_high_spend"}),
    ("rating", "Rating", lambda v: f"{v:.1f}", {"rating_drop"}),
    ("review_count", "Reviews", lambda v: f"{v:,}", {"rating_drop"}),
    ("image_count", "Images", str, {"weak_content"}),
    ("bullet_count", "Bullets", str, {"weak_content"}),
    ("status", "Status", str, {"suppressed"}),
    ("buybox_owner", "Buy Box owner", str, {"lost_buybox"}),
]


def _snapshot_rows(m: ListingMetrics, issue_codes: set[str]) -> list[SnapshotRow]:
    out = []
    for field, label, fmt, bad_codes in _SNAPSHOT_FIELDS:
        if field == "buybox_owner" and m.platform != "Amazon":
            label = "Featured seller"
        latest = getattr(m.latest, field)
        previous = getattr(m.previous, field) if m.previous else None
        change = None
        if previous is not None and previous != latest:
            if isinstance(latest, (int, float)) and isinstance(previous, (int, float)):
                diff = latest - previous
                change = f"{'▲' if diff > 0 else '▼'} {fmt(abs(diff))}"
            else:
                change = "changed"
        flagged = bool(bad_codes & issue_codes)
        tone = "bad" if flagged and (change is not None or m.previous is None) else ("chg" if change else "same")
        if flagged and field in ("stock", "status", "buybox_owner") and tone == "same":
            tone = "bad"
        out.append(
            SnapshotRow(
                field=field,
                label=label,
                previous=fmt(previous) if previous is not None else None,
                latest=fmt(latest),
                change=change,
                tone=tone,
            )
        )
    return out


def _representative_reviews(reviews: list[ReviewOut]) -> list[ReviewOut]:
    by_recent = sorted(reviews, key=lambda r: r.review_date, reverse=True)
    negative = [r for r in by_recent if r.stars <= 2][:2]
    positive = [r for r in by_recent if r.stars >= 4][:1]
    picked = negative + positive
    if len(picked) < 3:
        picked += [r for r in by_recent if r not in picked][: 3 - len(picked)]
    return picked


@app.get("/api/sku/{sku}", response_model=SkuDetailOut)
def sku_detail(sku: str, conn: sqlite3.Connection = Depends(db)) -> SkuDetailOut:
    metrics_map = _metrics_map(conn)
    present = {p: metrics_map[(sku, p)] for p in PLATFORMS if (sku, p) in metrics_map}
    if not present:
        raise HTTPException(404, f"SKU {sku} not found")

    cfg = load_config()
    ai_enabled = get_ai_enabled(conn)
    issue_rows = conn.execute(f"{ISSUE_SELECT} WHERE i.sku = ?{QUEUE_ORDER}", (sku,)).fetchall()

    platforms = {}
    for p, m in present.items():
        p_rows = [r for r in issue_rows if r["platform"] == p]
        open_codes = {r["issue_code"] for r in p_rows if r["decision"] is None}
        deltas = {}
        if m.previous is not None:
            for field in ("price", "stock", "rating"):
                change = round(getattr(m.latest, field) - getattr(m.previous, field), 2)
                if change != 0:
                    deltas[field] = change
        platforms[p] = PlatformDetailOut(
            platform=p,
            buybox_label="Buy Box owner" if p == "Amazon" else "Featured seller",
            latest=_listing_out(m.latest),
            previous=_listing_out(m.previous) if m.previous else None,
            deltas=deltas,
            snapshot_rows=_snapshot_rows(m, open_codes),
            issues=[_issue_out(r) for r in p_rows],
        )

    review_rows = [r for m in present.values() for r in m.reviews]
    languages = {r.text: detect_language(r.text, cfg) for r in review_rows}
    translations = translate_reviews([t for t, lang in languages.items() if lang == "hinglish"], cfg, ai_enabled)
    reviews_out = sorted(
        (
            ReviewOut(
                platform=r.platform,
                review_date=r.review_date,
                stars=r.stars,
                text=r.text,
                language=languages[r.text],
                translation=translations.get(r.text),
            )
            for r in review_rows
        ),
        key=lambda r: r.review_date,
        reverse=True,
    )
    stars = Counter(r.stars for r in review_rows)

    themes, themes_ai = [], False
    if review_rows:
        clustered, themes_ai = cluster_complaints(review_rows, cfg, ai_enabled)
        themes = [ComplaintThemeOut(**t.model_dump()) for t in clustered.themes]

    first = next(iter(present.values()))
    return SkuDetailOut(
        sku=sku,
        brand=first.brand,
        brand_slug=_slug(first.brand),
        category=first.latest.category,
        platforms=platforms,
        missing_platforms=[p for p in PLATFORMS if p not in present],
        reviews=reviews_out,
        representative_reviews=_representative_reviews(reviews_out),
        star_distribution={str(s): stars.get(s, 0) for s in range(5, 0, -1)},
        average_stars=round(sum(r.stars for r in review_rows) / len(review_rows), 1) if review_rows else None,
        complaint_themes=themes,
        themes_ai_generated=themes_ai,
        ai_enabled=ai_enabled,
    )


def _monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


@app.get("/api/brand/{brand}/report", response_model=BrandReportOut)
def brand_report(brand: str, week: str | None = None, conn: sqlite3.Connection = Depends(db)) -> BrandReportOut:
    match = _resolve_brand(conn, brand)
    if match is None:
        raise HTTPException(404, f"Brand {brand} not found")

    latest_date = conn.execute("SELECT MAX(snapshot_date) FROM listings").fetchone()[0]
    data_week = _monday(date.fromisoformat(latest_date)) if latest_date else _monday(date.today())
    try:
        week_start = _monday(date.fromisoformat(week)) if week else data_week
    except ValueError as e:
        raise HTTPException(400, "week must be a date like 2026-10-19") from e
    has_data = latest_date is not None and week_start == data_week

    cfg = load_config()
    rows = (
        conn.execute(f"{ISSUE_SELECT} WHERE i.brand = ?{QUEUE_ORDER}", (match,)).fetchall() if has_data else []
    )
    open_rows = [r for r in rows if r["decision"] is None]
    total_impact = round(sum(_capped_by_listing(conn, rows).values()), 2) if rows else 0.0
    critical = sum(1 for r in rows if r["severity"] == "critical")
    approved = sum(1 for r in rows if r["decision"] in ("approve", "approve_edited"))
    dismissed = sum(1 for r in rows if r["decision"] == "dismiss")
    top = sorted(rows, key=lambda r: r["impact_inr"], reverse=True)[:5]

    top_item = None
    if top:
        t = top[0]
        top_item = {
            "sku": t["sku"],
            "platform": t["platform"],
            "label": ISSUE_LABELS.get(t["issue_code"], t["issue_code"]),
            "impact_inr": t["impact_inr"],
        }
    summary, ai_generated = summarize_brand_week(
        match,
        {
            "total_issues": len(rows),
            "total_impact_inr": total_impact,
            "critical_count": critical,
            "approved_count": approved,
            "dismissed_count": dismissed,
            "open_count": len(open_rows),
            "top_item": top_item,
        },
        cfg,
        get_ai_enabled(conn),
    )
    if not has_data:
        summary.summary = f"No audit data for {match} in the week of {week_start.strftime('%d %b %Y')}."
        ai_generated = False

    listing_count = conn.execute(
        "SELECT COUNT(*) FROM (SELECT DISTINCT sku, platform FROM listings WHERE brand = ?)", (match,)
    ).fetchone()[0]
    snap = latest_snapshot(conn)
    return BrandReportOut(
        brand=match,
        brand_slug=_slug(match),
        category=cfg["brands"].get(match, {}).get("category", ""),
        listing_count=listing_count,
        audited_at=snap["audited_at"] if snap else None,
        week_start=week_start.isoformat(),
        week_end=(week_start + timedelta(days=6)).isoformat(),
        prev_week=(week_start - timedelta(days=7)).isoformat(),
        next_week=(week_start + timedelta(days=7)).isoformat() if week_start < data_week else None,
        has_data=has_data,
        summary=summary.summary,
        ai_generated=ai_generated,
        total_issues=len(rows),
        open_issues=len(open_rows),
        total_impact_inr=total_impact,
        critical_count=critical,
        approved_count=approved,
        dismissed_count=dismissed,
        top_issues=[_issue_out(r) for r in top],
    )


def _finite(value):
    return None if isinstance(value, float) and not math.isfinite(value) else value


@app.get("/api/debug")
def debug(conn: sqlite3.Connection = Depends(db)) -> dict:
    """Full computed state per listing: the engine's proof-of-correctness surface."""
    metrics_map = _metrics_map(conn)
    rows = conn.execute(ISSUE_SELECT).fetchall()
    capped = _capped_by_listing(conn, rows)
    snapshot = _snapshot_out(latest_snapshot(conn))
    issues_by_listing: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        issues_by_listing[f"{r['sku']}|{r['platform']}"].append(
            {
                "id": r["id"],
                "rule_id": RULE_IDS.get(r["issue_code"]),
                "code": r["issue_code"],
                "severity": r["severity"],
                "impact_inr": r["impact_inr"],
                "impact_calc_text": r["impact_calc_text"],
                "evidence": json.loads(r["evidence_json"]),
                "ai_generated": bool(r["ai_generated"]),
                "status": _status(r["decision"]),
            }
        )

    listings = {}
    for (sku, platform), m in sorted(metrics_map.items()):
        key = f"{sku}|{platform}"
        listings[key] = {
            "brand": m.brand,
            "metrics": {
                "avg_daily_spend": round(m.avg_daily_spend, 2),
                "avg_daily_sales": round(m.avg_daily_sales, 2),
                "avg_daily_units": round(m.avg_daily_units, 2),
                "roas": _finite(round(m.roas, 3)) if m.roas is not None else None,
                "days_cover": _finite(round(m.days_cover, 2)),
                "price_delta_pct": m.price_delta_pct,
                "price_change_pct": m.price_change_pct,
                "rating_delta": m.rating_delta,
                "low_star_count_7d": m.low_star_count_7d,
                "orders_7d": m.orders_7d,
            },
            "issues": issues_by_listing.get(key, []),
            "uncapped_total_inr": round(sum(i["impact_inr"] for i in issues_by_listing.get(key, [])), 2),
            "capped_total_inr": capped.get((sku, platform), 0.0),
            "recovery_cap_inr": round(m.avg_daily_spend + m.avg_daily_sales, 2),
        }

    return {
        "summary": {
            "snapshot": snapshot.model_dump() if snapshot else None,
            "listing_count": len(metrics_map),
            "flagged_listing_count": len(capped),
            "issue_count": len(rows),
            "issues_by_code": dict(Counter(r["issue_code"] for r in rows)),
            "uncapped_total_inr": round(sum(r["impact_inr"] for r in rows), 2),
            "capped_total_inr": round(sum(capped.values()), 2),
            "ai_enabled": get_ai_enabled(conn),
        },
        "listings": listings,
    }


_DECISION_SELECT = (
    "SELECT d.*, i.issue_code, i.sku, i.platform, i.brand, i.impact_inr "
    "FROM decisions d JOIN issues i ON i.id = d.issue_id"
)


def _decision_out(row: sqlite3.Row) -> DecisionOut:
    return DecisionOut(
        id=row["id"],
        issue_id=row["issue_id"],
        decision=row["action"],
        recipient=RECIPIENTS.get(row["issue_code"], "internal"),
        final_text=row["message_text"],
        decided_at=row["created_at"],
        undone_at=row["undone_at"],
        sku=row["sku"],
        platform=row["platform"],
        brand=row["brand"],
        issue_code=row["issue_code"],
        issue_label=ISSUE_LABELS.get(row["issue_code"], row["issue_code"]),
        impact_inr=row["impact_inr"],
    )


@app.get("/api/decisions", response_model=list[DecisionOut])
def list_decisions(limit: int = 50, conn: sqlite3.Connection = Depends(db)) -> list[DecisionOut]:
    rows = conn.execute(f"{_DECISION_SELECT} ORDER BY d.id DESC LIMIT ?", (limit,)).fetchall()
    return [_decision_out(r) for r in rows]


@app.get("/api/decisions/{decision_id}", response_model=DecisionOut)
def get_decision(decision_id: int, conn: sqlite3.Connection = Depends(db)) -> DecisionOut:
    row = conn.execute(f"{_DECISION_SELECT} WHERE d.id = ?", (decision_id,)).fetchone()
    if row is None:
        raise HTTPException(404, f"Decision {decision_id} not found")
    return _decision_out(row)


SAMPLE_FILES = ("listings", "ads", "reviews")


@app.get("/api/samples/{name}.csv")
def sample_csv(name: str) -> FileResponse:
    """The bundled sample CSVs, so a reviewer can try the upload without their own exports."""
    if name not in SAMPLE_FILES:
        raise HTTPException(404, f"No sample file {name}.csv")
    return FileResponse(SEED_DIR / f"{name}.csv", media_type="text/csv", filename=f"{name}.csv")


@app.get("/api/settings/ai", response_model=AiSettingOut)
def get_ai_setting(conn: sqlite3.Connection = Depends(db)) -> AiSettingOut:
    return AiSettingOut(enabled=get_ai_enabled(conn), available=ai_available(load_config()))


# ---- writes ----


@app.post("/api/decisions", response_model=DecisionOut)
def create_decision(body: DecisionIn, conn: sqlite3.Connection = Depends(db)) -> DecisionOut:
    issue = conn.execute("SELECT * FROM issues WHERE id = ?", (body.issue_id,)).fetchone()
    if issue is None:
        raise HTTPException(404, f"Issue {body.issue_id} not found")
    if conn.execute(
        "SELECT 1 FROM decisions WHERE issue_id = ? AND undone_at IS NULL", (body.issue_id,)
    ).fetchone():
        raise HTTPException(409, f"Issue {body.issue_id} already has a decision")

    final_text = None
    if body.decision in ("approve", "approve_edited"):
        fix = issue["suggested_fix"]
        if body.decision == "approve_edited":
            if not body.fix_text or not body.fix_text.strip():
                raise HTTPException(422, "approve_edited needs the edited fix_text")
            fix = body.fix_text.strip()
        final_text = compose_message(
            issue["issue_code"], issue["sku"], issue["platform"], issue["brand"], issue["impact_inr"], fix
        )

    cur = conn.execute(
        "INSERT INTO decisions (issue_id, action, message_text, edited, created_at) VALUES (?,?,?,?,?)",
        (body.issue_id, body.decision, final_text, 1 if body.decision == "approve_edited" else 0, _now()),
    )
    conn.commit()
    return get_decision(cur.lastrowid, conn)


@app.post("/api/decisions/{decision_id}/undo", response_model=DecisionOut)
def undo_decision(decision_id: int, conn: sqlite3.Connection = Depends(db)) -> DecisionOut:
    row = conn.execute("SELECT * FROM decisions WHERE id = ?", (decision_id,)).fetchone()
    if row is None:
        raise HTTPException(404, f"Decision {decision_id} not found")
    if row["undone_at"] is None:
        conn.execute("UPDATE decisions SET undone_at = ? WHERE id = ?", (_now(), decision_id))
        conn.commit()
    return get_decision(decision_id, conn)


@app.post("/api/upload", response_model=UploadResultOut)
def upload(
    listings: UploadFile = File(...),
    ads: UploadFile = File(...),
    reviews: UploadFile = File(...),
    conn: sqlite3.Connection = Depends(db),
) -> UploadResultOut:
    with tempfile.TemporaryDirectory() as tmp:
        paths, file_names = {}, {}
        for name, f in (("listings", listings), ("ads", ads), ("reviews", reviews)):
            original = Path(f.filename or f"{name}.csv").name
            suffix = Path(original).suffix.lower()
            if suffix not in TEXT_SUFFIXES | SPREADSHEET_SUFFIXES:
                raise HTTPException(
                    400, f"{name.capitalize()} file '{original}': unsupported file type '{suffix}'. Upload {ACCEPTED}."
                )
            path = Path(tmp) / f"{name}{suffix}"
            path.write_bytes(f.file.read())
            paths[name] = path
            file_names[name] = original
        try:
            counts = ingest_csvs(conn, paths["listings"], paths["ads"], paths["reviews"], file_names)
        except CsvValidationError as e:
            raise HTTPException(400, str(e)) from e
        except sqlite3.IntegrityError as e:
            raise HTTPException(400, f"CSV has duplicate rows: {e}") from e

    return UploadResultOut(**counts, snapshot=_snapshot_out(latest_snapshot(conn)))


@app.post("/api/reset", response_model=AuditResultOut)
def reset_to_sample(conn: sqlite3.Connection = Depends(db)) -> AuditResultOut:
    """Reloads and audits the bundled sample data in one step, dropping uploads and decisions."""
    clear_ingested_data(conn)
    ingest_csvs(conn, *(SEED_DIR / f"{n}.csv" for n in SAMPLE_FILES))
    count = run_audit(conn, load_config(), allow_ai=False)
    _fill_ai_drafts_in_background()
    return AuditResultOut(issues_computed=count, snapshot=_snapshot_out(latest_snapshot(conn)))


@app.post("/api/audit/run", response_model=AuditResultOut)
def audit_run(conn: sqlite3.Connection = Depends(db)) -> AuditResultOut:
    if latest_snapshot(conn) is None:
        raise HTTPException(409, "Upload data before running an audit")
    count = run_audit(conn, load_config(), allow_ai=False)
    _fill_ai_drafts_in_background()
    return AuditResultOut(issues_computed=count, snapshot=_snapshot_out(latest_snapshot(conn)))


@app.post("/api/settings/ai", response_model=AiSettingOut)
def set_ai_setting(body: AiSettingIn, conn: sqlite3.Connection = Depends(db)) -> AiSettingOut:
    set_ai_enabled(conn, body.enabled)
    cfg = load_config()
    if body.enabled and ai_available(cfg):
        _fill_ai_drafts_in_background()
        updated = 0
    else:
        updated = refresh_ai_dependent_text(conn, cfg)
    return AiSettingOut(enabled=body.enabled, available=ai_available(cfg), updated_count=updated)
