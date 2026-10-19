import csv
import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.db
from app.ai import ComplaintThemes, _strict_schema, detect_language
from app.config import load_config
from app.detectors import ISSUE_CODES
from app.main import app as fastapi_app

SEED_DIR = Path(__file__).resolve().parent.parent / "seed"
SEV_RANK = {"critical": 0, "high": 1, "medium": 1, "low": 1}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(app.db, "DB_PATH", tmp_path / "test.db")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with TestClient(fastapi_app) as c:
        yield c


def _seed_csv(name: str) -> tuple[list[str], list[dict]]:
    with open(SEED_DIR / name, encoding="utf-8") as f:
        lines = [line for line in f if not line.lstrip().startswith("#")]
    reader = csv.DictReader(io.StringIO("".join(lines)))
    return reader.fieldnames, list(reader)


def _to_csv(fieldnames: list[str], rows: list[dict]) -> bytes:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8")


def _upload(client, listings: bytes, ads: bytes, reviews: bytes):
    return client.post(
        "/api/upload",
        files={
            "listings": ("listings.csv", listings, "text/csv"),
            "ads": ("ads.csv", ads, "text/csv"),
            "reviews": ("reviews.csv", reviews, "text/csv"),
        },
    )


def _seed_bytes(mutate_listings=None, drop_listing=None):
    l_fields, l_rows = _seed_csv("listings.csv")
    a_fields, a_rows = _seed_csv("ads.csv")
    r_fields, r_rows = _seed_csv("reviews.csv")
    if mutate_listings:
        for row in l_rows:
            mutate_listings(row)
    if drop_listing:
        l_rows = [r for r in l_rows if not drop_listing(r)]
    return _to_csv(l_fields, l_rows), _to_csv(a_fields, a_rows), _to_csv(r_fields, r_rows)


# ---- overview ----


def test_seed_is_loaded_and_audited_on_startup(client):
    p = client.get("/api/portfolio").json()
    assert p["has_data"] is True
    assert p["snapshot"]["status"] == "audited"
    assert p["snapshot"]["row_counts"] == {"listings": 480, "ads": 3360, "reviews": 265}
    assert p["brands"] == ["GlowVeda", "Munchkraft", "Vayu Home"]
    assert {c["brand_slug"] for c in p["cells"]} == {"glowveda", "munchkraft", "vayu-home"}


def test_portfolio_total_is_capped_and_cells_add_up(client):
    p = client.get("/api/portfolio").json()
    assert 0 < p["total_daily_loss_inr"] < p["uncapped_daily_loss_inr"]
    for sev in ("critical", "high", "medium", "low"):
        assert sum(c["severity_counts"][sev] for c in p["cells"]) == p["severity_counts"][sev]
    assert sum(c["capped_daily_loss_inr"] for c in p["cells"]) == pytest.approx(p["total_daily_loss_inr"], abs=0.1)


def test_portfolio_counts_only_open_issues(client):
    before = client.get("/api/portfolio").json()
    top = client.get("/api/issues").json()[0]
    client.post("/api/decisions", json={"issue_id": top["id"], "decision": "approve"})
    after = client.get("/api/portfolio").json()
    assert after["open_issue_count"] == before["open_issue_count"] - 1
    assert after["approved_count"] == 1
    assert after["approved_impact_inr"] == top["impact_inr"]
    assert after["total_daily_loss_inr"] < before["total_daily_loss_inr"]


# ---- queue ----


def test_queue_pins_critical_first_then_ranks_by_impact(client):
    issues = client.get("/api/issues").json()
    keys = [(SEV_RANK[i["severity"]], -i["impact_inr"]) for i in issues]
    assert keys == sorted(keys)
    assert {i["issue_code"] for i in issues} == set(ISSUE_CODES)


