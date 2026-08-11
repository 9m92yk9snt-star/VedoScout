import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "@/index.css";
import App from "@/App";

// Swallow benign browser-internal noise so it never surfaces as an "uncaught"
// runtime error (mobile Safari especially):
// - "Can't find variable: EmptyRanges" — WebKit's OWN built-in <video controls>
//   UI script throwing internally (played/syncControl/handleEvent stack). Not our code.
// - AbortError — cancelled media play()/load or a dismissed share sheet.
const isBenign = (reasonOrMsg) => {
  const msg = String((reasonOrMsg && reasonOrMsg.message) || reasonOrMsg || "");
  return (
    msg.includes("EmptyRanges")
    || (reasonOrMsg && reasonOrMsg.name === "AbortError")
    || msg.includes("The operation was aborted")
    || msg.includes("interrupted by a call to pause")
    || msg.includes("ResizeObserver loop")
  );
};
window.addEventListener("error", (e) => {
  if (isBenign(e.error || e.message)) { e.preventDefault(); e.stopImmediatePropagation(); }
}, true);
window.addEventListener("unhandledrejection", (e) => {
  if (isBenign(e.reason)) { e.preventDefault(); e.stopImmediatePropagation(); }
}, true);

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60_000,
      refetchOnWindowFocus: false,
    },
  },
});

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </React.StrictMode>,
);
