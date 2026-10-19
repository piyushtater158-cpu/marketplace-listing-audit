import Link from "next/link";
import { decide, undoDecision } from "@/app/actions";
import { Header } from "@/components/Header";
import { CopyButton, SelectedText } from "@/components/client";
import { AiTag, Icon, Plat, SevBadge } from "@/components/ui";
import { getBrands, getDecision, getIssues, getPortfolio, type Decision, type Issue } from "@/lib/api";
import { day, inr, num, openFor, plural, recipientLabel, time } from "@/lib/format";

export const metadata = { title: "Issue queue" };

const TOP_N = 10;

type Filters = { brand?: string; platform?: string; severity?: string; all?: string };
type SearchParams = Promise<Record<string, string | string[] | undefined>>;

function queueHref(filters: Filters, extra: Record<string, string> = {}, hash = ""): string {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries({ ...filters, ...extra })) if (v) qs.set(k, v);
  const s = qs.toString();
  return `/queue${s ? `?${s}` : ""}${hash}`;
}

function BackFields({ filters }: { filters: Filters }) {
  return (
    <>
      {Object.entries(filters).map(([k, v]) => (v ? <input key={k} type="hidden" name={`back_${k}`} value={v} /> : null))}
    </>
  );
}

function FixBlock({ issue, editing }: { issue: Issue; editing: boolean }) {
  const fix = issue.fix;
  const to = recipientLabel(issue.recipient, issue.brand, issue.issue_code);
  const tag = fix.source === "ai" ? <AiTag>AI draft</AiTag> : <span className="rule-tag">Rule {issue.rule_id}</span>;

  if (editing) {
    const fieldId = `fix-${issue.id}`;
    return (
      <div className="fix">
        <div className="fix-head">
          <label htmlFor={fieldId}>
            {fix.kind === "content" ? "Suggested rewrite" : "Suggested message"}{" "}
            <span className="to">· {fix.kind === "content" ? "title + bullets" : `to ${to}`} · editing</span>
          </label>
          {tag}
        </div>
        <textarea id={fieldId} name="fix_text" defaultValue={issue.suggested_fix} rows={fix.kind === "content" ? 7 : 3} />
        <span className="edit-note">
          <Icon.EditNote />
          Your edited text is what gets copied and logged
        </span>
      </div>
    );
  }

  if (fix.kind === "content") {
    return (
      <div className="fix">
        <div className="fix-head">
          <span>
            Suggested rewrite <span className="to">· title + bullets · to {to}</span>
          </span>
          {tag}
        </div>
        <span className="fix-lbl">
          Title · {fix.title?.length ?? 0} chars{fix.title_note ? ` · ${fix.title_note}` : ""}
        </span>
        <p className="fix-title">{fix.title}</p>
        <span className="fix-lbl">Bullets</span>
        <ul>
          {(fix.bullets ?? []).map((b) => (
            <li key={b}>{b}</li>
          ))}
        </ul>
      </div>
    );
  }

  return (
    <div className="fix">
      <div className="fix-head">
        <span>
          Suggested message <span className="to">· to {to}</span>
        </span>
        {tag}
      </div>
      <p>{fix.text}</p>
    </div>
  );
}

