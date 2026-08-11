# Repository Security Hardening Design

## Summary

Buildable will use GitHub repository rules, required automated checks, signed commits, and dependency/security automation to protect `main`. The repository has one maintainer, `@cpieper`, and no other trusted reviewer. Every change—including changes from the maintainer—must reach `main` through a pull request. Automated checks replace mandatory human approval, which would deadlock a solo-maintainer repository because GitHub does not allow a pull request author to approve their own pull request.

The rollout has two phases. First, add and validate the checked-in workflows and policy files through a pull request. Second, enable the GitHub-side settings and activate required checks only after their exact status-check names have appeared successfully. This prevents an untested or incorrectly named check from locking `main`.

## Goals

- Prevent routine direct pushes to `main`, including by the repository owner.
- Ensure only commits with a GitHub-verified cryptographic signature enter `main`.
- Require every change to pass project tests, static checks, builds, and security checks.
- Prevent force pushes and deletion of `main`.
- Minimize GitHub Actions token and third-party action risk.
- Detect vulnerable dependencies, leaked secrets, and common code vulnerabilities.
- Give outside reporters a private vulnerability-reporting path.
- Keep the process usable for one maintainer and for signed Dependabot updates.

## Non-goals

- Requiring a human approval while the repository has only one maintainer.
- Rewriting existing `main` history to retroactively sign old commits.
- Introducing organization-level policy, Terraform, or another policy-as-code platform.
- Adding deployment gates or release-signing infrastructure.
- Enabling automatic merging of dependency updates.

## Current State

- `main` is the default branch.
- The repository is public and owned by the personal GitHub account `cpieper`.
- `cpieper` has administrative access and is the only intended writer.
- No branch protection rule or repository ruleset exists.
- No GitHub Actions workflows, Dependabot configuration, `CODEOWNERS`, or `SECURITY.md` exist.
- GitHub Actions is enabled with a read-only default workflow token; workflows cannot approve pull requests.
- Actions may currently use any action, and full-SHA pinning is not enforced.
- Secret scanning and push protection are enabled.
- Dependabot security updates are disabled.
- Local Git configuration requests commit signing, but recent repository history is unsigned. Existing history will remain unchanged; enforcement applies to commits newly introduced to `main`.

## GitHub Ruleset

Create one active branch ruleset named `Protect main`, targeting `refs/heads/main`. Do not configure a bypass actor. An administrator can still edit or disable the ruleset as an explicit break-glass action, but there is no routine bypass during pushes or pull-request merges.

The ruleset will:

- block branch deletion;
- block non-fast-forward updates and force pushes;
- require commits introduced to `main` to have a verified signature;
- require every update to be associated with a pull request;
- require zero approving reviews;
- require all review conversations to be resolved;
- require the pull-request branch to be up to date before merging;
- require successful checks for backend validation, frontend validation, dependency review, and CodeQL analysis.

The ruleset will not use `restrict_updates`. A mandatory pull request already blocks direct pushes, and only accounts with write access can merge. Because `cpieper` is the only writer, only `cpieper` can update `main` through the permitted pull-request path. Adding `restrict_updates` with a bypass actor could inadvertently let that actor skip signing or status-check requirements.

## Pull Requests and Merge Methods

The repository will allow merge commits and squash merges, and disable rebase merges.

- `cpieper` may squash-merge their own pull requests. GitHub signs commits it creates through the web interface.
- Dependabot signs its commits by default. Merge commits remain available for a Dependabot pull request because GitHub does not permit a maintainer who is not the pull-request author to squash into a branch that requires signed commits.
- Rebase merging is disabled because GitHub documents that its rebase-and-merge path adds commits without commit signature verification.

Merged branches will be deleted automatically. Auto-merge remains disabled initially so the maintainer performs an explicit final merge after reviewing results.

## Required Workflows

### Continuous Integration

Add `.github/workflows/ci.yml`, triggered for pull requests to `main` and pushes to `main`. It contains two independent, required jobs:

- `Backend`: install the locked uv environment on Python 3.12, run Ruff, and run pytest.
- `Frontend`: install the locked npm environment on Node.js 22, run Vitest, run Svelte/TypeScript checks, and build the production frontend.

The workflow will use concurrency cancellation for superseded runs, explicit timeouts, least-privilege `contents: read` permissions, and no persisted checkout credentials.

### Security Checks

Add `.github/workflows/security.yml` with:

- `Dependency Review` on pull requests, failing when a change introduces a dependency with a high or critical known vulnerability.
- `CodeQL (python)` and `CodeQL (javascript-typescript)` on pull requests, pushes to `main`, and a weekly schedule.

