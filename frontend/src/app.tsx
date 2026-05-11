// App root — Phase A: single QueueView.
// Extension point: switch on window.location.hash for BoardView / DigestView in Phase B.
// QueryClient is configured here so all views share the same cache.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { QueueView } from "./views/QueueView";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Retry once on network failure; surface the error quickly.
      retry: 1,
      staleTime: 30_000,
    },
  },
});

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      {/* Phase B: switch on hash/pathname to render BoardView or DigestView */}
      <QueueView />
    </QueryClientProvider>
  );
}
