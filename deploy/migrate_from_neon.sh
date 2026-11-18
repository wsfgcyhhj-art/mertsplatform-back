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

# PostgreSQL 18 clients can read Neon 16/17/18; restore uses the local PostgreSQL 17 db.
source_version=$(docker run --rm -e NEON_DATABASE_URL postgres:18-alpine sh -ec '
    exec psql -X --no-password --dbname="$NEON_DATABASE_URL" -Atc "SHOW server_version_num"
')
if [[ ! "$source_version" =~ ^[0-9]+$ ]] || (( source_version >= 190000 )); then
    echo 'Source must be PostgreSQL 18 or older.' >&2
    exit 1
fi

dump=$(mktemp "deploy/backups/neon-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX.sql")
trap 'echo "Migration failed; keep Neon stopped until reviewed. Dump (possibly incomplete): $dump" >&2' ERR
echo "Saving complete schema and data to $dump"
docker run --rm -e NEON_DATABASE_URL postgres:18-alpine sh -ec '
    exec pg_dump --no-password --dbname="$NEON_DATABASE_URL" --format=plain --no-owner --no-acl --no-tablespaces --quote-all-identifiers
' >"$dump"
test -s "$dump"

# Filter pg_dump metadata only: preserve COPY data and function bodies verbatim.
awk '
    BEGIN { header = 1; acl = 1 }
    copy { print; if ($0 == "\\.") copy = 0; next }
    /^COPY .* FROM stdin;$/ { copy = 1; print; next }
    /^-- Name: .*; Type: / { header = 0; acl = ($0 ~ /; Type: (DEFAULT ACL|ACL);/) }
    header && /^SET transaction_timeout[[:space:]]*=/ { next }
    acl && /^(ALTER DEFAULT PRIVILEGES FOR ROLE|GRANT|REVOKE)[[:space:]]/ {
        statement = $0
        while (statement !~ /;[[:space:]]*$/ && (getline line) > 0)
            statement = statement "\n" line
        sql = statement
        gsub(/[[:space:]]+/, " ", sql)
        if (sql ~ /^ALTER DEFAULT PRIVILEGES FOR ROLE "?neon[[:alnum:]_]*"? / ||
            sql ~ /^GRANT .* TO "?neon[[:alnum:]_]*"?([,; ]|$)/ ||
            sql ~ /^REVOKE .* FROM "?neon[[:alnum:]_]*"?([,; ]|$)/) next
        print statement
        next
    }
    { print }
' "$dump" >"$dump.restore"
sha256sum "$dump" "$dump.restore" >"$dump.sha256"

# Stop on the first SQL error and roll back the entire restore on failure.
target_psql --single-transaction --file=- <"$dump.restore"
target_psql -c ANALYZE
trap - ERR
echo "Restore completed. Keep the dump and checksum: $dump"
echo 'Verify records and balances before starting the application and retiring Neon.'
