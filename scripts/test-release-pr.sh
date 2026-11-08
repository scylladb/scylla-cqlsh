#!/usr/bin/env bash
# End-to-end check of scripts/release-pr.sh, in a throwaway repo with a bare remote and a fake gh.
# Run: ./scripts/test-release-pr.sh
set -euo pipefail
script=$(cd "$(dirname "$0")" && pwd)/release-pr.sh
t=$(mktemp -d)
trap 'rm -rf "$t"' EXIT
export GIT_AUTHOR_NAME=test GIT_AUTHOR_EMAIL=test@example.com GIT_COMMITTER_NAME=test GIT_COMMITTER_EMAIL=test@example.com

git init -q --bare -b master "$t/remote.git"
git clone -q "$t/remote.git" "$t/work" 2>/dev/null
cd "$t/work"
git switch -q -c master
git commit -q --allow-empty -m "initial"
git tag v6.1.0-scylla
git commit -q --allow-empty -m "cqlsh: a change"
git push -q origin master v6.1.0-scylla

# fake gh: open PR title in $t/pr_title, last merged release PR's merge commit in $t/merged
mkdir "$t/bin"
cat >"$t/bin/gh" <<EOF
#!/usr/bin/env bash
case "\$1 \$2" in
  "pr list") if [[ "\$*" == *merged* ]]; then cat "$t/merged" 2>/dev/null || true; elif [[ -f "$t/pr_title" ]]; then echo 1; fi ;;
  "pr create"|"pr edit") while [[ \$# -gt 0 ]]; do [[ \$1 == --title ]] && echo "\$2" >"$t/pr_title"; shift; done ;;
esac
EOF
chmod +x "$t/bin/gh"
export PATH="$t/bin:$PATH" GITHUB_REF_NAME=master GH_TOKEN=x BUMP=

run() { git switch -q master; "$script" >/dev/null; }
top_heading() { git show "$1:CHANGELOG.md" | sed -n 's/^## //p' | sed -n 1p; }
push_commit() { git switch -q master; git commit -q --allow-empty -m "$1"; git push -q origin master; }
# rebase-merge the release PR, then record it as the last merged release PR
merge_release() {
    git switch -q master; git merge -q --ff-only origin/release/master; git push -q origin master
    git rev-parse HEAD >"$t/merged"; rm "$t/pr_title"
}
remote_tag() { git -C "$t/remote.git" rev-parse -q --verify "refs/tags/$1" || true; }
check() { echo "ok: $1"; }

run
test "$(cat "$t/pr_title")" = "release: v6.1.1-scylla"
git -C "$t/remote.git" show release/master:CHANGELOG.md | grep -q "cqlsh: a change"
check "opens the release PR with the next patch and the changelog"

push_commit "release: v9.9.9-scylla"; run
test -z "$(remote_tag v9.9.9-scylla)"
check "a commit that only looks like a release tags nothing"

BUMP=minor run
push_commit "cqlsh: another change"; run
test "$(cat "$t/pr_title")" = "release: v6.2.0-scylla"
test "$(top_heading origin/release/master)" = "v6.2.0-scylla"
check "a minor bump from a manual run survives the next push"

echo "release: v9.0.0-scylla" >"$t/pr_title"; merge_release
release_sha=$(git rev-parse HEAD)
push_commit "cqlsh: after release"; run
test "$(remote_tag v6.2.0-scylla)" = "$release_sha"
test "$(top_heading "$release_sha")" = "v6.2.0-scylla"
test -z "$(remote_tag v9.0.0-scylla)"
test "$(cat "$t/pr_title")" = "release: v6.2.1-scylla"
check "a merge is tagged with its CHANGELOG version (title edits ignored), even when a later push superseded its run"

run
check "rerun is idempotent"

git tag v6.2.1-scylla "$(git rev-list --max-parents=0 HEAD)"; rm "$t/pr_title"
if run 2>/dev/null; then echo "expected a failure on a tag clash"; exit 1; fi
check "a version already tagged elsewhere fails the run"
