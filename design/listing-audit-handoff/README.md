# Listing Audit — design handoff package

Open `pages/index.html` in a browser. Every page links to the others. Nothing needs a server; fonts load from Google Fonts.

| File | Screen | Next.js route |
|---|---|---|
| pages/index.html | Portfolio overview (audited) | `/` |
| pages/overview-awaiting-audit.html | Overview right after an upload, before the audit runs | `/` |
| pages/queue.html | Issue queue (decided strip, edit state on card #3) | `/queue` |
| pages/queue-empty.html | Queue with zero open issues | `/queue` |
| pages/sku.html | SKU detail, both platforms | `/sku/[sku]` |
| pages/sku-one-platform.html | SKU detail, listed on one platform only | `/sku/[sku]` |
| pages/brand.html | Brand weekly summary (one template for all brands) | `/brand/[brand]` |
| pages/components.html | Component sheet: tokens, badges, buttons, toggle, upload, states | reference only |
| pages/handoff.html | One-page engineering summary | reference only |

- `HANDOFF.md`: full spec covering routes, query params, form contracts, data fields, formulas, AI on/off rules, states and open assumptions. **Read this first.**
- `globals.css`: all styles, extracted. A SHARED section is identical across pages; PAGE sections differ by route.
- `source/*.dc.html`: the original design-canvas files, kept for reference. The `pages/` files are the same markup without the canvas runtime.

Porting notes:
- In `pages/`, `href` values point at the other static files so you can click through. The **real app route is in each link's `data-route` attribute**. Use that.
- Form `action`s, input `name`s and button `name`/`value`s are the server-action contract (HANDOFF.md §3). The forms don't submit anywhere in this static package.
- Each page still carries its own `<style>` block so it renders standalone. In the app, use `globals.css` instead.
- All names, SKUs, ₹ figures and dates are sample data.
