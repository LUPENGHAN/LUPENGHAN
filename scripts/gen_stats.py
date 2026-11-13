#!/usr/bin/env python3
"""Generate a terminal-styled GitHub stats card as SVG.

Data comes from the GitHub GraphQL API. Runs in CI with GITHUB_TOKEN,
or locally with a token from GITHUB_TOKEN / GH_TOKEN / `gh auth token`.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import date, datetime

GRAPHQL_URL = "https://api.github.com/graphql"

QUERY = """
query($login: String!) {
  user(login: $login) {
    repositories(privacy: PUBLIC, ownerAffiliations: OWNER) { totalCount }
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
    }
  }
}
"""

# Palette shared with assets/banner.svg
BG_FROM = "#0d1117"
BG_TO = "#161b22"
BORDER = "#30363d"
DIVIDER = "#21262d"
PROMPT = "#3fb950"
COMMAND = "#c9d1d9"
MUTED = "#8b949e"
DIM = "#484f58"
CURSOR = "#3fb950"
HEAT = ["#21262d", "#0e4429", "#006d32", "#26a641", "#39d353"]

FONT = "ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, 'Liberation Mono', monospace"

WIDTH = 900
HEIGHT = 280
HEATMAP_COLS = 52
CELL = 9
GAP = 3
PITCH = CELL + GAP


def resolve_token() -> str:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        return token.strip()
    gh = shutil.which("gh")
    if gh:
        try:
            out = subprocess.run(
                [gh, "auth", "token"], capture_output=True, text=True, timeout=15
            )
            if out.returncode == 0 and out.stdout.strip():
                return out.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            pass
    sys.exit("error: no GitHub token (set GITHUB_TOKEN, GH_TOKEN, or log in with gh)")


def fetch(login: str, token: str) -> dict:
    body = json.dumps({"query": QUERY, "variables": {"login": login}}).encode()
    request = urllib.request.Request(
        GRAPHQL_URL,
        data=body,
        headers={
            "Authorization": f"bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "profile-readme-stats",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", "replace")[:300]
        sys.exit(f"error: GitHub API returned HTTP {error.code}: {detail}")
    except urllib.error.URLError as error:
        sys.exit(f"error: cannot reach GitHub API: {error.reason}")

    if payload.get("errors"):
        messages = "; ".join(e.get("message", "?") for e in payload["errors"])
        sys.exit(f"error: GitHub API error: {messages}")

    return payload["data"]["user"]


def parse_days(user: dict) -> list[tuple[date, int]]:
    calendar = user["contributionsCollection"]["contributionCalendar"]
    days: list[tuple[date, int]] = []
    for week in calendar["weeks"]:
        for day in week["contributionDays"]:
            days.append((date.fromisoformat(day["date"]), day["contributionCount"]))
    days.sort(key=lambda item: item[0])
    today = date.today()
    return [(day, count) for day, count in days if day <= today]


def streaks(days: list[tuple[date, int]]) -> tuple[int, int]:
    """Return (current streak, longest streak) in days."""
    longest = run = 0
    for _, count in days:
        run = run + 1 if count > 0 else 0
        longest = max(longest, run)

    current = 0
    index = len(days) - 1
    # A day that has not been filled in yet does not break the streak.
    if index >= 0 and days[index][1] == 0 and days[index][0] == date.today():
        index -= 1
    while index >= 0 and days[index][1] > 0:
        current += 1
        index -= 1
    return current, longest


def heat_color(count: int) -> str:
    if count <= 0:
        return HEAT[0]
    if count <= 2:
        return HEAT[1]
    if count <= 5:
        return HEAT[2]
    if count <= 9:
        return HEAT[3]
    return HEAT[4]


def heatmap(day_list: list[tuple[date, int]]) -> str:
    window = day_list[-HEATMAP_COLS * 7 :]
    columns = [window[i : i + 7] for i in range(0, len(window), 7)]
    total_width = len(columns) * PITCH - GAP
    x0 = (WIDTH - total_width) / 2
    y0 = 166

    cells = []
    for column, week in enumerate(columns):
        for row, (day, count) in enumerate(week):
            x = x0 + column * PITCH
            y = y0 + row * PITCH
            cells.append(
                f'<rect x="{x:.1f}" y="{y}" width="{CELL}" height="{CELL}" rx="2" '
                f'fill="{heat_color(count)}"><title>{day.isoformat()}: {count}</title></rect>'
            )
    return "\n    ".join(cells)


def metric(x: int, value: str, label: str) -> str:
    return f"""<g>
      <text x="{x}" y="112" font-family="{FONT}" font-size="34" font-weight="700" fill="url(#num)">{value}</text>
      <text x="{x}" y="138" font-family="{FONT}" font-size="12" fill="{MUTED}" letter-spacing="1">{label}</text>
    </g>"""


def render(login: str, days: list[tuple[date, int]], repos: int) -> str:
    total = sum(count for _, count in days)
    current, longest = streaks(days)
    generated = datetime.now().strftime("%Y-%m-%d")

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-label="GitHub stats for {login}">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="{WIDTH}" y2="{HEIGHT}" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="{BG_FROM}"/>
      <stop offset="1" stop-color="{BG_TO}"/>
    </linearGradient>
    <linearGradient id="num" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="{PROMPT}"/>
      <stop offset="1" stop-color="#39c5cf"/>
    </linearGradient>
    <radialGradient id="glow" cx="0.5" cy="0.5" r="0.5">
      <stop offset="0" stop-color="{PROMPT}" stop-opacity="0.14"/>
      <stop offset="1" stop-color="{PROMPT}" stop-opacity="0"/>
    </radialGradient>
    <clipPath id="panel"><rect x="4" y="4" width="{WIDTH - 8}" height="{HEIGHT - 8}" rx="14"/></clipPath>
  </defs>

  <g clip-path="url(#panel)">
    <rect x="4" y="4" width="{WIDTH - 8}" height="{HEIGHT - 8}" fill="url(#bg)"/>
    <circle cx="120" cy="30" r="200" fill="url(#glow)"/>
  </g>
  <rect x="4" y="4" width="{WIDTH - 8}" height="{HEIGHT - 8}" rx="14" fill="none" stroke="{BORDER}" stroke-width="1.5"/>
  <path d="M4 60 H{WIDTH - 4}" stroke="{DIVIDER}" stroke-width="1.5"/>

  <text x="40" y="40" font-family="{FONT}" font-size="15" fill="{PROMPT}">$</text>
  <text x="58" y="40" font-family="{FONT}" font-size="15" fill="{COMMAND}">./stats.sh --since=365d</text>
  <text x="{WIDTH - 40}" y="40" font-family="{FONT}" font-size="12" fill="{DIM}" text-anchor="end">updated {generated}</text>

  {metric(40, f"{total:,}", "CONTRIBUTIONS · 1Y")}
  {metric(260, str(current), "CURRENT STREAK · DAYS")}
  {metric(500, str(longest), "LONGEST STREAK · DAYS")}
  {metric(740, str(repos), "PUBLIC REPOS")}

  <g>
    {heatmap(days)}
  </g>
  <text x="{WIDTH - 40}" y="{HEIGHT - 14}" font-family="{FONT}" font-size="11" fill="{DIM}" text-anchor="end">last 52 weeks · public contributions</text>
</svg>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user", default="LUPENGHAN", help="GitHub login (default: LUPENGHAN)")
    parser.add_argument("--out", default="dist/stats.svg", help="output SVG path")
    args = parser.parse_args()

    user = fetch(args.user, resolve_token())
    days = parse_days(user)
    repos = user["repositories"]["totalCount"]
    svg = render(args.user, days, repos)

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as handle:
        handle.write(svg)
    print(f"wrote {args.out}: {sum(c for _, c in days):,} contributions, {len(days)} days, {repos} repos")


if __name__ == "__main__":
    main()
