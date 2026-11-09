"""GitHub issue and Project synchronization for reach plans and pull requests."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

MANAGED_START = "<!-- reach-managed:start -->"
MANAGED_END = "<!-- reach-managed:end -->"
TASK_ID = re.compile(r"^[a-z0-9][a-z0-9-]*/[A-Za-z0-9][A-Za-z0-9._-]*$")
MARKER = re.compile(r"<!-- reach-task: ([^\s]+) -->")
METADATA = re.compile(r"^<!-- reach-task\n(.*?)\n-->\s*$", re.S)
PLAN_FILES = {"docs/app_iteration_plan.md", "docs/implementation_plan.md"}
WEEK_TITLE = re.compile(r"^W(\d{2}): Week of (\d{4}-\d{2}-\d{2})$")
BERLIN = ZoneInfo("Europe/Berlin")


class SyncError(RuntimeError):
    """Raised when a plan or GitHub preflight is invalid."""


@dataclass(frozen=True)
class Task:
    task_id: str
    title: str
    summary: str
    criteria: tuple[str, ...]
    owner: str | None = None
    target_date: str | None = None
    dependencies: tuple[str, ...] = ()

    def managed_body(self) -> str:
        criteria = "\n".join(f"- [ ] {item}" for item in self.criteria)
        deps = ", ".join(self.dependencies) if self.dependencies else "None"
        return (
            f"{MANAGED_START}\n<!-- reach-task: {self.task_id} -->\n\n"
            f"## Summary\n{self.summary}\n\n## Acceptance criteria\n{criteria}\n\n"
            f"## Tracking metadata\n- Owner: {self.owner or 'Unassigned'}\n"
            f"- Target date: {self.target_date or 'Unscheduled'}\n"
            f"- Dependencies: {deps}\n{MANAGED_END}"
        )


def parse_tasks(markdown: str, source: str = "plan") -> list[Task]:
    """Parse task metadata comments immediately following H3 package headings."""
    lines = markdown.splitlines()
    tasks: list[Task] = []
    ids: set[str] = set()
    for index, line in enumerate(lines):
        if not line.startswith("### "):
            continue
        if index + 1 >= len(lines) or not lines[index + 1].startswith("<!-- reach-task"):
            continue
        heading = line[4:].strip()
        metadata_end = index + 1
        while metadata_end < len(lines) and "-->" not in lines[metadata_end]:
            metadata_end += 1
        metadata_text = "\n".join(lines[index + 1 : metadata_end + 1]).strip()
        match = METADATA.fullmatch(metadata_text)
        if not match:
            raise SyncError(f"{source}: malformed task metadata after heading '{heading}'")
        fields: dict[str, str] = {}
        for item in match.group(1).splitlines():
            if ":" not in item:
                raise SyncError(f"{source}: malformed metadata line {item!r}")
            key, value = item.split(":", 1)
            key, value = key.strip(), value.strip()
            if key not in {"id", "owner", "target_date", "depends_on"} or key in fields:
                raise SyncError(f"{source}: unknown or repeated metadata key {key!r}")
            fields[key] = value
        task_id = fields.get("id", "")
        if not TASK_ID.fullmatch(task_id):
            raise SyncError(f"{source}: missing or invalid task id after '{heading}'")
        if task_id in ids:
            raise SyncError(f"{source}: duplicate task id {task_id!r}")
        ids.add(task_id)
        owner = fields.get("owner") or None
        if owner and not re.fullmatch(r"[A-Za-z0-9-]+", owner):
            raise SyncError(f"{source}: invalid owner for {task_id}")
        target = fields.get("target_date") or None
        if target:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", target):
                raise SyncError(f"{source}: target_date must use YYYY-MM-DD for {task_id}")
            try:
                date.fromisoformat(target)
            except ValueError as exc:
                raise SyncError(f"{source}: invalid target_date for {task_id}") from exc
        deps = tuple(x.strip() for x in fields.get("depends_on", "").split(",") if x.strip())
        if any(not TASK_ID.fullmatch(dep) for dep in deps):
            raise SyncError(f"{source}: invalid dependency for {task_id}")
        end = metadata_end + 1
        while end < len(lines) and not lines[end].startswith("### "):
            end += 1
        block = lines[metadata_end + 1 : end]
        summary = _section_text(block, "Summary") or _opening_summary(block)
        criteria = _section_items(block, {"Done when", "Acceptance criteria"}) or _bold_criteria(
            block
        )
        if not summary:
            raise SyncError(f"{source}: task {task_id} has no Summary section")
        if not criteria:
            raise SyncError(f"{source}: task {task_id} has no Done when / Acceptance criteria")
        tasks.append(Task(task_id, heading, summary, tuple(criteria), owner, target, deps))
    return tasks


def _section_text(lines: list[str], heading: str) -> str:
    start = next((i for i, line in enumerate(lines) if line.strip() == f"## {heading}"), None)
    if start is None:
        return ""
    out: list[str] = []
    for line in lines[start + 1 :]:
        if line.startswith("## ") or line.startswith("### "):
            break
        if line.strip():
            out.append(line.strip())
    return "\n".join(out)


def _section_items(lines: list[str], headings: set[str]) -> list[str]:
    start = next(
        (i for i, line in enumerate(lines) if line.strip() in {f"## {h}" for h in headings}), None
    )
    if start is None:
        return []
    result: list[str] = []
    for line in lines[start + 1 :]:
        if line.startswith("## ") or line.startswith("### "):
            break
        item = re.match(r"^\s*[-*] \[[ xX]\] (.+)$", line)
        if item:
            result.append(item.group(1).strip())
    return result


def _opening_summary(lines: list[str]) -> str:
    paragraphs: list[str] = []
    for line in lines:
        if not line.strip():
            if paragraphs:
                break
            continue
        if line.startswith(("1.", "2.", "3.", "**Done when:**", "**Done when**:")):
            break
        paragraphs.append(line.strip())
    return " ".join(paragraphs)


def _bold_criteria(lines: list[str]) -> list[str]:
    start = next(
        (
            i
            for i, line in enumerate(lines)
            if re.match(r"^\*\*Done when:?\*\*", line.strip(), re.I)
        ),
        None,
    )
    if start is None:
        return []
    initial = re.sub(r"^\*\*Done when:?\*\*\s*", "", lines[start].strip(), flags=re.I)
    result = [initial] if initial else []
    for line in lines[start + 1 :]:
        if line.startswith("### ") or line.strip().startswith("**") or not line.strip():
            break
        item = re.match(r"^\s*[-*] \[[ xX]\] (.+)$", line)
        if item:
            result.append(item.group(1).strip())
        elif result:
            result[-1] = f"{result[-1]} {line.strip()}"
    return result


def replace_managed_body(body: str, managed: str) -> str:
    """Replace only the marked section, retaining all human-written text around it."""
    if MANAGED_START in body or MANAGED_END in body:
        if body.count(MANAGED_START) != 1 or body.count(MANAGED_END) != 1:
            raise SyncError("issue body has malformed managed-section markers")
        start, end = body.index(MANAGED_START), body.index(MANAGED_END) + len(MANAGED_END)
        if start > end:
            raise SyncError("issue body has reversed managed-section markers")
        return body[:start] + managed + body[end:]
    return f"{body.rstrip()}\n\n{managed}" if body.strip() else managed


def week_for(now: datetime) -> tuple[date, date]:
    """Return Monday in Europe/Berlin and the following Monday."""
    local = now.astimezone(BERLIN).date()
    monday = local - timedelta(days=local.weekday())
    return monday, monday + timedelta(days=7)


class GitHub:
    """Small standard-library GitHub REST and GraphQL client."""

    def __init__(
        self, token: str, repository: str, api_url: str = "https://api.github.com"
    ) -> None:
        self.token, self.repository, self.api_url = token, repository, api_url.rstrip("/")
        self.graphql_token = token

    def request(self, method: str, path: str, data: dict | None = None) -> dict | list:
        url = path if path.startswith("https://") else f"{self.api_url}{path}"
        payload = json.dumps(data).encode() if data is not None else None
        req = urllib.request.Request(url, data=payload, method=method)
        req.add_header(
            "Authorization",
            f"Bearer {self.graphql_token if url.endswith('/graphql') else self.token}",
        )
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("X-GitHub-Api-Version", "2022-11-28")
        if payload:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                return json.loads(response.read())
        except (urllib.error.HTTPError, urllib.error.URLError) as exc:
            raise SyncError(f"GitHub API {method} {url} failed: {exc}") from exc

    def graphql(self, query: str, variables: dict) -> dict:
        result = self.request(
            "POST", "https://api.github.com/graphql", {"query": query, "variables": variables}
        )
        if result.get("errors"):
            raise SyncError(f"GitHub Project API preflight failed: {result['errors']}")
        return result["data"]


def _rest(client: GitHub, method: str, path: str, data: dict | None = None) -> dict | list:
    return client.request(method, f"/repos/{client.repository}/{path.lstrip('/')}", data)


def _legacy_package_issue(task: Task, issues: list[dict]) -> list[dict]:
    """Find a pre-marker issue by its unambiguous package key during bootstrap."""
    package = task.task_id.rsplit("/", 1)[-1]
    pattern = re.compile(rf"^{re.escape(package)}(?:\s*[:—–-]|$)", re.I)
    return [
        issue
        for issue in issues
        if "pull_request" not in issue and pattern.search(issue.get("title", ""))
    ]


def _all(client: GitHub, path: str) -> list[dict]:
    result: list[dict] = []
    page = 1
    while True:
        rows = _rest(client, "GET", f"{path}{'&' if '?' in path else '?'}per_page=100&page={page}")
        result.extend(rows)
        if len(rows) < 100:
            return result
        page += 1


def active_milestone(client: GitHub, now: datetime, apply: bool) -> dict:
    monday, next_monday = week_for(now)
    milestones = _all(client, "milestones?state=all")
    weekly = [(WEEK_TITLE.match(m["title"]), m) for m in milestones]
    anchors = [
        (int(match.group(1)), date.fromisoformat(match.group(2))) for match, _ in weekly if match
    ]
    week = 1
    if anchors:
        anchor_number, anchor_date = min(anchors, key=lambda item: abs((item[1] - monday).days))
        delta = (monday - anchor_date).days
        if delta % 7:
            raise SyncError("weekly milestone dates are not aligned to Mondays")
        week = anchor_number + delta // 7
    if week < 1:
        raise SyncError("calculated weekly milestone number is invalid")
    title = f"W{week:02d}: Week of {monday.isoformat()}"
    found = [m for m in milestones if m["title"] == title]
    if found:
        if found[0]["state"] != "open":
            if not apply:
                return {**found[0], "planned_reopen": True}
            updated = _rest(client, "PATCH", f"milestones/{found[0]['number']}", {"state": "open"})
            return {**updated, "reopened": True}
        return found[0]
    if not apply:
        return {
            "number": None,
            "title": title,
            "state": "planned",
            "planned_create": True,
            "due_on": f"{next_monday.isoformat()}T00:00:00Z",
        }
    created = _rest(
        client,
        "POST",
        "milestones",
        {
            "title": title,
            "description": "Weekly planning milestone; due on the Monday meeting date.",
            "due_on": f"{next_monday.isoformat()}T00:00:00Z",
        },
    )
    return {**created, "created": True}


def project_item(
    client: GitHub,
    project_id: str,
    status_field: str,
    options: dict[str, str],
    issue: dict,
    status: str,
    apply: bool,
    add_if_missing: bool = True,
) -> str:
    query = """query($id:ID!,$cursor:String) {
      node(id:$id) { ... on ProjectV2 {
        items(first:100,after:$cursor) { nodes {
          id content { ... on Issue { id number } }
          fieldValues(first:50) { nodes {
            ... on ProjectV2ItemFieldSingleSelectValue {
              field { ... on ProjectV2FieldCommon { id } } optionId
            }
          } }
        } pageInfo { hasNextPage endCursor } }
      } }
    }"""
    nodes: list[dict] = []
    cursor = None
    while True:
        connection = client.graphql(query, {"id": project_id, "cursor": cursor})["node"]["items"]
        nodes.extend(connection["nodes"])
        if not connection["pageInfo"]["hasNextPage"]:
            break
        cursor = connection["pageInfo"]["endCursor"]
    row = next(
        (item for item in nodes if item.get("content", {}).get("id") == issue["node_id"]), None
    )
    if row is None:
        if not add_if_missing:
            return f"issue #{issue['number']} is not on the Project"
        if not apply:
            return f"add issue #{issue['number']} to Project with status {status}"
        row = client.graphql(
            """mutation($project:ID!,$content:ID!) {
              addProjectV2ItemById(input:{projectId:$project,contentId:$content}) { item { id } }
            }""",
            {"project": project_id, "content": issue["node_id"]},
        )["addProjectV2ItemById"]["item"]
    desired = options[status.casefold()]
    if any(
        v.get("field", {}).get("id") == status_field and v.get("optionId") == desired
        for v in row.get("fieldValues", {}).get("nodes", [])
    ):
        return f"Project status already {status} for issue #{issue['number']}"
    if not apply:
        return f"set Project status {status} for issue #{issue['number']}"
    client.graphql(
        """mutation($project:ID!,$item:ID!,$field:ID!,$option:String!) {
          updateProjectV2ItemFieldValue(input:{projectId:$project,itemId:$item,fieldId:$field,
            value:{singleSelectOptionId:$option}}) { projectV2Item { id } }
        }""",
        {"project": project_id, "item": row["id"], "field": status_field, "option": desired},
    )
    return f"set Project status {status} for issue #{issue['number']}"


def reconcile_tasks(
    client: GitHub,
    tasks: list[Task],
    project: tuple[str, str, dict[str, str]],
    apply: bool,
    now: datetime,
) -> list[str]:
    project_id, status_field, options = project
    milestone = active_milestone(client, now, apply)
    actions: list[str] = []
    if milestone.get("planned_create") or milestone.get("created"):
        actions.append(
            f"create milestone {milestone['title']} due {milestone.get('due_on', 'next Monday')}"
        )
    if milestone.get("planned_reopen") or milestone.get("reopened"):
        actions.append(f"reopen milestone {milestone['title']}")
    issues = _all(client, "issues?state=all")
    open_prs = [
        p for p in _all(client, "pulls?state=open") if p.get("base", {}).get("ref") == "dev"
    ]
    by_task: dict[str, list[dict]] = {}
    processed_issue_numbers: set[int] = set()
    for issue in issues:
        if "pull_request" in issue:
            continue
        for task_id in MARKER.findall(issue.get("body") or ""):
            by_task.setdefault(task_id, []).append(issue)
    desired_ids = {t.task_id for t in tasks}
    removed = sorted(set(by_task) - desired_ids)
    for task_id in removed:
        actions.append(f"REVIEW: plan task {task_id} was removed; leave issue(s) open")
    for task in tasks:
        found = by_task.get(task.task_id, [])
        if not found:
            found = _legacy_package_issue(task, issues)
        if len(found) > 1:
            raise SyncError(f"multiple issues carry task marker {task.task_id}")
        body = task.managed_body()
        if found:
            issue = found[0]
            if issue["state"] != "open":
                actions.append(f"reopen unfinished task issue #{issue['number']} ({task.task_id})")
                if apply:
                    issue = _rest(client, "PATCH", f"issues/{issue['number']}", {"state": "open"})
            if task.owner and task.owner not in {
                assignee.get("login") for assignee in issue.get("assignees", [])
            }:
                actions.append(f"assign issue #{issue['number']} to @{task.owner}")
                if apply:
                    _rest(
                        client,
                        "POST",
                        f"issues/{issue['number']}/assignees",
                        {"assignees": [task.owner]},
                    )
            merged_body = replace_managed_body(issue.get("body") or "", body)
            if merged_body != (issue.get("body") or "") or issue.get("title") != task.title:
                actions.append(
                    f"update managed section/title of issue #{issue['number']} ({task.task_id})"
                )
                if apply:
                    _rest(
                        client,
                        "PATCH",
                        f"issues/{issue['number']}",
                        {"body": merged_body, "title": task.title},
                    )
        else:
            issue = {
                "number": None,
                "node_id": None,
                "state": "open",
                "title": task.title,
                "body": body,
            }
            actions.append(f"create issue: {task.title} ({task.task_id})")
            if milestone.get("planned_create"):
                actions.append(f"assign new issue {task.task_id} to {milestone['title']}")
            if apply:
                payload = {"title": task.title, "body": body}
                if task.owner:
                    payload["assignees"] = [task.owner]
                issue = _rest(client, "POST", "issues", payload)
        if issue.get("number") is None:
            if not apply:
                actions.append(f"add new issue {task.task_id} to Project with status Todo")
            continue
        processed_issue_numbers.add(issue["number"])
        if (
            issue.get("state") == "open"
            and (issue.get("milestone") or {}).get("title") != milestone["title"]
        ):
            actions.append(f"move open issue #{issue['number']} to {milestone['title']}")
            if apply:
                _rest(
                    client, "PATCH", f"issues/{issue['number']}", {"milestone": milestone["number"]}
                )
        package_key = task.task_id.rsplit("/", 1)[-1]
        linked = any(
            issue.get("number")
            in (
                parse_issue_refs(p.get("body") or "")
                | {int(n) for n in re.findall(r"(?i)tracking issue:\s*#(\d+)", p.get("body") or "")}
                | branch_issue_refs(p.get("head", {}).get("ref", ""))
            )
            or bool(
                re.search(rf"(?i)(?:pull request|PR)\s*#?{p['number']}\b", issue.get("body", ""))
            )
            or bool(
                re.search(
                    rf"\b{re.escape(package_key)}\b",
                    f"{p.get('title', '')} {p.get('body', '')}",
                    re.I,
                )
            )
            for p in open_prs
        )
        status = "Done" if issue["state"] == "closed" else "In progress" if linked else "Todo"
        actions.append(
            project_item(client, project_id, status_field, options, issue, status, apply)
        )
    # At rollover, move every still-open automation-managed task, including PR-originated work.
    open_issue_numbers: set[int] = set()
    for open_pr in open_prs:
        text = open_pr.get("body") or ""
        open_issue_numbers.update(parse_issue_refs(text))
        open_issue_numbers.update(int(n) for n in re.findall(r"(?i)tracking issue:\s*#(\d+)", text))
        open_issue_numbers.update(branch_issue_refs(open_pr.get("head", {}).get("ref", "")))
    for issue in issues:
        if "pull_request" in issue or issue["state"] != "open":
            continue
        body = issue.get("body") or ""
        if not (MARKER.search(body) or re.search(r"<!-- reach-pr: \d+ -->", body)):
            continue
        if issue["number"] in processed_issue_numbers:
            continue
        if (issue.get("milestone") or {}).get("title") != milestone["title"]:
            actions.append(f"carry open managed issue #{issue['number']} to {milestone['title']}")
            if apply:
                _rest(
                    client, "PATCH", f"issues/{issue['number']}", {"milestone": milestone["number"]}
                )
        status = "In progress" if issue["number"] in open_issue_numbers else "Todo"
        actions.append(
            project_item(client, project_id, status_field, options, issue, status, apply)
        )
    return actions


def parse_issue_refs(text: str) -> set[int]:
    return {
        int(value)
        for value in re.findall(r"(?i)\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(\d+)\b", text)
    }


def branch_issue_refs(branch: str) -> set[int]:
    return {
        int(value) for value in re.findall(r"(?:^|[/_-])(?:issue-?)?(\d+)(?:[/_-]|$)", branch, re.I)
    }


def sync_pr(
    client: GitHub, pr: dict, project: tuple[str, str, dict[str, str]], apply: bool, now: datetime
) -> list[str]:
    if pr.get("base", {}).get("ref") != "dev":
        return [f"ignore PR #{pr.get('number')}: base is not dev"]
    number = pr["number"]
    body = pr.get("body") or ""
    refs = parse_issue_refs(body)
    refs.update(int(value) for value in re.findall(r"(?i)tracking issue:\s*#(\d+)", body))
    branch = pr.get("head", {}).get("ref", "")
    branch_refs = branch_issue_refs(branch)
    candidates = refs | branch_refs
    issues = _all(client, "issues?state=all")
    known = {row["number"]: row for row in issues if "pull_request" not in row}
    # Bootstrap migration: legacy task issues may already name the PR before either side had a
    # stable marker. Also recognize the package shorthand in a PR's plan description.
    package_keys = set(
        re.findall(r"\b(?:W\d{1,2}[a-z]?|P\d{1,2})\b", f"{pr.get('title', '')} {body}", re.I)
    )
    for issue_number, row in known.items():
        text = row.get("body") or ""
        generated_for_pr = bool(re.search(rf"<!-- reach-pr: {number} -->", text))
        mentioned_pr = bool(re.search(rf"(?i)(?:pull request|PR)\s*#?{number}\b", text))
        title_key = re.match(
            r"^((?:W\d{1,2}[a-z]?|P\d{1,2}))(?=\s*[:—–-]|$)", row.get("title", ""), re.I
        )
        if (
            generated_for_pr
            or mentioned_pr
            or (
                pr.get("state") == "open"
                and title_key
                and title_key.group(1).casefold() in {key.casefold() for key in package_keys}
            )
        ):
            candidates.add(issue_number)
    candidates &= known.keys()
    if len(candidates) > 1:
        return [
            f"AMBIGUOUS PR #{number}: candidate issues {sorted(candidates)}; "
            "add one closing reference"
        ]
    if not candidates and pr.get("state") != "open":
        return [f"ignore closed PR #{number} without an existing tracking issue"]
    milestone = active_milestone(client, now, apply)
    project_id, status_field, options = project
    if candidates:
        issue = known[next(iter(candidates))]
        actions = [f"reuse issue #{issue['number']} for PR #{number}"]
        if milestone.get("planned_create") or milestone.get("created"):
            actions.append(
                f"create milestone {milestone['title']} due "
                f"{milestone.get('due_on', 'next Monday')}"
            )
        if milestone.get("planned_reopen") or milestone.get("reopened"):
            actions.append(f"reopen milestone {milestone['title']}")
        if (
            issue["state"] == "open"
            and (issue.get("milestone") or {}).get("title") != milestone["title"]
        ):
            actions.append(f"move open issue #{issue['number']} to {milestone['title']}")
            if apply:
                _rest(
                    client,
                    "PATCH",
                    f"issues/{issue['number']}",
                    {"milestone": milestone["number"]},
                )
        if not parse_issue_refs(body) and not re.search(
            rf"(?i)tracking issue:\s*#{issue['number']}\b", body
        ):
            actions.append(f"link PR #{number} to issue #{issue['number']} in the PR body")
            if apply:
                _rest(
                    client,
                    "PATCH",
                    f"pulls/{number}",
                    {"body": f"{body.rstrip()}\n\nTracking issue: #{issue['number']}"},
                )
    else:
        title = pr["title"]
        text_body = (
            f"{body.strip()}\n\nTracking pull request: #{number}.\n<!-- reach-pr: {number} -->"
        )
        actions = [f"create tracking issue for PR #{number}: {title}"]
        if milestone.get("planned_create") or milestone.get("created"):
            actions.append(
                f"create milestone {milestone['title']} due "
                f"{milestone.get('due_on', 'next Monday')}"
            )
        if milestone.get("planned_reopen") or milestone.get("reopened"):
            actions.append(f"reopen milestone {milestone['title']}")
        if not apply:
            return actions + [
                "add issue reference to PR body",
                f"assign issue to {milestone['title']}",
                "add issue to Project with status In progress",
            ]
        issue = _rest(
            client,
            "POST",
            "issues",
            {"title": title, "body": text_body, "milestone": milestone["number"]},
        )
        linked_body = f"{body.rstrip()}\n\nTracking issue: #{issue['number']}"
        _rest(client, "PATCH", f"pulls/{number}", {"body": linked_body})
    status = (
        "Done"
        if issue["state"] == "closed"
        else "In progress"
        if pr.get("state") == "open"
        else "Todo"
    )
    actions.append(project_item(client, project_id, status_field, options, issue, status, apply))
    if pr.get("merged") and not parse_issue_refs(body):
        actions.append(f"REVIEW: merged PR #{number} has no closing reference; issue remains open")
    return actions


def sync_issue(
    client: GitHub,
    issue: dict,
    project: tuple[str, str, dict[str, str]],
    apply: bool,
) -> list[str]:
    """Update a tracked issue's Project status when its state or linked PRs change."""
    if "pull_request" in issue:
        return []
    body = issue.get("body") or ""
    managed = bool(MARKER.search(body) or re.search(r"<!-- reach-pr: \d+ -->", body))
    open_prs = [
        p for p in _all(client, "pulls?state=open") if p.get("base", {}).get("ref") == "dev"
    ]
    linked = any(
        issue["number"]
        in (
            parse_issue_refs(p.get("body") or "")
            | {int(n) for n in re.findall(r"(?i)tracking issue:\s*#(\d+)", p.get("body") or "")}
            | branch_issue_refs(p.get("head", {}).get("ref", ""))
        )
        for p in open_prs
    )
    status = "Done" if issue["state"] == "closed" else "In progress" if linked else "Todo"
    project_id, status_field, options = project
    result = project_item(
        client, project_id, status_field, options, issue, status, apply, add_if_missing=managed
    )
    return [result]


