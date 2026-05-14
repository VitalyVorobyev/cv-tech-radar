// Sortable per-item score breakdown.
// Columns can be sorted ascending/descending by clicking the header.
// Row click invokes onSelect(item_id).

import { useMemo, useState } from "react";
import type { ScoreDebugItem } from "../lib/api";
import { RingLabel } from "./RingLabel";

type ColumnKey =
  | "item_id"
  | "final"
  | "ring"
  | "relevance"
  | "source_priority"
  | "implementation"
  | "novelty"
  | "negative_penalty"
  | "tracks"
  | "matched_keywords"
  | "title";

interface SortState {
  key: ColumnKey;
  dir: "asc" | "desc";
}

interface ScoreBreakdownTableProps {
  items: ScoreDebugItem[];
  onSelect?: (itemId: number) => void;
}

const COLUMNS: { key: ColumnKey; label: string; numeric?: boolean }[] = [
  { key: "item_id", label: "id", numeric: true },
  { key: "final", label: "final", numeric: true },
  { key: "ring", label: "ring" },
  { key: "relevance", label: "rel.", numeric: true },
  { key: "source_priority", label: "src.", numeric: true },
  { key: "implementation", label: "impl.", numeric: true },
  { key: "novelty", label: "novelty", numeric: true },
  { key: "negative_penalty", label: "neg.", numeric: true },
  { key: "tracks", label: "tracks" },
  { key: "matched_keywords", label: "matched" },
  { key: "title", label: "title" },
];

function compareItems(a: ScoreDebugItem, b: ScoreDebugItem, sort: SortState): number {
  const av = a[sort.key as keyof ScoreDebugItem];
  const bv = b[sort.key as keyof ScoreDebugItem];
  let cmp = 0;
  if (typeof av === "number" && typeof bv === "number") {
    cmp = av - bv;
  } else if (Array.isArray(av) && Array.isArray(bv)) {
    cmp = av.join(",").localeCompare(bv.join(","));
  } else {
    cmp = String(av ?? "").localeCompare(String(bv ?? ""));
  }
  return sort.dir === "asc" ? cmp : -cmp;
}

function fmtScore(n: number): string {
  if (!Number.isFinite(n)) return "—";
  return n.toFixed(1);
}

export function ScoreBreakdownTable({ items, onSelect }: ScoreBreakdownTableProps) {
  const [sort, setSort] = useState<SortState>({ key: "final", dir: "desc" });

  const sorted = useMemo(() => {
    const next = [...items];
    next.sort((a, b) => compareItems(a, b, sort));
    return next;
  }, [items, sort]);

  function onHeaderClick(key: ColumnKey) {
    setSort((prev) =>
      prev.key === key
        ? { key, dir: prev.dir === "asc" ? "desc" : "asc" }
        : { key, dir: key === "title" || key === "tracks" || key === "matched_keywords" || key === "ring" ? "asc" : "desc" },
    );
  }

  return (
    <div style={{ overflowX: "auto" }}>
      <table
        style={{
          width: "100%",
          borderCollapse: "collapse",
          fontFamily: "var(--font-mono)",
          fontSize: "var(--text-small)",
        }}
      >
        <thead>
          <tr style={{ borderBottom: "1px solid var(--color-rule)" }}>
            {COLUMNS.map((col) => {
              const active = sort.key === col.key;
              return (
                <th
                  key={col.key}
                  scope="col"
                  onClick={() => onHeaderClick(col.key)}
                  style={{
                    textAlign: col.numeric ? "right" : "left",
                    padding: "0.5rem 0.5rem",
                    fontSize: "var(--text-micro)",
                    fontWeight: 400,
                    letterSpacing: "var(--tracking-caps)",
                    textTransform: "uppercase",
                    color: active ? "var(--color-ink)" : "var(--color-muted)",
                    cursor: "pointer",
                    whiteSpace: "nowrap",
                    userSelect: "none",
                  }}
                >
                  {col.label}
                  {active && (
                    <span aria-hidden="true" style={{ marginLeft: "0.25rem" }}>
                      {sort.dir === "asc" ? "↑" : "↓"}
                    </span>
                  )}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {sorted.map((row) => (
            <tr
              key={row.item_id}
              onClick={() => onSelect?.(row.item_id)}
              style={{
                cursor: onSelect ? "pointer" : "default",
                borderBottom: "1px solid var(--color-rule)",
              }}
            >
              <td style={cellNumStyle}>{row.item_id}</td>
              <td style={{ ...cellNumStyle, fontWeight: 500 }}>{fmtScore(row.final)}</td>
              <td style={cellTextStyle}>
                <RingLabel ring={row.ring} />
              </td>
              <td style={cellNumStyle}>{fmtScore(row.relevance)}</td>
              <td style={cellNumStyle}>{fmtScore(row.source_priority)}</td>
              <td style={cellNumStyle}>{fmtScore(row.implementation)}</td>
              <td style={cellNumStyle}>{fmtScore(row.novelty)}</td>
              <td style={cellNumStyle}>{fmtScore(row.negative_penalty)}</td>
              <td style={cellMutedStyle}>{row.tracks.join(", ") || "—"}</td>
              <td style={cellMutedStyle}>
                {row.matched_keywords.length > 0
                  ? row.matched_keywords.slice(0, 4).join(", ") +
                    (row.matched_keywords.length > 4 ? "…" : "")
                  : "—"}
              </td>
              <td style={{ ...cellTextStyle, fontFamily: "var(--font-sans)" }}>
                {row.title}
              </td>
            </tr>
          ))}
          {sorted.length === 0 && (
            <tr>
              <td
                colSpan={COLUMNS.length}
                style={{
                  padding: "1.5rem",
                  textAlign: "center",
                  color: "var(--color-muted)",
                  fontStyle: "italic",
                  fontFamily: "var(--font-display)",
                }}
              >
                No classified items for this date.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

const cellTextStyle: React.CSSProperties = {
  padding: "0.5rem 0.5rem",
  verticalAlign: "top",
  textAlign: "left",
};

const cellNumStyle: React.CSSProperties = {
  ...cellTextStyle,
  textAlign: "right",
  whiteSpace: "nowrap",
};

const cellMutedStyle: React.CSSProperties = {
  ...cellTextStyle,
  color: "var(--color-muted)",
  maxWidth: "12rem",
  overflow: "hidden",
  textOverflow: "ellipsis",
  whiteSpace: "nowrap",
};
