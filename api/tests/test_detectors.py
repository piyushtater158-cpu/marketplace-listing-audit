import json
from pathlib import Path

import pytest

from app.engine import run_engine
from app.ingest import parse_ads, parse_listings, parse_reviews

SEED_DIR = Path(__file__).resolve().parent.parent / "seed"


@pytest.fixture(scope="module")
def engine_result():
    listings = parse_listings(SEED_DIR / "listings.csv")
    ads = parse_ads(SEED_DIR / "ads.csv")
    reviews = parse_reviews(SEED_DIR / "reviews.csv")
    return run_engine(listings, ads, reviews)


@pytest.fixture(scope="module")
def manifest():
    with open(SEED_DIR / "manifest.json", "r", encoding="utf-8") as f:
        return json.load(f)


def _actual_codes_by_pair(issues):
    actual: dict[str, list[str]] = {}
    for issue in issues:
        key = f"{issue.sku}|{issue.platform}"
        actual.setdefault(key, []).append(issue.code)
    return actual


def test_every_manifest_pair_matches_exactly(engine_result, manifest):
    _, issues = engine_result
    actual = _actual_codes_by_pair(issues)

    mismatches = []
    for key, expected_codes in manifest.items():
        actual_codes = sorted(actual.get(key, []))
        if actual_codes != sorted(expected_codes):
            mismatches.append(f"{key}: expected {sorted(expected_codes)}, got {actual_codes}")

    assert not mismatches, "\n".join(mismatches)


def test_no_spurious_pairs_outside_manifest(engine_result, manifest):
    _, issues = engine_result
    actual = _actual_codes_by_pair(issues)
    unexpected_keys = set(actual.keys()) - set(manifest.keys())
    assert not unexpected_keys, f"issues fired for unlisted pairs: {unexpected_keys}"


@pytest.mark.parametrize(
    "code",
    [
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
    ],
)
def test_every_issue_code_fires_at_least_once(engine_result, code):
    _, issues = engine_result
    codes = {issue.code for issue in issues}
    assert code in codes, f"{code} never fired on any seeded listing"


def test_stacked_listing_demonstrates_capping(engine_result):
    from app.engine import portfolio_capped_totals

    metrics_map, issues = engine_result
    by_pair: dict[tuple, list] = {}
    for issue in issues:
        by_pair.setdefault((issue.sku, issue.platform), []).append(issue)

    stacked_pairs = [
        key for key, issue_list in by_pair.items() if len(issue_list) >= 3
    ]
    assert stacked_pairs, "expected at least one listing with 3+ simultaneous issues"

    capped = portfolio_capped_totals(metrics_map, issues)
    for key in stacked_pairs:
        raw_sum = sum(i.impact_inr for i in by_pair[key])
        cap_value = metrics_map[key].avg_daily_spend + metrics_map[key].avg_daily_sales
        assert raw_sum > cap_value, f"{key}: expected raw sum to exceed the cap to prove capping matters"
        assert capped[key] == pytest.approx(cap_value, rel=1e-6)


def test_price_mismatch_only_fires_on_higher_priced_platform(engine_result):
    _, issues = engine_result
    mismatch_issues = [i for i in issues if i.code == "price_mismatch"]
    assert mismatch_issues
    for issue in mismatch_issues:
        assert issue.evidence["gap_pct"] > 0
