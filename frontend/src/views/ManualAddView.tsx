// Manual-add view — form for inserting a paper found outside arXiv.
// The submission runs the keyword classifier inline (see /api/items/manual),
// so the item appears in the queue immediately on success.

import { useId, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  ApiError,
  api,
  type ManualDraftResponse,
  type ManualItemPayload,
  type ManualItemResponse,
  type ManualItemType,
  type Ring,
} from "../lib/api";
import { Button } from "../ui/Button";
import { Chrome } from "../ui/Chrome";
import { KeywordList } from "../ui/KeywordList";
import { OllamaChatPanel } from "../ui/OllamaChatPanel";
import { RingLabel } from "../ui/RingLabel";
import { TextField } from "../ui/TextField";

const ITEM_TYPES: { value: ManualItemType; label: string }[] = [
  { value: "paper", label: "Paper" },
  { value: "blog_post", label: "Blog post" },
  { value: "vendor_news", label: "Vendor news" },
  { value: "library_release", label: "Library release" },
  { value: "standard_update", label: "Standard update" },
  { value: "dataset", label: "Dataset" },
  { value: "benchmark", label: "Benchmark" },
  { value: "conference_item", label: "Conference item" },
  { value: "github_repo", label: "GitHub repo" },
  { value: "atlas_candidate", label: "Atlas candidate" },
];

function isoToday(): string {
  return new Date().toISOString().slice(0, 10);
}

interface FormState {
  url: string;
  title: string;
  abstract: string;
  publishedDate: string; // YYYY-MM-DD from <input type="date">
  authors: string[];
  pdfUrl: string;
  doi: string;
  externalId: string;
  itemType: ManualItemType;
}

function emptyForm(): FormState {
  return {
    url: "",
    title: "",
    abstract: "",
    publishedDate: isoToday(),
    authors: [],
    pdfUrl: "",
    doi: "",
    externalId: "",
    itemType: "paper",
  };
}

interface SuccessState {
  response: ManualItemResponse;
  date: string;
}

function nullIfBlank(value: string): string | null {
  const trimmed = value.trim();
  return trimmed === "" ? null : trimmed;
}

function buildPayload(form: FormState): ManualItemPayload {
  return {
    title: form.title.trim(),
    url: form.url.trim(),
    abstract: form.abstract.trim(),
    published_at: `${form.publishedDate}T00:00:00Z`,
    authors: form.authors.map((a) => a.trim()).filter(Boolean),
    pdf_url: nullIfBlank(form.pdfUrl),
    doi: nullIfBlank(form.doi),
    external_id: nullIfBlank(form.externalId),
    item_type: form.itemType,
  };
}

interface FieldErrors {
  url?: string;
  title?: string;
  publishedDate?: string;
}

function validateLocal(form: FormState): FieldErrors {
  const errors: FieldErrors = {};
  if (form.url.trim() === "") errors.url = "URL is required";
  if (form.title.trim() === "") errors.title = "title is required";
  else if (form.title.trim().length > 500)
    errors.title = "title must be 500 chars or less";
  if (form.publishedDate === "") errors.publishedDate = "published date is required";
  return errors;
}

function mapServerErrors(err: ApiError): {
  general: string;
  fields: FieldErrors;
} {
  const fields: FieldErrors = {};
  if (err.validationErrors) {
    for (const item of err.validationErrors) {
      // FastAPI loc looks like ["body", "title"]. Drop the first part.
      const path = item.loc.slice(1);
      const key = path.length > 0 ? String(path[0]) : "";
      if (key === "title" && !fields.title) fields.title = item.msg;
      else if (key === "url" && !fields.url) fields.url = item.msg;
      else if (key === "published_at" && !fields.publishedDate)
        fields.publishedDate = item.msg;
    }
  }
  return { general: err.message, fields };
}

function chipStyle(): React.CSSProperties {
  return {
    display: "inline-flex",
    alignItems: "center",
    fontFamily: "var(--font-mono)",
    fontSize: "var(--text-small)",
    color: "var(--color-ink)",
    border: "1px solid var(--color-rule)",
    borderRadius: "var(--radius-sm)",
    padding: "0.125rem 0.5rem",
    background: "transparent",
  };
}

function captionStyle(): React.CSSProperties {
  return {
    fontFamily: "var(--font-mono)",
    fontSize: "var(--text-micro)",
    color: "var(--color-muted)",
    letterSpacing: "var(--tracking-caps)",
    textTransform: "uppercase",
  };
}

