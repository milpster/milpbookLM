import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { AuthProvider } from "./state/auth";
import "./styles.css";

const root = document.getElementById("root");
if (root === null) throw new Error("Application root is missing");

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 15_000, retry: false }, mutations: { retry: false } },
});

createRoot(root).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <App />
      </AuthProvider>
    </QueryClientProvider>
  </StrictMode>,
);
