#!/usr/bin/env python3
"""Génère les cartes de la section « GitHub Stats » du README.

Trois SVG statiques, même palette que la bannière (bleu #1f6feb -> #36BCF7
sur le fond GitHub dark) :

  stats/overview.svg   chiffres clés + courbe des contributions sur 12 mois
  stats/languages.svg  langages par nombre de repos
  stats/rank.svg       rang façon github-readme-stats (S / A+ / ... / C)

Tout vient de l'API GraphQL de GitHub : aucun service tiers au rendu.
"""
import datetime as dt
import json
import math
import os
import pathlib
import urllib.error
import urllib.request
from collections import Counter

LOGIN = os.environ.get("STATS_LOGIN", "raslenraslen")
TOKEN = os.environ.get("GITHUB_TOKEN")
OUT = pathlib.Path(__file__).resolve().parents[2] / "stats"

# Du markup, pas des langages : ils écraseraient la carte (vieux projets web).
EXCLUDED_LANGUAGES = {"HTML", "CSS", "SCSS", "Roff"}

BG, BORDER, GRID = "#0d1117", "#30363d", "#21262d"
TITLE, TEXT, MUTED = "#e6edf3", "#c9d1d9", "#8b949e"
BLUE, CYAN = "#1f6feb", "#36bcf7"
SHADES = ["#36bcf7", "#2fa4f2", "#2a8cec", "#1f6feb", "#2f5fc4", "#3b5299"]
FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans', Helvetica, Arial, sans-serif"