def test_queue_cards_carry_rule_id_calc_line_evidence_and_fix(client):
    for i in client.get("/api/issues").json():
        assert i["rule_id"] and i["impact_calc_text"]
        assert 1 <= len(i["evidence_points"]) <= 4
        assert any(p["bad"] for p in i["evidence_points"])
        assert i["fix"]["kind"] in ("message", "content")
        assert i["fix"]["source"] == "rule"
        assert i["status"] == "open"


def test_queue_filters_accept_design_slugs(client):
    issues = client.get("/api/issues", params={"brand": "vayu-home", "platform": "flipkart"}).json()
    assert issues
    assert {(i["brand"], i["platform"]) for i in issues} == {("Vayu Home", "Flipkart")}
    crit = client.get("/api/issues", params={"severity": "critical"}).json()
    assert crit and {i["severity"] for i in crit} == {"critical"}
    assert client.get("/api/issues", params={"brand": "nobody"}).json() == []


def test_weak_content_fix_is_a_content_block_reusing_the_passing_title(client):
    weak = [i for i in client.get("/api/issues").json() if i["issue_code"] == "weak_content"]
    assert weak
    for issue in weak:
        assert issue["fix"]["kind"] == "content"
        assert issue["fix"]["title_note"].startswith("already live on")
        assert len(issue["fix"]["bullets"]) == 5


# ---- decisions ----


def test_approve_produces_final_text_and_leaves_queue(client):
    top = client.get("/api/issues").json()[0]
    resp = client.post("/api/decisions", json={"issue_id": top["id"], "decision": "approve"})
    assert resp.status_code == 200
    d = resp.json()
    assert d["decision"] == "approve"
    assert top["sku"] in d["final_text"] and top["suggested_fix"] in d["final_text"]
    assert d["sku"] == top["sku"] and d["issue_label"] == top["issue_label"]

    assert top["id"] not in {i["id"] for i in client.get("/api/issues").json()}
    assert client.get(f"/api/issues/{top['id']}").json()["status"] == "approved"
    assert client.get(f"/api/decisions/{d['id']}").json()["final_text"] == d["final_text"]

    again = client.post("/api/decisions", json={"issue_id": top["id"], "decision": "dismiss"})
    assert again.status_code == 409


def test_approve_edited_uses_edited_text_and_requires_it(client):
    issue = client.get("/api/issues").json()[1]
    missing = client.post("/api/decisions", json={"issue_id": issue["id"], "decision": "approve_edited"})
    assert missing.status_code == 422

    edited = "Pause the campaign today and ping me when stock lands."
    d = client.post(
        "/api/decisions", json={"issue_id": issue["id"], "decision": "approve_edited", "fix_text": edited}
    ).json()
    assert d["decision"] == "approve_edited"
    assert edited in d["final_text"]
    assert issue["suggested_fix"] not in d["final_text"]


def test_dismiss_has_no_final_text(client):
    issue = client.get("/api/issues").json()[2]
    d = client.post("/api/decisions", json={"issue_id": issue["id"], "decision": "dismiss"}).json()
    assert d["decision"] == "dismiss" and d["final_text"] is None
    assert client.get(f"/api/issues/{issue['id']}").json()["status"] == "dismissed"


def test_undo_reopens_issue_and_allows_a_new_decision(client):
    issue = client.get("/api/issues").json()[0]
    d = client.post("/api/decisions", json={"issue_id": issue["id"], "decision": "dismiss"}).json()
    undone = client.post(f"/api/decisions/{d['id']}/undo").json()
    assert undone["undone_at"] is not None
    assert issue["id"] in {i["id"] for i in client.get("/api/issues").json()}

    again = client.post("/api/decisions", json={"issue_id": issue["id"], "decision": "approve"})
    assert again.status_code == 200
    assert client.post("/api/decisions/999999/undo").status_code == 404


def test_unknown_issue_is_404(client):
    assert client.post("/api/decisions", json={"issue_id": 999999, "decision": "approve"}).status_code == 404
    assert client.get("/api/issues/999999").status_code == 404


# ---- SKU ----


