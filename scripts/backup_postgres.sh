#!/usr/bin/env bash
set -euo pipefail
umask 077

project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
destination=${1:-"$project_dir/backups/chinese-study-$(date +%Y%m%d-%H%M%S).dump"}
mkdir -p -- "$(dirname -- "$destination")"
partial=$(mktemp "$destination.partial.XXXXXX")
trap 'rm -f -- "$partial"' EXIT

docker compose --project-directory "$project_dir" -f "$project_dir/docker-compose.yml" exec -T postgres \
  sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom' \
  > "$partial"

# Publish only a complete dump and never replace an existing backup.
ln -- "$partial" "$destination"
printf 'Đã lưu bản sao PostgreSQL vào %s\n' "$destination"
