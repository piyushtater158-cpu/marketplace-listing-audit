import pytest

from app.ai import (
    brand_summary_fallback,
    cluster_complaints,
    explain_ad_waste,
    rewrite_content,
)
from app.config import load_config
from app.metrics import ReviewRow


@pytest.fixture(scope="module")
def cfg():
    return load_config()


def test_rewrite_content_fallback_hits_length_window_and_keyword(cfg):
    th = cfg["thresholds"]
    rewrite, ai_generated = rewrite_content(
        "GlowVeda", "skincare", "x", cfg, ai_enabled=False
    )
    assert ai_generated is False
    assert th["title_min_chars"] <= len(rewrite.title) <= th["title_max_chars"]
    assert len(rewrite.bullets) == 5
    assert "serum" in rewrite.title.lower() or "cream" in rewrite.title.lower() or "skin" in rewrite.title.lower()


def test_cluster_complaints_fallback_finds_hinglish_themes(cfg):
    reviews = [
        ReviewRow("SKU-1", "Amazon", "2026-10-15", 1, "Product tuta hua aaya, bahut disappointing."),
        ReviewRow("SKU-1", "Amazon", "2026-10-16", 1, "Lagta hai nakli product bheja hai."),
        ReviewRow("SKU-1", "Amazon", "2026-10-17", 2, "Ghatiya packaging ki wajah se box leak ho gaya."),
        ReviewRow("SKU-1", "Amazon", "2026-10-10", 5, "Great product, works well."),
    ]
    themes, ai_generated = cluster_complaints(reviews, cfg, ai_enabled=False)
    assert ai_generated is False
    theme_names = {t.theme for t in themes.themes}
    assert "damaged" in theme_names
    assert "fake" in theme_names
    assert "packaging" in theme_names
    assert "Great product" not in " ".join(t.example_quote for t in themes.themes if t.polarity == "neg")


def test_cluster_complaints_fallback_turns_praise_into_positive_themes_only(cfg):
    reviews = [ReviewRow("SKU-1", "Amazon", "2026-10-15", 5, "Bahut acha product hai, paisa vasool!")]
    themes, _ = cluster_complaints(reviews, cfg, ai_enabled=False)
    assert themes.themes
    assert {t.polarity for t in themes.themes} == {"pos"}


def test_cluster_complaints_fallback_lists_complaints_before_praise(cfg):
    reviews = [
        ReviewRow("SKU-1", "Amazon", "2026-10-15", 5, "Great value for money, will buy again."),
        ReviewRow("SKU-1", "Amazon", "2026-10-16", 1, "Product tuta hua aaya, bahut disappointing."),
    ]
    themes, _ = cluster_complaints(reviews, cfg, ai_enabled=False)
    assert [t.polarity for t in themes.themes] == ["neg", "pos"]


def test_explain_ad_waste_fallback_is_grounded_in_evidence(cfg):
    from app.metrics import ListingMetrics, ListingRow

    latest = ListingRow(
        "2026-10-19", "GlowVeda", "SKU-1", "Amazon", "Title", 6, 2, 500.0, 550.0,
        50, 4.3, 100, "Shree Retail Traders", "skincare", "active", 56.0,
    )
    m = ListingMetrics(
        sku="SKU-1", platform="Amazon", brand="GlowVeda", latest=latest,
        previous=None, other_platform=None,
    )
    explanation, ai_generated = explain_ad_waste(
        m, {"orders_7d": 0, "roas": None}, cfg, ai_enabled=False
    )
    assert ai_generated is False
    assert "zero orders" in explanation.explanation
    assert "Buy Box" in explanation.explanation or "featured-seller" in explanation.explanation


def test_brand_summary_fallback_reads_as_finished_not_apologetic(cfg):
    summary = brand_summary_fallback("GlowVeda", 5, 12500.0, 2)
    text = summary.summary.lower()
    assert "unavailable" not in text
    assert "fallback" not in text
    assert "glowveda" in text
    assert "12,500" in summary.summary or "12500" in summary.summary