def test_sku_detail_shows_both_platforms_snapshot_rows_and_reviews(client):
    issue = next(i for i in client.get("/api/issues").json() if i["issue_code"] == "rating_drop")
    detail = client.get(f"/api/sku/{issue['sku']}").json()
    assert set(detail["platforms"]) == {"Amazon", "Flipkart"}
    assert detail["missing_platforms"] == []
    assert detail["brand_slug"] == issue["brand_slug"]
    assert sum(detail["star_distribution"].values()) == len(detail["reviews"])
    assert detail["average_stars"] is not None
    assert detail["representative_reviews"]
    assert any(t["polarity"] == "neg" for t in detail["complaint_themes"])

    rows = {r["field"]: r for r in detail["platforms"][issue["platform"]]["snapshot_rows"]}
    assert set(rows) >= {"price", "stock", "rating", "status", "buybox_owner"}
    assert all(r["tone"] in ("bad", "chg", "same") for r in rows.values())


def test_price_shock_marks_price_row_bad(client):
    issue = next(i for i in client.get("/api/issues").json() if i["issue_code"] == "price_shock")
    rows = client.get(f"/api/sku/{issue['sku']}").json()["platforms"][issue["platform"]]["snapshot_rows"]
    price = next(r for r in rows if r["field"] == "price")
    assert price["tone"] == "bad" and price["change"].startswith("▼")


def test_reviews_flag_hinglish_and_hide_translation_without_ai(client):
    issue = next(i for i in client.get("/api/issues").json() if i["issue_code"] == "rating_drop")
    reviews = client.get(f"/api/sku/{issue['sku']}").json()["reviews"]
    assert any(r["language"] == "hinglish" for r in reviews)
    assert all(r["translation"] is None for r in reviews)


def test_sku_detail_unknown_is_404(client):
    assert client.get("/api/sku/NOPE-000").status_code == 404


# ---- brand ----


def test_brand_report_accepts_name_or_slug_and_defaults_to_data_week(client):
    by_name = client.get("/api/brand/Vayu Home/report").json()
    by_slug = client.get("/api/brand/vayu-home/report").json()
    assert by_name == by_slug
    assert by_name["has_data"] is True
    assert by_name["week_start"] == "2026-10-19" and by_name["week_end"] == "2026-10-25"
    assert "Vayu Home" in by_name["summary"]
    assert by_name["ai_generated"] is False
    assert len(by_name["top_issues"]) <= 5
    assert client.get("/api/brand/nobody/report").status_code == 404


def test_brand_report_other_week_has_no_data_and_links_back(client):
    r = client.get("/api/brand/glowveda/report", params={"week": "2026-10-14"}).json()
    assert r["week_start"] == "2026-10-12"
    assert r["has_data"] is False and r["total_issues"] == 0
    assert r["next_week"] == "2026-10-19"
    assert client.get("/api/brand/glowveda/report", params={"week": "nope"}).status_code == 400


def test_brand_report_counts_decisions(client):
    issues = client.get("/api/issues", params={"brand": "glowveda"}).json()
    client.post("/api/decisions", json={"issue_id": issues[0]["id"], "decision": "approve"})
    client.post("/api/decisions", json={"issue_id": issues[1]["id"], "decision": "dismiss"})
    report = client.get("/api/brand/glowveda/report").json()
    assert report["approved_count"] == 1
    assert report["dismissed_count"] == 1
    assert report["open_issues"] == report["total_issues"] - 2


# ---- AI toggle ----


def test_ai_toggle_changes_language_not_issues_or_numbers(client):
    before = client.get("/api/issues", params={"status": "all"}).json()
    resp = client.post("/api/settings/ai", json={"enabled": False}).json()
    assert resp["enabled"] is False and resp["updated_count"] > 0
    after = client.get("/api/issues", params={"status": "all"}).json()

    assert [(i["id"], i["issue_code"], i["impact_inr"], i["severity"]) for i in before] == [
        (i["id"], i["issue_code"], i["impact_inr"], i["severity"]) for i in after
    ]
    assert not any(i["ai_generated"] for i in after)
    assert client.get("/api/settings/ai").json()["enabled"] is False
    assert client.get("/api/portfolio").json()["ai_enabled"] is False


