#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
container_name="fl-signal-atomic-${RANDOM}-$$"
test_mode=""
local_cluster_root=""
local_socket_dir=""
local_port=""
local_database=""
postgres_bin=""
pg_ctl_bin=""
initdb_bin=""
createdb_bin=""
psql_bin=""
local_pg_version=""

find_pg_tool() {
  local tool="$1"
  local pg_bindir=""
  if command -v "$tool" >/dev/null 2>&1; then
    command -v "$tool"
    return 0
  fi
  if command -v pg_config >/dev/null 2>&1; then
    pg_bindir="$(pg_config --bindir)"
    if test -x "$pg_bindir/$tool"; then
      printf '%s\n' "$pg_bindir/$tool"
      return 0
    fi
  fi
  return 1
}

cleanup() {
  local exit_status=$?
  trap - EXIT HUP INT TERM
  if test "$test_mode" = "docker"; then
    docker rm -f "$container_name" >/dev/null 2>&1 || true
  elif test "$test_mode" = "local" && test -n "$local_cluster_root"; then
    if test -n "$pg_ctl_bin" && test -d "$local_cluster_root/data"; then
      "$pg_ctl_bin" -D "$local_cluster_root/data" -m immediate -w stop >/dev/null 2>&1 || true
    fi
    case "$local_cluster_root" in
      "${TMPDIR:-/tmp}"/fl-signal-atomic-pg.*)
        rm -rf -- "$local_cluster_root"
        ;;
      *)
        echo "REFUSE: unexpected local PostgreSQL cleanup path: $local_cluster_root" >&2
        ;;
    esac
  fi
  exit "$exit_status"
}
trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

run_psql() {
  case "$test_mode" in
    docker)
      docker exec -i "$container_name" psql \
        -X --no-password -v ON_ERROR_STOP=1 -U postgres -d fl_signal_atomic_test "$@"
      ;;
    local)
      PGHOST="$local_socket_dir" PGPORT="$local_port" PGUSER=postgres \
        PGDATABASE="$local_database" "$psql_bin" \
        -X --no-password -v ON_ERROR_STOP=1 "$@"
      ;;
    dsn)
      PGCONNECT_TIMEOUT=5 PGDATABASE="$FL_SIGNAL_TEST_DATABASE_URL" "$psql_bin" \
        -X --no-password -v ON_ERROR_STOP=1 "$@"
      ;;
    *)
      echo "REFUSE: no disposable PostgreSQL test mode is configured" >&2
      return 70
      ;;
  esac
}

assert_disposable_target() {
  local safety_row=""
  local database_name=""
  local server_version_num=""
  local is_superuser=""
  local in_recovery=""
  local custom_schema_count=""
  local user_relation_count=""

  safety_row="$(run_psql -At -F '|' -c "
    select
      current_database(),
      current_setting('server_version_num'),
      current_setting('is_superuser'),
      pg_catalog.pg_is_in_recovery(),
      (
        select count(*)
        from pg_catalog.pg_namespace
        where nspname <> 'public'
          and nspname <> 'information_schema'
          and nspname !~ '^pg_'
      ),
      (
        select count(*)
        from pg_catalog.pg_class c
        join pg_catalog.pg_namespace n on n.oid = c.relnamespace
        where n.nspname = 'public'
          and c.relkind in ('r', 'p', 'v', 'm', 'S', 'f')
      );
  ")"
  IFS='|' read -r database_name server_version_num is_superuser in_recovery \
    custom_schema_count user_relation_count <<<"$safety_row"

  if [[ ! "$database_name" =~ ^fl_signal_atomic_test([_-][A-Za-z0-9_-]+)?$ ]]; then
    echo "REFUSE: disposable database name must begin with fl_signal_atomic_test" >&2
    return 64
  fi
  if (( server_version_num < 170000 || server_version_num >= 180000 )); then
    echo "REFUSE: disposable integration test requires PostgreSQL 17" >&2
    return 65
  fi
  if test "$is_superuser" != "on" || test "$in_recovery" != "f"; then
    echo "REFUSE: target must be a writable superuser-owned disposable PostgreSQL database" >&2
    return 66
  fi
  if test "$custom_schema_count" != "0" || test "$user_relation_count" != "0"; then
    echo "REFUSE: target is not an empty disposable PostgreSQL database" >&2
    return 67
  fi
}

