import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { FormEvent, KeyboardEvent, ReactNode } from "react";
import { useRef, useState } from "react";
import { streamChat } from "../api/chat-stream";
import {
  cancelConversation,
  createConversation,
  getCapabilities,
  getConversation,
  listNoteRevisions,
  listNotes,
  isApiError,
  updateConversationConfig,
} from "../api/client";
import { queryKeys } from "../api/query-keys";
import type { ChatConfig, Conversation } from "../api/schemas";
import { chatConfigSchema } from "../api/schemas";
import { getActiveConversation, rememberActiveConversation } from "../state/conversations";
import { citationKey, dedupeCitations } from "./citations";

type Props = {
  readonly actorId: string;
  readonly notebookId: string;
  readonly navigate: (path: string) => void;
};
const defaultConfig: ChatConfig = { style: "standard", length: "default", output_language: "EN" };

export function ChatPanel({ actorId, notebookId, navigate }: Props): ReactNode {
  const queryClient = useQueryClient();
  // Seeded from the route-external store: this state must survive SPA unmounts.
  const [conversationId, setConversationId] = useState<string | null>(() =>
    getActiveConversation(notebookId),
  );
  const [streamed, setStreamed] = useState("");
  const [status, setStatus] = useState("Ready");
  const [createError, setCreateError] = useState("");
  const controller = useRef<AbortController | null>(null);
  const capabilities = useQuery({ queryKey: queryKeys.capabilities(), queryFn: getCapabilities });
  const chatCapability = capabilities.data?.capabilities.find(
    (item) => item.id === "grounded_chat",
  );
  const chatAvailable = chatCapability?.state === "available";
  const conversation = useQuery({
    queryKey: queryKeys.privateConversation(actorId, conversationId ?? "new"),
    queryFn: () => getConversation(conversationId ?? ""),
    enabled: conversationId !== null,
  });
  const noteRevisions = useQuery({
    queryKey: queryKeys.chatNoteRevisions(actorId, notebookId),
    queryFn: async () => {
      const notes = await listNotes(notebookId);
      const revisions = await Promise.all(notes.notes.map((note) => listNoteRevisions(note.note_id)));
      return revisions.flatMap((result) => result.revisions);
    },
  });
  const selectionKey = `milpbookLM:chat-notes:${actorId}:${notebookId}`;
  const [selectedNoteRevisionIds, setSelectedNoteRevisionIds] = useState<readonly string[]>(() => {
    const saved = sessionStorage.getItem(selectionKey);
    return saved === null ? [] : JSON.parse(saved) as string[];
  });
  const create = useMutation({
    mutationFn: () => createConversation(notebookId, defaultConfig),
    onMutate: () => setCreateError(""),
    onSuccess: (state) => {
      setConversationId(state.id);
      rememberActiveConversation(notebookId, state.id);
      queryClient.setQueryData(queryKeys.privateConversation(actorId, state.id), state);
    },
    onError: (error: unknown) =>
      setCreateError(
        isApiError(error) && error.response.status === 403
          ? "The request was blocked by a security check. Reload the page and try again. If it keeps happening, open milpbookLM at its configured web address."
          : "Could not start the conversation. Your session is still active; please try again.",
      ),
  });
  const updateConfig = useMutation({
    mutationFn: ({ id, config }: { readonly id: string; readonly config: ChatConfig }) =>
      updateConversationConfig(id, config),
    onSuccess: (state) =>
      queryClient.setQueryData(queryKeys.privateConversation(actorId, state.id), state),
  });

  const send = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault();
    if (conversationId === null) return;
    const data = new FormData(event.currentTarget);
    const content = String(data.get("message") ?? "").trim();
    if (content === "") return;
    event.currentTarget.reset();
    setStreamed("");
    setStatus("Generating answer");
    controller.current = new AbortController();
    try {
      await streamChat(conversationId, content, selectedNoteRevisionIds, controller.current.signal, {
        onToken: (token) => setStreamed((current) => current + token),
        onTerminal: (terminal) => {
          if (terminal.state !== null)
            queryClient.setQueryData(
              queryKeys.privateConversation(actorId, conversationId),
              terminal.state,
            );
          setStreamed("");
          setStatus(
            terminal.insufficient_evidence
              ? "Sources do not contain enough evidence"
              : "Answer complete",
          );
        },
        onCancelled: () => {
          setStreamed("");
          setStatus("Generation cancelled");
        },
      });
    } catch (caught) {
      if (!(caught instanceof DOMException && caught.name === "AbortError"))
        setStatus("The connection was lost. The conversation was reloaded.");
      await queryClient.fetchQuery({
        queryKey: queryKeys.privateConversation(actorId, conversationId),
        queryFn: () => getConversation(conversationId),
      });
      setStreamed("");
    } finally {
      controller.current = null;
    }
  };

  const onMessageKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>): void => {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      event.currentTarget.form?.requestSubmit();
    }
  };

  if (!chatAvailable)
    return (
      <div className="empty-state">
        <h2>Chat unavailable</h2>
        <p>
          {chatCapability?.reason ?? "Chat is not available on this installation."}
        </p>
      </div>
    );
  if (conversationId === null)
    return (
      <div className="empty-state">
        <h2>Start a private conversation</h2>
        <p>Your conversation stays private to you and is never shared with the notebook.</p>
        <button
          className="primary"
          type="button"
          disabled={create.isPending}
          onClick={() => create.mutate()}
        >
          {create.isPending ? "Starting..." : "New conversation"}
        </button>
        {createError === "" ? null : (
          <p className="notice error" role="alert">
            {createError}
          </p>
        )}
      </div>
    );
  const state = conversation.data;
  return (
    <div className="chat-layout">
      <section className="conversation" aria-labelledby="conversation-title">
        <div className="chat-toolbar">
          <h2 id="conversation-title">Conversation</h2>
          {state === undefined ? null : (
            <ConfigForm
              state={state}
              pending={updateConfig.isPending}
              onChange={(config) => updateConfig.mutate({ id: state.id, config })}
            />
          )}
        </div>
        <ol className="message-log">
          {state?.messages.map((message) => {
            const citations = dedupeCitations(message.citations);
            return (
              <li key={message.id} className={`message ${message.role}`}>
                <p className="resource-meta">{message.role}</p>
                <div className="message-content">{message.content}</div>
                {citations.length === 0 ? null : (
                  <fieldset className="citation-list" aria-label="Citations">
                    {citations.map((citation) => (
                      <a
                        key={citationKey(citation)}
                        href={`/viewer/${citation.source_version_id}/${citation.node_id}`}
                        onClick={(event) => {
                          event.preventDefault();
                          navigate(`/viewer/${citation.source_version_id}/${citation.node_id}`);
                        }}
                      >
                        {citation.label}
                      </a>
                    ))}
                  </fieldset>
                )}
              </li>
            );
          })}
        </ol>
        {streamed === "" ? null : (
          <div className="message assistant streaming">
            <p className="resource-meta">assistant, streaming</p>
            <div>{streamed}</div>
          </div>
        )}
        <p className="muted" role="status" aria-live="polite">
          {status}
        </p>
        <fieldset className="note-selection">
          <legend>Selected notes for grounding</legend>
          <p className="muted">Only checked immutable revisions are sent with this chat request.</p>
          {noteRevisions.data?.map((revision) => {
            const selected = selectedNoteRevisionIds.includes(revision.revision_id);
            return (
              <label key={revision.revision_id}>
                <input
                  type="checkbox"
                  checked={selected}
                  onChange={() => {
                    const next = selected
                      ? selectedNoteRevisionIds.filter((id) => id !== revision.revision_id)
                      : [...selectedNoteRevisionIds, revision.revision_id];
                    sessionStorage.setItem(selectionKey, JSON.stringify(next));
                    setSelectedNoteRevisionIds(next);
                  }}
                />
                Note revision {revision.revision_number}
              </label>
            );
          })}
        </fieldset>
        <form className="composer" onSubmit={(event) => void send(event)}>
          <label htmlFor="chat-message">Ask about selected notes and sources</label>
          <textarea
            id="chat-message"
            name="message"
            rows={3}
            required
            maxLength={10_000}
            onKeyDown={onMessageKeyDown}
          />
          <div className="action-cluster">
            <button className="primary" type="submit" disabled={controller.current !== null}>
              Send
            </button>
            <button
              type="button"
              disabled={controller.current === null}
              onClick={() => {
                void cancelConversation(conversationId);
                controller.current?.abort();
              }}
            >
              Cancel
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}

function ConfigForm({
  state,
  pending,
  onChange,
}: {
  readonly state: Conversation;
  readonly pending: boolean;
  readonly onChange: (config: ChatConfig) => void;
}): ReactNode {
  const submit = (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    onChange(
      chatConfigSchema.parse({
        style: data.get("style"),
        length: data.get("length"),
        output_language: data.get("language"),
      }),
    );
  };
  return (
    <form className="chat-config" onSubmit={submit}>
      <label>
        Style
        <select name="style" defaultValue={state.config.style}>
          <option value="standard">Standard</option>
          <option value="learning">Learning</option>
          <option value="custom">Custom</option>
        </select>
      </label>
      <label>
        Length
        <select name="length" defaultValue={state.config.length}>
          <option value="shorter">Shorter</option>
          <option value="default">Default</option>
          <option value="longer">Longer</option>
        </select>
      </label>
      <label>
        Output language
        <select name="language" defaultValue={state.config.output_language}>
          <option value="EN">English</option>
          <option value="DE">Deutsch</option>
        </select>
      </label>
      <button type="submit" disabled={pending}>
        {pending ? "Saving..." : "Save settings"}
      </button>
    </form>
  );
}
