# 17 — Authentication, Authorization, Sharing and Collaboration

## 1. Multi-user requirement

Authentication and authorization are core even though the installation serves trusted colleagues. The system must know who owns and can access each notebook/source/artifact.

## 2. Initial roles and permission baseline

At minimum:

- **installation administrator** — manages installation configuration, users, providers, health and policy; administration does **not** automatically grant notebook-content access. Any emergency/support impersonation or break-glass content access, if implemented, must be explicit and audited;
- **notebook owner** — full notebook content/control, membership, sharing/copy/publication policy and destructive notebook operations;
- **notebook editor** — create/edit sources, shared notes and Studio artifacts; run research/Agentic Chat/execution subject to installation policy; manage ordinary notebook membership/sharing except owner-only operations such as ownership transfer, destructive notebook deletion and installation-governed public-sharing policy;
- **notebook viewer** — read allowed sources/shared notes/artifacts and run private ordinary grounded chat; no notebook mutation, Studio generation, source import, Agentic Chat/code execution or policy/provider administration by default.

Every user's conversation history remains private to that user unless a separate explicit share/publish operation is introduced. No organization/workspace role hierarchy is required in the baseline.

### 2.1 Permission matrix

The baseline authorization contract is:

| Capability | Owner | Editor | Viewer |
|---|---:|---:|---:|
| Read allowed sources/shared notes/artifacts | Yes | Yes | Yes |
| Run private ordinary grounded chat | Yes | Yes | Yes |
| Add/refresh/remove active sources | Yes | Yes | No |
| Edit shared user-authored notes | Yes | Yes | No |
| Generate/revise Studio artifacts | Yes | Yes | No |
| Run Research / Agentic Chat / code execution | Yes* | Yes* | No |
| Invite/remove viewer/editor members | Yes | Yes | No |
| Change notebook-wide shared model/provider defaults | Yes | No | No |
| Allow/forbid notebook copies or enable/disable public/link publication policy | Yes | No | No |
| Create/revoke artifact share link within enabled notebook policy | Yes | Yes | No |
| Copy notebook into a new notebook the caller owns | If allowed | If allowed | If allowed |
| Hard/privacy purge shared notebook content | Yes | No | No |
| Transfer ownership / add or remove owners | Yes | No | No |
| Delete notebook | Yes | No | No |

`*` Subject to installation/notebook provider/tool/execution policy and current source restrictions. Source-level restrictions can further reduce any role's access. An installation administrator has administrative powers described above but no implicit notebook-content role. Implementations MAY later add finer-grained permissions, but baseline behavior must not become more permissive than this matrix without an explicit policy/ADR.

## 3. Notebook sharing

Notebook sharing target:

- private;
- explicit member sharing;
- focused chat-view links;
- link-based viewing if enabled;
- public publishing if installation policy permits;
- owner-controlled notebook copy permission;
- artifact-specific share links where supported.

Editors can add/change sources, chat, notes and artifacts. Viewers can inspect allowed sources and shared notes, chat against the notebook if policy permits, and consume published artifacts without changing notebook content. **Each user's ordinary chat history is private to that user by default**, including in shared notebooks; notes and shared notebook content follow notebook ACLs. A focused chat-view link is a presentation mode, not an authorization boundary: hiding Sources/Studio in that view MUST NOT be treated as revoking access the viewer otherwise has. A user may start/reset to a new private conversation without destroying prior history; an explicit delete-history action is a privacy deletion and must purge that user's private conversation content and private context snapshots/caches rather than retaining a hidden copy for reproducibility.

### 3.1 Notebook copy semantics

For reference-product parity, an owner may allow or forbid notebook copies. A default private copy SHOULD duplicate source references/snapshots and Studio artifacts that the copying user is entitled to copy, while excluding other users' conversation histories and excluding notes by default. Source access/restrictions MUST be re-evaluated for the destination owner; copying a notebook cannot launder access to restricted sources or artifacts. The self-hosted implementation MAY offer additional explicit copy/export options beyond the parity default.

## 4. Public and featured notebooks

Public sharing is a late, optional parity surface and SHOULD be disabled by default in a private self-hosted deployment. If public notebook or artifact links are implemented, they must reuse one scoped/revocable share-link mechanism rather than create a separate anonymous-publication subsystem. Public links must not expose provider credentials, private job logs or hidden source metadata. If anonymous/share-token access is enabled, tokens MUST be high-entropy, unguessable, revocable and scope-bound; public endpoints require rate/abuse limits and must not treat resource ids alone as authorization. Featured/curated notebook discovery is optional presentation over that same sharing state, not a separate content platform.

The reference product currently lets owners and editors publish/manage public links. This self-hosted baseline deliberately keeps the notebook-wide decision to enable/disable public or link publication owner-only; once enabled, editors may create/revoke artifact share links within that policy. This is a documented least-privilege divergence, not an accidental misunderstanding of reference behavior.

A share link resolves the current share grant plus a live notebook/artifact resource; it is not a permanent copied credential to deleted content. Making the notebook private, revoking the grant, deleting the notebook/artifact, or losing required dependency-derived permission MUST make the link stop resolving. Artifact links may expose only the artifact when local policy chooses narrower sharing than the reference product, but that scope reduction never bypasses source/connector restrictions.