if test -n "${FL_SIGNAL_TEST_DATABASE_URL:-}"; then
  if test "${FL_SIGNAL_DISPOSABLE_TEST_CONFIRM:-}" != "YES"; then
    echo "REFUSE: set FL_SIGNAL_DISPOSABLE_TEST_CONFIRM=YES only for an expendable test database" >&2
    exit 64
  fi
  case "$FL_SIGNAL_TEST_DATABASE_URL" in
    *supabase.co*|*supabase.com*|*pooler.supabase*)
      echo "REFUSE: hosted/linked Supabase endpoints are never valid disposable test targets" >&2
      exit 64
      ;;
  esac
  psql_bin="$(find_pg_tool psql || true)"
  if test -z "$psql_bin"; then
    echo "SKIP: psql is required for FL_SIGNAL_TEST_DATABASE_URL" >&2
    exit 77
  fi
  test_mode="dsn"
  assert_disposable_target
elif command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  test_mode="docker"
  docker run --detach --name "$container_name" \
    --env POSTGRES_PASSWORD=fl_signal_disposable_test \
    --env POSTGRES_DB=fl_signal_atomic_test \
    postgres:17-alpine >/dev/null

  for _ in $(seq 1 30); do
    if docker exec "$container_name" pg_isready \
      -U postgres -d fl_signal_atomic_test >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done
  docker exec "$container_name" pg_isready \
    -U postgres -d fl_signal_atomic_test >/dev/null
  assert_disposable_target
else
  postgres_bin="$(find_pg_tool postgres || true)"
  pg_ctl_bin="$(find_pg_tool pg_ctl || true)"
  initdb_bin="$(find_pg_tool initdb || true)"
  createdb_bin="$(find_pg_tool createdb || true)"
  psql_bin="$(find_pg_tool psql || true)"
  if test -z "$postgres_bin" || test -z "$pg_ctl_bin" \
     || test -z "$initdb_bin" || test -z "$createdb_bin" \
     || test -z "$psql_bin"; then
    echo "SKIP: Docker, PostgreSQL 17 tools, or FL_SIGNAL_TEST_DATABASE_URL are required" >&2
    exit 77
  fi
  local_pg_version="$($postgres_bin --version)"
  case "$local_pg_version" in
    *"PostgreSQL) 17."*|*"PostgreSQL 17."*) ;;
    *)
      echo "SKIP: locally managed fallback requires PostgreSQL 17 tools" >&2
      exit 77
      ;;
  esac

  test_mode="local"
  local_cluster_root="$(mktemp -d "${TMPDIR:-/tmp}/fl-signal-atomic-pg.XXXXXX")"
  local_socket_dir="$local_cluster_root/socket"
  local_port="$((55000 + RANDOM % 1000))"
  local_database="fl_signal_atomic_test_local_$$"
  mkdir -m 700 "$local_socket_dir"
  "$initdb_bin" -D "$local_cluster_root/data" --username=postgres \
    --auth=trust --encoding=UTF8 --no-locale >/dev/null
  "$pg_ctl_bin" -D "$local_cluster_root/data" \
    -o "-F -p $local_port -k $local_socket_dir -h ''" \
    -w start >/dev/null
  PGHOST="$local_socket_dir" PGPORT="$local_port" PGUSER=postgres \
    PGDATABASE=postgres "$createdb_bin" "$local_database"
  assert_disposable_target
fi

run_psql < "$repo_dir/tests/sql/external_source_atomic_fixture.sql"
run_psql < "$repo_dir/supabase/migrations/20260901012400_external_source_atomic_commit.sql"
run_psql < "$repo_dir/tests/sql/external_source_atomic_assertions.sql"
run_psql < "$repo_dir/supabase/migrations/20260901012500_external_source_collector_cron_cutover.sql"
run_psql < "$repo_dir/tests/sql/external_source_schedule_assertions.sql"
