import { useQueryClient } from "@tanstack/react-query";
import type { ReactNode } from "react";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { getActor, isApiError, login, logout, onSessionInvalidated, register } from "../api/client";
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
  const actorRef = useRef<Actor | null>(null);

  const applyActor = useCallback((next: Actor | null) => {
    actorRef.current = next;
    setActor(next);
  }, []);

  const clearSession = useCallback(() => {
    applyActor(null);
    queryClient.clear();
  }, [applyActor, queryClient]);

  // A session-invalidation signal means the cookie/CSRF pair is dead. Drop the
  // session once; repeat signals while already logged out (e.g. failed logins)
  // must not re-clear.
  useEffect(
    () =>
      onSessionInvalidated(() => {
        if (actorRef.current === null) return;
        clearSession();
      }),
    [clearSession],
  );

  // Re-check the session when the tab becomes visible again: a 401 clears the
  // session, transient failures keep it.
  useEffect(() => {
    const revalidate = (): void => {
      if (document.visibilityState !== "visible" || actorRef.current === null) return;
      getActor()
        .then(applyActor)
        .catch((error: unknown) => {
          if (isApiError(error) && error.response.status === 401) clearSession();
        });
    };
    document.addEventListener("visibilitychange", revalidate);
    return () => document.removeEventListener("visibilitychange", revalidate);
  }, [applyActor, clearSession]);

  useEffect(() => {
    let cancelled = false;
    getActor()
      .then((resolved) => {
        if (!cancelled) applyActor(resolved);
      })
      .catch(() => {
        if (!cancelled) applyActor(null);
      })
      .finally(() => {
        if (!cancelled) setChecking(false);
      });
    return () => {
      cancelled = true;
    };
  }, [applyActor]);

  const value = useMemo<AuthState>(
    () => ({
      actor,
      checking,
      signIn: async (email, password) => {
        await login(email, password);
        applyActor(await getActor());
      },
      signUp: async (email, displayName, password) => {
        await register({ email, display_name: displayName, password });
        await login(email, password);
        applyActor(await getActor());
      },
      signOut: async () => {
        // The session may already be dead server-side; clear locally regardless.
        await logout().catch(() => undefined);
        clearSession();
      },
    }),
    [actor, checking, applyActor, clearSession],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const state = useContext(AuthContext);
  if (state === null) throw new Error("AuthProvider is missing");
  return state;
}
