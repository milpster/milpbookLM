import { type KeyboardEvent, type ReactNode, useEffect, useId, useRef, useState } from "react";
import {
  type EditorBlock,
  type HeadingLevel,
  type NewBlockKind,
  newEditorBlock,
} from "./note-blocks";

type EditableField = HTMLInputElement | HTMLTextAreaElement;
type ListBlock = Extract<EditorBlock, { readonly kind: "ordered_list" | "unordered_list" }>;

function assertNever(value: never): never {
  throw new Error(`Unexpected note block: ${JSON.stringify(value)}`);
}

function isListBlock(block: EditorBlock): block is ListBlock {
  return block.kind === "ordered_list" || block.kind === "unordered_list";
}

function updateAt<T>(items: readonly T[], index: number, next: T): readonly T[] {
  return items.map((item, currentIndex) => (currentIndex === index ? next : item));
}

export function BlockEditor({
  blocks,
  onChange,
  disabled,
}: {
  readonly blocks: readonly EditorBlock[];
  readonly onChange: (blocks: readonly EditorBlock[]) => void;
  readonly disabled: boolean;
}): ReactNode {
  const [isAddMenuOpen, setIsAddMenuOpen] = useState(false);
  const addMenuId = useId();
  const fields = useRef(new Map<string, EditableField>());
  const pendingFocus = useRef<string | null>(null);

  useEffect(() => {
    const fieldKey = pendingFocus.current;
    if (fieldKey !== null) fields.current.get(fieldKey)?.focus();
    pendingFocus.current = null;
  });

  const rememberField = (fieldKey: string, element: EditableField | null): void => {
    if (element === null) fields.current.delete(fieldKey);
    else fields.current.set(fieldKey, element);
  };
  const updateBlock = (blockIndex: number, next: EditorBlock): void =>
    onChange(updateAt(blocks, blockIndex, next));
  const editableFieldKey = (block: EditorBlock, blockIndex: number): string | null => {
    switch (block.kind) {
      case "paragraph":
      case "heading":
        return `block-${blockIndex}`;
      case "ordered_list":
      case "unordered_list":
        return block.items.length === 0 ? null : `list-${blockIndex}-${block.items.length - 1}`;
      case "preserved":
        return null;
      default:
        return assertNever(block);
    }
  };
  const previousEditableFieldKey = (blockIndex: number): string | null => {
    for (let previousIndex = blockIndex - 1; previousIndex >= 0; previousIndex -= 1) {
      const previousBlock = blocks[previousIndex];
      if (previousBlock === undefined) continue;
      const fieldKey = editableFieldKey(previousBlock, previousIndex);
      if (fieldKey !== null) return fieldKey;
    }
    return null;
  };
  const removeBlock = (blockIndex: number): void => {
    pendingFocus.current = previousEditableFieldKey(blockIndex);
    onChange(blocks.filter((_, index) => index !== blockIndex));
  };
  const moveBlock = (blockIndex: number, direction: -1 | 1): void => {
    const destination = blockIndex + direction;
    const block = blocks[blockIndex];
    if (block === undefined || destination < 0 || destination >= blocks.length) return;
    const nextBlocks = [...blocks];
    nextBlocks.splice(blockIndex, 1);
    nextBlocks.splice(destination, 0, block);
    onChange(nextBlocks);
  };
  const updateText = (blockIndex: number, text: string): void => {
    const block = blocks[blockIndex];
    if (block === undefined) return;
    switch (block.kind) {
      case "paragraph":
      case "heading":
        updateBlock(blockIndex, { ...block, text });
        return;
      case "ordered_list":
      case "unordered_list":
      case "preserved":
        return;
      default:
        assertNever(block);
    }
  };
  const updateHeadingLevel = (blockIndex: number, level: HeadingLevel): void => {
    const block = blocks[blockIndex];
    if (block?.kind === "heading") updateBlock(blockIndex, { ...block, level });
  };
  const updateListItem = (blockIndex: number, itemIndex: number, text: string): void => {
    const block = blocks[blockIndex];
    if (block === undefined || !isListBlock(block)) return;
    const items =
      block.items[itemIndex] === undefined
        ? [...block.items, text]
        : updateAt(block.items, itemIndex, text);
    updateBlock(blockIndex, { ...block, items });
  };
  const onListItemKeyDown = (
    event: KeyboardEvent<HTMLInputElement>,
    blockIndex: number,
    itemIndex: number,
  ): void => {
    const block = blocks[blockIndex];
    if (block === undefined || !isListBlock(block)) return;
    if (event.key === "Enter") {
      event.preventDefault();
      const items = block.items.length === 0 ? [""] : [...block.items];
      items.splice(itemIndex + 1, 0, "");
      pendingFocus.current = `list-${blockIndex}-${itemIndex + 1}`;
      updateBlock(blockIndex, { ...block, items });
      return;
    }
    if (event.key !== "Backspace" || event.currentTarget.value !== "") return;
    event.preventDefault();
    if (block.items.length <= 1) {
      removeBlock(blockIndex);
      return;
    }
    pendingFocus.current = `list-${blockIndex}-${Math.max(0, itemIndex - 1)}`;
    updateBlock(blockIndex, {
      ...block,
      items: block.items.filter((_, index) => index !== itemIndex),
    });
  };
  const addBlock = (kind: NewBlockKind): void => {
    const blockIndex = blocks.length;
    pendingFocus.current =
      kind === "paragraph" || kind === "heading" ? `block-${blockIndex}` : `list-${blockIndex}-0`;
    onChange([...blocks, newEditorBlock(kind)]);
    setIsAddMenuOpen(false);
  };
  const blockKeyOccurrences = new Map<string, number>();

  return (
    <div className="note-editor">
      {blocks.length === 0 ? (
        <p className="note-editor-empty">Start writing or add a block.</p>
      ) : null}
      {blocks.map((block, blockIndex) => {
        const snapshot = block.kind === "preserved" ? block.content : block.preserved;
        const baseBlockKey = `${block.kind}:${JSON.stringify(snapshot)}`;
        const blockOccurrence = blockKeyOccurrences.get(baseBlockKey) ?? 0;
        blockKeyOccurrences.set(baseBlockKey, blockOccurrence + 1);
        const blockKey = `${baseBlockKey}:${blockOccurrence}`;
        let field: ReactNode;
        switch (block.kind) {
          case "paragraph":
            field = (
              <textarea
                ref={(element) => rememberField(`block-${blockIndex}`, element)}
                className="note-editor-paragraph"
                aria-label={`Paragraph block ${blockIndex + 1}`}
                placeholder="Write something…"
                rows={1}
                value={block.text}
                disabled={disabled}
                onChange={(event) => updateText(blockIndex, event.target.value)}
              />
            );
            break;
          case "heading":
            field = (
              <div className="note-editor-heading">
                <input
                  ref={(element) => rememberField(`block-${blockIndex}`, element)}
                  className={`note-editor-heading-input level-${block.level}`}
                  aria-label={`Heading block ${blockIndex + 1}`}
                  placeholder="Heading…"
                  value={block.text}
                  disabled={disabled}
                  onChange={(event) => updateText(blockIndex, event.target.value)}
                />
                <fieldset
                  className="note-editor-heading-level"
                  aria-label={`Heading level for block ${blockIndex + 1}`}
                >
                  <button
                    type="button"
                    aria-label={`Set heading block ${blockIndex + 1} to H2`}
                    aria-pressed={block.level === 2}
                    disabled={disabled}
                    onClick={() => updateHeadingLevel(blockIndex, 2)}
                  >
                    H2
                  </button>
                  <button
                    type="button"
                    aria-label={`Set heading block ${blockIndex + 1} to H3`}
                    aria-pressed={block.level === 3}
                    disabled={disabled}
                    onClick={() => updateHeadingLevel(blockIndex, 3)}
                  >
                    H3
                  </button>
                </fieldset>
              </div>
            );
            break;
          case "ordered_list":
          case "unordered_list": {
            const List = block.kind === "ordered_list" ? "ol" : "ul";
            const items = block.items.length === 0 ? [""] : block.items;
            let itemKeyIndex = 0;
            field = (
              <List className={`note-editor-list note-editor-list--${block.kind}`}>
                {items.map((item, itemIndex) => {
                  const itemKey = `${blockKey}:item-${itemKeyIndex}`;
                  itemKeyIndex += 1;
                  return (
                    <li key={itemKey}>
                      <input
                        ref={(element) => rememberField(`list-${blockIndex}-${itemIndex}`, element)}
                        className="note-editor-list-input"
                        aria-label={`List item ${itemIndex + 1} in block ${blockIndex + 1}`}
                        placeholder="List item…"
                        value={item}
                        disabled={disabled}
                        onChange={(event) =>
                          updateListItem(blockIndex, itemIndex, event.target.value)
                        }
                        onKeyDown={(event) => onListItemKeyDown(event, blockIndex, itemIndex)}
                      />
                    </li>
                  );
                })}
              </List>
            );
            break;
          }
          case "preserved":
            field = (
              <p className="note-editor-preserved">
                <span>Preserved block</span> This block is preserved unchanged and is not editable.
              </p>
            );
            break;
          default:
            field = assertNever(block);
        }
        return (
          <article className={`note-editor-block note-editor-block--${block.kind}`} key={blockKey}>
            {field}
            {block.kind === "preserved" ? null : (
              <fieldset
                className="note-editor-block-actions"
                aria-label={`Block ${blockIndex + 1} controls`}
              >
                <button
                  type="button"
                  aria-label={`Move block ${blockIndex + 1} up`}
                  disabled={disabled || blockIndex === 0}
                  onClick={() => moveBlock(blockIndex, -1)}
                >
                  <span aria-hidden="true">&#8593;</span>
                </button>
                <button
                  type="button"
                  aria-label={`Move block ${blockIndex + 1} down`}
                  disabled={disabled || blockIndex === blocks.length - 1}
                  onClick={() => moveBlock(blockIndex, 1)}
                >
                  <span aria-hidden="true">&#8595;</span>
                </button>
                <button
                  type="button"
                  aria-label={`Delete block ${blockIndex + 1}`}
                  disabled={disabled}
                  onClick={() => removeBlock(blockIndex)}
                >
                  <span aria-hidden="true">&#215;</span>
                </button>
              </fieldset>
            )}
          </article>
        );
      })}
      <div className="note-editor-insert">
        <button
          className="note-editor-add-trigger"
          type="button"
          aria-expanded={isAddMenuOpen}
          aria-controls={addMenuId}
          disabled={disabled}
          onClick={() => setIsAddMenuOpen((open) => !open)}
        >
          + Add block
        </button>
        {isAddMenuOpen ? (
          <fieldset id={addMenuId} className="note-editor-add-menu">
            <legend className="sr-only">Add a block</legend>
            <button type="button" disabled={disabled} onClick={() => addBlock("paragraph")}>
              Paragraph
            </button>
            <button type="button" disabled={disabled} onClick={() => addBlock("heading")}>
              Heading
            </button>
            <button type="button" disabled={disabled} onClick={() => addBlock("ordered_list")}>
              Ordered list
            </button>
            <button type="button" disabled={disabled} onClick={() => addBlock("unordered_list")}>
              Unordered list
            </button>
          </fieldset>
        ) : null}
      </div>
    </div>
  );
}
