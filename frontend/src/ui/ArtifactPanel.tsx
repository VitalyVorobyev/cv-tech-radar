// Slide-in detail panel for an ecosystem artifact. Opens on radar-dot click;
// shows ecosystem refs (per-ecosystem last version + status), release-event
// history, the decision ring timeline, and Promote/Demote actions. Modeled on
// ItemPanel.tsx — animation is gated by prefers-reduced-motion via the
// `.cvradar-slide-in` keyframes in styles.css.

import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type {
  ArtifactDetail,
  ArtifactRefDetail,
  EcosystemEventItem,
  Ring,
} from "../lib/api";
import { api, isStaticMode } from "../lib/api";
import { CAPABILITY_LABEL, type CapabilityId, RING_ORDER } from "../lib/constants";
import { EcosystemBadge } from "./EcosystemBadge";
import { SeverityDot } from "./SeverityDot";

const IS_STATIC = isStaticMode();

interface ArtifactPanelProps {
  artifactId: number;
  onClose(): void;
}

function nextRing(current: Ring, direction: "promote" | "demote"): Ring | null {
  const idx = RING_ORDER.indexOf(current);
  if (idx < 0) return null;
  const target = direction === "promote" ? idx - 1 : idx + 1;
  if (target < 0 || target >= RING_ORDER.length) return null;
  return RING_ORDER[target]!;
}

function formatHistoryAt(at: string): string {
  const d = new Date(at);
  if (Number.isNaN(d.getTime())) return at;
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function formatVersionDate(at: string | null): string {
  if (!at) return "";
  const d = new Date(at);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

export function ArtifactPanel({ artifactId, onClose }: ArtifactPanelProps) {
  const queryClient = useQueryClient();
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["ecosystem-artifact", artifactId],
    queryFn: () => api.ecosystemArtifact(artifactId),
  });

  const decide = useMutation({
    mutationFn: async (target: Ring) => {
      if (!data) throw new Error("no artifact");
      return api.postEcosystemDecision({
        artifact_id: artifactId,
        ring: target,
        reason: `Moved to ${target} from the ecosystem radar.`,
        tracks: data.tracks,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["ecosystem-artifact", artifactId] });
      queryClient.invalidateQueries({ queryKey: ["ecosystem-board"] });
    },
  });

  // "Remove from radar" records an Ignore decision — the artifact drops off
  // the board (which excludes Ignore) but keeps its history.
  const remove = useMutation({
    mutationFn: async () => {
      if (!data) throw new Error("no artifact");
      return api.postEcosystemDecision({
        artifact_id: artifactId,
        ring: "Ignore",
        reason: "Removed from the ecosystem radar.",
        tracks: data.tracks,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["ecosystem-board"] });
      onClose();
    },
  });

  // Esc to close.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <aside
      role="dialog"
      aria-modal="false"
      aria-label="Artifact detail"
      className="cvradar-slide-in"
      style={{
        position: "fixed",
        top: 0,
        right: 0,
        height: "100dvh",
        width: "min(440px, 95vw)",
        zIndex: 40,
        padding: "1.5rem",
        background: "var(--color-paper)",
        borderLeft: "1px solid var(--color-rule)",
        overflowY: "auto",
        display: "flex",
        flexDirection: "column",
        gap: "1rem",
      }}
    >
      <header
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: "1rem",
        }}
      >
        <span
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: "var(--text-micro)",
            color: "var(--color-muted)",
          }}
        >
          {data ? `${data.key} · ${data.status}` : `#${artifactId}`}
        </span>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          style={{
            background: "transparent",
            border: "none",
            cursor: "pointer",
            padding: 0,
            fontFamily: "var(--font-mono)",
            fontSize: "var(--text-small)",
            color: "var(--color-muted)",
          }}
        >
          ✕
        </button>
      </header>

      {isLoading && (
        <div className="skeleton-block" style={{ height: "3.5rem" }} aria-hidden="true" />
      )}
      {isError && (
        <div
          role="alert"
          style={{
            fontFamily: "var(--font-display)",
            fontStyle: "italic",
            color: "var(--color-muted)",
          }}
        >
          Could not load: {error instanceof Error ? error.message : "unknown error"}.
        </div>
      )}

      {data && (
        <ArtifactPanelBody
          data={data}
          onDecide={decide.mutate}
          onRemove={remove.mutate}
          removePending={remove.isPending}
        />
      )}
    </aside>
  );
}

