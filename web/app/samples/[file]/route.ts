import { API_URL } from "@/lib/api";

const FILES = new Set(["listings.csv", "ads.csv", "reviews.csv"]);

/** The browser never talks to the API directly, so sample downloads are relayed here. */
export async function GET(_req: Request, { params }: { params: Promise<{ file: string }> }) {
  const { file } = await params;
  if (!FILES.has(file)) return new Response("Not found", { status: 404 });
  const res = await fetch(`${API_URL}/api/samples/${file}`, { cache: "no-store" });
  if (!res.ok) return new Response("Sample file unavailable", { status: 502 });
  return new Response(res.body, {
    headers: {
      "Content-Type": "text/csv; charset=utf-8",
      "Content-Disposition": `attachment; filename="${file}"`,
    },
  });
}
