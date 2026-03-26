#!/usr/bin/env python3
"""Post-processing for PR Review Bot: Slack notifications, CI wait, re-request review."""

import json
import os
import subprocess
import sys
import time
import urllib.request

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------

CI_WORKFLOW = "ci.yml"
CI_POLL_INTERVAL = 30  # seconds
CI_TIMEOUT = 1200  # 20 minutes


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


SLACK_WEBHOOK_URL = env("SLACK_WEBHOOK_URL")
PR_NUMBER = env("PR_NUMBER")
PR_TITLE = env("PR_TITLE")
PR_URL = env("PR_URL")
PR_HEAD_REF = env("PR_HEAD_REF")
COMMENT_URL = env("COMMENT_URL")
COMMENT_USER = env("COMMENT_USER")
COMMENT_PATH = env("COMMENT_PATH")
COMMENT_LINE = env("COMMENT_LINE")
REPO = env("REPO")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def run(cmd: list[str], input_data: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, input=input_data, capture_output=True, text=True)


def gh_api(method: str, endpoint: str, data: dict | None = None):
    if data:
        result = run(["gh", "api", "-X", method, endpoint, "--input", "-"], json.dumps(data))
    else:
        result = run(["gh", "api", "-X", method, endpoint])
    if result.returncode != 0:
        print(f"gh api error: {result.stderr}", file=sys.stderr)
        return None
    return json.loads(result.stdout) if result.stdout.strip() else None


def send_slack(text: str) -> None:
    if not SLACK_WEBHOOK_URL:
        print("SLACK_WEBHOOK_URL not set, skipping notification", file=sys.stderr)
        return
    payload = json.dumps(
        {"blocks": [{"type": "section", "text": {"type": "mrkdwn", "text": text}}]}
    ).encode()
    req = urllib.request.Request(
        SLACK_WEBHOOK_URL, data=payload, headers={"Content-Type": "application/json"}
    )
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print(f"Slack error: {e}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Detect what Claude did by inspecting git log + PR comments
# ---------------------------------------------------------------------------


def claude_pushed_commits() -> bool:
    """Check if the claude step pushed any new commits."""
    result = run(["git", "log", "--oneline", "-5", "--format=%an|%s"])
    if result.returncode != 0:
        return False
    for line in result.stdout.strip().splitlines():
        if "address review:" in line.lower():
            return True
    return False


def claude_flagged() -> bool:
    """Check if Claude's PR comment indicates a FLAG."""
    comments = gh_api("GET", f"/repos/{REPO}/pulls/{PR_NUMBER}/comments") or []
    for c in reversed(comments):
        if c["user"]["login"].endswith("[bot]") and c.get("in_reply_to_id"):
            body = c.get("body", "").lower()
            if "flag" in body or "too large" in body or "ambiguous" in body or "unsure" in body:
                return True
            if "applied" in body or "committed" in body or "pushed" in body:
                return False
    return False


# ---------------------------------------------------------------------------
# Wait for CI
# ---------------------------------------------------------------------------


def wait_for_ci() -> bool:
    """Wait for the CI workflow to complete on the PR branch. Returns True if passed."""
    print(f"Waiting for CI ({CI_WORKFLOW}) on branch {PR_HEAD_REF}...")

    # Give GitHub time to register the push and start the workflow
    time.sleep(10)

    elapsed = 0

    while elapsed < CI_TIMEOUT:
        result = run([
            "gh", "run", "list",
            "--repo", REPO,
            "--branch", PR_HEAD_REF,
            "--workflow", CI_WORKFLOW,
            "--limit", "1",
            "--json", "databaseId,status,conclusion",
        ])
        if result.returncode == 0 and result.stdout.strip():
            runs = json.loads(result.stdout)
            if runs:
                latest = runs[0]
                run_id = latest["databaseId"]
                status = latest["status"]
                conclusion = latest.get("conclusion")

                if status == "completed":
                    if conclusion == "success":
                        print(f"CI run {run_id} passed")
                        return True
                    else:
                        print(f"CI run {run_id} finished with conclusion: {conclusion}")
                        return False
                else:
                    print(f"CI run {run_id} status: {status} (waiting...)")

        time.sleep(CI_POLL_INTERVAL)
        elapsed += CI_POLL_INTERVAL

    print(f"CI timed out after {CI_TIMEOUT}s")
    return False


# ---------------------------------------------------------------------------
# Re-request review
# ---------------------------------------------------------------------------


def all_comments_addressed() -> bool:
    """Check if all top-level review comments have been addressed by the bot."""
    comments = gh_api("GET", f"/repos/{REPO}/pulls/{PR_NUMBER}/comments") or []

    top_level = [
        c for c in comments
        if not c.get("in_reply_to_id")
        and not c["user"]["login"].endswith("[bot]")
        and c["user"]["login"] != "github-actions"
    ]

    addressed_ids = set()
    for c in comments:
        if c.get("in_reply_to_id") and c["user"]["login"].endswith("[bot]"):
            addressed_ids.add(c["in_reply_to_id"])

    unaddressed = [c for c in top_level if c["id"] not in addressed_ids]
    if unaddressed:
        print(f"{len(unaddressed)} comment(s) still unaddressed")
        return False
    return True


def rerequest_review() -> None:
    print(f"All comments addressed and CI passed. Re-requesting review from @{COMMENT_USER}")
    gh_api(
        "POST",
        f"/repos/{REPO}/pulls/{PR_NUMBER}/requested_reviewers",
        {"reviewers": [COMMENT_USER]},
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    pushed = claude_pushed_commits()
    flagged = claude_flagged()

    print(f"Post-process: pushed={pushed}, flagged={flagged}")

    # Send Slack notification if Claude flagged the comment
    if flagged:
        line_ref = f"{COMMENT_PATH}:{COMMENT_LINE}" if COMMENT_PATH else "N/A"
        send_slack(
            f":mag: *PR Review needs your attention*\n"
            f"*PR:* <{PR_URL}|{PR_TITLE}>\n"
            f"*Comment by:* @{COMMENT_USER}\n"
            f"*File:* `{line_ref}`\n\n"
            f"<{COMMENT_URL}|View comment>"
        )

    # If Claude pushed changes, wait for CI before re-requesting review
    if pushed:
        ci_passed = wait_for_ci()
        if ci_passed and all_comments_addressed():
            rerequest_review()
        elif not ci_passed:
            send_slack(
                f":x: *CI failed after applying review suggestion*\n"
                f"*PR:* <{PR_URL}|{PR_TITLE}>\n"
                f"*Comment by:* @{COMMENT_USER}\n"
                f"<{COMMENT_URL}|View comment>"
            )
    elif flagged and all_comments_addressed():
        rerequest_review()


if __name__ == "__main__":
    main()
