#!/usr/bin/env bash
# Run by .github/workflows/release-pr.yml on each push to master / branch-*:
#  - tag the last merged release PR, if its tag doesn't exist yet
#  - open or update the rolling release PR for this branch
# needs: full history and tags, GH_TOKEN, GITHUB_REF_NAME; BUMP=patch|minor|major (default patch)
set -euo pipefail

base=${GITHUB_REF_NAME:?}
branch=release/$base
has_tag() { git rev-parse -q --verify "refs/tags/$1" >/dev/null; }
# the version is the top CHANGELOG.md heading of a release commit, so the tag always
# matches the notes that were merged (the PR title is informational only)
changelog_version() {
    git show "$1:CHANGELOG.md" 2>/dev/null | awk '/^## v[0-9]+\.[0-9]+\.[0-9]+-scylla$/ {print $2; exit}' || true
}

# The last merged PR from the bot's own release branch, looked up through the API rather
# than from HEAD: any merge style works, and a merge whose run was superseded by a later
# push still gets tagged.
sha=$(gh pr list --base "$base" --head "$branch" --state merged --limit 10 \
    --json mergeCommit,mergedAt,isCrossRepository \
    --jq '[.[] | select(.isCrossRepository | not)] | max_by(.mergedAt) // empty | .mergeCommit.oid')
tag=${sha:+$(changelog_version "$sha")}
if [[ -n $tag ]]; then
    if ! has_tag "$tag"; then
        git tag "$tag" "$sha"
        git push origin "$tag"
    elif [[ $(git rev-parse "$tag^{commit}") != "$sha" ]]; then
        echo "::warning::$tag already tags another commit, so $sha wasn't released"
    fi
fi

last=$(git describe --tags --abbrev=0 --match 'v*-scylla')
changes=$(git log "$last..HEAD" --no-merges --format='* %s (%h)')
if [[ -z $changes ]]; then
    echo "nothing to release since $last"
    exit 0
fi

IFS=. read -r major minor patch <<<"${last#v}"
patch=${patch%-scylla}
case ${BUMP:-patch} in
    major) next=v$((major + 1)).0.0-scylla ;;
    minor) next=v$major.$((minor + 1)).0-scylla ;;
    patch) next=v$major.$minor.$((patch + 1))-scylla ;;
    *) echo "bad BUMP: $BUMP" >&2; exit 1 ;;
esac

# a minor/major bump from an earlier manual run survives the next push; an explicit BUMP replaces it
open_pr=$(gh pr list --head "$branch" --base "$base" --state open --json number,isCrossRepository \
    --jq '[.[] | select(.isCrossRepository | not)][0].number // ""')
if [[ -z ${BUMP:-} && -n $open_pr ]]; then
    git fetch -q origin "+refs/heads/$branch:refs/remotes/origin/$branch" || true
    kept=$(changelog_version "origin/$branch")
    if [[ -n $kept ]] && ! has_tag "$kept"; then next=$kept; fi
fi
# tags are repo-wide: a branch-* cut from master without a new minor proposes the same patch
if has_tag "$next"; then
    echo "::error::$next is already tagged on another branch; run the Release PR workflow with a minor bump"
    exit 1
fi

git switch -q -C "$branch"
{
    printf '## %s\n\n%s\n\n' "$next" "$changes"
    if [[ -f CHANGELOG.md ]]; then cat CHANGELOG.md; fi
} >CHANGELOG.md.new
mv CHANGELOG.md.new CHANGELOG.md
git add CHANGELOG.md
git -c user.name='scylla-cqlsh release' -c user.email='noreply@scylladb.com' commit -q -m "release: $next"
git push -q -f origin "$branch"

body="Merging this PR tags \`$next\` on \`$base\`, which publishes it (GitHub release, PyPI, Docker).

This PR is regenerated on every push to \`$base\`. The version is the top heading of \`CHANGELOG.md\`; editing the title doesn't change it. To release a minor or major version, run the *Release PR* workflow with that bump.

## Changes since $last

$changes"

if [[ -n $open_pr ]]; then
    gh pr edit "$branch" --title "release: $next" --body "$body"
else
    gh pr create --base "$base" --head "$branch" --title "release: $next" --body "$body"
fi
