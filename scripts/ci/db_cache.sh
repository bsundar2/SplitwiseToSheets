#!/usr/bin/env bash
# Encrypts / decrypts the SQLite mirror around the GitHub Actions cache.
#
# The database holds the full Splitwise history, and this repo is public:
# a workflow run from a fork's pull request can restore caches saved on
# main. So only data/transactions.db.enc is ever cached, encrypted with the
# DB_CACHE_KEY repo secret, which fork pull requests never receive.
#
#   scripts/ci/db_cache.sh decrypt   # after restoring the cache
#   scripts/ci/db_cache.sh encrypt   # before saving it
set -euo pipefail

DB=data/transactions.db
ENC=data/transactions.db.enc

if [ -z "${DB_CACHE_KEY:-}" ]; then
  echo "::error::The DB_CACHE_KEY secret is not set. Add it under Settings > Secrets and variables > Actions (any long random string, e.g. from 'openssl rand -base64 32')." >&2
  exit 1
fi

openssl_args=(-aes-256-cbc -pbkdf2 -iter 200000 -pass env:DB_CACHE_KEY)

case "${1:-}" in
  decrypt)
    if [ -f "$ENC" ]; then
      # Decrypt to a temp file so a wrong key can't leave a partial
      # database behind for the always() encrypt step to cache over the
      # good copy.
      if ! openssl enc -d "${openssl_args[@]}" -in "$ENC" -out "$DB.tmp"; then
        rm -f "$DB.tmp"
        echo "::error::Couldn't decrypt the cached database. Did DB_CACHE_KEY change?" >&2
        exit 1
      fi
      mv "$DB.tmp" "$DB"
      rm -f "$ENC"
      echo "Restored the cached database."
    else
      echo "No cached database; starting from an empty one."
    fi
    ;;
  encrypt)
    if [ -f "$DB" ]; then
      openssl enc -salt "${openssl_args[@]}" -in "$DB" -out "$ENC"
      echo "Encrypted the database for caching."
    else
      echo "No database to cache."
    fi
    ;;
  *)
    echo "usage: $0 decrypt|encrypt" >&2
    exit 2
    ;;
esac
