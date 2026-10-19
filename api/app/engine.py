from collections import defaultdict
from dataclasses import dataclass

from app.config import load_config
from app.detectors import detect_all
from app.impact import cap_listing_total, compute_impact_inr, compute_severity, explain_impact
from app.metrics import AdRow, ListingMetrics, ListingRow, ReviewRow, compute_metrics


@dataclass
class ComputedIssue:
    sku: str
    platform: str
    brand: str
    code: str
    severity: str
    impact_inr: float
    evidence: dict
    impact_calc_text: str = ""


def group_by_sku_platform(rows: list[ListingRow]) -> dict[tuple[str, str], list[ListingRow]]:
    grouped: dict[tuple[str, str], list[ListingRow]] = defaultdict(list)
    for r in rows:
        grouped[(r.sku, r.platform)].append(r)
    return grouped


def build_metrics_map(
    listings: list[ListingRow], ads: list[AdRow], reviews: list[ReviewRow]
) -> dict[tuple[str, str], ListingMetrics]:
    grouped = group_by_sku_platform(listings)
    result: dict[tuple[str, str], ListingMetrics] = {}

    for (sku, platform), rows in grouped.items():
        rows_sorted = sorted(rows, key=lambda r: r.snapshot_date)
        latest = rows_sorted[-1]
        previous = rows_sorted[-2] if len(rows_sorted) > 1 else None

        other_platform_name = "Flipkart" if platform == "Amazon" else "Amazon"
        other_rows = grouped.get((sku, other_platform_name))
        other_platform = (
            sorted(other_rows, key=lambda r: r.snapshot_date)[-1] if other_rows else None
        )

        result[(sku, platform)] = compute_metrics(latest, previous, other_platform, ads, reviews)

    return result


def run_engine(
    listings: list[ListingRow], ads: list[AdRow], reviews: list[ReviewRow]
) -> tuple[dict[tuple[str, str], ListingMetrics], list[ComputedIssue]]:
    cfg = load_config()
    metrics_map = build_metrics_map(listings, ads, reviews)

    issues: list[ComputedIssue] = []
    for (sku, platform), m in metrics_map.items():
        for raw in detect_all(m, cfg):
            impact = compute_impact_inr(raw, m, cfg)
            severity = compute_severity(raw.code, impact, cfg)
            issues.append(
                ComputedIssue(
                    sku=sku,
                    platform=platform,
                    brand=m.brand,
                    code=raw.code,
                    severity=severity,
                    impact_inr=round(impact, 2),
                    evidence=raw.evidence,
                    impact_calc_text=explain_impact(raw, m, cfg),
                )
            )
    return metrics_map, issues


def portfolio_capped_totals(
    metrics_map: dict[tuple[str, str], ListingMetrics], issues: list[ComputedIssue]
) -> dict[tuple[str, str], float]:
    by_listing: dict[tuple[str, str], list[float]] = defaultdict(list)
    for issue in issues:
        by_listing[(issue.sku, issue.platform)].append(issue.impact_inr)

    capped: dict[tuple[str, str], float] = {}
    for key, impacts in by_listing.items():
        capped[key] = round(cap_listing_total(impacts, metrics_map[key]), 2)
    return capped
