# How to contribute

Thanks for helping out!

## Commits and PR titles

We follow "[Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/)", combined with the "[Angular Commit Message format](https://github.com/angular/angular/blob/main/CONTRIBUTING.md#-commit-message-format)".

PRs are squash-merged, so the **PR title** becomes the commit on `main`. That's where this convention matters most, but please use it for individual commits too.

Start the title with one of these keywords:

- `feat`: new feature for the user
- `fix`: bug fix for the user
- `docs`: changes to the documentation
- `style`: formatting, missing semi colons, etc; no production code change
- `refactor`: refactoring production code, eg. renaming a variable
- `test`: adding missing tests, refactoring tests; no production code change
- `chore`: cleanups, version updates etc; no production code change

Write an _imperative_ description of the change. Don't describe what _you did_; describe what the commit will **do** when it is applied.
In your head, finish the sentence: "**This commit will... `<verb> <subject> ...`**".

Some examples:

- `feat:` (This commit will) `Add info-button to Profile-page header`
- `docs:` (This commit will) `Remove confusing/inconsistent terms from helper-functions examples`
- `refactor:` (This commit will) `Load the program-list fast again`
- `fix:` (This commit will) `Prevent the user from submitting an empty form`

Some additional reading:

- [Commit Often, Perfect Later, Publish Once: Git Best Practices](https://sethrobertson.github.io/GitBestPractices/)

## Branches

Name branches `username/branch-description`, e.g. `aberonni/ignore-duplicates`. This reflects that each branch has one owner (see [Pull Request Guidelines](#pull-request-guidelines)).

This is not strictly enforced, but we strongly encourage it for consistency.

## Pull Request Guidelines

Submit changes through [pull requests](https://docs.github.com/en/pull-requests) and follow the pre-populated description template.

- **Draft PRs**: Ignore unless the author explicitly requests attention.
- **Ownership**: Each branch has one owner/maintainer who is also the PR author.
- **Review readiness**:
  - The PR author decides when it's ready for review.
  - "Ready for review" means it's likely to be merged after approval unless stated otherwise.
  - The same reviewer should perform subsequent reviews on a PR they've already reviewed.
- **Reviewers**: Limit to one reviewer unless additional expertise is needed.
- **Merging**:
  - The author merges after approval, though reviewers may merge immediately after approving.
  - If the author doesn't want immediate merging, they must state this in the PR description.
  - PRs must be up-to-date with the target branch before merging, preferably via rebase.
- **Changes during review**:
  - Only the PR author can modify their branch. Reviewers request changes via reviews.
  - Exception: After approval, a reviewer may rebase via GitHub UI if auto-merge is enabled and only a branch update (without conflicts) is pending.
- **PR Lifecycle**:
  - Keep PRs small and merge quickly to minimize maintenance overhead.
  - Prioritize reviewing code over writing new code.
  - Split large changes into smaller, independently mergeable units.
- **PRs targeting main**:
  - A title following the [convention above](#commits-and-pr-titles) (e.g., `feat: Ignore duplicates`)
  - An Azure DevOps reference (`AB#12345`) in the description (checked by CI). This links the PR and the DevOps item both ways.
  - One of the [labels we use for auto-generating release notes](../.github/release.yml) (checked by CI)
- **PRs targeting non-main branches**:
  - If the target branch is under review, keep the PR in draft until the target branch merges to main.

### Feature Branches

We avoid "feature branches" (long-lived branches with multiple/no owners). For PRs resulting from multiple authors:

- A single person (the PR author) owns the PR and all related changes
- The PR needs review from someone who hasn't contributed to it
- Example: If Bob creates a PR and Jules adds code to it via another PR, someone other than Bob or Jules must review the main PR.

### PR Content Guidelines

- **Avoid mixing responsibilities**:
  - Too broad: Adding a backend endpoint, migrating data, creating frontend code to display it, and adding helper functions.
  - Appropriate scope: Adding a property to an existing entity and displaying it in an existing component.
  - Adding a lint rule plus necessary fixes is acceptable, but adding unrelated features is not.
- **Prefer non-breaking changes**:
  - Example: Add unused backend endpoints or remove frontend elements without removing related endpoints.
  - Separate changes reduce risk and simplify review (though context for both sides is still needed).

#### Cross-repo changes

Frontend code lives in the [go-web-app](https://github.com/rodekruis/go-web-app/tree/nrw-develop) repo; backend code lives here. When a change spans both repos (e.g. a new or changed API contract), create "sibling PRs":

1. Try to minimize the "shared" parts, and postpone other changes on both sides to follow-up PRs.
2. Prepare sibling PRs in both repos as ready-to-merge, but expect the e2e test on NRW-repo to potentially fail. (as it uses nrw-develop, and not the feature branch.)
3. Merge the **front-end PR first**
4. Re-run any failing e2e tests on the back-end PR (NRW) — they clone `nrw-develop` HEAD and should now pick up the updated FE.
5. Merge the back-end PR if e2e passes.
6. If e2e still fails: fix the back-end PR or create a follow-up front-end PR and repeat this process.

---

Some useful reading:

- [A guide to mindful communication in code reviews](https://kickstarter.engineering/a-guide-to-mindful-communication-in-code-reviews-48aab5282e5e)