function ArtifactPanelBody({
  data,
  onDecide,
  onRemove,
  removePending,
}: {
  data: ArtifactDetail;
  onDecide(target: Ring): void;
  onRemove(): void;
  removePending: boolean;
}) {
  const ringIsAccent = data.ring === "Use" || data.ring === "Prototype";
  const promoteTarget =
    data.ring && data.ring !== "Ignore" ? nextRing(data.ring, "promote") : null;
  const demoteTarget =
    data.ring && data.ring !== "Ignore" ? nextRing(data.ring, "demote") : null;
  const canRemove = Boolean(data.ring) && data.ring !== "Ignore";
  const capabilityLabel =
    CAPABILITY_LABEL[data.capability as CapabilityId] ?? data.capability;
  return (
    <>
      <h2
        style={{
          fontFamily: "var(--font-display)",
          fontSize: "1.6rem",
          fontWeight: 400,
          letterSpacing: "-0.01em",
          lineHeight: 1.2,
          margin: 0,
        }}
      >
        {data.name}
      </h2>

      <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem", alignItems: "center" }}>
        {data.ring && (
          <span
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "var(--text-micro)",
              letterSpacing: "0.08em",
              textTransform: "uppercase",
              color: ringIsAccent ? "var(--color-accent)" : "currentColor",
              border: "1px solid var(--color-rule)",
              borderRadius: "var(--radius-sm)",
              padding: "0.125rem 0.5rem",
            }}
          >
            {data.ring}
          </span>
        )}
        <span style={pillMutedStyle}>{capabilityLabel}</span>
        {data.tracks.map((track) => (
          <span key={track} style={pillMutedStyle}>
            {track}
          </span>
        ))}
      </div>

      {data.description && (
        <blockquote
          style={{
            margin: 0,
            fontFamily: "var(--font-display)",
            fontStyle: "italic",
            fontSize: "1.05rem",
            opacity: 0.85,
            lineHeight: 1.5,
          }}
        >
          &ldquo;{data.description}&rdquo;
        </blockquote>
      )}

      {data.decisions.length > 0 && (
        <div
          aria-label="Decision history"
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: "0.25rem",
            alignItems: "baseline",
            fontFamily: "var(--font-mono)",
            fontSize: "var(--text-small)",
          }}
        >
          {data.decisions.map((entry, i) => {
            const last = i === data.decisions.length - 1;
            return (
              <span
                key={`${entry.ring}-${entry.decided_at}-${i}`}
                style={{ display: "inline-flex", alignItems: "baseline", gap: "0.25rem" }}
              >
                {i > 0 && (
                  <span style={{ color: "var(--color-muted)" }} aria-hidden="true">
                    →
                  </span>
                )}
                <span
                  style={{
                    color: last ? "var(--color-accent)" : "var(--color-muted)",
                    textTransform: "uppercase",
                    letterSpacing: "0.06em",
                  }}
                  title={formatHistoryAt(entry.decided_at)}
                >
                  {entry.ring}
                </span>
              </span>
            );
          })}
        </div>
      )}

      <RefsSection refs={data.refs} />

      <EventsSection events={data.events} />

      <footer style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem", marginTop: "auto" }}>
        {data.homepage_url && (
          <a
            href={data.homepage_url}
            target="_blank"
            rel="noopener noreferrer"
            style={actionStyle}
          >
            Homepage ↗
          </a>
        )}
        {!IS_STATIC && promoteTarget && (
          <button type="button" style={actionStyle} onClick={() => onDecide(promoteTarget)}>
            Promote to {promoteTarget}
          </button>
        )}
        {!IS_STATIC && demoteTarget && (
          <button type="button" style={actionStyle} onClick={() => onDecide(demoteTarget)}>
            Demote to {demoteTarget}
          </button>
        )}
        {!IS_STATIC && canRemove && (
          <button
            type="button"
            style={removeStyle}
            disabled={removePending}
            onClick={() => onRemove()}
          >
            {removePending ? "Removing…" : "Remove from radar"}
          </button>
        )}
      </footer>
    </>
  );
}

function SectionHeading({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={{
        fontFamily: "var(--font-mono)",
        fontSize: "var(--text-micro)",
        color: "var(--color-muted)",
        letterSpacing: "0.08em",
        textTransform: "uppercase",
        marginBottom: "0.5rem",
      }}
    >
      {children}
    </div>
  );
}

