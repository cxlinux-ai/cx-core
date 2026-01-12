#!/usr/bin/env python3
"""
CLA Enforcement Script for GitHub Pull Requests
Checks all commit authors against a CLA signer list.
"""

import json
import os
import re
import sys

import requests

# Configuration
GITHUB_API = "https://api.github.com"
CLA_FILE = ".github/cla-signers.json"
CLA_DOC_URL = "https://github.com/cortexlinux/cortex/blob/main/CLA.md"
CLA_SIGN_ISSUE_URL = "https://github.com/cortexlinux/cortex/issues/new?template=cla-signature.yml"


def get_env(key: str) -> str:
    value = os.environ.get(key)
    if not value:
        print(f"Error: {key} environment variable not set")
        sys.exit(1)
    return value


def github_request(endpoint: str, token: str) -> dict:
    """Make authenticated GitHub API request."""
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
    }
    url = f"{GITHUB_API}/{endpoint}" if not endpoint.startswith("http") else endpoint
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json()


def github_post(endpoint: str, token: str, data: dict) -> dict:
    """Make authenticated GitHub API POST request."""
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
    }
    url = f"{GITHUB_API}/{endpoint}"
    response = requests.post(url, headers=headers, json=data)
    response.raise_for_status()
    return response.json()


def normalize_email(email: str) -> str:
    """Normalize email for comparison."""
    if not email:
        return ""
    email = email.lower().strip()
    # Handle GitHub noreply emails
    # Format: 12345678+username@users.noreply.github.com
    noreply_match = re.match(r"(\d+\+)?(.+)@users\.noreply\.github\.com", email)
    if noreply_match:
        return f"{noreply_match.group(2)}@github.noreply"
    return email


def extract_co_authors(message: str) -> list[tuple[str, str]]:
    """Extract co-authors from commit message."""
    co_authors = []
    pattern = r"Co-authored-by:\s*(.+?)\s*<(.+?)>"
    for match in re.finditer(pattern, message, re.IGNORECASE):
        name, email = match.groups()
        co_authors.append((name.strip(), email.strip()))
    return co_authors


def load_cla_signers() -> dict:
    """Load CLA signers from JSON file."""
    try:
        with open(CLA_FILE) as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Warning: {CLA_FILE} not found, creating empty signer list")
        return {"individuals": [], "corporations": {}}
    except json.JSONDecodeError as e:
        print(f"Error parsing {CLA_FILE}: {e}")
        sys.exit(1)


def is_signer(username: str | None, email: str, signers: dict) -> tuple[bool, str | None]:
    """
    Check if a user has signed the CLA.
    Returns (is_signed, signing_entity).
    """
    normalized_email = normalize_email(email)
    username_lower = username.lower() if username else None

    # Check individual signers
    for signer in signers.get("individuals", []):
        signer_username = signer.get("github_username", "").lower()
        signer_emails = [normalize_email(e) for e in signer.get("emails", [])]

        if username_lower and signer_username == username_lower:
            return True, f"@{username}"
        if normalized_email in signer_emails:
            return True, signer.get("name", email)

    # Check corporate signers
    for corp_name, corp_data in signers.get("corporations", {}).items():
        corp_emails = [normalize_email(e) for e in corp_data.get("emails", [])]
        corp_domains = corp_data.get("domains", [])
        corp_members = [m.lower() for m in corp_data.get("github_usernames", [])]

        # Check by username
        if username_lower and username_lower in corp_members:
            return True, f"{corp_name} (corporate)"

        # Check by email
        if normalized_email in corp_emails:
            return True, f"{corp_name} (corporate)"

        # Check by email domain
        email_domain = normalized_email.split("@")[-1] if "@" in normalized_email else ""
        if email_domain in corp_domains:
            return True, f"{corp_name} (corporate domain)"

    return False, None