CodeQL uses the repository's ordinary build path where practical. Security workflows receive only the permissions required to read contents and upload security results. Required check names will be copied from successful GitHub runs rather than assumed when the ruleset is activated.

### Action Supply-chain Controls

Every non-local action reference will be pinned to a full 40-character commit SHA with a nearby release-tag comment for maintainability. Dependabot will update both the SHA and comment.

Repository Actions policy will:

- keep Actions enabled;
- retain read-only default workflow permissions;
- retain the prohibition on workflows approving pull requests;
- require full-SHA action pinning;
- allow GitHub-owned actions and the specifically required `astral-sh/setup-uv` action;
- reject unapproved third-party actions.

## Dependency Automation

Add `.github/dependabot.yml` with weekly grouped updates and conservative pull-request limits for:

- uv dependencies in `/backend`;
- npm dependencies in `/frontend`;
- Docker dependencies at the repository root;
- GitHub Actions in `/.github/workflows`.

Enable the dependency graph, Dependabot alerts, and Dependabot security updates. Dependabot pull requests must pass the same ruleset and required checks as other pull requests. They will never auto-merge.

## Repository Policy Files

- `.github/CODEOWNERS` assigns all paths to `@cpieper`. Code-owner approval is documented but not required while there is only one maintainer.
- `.github/pull_request_template.md` prompts for a summary, test evidence, security impact, and operational/migration considerations.
- `SECURITY.md` directs vulnerability reporters to GitHub private vulnerability reporting and discourages public issue disclosure.

The repository will not enable web commit signoff because Developer Certificate of Origin signoff is not a cryptographic commit signature and is outside this design's provenance goal.

## GitHub Security Features

Enable or retain:

- dependency graph;
- Dependabot alerts and security-update pull requests;
- secret scanning;
- secret-scanning push protection;
- secret validity checks and non-provider pattern detection when available for this public repository;
- private vulnerability reporting;
- CodeQL code scanning through the checked-in workflow.

Any feature unavailable to this personal public repository or current GitHub plan will be reported and skipped rather than silently replaced with a weaker control.

## Failure Handling and Recovery

- Workflow failures block merging but do not affect feature branches.
- If an expected status name differs from the design, use the successful check name reported by GitHub before activating the ruleset.
- If signing rejects a commit, rewrite only the affected feature-branch commit with a verified signature and force-push the feature branch; never weaken the `main` rule to accommodate it.
- If a GitHub App or Dependabot cannot merge under signature enforcement, confirm that its commits are verified and use an allowed signed merge path.
- If a ruleset configuration locks merging unexpectedly, the owner may edit the ruleset as an audited break-glass action, make the smallest correction, and restore active enforcement immediately.
- Existing unsigned commits on `main` are not rewritten.

## Verification

Before the GitHub ruleset is activated:

1. Validate workflow YAML and Dependabot configuration locally where tooling permits.
2. Run `make test` and `make check` locally.
3. Confirm the implementation commits show `Verified` on GitHub.
4. Open the implementation pull request and confirm all intended jobs run successfully.
5. Record the exact GitHub check names and configure them as required checks.

After activation:

1. Read the repository ruleset through the GitHub API and compare every rule to this design.
2. Read repository merge, Actions, and security settings through the GitHub API.
3. Confirm a direct push to `main` is rejected without changing repository history.
4. Confirm an unsigned test commit cannot be merged into `main`.
5. Confirm a signed pull request with all required checks can be merged by `cpieper`.
6. Confirm Dependabot, CodeQL, secret scanning, push protection, and private vulnerability reporting are enabled or document any plan-related limitation.

## Rollout Sequence

1. Create the checked-in workflows and policy files on `codex/repository-security-hardening` using signed commits.
2. Run local validation and open a pull request.
3. Observe and fix GitHub workflow runs until all intended checks pass.
4. Merge the setup pull request using a signed GitHub merge path.
5. Configure merge methods, automatic branch deletion, Actions policy, and GitHub security features.
6. Create and activate the `Protect main` ruleset using the observed status-check names.
7. Read back and verify all settings, then perform non-destructive enforcement checks.

## Acceptance Criteria

- Direct pushes to `main`, including by `cpieper`, are rejected.
- Every change to `main` is associated with a pull request.
- Only verified signed commits enter `main` after activation.
- Backend, frontend, dependency-review, and CodeQL checks pass before merging.
- Review conversations must be resolved; human approval is not required.
- Force pushes and deletion of `main` are blocked.
- Actions use least privilege, approved publishers, and immutable SHA references.
- Dependabot and GitHub security features are enabled as designed.
- A private vulnerability-reporting path and repository security policy are visible.
