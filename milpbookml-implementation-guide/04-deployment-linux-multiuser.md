# 04 — Rootless Podman Deployment

## Services

The reference Compose project contains `web-api`, `worker-core`, optional `worker-media`, `browser-worker`, `postgres`, and a one-shot `migrate` service. SearXNG is a separately version-pinned service in the same private network profile, with JSON output explicitly enabled. Only the reverse proxy/API entry point is published. Because SearXNG is internal-only and application quotas apply before it, its public-instance bot limiter is disabled in the minimal profile; enabling that limiter adds its documented Valkey dependency as an optional deployment component.

Podman's `podman compose` command delegates to an external Compose provider. The supported profile therefore pins and selects `podman-compose` explicitly through `PODMAN_COMPOSE_PROVIDER`; it does not depend on whichever provider happens to have host precedence.

The reference `execution-worker` is a host-side systemd service under a dedicated unprivileged account, not a privileged or broadly mounted application container. This avoids relying on non-portable nested user-namespace behavior inside a rootless container. It exposes a permission-restricted Unix socket to `worker-core`; the browser-facing API cannot mount or reach that socket. The protocol accepts only a signed/nonce-bound execution specification containing a known runtime-image digest, staged blob IDs, limits and declared outputs. The broker obtains the peer identity from Unix credentials, rejects unknown callers, re-resolves staged inputs through its own narrow read service and never accepts host paths or arbitrary mount directives. An installation may containerize this worker only after the complete Chapter 12 prerequisite and escape suite passes on that topology.

## Identities and storage

Run all containers rootless with fixed non-root UIDs, read-only root filesystems, dropped capabilities, `no-new-privileges`, tmpfs scratch and explicit volumes. Parser/browser/execution workers use distinct identities and mounts. PostgreSQL, blobs, configuration and backups use separate volumes.

## Startup and upgrades

The migration job takes an advisory lock, verifies compatible source version, applies forward migrations and records build metadata. API readiness stays false during incompatible schema states. Rollback uses restored backups or an explicitly supported down migration; destructive migration rehearsals are mandatory.

## Systemd

Ship Quadlet/user-unit examples with lingering documented, restart limits, ordered database readiness and journal integration. Never require rootful containers.

The installer verifies subordinate UID/GID ranges, unprivileged user namespaces, cgroup v2 delegation to the execution service, Bubblewrap's installed version, filesystem atomic-finalization support and SELinux/AppArmor behavior. Missing prerequisites disable execution and fail its capability readiness; the installer never suggests disabling the host MAC framework globally.

## Configuration

Use environment/file secrets with `_FILE` support. Validate a typed configuration at startup and reject unknown security-sensitive keys. Installation configuration, user preferences and notebook policy remain distinct scopes.

Terminate TLS at a documented reverse proxy such as Caddy or an equivalent administrator-selected proxy. Forward only normalized scheme/host/client-address metadata from explicitly configured peers; strip incoming identity/proxy headers at the edge. The backend binds to a private Unix socket/network and is not simultaneously exposed on an unauthenticated host port.

## Health

`/health/live` checks the process only; `/health/ready` checks schema, database and blob integrity plus mandatory runtime prerequisites. `/api/v1/admin/diagnostics` reports optional provider/capability degradation without secrets.
