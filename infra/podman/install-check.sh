#!/usr/bin/env bash
set -u

blob_root=${1:-"$HOME/.local/share/milpbooklm/blobs"}
output=${2:-"prerequisites.json"}
failures=0
checks=()

record() {
  local name=$1
  local state=$2
  local detail=$3
  checks+=("{\"name\":\"$name\",\"status\":\"$state\",\"detail\":\"$detail\"}")
  if [ "$state" = "fail" ]; then
    failures=$((failures + 1))
  fi
}

if command -v podman >/dev/null 2>&1; then
  record podman pass installed
else
  record podman fail not_installed
fi

if command -v podman-compose >/dev/null 2>&1 && podman-compose --version 2>/dev/null | awk '{exit index($0,"1.6.0") == 0}'; then
  record podman_compose pass version_1.6.0
else
  record podman_compose fail version_1.6.0_required
fi

user_name=$(id -un)
if awk -F: -v user="$user_name" '$1 == user && $3 >= 65536 {found=1} END {exit !found}' /etc/subuid 2>/dev/null; then
  record subordinate_uids pass range_present
else
  record subordinate_uids fail range_missing_or_too_small
fi
if awk -F: -v user="$user_name" '$1 == user && $3 >= 65536 {found=1} END {exit !found}' /etc/subgid 2>/dev/null; then
  record subordinate_gids pass range_present
else
  record subordinate_gids fail range_missing_or_too_small
fi

userns_clone=1
if [ -r /proc/sys/kernel/unprivileged_userns_clone ]; then
  read -r userns_clone </proc/sys/kernel/unprivileged_userns_clone
fi
read -r max_userns </proc/sys/user/max_user_namespaces
if [ "$userns_clone" = "1" ] && [ "$max_userns" -gt 0 ]; then
  record unprivileged_user_namespaces pass enabled
else
  record unprivileged_user_namespaces fail disabled
fi

controllers=""
if [ -r /sys/fs/cgroup/cgroup.controllers ]; then
  read -r controllers </sys/fs/cgroup/cgroup.controllers
fi
if [ -n "$controllers" ] && printf '%s\n' "$controllers" | awk '{for(i=1;i<=NF;i++) seen[$i]=1} END {exit !(seen["memory"] && seen["pids"] && seen["cpu"] && seen["io"])}'; then
  record cgroup_v2_controllers pass memory_pids_cpu_io
else
  record cgroup_v2_controllers fail required_controllers_missing
fi

delegate=$(systemctl --user show execution-worker.service -p DelegateControllers --value 2>/dev/null || true)
if printf '%s\n' "$delegate" | awk '{for(i=1;i<=NF;i++) seen[$i]=1} END {exit !(seen["memory"] && seen["pids"] && seen["cpu"] && seen["io"])}'; then
  record cgroup_v2_delegation pass memory_pids_cpu_io
else
  record cgroup_v2_delegation fail user_unit_drop_in_not_active
fi

if command -v bwrap >/dev/null 2>&1; then
  bwrap_version=$(bwrap --version | awk '{print $2}')
  record bubblewrap pass "version_$bwrap_version"
else
  record bubblewrap fail not_installed
fi

if mkdir -p "$blob_root" 2>/dev/null; then
  source_file="$blob_root/.atomic-source-$$"
  target_file="$blob_root/.atomic-target-$$"
  if printf 'probe' >"$source_file" && ln "$source_file" "$target_file" 2>/dev/null; then
    record filesystem_atomic_finalize pass hardlink_supported
  else
    record filesystem_atomic_finalize fail hardlink_not_supported
  fi
  rm -f "$source_file" "$target_file"
else
  record filesystem_atomic_finalize fail blob_root_unavailable
fi

if [ -r /sys/module/apparmor/parameters/enabled ]; then
  read -r apparmor </sys/module/apparmor/parameters/enabled
  if [ "$apparmor" = "Y" ]; then
    record host_mac pass apparmor_enabled
  else
    record host_mac fail apparmor_disabled
  fi
elif command -v getenforce >/dev/null 2>&1; then
  selinux=$(getenforce)
  if [ "$selinux" = "Enforcing" ]; then
    record host_mac pass selinux_enforcing
  else
    record host_mac fail selinux_not_enforcing
  fi
else
  record host_mac pass no_host_mac_detected
fi

ready=false
execution_enabled=false
if [ "$failures" -eq 0 ]; then
  ready=true
  execution_enabled=true
fi

joined=$(IFS=,; printf '%s' "${checks[*]}")
printf '{\n  "schema_version": 1,\n  "ready": %s,\n  "execution_enabled": %s,\n  "checks": [%s]\n}\n' \
  "$ready" "$execution_enabled" "$joined" >"$output"
printf 'prerequisite report: %s (failures=%d, execution_enabled=%s)\n' "$output" "$failures" "$execution_enabled"
exit "$failures"
