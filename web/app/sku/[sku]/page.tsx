import Link from "next/link";
import { notFound } from "next/navigation";
import { Header } from "@/components/Header";
import { AiTag, Icon, Plat, SevBadge } from "@/components/ui";
import { getPortfolio, getSku, type Issue, type PlatformDetail, type Review, type SkuDetail, type SnapshotRow } from "@/lib/api";
import { capitalize, day, inr, num, plural } from "@/lib/format";

type Params = Promise<{ sku: string }>;

export async function generateMetadata({ params }: { params: Params }) {
  const { sku } = await params;
  return { title: decodeURIComponent(sku) };
}

const STOCK_CODES = ["oos_ads_live", "low_stock_high_spend"];
const PRICE_CODES = ["price_mismatch", "price_above_mrp", "price_shock"];
const MAIN_FIELDS = ["price", "stock", "rating", "review_count", "buybox_owner"];

function openIssue(pd: PlatformDetail, codes: string[]): Issue | undefined {
  return pd.issues.find((i) => i.status === "open" && codes.includes(i.issue_code));
}

function headline(d: SkuDetail): string {
  const order = ["Amazon", "Flipkart"].map((p) => d.platforms[p]).filter(Boolean) as PlatformDetail[];
  const clean = order.find((pd) => !pd.issues.some((i) => i.issue_code === "weak_content"));
  return (clean ?? order[0]).latest.title;
}

function PlatformColumn({ pd, other }: { pd: PlatformDetail; other?: PlatformDetail }) {
  const l = pd.latest;
  const stock = openIssue(pd, STOCK_CODES);
  const price = openIssue(pd, PRICE_CODES);
  const rating = openIssue(pd, ["rating_drop"]);
  const buybox = openIssue(pd, ["lost_buybox"]);
  const status = openIssue(pd, ["suppressed"]);
  const content = openIssue(pd, ["weak_content"]);
  const discount = l.mrp > 0 && l.price < l.mrp ? Math.round((1 - l.price / l.mrp) * 100) : 0;
  const id = `c-${pd.platform.toLowerCase()}`;

  return (
    <section className="col panel" aria-labelledby={id}>
      <div className="col-head">
        <h2 id={id}>
          <Plat platform={pd.platform} withName />
        </h2>
        <span className="col-id">As of {day(l.snapshot_date)}</span>
      </div>
      <dl className="attrs">
        <dt className="first">Title</dt>
        <dd className="first">
          <span className="ttl">
            {l.title}
            <small>
              {plural(l.title.length, "character")}
              {content ? " · content gaps flagged" : ""}
            </small>
          </span>
        </dd>
        <dt>Images</dt>
        <dd>
          <span className={`v${content ? " bad" : ""}`}>{l.image_count}</span>
        </dd>
        <dt>Bullets</dt>
        <dd>
          <span className={`v${content ? " bad" : ""}`}>{l.bullet_count}</span>
        </dd>
        <dt>Price</dt>
        <dd>
          <span className={`v${price ? " bad" : ""}`}>{inr(l.price)}</span>
          {other && other.latest.price !== l.price ? <span className="differs">Differs</span> : null}
        </dd>
        <dt>MRP</dt>
        <dd>
          <span className="v">{inr(l.mrp)}</span>
          {l.price > l.mrp ? (
            <span className="hint bad">Price above MRP</span>
          ) : discount ? (
            <span className="hint">{discount}% off</span>
          ) : null}
        </dd>
        <dt>Stock</dt>
        <dd>
          <span className={`v${stock ? " bad" : ""}`}>{plural(l.stock, "unit")}</span>
          {stock ? (
            <SevBadge sev={stock.severity} label={stock.issue_code === "oos_ads_live" ? "Out of stock" : "Low stock"} />
          ) : null}
        </dd>
        <dt>Rating</dt>
        <dd>
          <span className={`v${rating ? " bad" : ""}`}>{l.rating.toFixed(1)}</span>
          <span className="hint">{plural(l.review_count, "review")}</span>
        </dd>
        <dt>{pd.buybox_label}</dt>
        <dd className={buybox ? "bad" : undefined}>{l.buybox_owner}</dd>
        <dt>Status</dt>
        <dd>
          <span className="st">
            <span
              className="st-dot"
              style={{ background: status ? "#A61B1B" : l.status.toLowerCase() === "active" ? "#1F6B45" : "#B44D0A" }}
              aria-hidden="true"
            />
            {capitalize(l.status)}
          </span>
        </dd>
      </dl>
    </section>
  );
}

