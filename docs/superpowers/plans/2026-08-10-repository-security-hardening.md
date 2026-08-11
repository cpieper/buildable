# Repository Security Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Protect Buildable's `main` branch with mandatory pull requests, verified signed commits, required CI/security checks, least-privilege Actions, and GitHub dependency/secret-scanning controls.

**Architecture:** Land immutable, least-privilege GitHub workflows and repository policy files before enabling enforcement. After those workflows pass on GitHub, configure repository-wide security and merge settings, create a no-bypass branch ruleset using the observed check names, and smoke-test that ruleset on a disposable branch before narrowing it to `main` alone.

**Tech Stack:** GitHub Actions, GitHub repository rulesets and REST API, CodeQL, Dependabot, uv/Python 3.12, npm/Node.js 22, Ruff, pytest, Vitest, Svelte Check, GPG-signed Git commits.

## Global Constraints

- Every change to `main`, including changes from `@cpieper`, must use a pull request.
- Pull requests require zero approving reviews because this repository has one maintainer.
- All review conversations must be resolved before merge.
- Commits newly introduced to `main` must have GitHub-verified signatures; existing history is not rewritten.
- `main` cannot be force-pushed or deleted, and the ruleset has no bypass actors.
- Required status checks are strict: the pull-request branch must be current with `main`.
- Allow merge commits and squash merges; disable rebase merges.
- Keep workflow tokens read-only by default and unable to approve pull requests.
- Pin every external action to a full 40-character commit SHA.
- Allow only GitHub-owned actions and `astral-sh/setup-uv`.
- Dependabot may open pull requests but must never auto-merge them.
- If a GitHub feature is unavailable to this public personal repository, report and skip it rather than replacing it with a weaker control.
- All local commits created by this implementation must use `git commit -S` and verify as good signatures before push.

---

## File Structure

- `.github/CODEOWNERS`: documents `@cpieper` as owner for every path without requiring self-approval.
- `.github/pull_request_template.md`: prompts for change, validation, security, and operational context.
- `.github/dependabot.yml`: schedules grouped uv, npm, Docker, and Actions updates.
- `.github/workflows/ci.yml`: required backend and frontend project validation.
- `.github/workflows/security.yml`: required dependency review and CodeQL analysis.
- `SECURITY.md`: directs vulnerability reports to GitHub private vulnerability reporting.
- `.superpowers/protect-main-ruleset.json`: temporary ignored API payload used only while creating and verifying the ruleset; remove it before completion.

## Immutable Action Versions

- `actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1` (`v7.0.1`)
- `actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97` (`v7.0.0`)
- `actions/setup-node@820762786026740c76f36085b0efc47a31fe5020` (`v7.0.0`)
- `astral-sh/setup-uv@c771a70e6277c0a99b617c7a806ffedaca235ff9` (`v9.0.0`)
- `actions/dependency-review-action@a1d282b36b6f3519aa1f3fc636f609c47dddb294` (`v5.0.0`)
- `github/codeql-action/init@18420e3271f74589575af831a523c833acda327f` (`codeql-bundle-v2.26.2`)
- `github/codeql-action/analyze@18420e3271f74589575af831a523c833acda327f` (`codeql-bundle-v2.26.2`)

### Task 1: Add Repository Policy and Dependency Automation

**Files:**
- Create: `.github/CODEOWNERS`
- Create: `.github/pull_request_template.md`
- Create: `.github/dependabot.yml`
- Create: `SECURITY.md`

**Interfaces:**
- Consumes: the personal repository owner `cpieper` and GitHub private vulnerability reporting.
- Produces: repository ownership metadata, PR prompts, vulnerability-reporting instructions, and weekly dependency-update PRs consumed by the protected PR workflow.

- [ ] **Step 1: Create the ownership and PR policy files**

Create `.github/CODEOWNERS`:

```text
# Buildable has one maintainer. Approval is not required while the owner is also the PR author.
* @cpieper
```

Create `.github/pull_request_template.md`:

