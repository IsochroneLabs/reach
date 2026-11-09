from datetime import datetime

import pytest

from reach_pipeline.github_sync import (
    MANAGED_END,
    MANAGED_START,
    SyncError,
    Task,
    active_milestone,
    parse_issue_refs,
    parse_tasks,
    project_item,
    project_preflight,
    reconcile_tasks,
    replace_managed_body,
    sync_issue,
    sync_pr,
    week_for,
)

VALID = """### W5 — Details
<!-- reach-task
id: app-iteration/W5
owner: ricoS03
target_date: 2026-12-04
depends_on: app-iteration/W4
-->

Summary text.

**Done when:** Finished behavior is documented.
"""


def test_parse_valid_task_metadata_and_acceptance_criteria():
    task = parse_tasks(VALID, "fixture.md")[0]
    assert task == Task(
        "app-iteration/W5",
        "W5 — Details",
        "Summary text.",
        ("Finished behavior is documented.",),
        "ricoS03",
        "2026-12-04",
        ("app-iteration/W4",),
    )


def test_reject_missing_id_malformed_metadata_and_duplicate_ids():
    with pytest.raises(SyncError, match="malformed task metadata"):
        parse_tasks("### X\n<!-- reach-task\nid: x\n\n**Done when:** yes")
    with pytest.raises(SyncError, match="missing or invalid task id"):
        parse_tasks(VALID.replace("id: app-iteration/W5", "id: "))
    with pytest.raises(SyncError, match="duplicate task id"):
        parse_tasks(VALID + VALID)


def test_reject_bad_dependency_or_missing_criteria():
    with pytest.raises(SyncError, match="invalid dependency"):
        parse_tasks(VALID.replace("app-iteration/W4", "not a task id"))
    with pytest.raises(SyncError, match="no Done when"):
        parse_tasks(
            VALID.replace("**Done when:** Finished behavior is documented.", "No criteria.")
        )


def test_managed_section_updates_without_overwriting_human_notes():
    old = f"Human notes before.\n\n{MANAGED_START}\nold\n{MANAGED_END}\n\nHuman notes after."
    updated = replace_managed_body(old, f"{MANAGED_START}\nnew\n{MANAGED_END}")
    assert updated.startswith("Human notes before.")
    assert updated.endswith("Human notes after.")
    assert "old" not in updated


def test_managed_section_is_appended_once_and_malformed_markers_fail():
    managed = f"{MANAGED_START}\nbody\n{MANAGED_END}"
    assert replace_managed_body("Human note", managed).count(MANAGED_START) == 1
    with pytest.raises(SyncError, match="malformed managed-section"):
        replace_managed_body(f"{MANAGED_START} only", managed)


def test_week_rollover_uses_monday_in_berlin():
    monday, following = week_for(datetime.fromisoformat("2026-11-08T23:30:00+00:00"))
    assert monday.isoformat() == "2026-11-09"
    assert following.isoformat() == "2026-11-16"


def test_closing_references_are_explicit_only():
    assert parse_issue_refs("Fixes #12 and resolves #13; Tracking issue: #14") == {12, 13}


class FakeGitHub:
    def __init__(self):
        self.repository = "IsochroneLabs/reach"
        self.issues = []
        self.created = 0
        self.patches = []

    def request(self, method, path, data=None):
        if method == "POST" and path.endswith("/issues"):
            self.created += 1
            issue = {
                "number": self.created,
                "node_id": f"issue-{self.created}",
                "state": "open",
                **data,
            }
            issue["assignees"] = [{"login": login} for login in data.get("assignees", [])]
            self.issues.append(issue)
            return issue
        if method == "PATCH":
            self.patches.append((path, data))
            issue = self.issues[0]
            issue.update(data)
            if data.get("milestone"):
                issue["milestone"] = {
                    "number": data["milestone"],
                    "title": "W02: Week of 2026-11-09",
                }
            return issue
        raise AssertionError((method, path, data))


def test_plan_sync_creates_once_then_updates_only_managed_section(monkeypatch):
    import reach_pipeline.github_sync as sync

    client = FakeGitHub()
    monkeypatch.setattr(
        sync, "_all", lambda _client, path: client.issues if path.startswith("issues?") else []
    )
    monkeypatch.setattr(
        sync, "active_milestone", lambda *_args: {"number": 7, "title": "W02: Week of 2026-11-09"}
    )
    project_calls = []
    monkeypatch.setattr(
        sync,
        "project_item",
        lambda *_args: project_calls.append(_args[4]["number"]) or "project synced",
    )
    task = parse_tasks(VALID)[0]
    project = ("project", "status", {"todo": "todo", "in progress": "progress", "done": "done"})

    reconcile_tasks(
        client, [task], project, True, datetime.fromisoformat("2026-11-09T12:00:00+01:00")
    )
    client.issues[0]["body"] += "\n\nHuman note."
    reconcile_tasks(
        client, [task], project, True, datetime.fromisoformat("2026-11-09T12:00:00+01:00")
    )

    assert client.created == 1
    assert "Human note." in client.issues[0]["body"]
    assert len(client.patches) == 1
    assert project_calls == [1, 1]