function RefsSection({ refs }: { refs: ArtifactRefDetail[] }) {
  return (
    <section aria-label="Ecosystem refs">
      <SectionHeading>Ecosystem refs</SectionHeading>
      {refs.length === 0 ? (
        <div
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: "var(--text-micro)",
            color: "var(--color-muted)",
          }}
        >
          ↳ no ecosystem refs configured
        </div>
      ) : (
        <ul
          style={{
            listStyle: "none",
            padding: 0,
            margin: 0,
            display: "flex",
            flexDirection: "column",
            gap: "0.5rem",
          }}
        >
          {refs.map((ref) => (
            <li
              key={`${ref.ecosystem}-${ref.ref}`}
              style={{
                display: "flex",
                alignItems: "baseline",
                gap: "0.5rem",
                flexWrap: "wrap",
              }}
            >
              <EcosystemBadge ecosystem={ref.ecosystem} />
              <span
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: "var(--text-small)",
                  color: "inherit",
                }}
              >
                {ref.ref}
              </span>
              <span
                style={{
                  marginLeft: "auto",
                  fontFamily: "var(--font-mono)",
                  fontSize: "var(--text-micro)",
                  color:
                    ref.last_status === "ok"
                      ? "var(--color-muted)"
                      : "var(--color-accent)",
                }}
                title={
                  ref.last_release_at
                    ? `released ${formatVersionDate(ref.last_release_at)}`
                    : ref.last_status
                }
              >
                {ref.last_version
                  ? ref.last_version
                  : ref.last_status === "ok"
                    ? "—"
                    : ref.last_status}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function EventsSection({ events }: { events: EcosystemEventItem[] }) {
  return (
    <section aria-label="Release history">
      <SectionHeading>Release history</SectionHeading>
      {events.length === 0 ? (
        <div
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: "var(--text-micro)",
            color: "var(--color-muted)",
          }}
        >
          ↳ no release events recorded yet
        </div>
      ) : (
        <ul
          style={{
            listStyle: "none",
            padding: 0,
            margin: 0,
            display: "flex",
            flexDirection: "column",
            gap: "0.5rem",
          }}
        >
          {events.slice(0, 12).map((event) => (
            <ArtifactEventRow key={event.id} event={event} />
          ))}
        </ul>
      )}
    </section>
  );
}

function ArtifactEventRow({ event }: { event: EcosystemEventItem }) {
  const [open, setOpen] = useState(false);
  const hasBody = event.body.trim().length > 0;
  return (
    <li>
      <button
        type="button"
        onClick={() => hasBody && setOpen((v) => !v)}
        aria-expanded={hasBody ? open : undefined}
        style={{
          display: "flex",
          width: "100%",
          alignItems: "baseline",
          gap: "0.5rem",
          background: "transparent",
          border: "none",
          padding: 0,
          cursor: hasBody ? "pointer" : "default",
          textAlign: "left",
          color: "inherit",
        }}
      >
        <SeverityDot severity={event.severity} />
        <EcosystemBadge ecosystem={event.ecosystem} />
        <span
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: "var(--text-small)",
          }}
        >
          {event.version ?? event.event_type}
        </span>
        <span
          style={{
            marginLeft: "auto",
            fontFamily: "var(--font-mono)",
            fontSize: "var(--text-micro)",
            color: "var(--color-muted)",
            whiteSpace: "nowrap",
          }}
        >
          {formatVersionDate(event.event_date)}
        </span>
      </button>
      {event.summary && (
        <div
          style={{
            fontFamily: "var(--font-sans)",
            fontSize: "var(--text-small)",
            color: "var(--color-muted)",
            lineHeight: 1.4,
            marginTop: "0.125rem",
            marginLeft: "1rem",
          }}
        >
          {event.summary}
        </div>
      )}
      {open && hasBody && (
        <pre
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: "var(--text-micro)",
            color: "var(--color-muted)",
            lineHeight: 1.5,
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
            margin: "0.375rem 0 0 1rem",
            padding: "0.5rem",
            border: "1px solid var(--color-rule)",
            borderRadius: "var(--radius-sm)",
            maxHeight: "16rem",
            overflowY: "auto",
          }}
        >
          {event.body}
        </pre>
      )}
    </li>
  );
}

const pillMutedStyle = {
  fontFamily: "var(--font-mono)",
  fontSize: "var(--text-micro)",
  letterSpacing: "0.04em",
  color: "var(--color-muted)",
  border: "1px solid var(--color-rule)",
  borderRadius: "var(--radius-sm)",
  padding: "0.125rem 0.5rem",
} as const;

const actionStyle = {
  display: "inline-block",
  background: "transparent",
  border: "1px solid var(--color-rule)",
  color: "inherit",
  fontFamily: "var(--font-mono)",
  fontSize: "var(--text-small)",
  letterSpacing: "0.04em",
  padding: "0.5rem 0.875rem",
  borderRadius: "var(--radius-sm)",
  textDecoration: "none",
  cursor: "pointer",
} as const;

const removeStyle = {
  ...actionStyle,
  marginLeft: "auto",
  color: "var(--color-muted)",
  border: "1px solid transparent",
} as const;