function MissingColumn({ platform, sku, brand, siblings }: { platform: string; sku: string; brand: string; siblings: number }) {
  return (
    <section className="col panel col-missing" aria-labelledby="c-missing">
      <div className="col-head">
        <h2 id="c-missing">
          <Plat platform={platform} withName />
        </h2>
        <span className="col-id">No listing</span>
      </div>
      <div className="missing">
        <div className="missing-ic">
          <Icon.Missing />
        </div>
        <h3>Not listed on {platform}</h3>
        <p>
          The latest listings upload has no {platform} row for {sku}. {brand} has {plural(siblings, "other SKU")} live on{" "}
          {platform}.
        </p>
        <p className="hint">Cross-platform checks (price gap) are skipped for this SKU.</p>
      </div>
    </section>
  );
}

function Delta({ row }: { row?: SnapshotRow }) {
  if (!row) return <span className="d d-same">—</span>;
  const cls = row.tone === "bad" ? "d-bad" : row.tone === "chg" ? "d-chg" : "d-same";
  return <span className={`d ${cls}`}>{row.change ?? "No change"}</span>;
}

function SnapshotTable({ d }: { d: SkuDetail }) {
  const pds = ["Amazon", "Flipkart"].map((p) => d.platforms[p]).filter(Boolean) as PlatformDetail[];
  const withPrev = pds.find((pd) => pd.previous);
  if (!withPrev) {
    return <p className="empty-note">Only one snapshot uploaded for this SKU, so there is nothing to compare yet.</p>;
  }
  const prevDate = day(withPrev.previous!.snapshot_date);
  const lastDate = day(withPrev.latest.snapshot_date);
  const byField = (pd: PlatformDetail) => Object.fromEntries(pd.snapshot_rows.map((r) => [r.field, r]));
  const maps = pds.map(byField);
  const fields = pds[0].snapshot_rows
    .map((r) => r.field)
    .filter((f) => MAIN_FIELDS.includes(f) || maps.some((m) => m[f] && m[f].tone !== "same"));
  const label = (f: string) =>
    f === "buybox_owner" ? (pds.length > 1 ? "Buy Box / featured" : maps[0][f].label) : maps[0][f]?.label ?? f;

  return (
    <div className="tbl-wrap">
      <table className="snap">
        <thead>
          {pds.length > 1 ? (
            <tr>
              <th scope="col" />
              {pds.map((pd) => (
                <th key={pd.platform} scope="colgroup" colSpan={3} className="grp">
                  <Plat platform={pd.platform} /> {pd.platform}
                </th>
              ))}
            </tr>
          ) : null}
          <tr>
            <th scope="col" style={{ paddingLeft: 18 }}>
              Metric
            </th>
            {pds.map((pd) => [
              <th key={`${pd.platform}-p`} scope="col" className={pds.length > 1 ? "grp" : undefined}>
                {prevDate}
              </th>,
              <th key={`${pd.platform}-l`} scope="col">
                {lastDate}
              </th>,
              <th key={`${pd.platform}-c`} scope="col">
                Change
              </th>,
            ])}
          </tr>
        </thead>
        <tbody>
          {fields.map((f) => {
            const changed = maps.some((m) => m[f] && m[f].tone !== "same");
            return (
              <tr key={f} className={changed ? "chg" : undefined}>
                <th scope="row">{label(f)}</th>
                {maps.map((m, i) => {
                  const row = m[f];
                  const numeric = f !== "buybox_owner" && f !== "status";
                  return [
                    <td key={`${i}-p`} className={`${numeric ? "n " : ""}${pds.length > 1 ? "grp" : ""}`.trim() || undefined}>
                      {row?.previous ?? "—"}
                    </td>,
                    <td key={`${i}-l`} className={numeric ? "n" : undefined}>
                      {row?.latest ?? "—"}
                    </td>,
                    <td key={`${i}-c`}>
                      <Delta row={row} />
                    </td>,
                  ];
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

const stars = (n: number) => "★".repeat(n) + "☆".repeat(5 - n);

function Quote({ r }: { r: Review }) {
  return (
    <figure className="q">
      <div className="q-meta">
        <span className={`q-stars${r.stars >= 4 ? " hi" : ""}`} role="img" aria-label={`${r.stars} out of 5 stars`}>
          {stars(r.stars)}
        </span>
        <Plat platform={r.platform} />
        <span>{day(r.review_date)}</span>
      </div>
      <blockquote>{r.text}</blockquote>
      {r.translation ? (
        <div className="tr">
          <AiTag>AI translation</AiTag>“{r.translation}”
        </div>
      ) : null}
    </figure>
  );
}

function Reviews({ d }: { d: SkuDetail }) {
  const total = d.reviews.length;
  const where = Object.keys(d.platforms).length > 1 ? "Both platforms" : `${Object.keys(d.platforms)[0]} only`;
  return (
    <section className="panel" aria-labelledby="rev-h">
      <div className="sec-head">
        <h2 id="rev-h">Reviews</h2>
        <span>
          {where} · {plural(total, "review")}
        </span>
      </div>
      {total === 0 ? (
        <p className="empty-note">No reviews in the uploaded file for this SKU.</p>
      ) : (
        <>
          <div className="rev">
            <div className="stars">
              <div className="avg">
                <b>{d.average_stars?.toFixed(1)}</b>
                <span>average across uploaded reviews</span>
              </div>
              {["5", "4", "3", "2", "1"].map((s) => {
                const n = d.star_distribution[s] ?? 0;
                const pct = Math.round((n / total) * 100);
                return (
                  <div className="srow" key={s}>
                    <span className="lbl">{s}★</span>
                    <div className="track">
                      <div className={`fill${Number(s) <= 2 ? " lo" : ""}`} style={{ width: `${pct}%` }} />
                    </div>
                    <span className="c">
                      {num(n)} · {pct}%
                    </span>
                  </div>
                );
              })}
            </div>
            <div className="quotes">
              {d.representative_reviews.map((r, i) => (
                <Quote key={`${r.review_date}-${i}`} r={r} />
              ))}
            </div>
          </div>
          {d.complaint_themes.length ? (
            <div className="themes">
              <div className="themes-h">
                Complaint and praise themes {d.themes_ai_generated ? <AiTag>AI-clustered</AiTag> : null}
                <span className="m">
                  {d.themes_ai_generated ? `from ${plural(total, "review")}` : `keyword match across ${plural(total, "review")}`}
                </span>
              </div>
              <ul className="chips">
                {d.complaint_themes.map((t) => (
                  <li key={`${t.polarity}-${t.theme}`} className={`chip ${t.polarity}`} title={`e.g. “${t.example_quote}”`}>
                    <span className="g" aria-label={t.polarity === "neg" ? "Complaint" : "Praise"}>
                      {t.polarity === "neg" ? "−" : "+"}
                    </span>
                    {capitalize(t.theme)}
                    <span className="n">{t.count}</span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </>
      )}
    </section>
  );
}

export default async function SkuPage({ params }: { params: Params }) {
  const { sku: raw } = await params;
  const sku = decodeURIComponent(raw);
  const [d, p] = await Promise.all([getSku(sku), getPortfolio()]);
  if (!d) notFound();

  const listed = ["Amazon", "Flipkart"].filter((pl) => d.platforms[pl]);
  const single = d.missing_platforms.length > 0;
  const open = Object.values(d.platforms)
    .flatMap((pd) => pd.issues)
    .filter((i) => i.status === "open");

  return (
    <div className={`app ${single ? "pg-sku-single" : "pg-sku"}`}>
      <Header active="" />
      <main className="main">
        <nav className="crumbs" aria-label="Breadcrumb">
          <Link href="/">Overview</Link>
          <span aria-hidden="true">/</span>
          <Link href={`/brand/${d.brand_slug}`}>{d.brand}</Link>
          <span aria-hidden="true">/</span>
          <span aria-current="page" className="mono">
            {d.sku}
          </span>
        </nav>

        <div className="sku-head">
          <div>
            <h1>{headline(d)}</h1>
            <div className="sku-id">
              {d.sku} · {d.brand} · listed on {listed.length > 1 ? "Amazon and Flipkart" : `${listed[0]} only`}
            </div>
          </div>
          {open.length ? (
            <div className="open-issues" aria-label="Open issues on this SKU">
              {open.map((i) => (
                <Link key={i.id} className="oi" href={`/queue?all=1#iss-${i.id}`}>
                  <SevBadge sev={i.severity} />
                  <Plat platform={i.platform} />
                  {i.issue_label}
                  <span className="num">{inr(i.impact_inr)}/day</span>
                </Link>
              ))}
            </div>
          ) : null}
        </div>

        <div className="cols">
          {["Amazon", "Flipkart"].map((pl) => {
            const pd = d.platforms[pl];
            if (pd) return <PlatformColumn key={pl} pd={pd} other={d.platforms[pl === "Amazon" ? "Flipkart" : "Amazon"]} />;
            const cell = p.cells.find((c) => c.brand === d.brand && c.platform === pl);
            return <MissingColumn key={pl} platform={pl} sku={d.sku} brand={d.brand} siblings={cell?.listing_count ?? 0} />;
          })}
        </div>

        <section className="panel" aria-labelledby="snap-h">
          <div className="sec-head">
            <h2 id="snap-h">What changed between snapshots</h2>
            <span>{single ? `${listed[0]} only · ` : ""}changed rows highlighted</span>
          </div>
          <SnapshotTable d={d} />
        </section>

        <Reviews d={d} />
      </main>
    </div>
  );
}
