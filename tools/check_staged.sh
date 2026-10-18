#!/usr/bin/env bash
# Scan the STAGED version of site sources (not the working tree) with check_public.py.
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel)"
cd "${ROOT}"

TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

N=0
while IFS= read -r -d '' path; do
  mkdir -p "${TMP}/$(dirname -- "${path}")"
  git show ":${path}" > "${TMP}/${path}"
  N=$((N + 1))
done < <(git diff --cached --name-only -z --diff-filter=ACMRT -- content data layouts i18n static assets hugo.toml README.md BACKLOG.md .github .hugo-version)

[ "${N}" -gt 0 ] || exit 0

ARGS=()
if [ -f "${ROOT}/.denylist" ]; then
  ARGS=(--denylist "${ROOT}/.denylist")
else
  echo "WARNING: denylist not found, name check skipped (copy .denylist.example to .denylist)" >&2
fi
cd "${TMP}"
python3 -I "${ROOT}/tools/check_public.py" "${ARGS[@]}" .