def test_bootstrap_reuses_and_reopens_legacy_package_issue(monkeypatch):
    import reach_pipeline.github_sync as sync

    issue = {
        "number": 40,
        "node_id": "issue-40",
        "state": "closed",
        "title": "W5: Add facility details and show park areas with access points",
        "body": "## Duplicate tracking note\nFollow PR #39.",
        "assignees": [{"login": "ricoS03"}],
        "milestone": {"number": 7, "title": "W02: Week of 2026-11-09"},
    }
    client = FakeGitHub()
    client.issues = [issue]
    monkeypatch.setattr(
        sync, "_all", lambda _client, path: client.issues if path.startswith("issues?") else []
    )
    monkeypatch.setattr(
        sync, "active_milestone", lambda *_args: {"number": 7, "title": "W02: Week of 2026-11-09"}
    )
    monkeypatch.setattr(sync, "project_item", lambda *_args: "project synced")
    task = parse_tasks(VALID)[0]
    project = ("project", "status", {"todo": "todo", "in progress": "progress", "done": "done"})

    actions = reconcile_tasks(
        client, [task], project, True, datetime.fromisoformat("2026-11-09T12:00:00+01:00")
    )

    assert client.created == 0
    assert issue["state"] == "open"
    assert "<!-- reach-task: app-iteration/W5 -->" in issue["body"]
    assert "Follow PR #39." in issue["body"]
    assert any("reopen unfinished task issue #40" in action for action in actions)


def test_pr_sync_reuses_explicit_issue_and_does_not_close_for_unmerged_pr(monkeypatch):
    import reach_pipeline.github_sync as sync

    issue = {"number": 12, "node_id": "issue-12", "state": "open", "title": "Task", "body": ""}
    client = FakeGitHub()
    monkeypatch.setattr(
        sync, "_all", lambda _client, path: [issue] if path.startswith("issues?") else []
    )
    statuses = []
    monkeypatch.setattr(
        sync,
        "project_item",
        lambda _client, _pid, _fid, _options, _issue, state, _apply: (
            statuses.append(state) or state
        ),
    )
    project = ("project", "status", {"todo": "todo", "in progress": "progress", "done": "done"})
    pr = {
        "number": 25,
        "title": "Improve task",
        "body": "Closes #12",
        "state": "closed",
        "merged": False,
        "base": {"ref": "dev"},
        "head": {"ref": "feature/fix"},
    }

    actions = sync_pr(
        client, pr, project, False, datetime.fromisoformat("2026-11-09T12:00:00+01:00")
    )

    assert any("reuse issue #12" in action for action in actions)
    assert statuses == ["Todo"]
    assert client.created == 0


def test_pr_sync_reports_ambiguous_issues_without_guessing(monkeypatch):
    import reach_pipeline.github_sync as sync

    issues = [{"number": n, "node_id": f"issue-{n}", "state": "open"} for n in (12, 13)]
    client = FakeGitHub()
    monkeypatch.setattr(sync, "_all", lambda _client, _path: issues)
    project = ("project", "status", {"todo": "todo", "in progress": "progress", "done": "done"})
    pr = {
        "number": 25,
        "title": "Task",
        "body": "Fixes #12 and closes #13",
        "state": "open",
        "base": {"ref": "dev"},
        "head": {"ref": "feature/fix"},
    }

    actions = sync_pr(
        client, pr, project, False, datetime.fromisoformat("2026-11-09T12:00:00+01:00")
    )

    assert actions == ["AMBIGUOUS PR #25: candidate issues [12, 13]; add one closing reference"]
    assert client.created == 0


def test_pr_sync_finds_its_generated_issue_after_a_partial_failure(monkeypatch):
    import reach_pipeline.github_sync as sync

    issue = {
        "number": 12,
        "node_id": "issue-12",
        "state": "open",
        "title": "Task",
        "body": "<!-- reach-pr: 25 -->",
    }
    client = FakeGitHub()
    monkeypatch.setattr(sync, "_all", lambda *_args: [issue])
    monkeypatch.setattr(sync, "project_item", lambda *_args: "project synced")
    project = ("project", "status", {"todo": "todo", "in progress": "progress", "done": "done"})
    pr = {
        "number": 25,
        "title": "Task",
        "body": "Details",
        "state": "open",
        "base": {"ref": "dev"},
        "head": {"ref": "feature/task"},
    }

    actions = sync_pr(
        client, pr, project, False, datetime.fromisoformat("2026-11-09T12:00:00+01:00")
    )

    assert any("reuse issue #12" in action for action in actions)
    assert client.created == 0


