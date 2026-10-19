"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { post, type Decision } from "@/lib/api";

const FILTER_KEYS = ["brand", "platform", "severity", "all"] as const;

/** Queue filters travel with each decision form as back_* fields so the redirect lands
 * on the same filtered view. */
function backQuery(formData: FormData, extra: Record<string, string> = {}): string {
  const qs = new URLSearchParams();
  for (const key of FILTER_KEYS) {
    const value = formData.get(`back_${key}`);
    if (typeof value === "string" && value) qs.set(key, value);
  }
  for (const [k, v] of Object.entries(extra)) qs.set(k, v);
  const s = qs.toString();
  return s ? `?${s}` : "";
}

export type UploadState = { error: string | null };

export async function uploadData(_prev: UploadState, formData: FormData): Promise<UploadState> {
  const body = new FormData();
  for (const name of ["listings", "ads", "reviews"]) {
    const file = formData.get(name);
    if (!(file instanceof File) || file.size === 0) {
      return { error: `Choose a ${name}.csv file. All three files are required.` };
    }
    body.append(name, file, file.name);
  }
  const res = await post("/api/upload", body);
  if (!res.ok) return { error: res.error };
  revalidatePath("/", "layout");
  redirect("/");
}

export async function runAudit(): Promise<void> {
  const res = await post("/api/audit/run");
  if (!res.ok) throw new Error(res.error ?? "Audit failed");
  revalidatePath("/", "layout");
  redirect("/");
}

export async function decide(formData: FormData): Promise<void> {
  const issueId = Number(formData.get("issue"));
  const decision = String(formData.get("decision"));
  const fixText = formData.get("fix_text");
  const res = await post<Decision>("/api/decisions", {
    issue_id: issueId,
    decision,
    fix_text: decision === "approve_edited" && typeof fixText === "string" ? fixText : null,
  });
  revalidatePath("/", "layout");
  if (res.status === 409) redirect(`/queue${backQuery(formData)}`);
  if (!res.ok || !res.data) throw new Error(res.error ?? "Could not save the decision");
  redirect(`/queue${backQuery(formData, { decided: String(res.data.id) })}`);
}

export async function undoDecision(formData: FormData): Promise<void> {
  const decisionId = String(formData.get("decision_id"));
  const issueId = String(formData.get("issue_id"));
  const res = await post<Decision>(`/api/decisions/${encodeURIComponent(decisionId)}/undo`);
  if (!res.ok) throw new Error(res.error ?? "Could not undo the decision");
  revalidatePath("/", "layout");
  redirect(`/queue${backQuery(formData, { all: "1" })}#iss-${issueId}`);
}

export async function setAi(formData: FormData): Promise<void> {
  const res = await post("/api/settings/ai", { enabled: formData.get("ai") !== null });
  if (!res.ok) throw new Error(res.error ?? "Could not change the AI setting");
  revalidatePath("/", "layout");
}
