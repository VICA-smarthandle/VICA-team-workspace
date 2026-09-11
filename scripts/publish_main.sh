#!/usr/bin/env bash
set -euo pipefail

REPO=${1:?사용법: publish_main.sh <저장소> [dev-ref] [--dart] [--manifest]}
DEV=${2:-origin/dev}
shift $(( $# >= 2 ? 2 : $# ))
DART=0
MANIFEST=0
for arg in "$@"; do
  case "$arg" in
    --dart) DART=1 ;;
    --manifest) MANIFEST=1 ;;
    *) echo "모르는 옵션: $arg" >&2; exit 2 ;;
  esac
done

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
cd "$REPO"
[ "$(git branch --show-current)" = main ] || { echo "main 이 체크아웃돼 있어야 한다: $REPO" >&2; exit 2; }
[ -z "$(git status --porcelain)" ] || { echo "작업 트리가 깨끗해야 한다: $REPO" >&2; exit 2; }
DEV_SHA=$(git rev-parse --short "$DEV")
if git merge-base --is-ancestor "$DEV" HEAD; then
  echo "main 이 이미 $DEV($DEV_SHA) 를 담고 있다. 할 일 없음."
  exit 0
fi

git merge -s ours --no-ff --no-commit "$DEV" >/dev/null
git rm -r -q .
git checkout -q "$DEV" -- .
python3 "$HERE/strip_comments.py" --root .
if [ "$DART" = 1 ]; then
  [ -f .dart_tool/package_config.json ] || flutter pub get >/dev/null
  dart format lib test >/dev/null
fi
if [ "$MANIFEST" = 1 ] && [ -f workspace.repos ]; then
  sed -i -E 's/^([[:space:]]*version:[[:space:]]*)dev[[:space:]]*$/\1main/' workspace.repos
fi
git add -A
MSG="chore(main): dev ${DEV_SHA} 스냅샷 — 주석 제거본"
if [ -n "${COMMIT_TRAILER:-}" ]; then
  MSG="$MSG"$'\n\n'"$COMMIT_TRAILER"
fi
git commit -q -m "$MSG"
echo "main ← $DEV($DEV_SHA) 스냅샷 커밋: $(git rev-parse --short HEAD)"
