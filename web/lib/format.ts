import type { Severity } from "./api";

const TZ = "Asia/Kolkata";

/** Indian digit grouping: 1240 -> "₹1,240", 124000 -> "₹1,24,000". */
export function inr(value: number): string {
  return `${value < 0 ? "-" : ""}₹${Math.round(Math.abs(value)).toLocaleString("en-IN")}`;
}

export function num(value: number): string {
  return value.toLocaleString("en-IN");
}

function toDate(iso: string): Date {
  return new Date(/^\d{4}-\d{2}-\d{2}$/.test(iso) ? `${iso}T00:00:00+05:30` : iso);
}

/** "19 Oct" */
export function day(iso: string): string {
  return new Intl.DateTimeFormat("en-GB", { timeZone: TZ, day: "numeric", month: "short" }).format(toDate(iso));
}

/** "12:24" */
export function time(iso: string): string {
  return new Intl.DateTimeFormat("en-GB", { timeZone: TZ, hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(
    toDate(iso),
  );
}

/** Whole days between iso and now, in IST calendar days. */
export function daysSince(iso: string): number {
  const fmt = new Intl.DateTimeFormat("en-CA", { timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit" });
  const a = Date.parse(fmt.format(toDate(iso)));
  const b = Date.parse(fmt.format(new Date()));
  return Math.max(0, Math.round((b - a) / 86_400_000));
}

export function openFor(iso: string): string {
  const d = daysSince(iso);
  return d === 0 ? "Opened today" : `Open ${d} day${d === 1 ? "" : "s"}`;
}

/** "19–25 Oct 2026" from a Monday and Sunday. */
export function weekRange(start: string, end: string): string {
  const s = toDate(start);
  const e = toDate(end);
  const sameMonth = s.getUTCMonth() === e.getUTCMonth();
  const y = new Intl.DateTimeFormat("en-GB", { timeZone: TZ, year: "numeric" }).format(e);
  const dS = new Intl.DateTimeFormat("en-GB", { timeZone: TZ, day: "numeric", ...(sameMonth ? {} : { month: "short" }) }).format(s);
  return `${dS}–${day(end)} ${y}`;
}

export function plural(n: number, word: string, many = `${word}s`): string {
  return `${num(n)} ${n === 1 ? word : many}`;
}

const CATEGORY_LABELS: Record<string, string> = {
  skincare: "Skincare",
  snacks: "Snacks",
  home_appliances: "Home appliances",
};
export const categoryLabel = (c: string) => CATEGORY_LABELS[c] ?? c.replace(/_/g, " ").replace(/^\w/, (m) => m.toUpperCase());

export const SEVERITIES: Severity[] = ["critical", "high", "medium", "low"];
export const SEV_CLASS: Record<Severity, string> = { critical: "crit", high: "high", medium: "med", low: "low" };
export const SEV_LABEL: Record<Severity, string> = { critical: "Critical", high: "High", medium: "Medium", low: "Low" };

export const capitalize = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

/** "send to PPC team" / "to GlowVeda" — who an approved fix goes to. */
export function recipientLabel(recipient: "brand" | "internal", brand: string, issueCode: string): string {
  if (recipient === "brand") return brand;
  if (issueCode === "oos_ads_live" || issueCode === "ad_waste") return "PPC team";
  if (issueCode === "weak_content") return "content team";
  return "marketplace ops";
}
