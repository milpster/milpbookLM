"""ARCH-05-002: notebook memberships are the ownership source of truth; the optional
denormalized owner pointer is display-only and never grants access."""

from __future__ import annotations

import uuid

from hypothesis import given
from hypothesis import strategies as st
from milpbooklm_domain.ownership import (
    CustodyState,
    MembershipRole,
    NotebookMembership,
    NotebookOwnership,
    authorize,
    can_remove_owner,
    owner_ids,
    ownership_violation,
)

from tests.domain.invariants._factories import Db
from tests.domain.invariants._ver import write_ver

ROLE_BY_INDEX = (MembershipRole.OWNER, MembershipRole.EDITOR, MembershipRole.VIEWER)


def _ownership(
    users: list[uuid.UUID], role_indexes: list[int], custody: CustodyState
) -> NotebookOwnership:
    return NotebookOwnership(
        memberships=tuple(
            NotebookMembership(user, ROLE_BY_INDEX[role])
            for user, role in zip(users, role_indexes, strict=True)
        ),
        custody_state=custody,
        denormalized_owner_pointer=users[0] if users else None,
    )


def test_arch_05_002_owner_membership_is_truth(pg_env: dict[str, str]) -> None:
    @given(
        st.lists(st.uuids(), min_size=1, max_size=4)
        .flatmap(
            lambda users: st.tuples(
                st.just(users),
                st.lists(
                    st.integers(min_value=0, max_value=2),
                    min_size=len(users),
                    max_size=len(users),
                ),
            )
        ),
        st.sampled_from(list(CustodyState)),
    )
    def property_holds(
        pair: tuple[list[uuid.UUID], list[int]], custody: CustodyState
    ) -> None:
        users, role_indexes = pair
        own = _ownership(users, role_indexes, custody)
        has_owner = any(ROLE_BY_INDEX[r] is MembershipRole.OWNER for r in role_indexes)
        expected_violation = not has_owner and custody is not CustodyState.LOCKED_ADMIN_CUSTODY
        assert (ownership_violation(own) is None) is not expected_violation
        # The denormalized pointer (set to users[0] above) must never enter the owner set.
        assert owner_ids(own) == frozenset(
            u
            for u, r in zip(users, role_indexes, strict=True)
            if ROLE_BY_INDEX[r] is MembershipRole.OWNER
        )

    property_holds()

    # Explicit pointer-ignoring: a stranger pointer + one real owner membership.
    real_owner, stranger = uuid.uuid4(), uuid.uuid4()
    own = NotebookOwnership(
        memberships=(NotebookMembership(real_owner, MembershipRole.OWNER),),
        denormalized_owner_pointer=stranger,
    )
    assert owner_ids(own) == frozenset({real_owner})
    assert can_remove_owner(own, stranger) is False
    assert authorize(own, real_owner, MembershipRole.OWNER) is True
    # Final-owner rule: one owner, no custody -> not removable; with custody -> removable.
    assert can_remove_owner(own, real_owner) is False
    custodied = NotebookOwnership(
        memberships=own.memberships, custody_state=CustodyState.LOCKED_ADMIN_CUSTODY
    )
    assert can_remove_owner(custodied, real_owner) is True

    # DB: the denormalized pointer never materializes an owner membership.
    db = Db(pg_env["app"])
    try:
        owner_user, other_user = db.user(), db.user()
        notebook = db.notebook(owner_user)
        db.conn.execute("UPDATE notebooks SET owner_user_id = %s WHERE id ="
            " %s", (other_user, notebook))
        pointer_row = db.conn.execute(
            "SELECT owner_user_id FROM notebooks WHERE id = %s", (notebook,)
        ).fetchone()[0]
        membership_rows = db.conn.execute(
            "SELECT count(*) FROM notebook_memberships WHERE notebook_id = %s AND user_id = %s AND"
                " role = 'owner'",
            (notebook, other_user),
        ).fetchone()[0]
        assert pointer_row == other_user  # the display pointer moved...
        assert membership_rows == 0  # ...but created no owner membership (pointer is not truth)
    finally:
        db.close()
    write_ver(
        verification_id="VER-ARCH-05-002",
        requirement_id="ARCH-05-002",
        test_path="tests/domain/invariants/ver-arch-05-002.py",
        checks={
            "property": "hypothesis: violation is None iff an owner membership exists or custody"
                " is locked; pointer never in owner set",
            "pointer_ignored": "can_remove_owner/authorize consult memberships only",
            "final_owner_rule": "single owner removable iff locked_admin_custody",
            "db_pointer_not_truth": "owner_user_id update creates no notebook_memberships row",
        },
    )
