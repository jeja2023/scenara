#!/usr/bin/env bash
set -euo pipefail

bundle_dir="${1:-$(pwd)}"
env_file="${2:?usage: install-offline.sh BUNDLE_DIRECTORY ENV_FILE [RESULT_JSON]}"
result_file="${3:-}"
bundle_dir="$(realpath "$bundle_dir")"
env_file="$(realpath "$env_file")"
if [ -n "$result_file" ]; then
  result_file="$(realpath -m "$result_file")"
  test -d "$(dirname "$result_file")"
  test ! -e "$result_file" || {
    echo "refusing to overwrite existing result: $result_file" >&2
    exit 2
  }
fi
test -f "$bundle_dir/SHA256SUMS"
(
  cd "$bundle_dir"
  sha256sum --check SHA256SUMS
)
command -v docker >/dev/null
docker compose version >/dev/null
command -v nvidia-smi >/dev/null

version_ge() {
  test "$(printf '%s\n' "$2" "$1" | sort -V | head -n 1)" = "$2"
}

test "$(uname -s)" = "Linux" && test "$(uname -m)" = "x86_64" || {
  echo "Scenara 1.0 requires Linux x86_64" >&2
  exit 2
}
. /etc/os-release
test "${ID:-}" = "ubuntu" && test "${VERSION_ID:-}" = "24.04" || {
  echo "Scenara 1.0 requires Ubuntu 24.04" >&2
  exit 2
}
docker_version="$(docker version --format '{{.Server.Version}}')"
compose_version="$(docker compose version --short)"
version_ge "$docker_version" "27.0.0" || {
  echo "Scenara 1.0 requires Docker Engine 27 or newer" >&2
  exit 2
}
version_ge "$compose_version" "2.29.0" || {
  echo "Scenara 1.0 requires Docker Compose 2.29 or newer" >&2
  exit 2
}
gpu_count="$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | awk 'NF { count += 1 } END { print count + 0 }')"
test "$gpu_count" -gt 0 || {
  echo "Scenara 1.0 requires at least one measurable NVIDIA GPU" >&2
  exit 2
}
gpu_memory="$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | awk 'NF { total += $1 } END { print total + 0 }')"
test "$gpu_memory" -gt 0 || {
  echo "Scenara 1.0 requires measurable NVIDIA GPU memory" >&2
  exit 2
}
cuda_version="$(nvidia-smi | sed -n 's/.*CUDA Version: \([0-9.]*\).*/\1/p' | head -n 1)"
test -n "$cuda_version" && version_ge "$cuda_version" "12.8" || {
  echo "Scenara 1.0 requires an NVIDIA driver compatible with CUDA 12.8" >&2
  exit 2
}
docker load --input "$bundle_dir/images/scenara-images.tar"
compose=(docker compose --env-file "$env_file" -f "$bundle_dir/deploy/compose.yml")
"${compose[@]}" config --quiet
"${compose[@]}" up -d --no-build --wait
curl --fail --silent --show-error http://127.0.0.1:8000/readyz >/dev/null
curl --fail --silent --show-error http://127.0.0.1:8000/console/ | grep -q "Scenara 景枢"
for service in api batch-worker stream-worker scheduler postgres redis minio; do
  "${compose[@]}" ps --status running --services | grep -qx "$service" || {
    echo "Scenara service is not running: $service" >&2
    exit 2
  }
done
if [ -n "$result_file" ]; then
  umask 077
  temporary_result="$result_file.tmp.$$"
  trap 'rm -f "$temporary_result"' EXIT
  printf '%s\n' \
    '{' \
    '  "schema_version": "1.0",' \
    '  "evidence_type": "offline_install",' \
    '  "installer_exit_code": 0,' \
    '  "checksums_verified": true,' \
    '  "host": {' \
    '    "host_os": "ubuntu",' \
    '    "host_version": "24.04",' \
    "    \"gpu_count\": $gpu_count," \
    "    \"gpu_memory_mib\": $gpu_memory" \
    '  },' \
    '  "services": {' \
    '    "api": "running",' \
    '    "batch-worker": "running",' \
    '    "stream-worker": "running",' \
    '    "scheduler": "running",' \
    '    "postgres": "running",' \
    '    "redis": "running",' \
    '    "minio": "running"' \
    '  },' \
    '  "installer_checks": {' \
    '    "health": "passed",' \
    '    "console": "passed"' \
    '  }' \
    '}' > "$temporary_result"
  mv "$temporary_result" "$result_file"
  trap - EXIT
fi
printf 'offline_install=passed\ngpu_count=%s\ngpu_memory_mib=%s\nchecksums_verified=passed\ncheck.health=passed\ncheck.console=passed\n' "$gpu_count" "$gpu_memory"
for service in api batch-worker stream-worker scheduler postgres redis minio; do
  printf 'service.%s=running\n' "$service"
done
printf 'console_url=http://127.0.0.1:8000/console/\n'
