# Listing Audit — engineering handoff

Source of truth for porting the design canvas ("Marketplace Listing Audit") into Next.js (App Router).
Read with: the canvas export (one `.dc.html` per screen) and `globals.css` (extracted styles).

## 1. Porting rules

1. **Server Components by default.** Every page renders on the server. No loading skeletons or spinners.
2. **Links:** use each element's `data-route` as the real `href`. Every `*.dc.html` href is a prototype link only.
3. **Forms:** keep each `action`, `method`, input `name` and button `name`/`value` exactly as drawn. They are the contract below.
4. **Styles:** import `globals.css` once in `app/layout.tsx`. Drop the `<style>` block inside each artboard. The rules under `PAGE:` sections differ per route. Scope them per page (CSS module or a page class on `<main>`). Don't merge them: `.main`, `.cell` and `.sec-head` differ between pages.
5. **Fonts:** load Instrument Sans (400–700), IBM Plex Mono (400–600) and Newsreader (400/500, italic 400) through `next/font/google`. Map them to the font stacks in `globals.css`.
6. **Sample data:** every name, SKU, ₹ figure, date and quote in the canvas is sample data. Bind all of it to the DB. Nothing is hard-coded.
7. **Icons:** inline SVGs as drawn. Severity shape is part of the meaning (octagon / triangle / diamond / ring), so never swap shapes.

## 2. Routes

| Artboard | Route | Renders when |
|---|---|---|
| Main | `/` | latest snapshot `status = 'audited'` |
| OverviewFresh | `/` | latest snapshot `status = 'uploaded'` (audit not run) |
| Queue | `/queue` | ≥ 1 open issue in current filter |
| QueueEmpty | `/queue` | 0 open issues |
| Sku | `/sku/[sku]` | SKU has rows on both platforms |
| SkuSingle | `/sku/[sku]` | SKU has a row on one platform only. Missing column reads "Not listed on {platform}" |
| Brand | `/brand/[brand]?week=YYYY-MM-DD` | one template for all brands. `week` = Monday of the week, default current week |
| Components, Handoff | — | reference only, not routes |

Brand slugs: `glowveda`, `munchkraft`, `vayu-home`.

### `/queue` query params
| Param | Values | Effect |
|---|---|---|
| `brand` | brand slug | filter. Set by clicking a health-grid cell |
| `platform` | `amazon` \| `flipkart` | filter |
| `severity` | `critical` \| `high` \| `medium` \| `low` | filter. Set by the overview stat tiles |
| `edit` | issue id | that card renders in edit state (textarea) |
| `decided` | decision id | shows the "Approved / Dismissed" strip at the top |
| `all` | `1` | show the full list. The default shows the top N and a "Show all" row |

The scope line ("Showing all brands on Amazon and Flipkart") reflects the active filters.

## 3. Server actions (form contracts)

| Action | Method + endpoint | Fields | On success |
|---|---|---|---|
| Upload data | `POST /upload` (multipart) | `listings`, `ads`, `reviews` (.csv, all required) | create snapshot `status='uploaded'` → redirect `/` (renders OverviewFresh) |
| Run audit | `POST /audit/run` | — | compute issues for latest snapshot, `status='audited'` → redirect `/` |
| Decide | `POST /queue/decisions` | `issue`, `decision` = `approve` \| `approve_edited` \| `dismiss`, `fix_text` (only with `approve_edited`) | insert decision, close issue → redirect `/queue?decided={decision_id}` (keep active filters) |
| Undo | `POST /queue/decisions/undo` | `decision_id` | mark decision undone, reopen issue → redirect `/queue#{issue_id}` |
| Edit (link, not a form) | `GET /queue?edit={issue_id}#{issue_id}` | — | — |
| Cancel edit (link) | `GET /queue#{issue_id}` | — | — |
| AI on/off | `POST /settings/ai` | `ai` (checkbox; absent = off) | persist setting → redirect back to the referring page |

Every queue card carries `id="{issue_id}"`, so redirects that end in `#{issue_id}` keep the reviewer's place.
Validate uploads server-side (headers, required columns, row count > 0). On failure, re-render the upload panel open with the error text. That error state is not drawn; style it as the `.hint` line in critical red.

## 4. Client islands (the only JS)

1. **`<CopyButton targetId>`**: any element with `data-copy-target`. Uses `navigator.clipboard.writeText` on the target's text or value, then sets the label to "Copied" for 2 s.
   - **No-JS fallback (required):** after an approve, the decided strip shows `final_text` in a `readonly` textarea, pre-selected, so Ctrl/Cmd+C works.
   - **"Approve & copy"** is a normal submit button. Copying happens in the decided strip after the redirect. Don't copy on submit: the decision isn't confirmed yet.
2. **`<AiToggle>`**: wraps the header checkbox and calls `form.requestSubmit()` on change. Include a `<noscript>` "Save" submit button so it works without JS.

Everything else (`<details>` upload panel, `<details>` ₹ tooltip, filters, edit mode) works with zero JS.

