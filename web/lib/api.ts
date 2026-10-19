import { cache } from "react";
import type { components } from "@/types/api";

type S = components["schemas"];
export type Portfolio = S["PortfolioOut"];
export type PortfolioCell = S["PortfolioCell"];
export type Snapshot = S["SnapshotOut"];
export type Issue = S["IssueOut"];
export type Fix = S["FixOut"];
export type Decision = S["DecisionOut"];
export type SkuDetail = S["SkuDetailOut"];
export type PlatformDetail = S["PlatformDetailOut"];
export type SnapshotRow = S["SnapshotRow"];
export type Review = S["ReviewOut"];
export type BrandReport = S["BrandReportOut"];
export type Severity = Issue["severity"];
export type Brand = { name: string; slug: string; category: string };

export const API_URL = process.env.API_URL ?? "http://127.0.0.1:8000";

async function get<T>(path: string): Promise<T | null> {
  const res = await fetch(`${API_URL}${path}`, { cache: "no-store" });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`API ${path} failed: ${res.status} ${await res.text()}`);
  return (await res.json()) as T;
}

async function getOrThrow<T>(path: string): Promise<T> {
  const data = await get<T>(path);
  if (data === null) throw new Error(`API ${path} returned 404`);
  return data;
}

// React cache() dedupes these within one render, so the header and the page can both
// ask for the portfolio without a second request.
export const getPortfolio = cache(() => getOrThrow<Portfolio>("/api/portfolio"));
export const getBrands = cache(() => getOrThrow<Brand[]>("/api/brands"));

export type IssueFilters = { brand?: string; platform?: string; severity?: string };

export function getIssues(filters: IssueFilters = {}): Promise<Issue[]> {
  const qs = new URLSearchParams(
    Object.entries(filters).filter((e): e is [string, string] => Boolean(e[1])),
  ).toString();
  return getOrThrow<Issue[]>(`/api/issues${qs ? `?${qs}` : ""}`);
}

export const getDecision = (id: string) => get<Decision>(`/api/decisions/${encodeURIComponent(id)}`);
export const getSku = (sku: string) => get<SkuDetail>(`/api/sku/${encodeURIComponent(sku)}`);
export const getBrandReport = (brand: string, week?: string) =>
  get<BrandReport>(`/api/brand/${encodeURIComponent(brand)}/report${week ? `?week=${encodeURIComponent(week)}` : ""}`);

export async function post<T>(path: string, body?: unknown): Promise<{ ok: boolean; status: number; data: T | null; error: string | null }> {
  const init: RequestInit = { method: "POST", cache: "no-store" };
  if (body instanceof FormData) init.body = body;
  else if (body !== undefined) {
    init.body = JSON.stringify(body);
    init.headers = { "Content-Type": "application/json" };
  }
  const res = await fetch(`${API_URL}${path}`, init);
  const payload = await res.json().catch(() => null);
  if (res.ok) return { ok: true, status: res.status, data: payload as T, error: null };
  const detail = payload?.detail;
  return {
    ok: false,
    status: res.status,
    data: null,
    error: typeof detail === "string" ? detail : `Request failed (${res.status})`,
  };
}
