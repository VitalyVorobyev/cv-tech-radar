// Expanded decision panel shown inline beneath a CandidateRow.
// Contains: abstract, ring picker, reason field, action field, uncertain checkbox, save button.

import { useState, useEffect } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { Candidate, Ring, Decision } from "../lib/api";
import { api, ApiError } from "../lib/api";
import { RingPicker } from "./RingPicker";
import { TextField } from "./TextField";
import { Checkbox } from "./Checkbox";
import { Button } from "./Button";

interface CandidatePanelProps {
  candidate: Candidate;
  /** Called when mod+s or save button fires so the parent can also react */
  onSave?: (decision: Decision) => void;
}

export function CandidatePanel({ candidate, onSave }: CandidatePanelProps) {
  const existing = candidate.current_decision;
  const queryClient = useQueryClient();

  // Local form state — seeded from existing decision or suggestion
  const [ring, setRing] = useState<Ring>(existing?.ring ?? candidate.ring_suggested);
  const [reason, setReason] = useState(existing?.reason ?? "");
  const [action, setAction] = useState(existing?.action ?? "");
  const [uncertain, setUncertain] = useState(existing?.uncertain ?? false);
  const [reasonError, setReasonError] = useState<string | undefined>();
  const [rowError, setRowError] = useState<string | undefined>();

  // Re-seed if the candidate's existing decision changes (optimistic update resolved)
  useEffect(() => {
    if (existing) {
      setRing(existing.ring);
      setReason(existing.reason);
      setAction(existing.action ?? "");
      setUncertain(existing.uncertain);
    }
  }, [existing]);

  const mutation = useMutation({
    mutationFn: () =>
      api.postDecision({
        item_id: candidate.id,
        ring,
        reason,
        action: action || undefined,
        uncertain,
        decided_by: "curator",
      }),
    onSuccess: (data) => {
      setReasonError(undefined);
      setRowError(undefined);

      // Build a synthetic Decision to immediately reflect in the UI
      const newDecision: Decision = {
        id: data.decision_id,
        ring,
        reason,
        action,
        tracks: candidate.tracks,
        uncertain,
        decided_by: "curator",
        created_at: data.created_at,
      };

      // Optimistic update: patch the query cache
      queryClient.setQueryData<{ date: string; candidates: Candidate[] }>(
        ["queue", "today"],
        (old) => {
          if (!old) return old;
          return {
            ...old,
            candidates: old.candidates.map((c) =>
              c.id === candidate.id
                ? { ...c, current_decision: newDecision }
                : c,
            ),
          };
        },
      );

      onSave?.(newDecision);
    },
    onError: (err) => {
      if (err instanceof ApiError) {
        if (err.status === 422) {
          setReasonError(err.message);
        } else if (err.status === 404) {
          setRowError("Item no longer exists in the queue.");
        } else {
          setRowError(err.message);
        }
      } else {
        setRowError("Unexpected error. Try again.");
      }
    },
  });

  function handleSave() {
    if (!reason.trim()) {
      setReasonError("Reason is required.");
      return;
    }
    mutation.mutate();
  }

  // Expose save for the parent hotkey handler (mod+s)
  // The parent calls this via the panel ref — we use a data attribute trick instead:
  // parent passes onSave; hotkey calls it after triggering the button.
  // Simpler: expose via a named export that the parent can call.
  // We attach `data-save` so the QueueView can querySelector and click.

  return (
    <div
      style={{
        padding: "1.25rem 1.5rem 1.5rem",
        display: "flex",
        flexDirection: "column",
        gap: "1.25rem",
        borderTop: "1px solid var(--color-rule)",
      }}
    >
      {/* Abstract */}
      <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
        <p
          className="abstract-clamp"
          style={{
            fontFamily: "var(--font-display)",
            fontSize: "0.875rem",
            lineHeight: "1.5714",
            margin: 0,
          }}
        >
          {candidate.abstract}
        </p>
        {candidate.url && (
          <a
            href={candidate.url}
            target="_blank"
            rel="noopener noreferrer"
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "var(--text-micro)",
              color: "var(--color-accent)",
              textDecoration: "none",
            }}
          >
            Read full &rarr;
          </a>
        )}
      </div>

      {/* Pipeline rationale */}
      {candidate.pipeline_rationale && (
        <p
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: "var(--text-micro)",
            color: "var(--color-muted)",
            margin: 0,
            lineHeight: "1.6",
          }}
        >
          {candidate.pipeline_rationale}
        </p>
      )}

      {/* Ring picker */}
      <RingPicker value={ring} onChange={setRing} />

      {/* Reason — required */}
      <TextField
        id={`reason-${candidate.id}`}
        label="Reason"
        value={reason}
        onChange={(v) => {
          setReason(v);
          if (reasonError && v.trim()) setReasonError(undefined);
        }}
        placeholder="Short, skeptical rationale…"
        multiline
        required
        error={reasonError}
      />

      {/* Action — optional */}
      <TextField
        id={`action-${candidate.id}`}
        label="Action (optional)"
        value={action}
        onChange={setAction}
        placeholder="Concrete next step or leave blank"
      />

      {/* Uncertain + save row */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: "1rem",
          flexWrap: "wrap",
        }}
      >
        <Checkbox
          label="Uncertain"
          checked={uncertain}
          onChange={setUncertain}
        />

        <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
          {rowError && (
            <span
              role="alert"
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: "var(--text-micro)",
                color: "var(--color-accent)",
              }}
            >
              {rowError}
            </span>
          )}
          <Button
            variant="primary"
            size="sm"
            onClick={handleSave}
            disabled={mutation.isPending}
            data-save="true"
            aria-busy={mutation.isPending}
          >
            {mutation.isPending ? "Saving…" : "Save"}
          </Button>
        </div>
      </div>
    </div>
  );
}