function ResultCard({
  success,
  onAddAnother,
}: {
  success: SuccessState;
  onAddAnother: () => void;
}) {
  const { response, date } = success;
  const { item_id, created, tracks, recommended_ring, final_score } = response;
  const isToday = date === isoToday();
  const viewHref = isToday
    ? `#/queue?item=${item_id}`
    : `#/score-debug?date=${date}&item=${item_id}`;

  return (
    <section
      role="status"
      aria-live="polite"
      style={{
        border: "1px solid var(--color-accent)",
        borderRadius: "var(--radius-sm)",
        padding: "1rem 1.25rem",
        display: "flex",
        flexDirection: "column",
        gap: "0.75rem",
        background: "transparent",
      }}
    >
      <div style={{ display: "flex", alignItems: "baseline", gap: "0.5rem" }}>
        <span
          aria-hidden="true"
          style={{
            color: "var(--color-accent)",
            fontFamily: "var(--font-mono)",
            fontSize: "var(--text-body)",
          }}
        >
          {created ? "✓" : "↻"}
        </span>
        <h3
          style={{
            margin: 0,
            fontFamily: "var(--font-display)",
            fontSize: "1.25rem",
            fontWeight: 400,
            letterSpacing: "var(--tracking-tight)",
          }}
        >
          {created
            ? `Added as item #${item_id}`
            : `Updated existing item #${item_id}`}
        </h3>
      </div>

      <dl
        style={{
          display: "grid",
          gridTemplateColumns: "max-content 1fr",
          rowGap: "0.5rem",
          columnGap: "1rem",
          margin: 0,
        }}
      >
        <dt style={captionStyle()}>Ring</dt>
        <dd style={{ margin: 0 }}>
          <RingLabel ring={recommended_ring} />
        </dd>

        <dt style={captionStyle()}>Score</dt>
        <dd
          style={{
            margin: 0,
            fontFamily: "var(--font-mono)",
            fontSize: "var(--text-small)",
          }}
        >
          {final_score.toFixed(1)}
        </dd>

        <dt style={captionStyle()}>Tracks</dt>
        <dd style={{ margin: 0 }}>
          {tracks.length === 0 ? (
            <span
              style={{
                fontFamily: "var(--font-display)",
                fontStyle: "italic",
                color: "var(--color-muted)",
                fontSize: "var(--text-small)",
              }}
            >
              none matched
            </span>
          ) : (
            <div style={{ display: "flex", flexWrap: "wrap", gap: "0.375rem" }}>
              {tracks.map((track) => (
                <span key={track} style={chipStyle()}>
                  {track}
                </span>
              ))}
            </div>
          )}
        </dd>
      </dl>

      <div style={{ display: "flex", gap: "1.25rem", alignItems: "baseline" }}>
        <a
          href={viewHref}
          style={{
            fontFamily: "var(--font-sans)",
            fontSize: "var(--text-small)",
            color: "var(--color-ink)",
            textDecoration: "underline",
            textUnderlineOffset: "2px",
          }}
        >
          View in queue
        </a>
        <Button variant="ghost" onClick={onAddAnother}>
          Add another
        </Button>
      </div>
    </section>
  );
}

interface DraftFormState {
  url: string;
  title: string;
  abstract: string;
  hint: string;
}

function emptyDraftForm(): DraftFormState {
  return { url: "", title: "", abstract: "", hint: "" };
}

