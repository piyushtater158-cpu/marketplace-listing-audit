import json
import os
import re
import time
from typing import Literal

import httpx
from pydantic import BaseModel, ValidationError

from app.metrics import ListingMetrics, ReviewRow
from app.present import inr


class ContentRewrite(BaseModel):
    title: str
    bullets: list[str]


class ComplaintTheme(BaseModel):
    theme: str
    polarity: Literal["neg", "pos"]
    count: int
    example_quote: str


class ComplaintThemes(BaseModel):
    themes: list[ComplaintTheme]


class AdWasteExplanation(BaseModel):
    explanation: str


class BrandSummary(BaseModel):
    summary: str


class ReviewTranslation(BaseModel):
    index: int
    english: str


class ReviewTranslations(BaseModel):
    translations: list[ReviewTranslation]


def _strict_schema(model: type[BaseModel]) -> dict:
    """Pydantic's JSON schema adjusted for OpenAI-style strict structured output: every
    object closes additionalProperties and lists all its properties as required, and
    keywords strict mode rejects (title, default) are dropped."""
    schema = model.model_json_schema()

    def fix(node):
        if isinstance(node, dict):
            node.pop("title", None)
            node.pop("default", None)
            if node.get("type") == "object" and "properties" in node:
                node["additionalProperties"] = False
                node["required"] = list(node["properties"].keys())
            for value in node.values():
                fix(value)
        elif isinstance(node, list):
            for value in node:
                fix(value)

    fix(schema)
    return schema


def ai_available(cfg: dict) -> bool:
    return bool(os.environ.get(cfg["ai"]["api_key_env_var"]))


# Successful responses keyed by the exact request body, so a repeat request (same SKU
# page, toggling AI off and on again) never spends another call from the daily quota.
_response_cache: dict[str, BaseModel] = {}
_cooldown_until = 0.0


def _json_object(content: str) -> str:
    """Free models often wrap JSON in markdown fences or a sentence; keep the object."""
    start, end = content.find("{"), content.rfind("}")
    return content[start : end + 1] if start != -1 and end > start else content


def _call_openrouter(
    system_prompt: str, user_payload: dict, response_model: type[BaseModel], cfg: dict, task: str | None = None
) -> BaseModel | None:
    global _cooldown_until
    ai_cfg = cfg["ai"]
    api_key = os.environ.get(ai_cfg["api_key_env_var"])
    if not api_key or time.monotonic() < _cooldown_until:
        return None

    general = os.environ.get(ai_cfg["model_env_var"]) or ai_cfg["default_model"]
    model = ai_cfg.get("task_models", {}).get(task) or general
    schema = _strict_schema(response_model)
    body = {
        "model": model,
        "models": list(dict.fromkeys([model, general, *ai_cfg.get("fallback_models", [])])),
        "messages": [
            {
                "role": "system",
                "content": f"{system_prompt}\n\nRespond with only a JSON object matching this JSON "
                f"schema, with every required field present:\n{json.dumps(schema)}",
            },
            {"role": "user", "content": json.dumps(user_payload)},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": response_model.__name__, "schema": schema, "strict": True},
        },
    }
    if ai_cfg.get("disable_reasoning"):
        body["reasoning"] = {"enabled": False}

    cache_key = json.dumps(body, sort_keys=True)
    if cache_key in _response_cache:
        return _response_cache[cache_key]

    headers = {"Authorization": f"Bearer {api_key}"}
    for _attempt in range(2):
        try:
            resp = httpx.post(
                f"{ai_cfg['base_url']}/chat/completions",
                json=body,
                headers=headers,
                timeout=ai_cfg.get("timeout_seconds", 25),
            )
        except httpx.HTTPError:
            _cooldown_until = time.monotonic() + ai_cfg.get("cooldown_seconds", 60)
            return None
        if resp.status_code in (402, 429):
            _cooldown_until = time.monotonic() + ai_cfg.get("cooldown_seconds", 120)
            return None
        if resp.status_code >= 400:
            return None
        try:
            content = resp.json()["choices"][0]["message"]["content"] or ""
            result = response_model.model_validate_json(_json_object(content))
        except (ValidationError, KeyError, IndexError, TypeError, json.JSONDecodeError):
            continue
        _response_cache[cache_key] = result
        return result
    return None


# ---- fallbacks: the "AI off" path. These must stand on their own as finished content,
# never read as a degraded substitute. ----


def rewrite_content_fallback(brand: str, category: str, cfg: dict) -> ContentRewrite:
    template = cfg["content_templates"].get(category)
    if template is None:
        template = {
            "title": "{brand} [Product Name] - [Key Feature], [Size / Variant], Pack of 1",
            "bullets": [
                "KEY BENEFIT: [Main reason to buy]",
                "FEATURES: [Two or three concrete specs]",
                "BEST FOR: [Who and when]",
                "QUALITY: [Certification, material or test claim]",
                "IN THE BOX: 1 x {brand} [Product Name]",
            ],
        }
    return ContentRewrite(
        title=template["title"].format(brand=brand),
        bullets=[b.format(brand=brand) for b in template["bullets"]],
    )


