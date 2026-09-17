# 19 — Security, Privacy and Data Governance

## 1. Security model

The installation is intended for trusted users on controlled infrastructure, but it processes untrusted documents, webpages and model outputs. Threats include malicious source content, prompt injection, web content, generated code, provider data leakage and accidental cross-user data exposure.

## 2. Data classes

The system MAY support notebook/installation policy labels such as public, internal or local-only, but classification is not required in order to use external providers. The default product policy is local-first routing with external providers allowed. An administrator/notebook owner can explicitly impose a local-only or provider-restricted policy.

## 3. External provider policy

Provider metadata SHOULD describe:

- local versus remote;
- processing region if known;
- retention policy;
- training/improvement use;
- contractual/privacy classification;
- whether sensitive data is allowed.

Unknown privacy/retention/training properties MUST remain explicitly `unknown`; they must not be silently treated as equivalent to local/no-retention processing. Restrictive policies MAY reject providers whose required trust properties are unknown.

Routing must never violate notebook policy. Whenever notebook/user content is sent to an external provider/service API, the initiating user must receive a visible disclosure naming the provider/model or capability. This disclosure is required even when external use is permitted by default, and it must also occur on local-to-external fallback.

This matters immediately because OpenCode documents that Big Pickle data collected during its free period may be used to improve the model.

## 4. Prompt injection

Web and document content is data, not trusted instruction. Agent/tool prompts should delimit source content clearly, and the tool runtime should enforce permissions independently of model instructions.

## 5. Secrets

Provider and connector credentials:

- MUST NOT be stored as plaintext in the transactional database; DB-stored secrets use authenticated encryption under an installation master key kept outside that database (for example a root/service-readable secret file, environment/system credential mechanism, or external secret manager);
- must never be written to normal logs/traces or returned through general configuration APIs;
- must not appear in prompts unless required by an explicit, narrowly scoped tool mechanism;
- must not be staged into code execution environments;
- should be scoped to installation/user as appropriate and support rotation/revocation.

Backup procedures must document how encrypted secrets and the master key are recovered without storing both in the same unprotected backup set. Secret ciphertext SHOULD carry a key/version identifier so the installation master key can be rotated by re-encrypting/rewrapping stored credentials without changing notebook/domain objects; rotation and loss-recovery procedures must be testable before relying on encrypted provider credentials in production.

## 6. Isolation

Generated code uses the Bubblewrap execution provider described in Chapter 12. The default execution profile has no direct network access (AD-012); network-enabled profiles are explicit administrator opt-ins and must not implicitly receive application/provider secrets. Generated-code output is untrusted input when re-entering the application and must be validated/sanitized like uploaded content.

Web browser automation should also be separated from the main application process and use controlled credential/session access.

## 7. Upload safety

Parsers operate on potentially malicious files. Mature libraries and dependency patching are not sufficient isolation: risky/native parsers, OCR engines, document converters, archive tools and media decoders that process attacker-controlled bytes MUST run in an OS-level isolated worker/subprocess profile outside the main application process, with no ambient application/provider secrets, no direct network by default, a restricted service-owned workspace and explicit CPU/RAM/process/file/time limits. Source file type is detected rather than trusted solely from filename extension. Archive/decompression bombs, nested containers, password-protected files and embedded active content require limits/failure modes; document macros are never executed by ingestion. Parser outputs are treated as untrusted until validated. Original filenames are display metadata, not trusted filesystem paths: local blob storage SHOULD use opaque/content-derived object identifiers beneath a service-owned root and MUST prevent path traversal, unsafe symlink following and accidental executable placement.

The same isolation contract applies to media probing, thumbnail extraction, transcoding and composition over uploaded, source-derived, generated or provider-returned assets. A trusted provider label does not make its binary output safe to parse in the application process.

### 7.1 External references inside documents

Parsers MUST disable uncontrolled external-resource resolution, including remote templates, external XML entities/DTDs, linked images/stylesheets and linked workbook/document resources. Intentional external acquisition must go through the controlled fetch/connector layer and its SSRF policy rather than through a parser library's implicit network access.

## 8. Web acquisition and SSRF safety

URL ingestion, agent fetchers and browser helpers process attacker-controlled locations. Non-browser server-side fetchers MUST apply redirect and response-size/time limits and MUST block loopback, link-local, cloud-metadata and private-address targets in the default Internet-research profile, with explicit administrator policy/profile for intentional intranet access. Address policy must be rechecked after DNS resolution and redirects so DNS rebinding or redirect-to-private-address cases cannot bypass it. Browser automation must use an equivalent egress boundary for navigation and subresources and must not inherit unrestricted application credentials.

### 8.1 Provider endpoint and callback safety

Custom provider/connector base URLs and webhook/callback targets can themselves become SSRF vectors. User-scoped arbitrary endpoints SHOULD be disabled or constrained by installation policy; administrator-approved trusted-LAN endpoints can be classified separately from external Internet providers.