def bootstrap_weekly_project(
    client: GitHub,
    project: tuple[str, str, dict[str, str]],
    apply: bool,
    now: datetime,
) -> list[str]:
    """Add issues already in the active weekly milestone to the Project, once."""
    project_id, status_field, options = project
    milestone = active_milestone(client, now, apply)
    if milestone.get("number") is None:
        raise SyncError("bootstrap cannot resolve the active milestone number")
    open_prs = [
        p for p in _all(client, "pulls?state=open") if p.get("base", {}).get("ref") == "dev"
    ]
    linked_numbers: set[int] = set()
    for pr in open_prs:
        body = pr.get("body") or ""
        linked_numbers.update(parse_issue_refs(body))
        linked_numbers.update(int(n) for n in re.findall(r"(?i)tracking issue:\s*#(\d+)", body))
        linked_numbers.update(branch_issue_refs(pr.get("head", {}).get("ref", "")))
    actions: list[str] = []
    if milestone.get("planned_create") or milestone.get("created"):
        actions.append(
            f"create milestone {milestone['title']} due {milestone.get('due_on', 'next Monday')}"
        )
    if milestone.get("planned_reopen") or milestone.get("reopened"):
        actions.append(f"reopen milestone {milestone['title']}")
    for issue in _all(client, "issues?state=all"):
        if (
            "pull_request" in issue
            or (issue.get("milestone") or {}).get("number") != milestone["number"]
        ):
            continue
        status = (
            "Done"
            if issue["state"] == "closed"
            else "In progress"
            if issue["number"] in linked_numbers
            else "Todo"
        )
        actions.append(
            project_item(client, project_id, status_field, options, issue, status, apply)
        )
    return actions


