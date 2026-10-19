import pytest

from app.config import load_config
from app.detectors import RawIssue
from app.impact import cap_listing_total, compute_impact_inr, compute_severity
from app.metrics import ListingRow, ListingMetrics


def _listing_row(**overrides) -> ListingRow:
    base = dict(
        snapshot_date="2026-10-19",
        brand="GlowVeda",
        sku="TEST-001",
        platform="Amazon",
        title="Healthy Title With Enough Characters To Clear The Minimum",
        bullet_count=6,
        image_count=6,
        price=500.0,
        mrp=550.0,
        stock=50,
        rating=4.3,
        review_count=100,
        buybox_owner="GlowVeda Official Store",
        category="skincare",
        status="active",
        units_sold_7d=56.0,
    )
    base.update(overrides)
    return ListingRow(**base)


def _metrics(**overrides) -> ListingMetrics:
    latest = overrides.pop("latest", _listing_row())
    base = dict(
        sku=latest.sku,
        platform=latest.platform,
        brand=latest.brand,
        latest=latest,
        previous=None,
        other_platform=None,
        avg_daily_spend=200.0,
        avg_daily_sales=500.0,
        avg_daily_units=8.0,
        roas=2.5,
        days_cover=6.0,
        price_delta_pct=None,
        price_change_pct=None,
        rating_delta=None,
        low_star_count_7d=0,
        orders_7d=5,
    )
    base.update(overrides)
    return ListingMetrics(**base)


@pytest.fixture(scope="module")
def cfg():
    return load_config()


def test_oos_ads_live_impact_is_full_spend_plus_sales(cfg):
    m = _metrics(avg_daily_spend=200.0, avg_daily_sales=500.0)
    issue = RawIssue("oos_ads_live", {})
    assert compute_impact_inr(issue, m, cfg) == pytest.approx(700.0)


def test_low_stock_ramps_linearly_to_zero_at_threshold(cfg):
    th = cfg["thresholds"]["low_stock_days"]
    m = _metrics(avg_daily_sales=300.0, days_cover=th)  # exactly at threshold
    issue = RawIssue("low_stock_high_spend", {})
    assert compute_impact_inr(issue, m, cfg) == pytest.approx(0.0)

    m_zero_cover = _metrics(avg_daily_sales=300.0, days_cover=0.0)
    assert compute_impact_inr(issue, m_zero_cover, cfg) == pytest.approx(300.0)


def test_price_mismatch_is_capped_at_that_platforms_own_sales(cfg):
    m = _metrics(avg_daily_sales=100.0)
    issue = RawIssue("price_mismatch", {"gap_pct": 5.0})  # absurdly large gap on purpose
    impact = compute_impact_inr(issue, m, cfg)
    assert impact == pytest.approx(100.0)  # capped, not 100*5*elasticity


def test_price_above_mrp_is_forced_critical_regardless_of_impact_size(cfg):
    m = _metrics(avg_daily_sales=1.0)  # tiny sales -> tiny raw impact
    issue = RawIssue("price_above_mrp", {})
    impact = compute_impact_inr(issue, m, cfg)
    assert impact < 10  # confirm this really is a small number
    assert compute_severity("price_above_mrp", impact, cfg) == "critical"


def test_suppressed_is_forced_critical_regardless_of_impact_size(cfg):
    assert compute_severity("suppressed", 1.0, cfg) == "critical"


def test_severity_bands_follow_config_thresholds(cfg):
    bands = cfg["severity_bands_inr_per_day"]
    assert compute_severity("ad_waste", bands["critical"], cfg) == "critical"
    assert compute_severity("ad_waste", bands["high"], cfg) == "high"
    assert compute_severity("ad_waste", bands["medium"], cfg) == "medium"
    assert compute_severity("ad_waste", bands["medium"] - 1, cfg) == "low"


def test_ad_waste_uses_full_spend_when_zero_orders(cfg):
    m = _metrics(avg_daily_spend=400.0, avg_daily_sales=0.0)
    issue = RawIssue("ad_waste", {"orders_7d": 0})
    assert compute_impact_inr(issue, m, cfg) == pytest.approx(400.0)


def test_ad_waste_uses_roas_gap_when_orders_nonzero(cfg):
    target_roas = cfg["thresholds"]["target_roas"]
    m = _metrics(avg_daily_spend=400.0, avg_daily_sales=300.0)
    issue = RawIssue("ad_waste", {"orders_7d": 2})
    expected = max(0.0, 400.0 - 300.0 / target_roas)
    assert compute_impact_inr(issue, m, cfg) == pytest.approx(expected)


def test_price_shock_impact_is_units_times_price_delta(cfg):
    latest = _listing_row(price=750.0)
    previous = _listing_row(price=1000.0)
    m = _metrics(latest=latest, previous=previous, avg_daily_units=10.0)
    issue = RawIssue("price_shock", {})
    assert compute_impact_inr(issue, m, cfg) == pytest.approx(10.0 * 250.0)


def test_cap_listing_total_caps_a_stacked_listing_at_spend_plus_sales(cfg):
    m = _metrics(avg_daily_spend=200.0, avg_daily_sales=500.0)
    # three issues whose raw sum (700 + 200 + 500) comfortably exceeds the 700 cap
    capped = cap_listing_total([700.0, 200.0, 500.0], m)
    assert capped == pytest.approx(700.0)


def test_cap_listing_total_is_a_no_op_when_under_the_cap(cfg):
    m = _metrics(avg_daily_spend=200.0, avg_daily_sales=500.0)
    capped = cap_listing_total([50.0, 75.0], m)
    assert capped == pytest.approx(125.0)
