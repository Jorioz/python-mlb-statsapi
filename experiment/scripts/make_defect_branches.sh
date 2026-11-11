#!/usr/bin/env bash
# Create one branch per seeded defect from ci-experiment (clean v1.1.1 + CI
# configs), apply its patch and commit it. Pushing a defect/** branch triggers
# all four experiment workflows.
#
#   experiment/scripts/make_defect_branches.sh            # create branches only
#   experiment/scripts/make_defect_branches.sh --push     # also push to origin
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"
base=ci-experiment
push=${1:-}

for patch in experiment/defects/real/*.patch experiment/defects/mutants/M*.patch; do
  id=$(basename "$patch" .patch)
  id=${id%%-*}                       # RB1-a93b70e -> RB1
  branch="defect/$id"
  git switch -q -C "$branch" "$base"
  git apply "$patch"
  git commit -q -am "experiment: seed defect $id ($(basename "$patch"))"
  echo "created $branch"
  if [ "$push" = "--push" ]; then
    git push -q -f origin "$branch"
  fi
done
git switch -q "$base"
