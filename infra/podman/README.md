# Rootless Podman deployment

This project is intentionally unsupported under Docker or a rootful container daemon. The only
published service is Caddy; PostgreSQL, application workers, and SearXNG remain on the internal
network. Caddy reaches the API exclusively through `api-socket` and issues a local-CA certificate
for the configured LAN SAN (`MILPBOOKLM_LAN_HOST`). ACME is out of scope for v1.

## Host preparation

The administrator-run Ubuntu preparation commands are:

```sh
sudo apt-get update
sudo apt-get install -y podman bubblewrap
sudo usermod --add-subuids 100000-165535 --add-subgids 100000-165535 "$USER"
loginctl enable-linger "$USER"
uv tool install podman-compose==1.6.0
```

Log out and back in after changing subordinate ID ranges. Do not disable SELinux or AppArmor;
`install-check.sh` reports their state and fails closed when mandatory isolation prerequisites are
missing. Copy the example environment to `milpbooklm.env`, set a digest-pinned application image,
create the four files under `secrets/` with mode `0600`, and generate the prerequisite report:

```sh
./install-check.sh "$HOME/.local/share/milpbooklm/blobs" prerequisites.json
install -Dm0600 prerequisites.json "$HOME/.local/share/milpbooklm/config/prerequisites.json"
```

Install the example user units and Quadlet network under `~/.config/containers/systemd/` and
`~/.config/systemd/user/`, run `systemctl --user daemon-reload`, then enable
`milpbooklm-compose.service`. The compose service sets `PODMAN_COMPOSE_PROVIDER` to the exact uv
tool installation of `podman-compose` 1.6.0. Container stdout/stderr and service failures are
available through `journalctl --user -u milpbooklm-compose.service`.

The `execution-worker.socket` and hardened service/drop-in are placeholders only. Do not enable
them until task 29 installs the signed-spec broker executable. The API reports execution degraded
until the installer report says every prerequisite is ready.