def test_issue_events_update_tracked_status_without_adding_manual_issues(monkeypatch):
    import reach_pipeline.github_sync as sync

    monkeypatch.setattr(sync, "_all", lambda *_args: [])
    seen = []
    monkeypatch.setattr(
        sync,
        "project_item",
        lambda *_args, **kwargs: (
            seen.append((_args[4], _args[5], kwargs["add_if_missing"])) or "ok"
        ),
    )
    project = ("project", "status", {"todo": "todo", "in progress": "progress", "done": "done"})
    client = FakeGitHub()
    sync_issue(
        client,
        {"number": 12, "node_id": "issue-12", "state": "closed", "body": "<!-- reach-pr: 25 -->"},
        project,
        False,
    )
    manual_result = sync_issue(
        client,
        {"number": 13, "node_id": "issue-13", "state": "closed", "body": "manual"},
        project,
        False,
    )
    assert seen == [
        (
            {
                "number": 12,
                "node_id": "issue-12",
                "state": "closed",
                "body": "<!-- reach-pr: 25 -->",
            },
            "Done",
            True,
        ),
        (
            {"number": 13, "node_id": "issue-13", "state": "closed", "body": "manual"},
            "Done",
            False,
        ),
    ]
    assert manual_result == ["ok"]


def test_draft_pr_and_merged_pr_statuses(monkeypatch):
    import reach_pipeline.github_sync as sync

    client = FakeGitHub()
    project = ("project", "status", {"todo": "todo", "in progress": "progress", "done": "done"})
    issue = {"number": 12, "node_id": "issue-12", "state": "open", "title": "Task", "body": ""}
    monkeypatch.setattr(sync, "_all", lambda _client, _path: [issue])
    statuses = []
    monkeypatch.setattr(
        sync,
        "project_item",
        lambda _c, _p, _f, _o, _i, state, _a: statuses.append(state) or state,
    )
    draft = {
        "number": 25,
        "title": "Task",
        "body": "Tracking issue: #12",
        "state": "open",
        "draft": True,
        "base": {"ref": "dev"},
        "head": {"ref": "feature/task"},
    }
    sync_pr(client, draft, project, False, datetime.fromisoformat("2026-11-09T12:00:00+01:00"))
    issue["state"] = "closed"
    merged = {**draft, "state": "closed", "merged": True, "body": "Closes #12"}
    sync_pr(client, merged, project, False, datetime.fromisoformat("2026-11-09T12:00:00+01:00"))
    assert statuses == ["In progress", "Done"]


def test_pr_without_issue_plans_creation_and_link(monkeypatch):
    import reach_pipeline.github_sync as sync

    client = FakeGitHub()
    monkeypatch.setattr(sync, "_all", lambda *_args: [])
    monkeypatch.setattr(
        sync,
        "active_milestone",
        lambda *_args: {"number": None, "title": "W02: Week of 2026-11-09", "planned_create": True},
    )
    project = ("project", "status", {"todo": "todo", "in progress": "progress", "done": "done"})
    pr = {
        "number": 25,
        "title": "New task",
        "body": "Details",
        "state": "open",
        "base": {"ref": "dev"},
        "head": {"ref": "feature/new"},
    }

    actions = sync_pr(
        client, pr, project, False, datetime.fromisoformat("2026-11-09T12:00:00+01:00")
    )

    assert "create tracking issue for PR #25: New task" in actions
    assert "assign issue to W02: Week of 2026-11-09" in actions
    assert "add issue to Project with status In progress" in actions


def test_active_milestone_reuses_and_rolls_forward_without_fixed_week_numbers(monkeypatch):
    import reach_pipeline.github_sync as sync

    rows = [
        {"number": 17, "title": "W01: Week of 2026-11-02", "state": "closed"},
        {"number": 7, "title": "W02: Week of 2026-11-09", "state": "open"},
    ]
    monkeypatch.setattr(sync, "_all", lambda *_args: rows)
    now = datetime.fromisoformat("2026-11-09T12:00:00+01:00")
    assert active_milestone(FakeGitHub(), now, False)["number"] == 7
    next_week = active_milestone(
        FakeGitHub(), datetime.fromisoformat("2026-11-16T12:00:00+01:00"), False
    )
    assert next_week["title"] == "W03: Week of 2026-11-16"
    assert next_week["due_on"] == "2026-11-23T00:00:00Z"


