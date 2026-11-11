# GitHub task tracking automation

Iteration plans remain the source for task detail. A work package that needs tracking has one
metadata comment directly below its `###` heading:

```markdown
<!-- reach-task
id: app-iteration/W5
owner: RicoS03
target_date: 2026-12-04
depends_on: app-iteration/W4
-->
```

`id` is required, unique across the two approved plan files, and stable even if the heading changes.
Use a lowercase plan slug, `/`, then a package key (for example `app-iteration/W5` or
`implementation/P8`). `owner`, `target_date`, and `depends_on` are optional; owner is a GitHub
username, target date is ISO `YYYY-MM-DD`, and dependencies are comma-separated stable IDs. Leave
an optional value empty when it does not apply. Metadata keys must appear at most once and in the
exact form shown. Malformed blocks, duplicate IDs, unresolved dependencies, or tasks without a
summary and acceptance criterion fail the sync instead of being guessed.

The issue title follows the package heading. Its managed body section contains the summary,
checklist, and metadata. Automation replaces only the marked section; human-written notes outside
it remain. Removing a package from a plan produces a review notice. It does not close or delete the
issue.

## Workflow and permissions

`.github/workflows/issue-sync.yml` runs plan reconciliation after approved plan files reach `dev`,
handles PRs targeting `dev` (including drafts), and updates Project status when a tracked issue
changes state. It also reconciles open work every Monday at 02:00 UTC. It checks out trusted `dev`
code and never checks out or executes PR-head code. It provides a manual `plans` or `bootstrap` dispatch;
unchecked **Apply changes** runs a dry-run.

The workflow needs `GITHUB_TOKEN` with repository `issues: write` and `pull-requests: write`. Add
an Actions secret named `PROJECTS_TOKEN` containing a fine-grained token scoped to the
IsochroneLabs organization with Projects write permission. The workflow never prints the secret.
It validates that exactly one organization Project named **Data Science Project** exists and has a
Status field with Todo, In progress, and Done before writing any issue or milestone. If the token
or preflight is unavailable, it exits before changes and puts setup guidance in the Actions
summary. Do not paste the token into chat or commit it.

Open tracked issues are assigned to the weekly milestone titled `WNN: Week of YYYY-MM-DD`, where
the date is Monday in Europe/Berlin. The week number is derived from existing dated weekly
milestones. A missing week is created with the next Monday as its due date. At rollover, open
automation-managed issues move to the new week; closed and manually managed issues stay put.
Project cards contain issues only. Status is Todo without an open PR, In progress with an open PR,
and Done for a closed issue. An unmerged closed PR leaves its issue open. A merged PR closes an
issue only through GitHub's explicit closing keyword behavior.

## One-time bootstrap after merge

1. Keep `PROJECTS_TOKEN` unset while merging the automation and task metadata. The plan push run
   fails closed while the secret is absent, so it makes no external changes.
2. In repository **Settings → Secrets and variables → Actions**, create `PROJECTS_TOKEN` with the
   scope above.
3. Open **Actions → Issue and Project sync → Run workflow**. Select `bootstrap` and leave **Apply
   changes** unchecked. Inspect the generated Actions summary for issue creates/updates,
   milestone moves, and Project cards/statuses.
4. When the dry-run is correct, dispatch `bootstrap` again with **Apply changes** checked.
   Re-running is idempotent. This reconciles task markers from both plans and PRs targeting `dev`.

Do not change repository rulesets or Project fields to make the workflow pass.

## Security note

This repository is public. GitHub documents a default `pull_request_target` event policy for
public repositories that is in evaluate mode now and scheduled for enforcement on 2 Dec 2026.
The trigger is needed here because the workflow writes issues and PR bodies; it checks out only
trusted `dev` code and never executes pull request code. The event policy may still block these
runs after enforcement unless an organization administrator explicitly allows the event. This
change does not alter repository or organization settings.