def graphql(query, **variables):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={
            "Authorization": f"bearer {TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": "profile-stats",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.load(resp)
    if "errors" in payload:
        raise RuntimeError(payload["errors"])
    return payload["data"]


def fetch():
    user = graphql(
        """
        query($login:String!){
          user(login:$login){
            createdAt
            followers{totalCount}
            pullRequests{totalCount}
            openIssues:issues(states:OPEN){totalCount}
            closedIssues:issues(states:CLOSED){totalCount}
            repositoriesContributedTo(contributionTypes:[COMMIT,PULL_REQUEST,ISSUE]){totalCount}
            repositories(ownerAffiliations:OWNER,isFork:false,privacy:PUBLIC,first:100){
              totalCount
              nodes{
                stargazerCount
                languages(first:10,orderBy:{field:SIZE,direction:DESC}){nodes{name}}
              }
            }
            contributionsCollection{
              contributionCalendar{
                totalContributions
                weeks{contributionDays{date contributionCount}}
              }
            }
          }
        }""",
        login=LOGIN,
    )["user"]

    # L'API plafonne contributionsCollection à un an : on cumule année par année.
    commits = reviews = 0
    for year in range(int(user["createdAt"][:4]), dt.date.today().year + 1):
        try:
            block = graphql(
                """
                query($login:String!,$from:DateTime!,$to:DateTime!){
                  user(login:$login){contributionsCollection(from:$from,to:$to){
                    totalCommitContributions
                    restrictedContributionsCount
                    totalPullRequestReviewContributions}}}""",
                login=LOGIN,
                **{"from": f"{year}-01-01T00:00:00Z", "to": f"{year}-12-31T23:59:59Z"},
            )["user"]["contributionsCollection"]
        except urllib.error.HTTPError:
            break
        commits += block["totalCommitContributions"] + block["restrictedContributionsCount"]
        reviews += block["totalPullRequestReviewContributions"]

    repos = user["repositories"]
    languages = Counter(
        lang["name"]
        for repo in repos["nodes"]
        for lang in repo["languages"]["nodes"]
        if lang["name"] not in EXCLUDED_LANGUAGES
    )
    calendar = user["contributionsCollection"]["contributionCalendar"]
    return {
        "commits": commits,
        "reviews": reviews,
        "prs": user["pullRequests"]["totalCount"],
        "issues": user["openIssues"]["totalCount"] + user["closedIssues"]["totalCount"],
        "stars": sum(r["stargazerCount"] for r in repos["nodes"]),
        "followers": user["followers"]["totalCount"],
        "contributed_to": user["repositoriesContributedTo"]["totalCount"],
        "public_repos": repos["totalCount"],
        "repos_with_language": sum(1 for r in repos["nodes"] if r["languages"]["nodes"]),
        "languages": languages,
        "year_total": calendar["totalContributions"],
        # La semaine en cours est incomplète : elle ferait plonger la courbe à la fin.
        "weeks": [
            (w["contributionDays"][0]["date"], sum(d["contributionCount"] for d in w["contributionDays"]))
            for w in calendar["weeks"]
            if len(w["contributionDays"]) == 7
        ],
    }


def calculate_rank(commits, prs, issues, reviews, stars, followers):
    """Port fidèle de calculateRank.js de github-readme-stats (all_commits = True)."""
    exp = lambda x: 1 - 2**-x          # noqa: E731
    logn = lambda x: x / (1 + x)       # noqa: E731
    score = (
        2 * exp(commits / 1000)
        + 3 * exp(prs / 50)
        + 1 * exp(issues / 25)
        + 1 * exp(reviews / 2)
        + 4 * logn(stars / 50)
        + 1 * logn(followers / 10)
    ) / 12
    percentile = (1 - score) * 100
    thresholds = [1, 12.5, 25, 37.5, 50, 62.5, 75, 87.5, 100]
    levels = ["S", "A+", "A", "A-", "B+", "B", "B-", "C+", "C"]
    return next(l for t, l in zip(thresholds, levels) if percentile <= t), percentile


def human(n):
    return f"{n / 1000:.1f}k".replace(".0k", "k") if n >= 1000 else f"{n}"


def card(width, height, title, subtitle, body):
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
<defs>
  <linearGradient id="accent" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0" stop-color="{BLUE}"/><stop offset="1" stop-color="{CYAN}"/>
  </linearGradient>
</defs>
<style>text {{ font-family: {FONT} }}</style>
<rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="10" fill="{BG}" stroke="{BORDER}"/>
<rect x="28" y="26" width="3" height="16" rx="1.5" fill="url(#accent)"/>
<text x="40" y="39" font-size="15" font-weight="600" fill="{TITLE}">{title}</text>
<text x="{width - 28}" y="39" font-size="12" fill="{MUTED}" text-anchor="end">{subtitle}</text>
{body}
</svg>
'''


def smooth_path(points):
    """Courbe Catmull-Rom -> Bézier ; les points de contrôle restent sous la ligne de base."""
    floor = max(y for _, y in points)
    d = f"M{points[0][0]:.1f},{points[0][1]:.1f}"
    for i in range(len(points) - 1):
        p0 = points[max(i - 1, 0)]
        p1, p2 = points[i], points[i + 1]
        p3 = points[min(i + 2, len(points) - 1)]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, min(floor, p1[1] + (p2[1] - p0[1]) / 6))
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, min(floor, p2[1] - (p3[1] - p1[1]) / 6))
        d += f" C{c1[0]:.1f},{c1[1]:.1f} {c2[0]:.1f},{c2[1]:.1f} {p2[0]:.1f},{p2[1]:.1f}"
    return d


def render_overview(s):
    width, height = 840, 280
    kpis = [
        # restrictedContributionsCount compte toutes les contributions privées, pas que des commits.
        (human(s["commits"]), "Contributions · all time"),
        (human(s["year_total"]), "Last 12 months"),
        (human(s["prs"]), "Pull requests"),
        (human(s["public_repos"]), "Public repositories"),
    ]
    col = (width - 56) / len(kpis)
    body = "".join(
        f'<text x="{28 + i * col:.0f}" y="94" font-size="28" font-weight="600" fill="{TITLE}">{value}</text>'
        f'<text x="{28 + i * col:.0f}" y="116" font-size="12" fill="{MUTED}">{label}</text>'
        for i, (value, label) in enumerate(kpis)
    )

    left, right, top, bottom = 28, width - 28, 150, 240
    weeks = s["weeks"]
    peak = max(c for _, c in weeks) or 1
    step = (right - left) / (len(weeks) - 1)
    points = [(left + i * step, bottom - c / peak * (bottom - top)) for i, (_, c) in enumerate(weeks)]
    line = smooth_path(points)
    area = f"{line} L{right},{bottom} L{left},{bottom} Z"

    grid = "".join(
        f'<line x1="{left}" y1="{y:.1f}" x2="{right}" y2="{y:.1f}" stroke="{GRID}" stroke-dasharray="3 4"/>'
        for y in (top, (top + bottom) / 2)
    ) + f'<line x1="{left}" y1="{bottom}" x2="{right}" y2="{bottom}" stroke="{BORDER}"/>'

    months, last_month = [], None
    for i, (day, _) in enumerate(weeks):
        month = day[:7]
        if month != last_month:
            last_month = month
            months.append((left + i * step, dt.date.fromisoformat(day).strftime("%b")))
    # le premier mois est souvent partiel : on l'enlève s'il colle au suivant
    if len(months) > 1 and months[1][0] - months[0][0] < 30:
        months.pop(0)
    labels = "".join(
        f'<text x="{x:.1f}" y="{bottom + 20}" font-size="11" fill="{MUTED}">{name}</text>' for x, name in months
    )

    body += f'''
<defs>
  <linearGradient id="fill" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="{BLUE}" stop-opacity="0.45"/><stop offset="1" stop-color="{BLUE}" stop-opacity="0"/>
  </linearGradient>
</defs>
{grid}
<path d="{area}" fill="url(#fill)"/>
<path d="{line}" fill="none" stroke="url(#accent)" stroke-width="2.2" stroke-linejoin="round"/>
{labels}'''
    return card(width, height, "GitHub activity", "contributions per week · last 12 months", body)


def render_languages(s):
    width, height = 418, 240
    total = s["repos_with_language"] or 1
    top = s["languages"].most_common(6)
    track_x, track_w = 140, 196
    rows = []
    for i, (name, count) in enumerate(top):
        y = 80 + i * 26
        share = count / total
        rows.append(
            f'<text x="28" y="{y + 4}" font-size="13" fill="{TEXT}">{name}</text>'
            f'<rect x="{track_x}" y="{y - 4}" width="{track_w}" height="8" rx="4" fill="{GRID}"/>'
            f'<rect x="{track_x}" y="{y - 4}" width="{max(8, track_w * share):.1f}" height="8" rx="4" fill="{SHADES[i]}"/>'
            f'<text x="{width - 28}" y="{y + 4}" font-size="12" fill="{MUTED}" text-anchor="end">{share:.0%}</text>'
        )
    return card(width, height, "Languages", "share of repositories", "".join(rows))


def render_rank(s):
    width, height = 418, 240
    level, percentile = calculate_rank(
        s["commits"], s["prs"], s["issues"], s["reviews"], s["stars"], s["followers"]
    )
    rows = [
        ("Stars earned", s["stars"]),
        ("Followers", s["followers"]),
        ("Issues", s["issues"]),
        ("Contributed to", s["contributed_to"]),
    ]
    lines = "".join(
        f'<text x="28" y="{84 + i * 30}" font-size="13" fill="{TEXT}">{label}</text>'
        f'<text x="200" y="{84 + i * 30}" font-size="13" font-weight="600" fill="{TITLE}" text-anchor="end">{human(value)}</text>'
        for i, (label, value) in enumerate(rows)
    )
    # L'anneau se remplit d'autant plus que le percentile est bas (meilleur).
    r = 50
    circumference = 2 * math.pi * r
    offset = circumference * min(1.0, max(0.0, percentile / 100))
    ring = f'''
<g transform="translate(318,124)">
  <circle r="{r}" fill="none" stroke="{GRID}" stroke-width="8"/>
  <circle r="{r}" fill="none" stroke="url(#accent)" stroke-width="8" stroke-linecap="round"
          stroke-dasharray="{circumference:.2f}" stroke-dashoffset="{offset:.2f}" transform="rotate(-90)"/>
  <text y="11" font-size="32" font-weight="700" fill="{TITLE}" text-anchor="middle">{level}</text>
</g>
<text x="318" y="206" font-size="12" fill="{MUTED}" text-anchor="middle">top {percentile:.1f}% on GitHub</text>'''
    return card(width, height, "Rank", "", lines + ring)


def main():
    if not TOKEN:
        raise SystemExit("GITHUB_TOKEN manquant")
    stats = fetch()
    OUT.mkdir(exist_ok=True)
    for name, render in (("overview", render_overview), ("languages", render_languages), ("rank", render_rank)):
        (OUT / f"{name}.svg").write_text(render(stats), encoding="utf-8")
        print(f"  écrit  stats/{name}.svg")


if __name__ == "__main__":
    main()
