// Generic two-pane Ollama chat UI.
//
// The conversation lives entirely in component state — the server is
// stateless and folds the message list into a single Ollama /api/generate
// prompt. We surface latency from the previous reply as a quiet footer so
// the user can spot a model that's gotten slow.

import { useCallback, useEffect, useId, useRef, useState } from "react";
import {
  ApiError,
  api,
  type OllamaChatMessage,
  type OllamaChatResponse,
  type OllamaHealthResponse,
} from "../lib/api";
import { Button } from "./Button";

interface OllamaChatPanelProps {
  systemPrompt?: string;
  initialMessages?: OllamaChatMessage[];
  onAssistantReply?: (
    message: OllamaChatMessage,
    full: OllamaChatResponse,
  ) => void;
}

interface Latency {
  ms: number;
  model: string;
}

const captionStyle: React.CSSProperties = {
  fontFamily: "var(--font-mono)",
  fontSize: "var(--text-micro)",
  color: "var(--color-muted)",
  letterSpacing: "var(--tracking-caps)",
  textTransform: "uppercase",
};

function userBubbleStyle(): React.CSSProperties {
  return {
    alignSelf: "flex-end",
    maxWidth: "85%",
    border: "1px solid var(--color-accent)",
    borderRadius: "var(--radius-sm)",
    padding: "0.5rem 0.75rem",
    background: "transparent",
    fontFamily: "var(--font-sans)",
    fontSize: "var(--text-small)",
    lineHeight: 1.5,
    whiteSpace: "pre-wrap",
    wordBreak: "break-word",
  };
}

function assistantBubbleStyle(): React.CSSProperties {
  return {
    alignSelf: "flex-start",
    maxWidth: "85%",
    border: "1px solid var(--color-rule)",
    borderRadius: "var(--radius-sm)",
    padding: "0.5rem 0.75rem",
    background: "transparent",
    fontFamily: "var(--font-sans)",
    fontSize: "var(--text-small)",
    lineHeight: 1.5,
    whiteSpace: "pre-wrap",
    wordBreak: "break-word",
  };
}

function formatLatency(ms: number): string {
  if (ms < 1000) return `${ms} ms`;
  return `${(ms / 1000).toFixed(1)} s`;
}

