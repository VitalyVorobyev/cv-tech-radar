// Expanded decision panel shown inline beneath a CandidateRow.
// Contains: abstract, ring picker, reason field, action field, uncertain
// checkbox, and the decision actions.
//
// Two shapes, one panel:
//  * plain candidate (date queue)  — Save only; the human authors the decision.
//  * pending proposal (review inbox) — Confirm accepts the agent's proposal
//    verbatim, Save overrides it with an edited ring/reason (the backend
//    auto-confirms a human decision), Dismiss records Ignore.

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { Candidate, QueueResponse, Ring, Decision } from "../lib/api";
import { api, ApiError } from "../lib/api";
import { RingPicker } from "./RingPicker";
import { TextField } from "./TextField";
import { Checkbox } from "./Checkbox";
import { Button } from "./Button";

interface CandidatePanelProps {
  candidate: Candidate;
  /** Called when mod+s or save button fires so the parent can also react */
  onSave?: (decision: Decision) => void;
  /** Called after a proposal is confirmed as-is */
  onConfirm?: () => void;
  /** Called after a proposal is dismissed (recorded as Ignore) */
  onDismiss?: () => void;
}

const DISMISS_REASON = "Dismissed in review.";

export function CandidatePanel({
  candidate,
  onSave,
  onConfirm,
  onDismiss,
}: CandidatePanelProps) {
  const existing = candidate.current_decision;
  const proposal = candidate.proposal ?? null;
  // A confirmed decision wins; otherwise the agent's proposal seeds the form.
  const seed = existing ?? proposal;
  const queryClient = useQueryClient();

  // Local form state — seeded from the existing decision, the proposal, or the
  // pipeline suggestion, in that order.
  const [ring, setRing] = useState<Ring>(seed?.ring ?? candidate.ring_suggested);
  const [reason, setReason] = useState(seed?.reason ?? "");
  const [action, setAction] = useState(seed?.action ?? "");
  const [uncertain, setUncertain] = useState(seed?.uncertain ?? false);
  const [reasonError, setReasonError] = useState<string | undefined>();
  const [rowError, setRowError] = useState<string | undefined>();

  // Re-seed if the candidate's decision/proposal changes (optimistic update
  // resolved). Adjusting state during render (guarded by identity) avoids a
  // setState-in-effect; useState above already seeds the first render.
  const [seededDecision, setSeededDecision] = useState(seed);
  if (seed && seed !== seededDecision) {
    setSeededDecision(seed);
    setRing(seed.ring);
    setReason(seed.reason);
    setAction(seed.action ?? "");
    setUncertain(seed.uncertain);
  }

  // Every write here can change what is on the radar and what is still
  // pending; refresh both lanes plus the item detail.
  function invalidateAll() {
    queryClient.invalidateQueries({ queryKey: ["queue"] });
    queryClient.invalidateQueries({ queryKey: ["review"] });
    queryClient.invalidateQueries({ queryKey: ["review-summary"] });
    queryClient.invalidateQueries({ queryKey: ["board"] });
    queryClient.invalidateQueries({ queryKey: ["item", candidate.id] });
  }

  function handleError(err: unknown) {
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
  }

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

      // Optimistic update: patch every cached queue page. The queue query is
      // registered as ["queue", date] with a literal YYYY-MM-DD date, so a
      // prefix filter is the only key this panel can address — it does not
      // know which date it is being rendered for.
      queryClient.setQueriesData<QueueResponse>({ queryKey: ["queue"] }, (old) => {
        if (!old) return old;
        return {
          ...old,
          candidates: old.candidates.map((c) =>
            c.id === candidate.id ? { ...c, current_decision: newDecision } : c,
          ),
        };
      });
      invalidateAll();

      onSave?.(newDecision);
    },
    onError: handleError,
  });

  // Accept the agent's proposal verbatim — the human gate, one click.
  const confirmMutation = useMutation({
    mutationFn: () => {
      if (!proposal) throw new ApiError(400, "No proposal to confirm.");
      return api.confirmReview(proposal.decision_id);
    },
    onSuccess: () => {
      setReasonError(undefined);
      setRowError(undefined);
      invalidateAll();
      onConfirm?.();
    },
    onError: handleError,
  });

  // Quieter terminal action: record Ignore so the item leaves the inbox.
  const dismissMutation = useMutation({
    mutationFn: () =>
      api.postDecision({
        item_id: candidate.id,
        ring: "Ignore",
        reason: reason.trim() || DISMISS_REASON,
        uncertain: false,
        decided_by: "curator",
      }),
    onSuccess: () => {
      setReasonError(undefined);
      setRowError(undefined);
      invalidateAll();
      onDismiss?.();
    },
    onError: handleError,
  });

  function handleSave() {
    if (!reason.trim()) {
      setReasonError("Reason is required.");
      return;
    }
    mutation.mutate();
  }

  // Expose save for the parent hotkey handler (mod+s): the parent finds the
  // button via `[data-save="true"]` and clicks it. Confirm and dismiss carry
  // the same kind of hook for the review inbox.

  const busy =
    mutation.isPending || confirmMutation.isPending || dismissMutation.isPending;

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
      {/* Proposal banner — this decision is not on the radar yet */}
      {proposal && !existing && (
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            alignItems: "baseline",
            gap: "0.5rem",
            fontFamily: "var(--font-mono)",
            fontSize: "var(--text-micro)",
            color: "var(--color-muted)",
            letterSpacing: "0.04em",
            borderLeft: "2px solid var(--color-rule)",
            paddingLeft: "0.625rem",
          }}
        >
          <span>
            Proposed {proposal.ring} by {proposal.decided_by} — not on the radar
          </span>
          {candidate.previous_confirmed_ring && (
            <span>· was {candidate.previous_confirmed_ring}</span>
          )}
          {proposal.uncertain && <span>· uncertain</span>}
        </div>
      )}

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

      {/* Uncertain + action row */}
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
          {proposal && !existing && (
            <Button
              variant="primary"
              size="sm"
              onClick={() => confirmMutation.mutate()}
              disabled={busy}
              data-confirm="true"
              aria-busy={confirmMutation.isPending}
            >
              {confirmMutation.isPending ? "Confirming…" : "Confirm"}
            </Button>
          )}
          <Button
            variant={proposal && !existing ? "ghost" : "primary"}
            size="sm"
            onClick={handleSave}
            disabled={busy}
            data-save="true"
            aria-busy={mutation.isPending}
          >
            {mutation.isPending ? "Saving…" : "Save"}
          </Button>
          {proposal && !existing && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => dismissMutation.mutate()}
              disabled={busy}
              data-dismiss="true"
              aria-busy={dismissMutation.isPending}
              style={{ color: "var(--color-muted)", textDecoration: "none" }}
            >
              {dismissMutation.isPending ? "Dismissing…" : "Dismiss"}
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
