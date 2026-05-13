// Job polling helpers backed by TanStack Query.
// Polls every 400 ms while the job is queued/running, stops once terminal.

import { useQuery } from "@tanstack/react-query";
import type { Job, JobState } from "./api";
import { api, TERMINAL_JOB_STATES } from "./api";

const POLL_INTERVAL_MS = 400;

export function isTerminalState(state: JobState | undefined | null): boolean {
  if (!state) return false;
  return (TERMINAL_JOB_STATES as ReadonlyArray<string>).includes(state);
}

/**
 * Poll a single job by id until it reaches a terminal state.
 *
 * Pass `null` for `jobId` to disable polling entirely (e.g. when no job
 * has been submitted yet for this stage).
 */
export function useJobPoller(jobId: string | null) {
  return useQuery<Job, Error>({
    queryKey: ["job", jobId],
    queryFn: () => api.getJob(jobId as string),
    enabled: jobId !== null,
    // Refetch every POLL_INTERVAL_MS while not terminal; stop polling once done.
    refetchInterval: (query) => {
      const data = query.state.data;
      if (!data) return POLL_INTERVAL_MS;
      return isTerminalState(data.state) ? false : POLL_INTERVAL_MS;
    },
    refetchIntervalInBackground: false,
    // We want the freshest job state, not the 30s default staleTime.
    staleTime: 0,
  });
}
