#!/usr/bin/env bash
set -euo pipefail

workspace_root="${1:-${SCENARA_WORKSPACE_ROOT:-$(cd "$(dirname "$0")/../../.." && pwd)}}"
workspace_root="$(realpath "$workspace_root")"
core_root="$workspace_root/scenara"
data_root="$workspace_root/scenara-data"
model_root="$workspace_root/scenara-model"

for root in "$core_root" "$data_root" "$model_root"; do
  test -d "$root/.git" || {
    echo "missing git repository: $root" >&2
    exit 2
  }
done

docker_cmd=(docker)
if ! docker info >/dev/null 2>&1; then
  docker_cmd=(sudo docker)
fi

core_sha="$(git -C "$core_root" rev-parse HEAD)"
data_sha="$(git -C "$data_root" rev-parse HEAD)"
model_sha="$(git -C "$model_root" rev-parse HEAD)"

core_image="scenara-api:$core_sha"
data_image="scenara-data:$data_sha"
model_image="scenara-model:$model_sha"

"${docker_cmd[@]}" build -f "$data_root/deploy/Dockerfile" -t "$data_image" "$data_root"
"${docker_cmd[@]}" build -f "$core_root/Dockerfile" -t "$core_image" "$core_root"
"${docker_cmd[@]}" build --build-arg SCENARA_MODEL_EXTRAS=postgres,s3 -f "$model_root/Dockerfile" -t "$model_image" "$model_root"

cat <<EOF

Local production image references:
SCENARA_LOCAL_IMAGE_MODE=true
SCENARA_IMAGE_REFERENCE=$core_image
SCENARA_DATA_IMAGE=$data_image
SCENARA_MODEL_IMAGE=$model_image
EOF
