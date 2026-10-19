import Link from "next/link";
import { runAudit } from "@/app/actions";
import { Header } from "@/components/Header";
import { Icon, Plat, SevBadge, SevIcon } from "@/components/ui";
import { getPortfolio, type Portfolio, type PortfolioCell } from "@/lib/api";
import { SEVERITIES, SEV_CLASS, categoryLabel, daysSince, inr, num, plural } from "@/lib/format";

export const metadata = { title: { absolute: "Portfolio overview · Listing Audit" } };

const TILE_HINT = { critical: "Act today", high: "This week", medium: "Batch-fix", low: "When convenient" } as const;

function cellSummary(cell: PortfolioCell) {
  return SEVERITIES.filter((s) => cell.severity_counts[s] > 0).map((s) => `${cell.severity_counts[s]} ${s}`);
}

function brandRows(p: Portfolio) {
  return p.brands.map((brand) => {
    const cells = p.platforms.map((platform) => p.cells.find((c) => c.brand === brand && c.platform === platform)!);
    return { brand, slug: cells[0].brand_slug, category: cells[0].category, cells };
  });
}

function GridHead() {
  return (
    <thead>
      <tr>
        <th scope="col">
          <span style={{ paddingLeft: 10 }}>Brand</span>
        </th>
        <th scope="col">
          <span className="th-plat">
            <Plat platform="Amazon" withName />
          </span>
        </th>
        <th scope="col">
          <span className="th-plat">
            <Plat platform="Flipkart" withName />
          </span>
        </th>
      </tr>
    </thead>
  );
}

function AuditedCell({ cell }: { cell: PortfolioCell }) {
  const href = `/queue?brand=${cell.brand_slug}&platform=${cell.platform.toLowerCase()}`;
  if (cell.issue_count === 0) {
    return (
      <Link className="cell cell-ok" href={href} aria-label={`${cell.brand} on ${cell.platform}: all clear, no open issues.`}>
        <div className="ok-row">
          <Icon.OkCircle />
          All clear
        </div>
        <div className="cell-line">
          <span>{cell.listing_count ? `${plural(cell.listing_count, "listing")} checked` : `Not listed on ${cell.platform}`}</span>
        </div>
      </Link>
    );
  }
  const parts = cellSummary(cell);
  return (
    <Link
      className="cell"
      href={href}
      aria-label={`${cell.brand} on ${cell.platform}: ${parts.join(", ")}. ${inr(cell.capped_daily_loss_inr)} per day. View issues.`}
    >
      <div className="cell-top">
        <div className="counts">
          {SEVERITIES.map((s) => {
            const n = cell.severity_counts[s];
            return (
              <span key={s} className={`cc ${n ? `sev-${SEV_CLASS[s]}` : "is-zero"}`}>
                <SevIcon sev={s} outline={!n} />
                {n}
              </span>
            );
          })}
        </div>
        <span className="cell-amt">
          {inr(cell.capped_daily_loss_inr)}
          <small>/day</small>
        </span>
      </div>
      <div className="cell-line">
        <span>
          <b>{parts[0]}</b>
          {parts.length > 1 ? `, ${parts.slice(1).join(", ")}` : ""}
        </span>
        <span className="cell-go">View →</span>
      </div>
    </Link>
  );
}