export function OllamaChatPanel({
  systemPrompt,
  initialMessages,
  onAssistantReply,
}: OllamaChatPanelProps) {
  const textareaId = useId();
  const [messages, setMessages] = useState<OllamaChatMessage[]>(
    initialMessages ?? [],
  );
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [latency, setLatency] = useState<Latency | null>(null);
  const [health, setHealth] = useState<OllamaHealthResponse | null>(null);
  const [healthChecking, setHealthChecking] = useState(true);
  const listRef = useRef<HTMLDivElement>(null);

  const checkHealth = useCallback(async () => {
    setHealthChecking(true);
    try {
      const res = await api.getOllamaHealth();
      setHealth(res);
    } catch (err) {
      // Health endpoint should never 5xx; if it does, treat as unreachable.
      setHealth({
        ok: false,
        base_url: "(unknown)",
        chat_model: "",
        chat_enabled: false,
        embeddings_model: "",
        embeddings_enabled: false,
        error: err instanceof Error ? err.message : "health check failed",
      });
    } finally {
      setHealthChecking(false);
    }
  }, []);

  useEffect(() => {
    void checkHealth();
  }, [checkHealth]);

  // Auto-scroll the message list to the bottom when a new message lands.
  useEffect(() => {
    const el = listRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [messages, sending]);

  async function send() {
    const content = draft.trim();
    if (!content || sending) return;
    const nextMessages: OllamaChatMessage[] = [
      ...messages,
      { role: "user", content },
    ];
    setMessages(nextMessages);
    setDraft("");
    setError(null);
    setSending(true);
    try {
      const response = await api.postOllamaChat({
        messages: nextMessages,
        system: systemPrompt,
      });
      const assistant: OllamaChatMessage = {
        role: "assistant",
        content: response.reply,
      };
      setMessages((prev) => [...prev, assistant]);
      setLatency({ ms: response.latency_ms, model: response.model });
      onAssistantReply?.(assistant, response);
    } catch (err) {
      let message = "Chat failed";
      if (err instanceof ApiError) message = err.message;
      else if (err instanceof Error) message = err.message;
      setError(message);
      // Drop the optimistic user message — let the user retry by editing draft.
      setMessages(messages);
      setDraft(content);
    } finally {
      setSending(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    // Cmd/Ctrl + Enter sends; plain Enter inserts a newline (multi-line input).
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      void send();
    }
  }

  if (healthChecking && health === null) {
    return (
      <div
        style={{
          fontFamily: "var(--font-mono)",
          fontSize: "var(--text-micro)",
          color: "var(--color-muted)",
        }}
      >
        Checking Ollama…
      </div>
    );
  }

  if (health && !health.ok) {
    return (
      <div
        role="status"
        style={{
          border: "1px solid var(--color-rule)",
          borderRadius: "var(--radius-sm)",
          padding: "1rem 1.25rem",
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
          Ollama unreachable at{" "}
          <span style={{ fontFamily: "var(--font-mono)" }}>
            {health.base_url}
          </span>
          .
        </p>
        {health.error && (
          <p
            style={{
              margin: 0,
              fontFamily: "var(--font-mono)",
              fontSize: "var(--text-micro)",
              color: "var(--color-muted)",
              wordBreak: "break-word",
            }}
          >
            {health.error}
          </p>
        )}
        <div>
          <Button
            type="button"
            variant="ghost"
            onClick={() => void checkHealth()}
            disabled={healthChecking}
          >
            {healthChecking ? "Retrying…" : "Retry"}
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "0.75rem",
        border: "1px solid var(--color-rule)",
        borderRadius: "var(--radius-sm)",
        padding: "0.75rem",
      }}
    >
      <div
        ref={listRef}
        role="log"
        aria-live="polite"
        style={{
          display: "flex",
          flexDirection: "column",
          gap: "0.5rem",
          maxHeight: "20rem",
          minHeight: "8rem",
          overflowY: "auto",
          padding: "0.25rem",
        }}
      >
        {messages.length === 0 && (
          <p
            style={{
              margin: 0,
              fontFamily: "var(--font-display)",
              fontStyle: "italic",
              fontSize: "var(--text-small)",
              color: "var(--color-muted)",
            }}
          >
            Start the conversation. The model only sees what you type — there
            is no shared chat history across sessions.
          </p>
        )}
        {messages.map((msg, i) => (
          <div
            key={i}
            style={
              msg.role === "user" ? userBubbleStyle() : assistantBubbleStyle()
            }
          >
            {msg.content}
          </div>
        ))}
        {sending && (
          <div
            style={{
              ...assistantBubbleStyle(),
              fontStyle: "italic",
              color: "var(--color-muted)",
            }}
          >
            Thinking…
          </div>
        )}
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
        <label htmlFor={textareaId} style={captionStyle}>
          Message
        </label>
        <textarea
          id={textareaId}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Type a message — Cmd/Ctrl+Enter to send."
          rows={3}
          disabled={sending}
          style={{
            width: "100%",
            fontFamily: "var(--font-sans)",
            fontSize: "var(--text-small)",
            lineHeight: 1.5,
            background: "transparent",
            color: "inherit",
            border: "1px solid var(--color-rule)",
            borderRadius: "var(--radius-sm)",
            padding: "0.5rem 0.625rem",
            resize: "vertical",
            outline: "none",
          }}
        />
      </div>

      {error && (
        <div
          role="alert"
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: "var(--text-micro)",
            color: "var(--color-accent)",
            wordBreak: "break-word",
          }}
        >
          {error}
        </div>
      )}

      <div
        style={{
          display: "flex",
          alignItems: "baseline",
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
          {latency
            ? `Replied in ${formatLatency(latency.ms)} · ${latency.model}`
            : health
              ? `model: ${health.chat_model}`
              : ""}
        </span>
        <Button
          type="button"
          variant="primary"
          size="sm"
          onClick={() => void send()}
          disabled={sending || draft.trim() === ""}
        >
          {sending ? "Sending…" : "Send"}
        </Button>
      </div>
    </div>
  );
}
