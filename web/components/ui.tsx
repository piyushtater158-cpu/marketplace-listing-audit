import type { ReactNode } from "react";
import type { Severity } from "@/lib/api";
import { SEV_CLASS, SEV_LABEL } from "@/lib/format";

/** Severity glyph. Shape carries the meaning (octagon / triangle / diamond / ring);
 * `outline` is the zero-count variant used in the health grid. */
export function SevIcon({ sev, outline = false }: { sev: Severity; outline?: boolean }) {
  const common = { width: 12, height: 12, viewBox: "0 0 12 12", "aria-hidden": true } as const;
  if (sev === "critical")
    return outline ? (
      <svg {...common}><path d="M4 .6h4L11.4 4v4L8 11.4H4L.6 8V4z" fill="none" stroke="currentColor" strokeWidth="1.2" /></svg>
    ) : (
      <svg {...common}>
        <path d="M4 .6h4L11.4 4v4L8 11.4H4L.6 8V4z" fill="currentColor" />
        <path d="M6 3.1v3.4M6 8.6v.1" stroke="#fff" strokeWidth="1.6" strokeLinecap="round" />
      </svg>
    );
  if (sev === "high")
    return outline ? (
      <svg {...common}><path d="M6 .8l5.6 10H.4z" fill="none" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round" /></svg>
    ) : (
      <svg {...common}>
        <path d="M6 .8l5.6 10H.4z" fill="currentColor" stroke="currentColor" strokeWidth=".8" strokeLinejoin="round" />
        <path d="M6 4.3v2.9M6 9v.1" stroke="#fff" strokeWidth="1.5" strokeLinecap="round" />
      </svg>
    );
  if (sev === "medium")
    return outline ? (
      <svg {...common}><path d="M6 .6 11.4 6 6 11.4.6 6z" fill="none" stroke="currentColor" strokeWidth="1.2" /></svg>
    ) : (
      <svg {...common}>
        <path d="M6 .6 11.4 6 6 11.4.6 6z" fill="currentColor" />
        <path d="M3.8 6h4.4" stroke="#fff" strokeWidth="1.5" strokeLinecap="round" />
      </svg>
    );
  return outline ? (
    <svg {...common}><circle cx="6" cy="6" r="4.6" fill="none" stroke="currentColor" strokeWidth="1.2" /></svg>
  ) : (
    <svg {...common}>
      <circle cx="6" cy="6" r="4.6" fill="none" stroke="currentColor" strokeWidth="1.6" />
      <circle cx="6" cy="6" r="1.7" fill="currentColor" />
    </svg>
  );
}

export function SevBadge({ sev, label }: { sev: Severity; label?: string }) {
  return (
    <span className={`sev sev-${SEV_CLASS[sev]}`}>
      <SevIcon sev={sev} />
      {label ?? SEV_LABEL[sev]}
    </span>
  );
}

export function Plat({ platform, withName = false }: { platform: string; withName?: boolean }) {
  const amz = platform.toLowerCase() === "amazon";
  return (
    <>
      <span className={`plat ${amz ? "plat-amz" : "plat-fk"}`} title={withName ? undefined : platform}>
        {amz ? "AMZ" : "FK"}
      </span>
      {withName ? (amz ? "Amazon" : "Flipkart") : null}
    </>
  );
}

export function AiTag({ children }: { children: ReactNode }) {
  return (
    <span className="ai-tag">
      <svg width="11" height="11" viewBox="0 0 12 12" aria-hidden="true">
        <path d="M6 .8c.4 2.6 1.6 3.8 4.2 4.2v.1C7.6 5.5 6.4 6.7 6 9.3h-.1C5.5 6.7 4.3 5.5 1.7 5.1V5C4.3 4.6 5.5 3.4 5.9.8z" fill="currentColor" />
        <circle cx="10" cy="10" r="1.2" fill="currentColor" />
      </svg>
      {children}
    </span>
  );
}

const stroke = { fill: "none", stroke: "currentColor", strokeLinecap: "round", strokeLinejoin: "round" } as const;