```markdown
## Summary

<!-- What changed, and why? -->

## Validation

- [ ] Backend tests and checks pass, or are not applicable.
- [ ] Frontend tests, checks, and build pass, or are not applicable.
- [ ] I reviewed the diff for secrets and unintended generated files.

## Security impact

<!-- Describe changes to authentication, authorization, secrets, dependencies, data handling, or network exposure. Write "None" when there is no security impact. -->

## Operations and migration

<!-- Describe configuration, database, deployment, rollback, or migration requirements. Write "None" when there are none. -->
```

- [ ] **Step 2: Create the security policy**

Create `SECURITY.md`:

```markdown
# Security Policy

## Reporting a vulnerability

Please do not disclose suspected vulnerabilities in a public issue or discussion.

Use [GitHub private vulnerability reporting](https://github.com/cpieper/buildable/security/advisories/new) to send the maintainer a private report. Include the affected component, reproduction steps or a proof of concept, potential impact, and any suggested mitigation.

You should receive an acknowledgment within seven days. The maintainer will coordinate validation, remediation, and public disclosure through the private advisory.

## Supported versions

Buildable is currently maintained from the `main` branch. Security fixes are applied there; older revisions are not supported separately.
```

- [ ] **Step 3: Create grouped Dependabot schedules**

Create `.github/dependabot.yml`:

```yaml
version: 2
updates:
  - package-ecosystem: uv
    directory: /backend
    schedule:
      interval: weekly
      day: monday
      time: "09:00"
      timezone: America/New_York
    open-pull-requests-limit: 5
    groups:
      python-dependencies:
        patterns:
          - "*"

  - package-ecosystem: npm
    directory: /frontend
    schedule:
      interval: weekly
      day: monday
      time: "09:15"
      timezone: America/New_York
    open-pull-requests-limit: 5
    groups:
      frontend-dependencies:
        patterns:
          - "*"

  - package-ecosystem: docker
    directory: /
    schedule:
      interval: weekly
      day: monday
      time: "09:30"
      timezone: America/New_York
    open-pull-requests-limit: 3
    groups:
      container-images:
        patterns:
          - "*"

  - package-ecosystem: github-actions
    directory: /
    schedule:
      interval: weekly
      day: monday
      time: "09:45"
      timezone: America/New_York
    open-pull-requests-limit: 3
    groups:
      actions:
        patterns:
          - "*"
```

- [ ] **Step 4: Parse and inspect the new files**

Run:

```bash
ruby -e 'require "yaml"; YAML.load_file(".github/dependabot.yml"); puts "dependabot yaml ok"'
rg -n 'TBD|TODO|FIXME|PLACEHOLDER' .github SECURITY.md
git diff --check
```

Expected: YAML parsing prints `dependabot yaml ok`; `rg` has no matches and may exit 1; `git diff --check` prints nothing.

- [ ] **Step 5: Commit the policy files with a signature**

```bash
git add .github/CODEOWNERS .github/pull_request_template.md .github/dependabot.yml SECURITY.md
git diff --cached --check
git commit -S -m "chore: add repository security policies"
```

Expected: one signed commit containing only the four policy files.

### Task 2: Add Required Continuous Integration

**Files:**
- Create: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: `backend/pyproject.toml`, `backend/uv.lock`, `frontend/package.json`, and `frontend/package-lock.json`.
- Produces: GitHub status checks named exactly `Backend` and `Frontend`.

- [ ] **Step 1: Create the CI workflow**

Create `.github/workflows/ci.yml`:

```yaml
name: CI

on:
  pull_request:
    branches:
      - main
  push:
    branches:
      - main

permissions:
  contents: read

concurrency:
  group: ci-${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}
  cancel-in-progress: true

jobs:
  backend:
    name: Backend
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - name: Check out repository
        uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - name: Set up Python
        uses: actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97 # v7.0.0
        with:
          python-version: "3.12"
      - name: Set up uv
        uses: astral-sh/setup-uv@c771a70e6277c0a99b617c7a806ffedaca235ff9 # v9.0.0
        with:
          version: "0.10.3"
          enable-cache: true
          cache-dependency-glob: backend/uv.lock
      - name: Install backend dependencies
        working-directory: backend
        run: uv sync --frozen --all-groups
      - name: Run Ruff
        working-directory: backend
        run: uv run ruff check app tests
      - name: Run pytest
        working-directory: backend
        run: uv run pytest

  frontend:
    name: Frontend
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - name: Check out repository
        uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - name: Set up Node.js
        uses: actions/setup-node@820762786026740c76f36085b0efc47a31fe5020 # v7.0.0
        with:
          node-version: "22"
          cache: npm
          cache-dependency-path: frontend/package-lock.json
      - name: Install frontend dependencies
        working-directory: frontend
        run: npm ci
      - name: Run Vitest
        working-directory: frontend
        run: npm test
      - name: Run Svelte checks
        working-directory: frontend
        run: npm run check
      - name: Build frontend
        working-directory: frontend
        run: npm run build
```

- [ ] **Step 2: Parse the workflow and verify every action is immutable**

Run:

```bash
ruby -e 'require "yaml"; YAML.load_file(".github/workflows/ci.yml"); puts "ci yaml ok"'
rg -n 'uses: [^ ]+@(v[0-9]+|main|master|latest)([[:space:]]|$)' .github/workflows/ci.yml
rg -n 'uses: [^ ]+@[0-9a-f]{40}( # .+)?$' .github/workflows/ci.yml
```

Expected: YAML parsing succeeds; the mutable-reference search has no matches; the immutable-reference search reports all five `uses:` lines.

- [ ] **Step 3: Run the exact CI commands locally**

```bash
cd backend && uv sync --frozen --all-groups && uv run ruff check app tests && uv run pytest
cd ../frontend && npm ci && npm test && npm run check && npm run build
cd ..
```

Expected: every command exits 0.

- [ ] **Step 4: Commit the CI workflow with a signature**

```bash
git add .github/workflows/ci.yml
git diff --cached --check
git commit -S -m "ci: add required project checks"
```

Expected: one signed commit containing only `ci.yml`.

### Task 3: Add Required Security Analysis

**Files:**
- Create: `.github/workflows/security.yml`

**Interfaces:**
- Consumes: GitHub's dependency graph and the checked-out Python and JavaScript/TypeScript source trees.
- Produces: GitHub checks named exactly `Dependency Review`, `CodeQL (python)`, and `CodeQL (javascript-typescript)`, plus CodeQL SARIF results.

- [ ] **Step 1: Create the security workflow**

Create `.github/workflows/security.yml`:

```yaml
name: Security

on:
  pull_request:
    branches:
      - main
  push:
    branches:
      - main
  schedule:
    - cron: "23 7 * * 1"

permissions:
  contents: read

concurrency:
  group: security-${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}
  cancel-in-progress: true

jobs:
  dependency-review:
    name: Dependency Review
    if: github.event_name == 'pull_request'
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - name: Check out repository
        uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - name: Review dependency changes
        uses: actions/dependency-review-action@a1d282b36b6f3519aa1f3fc636f609c47dddb294 # v5.0.0
        with:
          fail-on-severity: high

  codeql:
    name: CodeQL (${{ matrix.language }})
    runs-on: ubuntu-latest
    timeout-minutes: 20
    permissions:
      contents: read
      security-events: write
    strategy:
      fail-fast: false
      matrix:
        language:
          - python
          - javascript-typescript
    steps:
      - name: Check out repository
        uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - name: Initialize CodeQL
        uses: github/codeql-action/init@18420e3271f74589575af831a523c833acda327f # codeql-bundle-v2.26.2
        with:
          languages: ${{ matrix.language }}
          build-mode: none
      - name: Analyze source
        uses: github/codeql-action/analyze@18420e3271f74589575af831a523c833acda327f # codeql-bundle-v2.26.2
        with:
          category: /language:${{ matrix.language }}
```

- [ ] **Step 2: Parse and audit the workflow**

Run:

```bash
ruby -e 'require "yaml"; YAML.load_file(".github/workflows/security.yml"); puts "security yaml ok"'
rg -n 'uses: [^ ]+@(v[0-9]+|main|master|latest)([[:space:]]|$)' .github/workflows/security.yml
rg -n 'uses: [^ ]+@[0-9a-f]{40}( # .+)?$' .github/workflows/security.yml
rg -n 'permissions:|contents: read|security-events: write|persist-credentials: false|timeout-minutes:' .github/workflows/security.yml
```

Expected: YAML parsing succeeds; no mutable reference is found; all five action references and least-privilege controls are present.

- [ ] **Step 3: Commit the security workflow with a signature**

```bash
git add .github/workflows/security.yml
git diff --cached --check
git commit -S -m "ci: add dependency review and CodeQL"
```

Expected: one signed commit containing only `security.yml`.

### Task 4: Verify the Complete Local Change Set

**Files:**
- Verify: `.github/CODEOWNERS`
- Verify: `.github/pull_request_template.md`
- Verify: `.github/dependabot.yml`
- Verify: `.github/workflows/ci.yml`
- Verify: `.github/workflows/security.yml`
- Verify: `SECURITY.md`
- Verify: `docs/superpowers/specs/2026-08-10-repository-security-hardening-design.md`
- Verify: `docs/superpowers/plans/2026-08-10-repository-security-hardening.md`

**Interfaces:**
- Consumes: all implementation artifacts and commits created so far.
- Produces: a clean, signed branch ready for GitHub validation.

- [ ] **Step 1: Run all local project checks**

```bash
make test
make check
```

Expected: backend tests, frontend tests, Ruff, Svelte Check, and the production frontend build all exit 0.

- [ ] **Step 2: Validate YAML and immutable action references as a set**

```bash
ruby -e 'require "yaml"; Dir[".github/**/*.{yml,yaml}"].sort.each { |path| YAML.load_file(path); puts "ok #{path}" }'
rg -n 'uses: [^ ]+@(v[0-9]+|main|master|latest)([[:space:]]|$)' .github/workflows
rg -n 'uses: [^ ]+@[0-9a-f]{40}( # .+)?$' .github/workflows
git diff --check origin/main...HEAD
```

Expected: every YAML file parses; mutable-reference search returns no matches; immutable-reference search returns every external action; diff check is empty.

- [ ] **Step 3: Verify every branch commit has a valid signature**

```bash
git log origin/main..HEAD --format='%H %G? %GS %s'
```

Expected: every listed commit contains signature status `G` and the expected signer identity. Any `N`, `B`, `E`, `U`, `X`, or `Y` stops the rollout.

- [ ] **Step 4: Confirm the worktree and scope are clean**

```bash
git status --short
git diff --stat origin/main...HEAD
```

Expected: status is empty; the diff contains only the design, plan, workflows, and policy files named above.

### Task 5: Publish and Validate the Setup Pull Request

**Files:**
- No new files unless a GitHub workflow exposes a concrete defect.

**Interfaces:**
- Consumes: the signed `codex/repository-security-hardening` branch.
- Produces: a merged setup PR and the exact live check names required by the ruleset.

- [ ] **Step 1: Push the signed feature branch**

```bash
git push -u origin codex/repository-security-hardening
```

Expected: the branch is created on `origin`; GitHub shows each commit as `Verified`.

- [ ] **Step 2: Open a draft pull request**

Use the `github:yeet` publishing workflow and create a draft PR with:

```text
Title: chore: harden repository security controls

Summary:
- add least-privilege CI and security workflows pinned to immutable action SHAs
- add Dependabot, ownership, pull-request, and vulnerability-reporting policy
- document the two-phase GitHub ruleset rollout

Validation:
- make test
- make check
- YAML parse and immutable action reference audit
- GPG signature verification for every branch commit

Rollout:
- merge this PR before enabling required checks
- configure repository settings and activate the no-bypass main ruleset after live checks pass
```

Expected: one draft PR targeting `main` from `codex/repository-security-hardening`.

- [ ] **Step 3: Wait for all GitHub checks and capture exact names**

```bash
gh pr checks --watch
gh pr checks --json name,bucket,workflow
```

Expected required names:

```text
Backend
Frontend
Dependency Review
CodeQL (python)
CodeQL (javascript-typescript)
```

All five must report success. If any name differs, update the plan and later ruleset payload to the exact observed name before proceeding.

- [ ] **Step 4: Fix only concrete workflow failures**

For each failure, inspect its job log with `gh run view --log-failed`, reproduce the failed command locally, apply the smallest correction, rerun its local validation, and make a new signed commit. Re-run Step 3 until all five checks pass. Do not weaken permissions, severity thresholds, signature requirements, or action pinning to make a check pass.

- [ ] **Step 5: Mark the PR ready and merge through a signed GitHub path**

```bash
gh pr ready
gh pr merge --squash --delete-branch
```

Expected: GitHub squash-merges the maintainer-authored PR, the new `main` commit displays `Verified`, and the feature branch is deleted remotely.

- [ ] **Step 6: Update local `main` and record its unchanged pre-ruleset head**

```bash
git switch main
git pull --ff-only origin main
git rev-parse HEAD
```

Expected: local `main` matches `origin/main`; save the printed SHA as the pre-ruleset baseline.

### Task 6: Configure Repository Merge, Actions, and Security Settings

**Files:**
- No repository files; this task changes GitHub repository settings through authenticated REST API calls.

**Interfaces:**
- Consumes: merged SHA-pinned workflows on `main` and administrator access as `cpieper`.
- Produces: restricted merge methods, least-privilege Actions policy, dependency security, expanded secret scanning, and private vulnerability reporting.

- [ ] **Step 1: Configure merge behavior**

```bash
gh api --method PATCH repos/cpieper/buildable \
  -F allow_merge_commit=true \
  -F allow_squash_merge=true \
  -F allow_rebase_merge=false \
  -F delete_branch_on_merge=true \
  -F allow_auto_merge=false \
  -F web_commit_signoff_required=false
```

Expected: response fields match the six requested values.

- [ ] **Step 2: Retain least-privilege workflow token defaults**

```bash
gh api --method PUT repos/cpieper/buildable/actions/permissions/workflow \
  -f default_workflow_permissions=read \
  -F can_approve_pull_request_reviews=false
```

Expected: HTTP 204.

- [ ] **Step 3: Restrict and SHA-pin allowed actions**

Run in this order:

```bash
gh api --method PUT repos/cpieper/buildable/actions/permissions \
  -F enabled=true \
  -f allowed_actions=selected \
  -F sha_pinning_required=true

gh api --method PUT repos/cpieper/buildable/actions/permissions/selected-actions \
  -F github_owned_allowed=true \
  -F verified_allowed=false \
  -f 'patterns_allowed[]=astral-sh/setup-uv@*'
```

Expected: both requests return HTTP 204. The wildcard selects the action identity; the repository-wide SHA policy still requires an immutable 40-character SHA in workflow usage.

- [ ] **Step 4: Enable dependency alerts and security updates**

```bash
gh api --method PUT repos/cpieper/buildable/vulnerability-alerts
gh api --method PUT repos/cpieper/buildable/automated-security-fixes
```

Expected: both requests return HTTP 204.

- [ ] **Step 5: Enable private vulnerability reporting**

```bash
gh api --method PUT repos/cpieper/buildable/private-vulnerability-reporting
```

Expected: HTTP 204. If GitHub returns a documented plan/availability error, preserve `SECURITY.md`, record the limitation, and continue without publishing an email address.

- [ ] **Step 6: Enable available expanded secret-scanning features**

Apply each feature separately so an unavailable feature does not roll back the others:

```bash
gh api --method PATCH repos/cpieper/buildable \
  -f 'security_and_analysis[secret_scanning][status]=enabled'

gh api --method PATCH repos/cpieper/buildable \
  -f 'security_and_analysis[secret_scanning_push_protection][status]=enabled'

gh api --method PATCH repos/cpieper/buildable \
  -f 'security_and_analysis[secret_scanning_validity_checks][status]=enabled'

gh api --method PATCH repos/cpieper/buildable \
  -f 'security_and_analysis[secret_scanning_non_provider_patterns][status]=enabled'
```

