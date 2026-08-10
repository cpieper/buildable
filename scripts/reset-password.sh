#!/usr/bin/env bash
set -euo pipefail

read -r -s "password?New shared password: "
printf '\n'
read -r -s "confirmation?Confirm new shared password: "
printf '\n'

if [[ "$password" != "$confirmation" ]]; then
  printf 'Passwords do not match.\n' >&2
  exit 1
fi

printf '%s\n%s\n' "$password" "$confirmation" | docker compose exec -T app what2build reset-password --stdin
