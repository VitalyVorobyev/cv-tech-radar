// Read/write helpers for URL search params. Preserves window.location.hash
// across writes so hash-based routing keeps working. Reads merge params
// from both window.location.search and the query portion of the hash
// (`#/route?foo=bar`) so shared deep links work either way.

export function readUrlParams(): URLSearchParams {
  const out = new URLSearchParams(window.location.search);
  const hash = window.location.hash;
  const q = hash.indexOf("?");
  if (q >= 0) {
    const hashParams = new URLSearchParams(hash.slice(q + 1));
    for (const [k, v] of hashParams.entries()) {
      if (!out.has(k)) out.set(k, v);
    }
  }
  return out;
}

export function writeUrlParams(
  values: Record<string, string | null | undefined>,
  defaults: Record<string, string> = {},
): void {
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(values)) {
    if (!v) continue;
    if (defaults[k] !== undefined && v === defaults[k]) continue;
    params.set(k, v);
  }
  const search = params.toString();
  const next =
    window.location.pathname + (search ? `?${search}` : "") + window.location.hash;
  window.history.replaceState({}, "", next);
}