Public/featured viewers MAY invoke ordinary read-only, source-grounded notebook chat when sharing policy allows, subject to abuse/rate limits. They MUST NOT gain Studio artifact-generation, source mutation, Agentic Chat/tool/code execution, privileged provider selection or administrative capabilities merely from view access. Creating/revising Studio artifacts requires an editor-capable permission or an explicit copy/fork into a notebook the user may edit.

## 5. Authorization checks

Permissions apply not only to HTTP resources but also to:

- retrieval candidate filtering;
- agent source access;
- artifact evidence;
- source downloads;
- execution staged files;
- connector credentials;
- provider credentials;
- exported files.

A retrieval result must never leak a source the user cannot access. For restricted connector sources, notebook membership alone may be insufficient: authorization MUST also evaluate any connector/source access rule for the requesting user. A shared notebook may therefore contain a source that is present but unavailable to a particular collaborator.

## 6. Connector-supplied source restrictions

A connector MAY report per-user access checks or source-level restrictions (for example a private repository or licensed subscription source). The authorization layer MUST provide a generic hook for those checks independent of notebook ACLs. Per AD-023, a generated/derived object that contains or exposes material from restricted input `SourceVersion`s MUST retain those dependencies and MUST re-evaluate applicable current access/reuse restrictions at read/view, notebook copy, share-link creation, download/export and publication time. Generation, summarization or embedding into another artifact is not permission laundering. A connector restriction MAY explicitly permit transformed output reuse or prohibit notebook-level sharing/publication while the source is attached; such rules are represented as generic policy metadata, not vendor-specific domain objects. This is a small policy hook, not a general digital-rights or rights-management platform.

## 7. Authentication mechanism

Local accounts are the baseline (AD-018). Password-based local accounts MUST use Argon2id or a documented equivalently strong adaptive password hash; browser sessions MUST use standard secure session-cookie/CSRF practices, rotate session identifiers on authentication/privilege change, and rate-limit authentication attempts. Local-account recovery may use an administrator-driven reset flow; SMTP/email infrastructure is not a baseline dependency. Generic OIDC or trusted reverse-proxy authentication are optional integrations for installations that already have identity infrastructure; no Google identity provider or other vendor account is required. A separate service-account/PAT mechanism is deferred with the external automation API; if added later, it is subject to the same ACL/source-access checks and audit policy.

### 7.1 Initial administrator bootstrap and recovery

The installation MUST ship with no universal/default password. First-administrator creation must require an explicit local/operator-controlled bootstrap mechanism, such as a CLI command or one-time setup token exposed only through a protected local setup path. After bootstrap, administrators can create/disable users and issue one-time password-reset/setup credentials without requiring SMTP. Bootstrap/reset tokens must be single-use, short-lived where applicable, stored only as hashes when persisted, and invalidated after successful use.

### 7.2 Trusted reverse-proxy authentication boundary

If reverse-proxy authentication is enabled, the backend MUST accept asserted identity headers only from explicitly configured trusted proxy peers or an equivalent protected local ingress boundary. The edge proxy MUST remove/overwrite client-supplied copies of all identity/role headers before setting trusted values. Network/service configuration MUST prevent ordinary clients from reaching the backend directly around the proxy; if such reachability cannot be guaranteed, reverse-proxy authentication MUST be disabled. Proxy assertions identify the principal only; notebook roles and source restrictions are still resolved by the application's own authorization layer.

## 8. Provider credential ownership

Installation-scoped/shared providers are available according to installation/notebook policy. Personal provider credentials are usable only by their owning user for operations that user is otherwise authorized to initiate. A notebook model default MUST NOT silently borrow a collaborator's personal API key; notebook-wide defaults resolve only to shared installation provider configurations. Public/share-link traffic can never use personal credentials.

## 9. User/account lifecycle

A notebook must always have at least one owner. **Disabling** an account immediately blocks new authentication/sessions and user-attributed job/tool dispatch even when the user is a sole owner; the affected solely owned notebook enters the locked administrative-custody state defined by AD-022. Disablement is therefore never delayed merely to resolve ownership.

Before **final account deletion**, every solely owned notebook must be transferred to another owner or scheduled for notebook deletion. Installation administrators may use AD-022's audited metadata-only custody operation to perform that transfer/scheduling without acquiring notebook-content read access or becoming a notebook member. Account deletion removes the user's memberships, private chat/conversation and agent/research trace data, private prompt/context snapshots and caches attributable solely to that user, personal provider/connector credentials, preferences and per-user artifact/study state according to retention policy. Shared notes/sources/artifacts authored by the user may remain when retained by the notebook; authorship becomes a tombstoned/non-login identity rather than an active principal.

## 10. Authorization changes during jobs

Job authorization is not only a creation-time check. Per AD-021, current permissions/source restrictions are rechecked before security-sensitive reads, external dispatches, execution staging, side-effecting tool calls and final publication. Removing a member or revoking a restricted source should cancel or block affected queued/running user jobs as soon as practical.

## 11. Collaboration

Realtime **note** editing/synchronization for notebook editors is a parity target and SHOULD be supported by the collaboration layer. General-purpose simultaneous editing of every artifact/source is not a baseline requirement. Activity history, artifact/source versioning and safe concurrent updates are required foundations. Product-facing usage analytics are late/optional; operational/system analytics belong in observability rather than the notebook product surface.
