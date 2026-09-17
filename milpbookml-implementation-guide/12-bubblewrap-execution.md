# 12 — Bubblewrap Execution Provider

## Process contract

`ExecutionProvider.run(spec)` accepts immutable staged inputs, runtime image/profile, argv, environment allowlist, resource limits and output declarations. It returns exit status, bounded stdout/stderr, produced artifact metadata, timings and audit correlation.

## Sandbox

Launch under a dedicated unprivileged UID using Bubblewrap: new user/PID/IPC/UTS/network namespaces; read-only runtime; tmpfs `/tmp`; explicit read-only inputs and writable output; minimal `/dev`; no host home, container socket or secrets; `no_new_privs`; seccomp where maintained. Default network namespace has no interfaces and no inherited connected descriptors.

## Resources

Create a cgroup v2 subtree per execution with memory, CPU and process limits; enforce wall timeout and output/temporary-storage quotas. Kill the whole cgroup on timeout/cancel. Record OOM and policy violations distinctly.

## Runtime images

Images are content-addressed, versioned and administrator-installed. No package installation during a run. A software-bill manifest accompanies each image.

## Output

Only declared paths under the output mount are collected. Validate size/type, quarantine, persist through the crash-consistent blob protocol, then publish after authorization revalidation. Symlinks and special files are rejected.

## Verification

Host-prerequisite tests and adversarial escape tests cover filesystem, process, network, descriptor, cgroup and signal boundaries. Unsupported kernels disable execution capability rather than weakening isolation.
