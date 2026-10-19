# Frontend Design Brief — Marketplace Listing Audit

This is an independent project. Don't carry over or match the visual identity of any other
brief you may have seen from this user — this one gets its own look.

## What this is

A dashboard for an Intent Farm account manager (AM). Intent Farm is a performance-marketing
and marketplace-growth agency running several brands' listings on Amazon and Flipkart.
Listings break quietly — out of stock while ads keep spending, images missing, titles
cut off, prices diverging across platforms, ratings sliding, Buy Box lost. The dashboard
audits every listing, flags issues, attaches an estimated daily rupee impact, ranks them by
urgency, and proposes a fix the AM approves (copy-and-send or a task — nothing here ever
auto-sends or auto-fixes anything).

## Who uses it, and how

- **Primary user:** the AM, at a desk, most days. Opens the dashboard, scans a health grid,
  drops into a ranked issue queue, triages several cards in a row (approve / edit / dismiss
  each), occasionally opens a single SKU or a brand's weekly summary, occasionally
  re-uploads a CSV after fixing something upstream.
- **Secondary context:** this is also a hiring-application artifact. A reviewer may open a
  live link once and look at it for under a minute. The first screen needs to read as "a
  real operational tool," not a demo.
- Desktop-first. Dense information, calm colors, clear hierarchy — this is a tool someone
  pays for, not a marketing page. Should degrade reasonably down to ~1024px; no phone layout
  needed.

## Design system to establish

- **Severity** — 4 levels (critical / high / medium / low). Communicate with color **and**
  an icon/label, never color alone.
- **Platform badge** — Amazon vs Flipkart. Needs to be scannable at a glance down a long
  list of cards, so keep it small but visually distinct between the two.
- **Rule-based vs AI-generated tag** — a small marker on any suggested-fix text, review
  theme, or brand-summary paragraph that came from the AI layer rather than a template.
  When AI is off, this tag simply never appears — the template version should look like a
  finished, intentional piece of content, not a fallback or an apology.
- **₹ impact number** — two variants. (1) The per-issue number used on queue cards: large,
  bold, the primary visual anchor of the card — this is what the AM ranks by. (2) The
  "capped portfolio total" shown once on the overview page, with a small info/tooltip
  affordance explaining it's deduplicated (the total is capped per listing so one SKU
  failing three ways doesn't triple-count its own wasted spend).
- **Action control** — a 3-state Approve / Edit / Dismiss button group. This becomes a
  native HTML form on our end — style it as buttons, no JS behavior required from you.
- **AI on/off toggle** — a simple switch, always visible in the global header, not buried in
  a settings page (there is no settings page).
- **CSV upload affordance** — 3 labeled file inputs (listings / ads / reviews) in a bordered
  card or small panel. No drag-and-drop requirement.

## Screens

### 1. Portfolio Overview — `/`
The first thing anyone opens. Answers "how bad is it right now, across everything."

- A grid: rows = brands (**GlowVeda** skincare, **Munchkraft** snacks, **Vayu Home** home
  appliances), columns = platform (Amazon, Flipkart). Each cell is a compact health summary:
  issue counts by severity (e.g. 4 small colored counts or a stacked bar) plus a one-line
  label like "2 critical, 1 high."
- One large hero number near the top: "Estimated daily loss: ₹X,XXX" (the capped total)
  with the info/tooltip affordance described above.
- Below that: 4 stat tiles, one per severity level, with the portfolio-wide count.
- **Empty/edge states to design:** a brand×platform cell with zero issues should look calm
  and positive — a checkmark and "All clear," not just a blank cell. Also design the state
  right after a fresh CSV upload before anything has been computed yet.
- Primary action out of this screen: into the issue queue — either a "View issue queue"
  button near the hero number, or clicking a cell to go to a queue filtered to that
  brand/platform.

### 2. Issue Queue — `/queue`
The actual work screen — where the AM spends the most time. A vertically ranked list of
cards, highest ₹ impact first. Each card:

