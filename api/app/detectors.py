from dataclasses import dataclass

from app.metrics import ListingMetrics

ISSUE_CODES = [
    "oos_ads_live",
    "low_stock_high_spend",
    "price_mismatch",
    "price_above_mrp",
    "price_shock",
    "weak_content",
    "rating_drop",
    "lost_buybox",
    "ad_waste",
    "suppressed",
]


@dataclass
class RawIssue:
    code: str
    evidence: dict


def _detect_oos_ads_live(m: ListingMetrics, cfg: dict) -> RawIssue | None:
    if m.latest.stock <= 0 and m.avg_daily_spend > 0:
        return RawIssue(
            "oos_ads_live",
            {
                "stock": m.latest.stock,
                "avg_daily_spend": round(m.avg_daily_spend, 2),
                "avg_daily_sales": round(m.avg_daily_sales, 2),
            },
        )
    return None


def _detect_low_stock_high_spend(m: ListingMetrics, cfg: dict) -> RawIssue | None:
    th = cfg["thresholds"]
    if m.latest.stock <= 0:
        return None  # out-of-stock is #1, not #2
    if m.days_cover < th["low_stock_days"] and m.avg_daily_spend > th["min_spend_inr"]:
        return RawIssue(
            "low_stock_high_spend",
            {
                "days_cover": round(m.days_cover, 1),
                "stock": m.latest.stock,
                "avg_daily_spend": round(m.avg_daily_spend, 2),
            },
        )
    return None


def _detect_price_mismatch(m: ListingMetrics, cfg: dict) -> RawIssue | None:
    th = cfg["thresholds"]
    if m.other_platform is None or m.price_delta_pct is None:
        return None
    # fire only on the higher-priced platform's row — this is the row "losing" cross-
    # platform demand, and avoids reporting the same gap twice (once per platform).
    if m.price_delta_pct > th["price_gap_pct"]:
        return RawIssue(
            "price_mismatch",
            {
                "this_platform_price": m.latest.price,
                "other_platform": m.other_platform.platform,
                "other_platform_price": m.other_platform.price,
                "gap_pct": round(m.price_delta_pct, 3),
            },
        )
    return None


def _detect_price_above_mrp(m: ListingMetrics, cfg: dict) -> RawIssue | None:
    if m.latest.price > m.latest.mrp:
        return RawIssue(
            "price_above_mrp",
            {"price": m.latest.price, "mrp": m.latest.mrp},
        )
    return None


def _detect_price_shock(m: ListingMetrics, cfg: dict) -> RawIssue | None:
    th = cfg["thresholds"]
    if m.previous is None or m.price_change_pct is None:
        return None
    if abs(m.price_change_pct) > th["price_shock_pct"]:
        return RawIssue(
            "price_shock",
            {
                "previous_price": m.previous.price,
                "current_price": m.latest.price,
                "change_pct": round(m.price_change_pct, 3),
            },
        )
    return None


def title_problems(title: str, category: str, cfg: dict) -> list[str]:
    th = cfg["thresholds"]
    problems = []
    title_len = len(title)
    if title_len < th["title_min_chars"]:
        problems.append(f"title too short ({title_len} chars)")
    elif title_len > th["title_max_chars"]:
        problems.append(f"title too long ({title_len} chars)")

    keywords = cfg["category_keywords"].get(category, [])
    if keywords and not any(kw.lower() in title.lower() for kw in keywords):
        problems.append("no category keyword in title")
    return problems


def _detect_weak_content(m: ListingMetrics, cfg: dict) -> RawIssue | None:
    th = cfg["thresholds"]
    problems = title_problems(m.latest.title, m.latest.category, cfg)

    if m.latest.image_count < th["min_images"]:
        problems.append(f"only {m.latest.image_count} images")

    if m.latest.bullet_count < th["min_bullets"]:
        problems.append(f"only {m.latest.bullet_count} bullets")

    if problems:
        return RawIssue(
            "weak_content",
            {"problems": problems, "title": m.latest.title},
        )
    return None


def _detect_rating_drop(m: ListingMetrics, cfg: dict) -> RawIssue | None:
    th = cfg["thresholds"]
    fired_by = []
    if m.rating_delta is not None and m.rating_delta <= -th["rating_drop_threshold"]:
        fired_by.append("snapshot_drop")
    if m.low_star_count_7d >= th["low_star_spike_count"]:
        fired_by.append("low_star_spike")
    if fired_by:
        return RawIssue(
            "rating_drop",
            {
                "rating_delta": round(m.rating_delta, 2) if m.rating_delta is not None else None,
                "low_star_count_7d": m.low_star_count_7d,
                "current_rating": m.latest.rating,
                "fired_by": fired_by,
            },
        )
    return None


def _detect_lost_buybox(m: ListingMetrics, cfg: dict) -> RawIssue | None:
    brand_cfg = cfg["brands"].get(m.brand, {})
    seller_name = brand_cfg.get("seller_name")
    if seller_name is None:
        return None
    if m.latest.buybox_owner != seller_name:
        label = "Lost Buy Box" if m.platform == "Amazon" else "Not the featured seller"
        return RawIssue(
            "lost_buybox",
            {
                "label": label,
                "expected_owner": seller_name,
                "actual_owner": m.latest.buybox_owner,
            },
        )
    return None


def _detect_ad_waste(m: ListingMetrics, cfg: dict) -> RawIssue | None:
    th = cfg["thresholds"]
    if m.avg_daily_spend <= th["min_spend_inr"]:
        return None
    zero_orders = m.orders_7d == 0
    low_roas = m.roas is not None and m.roas < th["target_roas"]
    if zero_orders or low_roas:
        return RawIssue(
            "ad_waste",
            {
                "avg_daily_spend": round(m.avg_daily_spend, 2),
                "orders_7d": m.orders_7d,
                "roas": round(m.roas, 2) if m.roas is not None else None,
                "target_roas": th["target_roas"],
            },
        )
    return None


def _detect_suppressed(m: ListingMetrics, cfg: dict) -> RawIssue | None:
    if m.latest.status.lower() in cfg["inactive_statuses"]:
        return RawIssue("suppressed", {"status": m.latest.status})
    return None


_ALL_DETECTORS = [
    _detect_oos_ads_live,
    _detect_low_stock_high_spend,
    _detect_price_mismatch,
    _detect_price_above_mrp,
    _detect_price_shock,
    _detect_weak_content,
    _detect_rating_drop,
    _detect_lost_buybox,
    _detect_ad_waste,
    _detect_suppressed,
]


def detect_all(m: ListingMetrics, cfg: dict) -> list[RawIssue]:
    issues = []
    for detector in _ALL_DETECTORS:
        result = detector(m, cfg)
        if result is not None:
            issues.append(result)
    return issues
