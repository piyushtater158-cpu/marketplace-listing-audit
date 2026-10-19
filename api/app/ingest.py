import csv
import io
from pathlib import Path

from app.metrics import AdRow, ListingRow, ReviewRow

LISTING_COLUMNS = [
    "snapshot_date", "brand", "sku", "platform", "title", "bullet_count", "image_count",
    "price", "mrp", "stock", "rating", "review_count", "buybox_owner", "category",
    "status", "units_sold_7d",
]
AD_COLUMNS = ["date", "sku", "platform", "spend", "clicks", "orders", "sales"]
REVIEW_COLUMNS = ["sku", "platform", "review_date", "stars", "text"]


class CsvValidationError(ValueError):
    """Raised for a CSV the AM can fix: wrong headers, no rows, or an unparseable value."""


def _read_rows(path: Path, required: list[str], label: str) -> list[dict]:
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            lines = [line for line in f if not line.lstrip().startswith("#")]
    except UnicodeDecodeError as e:
        raise CsvValidationError(f"{label}: file is not UTF-8 text") from e

    reader = csv.DictReader(io.StringIO("".join(lines)))
    headers = [h.strip() for h in (reader.fieldnames or [])]
    missing = [c for c in required if c not in headers]
    if missing:
        raise CsvValidationError(f"{label}: missing column(s) {', '.join(missing)}")

    rows = [{k.strip(): (v or "").strip() for k, v in r.items() if k} for r in reader]
    if not rows:
        raise CsvValidationError(f"{label}: no data rows")
    return rows


def _parse(rows: list[dict], label: str, build):
    out = []
    for line_no, r in enumerate(rows, start=2):
        try:
            out.append(build(r))
        except ValueError as e:
            raise CsvValidationError(f"{label}: row {line_no} has an invalid value ({e})") from e
    return out


def parse_listings(path: Path) -> list[ListingRow]:
    return _parse(
        _read_rows(path, LISTING_COLUMNS, "listings.csv"),
        "listings.csv",
        lambda r: ListingRow(
            snapshot_date=r["snapshot_date"],
            brand=r["brand"],
            sku=r["sku"],
            platform=r["platform"],
            title=r["title"],
            bullet_count=int(r["bullet_count"]),
            image_count=int(r["image_count"]),
            price=float(r["price"]),
            mrp=float(r["mrp"]),
            stock=float(r["stock"]),
            rating=float(r["rating"]),
            review_count=int(r["review_count"]),
            buybox_owner=r["buybox_owner"],
            category=r["category"],
            status=r["status"],
            units_sold_7d=float(r["units_sold_7d"]),
        ),
    )


def parse_ads(path: Path) -> list[AdRow]:
    return _parse(
        _read_rows(path, AD_COLUMNS, "ads.csv"),
        "ads.csv",
        lambda r: AdRow(
            date=r["date"],
            sku=r["sku"],
            platform=r["platform"],
            spend=float(r["spend"]),
            clicks=int(r["clicks"]),
            orders=int(r["orders"]),
            sales=float(r["sales"]),
        ),
    )


def parse_reviews(path: Path) -> list[ReviewRow]:
    return _parse(
        _read_rows(path, REVIEW_COLUMNS, "reviews.csv"),
        "reviews.csv",
        lambda r: ReviewRow(
            sku=r["sku"],
            platform=r["platform"],
            review_date=r["review_date"],
            stars=int(r["stars"]),
            text=r["text"],
        ),
    )
