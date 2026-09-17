# 17 — Authentication, Authorization and Collaboration

## Authentication

Local accounts use `argon2-cffi` Argon2id with install-time calibrated parameters recorded in each hash. Sessions use 256-bit CSPRNG opaque tokens; only a keyed token hash and metadata are stored. Cookies are Secure, HttpOnly and SameSite=Lax or stricter, rotated at login/privilege change and paired with origin/CSRF validation on unsafe methods. Authentication and recovery endpoints have account/IP rate controls and enumeration-resistant responses. Bootstrap creates a one-time administrator credential through a local CLI; recovery is local and audited. OIDC and trusted-proxy auth remain optional adapters.

## Authorization

Centralize policy decisions as `(actor, action, resource, context) -> allow/deny + reason`. Roles are owner, editor and viewer plus installation administrator powers that do not imply content access. Repository queries include authorization filters; handlers also enforce object-level decisions.

Encode the architecture's permission matrix as policy fixtures, not scattered route conditionals. Viewer mutation/tool/Studio denials, editor owner-only denials, source-restriction reductions, private-history isolation and administrator-without-membership denials are mandatory generated cases. Background jobs carry the initiating actor and never substitute a service account's broader authority for content decisions.

## Sharing

Share links store only hashed tokens, explicit scope, expiry and revocation. Anonymous/public access is disabled by default. Copying a notebook excludes private chat and notes and re-evaluates source/connector restrictions.

## Credentials

Encrypt provider/connector secrets with libsodium XChaCha20-Poly1305 using a versioned installation master-key ID, random nonce and associated owner/scope/provider data. Decryption occurs only inside the dispatching adapter process; plaintext never enters job payloads or logs. Rotation rewrites ciphertext transactionally/resumably while old keys remain available until verification completes. User credentials are addressable only by their owner and cannot be selected as shared notebook defaults or used by other actors/background work.

## Lifecycle

Disablement revokes sessions and dispatch immediately. Sole-owner notebooks enter locked custody; metadata-only audited transfer or scheduled deletion resolves them without granting administrators content access. Account deletion removes private histories, traces, snapshots, credentials and preferences while shared authorship becomes a tombstone.

## Tests

Generate a role/action/resource matrix with positive, denial, enumeration and confused-deputy tests, including async revocation and derived-output restriction propagation.