def test_ai_on_without_a_key_falls_back_cleanly_on_every_issue(client):
    client.post("/api/settings/ai", json={"enabled": False})
    resp = client.post("/api/settings/ai", json={"enabled": True}).json()
    assert resp["enabled"] is True and resp["updated_count"] > 0
    issues = client.get("/api/issues", params={"status": "all"}).json()
    assert all(i["fix"]["source"] == "rule" and (i["fix"]["text"] or i["fix"]["title"]) for i in issues)


def test_ai_availability_follows_the_api_key(client, monkeypatch):
    assert client.get("/api/portfolio").json()["ai_available"] is False
    assert client.get("/api/settings/ai").json()["available"] is False
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    assert client.get("/api/portfolio").json()["ai_available"] is True
    assert client.get("/api/settings/ai").json()["available"] is True


def test_strict_schema_closes_every_object():
    schema = _strict_schema(ComplaintThemes)
    theme = schema["$defs"]["ComplaintTheme"]
    assert theme["additionalProperties"] is False
    assert set(theme["required"]) == {"theme", "polarity", "count", "example_quote"}
    assert schema["additionalProperties"] is False


def test_detect_language():
    cfg = load_config()
    assert detect_language("Product acha tha pehle, ab box leak ho ke aaya", cfg) == "hinglish"
    assert detect_language("Great value for money, will buy again.", cfg) == "en"


# ---- debug ----


def test_debug_proves_every_code_fires(client):
    d = client.get("/api/debug").json()
    assert set(d["summary"]["issues_by_code"]) == set(ISSUE_CODES)
    assert d["summary"]["capped_total_inr"] < d["summary"]["uncapped_total_inr"]
    assert d["summary"]["listing_count"] == 240
    assert d["summary"]["snapshot"]["status"] == "audited"


# ---- upload + audit ----


def test_upload_then_audit_restock_clears_issue_and_total_drops(client):
    total_before = client.get("/api/portfolio").json()["total_daily_loss_inr"]
    oos = next(i for i in client.get("/api/issues").json() if i["issue_code"] == "oos_ads_live")

    def restock(row):
        if row["sku"] == oos["sku"] and row["platform"] == oos["platform"]:
            row["stock"] = "500"

    resp = _upload(client, *_seed_bytes(mutate_listings=restock))
    assert resp.status_code == 200
    assert resp.json()["snapshot"]["status"] == "uploaded"

    awaiting = client.get("/api/portfolio").json()
    assert awaiting["snapshot"]["status"] == "uploaded"
    assert awaiting["has_data"] is True and awaiting["open_issue_count"] == 0
    assert client.get("/api/issues").json() == []

    audit = client.post("/api/audit/run").json()
    assert audit["issues_computed"] > 0 and audit["snapshot"]["status"] == "audited"

    still_oos = [
        i for i in client.get("/api/issues").json()
        if i["issue_code"] == "oos_ads_live" and i["sku"] == oos["sku"] and i["platform"] == oos["platform"]
    ]
    assert still_oos == []
    assert client.get("/api/portfolio").json()["total_daily_loss_inr"] < total_before


def _decide_first_two(client):
    issues = client.get("/api/issues").json()
    approved = client.post("/api/decisions", json={"issue_id": issues[0]["id"], "decision": "approve"}).json()
    client.post("/api/decisions", json={"issue_id": issues[1]["id"], "decision": "dismiss"})
    return issues[0], issues[1], approved


def _status_by_key(client):
    return {
        (i["sku"], i["platform"], i["issue_code"]): i["status"]
        for i in client.get("/api/issues", params={"status": "all"}).json()
    }


