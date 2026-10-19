from app.ai import cluster_complaints, explain_ad_waste, rewrite_content
from app.detectors import RawIssue, title_problems
from app.metrics import ListingMetrics
from app.present import RECIPIENTS

AI_ENHANCED_CODES = {"weak_content", "rating_drop", "ad_waste"}


def _rule_based_fix(issue: RawIssue, m: ListingMetrics) -> str:
    e = issue.evidence
    if issue.code == "oos_ads_live":
        return (
            f"Pause the {m.platform} ad campaign for {m.sku} until restock — currently "
            f"burning ₹{e['avg_daily_spend']:.0f}/day with zero fulfillable orders."
        )
    if issue.code == "low_stock_high_spend":
        return (
            f"Reorder stock for {m.sku} now — {e['days_cover']:.1f} days of cover left "
            f"at current ad spend of ₹{e['avg_daily_spend']:.0f}/day."
        )
    if issue.code == "price_mismatch":
        return (
            f"Align {m.sku}'s {m.platform} price (₹{e['this_platform_price']:.0f}) with "
            f"{e['other_platform']} (₹{e['other_platform_price']:.0f}) — a "
            f"{e['gap_pct'] * 100:.0f}% gap is pushing demand to the cheaper platform."
        )
    if issue.code == "price_above_mrp":
        return (
            f"Price (₹{e['price']:.0f}) exceeds MRP (₹{e['mrp']:.0f}) for {m.sku} on "
            f"{m.platform} — correct immediately, this is a compliance risk in India."
        )
    if issue.code == "price_shock":
        direction = "increase" if e["change_pct"] > 0 else "drop"
        return (
            f"Confirm the {abs(e['change_pct']) * 100:.0f}% price {direction} on {m.sku} "
            f"({m.platform}) was intentional — revert if it was a pricing error."
        )
    if issue.code == "lost_buybox":
        return (
            f"{e['label']} for {m.sku} on {m.platform} — current owner: {e['actual_owner']}. "
            f"Review pricing and fulfillment speed to win it back."
        )
    if issue.code == "suppressed":
        return (
            f"Listing {m.sku} on {m.platform} is {e['status']} — file a reinstatement "
            f"request with {m.platform} seller support immediately."
        )
    raise ValueError(f"no rule-based fix defined for {issue.code}")


def fix_text(fix: dict) -> str:
    """Flat text form of a fix: what gets copied and what goes into the approval message."""
    if fix["kind"] == "content":
        bullets = "\n".join(f"- {b}" for b in fix["bullets"])
        return f"Title: {fix['title']}\n{bullets}"
    return fix["text"]


def suggested_fix(issue: RawIssue, m: ListingMetrics, cfg: dict, ai_enabled: bool) -> tuple[dict, bool]:
    """Returns (fix, ai_generated). A fix is either {kind: 'message', text} or
    {kind: 'content', title, title_note, bullets}, plus recipient and source."""
    recipient = RECIPIENTS.get(issue.code, "internal")

    def done(fix: dict, ai_generated: bool) -> tuple[dict, bool]:
        fix.update(recipient=recipient, source="ai" if ai_generated else "rule")
        return fix, ai_generated

    if issue.code == "weak_content":
        rewrite, ai_generated = rewrite_content(m.brand, m.latest.category, m.latest.title, cfg, ai_enabled)
        title, title_note = rewrite.title, None
        other = m.other_platform
        if not ai_generated and other is not None and not title_problems(other.title, other.category, cfg):
            title, title_note = other.title, f"already live on {other.platform}"
        return done(
            {"kind": "content", "title": title, "title_note": title_note, "bullets": rewrite.bullets},
            ai_generated,
        )

    if issue.code == "rating_drop":
        themes, ai_generated = cluster_complaints(m.reviews, cfg, ai_enabled)
        negative = [t for t in themes.themes if t.polarity == "neg"]
        if negative:
            top = negative[0]
            text = (
                f"Top complaint theme: '{top.theme}' ({top.count} mention(s)) — e.g. "
                f'"{top.example_quote}". Consider a quality-control review with the manufacturer.'
            )
        else:
            text = "Rating dropped but no clear complaint theme found in recent reviews — investigate manually."
        return done({"kind": "message", "text": text}, ai_generated)

    if issue.code == "ad_waste":
        explanation, ai_generated = explain_ad_waste(m, issue.evidence, cfg, ai_enabled)
        return done({"kind": "message", "text": explanation.explanation}, ai_generated)

    return done({"kind": "message", "text": _rule_based_fix(issue, m)}, False)