Inbound provider callbacks MUST authenticate the provider/account and bind to a previously created local job plus opaque provider operation id. Where supported, verify signatures over the raw body and timestamp, enforce a bounded replay window, use constant-time secret comparison and rotate callback secrets. Otherwise use an equally strong provider-specific verification/reconciliation mechanism. Callback payload URLs are untrusted: result acquisition uses the configured provider adapter/allowlist and normal size/redirect/address controls, not an arbitrary server-side fetch. Duplicate, late or out-of-order callbacks are idempotent and never bypass current authorization, malware/media validation, safety policy or the final publication check.

## 9. Authorization boundary

Every data access path — API, retrieval, background job, agent, artifact renderer and execution input staging — must enforce the same authorization model. Per AD-021, asynchronous work revalidates current authorization/source restrictions before sensitive reads or new external/side-effecting dispatch and before exposing final results; a durable job id is not an authorization capability.

### 9.0 Historical-reference authorization

Historical identifiers, manifests and citations are references, not capabilities: every later dereference MUST apply the viewer's current notebook/source/note access and ACL policy. This includes exact historical `SourceVersion`, `NoteRevision`, `RunEvidenceSnapshot` and `ArtifactVersion` references. Composite artifacts MUST also re-check access to embedded child artifact/source/note material at view/export/share time rather than assuming authorization inherited from generation time.

### 9.1 Browser/UI content isolation

Source HTML, model-produced Markdown/HTML/SVG, citation previews and execution outputs MUST be rendered through sanitization/escaping rules that prevent stored/reflected XSS. The deployment SHOULD use TLS (normally via reverse proxy), secure cookie settings when cookies are used, CSRF protection, a restrictive Content Security Policy where practical, and clickjacking/frame protections appropriate to embedding policy.

### 9.2 Cache isolation

Prompt/result/retrieval caches can leak data just as databases can. Cache keys and storage MUST be scoped by authorization/privacy boundary and the exact immutable inputs (`SourceVersion` + canonical representation, selected `NoteRevision`, relevant `ArtifactVersion`/`RunEvidenceSnapshot`, user-private `StudySessionSnapshot` where applicable, resolved retrieval/index generation, generation-config hash, conversation-context hash where applicable, policy/provider mode); shared caches MUST NOT make one user's or notebook's confidential content available to another. Policy, ACL or source-access revocation must invalidate or bypass affected cached results.

## 10. Audit log

Security-relevant events SHOULD be auditable:

- login/admin changes;
- membership/sharing changes;
- provider credential changes;
- external-provider dispatch/fallback events for content-bearing operations;
- source imports/deletions;
- research external access;
- execution launches;
- public/share-link creation;
- policy changes.

## 11. Source access and export restrictions

Some optional connectors may carry access or redistribution restrictions in addition to notebook ACLs. The platform MUST preserve applicable connector-provided machine-readable restrictions and version-pinned provenance/dependencies needed to enforce AD-023. A derived message, note, report, export or other artifact does not become unrestricted merely because it transformed the source. Current restrictions are re-evaluated at read/view, copy, share-link creation, download/export and publication boundaries; explicit connector policy may permit transformed-output reuse. The baseline does not attempt to infer copyright or construct a digital-rights-management system. Successful ingestion must not be presented as granting redistribution rights.

## 12. Deletion, purge and backups

Deletion follows AD-016 and deliberately distinguishes **removal from the active corpus** from **hard purge**. The same privacy principle applies to user-private chat/tool traces: an explicit delete-history/account-delete operation must remove content-bearing private prompt/context snapshots and caches instead of retaining them solely for reproducibility.

- removing/tombstoning a source immediately excludes it from all future retrieval/generation; historical versions may remain only while retained outputs reference them and policy allows retention;
- hard/privacy purge deletes source bytes/canonical content/derived indexes from primary storage and follows the AD-016 dependency closure across generated messages, source-derived/provenance-linked note revisions, artifact versions/renders, dependent study-session snapshots, run-evidence snapshots, retained research/tool/execution outputs and generated files, prompt/conversation/context snapshots, staged execution inputs and content-bearing caches; the UI shows a deleted/unavailable state rather than returning hidden stale data;
- notebook deletion may use a configurable trash/grace period, after which notebook-owned primary data is purged;
- reference-aware garbage collection removes unreferenced historical blobs/renders;
- backups follow a documented finite retention schedule. Hard purge guarantees removal from active/primary systems promptly and from backups when those backup generations expire; backups are not silently rewritten in place.

Privacy/purge requests take precedence over historical reproducibility. The system MUST purge all system-controlled copies it can identify through ownership, provenance, dependency, cache and stored-request/context references, but MUST NOT claim that this can recall content already transmitted to an external provider or discover independent user-authored/manual copies whose provenance has been severed. The destructive-purge UI SHOULD show the count/types of dependent outputs that will be removed or invalidated before confirmation. Audit records may retain non-content metadata required to prove that deletion occurred, but MUST NOT retain the deleted source body or secret material.

### 12.1 Blob integrity and garbage collection

Blob persistence/deletion follows AD-024. Reconciliation MUST be able to identify (a) finalized blobs with no committed reference after the orphan safety interval and (b) committed references whose blob is missing or fails expected size/hash validation. The former are garbage-collection candidates; the latter are integrity incidents that must be surfaced and must not be silently converted into successful empty content. Garbage collection must respect retained-version, purge and in-flight-operation references.