def cluster_complaints_fallback(reviews: list[ReviewRow], cfg: dict) -> ComplaintThemes:
    themes = []
    for polarity, lexicon, keep in (
        ("neg", cfg["hinglish_complaint_lexicon"], lambda r: r.stars <= 2),
        ("pos", cfg["positive_theme_lexicon"], lambda r: r.stars >= 4),
    ):
        for bucket, keywords in lexicon.items():
            matches = [
                r for r in reviews
                if keep(r) and any(kw.lower() in r.text.lower() for kw in keywords)
            ]
            if matches:
                themes.append(
                    ComplaintTheme(
                        theme=bucket, polarity=polarity, count=len(matches), example_quote=matches[0].text
                    )
                )
    themes.sort(key=lambda t: (t.polarity != "neg", -t.count))
    return ComplaintThemes(themes=themes)


def detect_language(text: str, cfg: dict) -> str:
    """'hinglish' when the review uses at least two common romanised-Hindi words."""
    words = set(re.findall(r"[a-z]+", text.lower()))
    return "hinglish" if len(words & set(cfg["hinglish_markers"])) >= 2 else "en"


def explain_ad_waste_fallback(m: ListingMetrics, issue_evidence: dict, cfg: dict) -> AdWasteExplanation:
    reasons = []
    if issue_evidence.get("orders_7d") == 0:
        reasons.append("zero orders in the last 7 days despite active ad spend")
    roas = issue_evidence.get("roas")
    target = cfg["thresholds"]["target_roas"]
    if roas is not None and roas < target:
        reasons.append(f"ROAS of {roas} is below the {target} target")
    min_images = cfg["thresholds"]["min_images"]
    if m.latest.image_count < min_images:
        reasons.append(f"only {m.latest.image_count} images (minimum {min_images}) likely hurting conversion")
    seller_name = cfg["brands"].get(m.brand, {}).get("seller_name")
    if seller_name and m.latest.buybox_owner != seller_name:
        reasons.append("the Buy Box/featured-seller slot is lost, so clicks may land on a competing offer")

    if reasons:
        explanation = "Likely conversion-side: " + "; ".join(reasons) + "."
    else:
        explanation = "Spend is outpacing sales with no obvious listing-side cause — worth a manual review."
    return AdWasteExplanation(explanation=explanation)


def brand_summary_fallback(
    brand: str,
    total_issues: int,
    total_impact_inr: float,
    critical_count: int,
    approved_count: int = 0,
    dismissed_count: int = 0,
    open_count: int | None = None,
    top_item: dict | None = None,
) -> BrandSummary:
    if total_issues == 0:
        return BrandSummary(summary=f"This week {brand} had no issues flagged. Every listing passed the audit.")
    open_count = total_issues - approved_count - dismissed_count if open_count is None else open_count
    parts = [
        f"This week {brand} had {total_issues} new issue{'s' if total_issues != 1 else ''}, "
        f"{approved_count} approved and {dismissed_count} dismissed, with {open_count} still open.",
        f"Estimated loss: {inr(total_impact_inr)}/day; {critical_count} of the issues are critical."
        if critical_count
        else f"Estimated loss: {inr(total_impact_inr)}/day.",
    ]
    if top_item:
        parts.append(
            f"Biggest item: {top_item['sku']} on {top_item['platform']}, "
            f"{top_item['label'].lower()}, {inr(top_item['impact_inr'])}/day."
        )
    return BrandSummary(summary=" ".join(parts))


# ---- dispatchers: try AI when enabled, always fall back cleanly ----

CONTENT_SYSTEM_PROMPT = (
    "You write concise, accurate e-commerce listing copy for an Indian marketplace "
    "seller. Given a brand, category and current weak title, return a rewritten title "
    "(40-150 characters, includes a relevant category keyword) and exactly 5 bullet "
    "points. No emojis, no superlatives you can't back up."
)
COMPLAINT_SYSTEM_PROMPT = (
    "You cluster marketplace customer reviews (English and Hinglish) into short named "
    "themes of 1-3 words. Return 1-6 themes. Mark complaint themes from 1-2 star reviews "
    "polarity 'neg' and praise themes from 4-5 star reviews polarity 'pos'. Each theme "
    "has a count and one representative quote copied verbatim from the input."
)
TRANSLATE_SYSTEM_PROMPT = (
    "Translate each Hinglish (romanised Hindi mixed with English) customer review into "
    "natural English. Keep the meaning and tone, keep emojis, add nothing. Return one "
    "translation per input index."
)
AD_WASTE_SYSTEM_PROMPT = (
    "You explain, in one or two sentences, the likely cause of wasted ad spend on a "
    "marketplace listing, grounded only in the listing state provided — never invent "
    "facts not in the payload."
)
BRAND_SUMMARY_SYSTEM_PROMPT = (
    "You write a short, factual weekly summary (3-5 sentences) of a brand's marketplace "
    "listing audit for its account manager. Use only the stats provided: issue counts, "
    "approved/dismissed/open, the estimated daily loss and the biggest item. Money amounts "
    "are given pre-formatted (e.g. ₹1,18,331/day): copy them exactly as written, never "
    "reformat or recompute them. Plain prose, no lists, no headings, no advice you can't "
    "ground in the stats."
)