function DraftPanel({
  onApply,
}: {
  onApply: (draft: ManualDraftResponse) => void;
}) {
  const urlId = useId();
  const titleId = useId();
  const abstractId = useId();
  const hintId = useId();

  const [form, setForm] = useState<DraftFormState>(emptyDraftForm);
  const [drafting, setDrafting] = useState(false);
  const [draft, setDraft] = useState<ManualDraftResponse | null>(null);
  const [draftError, setDraftError] = useState<string | null>(null);
  const [draftStatus, setDraftStatus] = useState<number | null>(null);

  function update<K extends keyof DraftFormState>(
    key: K,
    value: DraftFormState[K],
  ) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  function reset() {
    setForm(emptyDraftForm());
    setDraft(null);
    setDraftError(null);
    setDraftStatus(null);
  }

  async function handleGenerate(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setDraftError(null);
    setDraftStatus(null);

    const url = form.url.trim();
    const title = form.title.trim();
    const abstract = form.abstract.trim();
    const hint = form.hint.trim();

    if (!url && !title && !abstract && !hint) {
      setDraftError("Provide at least one of URL, title, abstract, or hint.");
      return;
    }

    setDrafting(true);
    try {
      const response = await api.postManualDraft({
        url: url || undefined,
        title: title || undefined,
        abstract: abstract || undefined,
        hint: hint || undefined,
      });
      setDraft(response);
    } catch (err) {
      if (err instanceof ApiError) {
        setDraftError(err.message);
        setDraftStatus(err.status);
      } else if (err instanceof Error) {
        setDraftError(err.message);
      } else {
        setDraftError("Draft failed");
      }
    } finally {
      setDrafting(false);
    }
  }

  const showOllamaHint = draftStatus === 502 || draftStatus === 503;

  return (
    <details
      style={{
        border: "1px solid var(--color-rule)",
        borderRadius: "var(--radius-sm)",
        padding: "0.75rem 1rem",
      }}
    >
      <summary
        style={{
          ...captionStyle(),
          cursor: "pointer",
          userSelect: "none",
        }}
      >
        Draft with Ollama
      </summary>
      <div
        style={{
          marginTop: "1rem",
          display: "flex",
          flexDirection: "column",
          gap: "1rem",
        }}
      >
        <p
          style={{
            margin: 0,
            fontFamily: "var(--font-sans)",
            fontSize: "var(--text-small)",
            color: "var(--color-muted)",
            lineHeight: 1.5,
          }}
        >
          Give the local model whatever you have — URL, title, a rough
          abstract, or a free-text hint — and it returns suggested tracks,
          ring, reason, and an action. Review the result before applying it.
        </p>

        <form
          onSubmit={handleGenerate}
          noValidate
          style={{
            display: "flex",
            flexDirection: "column",
            gap: "1rem",
          }}
        >
          <TextField
            id={urlId}
            label="URL (optional)"
            value={form.url}
            onChange={(v) => update("url", v)}
            placeholder="https://…"
            disabled={drafting}
          />
          <TextField
            id={titleId}
            label="Title (optional)"
            value={form.title}
            onChange={(v) => update("title", v)}
            disabled={drafting}
          />
          <TextField
            id={abstractId}
            label="Abstract (optional)"
            value={form.abstract}
            onChange={(v) => update("abstract", v)}
            multiline
            placeholder="Paste what you have so far."
            disabled={drafting}
          />
          <TextField
            id={hintId}
            label="Hint (optional)"
            value={form.hint}
            onChange={(v) => update("hint", v)}
            multiline
            placeholder="Short notes — what caught your eye?"
            disabled={drafting}
          />
          {draftError && (
            <div
              role="alert"
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: "var(--text-micro)",
                color: "var(--color-accent)",
                wordBreak: "break-word",
              }}
            >
              {draftError}
              {showOllamaHint && (
                <>
                  {" "}
                  <a
                    href="#/settings"
                    style={{
                      color: "var(--color-accent)",
                      textDecoration: "underline",
                      textUnderlineOffset: "2px",
                    }}
                  >
                    Check Ollama config in Settings.
                  </a>
                </>
              )}
            </div>
          )}
          <div style={{ display: "flex", gap: "1rem", alignItems: "baseline" }}>
            <Button type="submit" variant="primary" size="sm" disabled={drafting}>
              {drafting ? "Generating…" : "Generate draft"}
            </Button>
            {(draft || draftError) && (
              <Button
                type="button"
                variant="ghost"
                onClick={reset}
                disabled={drafting}
              >
                Clear
              </Button>
            )}
          </div>
        </form>

        {draft && (
          <DraftPreview draft={draft} onApply={() => onApply(draft)} />
        )}
      </div>
    </details>
  );
}