export const Icon = {
  Logo: () => (
    <svg width="24" height="24" viewBox="0 0 24 24" aria-hidden="true">
      <rect x="1" y="1" width="22" height="22" rx="6" fill="#15181C" />
      <path d="M6.5 8.5h11M6.5 12h7.5M6.5 15.5h4" stroke="#FFFFFF" strokeWidth="1.8" strokeLinecap="round" />
      <circle cx="16.8" cy="15.5" r="1.9" fill="#E3A33B" />
    </svg>
  ),
  Upload: () => (
    <svg width="15" height="15" viewBox="0 0 16 16" {...stroke} strokeWidth="1.6" aria-hidden="true">
      <path d="M8 10.5V2.5M4.8 5.6 8 2.4l3.2 3.2" />
      <path d="M2.5 10.5v2a1 1 0 0 0 1 1h9a1 1 0 0 0 1-1v-2" />
    </svg>
  ),
  Info: () => (
    <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">
      <path d="M6 5.2v3.6M6 3.1v.1" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  ),
  Arrow: () => (
    <svg width="16" height="16" viewBox="0 0 16 16" {...stroke} strokeWidth="1.8" aria-hidden="true">
      <path d="M3 8h10M9 4l4 4-4 4" />
    </svg>
  ),
  Play: () => (
    <svg width="16" height="16" viewBox="0 0 16 16" {...stroke} strokeWidth="1.8" aria-hidden="true">
      <path d="M5 3.2v9.6L12.8 8z" />
    </svg>
  ),
  Tick: ({ color = "#1F6B45", size = 14 }: { color?: string; size?: number }) => (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke={color} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="m3.5 8.4 2.8 2.8 6.2-6.4" />
    </svg>
  ),
  DecidedTick: () => (
    <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="#FFFFFF" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="m3.5 8.4 2.8 2.8 6.2-6.4" />
    </svg>
  ),
  OkCircle: () => (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true">
      <circle cx="9" cy="9" r="8" fill="#1F6B45" />
      <path d="m5.4 9.2 2.4 2.4 4.8-5" stroke="#fff" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  Wait: () => (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="#4A5059" strokeWidth="1.6" strokeLinecap="round" aria-hidden="true">
      <circle cx="9" cy="9" r="7.2" strokeDasharray="2.6 2.4" />
      <path d="M9 5.5V9l2.4 1.6" />
    </svg>
  ),
  Dismiss: () => (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden="true">
      <path d="m4 4 8 8M12 4l-8 8" />
    </svg>
  ),
  Edit: () => (
    <svg width="14" height="14" viewBox="0 0 16 16" {...stroke} strokeWidth="1.6" aria-hidden="true">
      <path d="M10.5 2.5l3 3L6 13H3v-3z" />
      <path d="m9 4 3 3" />
    </svg>
  ),
  EditNote: () => (
    <svg width="13" height="13" viewBox="0 0 16 16" {...stroke} strokeWidth="1.6" aria-hidden="true">
      <path d="M10.5 2.5l3 3L6 13H3v-3z" />
    </svg>
  ),
  Clipboard: () => (
    <svg width="15" height="15" viewBox="0 0 16 16" {...stroke} strokeWidth="1.6" aria-hidden="true">
      <rect x="3" y="2.5" width="10" height="12" rx="1.5" />
      <path d="M6 1.5h4v2H6z" />
    </svg>
  ),
  ApproveCopy: () => (
    <svg width="15" height="15" viewBox="0 0 16 16" {...stroke} strokeWidth="1.6" aria-hidden="true">
      <rect x="3" y="2.5" width="10" height="12" rx="1.5" />
      <path d="M6 1.5h4v2H6z" />
      <path d="m5.8 9 1.6 1.6 3-3.2" />
    </svg>
  ),
  Missing: () => (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="#4A5059" strokeWidth="1.6" strokeLinecap="round" aria-hidden="true">
      <path d="M4 9h10" />
    </svg>
  ),
  ClearBadge: () => (
    <svg width="30" height="30" viewBox="0 0 18 18" fill="none" aria-hidden="true">
      <path d="m4.6 9.3 2.9 2.9 5.9-6.2" stroke="#FFFFFF" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
};
