import { useCallback, useState } from "react";

export interface Tweaks {
  showLabels: boolean;
}

const DEFAULTS: Tweaks = { showLabels: false };
const STORAGE_KEY = "cvradar.tweaks";

function read(): Tweaks {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULTS;
    const parsed = JSON.parse(raw) as Partial<Tweaks>;
    return { ...DEFAULTS, ...parsed };
  } catch {
    return DEFAULTS;
  }
}

export function useTweaks(): [Tweaks, (next: Partial<Tweaks>) => void] {
  const [tweaks, setTweaks] = useState<Tweaks>(read);
  const update = useCallback((next: Partial<Tweaks>) => {
    setTweaks((prev) => {
      const merged = { ...prev, ...next };
      try {
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify(merged));
      } catch {
        // ignore quota / private mode
      }
      return merged;
    });
  }, []);
  return [tweaks, update];
}