Expected: each supported feature reports `enabled`. Record and skip only a specific feature that GitHub explicitly reports as unavailable.

- [ ] **Step 7: Read back every repository setting**

```bash
gh api --method GET repos/cpieper/buildable --jq '{allow_merge_commit,allow_squash_merge,allow_rebase_merge,delete_branch_on_merge,allow_auto_merge,web_commit_signoff_required,security_and_analysis}'
gh api --method GET repos/cpieper/buildable/actions/permissions
gh api --method GET repos/cpieper/buildable/actions/permissions/selected-actions
gh api --method GET repos/cpieper/buildable/actions/permissions/workflow
gh api --method GET repos/cpieper/buildable/private-vulnerability-reporting
```

Expected: readback exactly matches Steps 1-6, except for any explicitly documented unavailable feature.

### Task 7: Create and Smoke-test the No-bypass Main Ruleset

**Files:**
- Temporarily create and then delete: `.superpowers/protect-main-ruleset.json`

**Interfaces:**
- Consumes: live successful status names from Task 5 and the hardened settings from Task 6.
- Produces: one active `Protect main` ruleset targeting only `refs/heads/main`, with no bypass actors.

- [ ] **Step 1: Create a disposable branch at the current main SHA**

```bash
gh api --method POST repos/cpieper/buildable/git/refs \
  -f ref=refs/heads/codex/ruleset-smoke-test \
  -f sha="$(git rev-parse origin/main)"
```

Expected: GitHub creates `refs/heads/codex/ruleset-smoke-test` at exactly `origin/main`.

- [ ] **Step 2: Create the initial exact ruleset payload**

Create ignored file `.superpowers/protect-main-ruleset.json`:

```json
{
  "name": "Protect main",
  "target": "branch",
  "enforcement": "active",
  "bypass_actors": [],
  "conditions": {
    "ref_name": {
      "include": [
        "refs/heads/main",
        "refs/heads/codex/ruleset-smoke-test"
      ],
      "exclude": []
    }
  },
  "rules": [
    {
      "type": "deletion"
    },
    {
      "type": "non_fast_forward"
    },
    {
      "type": "required_signatures"
    },
    {
      "type": "pull_request",
      "parameters": {
        "required_approving_review_count": 0,
        "dismiss_stale_reviews_on_push": false,
        "require_code_owner_review": false,
        "require_last_push_approval": false,
        "required_review_thread_resolution": true,
        "allowed_merge_methods": [
          "merge",
          "squash"
        ]
      }
    },
    {
      "type": "required_status_checks",
      "parameters": {
        "strict_required_status_checks_policy": true,
        "do_not_enforce_on_create": false,
        "required_status_checks": [
          {
            "context": "Backend"
          },
          {
            "context": "Frontend"
          },
          {
            "context": "Dependency Review"
          },
          {
            "context": "CodeQL (python)"
          },
          {
            "context": "CodeQL (javascript-typescript)"
          }
        ]
      }
    }
  ]
}
```

- [ ] **Step 3: Create the active ruleset and capture its ID**

```bash
gh api --method POST repos/cpieper/buildable/rulesets \
  --input .superpowers/protect-main-ruleset.json \
  --jq '{id,name,enforcement,conditions,rules,bypass_actors}'
```

Expected: HTTP 201; name is `Protect main`; enforcement is `active`; bypass actors are empty; all five rule types are returned. Save the numeric `id` from the response as `RULESET_ID` without reusing a common system environment variable.

- [ ] **Step 4: Smoke-test direct-push rejection on the disposable branch**

```bash
git fetch origin codex/ruleset-smoke-test
git switch -c codex/ruleset-smoke-test --track origin/codex/ruleset-smoke-test
git -c commit.gpgsign=false commit --allow-empty -m "test: verify ruleset rejection"
git push origin HEAD:refs/heads/codex/ruleset-smoke-test
```

Expected: the push is rejected because the update is unsigned and is not associated with a pull request. If it succeeds, stop: do not apply the ruleset only to `main`; inspect rule-suite results and correct the payload first. A successful unexpected push affects only the disposable branch.

