import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { api } from "./api";
import { assembleQuadrants, type Quadrant } from "./constants";

// Single source of truth for radar quadrants. Fetches /api/tracks once per
// session and assembles the four quadrants with their tracks grouped by the
// `quadrant` field in config/topics.yaml. Components consuming this should
// tolerate the initial empty array (rendered before the request resolves).
export function useQuadrants(): {
  quadrants: Quadrant[];
  isLoading: boolean;
  isError: boolean;
} {
  const query = useQuery({
    queryKey: ["tracks"],
    queryFn: () => api.tracks(),
    staleTime: 5 * 60 * 1000,
  });

  const quadrants = useMemo(
    () => assembleQuadrants(query.data?.tracks ?? []),
    [query.data],
  );

  return { quadrants, isLoading: query.isLoading, isError: query.isError };
}
