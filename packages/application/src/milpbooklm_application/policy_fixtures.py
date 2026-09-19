"""
The baseline permission matrix as FIXTURE DATA (ch17 §2.1).

This is the fixture truth for ARCH-17-001..033: every decision the policy engine
makes derives from these rows, never from scattered route conditionals. The rows
transcribe the architecture-baseline matrix verbatim (architecture-baseline/
17-auth-sharing.md §2.1); changing them without a policy/ADR makes the baseline
more permissive and is forbidden (ARCH-17-003).
"""

from __future__ import annotations

from milpbooklm_domain.ownership import MembershipRole
from milpbooklm_domain.policy import (
    Grant,
    PolicyAction,
    PolicyMatrix,
)

OWNER = MembershipRole.OWNER
EDITOR = MembershipRole.EDITOR
VIEWER = MembershipRole.VIEWER

# (role, action, grant) rows of the baseline matrix. Absent cells default to DENY
# (PolicyMatrix.grant), so denials are explicit by omission of an ALLOW row.
MATRIX_ROWS: tuple[tuple[MembershipRole, PolicyAction, Grant], ...] = (
    # Read allowed sources / shared notes / artifacts: all three roles.
    (OWNER, PolicyAction.READ_CONTENT, Grant.ALLOW),
    (EDITOR, PolicyAction.READ_CONTENT, Grant.ALLOW),
    (VIEWER, PolicyAction.READ_CONTENT, Grant.ALLOW),
    # Run private ordinary grounded chat: all three roles (history stays private).
    (OWNER, PolicyAction.CHAT_GROUNDED_PRIVATE, Grant.ALLOW),
    (EDITOR, PolicyAction.CHAT_GROUNDED_PRIVATE, Grant.ALLOW),
    (VIEWER, PolicyAction.CHAT_GROUNDED_PRIVATE, Grant.ALLOW),
    # Add/refresh/remove active sources: owner + editor.
    (OWNER, PolicyAction.SOURCE_MUTATE, Grant.ALLOW),
    (EDITOR, PolicyAction.SOURCE_MUTATE, Grant.ALLOW),
    # Edit shared user-authored notes: owner + editor.
    (OWNER, PolicyAction.NOTE_MUTATE, Grant.ALLOW),
    (EDITOR, PolicyAction.NOTE_MUTATE, Grant.ALLOW),
    # Generate/revise Studio artifacts: owner + editor.
    (OWNER, PolicyAction.STUDIO_GENERATE, Grant.ALLOW),
    (EDITOR, PolicyAction.STUDIO_GENERATE, Grant.ALLOW),
    # Run Research / Agentic Chat / code execution: owner + editor (matrix footnote *).
    (OWNER, PolicyAction.RESEARCH_RUN, Grant.ALLOW),
    (EDITOR, PolicyAction.RESEARCH_RUN, Grant.ALLOW),
    # Invite/remove viewer/editor members: owner + editor.
    (OWNER, PolicyAction.MEMBER_MANAGE, Grant.ALLOW),
    (EDITOR, PolicyAction.MEMBER_MANAGE, Grant.ALLOW),
    # Change notebook-wide shared model/provider defaults: owner only.
    (OWNER, PolicyAction.PROVIDER_DEFAULTS, Grant.ALLOW),
    # Allow/forbid notebook copies or publication policy: owner only.
    (OWNER, PolicyAction.COPY_PUBLICATION_POLICY, Grant.ALLOW),
    # Create/revoke artifact share link within enabled policy: owner + editor.
    (OWNER, PolicyAction.SHARE_LINK_MANAGE, Grant.ALLOW),
    (EDITOR, PolicyAction.SHARE_LINK_MANAGE, Grant.ALLOW),
    # Copy notebook into a new notebook: every role, if the owner allows copies.
    (OWNER, PolicyAction.COPY_NOTEBOOK, Grant.IF_COPY_PERMITTED),
    (EDITOR, PolicyAction.COPY_NOTEBOOK, Grant.IF_COPY_PERMITTED),
    (VIEWER, PolicyAction.COPY_NOTEBOOK, Grant.IF_COPY_PERMITTED),
    # Hard/privacy purge of shared notebook content: owner only.
    (OWNER, PolicyAction.HARD_PURGE, Grant.ALLOW),
    # Transfer ownership / add or remove owners: owner only.
    (OWNER, PolicyAction.OWNERSHIP_TRANSFER, Grant.ALLOW),
    # Delete notebook: owner only.
    (OWNER, PolicyAction.NOTEBOOK_DELETE, Grant.ALLOW),
)

# Canonical fixture instance: the single matrix every application component uses.
BASELINE_MATRIX: PolicyMatrix = PolicyMatrix(
    grants={(role, action): grant for role, action, grant in MATRIX_ROWS}
)
