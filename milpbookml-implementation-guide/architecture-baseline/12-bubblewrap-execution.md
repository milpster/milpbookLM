# 12 — Local Isolated Code Execution with Bubblewrap

## 1. Rationale

Source-grounded data analysis is part of the parity target. Allowing the model to write and execute Python or small shell workflows makes spreadsheet analysis, statistics, transformations and custom charts much more capable than forcing every operation through a fixed analytics API.

Because the installation runs on our own GNU/Linux hardware for ourselves and colleagues, a heavyweight cloud microVM architecture is unnecessary. Generated code is nevertheless untrusted and should not run directly in the application process or with application credentials.

## 2. Abstraction

Higher layers target:

```text
ExecutionProvider
  create_session()
  stage_inputs()
  execute()
  collect_outputs()
  terminate()
```

Initial provider: `local-bubblewrap`.

Future possible providers: Podman/Docker, stronger VM isolation, remote worker. No higher-level feature may depend on Bubblewrap-specific arguments.

## 3. Linux identities

At minimum:

- application server runs as an unprivileged service identity;
- execution is performed by a separate unprivileged execution identity;
- execution identity has no access to application secrets/database credentials;
- workspace files are staged explicitly into per-run directories;
- identity separation is mediated by a narrow execution broker/IPC boundary rather than granting the application broad privilege to become arbitrary users.

## 4. Isolation profile

The enabled `local-bubblewrap` provider MUST enforce a reviewed baseline isolation profile containing:

- a private mount namespace and isolated root filesystem;
- read-only base runtime/interpreter files;
- writable ephemeral `/workspace` and temporary directories only where required;
- private `/tmp` and restricted `/proc`;
- no host home directories and no host `/run`/secret mounts;
- no host devices except an explicit minimal safe device set;
- private PID, IPC and network namespaces;
- `no_new_privs` and no effective capabilities;
- a new session or equivalent protection against terminal/TTY injection;
- a strict environment-variable allowlist;
- closure of unrelated inherited file descriptors/sockets before the child starts;
- explicit lifecycle supervision so cancellation, broker failure or timeout kills the sandbox process tree/cgroup rather than relying on Bubblewrap parent-process behavior alone.

The launcher SHOULD additionally prevent creation of nested user namespaces from inside the execution where supported and apply a reviewed seccomp allow/deny policy appropriate to the curated runtime. If a host cannot satisfy the mandatory namespace/privilege/resource prerequisites, the execution capability MUST be reported unavailable rather than silently running with weaker isolation.

Bubblewrap/chroot-style filesystem isolation is only one component. Bubblewrap is a toolkit for constructing a sandbox policy, not a complete ready-made security policy; protection depends on the launcher arguments and host-kernel configuration.

## 5. Resource controls

The execution launcher MUST enforce:

- wall-clock timeout;
- CPU quota/time;
- maximum resident memory;
- process count;
- output/file-size quota;
- maximum staged input size;
- execution concurrency limits.

A total writable-disk quota SHOULD also be enforced where the filesystem/storage mechanism supports it reliably. Linux cgroups are the preferred hard boundary for CPU/memory/process lifetime and MUST be used by the reference GNU/Linux execution provider for the resource classes they support. Bubblewrap itself is not a denial-of-service containment mechanism.

## 6. Runtime image

The base runtime can contain a curated analysis environment, initially likely including:

- Python;
- pandas;
- NumPy;
- SciPy;
- matplotlib;
- openpyxl;
- common CSV/JSON/text libraries.

Package installation at runtime SHOULD be disabled initially unless a controlled package policy is later introduced.

## 7. Input/output contract

Inputs are copied or bind-mounted read-only into the isolated environment under broker-generated safe paths; original filenames are metadata and are not trusted as staging paths. Outputs must be explicitly collected from a writable output directory and then registered as notebook/job artifacts after validation. Collection MUST reject path traversal and unsafe symlink/device/special-file tricks, enforce output quotas, determine content type independently of filename, and sanitize active formats (for example HTML/SVG) before browser rendering.

## 8. Networking

Direct outbound networking from model-generated code is **disabled by default** (AD-012). The initial Bubblewrap profile MUST unshare networking and must not inherit connected sockets or equivalent network-capable descriptors. Research/web access is performed through controlled agent web tools and required data is staged into `/workspace`.

Administrators MAY later define explicit alternative execution-network profiles such as `proxy-allowlist` or `unrestricted`, but these are opt-in policy choices. A network-enabled execution must be clearly indicated in the UI/job record, and the execution identity still receives no application/provider credentials by default.

## 9. Auditability

Each execution records code/script, input references, runtime image version, resource limits, stdout/stderr truncation, exit status, generated files and triggering user/agent/job. Code, stdout/stderr and staged/output content are notebook/user-private trace data subject to the same ACL/retention rules as the originating operation; they MUST NOT be copied into a globally readable administrator log merely for auditability.

## 10. Threat model

This is intended to contain accidental or model-generated harmful behavior on a trusted-team installation. It is not initially claimed to resist a determined hostile local user with host access or kernel-level vulnerabilities. The dedicated execution user, Bubblewrap policy, broker supervision, cgroups and secret separation together form the boundary; Bubblewrap alone must not be treated as one.

## 11. Version and host prerequisites

The deployment MUST use a currently supported/patched Bubblewrap build. As of the September 2026 reference baseline, upstream Bubblewrap 0.12.0 fixes a sandbox-setup absolute-symlink traversal issue disclosed in August 2026 and removes support for building Bubblewrap in historical setuid mode. The `local-bubblewrap` provider requires working unprivileged user namespaces plus the mount/PID/network namespace features used by its policy. Installation/health checks MUST reject a setuid-marked `bwrap` binary and MUST verify the required namespace operations before enabling model-driven execution. Bubblewrap remains a policy-construction toolkit; the launcher arguments, broker boundary, cgroups, seccomp and secret separation jointly define our sandbox.

## 12. Upstream security references

- Bubblewrap security model: https://github.com/containers/bubblewrap/blob/main/SECURITY.md
- Bubblewrap 0.12.0 release notes: https://github.com/containers/bubblewrap/blob/main/NEWS.md
- GHSA-pxhw-h44j-8pfx (fixed in 0.12.0): https://github.com/containers/bubblewrap/security/advisories/GHSA-pxhw-h44j-8pfx
