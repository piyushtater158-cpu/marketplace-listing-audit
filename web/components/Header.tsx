import Link from "next/link";
import { getBrands, getPortfolio } from "@/lib/api";
import { day, num, time } from "@/lib/format";
import { AiToggle, UploadPanel } from "./client";
import { Icon } from "./ui";

/** Global chrome on every screen. `active` is "overview", "queue" or a brand slug. */
export async function Header({ active }: { active: string }) {
  const [p, brands] = await Promise.all([getPortfolio(), getBrands()]);
  const snap = p.snapshot;
  const awaiting = snap?.status === "uploaded";
  const current = (key: string) => (active === key ? { "aria-current": "page" as const } : {});

  let stamp = "No data uploaded";
  if (snap?.status === "audited" && snap.audited_at) {
    stamp = `Audited ${day(snap.audited_at)}, ${time(snap.audited_at)} · ${num(p.listing_count)} listings`;
  } else if (awaiting) {
    stamp = `Uploaded ${time(snap.uploaded_at)} · not audited`;
  }

  return (
    <header className="hdr">
      <Link className="logo" href="/">
        <Icon.Logo />
        <b>Listing Audit</b>
        <span>Intent Farm</span>
      </Link>
      <nav className="nav" aria-label="Main">
        <Link href="/" {...current("overview")}>
          Overview
        </Link>
        <Link href="/queue" {...current("queue")}>
          Queue <span className="count">{awaiting ? "—" : num(p.open_issue_count)}</span>
        </Link>
        <span className="sep" aria-hidden="true" />
        {brands.map((b) => (
          <Link key={b.slug} href={`/brand/${b.slug}`} {...current(b.slug)}>
            {b.name}
          </Link>
        ))}
      </nav>
      <div className="hdr-right">
        <span className={`stamp${awaiting ? " warn" : ""}`}>{stamp}</span>
        <AiToggle enabled={p.ai_enabled} available={p.ai_available} />
        <UploadPanel />
      </div>
    </header>
  );
}