def test_rollover_carries_only_open_managed_issues(monkeypatch):
    import reach_pipeline.github_sync as sync

    issues = [
        {
            "number": 20,
            "node_id": "20",
            "state": "open",
            "body": "<!-- reach-task: app-iteration/W6 -->",
            "milestone": {"number": 7, "title": "W02: Week of 2026-11-09"},
        },
        {
            "number": 21,
            "node_id": "21",
            "state": "closed",
            "body": "<!-- reach-task: old/W1 -->",
            "milestone": {"number": 7, "title": "W02: Week of 2026-11-09"},
        },
        {
            "number": 22,
            "node_id": "22",
            "state": "open",
            "body": "manual issue",
            "milestone": {"number": 7, "title": "W02: Week of 2026-11-09"},
        },
    ]
    client = FakeGitHub()
    client.issues = issues
    monkeypatch.setattr(
        sync,
        "_all",
        lambda _client, path: issues if path.startswith("issues?") else [],
    )
    monkeypatch.setattr(
        sync,
        "active_milestone",
        lambda *_args: {"number": 8, "title": "W03: Week of 2026-11-16"},
    )
    monkeypatch.setattr(sync, "project_item", lambda *_args: "project synced")

    actions = reconcile_tasks(
        client,
        [],
        ("project", "status", {"todo": "todo", "in progress": "progress", "done": "done"}),
        True,
        datetime.fromisoformat("2026-11-16T12:00:00+01:00"),
    )

    assert any("carry open managed issue #20" in action for action in actions)
    assert all("#21" not in action for action in actions)
    assert all("#22" not in action for action in actions)
    assert issues[0]["milestone"]["number"] == 8
    assert issues[1]["milestone"]["number"] == 7
    assert issues[2]["milestone"]["number"] == 7


def test_project_preflight_requires_unique_project_and_status_options():
    class ProjectClient:
        repository = "IsochroneLabs/reach"

        def graphql(self, _query, _variables):
            return {
                "organization": {
                    "projectsV2": {
                        "nodes": [
                            {
                                "id": "project",
                                "title": "Data Science Project",
                                "fields": {
                                    "nodes": [
                                        {
                                            "id": "status",
                                            "name": "Status",
                                            "options": [{"id": "todo", "name": "Todo"}],
                                        }
                                    ]
                                },
                                "pageInfo": {"hasNextPage": False, "endCursor": None},
                            }
                        ],
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                    }
                }
            }

    with pytest.raises(SyncError, match="missing options"):
        project_preflight(ProjectClient())


def test_project_preflight_fails_when_project_is_missing():
    class ProjectClient:
        repository = "IsochroneLabs/reach"

        def graphql(self, _query, _variables):
            return {
                "organization": {"projectsV2": {"nodes": [], "pageInfo": {"hasNextPage": False}}}
            }

    with pytest.raises(SyncError, match="Expected one organization Project"):
        project_preflight(ProjectClient())


def test_missing_projects_token_fails_before_github_reads(monkeypatch):
    import sys

    import reach_pipeline.github_sync as sync

    monkeypatch.setattr(sys, "argv", ["github_sync", "--mode", "bootstrap"])
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    monkeypatch.delenv("PROJECTS_TOKEN", raising=False)
    with pytest.raises(SyncError, match="PROJECTS_TOKEN is missing"):
        sync.main()


def test_project_item_adds_once_and_updates_each_status():
    class ProjectClient:
        def __init__(self):
            self.item = None
            self.mutations = []

        def graphql(self, query, variables):
            if query.lstrip().startswith("query"):
                return {
                    "node": {
                        "items": {
                            "nodes": [self.item] if self.item else [],
                            "pageInfo": {"hasNextPage": False, "endCursor": None},
                        }
                    }
                }
            self.mutations.append((query, variables))
            if "addProjectV2ItemById" in query:
                self.item = {
                    "id": "item",
                    "content": {"id": "issue-id"},
                    "fieldValues": {"nodes": []},
                }
                return {"addProjectV2ItemById": {"item": {"id": "item"}}}
            option = variables["option"]
            self.item["fieldValues"]["nodes"] = [{"field": {"id": "field"}, "optionId": option}]
            return {"updateProjectV2ItemFieldValue": {"projectV2Item": {"id": "item"}}}

    client = ProjectClient()
    issue = {"number": 12, "node_id": "issue-id"}
    options = {"todo": "todo", "in progress": "progress", "done": "done"}
    for status in ("Todo", "In progress", "Done"):
        project_item(client, "project", "field", options, issue, status, True)
    project_item(client, "project", "field", options, issue, "Done", True)
    assert len(client.mutations) == 4
