import { describe, expect, it } from "vitest";
import {
  getActiveConversation,
  getNotebookTab,
  rememberActiveConversation,
  rememberNotebookTab,
} from "./conversations";

describe("notebook conversation store", () => {
  it("round-trips the active conversation id for a notebook", () => {
    expect(getActiveConversation("notebook-a")).toBeNull();
    rememberActiveConversation("notebook-a", "conversation-1");
    expect(getActiveConversation("notebook-a")).toBe("conversation-1");
  });

  it("keeps conversations of different notebooks separate", () => {
    rememberActiveConversation("notebook-a", "conversation-1");
    rememberActiveConversation("notebook-b", "conversation-2");
    expect(getActiveConversation("notebook-a")).toBe("conversation-1");
    expect(getActiveConversation("notebook-b")).toBe("conversation-2");
  });

  it("tracks the last opened tab per notebook, defaulting to sources", () => {
    expect(getNotebookTab("notebook-c")).toBe("sources");
    rememberNotebookTab("notebook-c", "chat");
    expect(getNotebookTab("notebook-c")).toBe("chat");
    expect(getNotebookTab("notebook-d")).toBe("sources");
  });
});
