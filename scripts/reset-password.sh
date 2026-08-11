#!/usr/bin/env bash
set -euo pipefail

printf 'New shared password: ' >&2
read -r -s password
printf '\n'
printf 'Confirm new shared password: ' >&2
read -r -s confirmation
printf '\n'

if [[ "$password" != "$confirmation" ]]; then
  printf 'Passwords do not match.\n' >&2
  exit 1
fi

printf '%s\n%s\n' "$password" "$confirmation" | docker compose exec -T app buildable reset-password --stdin
