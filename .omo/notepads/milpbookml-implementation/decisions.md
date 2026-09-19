# Decisions — milpbookml-implementation

Architectural choices and rationales discovered during work on this plan.

_Auto-scaffolded by /start-work. Append new entries below - never overwrite._

---

## D12 (2026-09-18, user) — Prototype-first execution + tooling mandates
- **Prototype-first**: all test-writing and non-prototype work is POSTPONED to a second wave. Wave 1 (current) delivers a working first prototype with most functionality. Manual/hands-on QA by agents is explicitly NOT deferred.
- **MCP-tools-first** (permission-enforced): every subagent prompt must name serena (find_symbol, get_symbols_overview, find_referencing_symbols, replace_symbol_body, execute_shell_command), codegraph, tldr, lsp_diagnostics, glob/grep/read as the primary tools; bash LAST resort; one-off scripts forbidden.
- **Concurrency**: max ONE active delegated agent at a time (user, 2026-09-18 later: supersedes the earlier "two as before").
- Task completion during prototype wave = functionality demonstrably works (hands-on evidence) + existing pipeline stays green; VER-evidence batches/mutation QA/new test files = second wave.

