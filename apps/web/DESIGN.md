# MilpBook LM Design System

## 0. Research Log

- Embedded refs: shortlisted Linear, Notion, and Sentry; picked the operational taste rules plus Linear because a precise, low-distraction research workspace benefits from strong hierarchy and restrained chrome.
- Lazyweb: skipped because the task supplies an architecture contract and no network design-research tool was available in the delegated tool surface.
- Imagen drafts: skipped because no image-generation tool was available and this is a product shell, not an image-led marketing surface.
- Personas: keyboard-first researcher, low-vision reader at 200% zoom, and self-hosting operator monitoring long-running ingestion.

## 1. Atmosphere & Identity

A quiet evidence desk: dark, precise, and reading-led. The signature is a narrow source rail beside an uninterrupted conversation and document surface, with one violet accent reserved for actions and current selection.

## 2. Color

| Role | Token | Value | Usage |
| --- | --- | --- | --- |
| Canvas | `--surface-canvas` | `#0b0d10` | App background |
| Panel | `--surface-panel` | `#111419` | Sidebar and controls |
| Elevated | `--surface-elevated` | `#191d24` | Dialog-like and selected surfaces |
| Hover | `--surface-hover` | `#232832` | Interactive hover |
| Primary text | `--text-primary` | `#f3f5f7` | Headings and body |
| Secondary text | `--text-secondary` | `#b6bdc8` | Supporting copy |
| Muted text | `--text-muted` | `#8f98a6` | Metadata and placeholders |
| Border | `--border-default` | `#313844` | Controls and separators |
| Accent | `--accent-primary` | `#7775e7` | Primary actions and selection |
| Accent hover | `--accent-hover` | `#908ef2` | Hover and focus |
| Success | `--status-success` | `#53b886` | Ready and complete |
| Warning | `--status-warning` | `#e2ad5b` | Waiting and degraded |
| Error | `--status-error` | `#ef7d7d` | Errors and destructive actions |

Accent is interactive, never decorative. Surfaces use tonal shifts and sparse borders; no glows.

## 3. Typography

The primary stack is `ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif`; mono is `ui-monospace, "SFMono-Regular", Consolas, monospace`. The scale is 32/28px page title, 22px section title, 18px lead, 16px body, 14px secondary, and 12px metadata. Body text never falls below 14px.

## 4. Spacing & Layout

Spacing uses a 4px base: `--space-1` 4px, `--space-2` 8px, `--space-3` 12px, `--space-4` 16px, `--space-5` 20px, `--space-6` 24px, `--space-8` 32px, `--space-10` 40px. The shell is bounded to 100dvh; the main region owns scrolling. At widths below 760px navigation becomes a wrapping horizontal rail and all split views become one readable column. Content measure is 72ch.

## 5. Components

### App shell
- **Structure**: skip link, banner header, navigation, scroll-owning main, job live region.
- **States**: authenticated, anonymous, loading, narrow.
- **Accessibility**: named landmarks, current-page link, skip target, logical DOM order.

### Action and field
- **Variants**: primary, secondary, danger; text, textarea, select, file.
- **States**: hover, active, focus-visible, disabled, busy, inline error.
- **Accessibility**: persistent labels, 44px minimum target, errors associated by description.

### Resource row
- **Structure**: title, state and version metadata, contextual action cluster.
- **States**: default, selected, removed, processing, failed, optimistic rename.
- **Layout**: cluster that wraps before overflow.

### Conversation turn
- **Variants**: user and assistant, streaming, insufficient evidence.
- **Accessibility**: messages are an ordered log; citations are links; streaming status is polite.

### Source viewer
- **Variants**: safe text, sandboxed untrusted HTML, PDF/media, unavailable.
- **Accessibility**: named frame, visible locator summary, no focus trap.
- **Security**: HTML iframe uses `sandbox=""`, `srcdoc`, and therefore an opaque origin with scripts disabled.

## 6. Motion & Interaction

Motion intensity is 2/10. Only focus, hover, pressed feedback, and route-loading opacity transitions are used at 120ms ease-out. Reduced-motion removes all transitions. No layout property animates.

## 7. Depth & Surface

Mixed tonal-shift and border strategy: canvas, panel, and elevated tokens establish depth; a single 1px border separates controls and pane boundaries. No decorative shadows.

## 8. Accessibility Constraints & Accepted Debt

WCAG 2.2 AA is the target: 4.5:1 body contrast, visible 2px focus, complete keyboard reachability, semantic landmarks, live job state, 200% zoom reflow, reduced motion, and 44px touch targets.

| Item | Location | Why accepted | Owner / Exit |
| --- | --- | --- | --- |
| Automated axe and cross-browser suites | Wave 2 | D12/D15 explicitly defer committed test infrastructure | Task 18 Wave 2 |
| Browser-native PDF accessibility varies | Source viewer | Prototype delegates PDF rendering to the browser | Replace with reviewed accessible PDF renderer after prototype |
