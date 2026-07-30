#!/usr/bin/env bash
set -euo pipefail

bundle_dir="${1:-$(pwd)}"
env_file="${2:?usage: install-offline.sh BUNDLE_DIRECTORY ENV_FILE}"
bundle_dir="$(realpath "$bundle_dir")"
env_file="$(realpath "$env_file")"
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
gpu_count="$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | wc -l)"
test "$gpu_count" -eq 1 || {
  echo "Scenara 1.0 requires exactly one NVIDIA GPU" >&2
  exit 2
}
gpu_memory="$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits)"
test "$gpu_memory" -ge 23000 || {
  echo "Scenara 1.0 requires a 24 GB NVIDIA GPU" >&2
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
printf 'offline_install=passed\nconsole_url=http://127.0.0.1:8000/console/\n'
