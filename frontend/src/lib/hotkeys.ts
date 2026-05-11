// Global keyboard shortcut hook.
// Registers a single keydown listener on document and dispatches to handlers.

import { useEffect, useRef } from "react";

export type HotkeyHandler = (e: KeyboardEvent) => void;

export interface HotkeyMap {
  /** j — move focus to next row */
  j?: HotkeyHandler;
  /** k — move focus to prev row */
  k?: HotkeyHandler;
  /** Enter — toggle expand on focused row */
  Enter?: HotkeyHandler;
  /** 1–5 — set ring on expanded panel */
  "1"?: HotkeyHandler;
  "2"?: HotkeyHandler;
  "3"?: HotkeyHandler;
  "4"?: HotkeyHandler;
  "5"?: HotkeyHandler;
  /** u — toggle uncertain */
  u?: HotkeyHandler;
  /** Cmd/Ctrl+S — save expanded panel */
  "mod+s"?: HotkeyHandler;
  /** / — focus filter input */
  "/"?: HotkeyHandler;
  /** ? — open shortcut sheet */
  "?"?: HotkeyHandler;
  /** Esc — close overlay / collapse row */
  Escape?: HotkeyHandler;
}

/**
 * Register global hotkeys. Handlers are stable-ref'd so callers can pass
 * inline functions without causing re-registration on every render.
 *
 * Hotkeys are suppressed when focus is inside an <input>, <textarea>,
 * or <select> element — except for mod+s and Escape, which always fire.
 */
export function useHotkeys(map: HotkeyMap): void {
  // Keep a stable ref so the effect doesn't re-run when handlers change.
  const mapRef = useRef(map);
  mapRef.current = map;

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent): void {
      const target = e.target as HTMLElement;
      const inField =
        target.tagName === "INPUT" ||
        target.tagName === "TEXTAREA" ||
        target.tagName === "SELECT" ||
        target.isContentEditable;

      const isMod = e.metaKey || e.ctrlKey;

      // mod+s always fires
      if (isMod && e.key === "s") {
        e.preventDefault();
        mapRef.current["mod+s"]?.(e);
        return;
      }

      // Esc always fires
      if (e.key === "Escape") {
        mapRef.current.Escape?.(e);
        return;
      }

      // All other hotkeys are suppressed when in a text field
      if (inField) return;

      const key = e.key as keyof HotkeyMap;
      const handler = mapRef.current[key];
      if (handler) {
        e.preventDefault();
        handler(e);
      }
    }

    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, []); // intentionally empty — mapRef keeps the handlers current
}
