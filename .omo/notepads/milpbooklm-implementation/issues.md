# Issues — milpbooklm-implementation

Problems and gotchas encountered during work on this plan.

_Auto-scaffolded by /start-work. Append new entries below - never overwrite._

---

## Go-live follow-up (2026-09-23)

- The Serena bulk replacement endpoint ignored its supplied file scope. All accidental edits were restored before continuing; use per-file replacements for template work.

## Go-live capability state audit (2026-09-24)

- No registry seed values were changed: the audit found no defensible basis to promote parser-only PDF or plain-text claims, and notes are implemented but intentionally policy-disabled.
- The capability surface unit test is the machine-checkable evidence table for all 57 non-target entries; deliberate non-targets remain omitted from the client-visible effective surface.
