export type HeadingLevel = 2 | 3;

type PreservedFields = {
  readonly preserved: Record<string, unknown>;
};

type ParagraphBlock = PreservedFields & {
  readonly kind: "paragraph";
  readonly text: string;
};

type HeadingBlock = PreservedFields & {
  readonly kind: "heading";
  readonly level: HeadingLevel;
  readonly text: string;
};

type OrderedListBlock = PreservedFields & {
  readonly kind: "ordered_list";
  readonly items: readonly string[];
};

type UnorderedListBlock = PreservedFields & {
  readonly kind: "unordered_list";
  readonly items: readonly string[];
};

type PreservedBlock = {
  readonly kind: "preserved";
  readonly content: unknown;
};

export type EditorBlock =
  | ParagraphBlock
  | HeadingBlock
  | OrderedListBlock
  | UnorderedListBlock
  | PreservedBlock;

export type EditorDocument = {
  readonly baseContent: Record<string, unknown>;
  readonly blocks: readonly EditorBlock[];
};

export type NewBlockKind = Exclude<EditorBlock["kind"], "preserved">;

function assertNever(value: never): never {
  throw new Error(`Unexpected note block: ${JSON.stringify(value)}`);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isHeadingLevel(value: unknown): value is HeadingLevel {
  return value === 2 || value === 3;
}

function stringItems(value: unknown): readonly string[] | null {
  if (!Array.isArray(value)) return null;
  const items: string[] = [];
  for (const item of value) {
    if (typeof item !== "string") return null;
    items.push(item);
  }
  return items;
}

function newParagraphBlock(text = ""): ParagraphBlock {
  return { kind: "paragraph", text, preserved: {} };
}

export function newEditorBlock(kind: NewBlockKind): EditorBlock {
  switch (kind) {
    case "paragraph":
      return newParagraphBlock();
    case "heading":
      return { kind: "heading", level: 2, text: "", preserved: {} };
    case "ordered_list":
      return { kind: "ordered_list", items: [""], preserved: {} };
    case "unordered_list":
      return { kind: "unordered_list", items: [""], preserved: {} };
    default:
      return assertNever(kind);
  }
}

export function emptyEditorDocument(): EditorDocument {
  return { baseContent: {}, blocks: [newParagraphBlock()] };
}

function parseBlock(block: unknown): EditorBlock {
  if (!isRecord(block)) return { kind: "preserved", content: block };
  const type = block["type"];
  const text = block["text"];
  if (type === "paragraph" && typeof text === "string")
    return { kind: "paragraph", text, preserved: block };
  if (type === "heading" && isHeadingLevel(block["level"]) && typeof text === "string")
    return { kind: "heading", level: block["level"], text, preserved: block };
  const items = stringItems(block["items"]);
  if (type === "ordered_list" && items !== null)
    return { kind: "ordered_list", items, preserved: block };
  if (type === "unordered_list" && items !== null)
    return { kind: "unordered_list", items, preserved: block };
  return { kind: "preserved", content: block };
}

export function editorDocumentFromContent(content: Record<string, unknown>): EditorDocument {
  const baseContent = Object.fromEntries(
    Object.entries(content).filter(([key]) => key !== "blocks"),
  );
  const rawBlocks = content["blocks"];
  if (Array.isArray(rawBlocks)) {
    return { baseContent, blocks: rawBlocks.map(parseBlock) };
  }
  const legacyText = content["text"];
  return {
    baseContent,
    blocks: [newParagraphBlock(typeof legacyText === "string" ? legacyText : "")],
  };
}

function serializeBlock(block: EditorBlock): unknown {
  switch (block.kind) {
    case "paragraph":
      return { ...block.preserved, type: "paragraph", text: block.text };
    case "heading":
      return { ...block.preserved, type: "heading", level: block.level, text: block.text };
    case "ordered_list":
      return { ...block.preserved, type: "ordered_list", items: [...block.items] };
    case "unordered_list":
      return { ...block.preserved, type: "unordered_list", items: [...block.items] };
    case "preserved":
      return block.content;
    default:
      return assertNever(block);
  }
}

export function serializeEditorDocument(document: EditorDocument): Record<string, unknown> {
  return {
    ...document.baseContent,
    blocks: document.blocks.map(serializeBlock),
  };
}

export function serializeEditorBlocks(blocks: readonly EditorBlock[]): Record<string, unknown> {
  return serializeEditorDocument({ baseContent: {}, blocks });
}

function trimBlockText(block: EditorBlock): EditorBlock {
  switch (block.kind) {
    case "paragraph":
      return { ...block, text: block.text.trim() };
    case "heading":
      return { ...block, text: block.text.trim() };
    case "ordered_list":
      return { ...block, items: block.items.map((item) => item.trim()) };
    case "unordered_list":
      return { ...block, items: block.items.map((item) => item.trim()) };
    case "preserved":
      return block;
    default:
      return assertNever(block);
  }
}

export function editorDocumentSignature(document: EditorDocument): string {
  return JSON.stringify(
    serializeEditorDocument({
      baseContent: document.baseContent,
      blocks: document.blocks.map(trimBlockText),
    }),
  );
}