function Audited({ p }: { p: Portfolio }) {
  const crit = p.severity_counts.critical;
  return (
    <main className="main">
      <section className="hero panel" aria-labelledby="loss-label">
        <div>
          <div className="eyebrow">
            <span id="loss-label">Estimated daily loss</span>
            <details className="tip">
              <summary aria-label="How this total is calculated">
                <Icon.Info />
              </summary>
              <div className="tip-pop panel pop">
                <b>Deduplicated, capped per listing</b>
                Each listing&apos;s open issues are summed, then capped at that listing&apos;s average daily sales plus daily
                ad spend, so one SKU failing three ways isn&apos;t counted three times. Uncapped sum:{" "}
                <span className="mono">{inr(p.uncapped_daily_loss_inr)}/day</span>.
              </div>
            </details>
          </div>
          <div className="hero-num">
            {inr(p.total_daily_loss_inr)}
            <small>/day</small>
          </div>
          <p className="hero-sub">
            {plural(p.open_issue_count, "open issue")} across {plural(p.flagged_listing_count, "listing")} ·{" "}
            {plural(p.brands.length, "brand")} · Amazon and Flipkart
          </p>
        </div>
        <div className="hero-r">
          <Link className="btn btn-primary btn-lg" href="/queue">
            View issue queue <Icon.Arrow />
          </Link>
          <span className="stamp">
            Critical first, then by ₹ impact · {crit ? `${crit} critical need action today` : "no critical issues open"}
          </span>
        </div>
      </section>

      <section className="tiles" aria-label="Open issues by severity">
        {SEVERITIES.map((s) => {
          const oldest = p.oldest_open_at[s];
          return (
            <Link key={s} className="tile panel" href={`/queue?severity=${s}`}>
              <SevBadge sev={s} />
              <span className="tile-n">{num(p.severity_counts[s])}</span>
              <span className="tile-f">
                <span>{oldest ? `Oldest open ${daysSince(oldest)}d` : "None open"}</span>
                <span>{TILE_HINT[s]}</span>
              </span>
            </Link>
          );
        })}
      </section>

      <section className="panel" aria-labelledby="grid-h">
        <div className="sec-head">
          <h2 id="grid-h">Health by brand and platform</h2>
          <span>Select a cell to open its issues in the queue</span>
        </div>
        <div className="hgrid-wrap">
          <table className="hgrid">
            <GridHead />
            <tbody>
              {brandRows(p).map((row) => (
                <tr key={row.brand}>
                  <th scope="row">
                    <div className="b-name">{row.brand}</div>
                    <div className="b-cat">
                      {categoryLabel(row.category)} · {plural(row.cells.reduce((n, c) => n + c.listing_count, 0), "listing")}
                    </div>
                    <Link className="b-link" href={`/brand/${row.slug}`}>
                      Weekly summary →
                    </Link>
                  </th>
                  {row.cells.map((cell) => (
                    <td key={cell.platform}>
                      <AuditedCell cell={cell} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}

function AwaitingAudit({ p }: { p: Portfolio }) {
  const snap = p.snapshot!;
  return (
    <main className="main">
      <section className="hero panel" aria-labelledby="loss-label">
        <div>
          <div className="eyebrow">
            <span id="loss-label">Estimated daily loss</span>
          </div>
          <div className="hero-num" aria-label="Not computed yet">
            —
          </div>
          <p className="hero-sub">New data is in. Nothing has been checked yet.</p>
          <ul className="files" aria-label="Uploaded files">
            {(["listings", "ads", "reviews"] as const).map((f) => (
              <li key={f}>
                <Icon.Tick />
                <span className="mono">{f}.csv</span>
                <span className="n">{plural(snap.row_counts[f] ?? 0, "row")}</span>
              </li>
            ))}
          </ul>
        </div>
        <div className="hero-r">
          <form action={runAudit}>
            <button className="btn btn-primary btn-lg" type="submit">
              <Icon.Play />
              Run audit
            </button>
            <span className="stamp">
              Checks {plural(p.listing_count, "listing")} across {p.brands.length * p.platforms.length} brand × platform
              pairs
            </span>
          </form>
        </div>
      </section>

      <section className="tiles" aria-label="Open issues by severity">
        {SEVERITIES.map((s) => (
          <div key={s} className="tile panel">
            <SevBadge sev={s} />
            <span className="tile-n" aria-label="Not computed">
              —
            </span>
            <span className="tile-f">After audit</span>
          </div>
        ))}
      </section>

      <section className="panel" aria-labelledby="grid-h">
        <div className="sec-head">
          <h2 id="grid-h">Health by brand and platform</h2>
          <span>Listings loaded per cell · checks run when you start the audit</span>
        </div>
        <div className="hgrid-wrap">
          <table className="hgrid">
            <GridHead />
            <tbody>
              {brandRows(p).map((row) => (
                <tr key={row.brand}>
                  <th scope="row">
                    <div className="b-name">{row.brand}</div>
                    <div className="b-cat">
                      {categoryLabel(row.category)} · {plural(row.cells.reduce((n, c) => n + c.listing_count, 0), "listing")}
                    </div>
                  </th>
                  {row.cells.map((cell) => (
                    <td key={cell.platform}>
                      <div className="cell">
                        <div className="wait-row">
                          <Icon.Wait />
                          Awaiting audit
                        </div>
                        <div className="cell-line">{plural(cell.listing_count, "listing")} loaded</div>
                      </div>
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}

export default async function OverviewPage() {
  const p = await getPortfolio();
  const awaiting = p.snapshot?.status === "uploaded";
  return (
    <div className={`app ${awaiting ? "pg-fresh" : "pg-overview"}`}>
      <Header active="overview" />
      {p.has_data ? (
        awaiting ? (
          <AwaitingAudit p={p} />
        ) : (
          <Audited p={p} />
        )
      ) : (
        <main className="main">
          <section className="panel nf">
            <h1>No data yet</h1>
            <p>Upload the listings, ads and reviews CSVs from the header to run the first audit.</p>
          </section>
        </main>
      )}
    </div>
  );
}
