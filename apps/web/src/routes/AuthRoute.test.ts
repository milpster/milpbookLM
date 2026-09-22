import ky, { HTTPError } from "ky";
import { describe, expect, it } from "vitest";
import { authFailureMessage } from "./AuthRoute";

async function loginError(status: number): Promise<HTTPError> {
  try {
    await ky.post("http://localhost/api/v1/auth/login", {
      retry: 0,
      fetch: async () => new Response(null, { status }),
    });
  } catch (error) {
    if (error instanceof HTTPError) return error;
    throw error;
  }
  throw new Error(`Expected HTTP ${status}`);
}

describe("authFailureMessage", () => {
  it("maps a 401 to the invalid-credentials notice", async () => {
    expect(authFailureMessage(await loginError(401))).toBe("Invalid email or password.");
  });

  it("maps a 429 to the rate-limit notice", async () => {
    expect(authFailureMessage(await loginError(429))).toBe(
      "Too many attempts. Please wait a few minutes and try again.",
    );
  });

  it("keeps the generic fallback for other HTTP failures", async () => {
    expect(authFailureMessage(await loginError(500))).toBe("Authentication failed");
  });

  it("keeps the existing fallbacks for non-HTTP errors", () => {
    expect(authFailureMessage(new Error("network down"))).toBe("Authentication failed");
    expect(authFailureMessage("stray rejection")).toBe("Authentication failed");
  });
});
