#!/usr/bin/env python3
"""Génère la carte de rang GitHub (S / A+ / A / ... / C).

Reprend l'algorithme officiel de anuraghazra/github-readme-stats
(src/calculateRank.js) plutôt que d'appeler son API : le rendu reste
auto-hébergé et ne peut pas tomber comme les services tiers.

Sortie : profile-summary-card-output/<theme>/5-rank.svg
"""
import json
import os
import pathlib
import urllib.error
import urllib.request

LOGIN = os.environ.get("RANK_LOGIN", "raslenraslen")
TOKEN = os.environ.get("GITHUB_TOKEN")
THEME = os.environ.get("RANK_THEME", "tokyonight")

BG, TITLE, TEXT, ACCENT, DIM = "#1a1b27", "#70a5fd", "#a9b1d6", "#bf91f3", "#565f89"


def graphql(query, **variables):
    body = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=body,
        headers={
            "Authorization": f"bearer {TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": "profile-rank-card",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.load(resp)
    if "errors" in payload:
        raise RuntimeError(payload["errors"])
    return payload["data"]


def fetch_stats():
    data = graphql(
        """
        query($login:String!){
          user(login:$login){
            createdAt
            followers{totalCount}
            pullRequests{totalCount}
            openIssues:issues(states:OPEN){totalCount}
            closedIssues:issues(states:CLOSED){totalCount}
            repositories(ownerAffiliations:OWNER,first:100,isFork:false){
              nodes{stargazerCount}
            }
          }
        }""",
        login=LOGIN,
    )["user"]

    commits = reviews = 0
    for year in range(int(data["createdAt"][:4]), 2100):
        try:
            block = graphql(
                """
                query($login:String!,$from:DateTime!,$to:DateTime!){
                  user(login:$login){contributionsCollection(from:$from,to:$to){
                    totalCommitContributions
                    restrictedContributionsCount
                    totalPullRequestReviewContributions}}}""",
                login=LOGIN,
                from_=None,
                **{"from": f"{year}-01-01T00:00:00Z", "to": f"{year}-12-31T23:59:59Z"},
            )["user"]["contributionsCollection"]
        except urllib.error.HTTPError:
            break
        commits += block["totalCommitContributions"] + block["restrictedContributionsCount"]
        reviews += block["totalPullRequestReviewContributions"]
        if year >= 2026 and block["totalCommitContributions"] == 0 and block["restrictedContributionsCount"] == 0:
            break

    return {
        "commits": commits,
        "prs": data["pullRequests"]["totalCount"],
        "issues": data["openIssues"]["totalCount"] + data["closedIssues"]["totalCount"],
        "reviews": reviews,
        "stars": sum(r["stargazerCount"] for r in data["repositories"]["nodes"]),
        "followers": data["followers"]["totalCount"],
    }


def calculate_rank(commits, prs, issues, reviews, stars, followers):
    """Port fidèle de calculateRank.js (all_commits = True)."""
    exp = lambda x: 1 - 2**-x          # noqa: E731
    logn = lambda x: x / (1 + x)       # noqa: E731
    weights = 2 + 3 + 1 + 1 + 4 + 1
    score = (
        2 * exp(commits / 1000)
        + 3 * exp(prs / 50)
        + 1 * exp(issues / 25)
        + 1 * exp(reviews / 2)
        + 4 * logn(stars / 50)
        + 1 * logn(followers / 10)
    ) / weights
    percentile = (1 - score) * 100
    thresholds = [1, 12.5, 25, 37.5, 50, 62.5, 75, 87.5, 100]
    levels = ["S", "A+", "A", "A-", "B+", "B", "B-", "C+", "C"]
    level = next(l for t, l in zip(thresholds, levels) if percentile <= t)
    return level, percentile


def human(n):
    return f"{n/1000:.1f}k".replace(".0k", "k") if n >= 1000 else str(n)


def render(level, percentile, s):
    # L'anneau se remplit d'autant plus que le percentile est bas (meilleur).
    progress = max(0.0, min(1.0, (100 - percentile) / 100))
    r = 38
    circumference = 2 * 3.141592653589793 * r
    offset = circumference * (1 - progress)
    rows = [
        ("Commits", human(s["commits"])),
        ("Pull requests", human(s["prs"])),
        ("Stars", human(s["stars"])),
        ("Followers", human(s["followers"])),
    ]
    lines = "".join(
        f'<text x="30" y="{88 + i*24}" font-size="13" fill="{TEXT}">{label}</text>'
        f'<text x="175" y="{88 + i*24}" font-size="13" fill="{ACCENT}" text-anchor="end">{value}</text>'
        for i, (label, value) in enumerate(rows)
    )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="340" height="200" viewBox="0 0 340 200">
<style>* {{ font-family: 'Segoe UI', Ubuntu, "Helvetica Neue", Sans-Serif }}</style>
<rect x="1" y="1" rx="5" ry="5" height="99%" width="99.41176470588235%" stroke="{BG}" stroke-width="1" fill="{BG}"/>
<text x="30" y="40" font-size="22" fill="{TITLE}">Rank</text>
{lines}
<g transform="translate(258,112)">
  <circle r="{r}" fill="none" stroke="{DIM}" stroke-width="6" stroke-opacity="0.35"/>
  <circle r="{r}" fill="none" stroke="{TITLE}" stroke-width="6" stroke-linecap="round"
          stroke-dasharray="{circumference:.2f}" stroke-dashoffset="{offset:.2f}"
          transform="rotate(-90)"/>
  <text text-anchor="middle" y="10" font-size="30" font-weight="700" fill="{ACCENT}">{level}</text>
</g>
<text x="258" y="178" text-anchor="middle" font-size="12" fill="{DIM}">top {percentile:.1f}%</text>
</svg>
'''


def main():
    if not TOKEN:
        raise SystemExit("GITHUB_TOKEN manquant")
    stats = fetch_stats()
    level, percentile = calculate_rank(**stats)
    out = pathlib.Path(__file__).resolve().parents[2] / "profile-summary-card-output" / THEME
    out.mkdir(parents=True, exist_ok=True)
    (out / "5-rank.svg").write_text(render(level, percentile, stats), encoding="utf-8")
    print(f"  rang {level} (top {percentile:.1f}%)  <- {stats}")


if __name__ == "__main__":
    main()
