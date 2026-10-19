ISSUE_LABELS = {
    "oos_ads_live": "Out of stock with ads running",
    "low_stock_high_spend": "Low stock with high ad spend",
    "price_mismatch": "Price mismatch across platforms",
    "price_above_mrp": "Price above MRP",
    "price_shock": "Sudden price change",
    "weak_content": "Weak listing content",
    "rating_drop": "Rating drop",
    "lost_buybox": "Lost Buy Box",
    "ad_waste": "Ad waste",
    "suppressed": "Suppressed or inactive listing",
}

RULE_IDS = {
    "oos_ads_live": "OOS-ADS-01",
    "low_stock_high_spend": "LOW-STOCK-01",
    "price_mismatch": "PRICE-GAP-01",
    "price_above_mrp": "PRICE-MRP-01",
    "price_shock": "PRICE-SHOCK-01",
    "weak_content": "CONTENT-01",
    "rating_drop": "RATING-01",
    "lost_buybox": "BUYBOX-01",
    "ad_waste": "AD-WASTE-01",
    "suppressed": "STATUS-01",
}

# Who acts on an approved fix: the brand's own team, or Intent Farm's internal team
# (ads, content, marketplace ops). Decides the shape of the copy-ready message.
RECIPIENTS = {
    "oos_ads_live": "internal",
    "low_stock_high_spend": "brand",
    "price_mismatch": "brand",
    "price_above_mrp": "brand",
    "price_shock": "brand",
    "weak_content": "internal",
    "rating_drop": "brand",
    "lost_buybox": "brand",
    "ad_waste": "internal",
    "suppressed": "internal",
}

INTERNAL_TEAMS = {
    "oos_ads_live": "Ads",
    "weak_content": "Content",
    "ad_waste": "Ads",
    "suppressed": "Marketplace Ops",
}


def inr(value: float) -> str:
    """Indian digit grouping: 1240 -> '₹1,240', 124000 -> '₹1,24,000'."""
    negative = value < 0
    digits = f"{abs(round(value)):d}"
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        digits = ",".join(groups) + "," + tail
    return f"{'-' if negative else ''}₹{digits}"


def _pct(value: float) -> str:
    return f"{value * 100:+.0f}%"


def _pt(label: str, value: str, bad: bool = False) -> dict:
    return {"label": label, "value": value, "bad": bad}


def evidence_points(code: str, platform: str, e: dict) -> list[dict]:
    """2-4 label:value points per card; `bad` marks the value that tripped the rule."""
    if code == "oos_ads_live":
        return [
            _pt("Stock", f"{e['stock']:.0f}", bad=True),
            _pt("Ad spend", f"{inr(e['avg_daily_spend'])}/day", bad=True),
            _pt("Daily sales avg", inr(e["avg_daily_sales"])),
        ]
    if code == "low_stock_high_spend":
        return [
            _pt("Stock", f"{e['stock']:.0f}"),
            _pt("Days of cover", f"{e['days_cover']:.1f}", bad=True),
            _pt("Ad spend", f"{inr(e['avg_daily_spend'])}/day"),
        ]
    if code == "price_mismatch":
        return [
            _pt(platform, inr(e["this_platform_price"]), bad=True),
            _pt(e["other_platform"], inr(e["other_platform_price"])),
            _pt("Gap", _pct(e["gap_pct"]), bad=True),
        ]
    if code == "price_above_mrp":
        return [
            _pt("Price", inr(e["price"]), bad=True),
            _pt("MRP", inr(e["mrp"])),
            _pt("Over MRP by", inr(e["price"] - e["mrp"]), bad=True),
        ]
    if code == "price_shock":
        return [
            _pt("Previous", inr(e["previous_price"])),
            _pt("Current", inr(e["current_price"]), bad=True),
            _pt("Change", _pct(e["change_pct"]), bad=True),
        ]
    if code == "weak_content":
        return [_pt("Gap", p, bad=True) for p in e["problems"][:4]]
    if code == "rating_drop":
        fired_by = e.get("fired_by", [])
        points = [_pt("Rating", f"{e['current_rating']:.1f}★")]
        if e.get("rating_delta") is not None:
            points.append(_pt("Change", f"{e['rating_delta']:+.1f}", bad="snapshot_drop" in fired_by))
        points.append(_pt("1-2★ reviews (7d)", str(e["low_star_count_7d"]), bad="low_star_spike" in fired_by))
        return points
    if code == "lost_buybox":
        owner_label = "Buy Box owner" if platform == "Amazon" else "Featured seller"
        return [
            _pt(owner_label, e["actual_owner"], bad=True),
            _pt("Expected", e["expected_owner"]),
        ]
    if code == "ad_waste":
        roas = e.get("roas")
        return [
            _pt("Ad spend", f"{inr(e['avg_daily_spend'])}/day"),
            _pt("Orders (7d)", str(e["orders_7d"]), bad=e["orders_7d"] == 0),
            _pt("ROAS", "n/a" if roas is None else f"{roas:.2f}", bad=roas is not None and roas < e["target_roas"]),
            _pt("Target ROAS", f"{e['target_roas']:.1f}"),
        ]
    if code == "suppressed":
        return [_pt("Status", e["status"], bad=True)]
    return []


def compose_message(code: str, sku: str, platform: str, brand: str, impact_inr: float, fix_text: str) -> str:
    """The copy-ready text produced on Approve. Brand-facing issues become a message to
    the brand; internal ones become a task entry for the owning Intent Farm team."""
    label = ISSUE_LABELS.get(code, code)
    if RECIPIENTS.get(code) == "brand":
        return (
            f"Hi {brand} team,\n\n"
            f"Flagging {sku} on {platform}: {label.lower()}, costing an estimated "
            f"{inr(impact_inr)}/day.\n\n"
            f"{fix_text}\n\n"
            f"Could you confirm once this is actioned?\n\n"
            f"Thanks,\nIntent Farm"
        )
    team = INTERNAL_TEAMS.get(code, "Marketplace Ops")
    return (
        f"TASK [{team}] {brand} / {sku} / {platform}\n"
        f"Issue: {label} (est. {inr(impact_inr)}/day)\n"
        f"Action: {fix_text}"
    )
