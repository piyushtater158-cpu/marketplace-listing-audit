"use client";

import { useActionState, useEffect, useRef, useState } from "react";
import { useFormStatus } from "react-dom";
import { resetToSample, setAi, uploadData, type UploadState } from "@/app/actions";
import { Icon } from "./ui";

export function CopyButton({
  targetId,
  label = "Copy",
  className = "btn btn-primary",
}: {
  targetId: string;
  label?: string;
  className?: string;
}) {
  const [copied, setCopied] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => {
    if (timer.current) clearTimeout(timer.current);
  }, []);

  async function copy() {
    const el = document.getElementById(targetId);
    if (!el) return;
    const text = el instanceof HTMLTextAreaElement || el instanceof HTMLInputElement ? el.value : el.textContent ?? "";
    await navigator.clipboard.writeText(text);
    setCopied(true);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => setCopied(false), 2000);
  }

  return (
    <button className={className} type="button" data-copy-target={targetId} onClick={copy}>
      <Icon.Clipboard />
      <span aria-live="polite">{copied ? "Copied" : label}</span>
    </button>
  );
}

/** Read-only text that arrives selected, so Ctrl/Cmd+C works even before Copy is pressed. */
export function SelectedText({ id, value, rows = 2 }: { id: string; value: string; rows?: number }) {
  const ref = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    ref.current?.focus({ preventScroll: true });
    ref.current?.select();
  }, []);
  return <textarea ref={ref} id={id} rows={rows} readOnly value={value} />;
}

function AiState({ enabled }: { enabled: boolean }) {
  const { pending } = useFormStatus();
  if (pending) return <span className="state">…</span>;
  return <span className={`state${enabled ? "" : " off"}`}>{enabled ? "ON" : "OFF"}</span>;
}

export function AiToggle({ enabled, available }: { enabled: boolean; available: boolean }) {
  if (!available) {
    return (
      <span className="switch no-key" title="Set OPENROUTER_API_KEY on the API to turn on AI drafts">
        <input className="sw" type="checkbox" checked={false} disabled readOnly aria-label="AI drafts unavailable" />{" "}
        AI drafts <span className="state off">NO KEY</span>
      </span>
    );
  }
  return (
    <form className="ai-form" action={setAi}>
      <label className="switch">
        <input
          key={String(enabled)}
          className="sw"
          type="checkbox"
          name="ai"
          defaultChecked={enabled}
          onChange={(e) => e.currentTarget.form?.requestSubmit()}
        />{" "}
        AI drafts <AiState enabled={enabled} />
      </label>
      <noscript>
        <button className="btn" type="submit">
          Save
        </button>
      </noscript>
    </form>
  );
}

const UPLOAD_FIELDS = [
  { name: "listings", label: "Listings", hint: "One row per SKU per platform, per snapshot date" },
  { name: "ads", label: "Ads", hint: "Daily spend, clicks, orders and sales by SKU" },
  { name: "reviews", label: "Reviews", hint: "Stars, text, date, platform" },
] as const;

function UploadSubmit({ files }: { files: Record<string, string> }) {
  const { pending } = useFormStatus();
  if (!pending) {
    return (
      <button className="btn btn-primary" type="submit">
        Upload files
      </button>
    );
  }
  return (
    <>
      <div className="files-st">
        {UPLOAD_FIELDS.map((f) => (
          <span key={f.name}>
            <span>{files[f.name] ?? `${f.name}.csv`}</span>
            <span>uploading…</span>
          </span>
        ))}
      </div>
      <div className="prog" role="progressbar" aria-label="Upload progress">
        <i />
      </div>
      <button className="btn btn-primary" type="submit" disabled>
        Uploading 3 files…
      </button>
    </>
  );
}

export function UploadPanel() {
  const [state, action] = useActionState<UploadState, FormData>(uploadData, { error: null });
  const [files, setFiles] = useState<Record<string, string>>({});

  return (
    <details className="upl" open={state.error ? true : undefined}>
      <summary className="btn">
        <Icon.Upload />
        Upload data
      </summary>
      <div className="upl-pop panel pop">
        <form className="upl-form" action={action}>
          <div className="upl-head">
            <b>Upload audit data</b>
            <span>Three CSVs. Replaces the current data; run the audit once the files are in.</span>
          </div>
          {UPLOAD_FIELDS.map((f) => (
            <div className="field" key={f.name}>
              <label htmlFor={`f-${f.name}`}>{f.label}</label>
              <input
                id={`f-${f.name}`}
                type="file"
                name={f.name}
                accept=".csv,text/csv"
                required
                onChange={(e) => {
                  const name = e.currentTarget.files?.[0]?.name;
                  setFiles((prev) => ({ ...prev, [f.name]: name ?? "" }));
                }}
              />
              <span className="hint">{f.hint}</span>
            </div>
          ))}
          {state.error ? (
            <span className="hint err" role="alert">
              {state.error}
            </span>
          ) : null}
          <UploadSubmit files={files} />
        </form>
        <div className="upl-samples">
          <span>
            No files to hand? Download the samples:{" "}
            {UPLOAD_FIELDS.map((f, i) => (
              <span key={f.name}>
                {i ? " · " : ""}
                <a href={`/samples/${f.name}.csv`} download>
                  {f.name}.csv
                </a>
              </span>
            ))}
          </span>
          <form action={resetToSample}>
            <ResetSubmit />
          </form>
        </div>
      </div>
    </details>
  );
}

function ResetSubmit() {
  const { pending } = useFormStatus();
  return (
    <button className="btn btn-ghost btn-sm" type="submit" disabled={pending}>
      {pending ? "Resetting…" : "Reset to sample data"}
    </button>
  );
}
