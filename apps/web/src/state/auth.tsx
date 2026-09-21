import { useQueryClient } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { getActor, login, logout, register } from "../api/client";
import type { Actor } from "../api/schemas";

type AuthState = {
  readonly actor: Actor | null;
  readonly checking: boolean;
  readonly signIn: (email: string, password: string) => Promise<void>;
  readonly signUp: (email: string, displayName: string, password: string) => Promise<void>;
  readonly signOut: () => Promise<void>;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { readonly children: ReactNode }): ReactNode {
  const queryClient = useQueryClient();
  const [actor, setActor] = useState<Actor | null>(null);
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    let cancelled = false;
    getActor()
      .then((resolved) => {
        if (!cancelled) setActor(resolved);
      })
      .catch(() => {
        if (!cancelled) setActor(null);
      })
      .finally(() => {
        if (!cancelled) setChecking(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const value = useMemo<AuthState>(
    () => ({
      actor,
      checking,
      signIn: async (email, password) => {
        await login(email, password);
        setActor(await getActor());
      },
      signUp: async (email, displayName, password) => {
        await register({ email, display_name: displayName, password });
        await login(email, password);
        setActor(await getActor());
      },
      signOut: async () => {
        await logout();
        setActor(null);
        queryClient.clear();
      },
    }),
    [actor, checking, queryClient],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const state = useContext(AuthContext);
  if (state === null) throw new Error("AuthProvider is missing");
  return state;
}