function IssueCard({ issue, rank, editing, filters }: { issue: Issue; rank: number; editing: boolean; filters: Filters }) {
  const anchor = `#iss-${issue.id}`;
  return (
    <li>
      <article className={`card panel${editing ? " editing" : ""}`} id={`iss-${issue.id}`} aria-labelledby={`i-${issue.id}`}>
        <form action={decide}>
          <input type="hidden" name="issue" value={issue.id} />
          <BackFields filters={filters} />
          <div className="card-body">
            <div className="card-main">
              <div className="meta">
                <span className="rank">#{rank}</span>
                <Link className="sku" href={`/sku/${encodeURIComponent(issue.sku)}`}>
                  {issue.sku}
                </Link>
                <Plat platform={issue.platform} />
                <span className="dot" aria-hidden="true" />
                <span>{issue.brand}</span>
              </div>
              <div className="issue">
                <h2 id={`i-${issue.id}`}>{issue.issue_label}</h2>
                <SevBadge sev={issue.severity} />
              </div>
              <dl className="ev">
                {issue.evidence_points.map((pt) => (
                  <div key={`${pt.label}-${pt.value}`}>
                    <dt>{pt.label}</dt>
                    <dd className={pt.bad ? "bad" : undefined}>{pt.value}</dd>
                  </div>
                ))}
              </dl>
              <FixBlock issue={issue} editing={editing} />
            </div>
            <div className="card-rail">
              <div className="impact">
                {inr(issue.impact_inr)}
                <small>/day</small>
              </div>
              <div className="rail-lbl">estimated loss</div>
              <div className="rail-calc">{issue.impact_calc_text}</div>
            </div>
          </div>
          <div className="card-foot">
            <span className="foot-meta">
              <span>Detected {day(issue.detected_at)}</span>
              <span>{openFor(issue.detected_at)}</span>
            </span>
            <div className="actions" role="group" aria-label={`Decision for ${issue.sku}`}>
              {editing ? (
                <>
                  <Link className="btn btn-ghost" href={queueHref(filters, {}, anchor)}>
                    Cancel edit
                  </Link>
                  <button className="btn btn-primary" type="submit" name="decision" value="approve_edited">
                    <Icon.ApproveCopy />
                    Approve edited &amp; copy
                  </button>
                </>
              ) : (
                <>
                  <button className="btn btn-ghost" type="submit" name="decision" value="dismiss">
                    <Icon.Dismiss />
                    Dismiss
                  </button>
                  <Link className="btn" href={queueHref(filters, { edit: String(issue.id) }, anchor)}>
                    <Icon.Edit />
                    Edit text
                  </Link>
                  <button className="btn btn-primary" type="submit" name="decision" value="approve">
                    <Icon.ApproveCopy />
                    Approve &amp; copy
                  </button>
                </>
              )}
            </div>
          </div>
        </form>
      </article>
    </li>
  );
}

function DecidedStrip({ d, filters }: { d: Decision; filters: Filters }) {
  const undo = (
    <form action={undoDecision}>
      <input type="hidden" name="decision_id" value={d.id} />
      <input type="hidden" name="issue_id" value={d.issue_id} />
      <BackFields filters={filters} />
      <button className={d.decision === "dismiss" ? "btn" : "btn btn-ghost"} type="submit">
        Undo
      </button>
    </form>
  );
  const what = (
    <>
      <span className="mono">{d.sku}</span> <Plat platform={d.platform} /> {d.issue_label}
    </>
  );

  if (d.decision === "dismiss") {
    return (
      <div className="toast" role="status">
        <Icon.Tick color="currentColor" size={16} />
        <span>
          <b>Dismissed</b> · {what} · logged {time(d.decided_at)}
        </span>
        {undo}
      </div>
    );
  }

  return (
    <section className="decided panel" role="status" aria-labelledby="decided-h">
      <div className="decided-top">
        <span className="decided-ic">
          <Icon.DecidedTick />
        </span>
        <span>
          <b id="decided-h">{d.decision === "approve_edited" ? "Approved with edits" : "Approved"}</b> · {what} · logged{" "}
          {time(d.decided_at)}
        </span>
        {undo}
      </div>
      <div className="decided-copy">
        <label className="lbl" htmlFor="approved-text">
          Approved text · send to {recipientLabel(d.recipient, d.brand, d.issue_code)}
        </label>
        <div className="copy-row">
          <SelectedText id="approved-text" value={d.final_text ?? ""} rows={Math.min(8, (d.final_text ?? "").split("\n").length + 1)} />
          <CopyButton targetId="approved-text" />
        </div>
        <span className="hint">Text is pre-selected. Ctrl+C works too.</span>
      </div>
    </section>
  );
}