- SKU + platform badge + brand name, small, top-left.
- Issue type label (e.g. "Out of stock with ads running") + severity badge.
- ₹ impact/day — large and bold, the card's visual anchor.
- Evidence — 2-4 short label:value data points (e.g. "Stock: 0 · Ad spend: ₹850/day · 4
  days"), not prose.
- Suggested fix — 1-3 sentences of copy-ready message text, or for content issues a short
  rewritten title + bullets block — in a lightly bordered/quoted block, with the
  rule-based/AI-generated tag.
- Action row: Approve / Edit / Dismiss. Approve should visually suggest "this copies text
  and logs a decision." Edit should suggest "the suggested-fix text becomes editable before
  you approve it."

A single default sort by impact is enough — don't over-design filter UI. **Empty state:**
"No open issues — queue is clear," designed as a reward state, not a dead end. **Decided
card:** once approved or dismissed, either the card disappears with a small toast/confirm
strip, or it stays with a muted "Approved ✓ 2m ago" treatment — pick whichever is cleaner;
disappearing-with-a-toast is probably simplest.

### 3. SKU Detail — `/sku/[sku]`
Deep-dive on one SKU across both platforms.

- Two columns side by side, Amazon | Flipkart. Each shows: title, image count, bullet
  count, price, MRP, stock, rating, review count, Buy Box/featured-seller owner, status.
- Below/beside the columns: a snapshot-history strip — a simple before/after comparison of
  the two snapshots, with price/stock/rating deltas highlighted where they changed.
- Below that: a reviews summary — star distribution (small bar or count per star), 2-3
  representative review quotes (some will be in Hinglish, e.g. "Product acha tha pehle, ab
  box leak ho ke aaya, bahut ghatiya packaging 😡"), and a complaint-theme chip list when
  theme clustering has run.
- **Edge case to design:** a SKU that exists on only one platform — the missing column
  should read as "Not listed on Flipkart," not a blank or broken-looking column.

### 4. Brand Weekly Summary — `/brand/[brand]`
A short, read-only, report-feeling page — intentionally the lightest screen, more
whitespace, more like a document than the dense screens above.

- Brand name/header.
- A short written paragraph (AI-written or templated) covering what happened that week.
- A small stat row: total issues, total estimated loss, approved/dismissed counts for the
  week.
- Optionally a short list of the 3-5 highest-impact items from the week.

## Global elements (every screen)

A persistent header/nav: product name, links to Overview / Queue / brand pages, the AI
on/off toggle (always visible), and a small "Upload data" entry point that opens the
3-file CSV form.

## What NOT to design

- No login/auth screens.
- No settings page beyond the single AI toggle in the header.
- No mobile layout. Desktop-first; graceful down to ~1024px is enough.
- No client-side loading skeletons or spinners — pages are fully server-rendered. If you
  want one loading state, the CSV upload submit is the only place it'd matter.
- No multi-step wizards. Every action is single-step.

## Deliverable format

Static HTML + CSS per screen (the 4 pages above, plus the shared header/nav and the shared
components: severity badge, platform badge, rule/AI tag, impact number, action button
group, AI toggle, upload form), via your export/handover link. This gets adapted directly
into Next.js Server Component pages, so semantic HTML with plain CSS or Tailwind utility
classes is easier to port than anything that depends on its own JS runtime. Keep
interactive-looking elements (buttons, toggle, upload inputs) as plain HTML form
elements/semantics even though they won't be functional in the handoff itself — they get
wired to real server actions on our end.

## Sample content to design against (so nothing is lorem ipsum)

- Brands: GlowVeda (skincare), Munchkraft (snacks), Vayu Home (home appliances).
- Example card: `GLOWVEDA-FW-014` · Amazon · "Out of stock with ads running" · Critical ·
  **₹1,240/day** · Evidence: "Stock: 0 · Ad spend: ₹850/day for 4 days · Daily sales avg:
  ₹390" · Suggested fix (rule-based): "Pause Sponsored Products campaign for
  GLOWVEDA-FW-014 until restock — currently burning ₹850/day with zero fulfillable orders."
- Example review (Hinglish, 2★): "Product acha tha pehle, ab box leak ho ke aaya, bahut
  ghatiya packaging 😡"
