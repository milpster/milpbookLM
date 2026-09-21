import type { FormEvent, ReactNode } from "react";
import { useState } from "react";
import type { RouteProps } from "../App";
import { useAuth } from "../state/auth";

export function AuthRoute({ navigate }: RouteProps): ReactNode {
  const { signIn, signUp } = useAuth();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault();
    setBusy(true);
    setError("");
    const data = new FormData(event.currentTarget);
    const email = String(data.get("email") ?? "");
    const password = String(data.get("password") ?? "");
    try {
      if (mode === "register") await signUp(email, String(data.get("displayName") ?? ""), password);
      else await signIn(email, password);
      navigate("/notebooks");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Authentication failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="auth-layout">
      <section className="auth-intro" aria-labelledby="auth-title">
        <p className="kicker">Private research workspace</p>
        <h1 id="auth-title">Read deeply. Answer from evidence.</h1>
        <p>Collect local sources, follow every citation, and keep private conversations private.</p>
      </section>
      <section className="auth-panel" aria-labelledby="form-title">
        <fieldset className="segmented" aria-label="Authentication mode">
          <button type="button" aria-pressed={mode === "login"} onClick={() => setMode("login")}>
            Log in
          </button>
          <button
            type="button"
            aria-pressed={mode === "register"}
            onClick={() => setMode("register")}
          >
            Register
          </button>
        </fieldset>
        <h2 id="form-title">{mode === "login" ? "Welcome back" : "Create an account"}</h2>
        <form className="form-stack" onSubmit={(event) => void submit(event)}>
          {mode === "register" ? (
            <label>
              Display name
              <input name="displayName" autoComplete="name" required />
            </label>
          ) : null}
          <label>
            Email
            <input name="email" type="email" autoComplete="email" required />
          </label>
          <label>
            Password
            <input
              name="password"
              type="password"
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              minLength={12}
              required
            />
          </label>
          {error === "" ? null : (
            <p className="notice error" role="alert">
              {error}
            </p>
          )}
          <button className="primary" type="submit" disabled={busy}>
            {busy ? "Working..." : mode === "login" ? "Log in" : "Register"}
          </button>
        </form>
      </section>
    </main>
  );
}