def get_pr_authors(owner: str, repo: str, pr_number: int, token: str) -> list[dict]:
    """
    Get all unique authors from PR commits.
    Returns list of {username, email, name, source}.
    """
    authors = {}

    # Get PR commits
    commits = github_request(f"repos/{owner}/{repo}/pulls/{pr_number}/commits?per_page=100", token)

    for commit in commits:
        sha = commit["sha"]
        commit_data = commit.get("commit", {})

        # Primary author
        author_data = commit_data.get("author", {})
        author_email = author_data.get("email", "")
        author_name = author_data.get("name", "")

        # Get GitHub username if available
        gh_author = commit.get("author")
        author_username = gh_author.get("login") if gh_author else None

        if author_email:
            key = normalize_email(author_email)
            if key and key not in authors:
                authors[key] = {
                    "username": author_username,
                    "email": author_email,
                    "name": author_name,
                    "source": f"commit {sha[:7]}",
                }

        # Committer (if different)
        committer_data = commit_data.get("committer", {})
        committer_email = committer_data.get("email", "")
        committer_name = committer_data.get("name", "")
        gh_committer = commit.get("committer")
        committer_username = gh_committer.get("login") if gh_committer else None

        # Skip GitHub's web-flow committer
        if committer_email and "noreply@github.com" not in committer_email:
            key = normalize_email(committer_email)
            if key and key not in authors:
                authors[key] = {
                    "username": committer_username,
                    "email": committer_email,
                    "name": committer_name,
                    "source": f"committer {sha[:7]}",
                }

        # Co-authors from commit message
        message = commit_data.get("message", "")
        for co_name, co_email in extract_co_authors(message):
            key = normalize_email(co_email)
            if key and key not in authors:
                authors[key] = {
                    "username": None,
                    "email": co_email,
                    "name": co_name,
                    "source": f"co-author {sha[:7]}",
                }

    return list(authors.values())


def post_comment(
    owner: str,
    repo: str,
    pr_number: int,
    token: str,
    missing_authors: list[dict],
    signed_authors: list[tuple[dict, str]],
) -> None:
    """Post or update CLA status comment on PR."""
    # Build comment body
    lines = ["## CLA Verification Failed\n"]
    lines.append("The following contributors have not signed the ")
    lines.append(f"[Contributor License Agreement]({CLA_DOC_URL}):\n\n")

    for author in missing_authors:
        username = author.get("username")
        name = author.get("name", "Unknown")
        email = author.get("email", "")
        if username:
            lines.append(f"- **@{username}** ({name}, `{email}`)\n")
        else:
            lines.append(f"- **{name}** (`{email}`)\n")

    lines.append("\n### How to Sign\n\n")
    lines.append("1. Read the [CLA document](" + CLA_DOC_URL + ")\n")
    lines.append("2. [Open a CLA signature request](" + CLA_SIGN_ISSUE_URL + ")\n")
    lines.append("3. A maintainer will add you to the signers list\n")
    lines.append("4. Comment `recheck` on this PR to re-run verification\n")

    if signed_authors:
        lines.append("\n### Verified Signers\n\n")
        for author, entity in signed_authors:
            username = author.get("username")
            if username:
                lines.append(f"- @{username} ({entity})\n")
            else:
                lines.append(f"- {author.get('name', author.get('email'))} ({entity})\n")

    lines.append("\n---\n")
    lines.append("*This check runs automatically. Maintainers can update ")
    lines.append("[`.github/cla-signers.json`](https://github.com/")
    lines.append(f"{owner}/{repo}/blob/main/.github/cla-signers.json) to add signers.*")

    comment_body = "".join(lines)

    # Check for existing CLA comment to update
    comments = github_request(
        f"repos/{owner}/{repo}/issues/{pr_number}/comments?per_page=100", token
    )

    cla_comment_id = None
    for comment in comments:
        if "## CLA Verification" in comment.get("body", ""):
            cla_comment_id = comment["id"]
            break

    if cla_comment_id:
        # Update existing comment
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
        }
        requests.patch(
            f"{GITHUB_API}/repos/{owner}/{repo}/issues/comments/{cla_comment_id}",
            headers=headers,
            json={"body": comment_body},
        )
    else:
        # Create new comment
        github_post(
            f"repos/{owner}/{repo}/issues/{pr_number}/comments", token, {"body": comment_body}
        )