def test_rerunning_the_audit_keeps_decisions(client):
    first, second, approved = _decide_first_two(client)
    client.post("/api/audit/run")

    status = _status_by_key(client)
    assert status[(first["sku"], first["platform"], first["issue_code"])] == "approved"
    assert status[(second["sku"], second["platform"], second["issue_code"])] == "dismissed"
    p = client.get("/api/portfolio").json()
    assert p["approved_count"] == 1 and p["dismissed_count"] == 1
    kept = client.get("/api/decisions").json()
    assert any(d["final_text"] == approved["final_text"] for d in kept)


def test_reupload_keeps_decisions_only_on_issues_that_still_fire(client):
    issues = client.get("/api/issues").json()
    oos = next(i for i in issues if i["issue_code"] == "oos_ads_live")
    other = next(i for i in issues if (i["sku"], i["platform"]) != (oos["sku"], oos["platform"]))
    client.post("/api/decisions", json={"issue_id": oos["id"], "decision": "approve"})
    client.post("/api/decisions", json={"issue_id": other["id"], "decision": "dismiss"})

    def restock(row):
        if row["sku"] == oos["sku"] and row["platform"] == oos["platform"]:
            row["stock"] = "500"

    _upload(client, *_seed_bytes(mutate_listings=restock))
    client.post("/api/audit/run")

    status = _status_by_key(client)
    assert (oos["sku"], oos["platform"], "oos_ads_live") not in status
    assert status[(other["sku"], other["platform"], other["issue_code"])] == "dismissed"
    p = client.get("/api/portfolio").json()
    assert p["approved_count"] == 0 and p["dismissed_count"] == 1


def test_upload_sku_on_one_platform_reads_as_not_listed(client):
    sku = _seed_csv("listings.csv")[1][0]["sku"]
    resp = _upload(client, *_seed_bytes(drop_listing=lambda r: r["sku"] == sku and r["platform"] == "Flipkart"))
    assert resp.status_code == 200
    client.post("/api/audit/run")
    detail = client.get(f"/api/sku/{sku}").json()
    assert list(detail["platforms"]) == ["Amazon"]
    assert detail["missing_platforms"] == ["Flipkart"]


def test_sample_csvs_download_and_reupload_cleanly(client):
    files = {}
    for name in ("listings", "ads", "reviews"):
        resp = client.get(f"/api/samples/{name}.csv")
        assert resp.status_code == 200 and resp.headers["content-type"].startswith("text/csv")
        files[name] = resp.content
    assert client.get("/api/samples/secrets.csv").status_code == 404
    assert _upload(client, files["listings"], files["ads"], files["reviews"]).status_code == 200


def test_reset_restores_the_audited_sample_and_clears_decisions(client):
    sku = _seed_csv("listings.csv")[1][0]["sku"]
    _upload(client, *_seed_bytes(drop_listing=lambda r: r["sku"] == sku))
    client.post("/api/audit/run")
    issue = client.get("/api/issues").json()[0]
    client.post("/api/decisions", json={"issue_id": issue["id"], "decision": "dismiss"})

    reset = client.post("/api/reset").json()
    assert reset["snapshot"]["status"] == "audited" and reset["issues_computed"] > 0
    p = client.get("/api/portfolio").json()
    assert p["snapshot"]["row_counts"] == {"listings": 480, "ads": 3360, "reviews": 265}
    assert p["dismissed_count"] == 0 and p["approved_count"] == 0
    assert client.get(f"/api/sku/{sku}").status_code == 200


def test_bad_upload_names_the_problem_and_keeps_existing_data(client):
    before = client.get("/api/portfolio").json()
    bad = b"sku,platform\nX,Amazon\n"
    resp = _upload(client, bad, bad, bad)
    assert resp.status_code == 400
    assert "listings.csv" in resp.json()["detail"] and "missing column" in resp.json()["detail"]

    header_only = _upload(client, b"", b"", b"")
    assert header_only.status_code == 400
    assert client.get("/api/portfolio").json() == before
