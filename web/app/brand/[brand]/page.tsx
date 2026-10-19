import Link from "next/link";
import { notFound } from "next/navigation";
import { Header } from "@/components/Header";
import { CopyButton } from "@/components/client";
import { AiTag, Plat, SevBadge } from "@/components/ui";
import { getBrandReport, type Issue } from "@/lib/api";
import { categoryLabel, day, inr, num, openFor, plural, time, weekRange } from "@/lib/format";

type Params = Promise<{ brand: string }>;
type SearchParams = Promise<Record<string, string | string[] | undefined>>;

export async function generateMetadata({ params }: { params: Params }) {
  const { brand } = await params;
  const r = await getBrandReport(brand);
  return { title: r ? `${r.brand} weekly summary` : "Brand not found" };
}

function StateTag({ issue }: { issue: Issue }) {
  if (issue.status === "approved")
    return <span className="state-tag ok">Approved {issue.decided_at ? day(issue.decided_at) : ""}</span>;
  if (issue.status === "dismissed")
    return <span className="state-tag">Dismissed {issue.decided_at ? day(issue.decided_at) : ""}</span>;
  return <span className="state-tag">{openFor(issue.detected_at).replace("Open ", "Open · ")}</span>;
}

export default async function BrandPage({ params, searchParams }: { params: Params; searchParams: SearchParams }) {
  const { brand } = await params;
  const { week } = await searchParams;
  const r = await getBrandReport(brand, typeof week === "string" ? week : undefined);
  if (!r) notFound();

  const weekLabel = (iso: string) => {
    const end = new Date(`${iso}T00:00:00Z`);
    end.setUTCDate(end.getUTCDate() + 6);
    return weekRange(iso, end.toISOString().slice(0, 10)).replace(/ \d{4}$/, "");
  };

  return (
    <div className="app pg-brand">
      <Header active={r.brand_slug} />
      <div className="paper">
        <article className="doc">
          <div className="week">
            <span className="eyebrow">Weekly summary</span>
            <nav className="week-nav" aria-label="Week">
              {r.prev_week ? (
                <Link href={`/brand/${r.brand_slug}?week=${r.prev_week}`} aria-label="Previous week">
                  ← {weekLabel(r.prev_week)}
                </Link>
              ) : null}
              <span className="cur">{weekRange(r.week_start, r.week_end)}</span>
              {r.next_week ? (
                <Link href={`/brand/${r.brand_slug}?week=${r.next_week}`} aria-label="Next week">
                  {weekLabel(r.next_week)} →
                </Link>
              ) : null}
            </nav>
          </div>

          <header className="title">
            <h1>{r.brand}</h1>
            <p>
              {categoryLabel(r.category)} · {plural(r.listing_count, "listing")} on Amazon and Flipkart
            </p>
          </header>

          <section className="summary" aria-label="Summary">
            <div className="summary-meta">
              {r.ai_generated ? <AiTag>AI-written from this week&apos;s audit data</AiTag> : <span />}
              {r.has_data ? <CopyButton targetId="summary-text" label="Copy summary" className="btn" /> : null}
            </div>
            <p className="prose" id="summary-text">
              {r.summary}
            </p>
          </section>

          {r.has_data ? (
            <>
              <dl className="stats">
                <div className="stat">
                  <dt>Issues raised</dt>
                  <dd>{num(r.total_issues)}</dd>
                </div>
                <div className="stat">
                  <dt>Estimated loss</dt>
                  <dd>
                    {inr(r.total_impact_inr)}
                    <small> /day</small>
                  </dd>
                </div>
                <div className="stat">
                  <dt>Approved</dt>
                  <dd>{num(r.approved_count)}</dd>
                </div>
                <div className="stat">
                  <dt>Dismissed</dt>
                  <dd>{num(r.dismissed_count)}</dd>
                </div>
                <div className="stat">
                  <dt>Still open</dt>
                  <dd>{num(r.open_issues)}</dd>
                </div>
              </dl>

              {r.top_issues.length ? (
                <section className="top" aria-labelledby="top-h">
                  <h2 id="top-h">Highest-impact items this week</h2>
                  <ol>
                    {r.top_issues.map((i, idx) => (
                      <li key={i.id}>
                        <span className="i">{String(idx + 1).padStart(2, "0")}</span>
                        <div className="what">
                          <b>{i.issue_label}</b>
                          <span>
                            <Link href={`/sku/${encodeURIComponent(i.sku)}`}>{i.sku}</Link>
                            <Plat platform={i.platform} />
                            <SevBadge sev={i.severity} />
                          </span>
                        </div>
                        <div className="amt">
                          <b>{inr(i.impact_inr)}/day</b>
                          <StateTag issue={i} />
                        </div>
                      </li>
                    ))}
                  </ol>
                </section>
              ) : null}
            </>
          ) : null}

          <p className="foot">
            {r.audited_at ? `Built from the ${day(r.audited_at)} audit (${time(r.audited_at)}). ` : ""}
            Loss figures are per day and capped per listing, the same way as the portfolio total.
          </p>
        </article>
      </div>
    </div>
  );
}
