#!/usr/bin/env python3
"""Génère les cartes de la section « GitHub Stats » du README.

Quatre SVG statiques, même palette que la bannière (bleu #1f6feb -> #36BCF7
sur le fond GitHub dark) :

  stats/overview.svg   chiffres clés + courbe des contributions sur 12 mois
  stats/languages.svg  langages par nombre de repos
  stats/rank.svg       rang façon github-readme-stats (S / A+ / ... / C)
  stats/streak.svg     total, série en cours et plus longue série

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
    # history = calendrier jour par jour depuis l'inscription : il donne le total
    # (le même que le profil GitHub) et les séries. commits ne sert qu'au rang.
    commits = reviews = 0
    history = {}
    for year in range(int(user["createdAt"][:4]), dt.date.today().year + 1):
        try:
            block = graphql(
                """
                query($login:String!,$from:DateTime!,$to:DateTime!){
                  user(login:$login){contributionsCollection(from:$from,to:$to){
                    contributionCalendar{weeks{contributionDays{date contributionCount}}}
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
        for week in block["contributionCalendar"]["weeks"]:
            for day in week["contributionDays"]:
                history[day["date"]] = day["contributionCount"]

    repos = user["repositories"]
    languages = Counter(
        lang["name"]
        for repo in repos["nodes"]
        for lang in repo["languages"]["nodes"]
        if lang["name"] not in EXCLUDED_LANGUAGES
    )
    calendar = user["contributionsCollection"]["contributionCalendar"]
    # Le calendrier de l'année en cours court jusqu'au 31 décembre : on coupe à
    # aujourd'hui, au sens de GitHub (dernier jour du calendrier glissant).
    today = calendar["weeks"][-1]["contributionDays"][-1]["date"]
    history = {day: count for day, count in history.items() if day <= today}
    return {
        "commits": commits,
        "all_time": sum(history.values()),
        "history": sorted(history.items()),
        "joined": user["createdAt"][:10],
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
        "days": [(d["date"], d["contributionCount"]) for w in calendar["weeks"] for d in w["contributionDays"]],
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


def nice_step(peak):
    """Pas d'axe lisible (1, 2, 5, 10, 20, 25, 50... ) : 3 à 5 graduations, au plus près du pic."""
    magnitude = 10 ** max(0, math.floor(math.log10(peak)) - 1) if peak > 0 else 1
    candidates = [m * magnitude for m in (1, 2, 2.5, 5, 10, 20, 25, 50, 100) if (m * magnitude) % 1 == 0]
    fitting = [c for c in candidates if 3 <= math.ceil(peak / c) <= 5]
    if not fitting:  # pic minuscule : une graduation par unité
        return 1
    return min(fitting, key=lambda c: (c * math.ceil(peak / c), -c))


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
    width, height = 840, 356
    kpis = [
        (f'{s["all_time"]:,}', "Contributions · all time"),
        (f'{s["year_total"]:,}', "Last 12 months"),
        (human(s["prs"]), "Pull requests"),
        (human(s["public_repos"]), "Public repositories"),
    ]
    col = (width - 56) / len(kpis)
    body = "".join(
        f'<text x="{28 + i * col:.0f}" y="94" font-size="28" font-weight="600" fill="{TITLE}">{value}</text>'
        f'<text x="{28 + i * col:.0f}" y="116" font-size="12" fill="{MUTED}">{label}</text>'
        for i, (value, label) in enumerate(kpis)
    )

    weeks = s["weeks"]
    peak = max(c for _, c in weeks) or 1
    tick = nice_step(peak)
    y_max = tick * math.ceil(peak / tick)

    left, right, top, bottom = 70, width - 28, 172, 292
    step = (right - left) / (len(weeks) - 1)
    y_of = lambda count: bottom - count / y_max * (bottom - top)  # noqa: E731
    points = [(left + i * step, y_of(c)) for i, (_, c) in enumerate(weeks)]
    line = smooth_path(points)
    area = f"{line} L{right},{bottom} L{left},{bottom} Z"

    # Axe vertical : graduations « rondes » (0, 50, 100...) avec leur valeur.
    y_axis = f'<text x="{left - 12}" y="{top - 16}" font-size="11" fill="{MUTED}" text-anchor="end">per week</text>'
    for v in [tick * k for k in range(int(y_max / tick) + 1)]:
        if v:
            y_axis += f'<line x1="{left}" y1="{y_of(v):.1f}" x2="{right}" y2="{y_of(v):.1f}" stroke="{GRID}" stroke-dasharray="3 4"/>'
        y_axis += f'<text x="{left - 12}" y="{y_of(v) + 4:.1f}" font-size="12" fill="{TEXT}" text-anchor="end">{v:g}</text>'
    y_axis += f'<line x1="{left}" y1="{bottom}" x2="{right}" y2="{bottom}" stroke="{BORDER}"/>'

    # Axe horizontal : chaque mois centré sur ses semaines, avec son total exact.
    totals = Counter()
    for day, count in s["days"]:
        totals[day[:7]] += count
    starts = []
    for i, (day, _) in enumerate(weeks):
        if not starts or starts[-1][1] != day[:7]:
            starts.append((i, day[:7]))
    # le premier mois n'est couvert qu'en partie : son total serait trompeur
    if len(starts) > 1 and weeks[0][0][8:] > "07":
        starts.pop(0)
    centers = [
        left + (i + (starts[k + 1][0] if k + 1 < len(starts) else len(weeks) - 1)) / 2 * step
        for k, (i, _) in enumerate(starts)
    ]
    # Le mois en cours ne couvre qu'une semaine ou deux : on écarte les libellés
    # de droite à gauche pour qu'ils ne se chevauchent pas.
    centers[-1] = min(centers[-1], right - 14)
    for k in range(len(centers) - 2, -1, -1):
        centers[k] = min(centers[k], centers[k + 1] - 44)
    x_axis = f'<text x="{left - 12}" y="{bottom + 40}" font-size="11" fill="{MUTED}" text-anchor="end">total</text>'
    for (i, month), x in zip(starts, centers):
        name = dt.date.fromisoformat(f"{month}-01").strftime("%b")
        x_axis += (
            f'<line x1="{left + i * step:.1f}" y1="{bottom}" x2="{left + i * step:.1f}" y2="{bottom + 5}" stroke="{BORDER}"/>'
            f'<text x="{x:.1f}" y="{bottom + 21}" font-size="12" fill="{TEXT}" text-anchor="middle">{name}</text>'
            f'<text x="{x:.1f}" y="{bottom + 40}" font-size="12" font-weight="600" fill="{TITLE}" text-anchor="middle">{totals[month]}</text>'
        )

    # Meilleure semaine : point + valeur exacte.
    best = max(range(len(weeks)), key=lambda i: weeks[i][1])
    bx, by = points[best]
    best_day = dt.date.fromisoformat(weeks[best][0])
    anchor = "end" if bx > right - 120 else "middle"
    marker = (
        f'<line x1="{bx:.1f}" y1="{by:.1f}" x2="{bx:.1f}" y2="{bottom}" stroke="{CYAN}" stroke-opacity="0.35" stroke-dasharray="2 3"/>'
        f'<circle cx="{bx:.1f}" cy="{by:.1f}" r="4.5" fill="{CYAN}" stroke="{BG}" stroke-width="2"/>'
        f'<text x="{bx - (8 if anchor == "end" else 0):.1f}" y="{by - 10:.1f}" font-size="12" text-anchor="{anchor}">'
        f'<tspan font-weight="600" fill="{TITLE}">{weeks[best][1]}</tspan>'
        f'<tspan fill="{MUTED}"> · week of {best_day:%b} {best_day.day}</tspan></text>'
    )

    body += f'''
<defs>
  <linearGradient id="fill" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="{BLUE}" stop-opacity="0.45"/><stop offset="1" stop-color="{BLUE}" stop-opacity="0"/>
  </linearGradient>
</defs>
{y_axis}
<path d="{area}" fill="url(#fill)"/>
<path d="{line}" fill="none" stroke="url(#accent)" stroke-width="2.2" stroke-linejoin="round"/>
{x_axis}
{marker}'''
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


def streaks(history):
    """(longueur, début, fin) de la série en cours et de la plus longue.

    Comme sur GitHub, un jour sans contribution aujourd'hui ne casse pas encore
    la série : elle reste « en cours » jusqu'à la fin de la journée.
    """
    longest = run = (0, None, None)
    for day, count in history:
        run = (run[0] + 1, run[1] or day, day) if count else (0, None, None)
        if run[0] > longest[0]:
            longest = run
    end = len(history) - 1
    if history and history[end][1] == 0:
        end -= 1
    start = end
    while start >= 0 and history[start][1]:
        start -= 1
    current = (end - start, history[start + 1][0], history[end][0]) if end > start else (0, None, None)
    return current, longest


def date_range(start, end, this_year):
    """« Aug 9 - Oct 3 », avec l'année seulement quand ce n'est pas l'année en cours."""
    def label(day):
        d = dt.date.fromisoformat(day)
        return f"{d:%b} {d.day}" + ("" if d.year == this_year else f", {d.year}")
    if start is None:
        return "—"
    return label(start) if start == end else f"{label(start)} - {label(end)}"


def render_streak(s):
    width, height = 840, 240
    this_year = dt.date.fromisoformat(s["history"][-1][0]).year
    current, longest = streaks(s["history"])
    joined = dt.date.fromisoformat(s["joined"])
    col = (width - 56) / 3
    left_x, mid_x, right_x = (28 + col * (k + 0.5) for k in range(3))

    def stat(x, value, label, detail):
        return (
            f'<text x="{x:.0f}" y="133" font-size="30" font-weight="600" fill="{TITLE}" text-anchor="middle">{value}</text>'
            f'<text x="{x:.0f}" y="190" font-size="13" fill="{TEXT}" text-anchor="middle">{label}</text>'
            f'<text x="{x:.0f}" y="210" font-size="12" fill="{MUTED}" text-anchor="middle">{detail}</text>'
        )

    dividers = "".join(
        f'<line x1="{28 + col * k:.0f}" y1="70" x2="{28 + col * k:.0f}" y2="210" stroke="{BORDER}"/>' for k in (1, 2)
    )
    # Série en cours : anneau + flamme, comme la carte streak d'origine.
    ring = (
        f'<circle cx="{mid_x:.0f}" cy="122" r="40" fill="none" stroke="url(#accent)" stroke-width="5"/>'
        f'<rect x="{mid_x - 12:.0f}" y="74" width="24" height="14" fill="{BG}"/>'
        f'<path transform="translate({mid_x:.0f},80)" fill="{CYAN}" d="M0,-10 C5,-5 8,-1 8,3 C8,8 4,11 0,11 '
        f'C-4,11 -8,8 -8,3 C-8,-1 -4,-3 -2,-7 C-1,-4 0,-2 2,-1 C2,-4 1,-7 0,-10 Z"/>'
        f'<text x="{mid_x:.0f}" y="133" font-size="30" font-weight="600" fill="{TITLE}" text-anchor="middle">{current[0]}</text>'
        f'<text x="{mid_x:.0f}" y="190" font-size="13" font-weight="600" fill="{CYAN}" text-anchor="middle">Current streak</text>'
        f'<text x="{mid_x:.0f}" y="210" font-size="12" fill="{MUTED}" text-anchor="middle">'
        f'{date_range(current[1], current[2], this_year)}</text>'
    )
    body = (
        dividers
        + stat(left_x, f'{s["all_time"]:,}', "Total contributions", f"{joined:%b} {joined.day}, {joined.year} - Present")
        + ring
        + stat(right_x, longest[0], "Longest streak", date_range(longest[1], longest[2], this_year))
    )
    return card(width, height, "Contribution streak", "", body)


def main():
    if not TOKEN:
        raise SystemExit("GITHUB_TOKEN manquant")
    stats = fetch()
    OUT.mkdir(exist_ok=True)
    for name, render in (("overview", render_overview), ("languages", render_languages), ("rank", render_rank), ("streak", render_streak)):
        (OUT / f"{name}.svg").write_text(render(stats), encoding="utf-8")
        print(f"  écrit  stats/{name}.svg")


if __name__ == "__main__":
    main()
