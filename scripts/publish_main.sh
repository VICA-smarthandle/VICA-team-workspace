#!/usr/bin/env bash
# dev 원고를 재료로 main 인쇄본(주석 제거본)을 굽는다.
#
# 사용법: publish_main.sh <main 이 체크아웃된 저장소 경로> [dev-ref] [--dart] [--manifest]
#   dev-ref     기본 origin/dev
#   --dart      지운 뒤 dart format lib test 를 돌린다 (Flutter 저장소)
#   --manifest  workspace.repos 의 version: dev 를 main 으로 바꾼다 (루트 저장소)
#
# 방식: main 에 dev 를 -s ours 로 머지(부모 기록만 남김)한 뒤 트리를 dev 것으로 갈아끼우고
# 주석을 지워 커밋한다. force push 가 필요 없고, 다음 번에도 충돌 없이 같은 절차를 반복한다.
# COMMIT_TRAILER 환경변수가 있으면 커밋 메시지 끝에 붙인다.
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
