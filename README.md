# Marketplace Listing Audit

**Live demo: [audit.piyushtater.com](https://audit.piyushtater.com)** (sample data; resets to the seed when the API restarts)

A dashboard for an Intent Farm account manager running several brands on Amazon and
Flipkart. It audits every listing from CSV exports, flags what is broken, prices each
problem in rupees per day, ranks the queue by urgency and drafts a fix for the AM to
approve. Approving produces copy-ready text (a message to the brand, or a task for the
internal team). Nothing is sent or changed automatically.

> **SAMPLE DATA.** Everything that ships in `api/seed/` is synthetic: three fictional
> brands (GlowVeda skincare, Munchkraft snacks, Vayu Home appliances), 40 SKUs each, on
> both platforms. No real seller, listing or review is included.

## Run it

**Docker (one command):**

```bash
docker compose up -d --build        # web on http://localhost:3000
```

The API is only reachable from the web container. To turn the AI layer on, put
`OPENROUTER_API_KEY=...` in a `.env` file next to `docker-compose.yml`. Without a key the
app runs entirely on rules and templates. The seed loads and is audited on first boot.
Data lives in the `api-data` volume.

**Hosted demo:** the web app runs on Vercel (`web/` as the root directory, `API_URL`
pointing at the API) and the API on Render's free plan via `render.yaml`. Render's free
plan has no persistent disk, so every restart reloads the seed: the demo always opens on
clean sample data.

**Local development:**

```bash
# API (Python 3.11+)
cd api
python -m venv .venv && .venv/Scripts/activate      # or: source .venv/bin/activate
pip install -e ".[dev]"
pytest                                               # 65 tests
uvicorn app.main:app --port 8010

# Web (Node 20+)
cd web
npm install
API_URL=http://127.0.0.1:8010 npm run dev            # http://localhost:3000
```

`npm run gen:api` regenerates `web/types/api.d.ts` from FastAPI's OpenAPI schema.
`npm run gen:css` rebuilds `web/app/globals.css` from the design handoff.
`python api/seed/generate_seed.py` regenerates the sample CSVs and `manifest.json`.

## How it works

```
CSV upload ─▶ FastAPI (api/) ─ SQLite ─▶ 10 rule detectors ─▶ ₹ impact + severity ─▶ AI text layer (optional)
                     ▲                                                                       │
                     └──────────── Next.js Server Components (web/) read over HTTP ◀─────────┘
```

* **`api/` owns all data and logic.** `config.yaml` holds every threshold and rupee
  factor, each with a one-line reason. Start there.
* **`web/` owns zero logic.** Every page is a Server Component that renders what the
  API returns. The five forms (upload, run audit, approve/edit/dismiss, undo, AI toggle)
  are Server Actions that forward to the API. The visual design comes from a Claude
  Design handoff (`design/listing-audit-handoff/`) and was ported as-is.
* Upload is two steps, as designed: files load into an *awaiting audit* state, then
  **Run audit** computes issues.

## The ten issue types

| Rule ID | Issue | Fires when | ₹ impact / day |
|---|---|---|---|
| `OOS-ADS-01` | Out of stock, ads running | stock = 0 and ad spend > 0 | ad spend + daily sales |
| `LOW-STOCK-01` | Low stock, high spend | days of cover < 3 and spend > ₹100/day | daily sales × shortfall ramp to 3 days |
| `PRICE-GAP-01` | Price mismatch across platforms | gap > 8% (flagged on the pricier side only) | daily sales × gap × 0.3 elasticity |
| `PRICE-MRP-01` | Price above MRP | price > MRP (always critical: compliance) | daily sales × 0.5 at risk |
| `PRICE-SHOCK-01` | Sudden price change | > 15% move between snapshots | units/day × price change |
| `CONTENT-01` | Weak content | title outside 40–150 chars, < 4 images, < 5 bullets, or no category keyword | daily sales × 8% per gap |
| `RATING-01` | Rating drop | rating fell ≥ 0.2, or ≥ 3 one/two-star reviews in 7 days | daily sales × 15% per 0.2★ |
| `BUYBOX-01` | Lost Buy Box / featured seller | owner ≠ the brand's seller name | ad spend + daily sales × 0.6 |
| `AD-WASTE-01` | Ad waste | spend > ₹100/day and zero orders or ROAS < 2.0 | spend above what sales justify at target ROAS |
| `STATUS-01` | Suppressed / inactive | status is suppressed, inactive or blocked (always critical) | ad spend + daily sales |

Daily figures are 7-day means from the ads file; units come from `units_sold_7d`.
Every card shows its own calculation line, e.g. "₹522 ad spend wasted + ₹1,341 daily sales lost".

**No double counting.** The queue ranks on each issue's own number. The portfolio
headline caps each listing's summed issues at that listing's daily ad spend plus daily
sales. That is the most a listing can actually lose in a day, so a SKU that is out of
stock, wasting spend and missing the Buy Box isn't counted three times. The tooltip
shows the uncapped sum next to it.

**Correctness.** `api/seed/manifest.json` lists the exact issues each seeded listing
should raise, derived from the generator's deliberate mutations rather than from running
the engine. `pytest` asserts the engine's output matches it exactly: every type fires,
nothing extra fires. `GET /api/debug` shows every metric and impact component per listing.

## AI on / off

The header switch is the only setting. Without `OPENROUTER_API_KEY` on the API it is
greyed out and reads "NO KEY", so the header never claims AI is on while every line is
coming from templates. AI never creates, removes or re-prices an issue.
It only writes language on top of issues the rules already raised:

| | AI on (OpenRouter, schema-validated JSON, one retry) | AI off |
|---|---|---|
| Weak-content fix | rewritten title + 5 bullets | the other platform's passing title, plus a category template with `[fields]` to fill |
| Rating-drop fix and review themes | clustered complaint and praise themes | keyword lexicon, including Hinglish (`tuta`, `nakli`, `ghatiya`, `leak`, `der se`) |
| Ad-waste explanation | grounded explanation | rule sentence built from ROAS, orders, images and Buy Box state |
| Hinglish review translation | shown with an "AI translation" tag | hidden |
| Brand weekly summary | written paragraph | template paragraph from the same numbers |

AI text carries an "AI draft" tag; rule text carries its rule ID. If a call fails, that
item silently uses the template.

**Free models only.** The AI layer runs on OpenRouter's free models, so it is built
around their limits (20 requests a minute, a daily cap, occasional upstream 429s):

* Models: `nvidia/nemotron-3-super-120b-a12b:free` (reasoning off, ~4s) for fixes and
  themes; `google/gemma-4-26b-a4b-it:free` for Hinglish translation and the brand summary,
  where Nemotron mistranslated and padded. Other free models are OpenRouter fallbacks.
* An audit never waits on AI. Issues are written with templates first; AI drafts for the
  12 highest-impact eligible issues fill in a few seconds later in the background.
* Identical requests are answered from memory; a 429, 402 or timeout pauses AI for 60s
  instead of retrying into an exhausted quota.
* Free models don't enforce the JSON schema strictly, so the schema is also spelled out
  in the prompt and replies are pulled out of markdown fences before validation.
* The brand summary is checked before it is shown: every ₹ figure must be one the API
  supplied, and it may not call all issues critical when only some are. A summary that
  fails either check is replaced by the template.

## CSV formats

All three files are required on upload. Lines starting with `#` are ignored. Uploads are
validated (headers, required columns, row count, value types) before anything is
replaced, and errors name the file and column.

* `listings.csv`: `snapshot_date, brand, sku, platform, title, bullet_count, image_count, price, mrp, stock, rating, review_count, buybox_owner, category, status, units_sold_7d`.
  Include two snapshot dates per listing to enable change detection.
* `ads.csv`: `date, sku, platform, spend, clicks, orders, sales` (14 days, daily).
* `reviews.csv`: `sku, platform, review_date, stars, text`.

Columns added beyond the original brief, and why: `status` (the suppressed check needs
it), `units_sold_7d` (days-of-cover from ad-attributed orders alone would overstate
cover; in Seller Central this comes from the Business Report, not the listings report),
`review_date` (a review "spike" needs a time axis) and `brand` (the top-level grouping).
The headers are simplified and do not reproduce Seller Central or Flipkart Seller Hub
exports column for column.

## Deliberate simplifications

* **Flipkart has no Buy Box.** On Flipkart the `buybox_owner` column is read as the
  featured or preferred seller, and the issue is labelled "Featured-seller slot lost".
* Rupee factors in `config.yaml` (elasticity, penalties, Buy Box share) are labelled
  estimates. They make issues comparable; they are not forecasts.
* A new upload replaces the previous data. History lives in the two snapshot dates
  inside the listings file, which is what the SKU page compares.
* Approve and dismiss decisions carry over a re-upload and re-audit when the same issue
  (same SKU, platform and rule) still fires, so the AM doesn't re-triage it. Decisions on
  issues that no longer fire are dropped. Undone decisions are not carried.
* Brand weeks run Monday to Sunday. Only the week of the latest snapshot has data.

> **SAMPLE DATA, again:** any figure you see in the running app comes from the
> synthetic seed unless you upload your own files.
