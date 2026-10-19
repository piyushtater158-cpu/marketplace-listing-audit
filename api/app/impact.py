from app.detectors import RawIssue
from app.metrics import ListingMetrics
from app.present import inr

FORCED_CRITICAL = {"price_above_mrp", "suppressed"}


def compute_impact_inr(issue: RawIssue, m: ListingMetrics, cfg: dict) -> float:
    f = cfg["impact_factors"]
    th = cfg["thresholds"]
    code = issue.code

    if code == "oos_ads_live":
        return m.avg_daily_spend + m.avg_daily_sales

    if code == "low_stock_high_spend":
        ramp = (th["low_stock_days"] - m.days_cover) / th["low_stock_days"]
        return max(0.0, m.avg_daily_sales * ramp)

    if code == "price_mismatch":
        raw = m.avg_daily_sales * issue.evidence["gap_pct"] * f["price_mismatch_elasticity"]
        return min(max(0.0, raw), m.avg_daily_sales)

    if code == "price_above_mrp":
        return m.avg_daily_sales * f["above_mrp_risk"]

    if code == "price_shock":
        price_delta = abs(m.latest.price - m.previous.price)
        return m.avg_daily_units * price_delta

    if code == "weak_content":
        n = len(issue.evidence["problems"])
        raw = m.avg_daily_sales * f["content_gap_uplift_per_element"] * n
        return min(raw, m.avg_daily_sales)

    if code == "rating_drop":
        magnitude = abs(m.rating_delta) if (m.rating_delta is not None and m.rating_delta <= -th["rating_drop_threshold"]) else th["rating_drop_threshold"]
        units = magnitude / th["rating_drop_threshold"]
        return m.avg_daily_sales * f["rating_penalty_per_unit"] * units

    if code == "lost_buybox":
        return m.avg_daily_spend + m.avg_daily_sales * f["buybox_loss_factor"]

    if code == "ad_waste":
        if issue.evidence.get("orders_7d") == 0:
            return m.avg_daily_spend
        return max(0.0, m.avg_daily_spend - m.avg_daily_sales / th["target_roas"])

    if code == "suppressed":
        return m.avg_daily_spend + m.avg_daily_sales

    raise ValueError(f"unknown issue code: {code}")


def explain_impact(issue: RawIssue, m: ListingMetrics, cfg: dict) -> str:
    """One line showing how impact_inr was built, with the real numbers. Mirrors
    compute_impact_inr branch for branch."""
    f = cfg["impact_factors"]
    th = cfg["thresholds"]
    spend, sales = inr(m.avg_daily_spend), inr(m.avg_daily_sales)
    code = issue.code

    if code == "oos_ads_live":
        return f"{spend} ad spend wasted + {sales} daily sales lost"
    if code == "low_stock_high_spend":
        return (
            f"{sales} daily sales × ({th['low_stock_days']} − {m.days_cover:.1f} days cover) "
            f"÷ {th['low_stock_days']} days"
        )
    if code == "price_mismatch":
        return (
            f"{sales} daily sales × {issue.evidence['gap_pct'] * 100:.0f}% price gap × "
            f"{f['price_mismatch_elasticity']} elasticity"
        )
    if code == "price_above_mrp":
        return f"{sales} daily sales × {f['above_mrp_risk']} at risk of delisting"
    if code == "price_shock":
        delta = abs(m.latest.price - m.previous.price)
        return f"{m.avg_daily_units:.1f} units/day × {inr(delta)} price change"
    if code == "weak_content":
        n = len(issue.evidence["problems"])
        return (
            f"{sales} daily sales × {f['content_gap_uplift_per_element'] * 100:.0f}% uplift × "
            f"{n} content gap{'s' if n != 1 else ''}"
        )
    if code == "rating_drop":
        dropped = m.rating_delta is not None and m.rating_delta <= -th["rating_drop_threshold"]
        magnitude = abs(m.rating_delta) if dropped else th["rating_drop_threshold"]
        return (
            f"{sales} daily sales × {f['rating_penalty_per_unit'] * 100:.0f}% per "
            f"{th['rating_drop_threshold']}★ × {magnitude / th['rating_drop_threshold']:.1f}"
        )
    if code == "lost_buybox":
        return f"{spend} ad spend + {sales} daily sales × {f['buybox_loss_factor']} lost share"
    if code == "ad_waste":
        if issue.evidence.get("orders_7d") == 0:
            return f"{spend} ad spend with zero orders"
        return f"{spend} ad spend − {sales} sales ÷ {th['target_roas']} target ROAS"
    if code == "suppressed":
        return f"{spend} ad spend wasted + {sales} daily sales lost"
    raise ValueError(f"unknown issue code: {code}")


def compute_severity(issue_code: str, impact_inr: float, cfg: dict) -> str:
    if issue_code in FORCED_CRITICAL:
        return "critical"
    bands = cfg["severity_bands_inr_per_day"]
    if impact_inr >= bands["critical"]:
        return "critical"
    if impact_inr >= bands["high"]:
        return "high"
    if impact_inr >= bands["medium"]:
        return "medium"
    return "low"


def cap_listing_total(impacts_inr: list[float], m: ListingMetrics) -> float:
    """The maximum actually recoverable from one listing per day — prevents a listing
    that fires OOS + ad-waste + lost-buybox from counting its own wasted spend three
    times in the portfolio headline total. Per-issue ranking in the queue stays uncapped."""
    cap = m.avg_daily_spend + m.avg_daily_sales
    return min(sum(impacts_inr), cap)
