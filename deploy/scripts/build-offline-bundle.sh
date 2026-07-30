#!/usr/bin/env bash
set -euo pipefail

output_dir="${1:?usage: build-offline-bundle.sh OUTPUT_DIRECTORY}"
output_dir="$(realpath -m "$output_dir")"
test "$output_dir" != "/"
tag="${SCENARA_IMAGE_TAG:-0.2.0-dev.0}"
[[ "$tag" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$ ]] || {
  echo "SCENARA_IMAGE_TAG contains unsupported characters" >&2
  exit 2
}
env_file="${SCENARA_COMPOSE_ENV_FILE:?set SCENARA_COMPOSE_ENV_FILE}"
model_bundle_dir="$(realpath "${SCENARA_MODEL_BUNDLE_DIR:?set SCENARA_MODEL_BUNDLE_DIR to the approved model package directory}")"
test -d "$model_bundle_dir"
find "$model_bundle_dir" -type f -print -quit | grep -q . || {
  echo "the approved model package directory is empty" >&2
  exit 2
}
repo_root="$(realpath "$(dirname "$0")/../..")"
compose_file="$repo_root/deploy/compose.yml"
staging="$output_dir/scenara-offline-$tag"
rm -rf "$staging"
mkdir -p "$staging/images" "$staging/wheels" "$staging/deploy" "$staging/models"

compose=(docker compose --env-file "$env_file" -f "$compose_file")
"${compose[@]}" config --quiet
"${compose[@]}" build api
mapfile -t images < <("${compose[@]}" config --images | sort -u)
for image in "${images[@]}"; do
  docker image inspect "$image" >/dev/null
done
for image in "${images[@]}"; do
  docker image inspect --format '{{.Id}} {{json .RepoDigests}}' "$image" | sed "s|^|$image |"
done > "$staging/container-images.txt"
docker save --output "$staging/images/scenara-images.tar" "${images[@]}"
python3 -m pip download \
  --dest "$staging/wheels" \
  --require-hashes \
  -r "$repo_root/requirements/production.lock"

cp "$compose_file" "$staging/deploy/compose.yml"
cp -R "$repo_root/deploy/scripts" "$staging/deploy/scripts"
cp -R "$repo_root/migrations" "$staging/migrations"
cp -R "$repo_root/examples/demo-clients" "$staging/examples"
cp -R "$repo_root/sdk" "$staging/sdk"
cp -R "$model_bundle_dir/." "$staging/models/"
(
  cd "$staging/models"
  find . -type f -print0 | sort -z | xargs -0 sha256sum > "$staging/model-SHA256SUMS"
)
cp "$repo_root/LICENSE" "$repo_root/NOTICE" "$repo_root/THIRD_PARTY_NOTICES.md" "$staging/"
cp "$repo_root/MODEL_ASSETS.md" "$repo_root/source-manifest.json" "$staging/"
date -u +%Y-%m-%dT%H:%M:%SZ > "$staging/created-at.txt"
source_commit="$(git -C "$repo_root" rev-parse HEAD)"
printf '%s\n' "$source_commit" > "$staging/source-commit.txt"
(
  cd "$staging"
  find . -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS
)
archive="$output_dir/scenara-offline-$tag.tar.gz"
tar -C "$output_dir" -czf "$archive" "scenara-offline-$tag"
image_digest="$(docker image inspect --format '{{.Id}}' "scenara-api:$tag")"
offline_bundle_sha256="$(sha256sum "$archive" | awk '{print $1}')"
openapi_sha256="$(sha256sum "$repo_root/docs/openapi.json" | awk '{print $1}')"
model_set_sha256="$(sha256sum "$staging/model-SHA256SUMS" | awk '{print $1}')"
cat > "$output_dir/scenara-offline-$tag.release-identity.json" <<EOF
{
  "source_commit": "$source_commit",
  "image_digest": "$image_digest",
  "offline_bundle_sha256": "$offline_bundle_sha256",
  "openapi_sha256": "$openapi_sha256",
  "model_set_sha256": "$model_set_sha256"
}
EOF