function DraftPreview({
  draft,
  onApply,
}: {
  draft: ManualDraftResponse;
  onApply: () => void;
}) {
  const latencySeconds = (draft.latency_ms / 1000).toFixed(1);
  return (
    <section
      aria-label="Drafted suggestion"
      style={{
        border: "1px solid var(--color-rule)",
        borderRadius: "var(--radius-sm)",
        padding: "1rem 1.25rem",
        display: "flex",
        flexDirection: "column",
        gap: "0.75rem",
      }}
    >
      <header
        style={{
          display: "flex",
          alignItems: "baseline",
          justifyContent: "space-between",
          gap: "1rem",
        }}
      >
        <span style={captionStyle()}>Suggested</span>
        <span
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: "var(--text-micro)",
            color: "var(--color-muted)",
          }}
        >
          {draft.model} · {latencySeconds} s
        </span>
      </header>

      {draft.title && (
        <h3
          style={{
            margin: 0,
            fontFamily: "var(--font-display)",
            fontSize: "1.25rem",
            fontWeight: 400,
            letterSpacing: "var(--tracking-tight)",
          }}
        >
          {draft.title}
        </h3>
      )}

      {draft.abstract && (
        <p
          style={{
            margin: 0,
            fontFamily: "var(--font-display)",
            fontSize: "var(--text-body)",
            lineHeight: 1.5,
          }}
        >
          {draft.abstract}
        </p>
      )}

      <dl
        style={{
          display: "grid",
          gridTemplateColumns: "max-content 1fr",
          rowGap: "0.5rem",
          columnGap: "1rem",
          margin: 0,
        }}
      >
        <dt style={captionStyle()}>Ring</dt>
        <dd style={{ margin: 0 }}>
          <RingLabel ring={(draft.suggested_ring as Ring) || "Watch"} />
        </dd>

        <dt style={captionStyle()}>Tracks</dt>
        <dd style={{ margin: 0 }}>
          {draft.suggested_tracks.length === 0 ? (
            <span
              style={{
                fontFamily: "var(--font-display)",
                fontStyle: "italic",
                color: "var(--color-muted)",
                fontSize: "var(--text-small)",
              }}
            >
              none suggested
            </span>
          ) : (
            <div style={{ display: "flex", flexWrap: "wrap", gap: "0.375rem" }}>
              {draft.suggested_tracks.map((t) => (
                <span key={t} style={chipStyle()}>
                  {t}
                </span>
              ))}
            </div>
          )}
        </dd>

        {draft.reason && (
          <>
            <dt style={captionStyle()}>Reason</dt>
            <dd
              style={{
                margin: 0,
                fontFamily: "var(--font-display)",
                fontStyle: "italic",
                fontSize: "var(--text-small)",
              }}
            >
              {draft.reason}
            </dd>
          </>
        )}

        {draft.action && (
          <>
            <dt style={captionStyle()}>Action</dt>
            <dd
              style={{
                margin: 0,
                fontFamily: "var(--font-sans)",
                fontSize: "var(--text-small)",
              }}
            >
              {draft.action}
            </dd>
          </>
        )}

        {draft.uncertain && (
          <>
            <dt style={captionStyle()}>Confidence</dt>
            <dd
              style={{
                margin: 0,
                fontFamily: "var(--font-mono)",
                fontSize: "var(--text-micro)",
                color: "var(--color-muted)",
              }}
            >
              uncertain
            </dd>
          </>
        )}
      </dl>

      <div style={{ display: "flex", gap: "1rem", alignItems: "baseline" }}>
        <Button type="button" variant="primary" size="sm" onClick={onApply}>
          Apply to form
        </Button>
      </div>

      <details>
        <summary
          style={{
            ...captionStyle(),
            cursor: "pointer",
            userSelect: "none",
          }}
        >
          View raw model output
        </summary>
        <pre
          style={{
            marginTop: "0.5rem",
            padding: "0.75rem",
            fontFamily: "var(--font-mono)",
            fontSize: "var(--text-micro)",
            color: "var(--color-muted)",
            border: "1px solid var(--color-rule)",
            borderRadius: "var(--radius-sm)",
            background: "transparent",
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
            overflowX: "auto",
          }}
        >
          {draft.raw_response}
        </pre>
      </details>
    </section>
  );
}

function buildChatSystemPrompt(tracks: string[] | undefined): string {
  const trackList =
    tracks && tracks.length > 0 ? tracks.join(", ") : "(no tracks configured)";
  return (
    "You are an assistant helping curate a private computer-vision technology " +
    "radar. The radar uses rings Use / Prototype / Evaluate / Watch / Ignore. " +
    `Configured tracks: ${trackList}. Prefer practical, industrially relevant ` +
    "work (calibration, 3D geometry/sensors, robot guidance, industrial " +
    "inspection, edge AI, sensors/standards). Be skeptical: famous authors " +
    "or large claims are not enough. When the user asks about a paper, give " +
    "a short verdict + reason + a concrete next action."
  );
}