- [ ] **Step 5: Restore local main and verify main did not move**

```bash
git switch main
git fetch origin main
git rev-parse origin/main
```

Expected: `origin/main` equals the pre-ruleset baseline SHA captured in Task 5 Step 6.

- [ ] **Step 6: Narrow the payload to main only and update the ruleset**

Edit `.superpowers/protect-main-ruleset.json` so `conditions.ref_name.include` is exactly:

```json
[
  "refs/heads/main"
]
```

Leave every other byte of policy meaning unchanged. Then run:

```bash
gh api --method PUT repos/cpieper/buildable/rulesets/"$RULESET_ID" \
  --input .superpowers/protect-main-ruleset.json \
  --jq '{id,name,enforcement,conditions,rules,bypass_actors}'
```

Expected: the active ruleset targets only `refs/heads/main`, has no bypass actors, and retains deletion, non-fast-forward, signature, PR, and required-check rules.

- [ ] **Step 7: Remove only the disposable test artifacts**

```bash
gh api --method DELETE repos/cpieper/buildable/git/refs/heads/codex/ruleset-smoke-test
```

Delete `.superpowers/protect-main-ruleset.json` with `apply_patch`. Delete the local `codex/ruleset-smoke-test` branch only after confirming `main` is checked out:

```bash
git branch -D codex/ruleset-smoke-test
git status --short
```

Expected: the GitHub API returns HTTP 204, the temporary payload no longer exists, the temporary local branch is gone, and the worktree is clean.

### Task 8: Verify Final Enforcement and Security State

**Files:**
- No file changes.

**Interfaces:**
- Consumes: the active ruleset and all repository settings.
- Produces: evidence-backed final state and an explicit list of any unavailable optional features.

- [ ] **Step 1: Read the complete ruleset and assert its critical fields**

```bash
gh api --method GET repos/cpieper/buildable/rulesets --jq '.[] | select(.name == "Protect main") | {id,name,target,enforcement}'
gh api --method GET repos/cpieper/buildable/rulesets/"$RULESET_ID" --jq '{name,target,enforcement,bypass_actors,conditions,rules}'
```

Expected: exactly one active branch ruleset named `Protect main`; only `refs/heads/main` is included; bypass actor list is empty; required approval count is 0; conversation resolution and strict checks are true; allowed merges are `merge` and `squash`; all five expected status checks are present.

- [ ] **Step 2: Confirm no legacy branch rule conflicts with the ruleset**

```bash
gh api --method GET repos/cpieper/buildable/branches/main/protection
```

Expected: HTTP 404 `Branch not protected`, because this design intentionally uses a repository ruleset rather than layering legacy branch protection.

- [ ] **Step 3: Confirm GitHub security and Actions state one final time**

```bash
gh api --method GET repos/cpieper/buildable --jq '{default_branch,visibility,allow_merge_commit,allow_squash_merge,allow_rebase_merge,delete_branch_on_merge,allow_auto_merge,web_commit_signoff_required,security_and_analysis}'
gh api --method GET repos/cpieper/buildable/actions/permissions
gh api --method GET repos/cpieper/buildable/actions/permissions/selected-actions
gh api --method GET repos/cpieper/buildable/actions/permissions/workflow
gh api --method GET repos/cpieper/buildable/private-vulnerability-reporting
```

Expected: settings match the approved design and Task 6 readback.

- [ ] **Step 4: Confirm the default branch and worktree are unchanged by smoke testing**

```bash
git fetch origin main
git rev-parse main
git rev-parse origin/main
git status --short
```

Expected: local and remote `main` point to the same verified setup-PR merge SHA; status is empty.

- [ ] **Step 5: Report completion with evidence**

Report:

- setup PR URL and verified merge SHA;
- ruleset ID and exact enforced checks;
- merge and Actions settings readback;
- enabled Dependabot, secret-scanning, CodeQL, and private-reporting features;
- disposable-branch push rejection result;
- any GitHub feature explicitly unavailable under the current repository/account plan.

Do not claim a control is active without its API readback or the relevant failed smoke-test output.
