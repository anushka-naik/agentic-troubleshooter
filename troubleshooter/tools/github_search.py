from dataclasses import dataclass

import httpx
from langsmith import traceable

_SEARCH_URL = "https://api.github.com/search/issues"
_BODY_PREVIEW = 600


@dataclass
class GitHubIssue:
    title: str
    url: str
    state: str
    comments: int
    repository: str
    body: str


@traceable(run_type="tool", name="github.search_issues")
def search_issues(query: str, token: str | None = None, limit: int = 5, timeout_s: float = 8.0) -> list[GitHubIssue]:
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    params = {"q": f"{query} in:title is:issue", "per_page": limit}

    response = httpx.get(_SEARCH_URL, params=params, headers=headers, timeout=timeout_s)
    response.raise_for_status()

    issues = []
    for item in response.json().get("items", [])[:limit]:
        repo = item.get("repository_url", "").removeprefix("https://api.github.com/repos/")
        issues.append(
            GitHubIssue(
                title=item.get("title", ""),
                url=item.get("html_url", ""),
                state=item.get("state", ""),
                comments=item.get("comments", 0),
                repository=repo,
                body=(item.get("body") or "")[:_BODY_PREVIEW],
            )
        )
    return issues
