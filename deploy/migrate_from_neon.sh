#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
: "${NEON_DATABASE_URL:?Export the direct Neon connection URL (not the pooler URL)}"
if [[ "${SOURCE_WRITES_STOPPED:-}" != yes ]]; then
    echo 'Stop all writers on Neon, then set SOURCE_WRITES_STOPPED=yes.' >&2
    exit 1
fi
export NEON_DATABASE_URL

mkdir -p deploy/backups
exec 9>deploy/backups/.migration.lock
flock -n 9 || { echo 'Another migration is running.' >&2; exit 1; }
docker compose config --quiet
running=$(docker compose ps --status running --services)
if [[ "$running" =~ (^|$'\n')(django_web|telegram_worker|node_api)($|$'\n') ]]; then
    echo 'Stop django_web, telegram_worker and node_api before restoring.' >&2
    exit 1
fi
docker compose exec -T db sh -ec 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"'

target_psql() {
    docker compose exec -T db sh -ec '
        export PGPASSWORD="$POSTGRES_PASSWORD"
        exec psql -X --no-password -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 "$@"
    ' sh "$@"
}

objects=$(target_psql -Atc "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname NOT IN ('pg_catalog','information_schema') AND n.nspname NOT LIKE 'pg_toast%' AND c.relkind IN ('r','p','S','v','m','f');")
if [[ "$objects" != 0 ]]; then
    echo 'Target database is not empty; nothing was overwritten.' >&2
    exit 1
fi

# Use the PostgreSQL 16 client from db; newer source versions require a planned upgrade.
source_version=$(docker compose exec -T -e NEON_DATABASE_URL db sh -ec '
    exec psql -X --no-password --dbname="$NEON_DATABASE_URL" -Atc "SHOW server_version_num"
')
if [[ ! "$source_version" =~ ^[0-9]+$ ]] || (( source_version >= 170000 )); then
    echo 'Source must be PostgreSQL 16 or older; cross-major downgrades are not supported.' >&2
    exit 1
fi

dump=$(mktemp "deploy/backups/neon-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX.sql")
trap 'echo "Migration failed; keep Neon stopped until reviewed. Dump (possibly incomplete): $dump" >&2' ERR
echo "Saving complete schema and data to $dump"
docker compose exec -T -e NEON_DATABASE_URL db sh -ec '
    exec pg_dump --no-password --dbname="$NEON_DATABASE_URL" --format=plain --no-owner --no-acl --no-tablespaces
' >"$dump"
test -s "$dump"
sha256sum "$dump" >"$dump.sha256"

# Stop on the first SQL error and roll back the entire restore on failure.
target_psql --single-transaction --file=- <"$dump"
target_psql -c ANALYZE
trap - ERR
echo "Restore completed. Keep the dump and checksum: $dump"
echo 'Verify records and balances before starting the application and retiring Neon.'
