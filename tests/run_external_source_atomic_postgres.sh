#!/usr/bin/env bash
set -euo pipefail

if ! command -v docker >/dev/null 2>&1; then
  echo "SKIP: docker is required for the disposable PostgreSQL integration test" >&2
  exit 77
fi

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
container_name="fl-signal-atomic-${RANDOM}-$$"

cleanup() {
  docker rm -f "$container_name" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

docker run --detach --name "$container_name" \
  --env POSTGRES_PASSWORD=fl_signal_disposable_test \
  --env POSTGRES_DB=fl_signal_atomic_test \
  postgres:17-alpine >/dev/null

for _ in $(seq 1 30); do
  if docker exec "$container_name" pg_isready -U postgres -d fl_signal_atomic_test >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

docker exec "$container_name" pg_isready -U postgres -d fl_signal_atomic_test >/dev/null
docker exec -i "$container_name" psql -v ON_ERROR_STOP=1 -U postgres -d fl_signal_atomic_test \
  < "$repo_dir/tests/sql/external_source_atomic_fixture.sql"
docker exec -i "$container_name" psql -v ON_ERROR_STOP=1 -U postgres -d fl_signal_atomic_test \
  < "$repo_dir/supabase/migrations/20260901012400_external_source_atomic_commit.sql"
docker exec -i "$container_name" psql -v ON_ERROR_STOP=1 -U postgres -d fl_signal_atomic_test \
  < "$repo_dir/tests/sql/external_source_atomic_assertions.sql"
docker exec -i "$container_name" psql -v ON_ERROR_STOP=1 -U postgres -d fl_signal_atomic_test \
  < "$repo_dir/supabase/migrations/20260901012500_external_source_collector_cron_cutover.sql"
docker exec -i "$container_name" psql -v ON_ERROR_STOP=1 -U postgres -d fl_signal_atomic_test \
  < "$repo_dir/tests/sql/external_source_schedule_assertions.sql"
