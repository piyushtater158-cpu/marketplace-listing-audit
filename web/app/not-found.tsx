import Link from "next/link";
import { Header } from "@/components/Header";

export default function NotFound() {
  return (
    <div className="app pg-overview">
      <Header active="" />
      <main className="main">
        <section className="panel nf">
          <h1>Not found</h1>
          <p>There is no SKU or brand with that name in the current upload. It may have been removed when new data replaced the old files.</p>
          <Link className="btn btn-primary" href="/">
            Back to overview
          </Link>
        </section>
      </main>
    </div>
  );
}