export function ManualAddView() {
  const urlId = useId();
  const titleId = useId();
  const abstractId = useId();
  const publishedId = useId();
  const pdfId = useId();
  const doiId = useId();
  const externalId = useId();
  const itemTypeId = useId();

  const [form, setForm] = useState<FormState>(emptyForm);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [generalError, setGeneralError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState<SuccessState | null>(null);

  // Topics power the chat panel's system prompt. We hit the existing
  // /api/config/topics endpoint and degrade silently if it fails — the chat
  // works without a track-aware prompt.
  const topicsQuery = useQuery({
    queryKey: ["topics-config"],
    queryFn: () => api.getTopicsConfig(),
    staleTime: 5 * 60_000,
  });
  const trackNames = topicsQuery.data?.tracks.map((t) => t.name);

  function update<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  function applyDraft(draft: ManualDraftResponse) {
    setForm((prev) => ({
      ...prev,
      title: draft.title || prev.title,
      abstract: draft.abstract || prev.abstract,
    }));
    setSuccess(null);
    setGeneralError(null);
    setErrors({});
  }

  function resetForm() {
    setForm(emptyForm());
    setErrors({});
    setGeneralError(null);
    setSuccess(null);
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setGeneralError(null);

    const localErrors = validateLocal(form);
    if (Object.keys(localErrors).length > 0) {
      setErrors(localErrors);
      return;
    }
    setErrors({});

    setSubmitting(true);
    try {
      const payload = buildPayload(form);
      const response = await api.postManualItem(payload);
      setSuccess({ response, date: form.publishedDate });
    } catch (err) {
      if (err instanceof ApiError) {
        const mapped = mapServerErrors(err);
        setErrors(mapped.fields);
        setGeneralError(mapped.general);
      } else if (err instanceof Error) {
        setGeneralError(err.message);
      } else {
        setGeneralError("Submit failed");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      style={{
        minHeight: "100dvh",
        display: "flex",
        flexDirection: "column",
        maxWidth: "80rem",
        margin: "0 auto",
      }}
    >
      <Chrome />
      <main
        style={{
          padding: "1.5rem",
          display: "flex",
          flexDirection: "column",
          gap: "1.5rem",
          maxWidth: "44rem",
        }}
      >
        <header style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
          <h2
            style={{
              fontFamily: "var(--font-display)",
              fontSize: "var(--text-display-l)",
              fontWeight: 400,
              margin: 0,
              letterSpacing: "var(--tracking-tight)",
            }}
          >
            Add paper
          </h2>
          <p
            style={{
              margin: 0,
              fontFamily: "var(--font-sans)",
              fontSize: "var(--text-small)",
              color: "var(--color-muted)",
              lineHeight: 1.5,
            }}
          >
            Add a paper you found outside of arXiv. It runs through the keyword
            classifier inline and appears in today&rsquo;s queue.
          </p>
        </header>

        {success && (
          <ResultCard success={success} onAddAnother={resetForm} />
        )}

        <DraftPanel onApply={applyDraft} />

        <form
          onSubmit={handleSubmit}
          noValidate
          style={{
            display: "flex",
            flexDirection: "column",
            gap: "1.25rem",
          }}
        >
          <TextField
            id={urlId}
            label="URL"
            value={form.url}
            onChange={(v) => update("url", v)}
            placeholder="https://arxiv.org/abs/…"
            required
            disabled={submitting}
            error={errors.url}
          />

          <TextField
            id={titleId}
            label="Title"
            value={form.title}
            onChange={(v) => update("title", v)}
            required
            disabled={submitting}
            error={errors.title}
          />

          <TextField
            id={abstractId}
            label="Abstract"
            value={form.abstract}
            onChange={(v) => update("abstract", v)}
            multiline
            placeholder="Paste the abstract here (optional)."
            disabled={submitting}
          />

          <div style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
            <label htmlFor={publishedId} style={captionStyle()}>
              Published date <span aria-hidden="true">*</span>
            </label>
            <input
              id={publishedId}
              type="date"
              value={form.publishedDate}
              onChange={(e) => update("publishedDate", e.target.value)}
              required
              disabled={submitting}
              aria-invalid={errors.publishedDate ? "true" : undefined}
              aria-describedby={
                errors.publishedDate ? `${publishedId}-error` : undefined
              }
              style={{
                width: "100%",
                fontFamily: "var(--font-mono)",
                fontSize: "var(--text-small)",
                background: "transparent",
                color: "inherit",
                border: "none",
                borderBottom: `1px solid ${errors.publishedDate ? "var(--color-accent)" : "var(--color-rule)"}`,
                outline: "none",
                padding: "0.25rem 0",
              }}
            />
            {errors.publishedDate && (
              <span
                id={`${publishedId}-error`}
                role="alert"
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: "var(--text-micro)",
                  color: "var(--color-accent)",
                }}
              >
                {errors.publishedDate}
              </span>
            )}
          </div>

          <KeywordList
            label="Authors"
            value={form.authors}
            onChange={(next) => update("authors", next)}
            placeholder="Add an author…"
            disabled={submitting}
          />

          <details
            style={{
              border: "1px solid var(--color-rule)",
              borderRadius: "var(--radius-sm)",
              padding: "0.75rem 1rem",
            }}
          >
            <summary
              style={{
                ...captionStyle(),
                cursor: "pointer",
                userSelect: "none",
              }}
            >
              More fields (optional)
            </summary>
            <div
              style={{
                marginTop: "1rem",
                display: "flex",
                flexDirection: "column",
                gap: "1.25rem",
              }}
            >
              <TextField
                id={pdfId}
                label="PDF URL"
                value={form.pdfUrl}
                onChange={(v) => update("pdfUrl", v)}
                placeholder="https://…/paper.pdf"
                disabled={submitting}
              />
              <TextField
                id={doiId}
                label="DOI"
                value={form.doi}
                onChange={(v) => update("doi", v)}
                placeholder="10.xxxx/…"
                disabled={submitting}
              />
              <TextField
                id={externalId}
                label="External ID"
                value={form.externalId}
                onChange={(v) => update("externalId", v)}
                placeholder="arxiv:2401.00000"
                disabled={submitting}
              />
              <div
                style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}
              >
                <label htmlFor={itemTypeId} style={captionStyle()}>
                  Item type
                </label>
                <select
                  id={itemTypeId}
                  value={form.itemType}
                  onChange={(e) =>
                    update("itemType", e.target.value as ManualItemType)
                  }
                  disabled={submitting}
                  style={{
                    fontFamily: "var(--font-sans)",
                    fontSize: "var(--text-small)",
                    background: "transparent",
                    color: "inherit",
                    border: "none",
                    borderBottom: "1px solid var(--color-rule)",
                    borderRadius: 0,
                    outline: "none",
                    padding: "0.25rem 0",
                  }}
                >
                  {ITEM_TYPES.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </details>

          {generalError && (
            <div
              role="alert"
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: "var(--text-micro)",
                color: "var(--color-accent)",
                wordBreak: "break-word",
              }}
            >
              {generalError}
            </div>
          )}

          <div style={{ display: "flex", gap: "1rem", alignItems: "baseline" }}>
            <Button type="submit" variant="primary" disabled={submitting}>
              {submitting ? "Submitting…" : "Submit"}
            </Button>
            <Button
              type="button"
              variant="ghost"
              onClick={resetForm}
              disabled={submitting}
            >
              Reset
            </Button>
          </div>
        </form>

        <details
          style={{
            border: "1px solid var(--color-rule)",
            borderRadius: "var(--radius-sm)",
            padding: "0.75rem 1rem",
          }}
        >
          <summary
            style={{
              ...captionStyle(),
              cursor: "pointer",
              userSelect: "none",
            }}
          >
            Chat with Ollama about a paper
          </summary>
          <div
            style={{
              marginTop: "1rem",
              display: "flex",
              flexDirection: "column",
              gap: "0.75rem",
            }}
          >
            <p
              style={{
                margin: 0,
                fontFamily: "var(--font-sans)",
                fontSize: "var(--text-small)",
                color: "var(--color-muted)",
                lineHeight: 1.5,
              }}
            >
              The panel is seeded with the radar's track list. Ask "should this
              paper be on the radar?" and the model will answer with the
              configured context in mind.
            </p>
            <OllamaChatPanel
              systemPrompt={buildChatSystemPrompt(trackNames)}
            />
          </div>
        </details>
      </main>
    </div>
  );
}