def post_success_comment(
    owner: str, repo: str, pr_number: int, token: str, signed_authors: list[tuple[dict, str]]
) -> None:
    """Post success comment or update existing CLA comment."""
    lines = ["## CLA Verification Passed\n\n"]
    lines.append("All contributors have signed the CLA.\n\n")

    if signed_authors:
        lines.append("| Contributor | Signed As |\n")
        lines.append("|-------------|----------|\n")
        for author, entity in signed_authors:
            username = author.get("username")
            name = author.get("name", author.get("email", "Unknown"))
            if username:
                lines.append(f"| @{username} | {entity} |\n")
            else:
                lines.append(f"| {name} | {entity} |\n")

    comment_body = "".join(lines)

    # Check for existing CLA comment to update
    comments = github_request(
        f"repos/{owner}/{repo}/issues/{pr_number}/comments?per_page=100", token
    )

    for comment in comments:
        if "## CLA Verification" in comment.get("body", ""):
            # Update existing comment
            headers = {
                "Authorization": f"token {token}",
                "Accept": "application/vnd.github+json",
            }
            requests.patch(
                f"{GITHUB_API}/repos/{owner}/{repo}/issues/comments/{comment['id']}",
                headers=headers,
                json={"body": comment_body},
            )
            return

    # No existing comment - only post if there were multiple authors
    # (single author PRs don't need a "you signed" comment)
    if len(signed_authors) > 1:
        github_post(
            f"repos/{owner}/{repo}/issues/{pr_number}/comments", token, {"body": comment_body}
        )


def main():
    # Get environment variables
    token = get_env("GITHUB_TOKEN")
    pr_number = int(get_env("PR_NUMBER"))
    owner = get_env("REPO_OWNER")
    repo = get_env("REPO_NAME")

    print(f"Checking CLA for PR #{pr_number} in {owner}/{repo}")

    # Load signers
    signers = load_cla_signers()
    print(f"Loaded {len(signers.get('individuals', []))} individual signers")
    print(f"Loaded {len(signers.get('corporations', {}))} corporate signers")

    # Get PR authors
    authors = get_pr_authors(owner, repo, pr_number, token)
    print(f"Found {len(authors)} unique contributor(s) in PR")

    # Check each author
    missing = []
    signed = []

    # Allowlist for bots
    bot_patterns = [
        "dependabot",
        "github-actions",
        "renovate",
        "codecov",
        "sonarcloud",
        "coderabbitai",
        "sonarqubecloud",
        "175728472+copilot@users.noreply.github.com",
        "noreply@github.com",
        "noreply@anthropic.com",
    ]

    for author in authors:
        email = author.get("email", "")
        username = author.get("username")
        name = author.get("name", "")

        # Skip bots
        is_bot = False
        for pattern in bot_patterns:
            if pattern in email.lower() or (username and pattern in username.lower()):
                is_bot = True
                break
        if is_bot:
            print(f"  Skipping bot: {username or email}")
            continue

        # Skip GitHub noreply for web commits
        if email == "noreply@github.com":
            continue

        is_signed, entity = is_signer(username, email, signers)
        if is_signed:
            print(f"  CLA signed: {username or email} ({entity})")
            signed.append((author, entity))
        else:
            print(f"  CLA missing: {username or email}")
            missing.append(author)

    # Report results
    if missing:
        print(f"\nFAILED: {len(missing)} contributor(s) have not signed the CLA")
        post_comment(owner, repo, pr_number, token, missing, signed)
        sys.exit(1)
    else:
        print(f"\nPASSED: All {len(signed)} contributor(s) have signed the CLA")
        post_success_comment(owner, repo, pr_number, token, signed)
        sys.exit(0)


if __name__ == "__main__":
    main()