export default async function QueuePage({ searchParams }: { searchParams: SearchParams }) {
  const sp = await searchParams;
  const one = (k: string) => (typeof sp[k] === "string" && sp[k] ? (sp[k] as string) : undefined);
  const filters: Filters = { brand: one("brand"), platform: one("platform"), severity: one("severity"), all: one("all") };
  const editId = one("edit");
  const decidedId = one("decided");

  const [p, brands, issues, decision] = await Promise.all([
    getPortfolio(),
    getBrands(),
    getIssues({ brand: filters.brand, platform: filters.platform, severity: filters.severity }),
    decidedId ? getDecision(decidedId) : Promise.resolve(null),
  ]);

  const brandName = filters.brand ? brands.find((b) => b.slug === filters.brand)?.name ?? filters.brand : null;
  const platformName = filters.platform ? (filters.platform.toLowerCase() === "amazon" ? "Amazon" : "Flipkart") : null;
  const filtered = Boolean(filters.brand || filters.platform || filters.severity);
  const awaiting = p.snapshot?.status === "uploaded";

  const editIndex = editId ? issues.findIndex((i) => String(i.id) === editId) : -1;
  const showAll = Boolean(filters.all) || editIndex >= TOP_N;
  const visible = showAll ? issues : issues.slice(0, TOP_N);
  const rest = issues.slice(TOP_N);
  const strip = decision && !decision.undone_at ? <DecidedStrip d={decision} filters={filters} /> : null;

  const scope = (
    <span className="scope">
      Showing <b>{brandName ?? "all brands"}</b> on <b>{platformName ?? "Amazon and Flipkart"}</b>
      {filters.severity ? (
        <>
          {" "}
          · <b>{filters.severity}</b> only
        </>
      ) : null}
      {filtered ? (
        <Link className="filters-clear" href="/queue">
          Clear filters
        </Link>
      ) : null}
    </span>
  );

  if (issues.length === 0) {
    const allClear = !filtered && !awaiting;
    return (
      <div className="app pg-queue pg-queue-empty">
        <Header active="queue" />
        <main className="main">
          <div className="page-head">
            <div>
              <h1>Issue queue</h1>
              <p>0 open</p>
            </div>
            {filtered ? scope : null}
          </div>
          {strip}
          <section className="clear panel" aria-labelledby="clear-h">
            <div className="badge">
              <Icon.ClearBadge />
            </div>
            {awaiting ? (
              <>
                <h2 id="clear-h">Audit not run yet</h2>
                <p>New data was uploaded. Run the audit from the overview to fill the queue.</p>
                <div className="next">
                  <Link className="btn btn-primary" href="/">
                    Go to overview
                  </Link>
                </div>
              </>
            ) : allClear ? (
              <>
                <h2 id="clear-h">No open issues — queue is clear</h2>
                <p>
                  Every flagged listing from the {p.snapshot?.audited_at ? day(p.snapshot.audited_at) : "latest"} audit has a
                  decision.
                </p>
                <div className="recap" aria-label="Decisions">
                  <div>
                    <b>{num(p.approved_count)}</b>
                    <span>approved</span>
                  </div>
                  <div>
                    <b>{num(p.dismissed_count)}</b>
                    <span>dismissed</span>
                  </div>
                  <div>
                    <b>{inr(p.approved_impact_inr)}</b>
                    <span>/day addressed</span>
                  </div>
                </div>
                <div className="next">
                  {brands[0] ? (
                    <Link className="btn btn-primary" href={`/brand/${brands[0].slug}`}>
                      Read this week&apos;s brand summaries
                    </Link>
                  ) : null}
                  <Link className="btn" href="/">
                    Back to overview
                  </Link>
                </div>
                <span className="hint">Upload fresh CSVs when brands send new files, then run the audit again.</span>
              </>
            ) : (
              <>
                <h2 id="clear-h">Nothing open here</h2>
                <p>
                  {brandName ?? "All brands"} on {platformName ?? "Amazon and Flipkart"}
                  {filters.severity ? ` (${filters.severity})` : ""} has no open issues.{" "}
                  {p.open_issue_count ? `${plural(p.open_issue_count, "issue")} are still open elsewhere.` : ""}
                </p>
                <div className="next">
                  <Link className="btn btn-primary" href="/queue">
                    Show all open issues
                  </Link>
                  <Link className="btn" href="/">
                    Back to overview
                  </Link>
                </div>
              </>
            )}
          </section>
        </main>
      </div>
    );
  }

  const restMax = rest.length ? Math.max(...rest.map((i) => i.impact_inr)) : 0;
  const restSum = rest.reduce((n, i) => n + i.impact_inr, 0);

  return (
    <div className="app pg-queue">
      <Header active="queue" />
      <main className="main">
        <div className="page-head">
          <div>
            <h1>Issue queue</h1>
            <p>
              {num(issues.length)} open · <span className="sortnote">critical first, then highest ₹ impact/day</span>
            </p>
          </div>
          {scope}
        </div>

        {strip}

        <ol className="qlist">
          {visible.map((issue, i) => (
            <IssueCard key={issue.id} issue={issue} rank={i + 1} editing={String(issue.id) === editId} filters={filters} />
          ))}
        </ol>

        {rest.length && !showAll ? (
          <div className="more panel">
            <span>
              Showing {visible.length} of {issues.length} · the other {rest.length} are {inr(restMax)}/day or less,{" "}
              {inr(restSum)}/day combined
            </span>
            <Link className="btn" href={queueHref(filters, { all: "1" })}>
              Show all {issues.length}
            </Link>
          </div>
        ) : null}
      </main>
    </div>
  );
}
