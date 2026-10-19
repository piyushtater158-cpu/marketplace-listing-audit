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


class _FakeResponse:
    def __init__(self, status_code: int, content: str = ""):
        self.status_code = status_code
        self._content = content

    def json(self):
        return {"choices": [{"message": {"content": self._content}}]}


@pytest.fixture()
def fake_openrouter(monkeypatch):
    import app.ai

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(app.ai, "_response_cache", {})
    monkeypatch.setattr(app.ai, "_cooldown_until", 0.0)
    calls = []

    def install(*responses):
        queue = list(responses)

        def fake_post(url, json, headers, timeout):
            calls.append(json)
            return queue.pop(0)

        monkeypatch.setattr(app.ai.httpx, "post", fake_post)
        return calls

    return install


def test_ai_reply_in_markdown_fences_is_parsed_and_cached(cfg, fake_openrouter):
    fenced = '```json\n{"title": "GlowVeda Vitamin C Face Serum for Glowing Skin, 30 ml", "bullets": ["a","b","c","d","e"]}\n```'
    calls = fake_openrouter(_FakeResponse(200, fenced))
    first, ai1 = rewrite_content("GlowVeda", "skincare", "x", cfg, ai_enabled=True)
    second, ai2 = rewrite_content("GlowVeda", "skincare", "x", cfg, ai_enabled=True)
    assert ai1 and ai2 and first == second
    assert len(calls) == 1
    assert calls[0]["model"].endswith(":free") and all(m.endswith("free") for m in calls[0]["models"])


def test_rate_limit_pauses_ai_instead_of_retrying(cfg, fake_openrouter):
    calls = fake_openrouter(_FakeResponse(429))
    rewrite, ai_generated = rewrite_content("GlowVeda", "skincare", "x", cfg, ai_enabled=True)
    assert ai_generated is False and len(rewrite.bullets) == 5
    _, again = rewrite_content("Munchkraft", "snacks", "y", cfg, ai_enabled=True)
    assert again is False
    assert len(calls) == 1


def test_ai_brand_summary_with_a_wrong_rupee_figure_is_rejected(cfg, fake_openrouter):
    from app.ai import summarize_brand_week

    stats = {
        "total_issues": 37, "total_impact_inr": 118331.0, "critical_count": 10, "approved_count": 0,
        "dismissed_count": 0, "open_count": 37,
        "top_item": {"sku": "GLOWVEDA-030", "platform": "Amazon", "label": "Suppressed", "impact_inr": 11377.0},
    }
    wrong = '{"summary": "GlowVeda has 37 open issues costing ₹18,331/day; the biggest is ₹1,377/day."}'
    right = '{"summary": "GlowVeda has 37 open issues costing ₹1,18,331/day; the biggest is ₹11,377/day."}'
    fake_openrouter(_FakeResponse(200, wrong))
    summary, ai_generated = summarize_brand_week("GlowVeda", stats, cfg, ai_enabled=True)
    assert ai_generated is False and "₹1,18,331" in summary.summary

    fake_openrouter(_FakeResponse(200, right))
    summary, ai_generated = summarize_brand_week("GlowVeda", {**stats, "open_count": 36}, cfg, ai_enabled=True)
    assert ai_generated is True and "₹1,18,331/day" in summary.summary

    all_critical = '{"summary": "GlowVeda has 37 open issues, all critical, costing ₹1,18,331/day."}'
    fake_openrouter(_FakeResponse(200, all_critical))
    _, ai_generated = summarize_brand_week("GlowVeda", {**stats, "open_count": 35}, cfg, ai_enabled=True)
    assert ai_generated is False


def test_only_top_impact_issues_get_ai_slots(cfg):
    from app.pipeline import _ai_slots

    items = [("oos_ads_live", 9000.0)] + [("ad_waste", float(i)) for i in range(20)]
    slots = _ai_slots(items, cfg, ai_enabled=True)
    limit = cfg["ai"]["max_fixes_per_run"]
    assert len(slots) == limit and 0 not in slots
    assert slots == set(range(21 - limit, 21))
    assert _ai_slots(items, cfg, ai_enabled=False) == set()


def test_brand_summary_fallback_reads_as_finished_not_apologetic(cfg):
    summary = brand_summary_fallback("GlowVeda", 5, 12500.0, 2)
    text = summary.summary.lower()
    assert "unavailable" not in text
    assert "fallback" not in text
    assert "glowveda" in text
    assert "12,500" in summary.summary or "12500" in summary.summary
