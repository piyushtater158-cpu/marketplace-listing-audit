import csv
import io
import re
from datetime import date, datetime
from pathlib import Path

from python_calamine import CalamineError, CalamineWorkbook

from app.metrics import AdRow, ListingRow, ReviewRow

LISTING_COLUMNS = [
    "snapshot_date", "brand", "sku", "platform", "title", "bullet_count", "image_count",
    "price", "mrp", "stock", "rating", "review_count", "buybox_owner", "category",
    "status", "units_sold_7d",
]
AD_COLUMNS = ["date", "sku", "platform", "spend", "clicks", "orders", "sales"]
REVIEW_COLUMNS = ["sku", "platform", "review_date", "stars", "text"]


class CsvValidationError(ValueError):
    """Raised for an upload the AM can fix: wrong file type, wrong headers, no rows, or an
    unparseable value. Covers CSV and spreadsheet files alike."""


TEXT_SUFFIXES = {".csv", ".txt", ".tsv", ""}
SPREADSHEET_SUFFIXES = {".xlsx", ".xlsm", ".xls", ".xlsb", ".ods"}
ACCEPTED = "CSV, Excel (.xlsx, .xls) or OpenDocument (.ods)"
# xlsx/xlsm/ods are zip containers; legacy .xls is an OLE2 compound file.
_SPREADSHEET_MAGIC = (b"PK\x03\x04", b"\xd0\xcf\x11\xe0")
# Real exports put a report title or blank lines above the header row.
_HEADER_SEARCH_ROWS = 20


def _column_key(header) -> str:
    """'Snapshot Date', 'snapshot-date' and ' snapshot_date ' all read as snapshot_date."""
    return re.sub(r"[^a-z0-9]+", "_", str(header).strip().lower()).strip("_")


def _cell_text(value) -> str:
    """Spreadsheet cells arrive typed: a stock of 200 reads as 200.0 and dates as date
    objects. Everything becomes the same text a CSV would have held."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _csv_grid(path: Path, label: str) -> list[tuple[str, list[list[str]]]]:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "cp1252"):  # Excel's plain "CSV" on Windows is cp1252
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise CsvValidationError(f"{label}: file is not readable text")
    sample = next((line for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")), "")
    delimiter = max((",", ";", "\t"), key=sample.count) if sample else ","
    return [("", list(csv.reader(io.StringIO(text), delimiter=delimiter)))]


def _spreadsheet_grid(path: Path, label: str) -> list[tuple[str, list[list[str]]]]:
    try:
        workbook = CalamineWorkbook.from_filelike(io.BytesIO(path.read_bytes()))
        return [
            (name, [[_cell_text(c) for c in row] for row in workbook.get_sheet_by_name(name).to_python()])
            for name in workbook.sheet_names
        ]
    except (CalamineError, ValueError, OSError) as e:
        raise CsvValidationError(f"{label}: could not read the spreadsheet ({e})") from e


def _grid(path: Path, label: str) -> list[tuple[str, list[list[str]]]]:
    """(sheet name, rows of cell text) for every sheet; a CSV is one unnamed sheet."""
    with open(path, "rb") as f:
        head = f.read(8)
    suffix = path.suffix.lower()
    if head.startswith(_SPREADSHEET_MAGIC) or suffix in SPREADSHEET_SUFFIXES:
        return _spreadsheet_grid(path, label)
    if suffix in TEXT_SUFFIXES:
        return _csv_grid(path, label)
    raise CsvValidationError(f"{label}: unsupported file type '{suffix}'. Upload {ACCEPTED}.")


def _read_rows(path: Path, required: list[str], label: str) -> list[dict]:
    """Rows as {column: text} from the first sheet whose header row has every required
    column. Lines starting with # are comments; fully blank rows are skipped. Each row
    carries its 1-based position in the file as '_row' for error messages."""
    sheets = _grid(path, label)
    best_missing, best_found = required, -1
    for sheet, grid in sheets:
        for idx, row in enumerate(grid[:_HEADER_SEARCH_ROWS]):
            keys = [_column_key(c) for c in row]
            missing = [c for c in required if c not in keys]
            found = len(required) - len(missing)
            if found > best_found:
                best_missing, best_found = missing, found
            if missing:
                continue
            position = {c: keys.index(c) for c in required}
            rows = []
            for line_no, cells in enumerate(grid[idx + 1 :], start=idx + 2):
                values = [str(c).strip() for c in cells]
                if not any(values) or values[0].startswith("#"):
                    continue
                rows.append(
                    {c: (values[i] if i < len(values) else "") for c, i in position.items()}
                    | {"_row": f"{f'sheet {sheet!r} ' if len(sheets) > 1 else ''}row {line_no}"}
                )
            if not rows:
                raise CsvValidationError(f"{label}: no data rows")
            return rows

    where = f" (checked sheets: {', '.join(name for name, _ in sheets)})" if len(sheets) > 1 else ""
    raise CsvValidationError(f"{label}: missing column(s) {', '.join(best_missing)}{where}")


_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d-%b-%Y", "%d %b %Y", "%Y/%m/%d")


def _iso_date(value: str) -> str:
    """Indian exports write day-first (19/10/2026, 19-Oct-2026); stored dates are ISO."""
    text = value.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"date {value!r} is not like 2026-10-19 or 19/10/2026")


def _platform(value: str) -> str:
    known = {"amazon": "Amazon", "flipkart": "Flipkart"}
    return known.get(value.strip().lower(), value.strip())


def _parse(rows: list[dict], label: str, build):
    out = []
    for r in rows:
        try:
            out.append(build(r))
        except ValueError as e:
            raise CsvValidationError(f"{label}: {r['_row']} has an invalid value ({e})") from e
    return out


def parse_listings(path: Path, label: str = "listings.csv") -> list[ListingRow]:
    return _parse(
        _read_rows(path, LISTING_COLUMNS, label),
        label,
        lambda r: ListingRow(
            snapshot_date=_iso_date(r["snapshot_date"]),
            brand=r["brand"],
            sku=r["sku"],
            platform=_platform(r["platform"]),
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


def parse_ads(path: Path, label: str = "ads.csv") -> list[AdRow]:
    return _parse(
        _read_rows(path, AD_COLUMNS, label),
        label,
        lambda r: AdRow(
            date=_iso_date(r["date"]),
            sku=r["sku"],
            platform=_platform(r["platform"]),
            spend=float(r["spend"]),
            clicks=int(r["clicks"]),
            orders=int(r["orders"]),
            sales=float(r["sales"]),
        ),
    )


def parse_reviews(path: Path, label: str = "reviews.csv") -> list[ReviewRow]:
    return _parse(
        _read_rows(path, REVIEW_COLUMNS, label),
        label,
        lambda r: ReviewRow(
            sku=r["sku"],
            platform=_platform(r["platform"]),
            review_date=_iso_date(r["review_date"]),
            stars=int(r["stars"]),
            text=r["text"],
        ),
    )
