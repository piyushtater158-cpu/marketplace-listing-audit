import math
from dataclasses import dataclass, field
from datetime import date, timedelta


@dataclass
class ListingRow:
    snapshot_date: str
    brand: str
    sku: str
    platform: str
    title: str
    bullet_count: int
    image_count: int
    price: float
    mrp: float
    stock: float
    rating: float
    review_count: int
    buybox_owner: str
    category: str
    status: str
    units_sold_7d: float


@dataclass
class AdRow:
    date: str
    sku: str
    platform: str
    spend: float
    clicks: int
    orders: int
    sales: float


@dataclass
class ReviewRow:
    sku: str
    platform: str
    review_date: str
    stars: int
    text: str


@dataclass
class ListingMetrics:
    sku: str
    platform: str
    brand: str
    latest: ListingRow
    previous: ListingRow | None
    other_platform: ListingRow | None
    ads_14d: list[AdRow] = field(default_factory=list)
    reviews: list[ReviewRow] = field(default_factory=list)

    avg_daily_spend: float = 0.0
    avg_daily_sales: float = 0.0
    avg_daily_units: float = 0.0
    roas: float | None = None
    days_cover: float = math.inf
    price_delta_pct: float | None = None
    price_change_pct: float | None = None
    rating_delta: float | None = None
    low_star_count_7d: int = 0
    orders_7d: int = 0


def _window(rows: list[AdRow], as_of: date, days: int) -> list[AdRow]:
    start = as_of - timedelta(days=days - 1)
    return [r for r in rows if start <= date.fromisoformat(r.date) <= as_of]


def compute_metrics(
    latest: ListingRow,
    previous: ListingRow | None,
    other_platform: ListingRow | None,
    ads_all: list[AdRow],
    reviews_all: list[ReviewRow],
) -> ListingMetrics:
    as_of = date.fromisoformat(latest.snapshot_date)

    ads_for_listing = [r for r in ads_all if r.sku == latest.sku and r.platform == latest.platform]
    ads_14d = _window(ads_for_listing, as_of, 14)
    ads_7d = _window(ads_for_listing, as_of, 7)

    total_spend_14d = sum(r.spend for r in ads_14d)
    total_sales_14d = sum(r.sales for r in ads_14d)

    avg_daily_spend = sum(r.spend for r in ads_7d) / 7 if ads_7d else 0.0
    avg_daily_sales = sum(r.sales for r in ads_7d) / 7 if ads_7d else 0.0
    orders_7d = sum(r.orders for r in ads_7d)

    avg_daily_units = latest.units_sold_7d / 7

    roas = (total_sales_14d / total_spend_14d) if total_spend_14d > 0 else None

    days_cover = (latest.stock / avg_daily_units) if avg_daily_units > 0 else math.inf

    price_delta_pct = None
    if other_platform is not None and other_platform.price > 0:
        price_delta_pct = (latest.price - other_platform.price) / other_platform.price

    price_change_pct = None
    rating_delta = None
    if previous is not None:
        if previous.price > 0:
            price_change_pct = (latest.price - previous.price) / previous.price
        rating_delta = latest.rating - previous.rating

    window_start = as_of - timedelta(days=6)
    low_star_count_7d = sum(
        1
        for r in reviews_all
        if r.sku == latest.sku
        and r.platform == latest.platform
        and window_start <= date.fromisoformat(r.review_date) <= as_of
        and r.stars <= 2
    )

    return ListingMetrics(
        sku=latest.sku,
        platform=latest.platform,
        brand=latest.brand,
        latest=latest,
        previous=previous,
        other_platform=other_platform,
        ads_14d=ads_14d,
        reviews=[r for r in reviews_all if r.sku == latest.sku and r.platform == latest.platform],
        avg_daily_spend=avg_daily_spend,
        avg_daily_sales=avg_daily_sales,
        avg_daily_units=avg_daily_units,
        roas=roas,
        days_cover=days_cover,
        price_delta_pct=price_delta_pct,
        price_change_pct=price_change_pct,
        rating_delta=rating_delta,
        low_star_count_7d=low_star_count_7d,
        orders_7d=orders_7d,
    )