def project_preflight(client: GitHub) -> tuple[str, str, dict[str, str]]:
    """Resolve exactly one organization Project and all required Status options."""
    projects: list[dict] = []
    cursor = None
    while True:
        data = client.graphql(
            """query($org:String!,$cursor:String) { organization(login:$org) {
              projectsV2(first:100,after:$cursor) { nodes { id title fields(first:50) { nodes {
                ... on ProjectV2SingleSelectField { id name options { id name } }
              } } pageInfo { hasNextPage endCursor } } } } }""",
            {"org": client.repository.split("/")[0], "cursor": cursor},
        )
        connection = data["organization"]["projectsV2"]
        projects.extend(p for p in connection["nodes"] if p["title"] == "Data Science Project")
        if not connection["pageInfo"]["hasNextPage"]:
            break
        cursor = connection["pageInfo"]["endCursor"]
    if len(projects) != 1:
        raise SyncError(
            f"Expected one organization Project 'Data Science Project'; found {len(projects)}"
        )
    project = projects[0]
    fields = [f for f in project["fields"]["nodes"] if f.get("name", "").casefold() == "status"]
    if len(fields) != 1:
        raise SyncError("Project must have exactly one Status field")
    options = {o["name"].casefold(): o["id"] for o in fields[0]["options"]}
    missing = {"todo", "in progress", "done"} - set(options)
    if missing:
        raise SyncError(f"Project Status field is missing options: {', '.join(sorted(missing))}")
    return project["id"], fields[0]["id"], options


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("plans", "pr", "issue", "bootstrap"), required=True)
    parser.add_argument("--apply", action="store_true", help="write changes; default is dry-run")
    parser.add_argument("--plan", action="append", default=[])
    parser.add_argument("--event", default=os.getenv("GITHUB_EVENT_PATH"))
    parser.add_argument("--now", help="override current time in ISO-8601 for tests")
    args = parser.parse_args()
    now = datetime.fromisoformat(args.now) if args.now else datetime.now(BERLIN)
    tasks: list[Task] = []
    if args.mode in {"plans", "bootstrap"}:
        files = args.plan or sorted(PLAN_FILES)
        for name in files:
            if name not in PLAN_FILES:
                raise SyncError(f"unapproved plan path: {name}")
            tasks.extend(parse_tasks(Path(name).read_text(), name))
        by_id = {task.task_id for task in tasks}
        if len(by_id) != len(tasks):
            raise SyncError("duplicate task IDs across approved plan files")
        unknown = sorted({dep for task in tasks for dep in task.dependencies} - by_id)
        if unknown:
            raise SyncError(f"unresolved task dependencies: {', '.join(unknown)}")
    event = json.loads(Path(args.event).read_text()) if args.event else {}
    pr = event.get("pull_request", {})
    issue_event = event.get("issue", {})
    if args.mode == "pr" and not pr:
        raise SyncError("event does not contain a pull_request")
    if args.mode == "issue" and not issue_event:
        raise SyncError("event does not contain an issue")
    repo = os.environ.get("GITHUB_REPOSITORY", "IsochroneLabs/reach")
    token = os.environ.get("GITHUB_TOKEN")
    project_token = os.environ.get("PROJECTS_TOKEN")
    if not project_token:
        raise SyncError(
            "PROJECTS_TOKEN is missing. Add an Actions secret scoped to IsochroneLabs "
            "organization Projects write; no issue or milestone changes were made."
        )
    if not token:
        raise SyncError("GITHUB_TOKEN is unavailable; no changes were made")
    client = GitHub(token, repo)
    client.graphql_token = project_token
    project = project_preflight(client)
    actions: list[str] = []
    if args.mode in {"plans", "bootstrap"}:
        actions.extend(reconcile_tasks(client, tasks, project, args.apply, now))
    if args.mode == "pr":
        actions.extend(sync_pr(client, pr, project, args.apply, now))
    if args.mode == "issue":
        actions.extend(sync_issue(client, issue_event, project, args.apply))
    if args.mode == "bootstrap":
        for item in _all(client, "pulls?state=all"):
            if item.get("base", {}).get("ref") == "dev":
                actions.extend(sync_pr(client, item, project, args.apply, now))
        actions.extend(bootstrap_weekly_project(client, project, args.apply, now))
    print(json.dumps({"mode": args.mode, "apply": args.apply, "actions": actions}, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SyncError as error:
        print(f"github-sync: {error}", file=sys.stderr)
        raise SystemExit(2) from error