_INR_AMOUNT = re.compile(r"₹\s?[\d,]+")


_ALL_CRITICAL = re.compile(r"\ball\b[^.]{0,40}\bcritical", re.IGNORECASE)


def _amounts_match(text: str, allowed: set[str]) -> bool:
    """Every ₹ figure in AI text must be one we supplied; a model that drops a digit
    group must not put a wrong number in front of the AM."""
    return {re.sub(r"\s", "", a).rstrip(",") for a in _INR_AMOUNT.findall(text)} <= allowed


def _summary_is_grounded(text: str, stats: dict, allowed_amounts: set[str]) -> bool:
    """Free models were seen calling every issue critical when only some were."""
    if stats["critical_count"] < stats["total_issues"] and _ALL_CRITICAL.search(text):
        return False
    return _amounts_match(text, allowed_amounts)


def rewrite_content(brand: str, category: str, current_title: str, cfg: dict, ai_enabled: bool) -> tuple[ContentRewrite, bool]:
    if ai_enabled:
        result = _call_openrouter(
            CONTENT_SYSTEM_PROMPT,
            {"brand": brand, "category": category, "current_title": current_title},
            ContentRewrite,
            cfg,
        )
        if result is not None:
            return result, True
    return rewrite_content_fallback(brand, category, cfg), False


def cluster_complaints(reviews: list[ReviewRow], cfg: dict, ai_enabled: bool) -> tuple[ComplaintThemes, bool]:
    if ai_enabled:
        result = _call_openrouter(
            COMPLAINT_SYSTEM_PROMPT,
            {"reviews": [{"stars": r.stars, "text": r.text} for r in reviews]},
            ComplaintThemes,
            cfg,
        )
        if result is not None:
            return result, True
    return cluster_complaints_fallback(reviews, cfg), False


def explain_ad_waste(m: ListingMetrics, issue_evidence: dict, cfg: dict, ai_enabled: bool) -> tuple[AdWasteExplanation, bool]:
    if ai_enabled:
        result = _call_openrouter(
            AD_WASTE_SYSTEM_PROMPT,
            {
                "sku": m.sku,
                "platform": m.platform,
                "evidence": issue_evidence,
                "image_count": m.latest.image_count,
                "buybox_owner": m.latest.buybox_owner,
            },
            AdWasteExplanation,
            cfg,
        )
        if result is not None:
            return result, True
    return explain_ad_waste_fallback(m, issue_evidence, cfg), False


def summarize_brand_week(brand: str, stats: dict, cfg: dict, ai_enabled: bool) -> tuple[BrandSummary, bool]:
    """stats: total_issues, total_impact_inr (capped, per day), critical_count,
    approved_count, dismissed_count, open_count, top_item {sku, platform, label, impact_inr}."""
    if ai_enabled and stats["total_issues"] > 0:
        top = stats["top_item"]
        payload = {
            "brand": brand,
            **{k: v for k, v in stats.items() if k not in ("total_impact_inr", "top_item")},
            "non_critical_count": stats["total_issues"] - stats["critical_count"],
            "estimated_daily_loss": f"{inr(stats['total_impact_inr'])}/day",
            "biggest_item": {**{k: v for k, v in top.items() if k != "impact_inr"}, "daily_loss": f"{inr(top['impact_inr'])}/day"}
            if top
            else None,
        }
        allowed = {inr(stats["total_impact_inr"])} | ({inr(top["impact_inr"])} if top else set())
        result = _call_openrouter(BRAND_SUMMARY_SYSTEM_PROMPT, payload, BrandSummary, cfg, task="brand_summary")
        if result is not None and _summary_is_grounded(result.summary, stats, allowed):
            return result, True
    return (
        brand_summary_fallback(
            brand,
            stats["total_issues"],
            stats["total_impact_inr"],
            stats["critical_count"],
            stats["approved_count"],
            stats["dismissed_count"],
            stats["open_count"],
            stats["top_item"],
        ),
        False,
    )


_translation_cache: dict[str, str] = {}


def translate_reviews(texts: list[str], cfg: dict, ai_enabled: bool) -> dict[str, str]:
    """AI-only: there is no rule-based translation, so with AI off (or on failure) this
    returns nothing and the UI shows no translation line."""
    if not ai_enabled:
        return {}
    pending = [t for t in dict.fromkeys(texts) if t not in _translation_cache]
    if pending:
        result = _call_openrouter(
            TRANSLATE_SYSTEM_PROMPT,
            {"reviews": [{"index": i, "text": t} for i, t in enumerate(pending)]},
            ReviewTranslations,
            cfg,
            task="translate",
        )
        if result is not None:
            for tr in result.translations:
                if 0 <= tr.index < len(pending) and tr.english.strip():
                    _translation_cache[pending[tr.index]] = tr.english.strip()
    return {t: _translation_cache[t] for t in texts if t in _translation_cache}