## 5. Data the UI reads (minimum fields)

```
snapshot   id, uploaded_at, audited_at, status('uploaded'|'audited'), row_counts{listings,ads,reviews}
listing    snapshot_id, sku, brand_slug, platform('amazon'|'flipkart'), platform_id (ASIN/FSN), title, image_count,
           bullet_count, price, mrp, stock, rating, review_count, buybox_owner, status, avg_daily_sales, avg_daily_units
ad_spend   snapshot_id, sku, platform, campaign, spend_per_day, active(bool)
review     snapshot_id, sku, platform, stars(1-5), text, date, verified(bool), language
issue      id, snapshot_id, sku, platform, brand_slug, rule_id, type_label, severity, impact_per_day, impact_calc_text,
           evidence[{label, value, bad:bool}] (2–4), fix{kind:'message'|'content', recipient, text | title+bullets[],
           source:'rule'|'ai'}, detected_at, status('open'|'approved'|'dismissed')
decision   id, issue_id, decision('approve'|'approve_edited'|'dismiss'), final_text, decided_at, undone_at
theme      sku, label, polarity('neg'|'pos'), count, window_days        (only if clustering ran)
settings   ai_enabled(bool)
```

Snapshot history on SKU pages compares the latest audited snapshot with the one before it.

## 6. Computation rules

**Queue sort:** `ORDER BY (severity = 'critical') DESC, impact_per_day DESC, detected_at ASC`.
Critical items always come first; within each group, the highest ₹ impact comes first.

**Portfolio total (hero, capped):**
`Σ over listings of min( Σ open issue impact on that listing, avg_daily_sales + daily_ad_spend )`.
Grid cells use the same per-listing capped figure, so the six cells add up exactly to the hero number. The tooltip also shows the uncapped sum.

**Per-issue impact.** Every term comes from CSV data or a named constant. Render `impact_calc_text` verbatim in the card rail.

| Rule ID | Issue | Default severity | Impact / day |
|---|---|---|---|
| `OOS-ADS-01` | Out of stock with ads running | critical | `ad_spend_per_day + avg_daily_sales` |
| `BUYBOX-01` | Buy Box / featured seller lost | critical | `avg_daily_sales × BUYBOX_SHARE` |
| `PRICE-GAP-02` | Price mismatch across platforms | high | `price_gap × avg_daily_units` (higher-priced listing) |
| `RATING-01` | Rating dropped below 4.0 | high | `avg_daily_sales × RATING_PENALTY` |
| `TITLE-LEN-01` | Title cut off on mobile | medium | `avg_daily_sales × TITLE_PENALTY` |
| `IMG-MIN-01` | Too few product images | medium | `avg_daily_sales × IMAGE_PENALTY` |
| `LOW-STOCK-01` | Low stock | low | `avg_daily_sales × LOW_STOCK_PENALTY` |

Put every constant in one config file (`lib/audit/config.ts`). Placeholder values from the canvas: `BUYBOX_SHARE 0.23`, `RATING_PENALTY 0.12`, `TITLE_PENALTY 0.06`, `IMAGE_PENALTY 0.11`, `TITLE_MOBILE_CUTOFF 80`, `RATING_FLOOR 4.0`, `IMAGE_MIN 6`.

## 7. AI on/off behaviour

| Element | AI on | AI off |
|---|---|---|
| Suggested fix | AI text + purple `AI draft` tag | rule template text + rule ID (`Rule OOS-ADS-01`) |
| Review translation | shown with `AI translation` tag | hidden |
| Complaint themes | chips + `AI-clustered` tag | section hidden |
| Brand summary paragraph | AI paragraph + tag | templated paragraph (see Components board) with no tag |

When AI is off, the AI tag must never render. Template output is finished content, not a fallback, so don't show any "AI unavailable" copy.
If an AI call fails while AI is on, use the template silently for that item.

## 8. States checklist (all drawn on the canvas)

- Overview: audited · awaiting audit (fresh upload) · "All clear" cell (green check)
- Queue: list · card edit state · decided strip with Undo + copy · empty "queue is clear" reward state
- SKU: both platforms · one platform ("Not listed on Flipkart") · snapshot deltas (bad = red, changed = blue, same = grey)
- Upload: idle · submitting (disabled button + progress bar, the only loading state)
- Not drawn, build to match: upload validation error, 404 for unknown SKU/brand

## 9. Accessibility (keep as drawn)

Native `<button>`, `<a>`, `<input>` with `<label>`. Severity is shown by shape + label + color, never color alone. Icon-only controls have an `aria-label`. Decided strip uses `role="status"`. Text contrast is ≥ 4.5:1. Don't lighten the greys.

## 10. Open assumptions (confirm with the business before launch)

1. Cap formula = `avg_daily_sales + daily_ad_spend` per listing.
2. All penalty constants in §6 are placeholders.
3. Sort rule: Critical pinned first, then ₹.
4. Brand week runs Monday–Sunday.
5. CSV column names are not specified yet. Map them to §5 fields in one parser module per file.
