"""ARCH-05-005: notebook membership does NOT grant access to another user's chat
history (private is the parity default); a reset creates a NEW conversation and never
mutates the old one."""

from __future__ import annotations

import uuid

from hypothesis import given
from hypothesis import strategies as st
from milpbooklm_domain.conversations import (
    ChatMode,
    Conversation,
    ConversationStatus,
    ConversationVisibility,
    Message,
    can_access_conversation,
    reset_conversation,
)

from tests.domain.invariants._factories import Db
from tests.domain.invariants._ver import write_ver


def _conversation(
    owner: uuid.UUID,
    visibility: ConversationVisibility,
    *,
    notebook_id: uuid.UUID | None = None,
) -> Conversation:
    return Conversation(
        id=uuid.uuid4(),
        owner_user_id=owner,
        notebook_id=notebook_id,
        visibility=visibility,
        mode=ChatMode.ORDINARY,
        status=ConversationStatus.OPEN,
        messages=(
            Message(
                id=uuid.uuid4(),
                role="assistant",
                content="secret reply",
                manifest_id=uuid.uuid4(),
            ),
        ),
    )


def test_arch_05_005_membership_is_not_chat_access(pg_env: dict[str, str]) -> None:
    @given(
        st.sampled_from(list(ConversationVisibility)),
        st.booleans(),
    )
    def property_holds(visibility: ConversationVisibility, member: bool) -> None:
        owner, other = uuid.uuid4(), uuid.uuid4()
        conversation = _conversation(owner, visibility)
        assert can_access_conversation(conversation, owner, is_notebook_member=member) is True
        # Membership alone is never an access path; only owner or explicit sharing is.
        assert can_access_conversation(conversation, other, is_notebook_member=member) is (
            visibility is ConversationVisibility.SHARED
        )

    property_holds()

    # Reset = a new open conversation; the old one (and its messages) is untouched.
    old = _conversation(uuid.uuid4(), ConversationVisibility.PRIVATE)
    new = reset_conversation(old, uuid.uuid4())
    assert new.id != old.id
    assert new.status is ConversationStatus.OPEN
    assert new.messages == ()
    assert old.messages != ()  # history preserved in the old conversation

    # DB: the conversation's access truth is its explicit owner_user_id column; the
    # notebook member is not the owner and the conversation stays private.
    db = Db(pg_env["app"])
    try:
        owner_user, member_user = db.user(), db.user()
        notebook = db.notebook(owner_user)
        db.membership(notebook, member_user, "editor")  # a real notebook member...
        conversation = db.conversation(owner_user, notebook_id=notebook)
        row = db.conn.execute(
            "SELECT owner_user_id, visibility FROM conversations WHERE id = %s", (conversation,)
        ).fetchone()
        assert row[0] == owner_user
        assert row[1] == "private"  # ...and the member still has no chat access
    finally:
        db.close()
    write_ver(
        verification_id="VER-ARCH-05-005",
        requirement_id="ARCH-05-005",
        test_path="tests/domain/invariants/ver-arch-05-005.py",
        checks={
            "property": "hypothesis: access iff owner or visibility=shared, membership never an"
                " access path",
            "reset_new_conversation": "reset returns a new open conversation with no messages; old"
                " history intact",
            "db_owner_is_truth": "conversations.owner_user_id + private visibility for a notebook"
                " member",
        },
    )
