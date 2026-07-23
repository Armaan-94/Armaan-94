#!/usr/bin/env python3
"""Regenerate assets/leetcode.svg from live LeetCode data.

Runs in CI (see .github/workflows/leetcode.yml). Uses only the standard
library. Fails gracefully: on any network/schema problem it leaves the
existing SVG untouched and exits 0, so the last good card stays on the
profile and the workflow simply commits nothing.
"""

import json
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta, date

USERNAME = "Armaan0904"
OUT = "assets/leetcode.svg"
GRAPHQL = "https://leetcode.com/graphql"

COLS, ROWS = 53, 7
CELL, GAP = 16, 4
PITCH = CELL + GAP
GRID_W = COLS * PITCH - GAP
X0 = (1200 - GRID_W) // 2
Y0 = 236
LEVELS = ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"]


def fetch():
    now = datetime.now(timezone.utc)
    cur, prev = now.year, now.year - 1
    query = f"""
    query card($username: String!) {{
      allQuestionsCount {{ difficulty count }}
      matchedUser(username: $username) {{
        username
        submitStatsGlobal {{ acSubmissionNum {{ difficulty count }} }}
        badges {{ displayName creationDate }}
        cur: userCalendar(year: {cur}) {{ submissionCalendar }}
        prev: userCalendar(year: {prev}) {{ submissionCalendar }}
      }}
    }}
    """
    payload = json.dumps({"query": query, "variables": {"username": USERNAME}}).encode()
    req = urllib.request.Request(
        GRAPHQL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (profile-card-bot)",
            "Referer": f"https://leetcode.com/u/{USERNAME}/",
            "Origin": "https://leetcode.com",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)
    if data.get("errors"):
        raise RuntimeError(f"GraphQL errors: {data['errors']}")
    m = data["data"]["matchedUser"]
    if not m:
        raise RuntimeError("user not found")

    # totals per difficulty (denominators)
    totals = {d["difficulty"]: d["count"] for d in data["data"]["allQuestionsCount"]}
    # solved per difficulty
    solved = {d["difficulty"]: d["count"] for d in m["submitStatsGlobal"]["acSubmissionNum"]}

    # merge two years of the daily submission calendar
    cal = {}
    for key in ("prev", "cur"):
        raw = (m.get(key) or {}).get("submissionCalendar")
        if raw:
            for ts, cnt in json.loads(raw).items():
                d = datetime.fromtimestamp(int(ts), timezone.utc).date()
                cal[d] = cal.get(d, 0) + int(cnt)

    # rolling-year window (last 365 days)
    today = now.date()
    year_ago = today - timedelta(days=364)
    submissions = sum(v for d, v in cal.items() if year_ago <= d <= today)
    active_days = sum(1 for d, v in cal.items() if year_ago <= d <= today and v > 0)

    # most recent badge
    badge_label = ""
    badges = m.get("badges") or []
    if badges:
        def key(b):
            return b.get("creationDate") or ""
        recent = sorted(badges, key=key)[-1]
        badge_label = recent.get("displayName") or ""

    return {
        "solved": solved.get("All", 0),
        "total_all": totals.get("All", 0),
        "easy": (solved.get("Easy", 0), totals.get("Easy", 0)),
        "medium": (solved.get("Medium", 0), totals.get("Medium", 0)),
        "hard": (solved.get("Hard", 0), totals.get("Hard", 0)),
        "active_days": active_days,
        "submissions": submissions,
        "badge_label": badge_label,
        "cal": cal,
        "today": today,
    }


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def build_svg(d):
    today = d["today"]
    # grid start: rightmost column holds today; rows are Sun..Sat
    row_today = (today.weekday() + 1) % 7  # Mon=0 -> 1, Sun=6 -> 0
    start = today - timedelta(days=(COLS - 1) * 7 + row_today)

    def level(c):
        if c <= 0:
            return 0
        if c == 1:
            return 1
        if c <= 3:
            return 2
        if c <= 6:
            return 3
        return 4

    rects, month_labels, last_month = [], [], None
    for col in range(COLS):
        col_first = start + timedelta(days=col * 7)
        if col_first.month != last_month:
            last_month = col_first.month
            mx = X0 + col * PITCH
            month_labels.append(
                f'<text x="{mx}" y="{Y0 + ROWS*PITCH + 14}" '
                f'font-family="ui-sans-serif,-apple-system,\'Segoe UI\',Roboto,Arial,sans-serif" '
                f'font-size="12" fill="#6e7681">{col_first.strftime("%b")}</text>'
            )
        for row in range(ROWS):
            day = start + timedelta(days=col * 7 + row)
            if day > today:
                continue
            lvl = level(d["cal"].get(day, 0))
            x, y = X0 + col * PITCH, Y0 + row * PITCH
            rects.append(f'<rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" rx="3" fill="{LEVELS[lvl]}"/>')
    cells_svg = "\n    ".join(rects)
    months_svg = "\n    ".join(month_labels)

    def bar(y, label, pair, color):
        s, t = pair
        track_x, track_w = 392, 178
        fill_w = max(3, round(track_w * (s / t))) if (s and t) else 0
        out = [
            f'<circle cx="292" cy="{y}" r="4" fill="{color}"/>',
            f'<text x="306" y="{y+4}" font-family="ui-sans-serif,-apple-system,\'Segoe UI\',Roboto,Arial,sans-serif" font-size="15" fill="#8b949e">{label}</text>',
            f'<rect x="{track_x}" y="{y-5}" width="{track_w}" height="9" rx="4.5" fill="#21262d"/>',
        ]
        if fill_w:
            out.append(f'<rect x="{track_x}" y="{y-5}" width="{fill_w}" height="9" rx="4.5" fill="{color}"/>')
        out.append(
            f'<text x="{track_x+track_w+12}" y="{y+4}" font-family="ui-monospace,\'SF Mono\',Consolas,monospace" font-size="13" fill="#c9d1d9">{s}<tspan fill="#6e7681"> / {t}</tspan></text>'
        )
        return "\n    ".join(out)

    bars = "\n    ".join([
        bar(96, "Easy", d["easy"], "#22c55e"),
        bar(126, "Medium", d["medium"], "#f59e0b"),
        bar(156, "Hard", d["hard"], "#f43f5e"),
    ])

    badge_svg = ""
    if d["badge_label"]:
        label = esc(d["badge_label"])
        width = min(240, 44 + int(len(label) * 7.2))
        badge_svg = (
            f'<g><rect x="{1156-width}" y="166" width="{width}" height="30" rx="15" fill="#161b22" stroke="#21262d"/>'
            f'<circle cx="{1156-width+22}" cy="181" r="6" fill="#ffa116"/>'
            f'<text x="{1156-width+38}" y="185" font-family="ui-sans-serif,-apple-system,\'Segoe UI\',Roboto,Arial,sans-serif" font-size="13" fill="#c9d1d9">{label}</text></g>'
        )

    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 410" width="1200" height="410" role="img" aria-label="LeetCode: {d['solved']} problems solved, {d['submissions']} submissions and {d['active_days']} active days in the past year">
  <title>LeetCode problem-solving activity</title>
  <defs>
    <linearGradient id="lc_panel" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#0d1117"/>
      <stop offset="0.6" stop-color="#0f1420"/>
      <stop offset="1" stop-color="#10182a"/>
    </linearGradient>
    <linearGradient id="lc_num" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#39d353"/>
      <stop offset="1" stop-color="#22d3ee"/>
    </linearGradient>
  </defs>

  <rect width="1200" height="410" rx="20" fill="url(#lc_panel)"/>
  <rect x="0.5" y="0.5" width="1199" height="409" rx="20" fill="none" stroke="#21262d"/>

  <rect x="44" y="44" width="10" height="10" rx="2.5" fill="#ffa116"/>
  <text x="64" y="53" font-family="ui-monospace,'SF Mono',Consolas,monospace" font-size="14" letter-spacing="2.5" fill="#8b949e">LEETCODE</text>
  <text x="180" y="53" font-family="ui-monospace,'SF Mono',Consolas,monospace" font-size="13" fill="#6e7681">@{USERNAME}</text>

  <text x="44" y="126" font-family="ui-sans-serif,-apple-system,'Segoe UI',Roboto,Arial,sans-serif" font-size="58" font-weight="800" letter-spacing="-2" fill="url(#lc_num)">{d['solved']}</text>
  <text x="166" y="112" font-family="ui-sans-serif,-apple-system,'Segoe UI',Roboto,Arial,sans-serif" font-size="15" fill="#8b949e">Solved</text>
  <text x="166" y="132" font-family="ui-monospace,'SF Mono',Consolas,monospace" font-size="13" fill="#6e7681">of {d['total_all']}</text>

  {bars}

  <text x="1156" y="60" text-anchor="end" font-family="ui-sans-serif,-apple-system,'Segoe UI',Roboto,Arial,sans-serif" font-size="15" fill="#8b949e">Total active days</text>
  <text x="1156" y="112" text-anchor="end" font-family="ui-sans-serif,-apple-system,'Segoe UI',Roboto,Arial,sans-serif" font-size="52" font-weight="800" letter-spacing="-1" fill="#c9d1d9">{d['active_days']}</text>
  <text x="1156" y="146" text-anchor="end" font-family="ui-monospace,'SF Mono',Consolas,monospace" font-size="13" fill="#6e7681">{d['submissions']} submissions · past year</text>
  {badge_svg}

  <text x="44" y="222" font-family="ui-sans-serif,-apple-system,'Segoe UI',Roboto,Arial,sans-serif" font-size="14" fill="#8b949e">Submission activity<tspan fill="#6e7681">  ·  past year</tspan></text>
  <g>
    <text x="972" y="223" text-anchor="end" font-family="ui-sans-serif,-apple-system,'Segoe UI',Roboto,Arial,sans-serif" font-size="12" fill="#6e7681">Less</text>
    <rect x="982"  y="213" width="12" height="12" rx="3" fill="{LEVELS[1]}"/>
    <rect x="998"  y="213" width="12" height="12" rx="3" fill="{LEVELS[2]}"/>
    <rect x="1014" y="213" width="12" height="12" rx="3" fill="{LEVELS[3]}"/>
    <rect x="1030" y="213" width="12" height="12" rx="3" fill="{LEVELS[4]}"/>
    <text x="1052" y="223" font-family="ui-sans-serif,-apple-system,'Segoe UI',Roboto,Arial,sans-serif" font-size="12" fill="#6e7681">More</text>
  </g>

  <g>
    {cells_svg}
  </g>

  {months_svg}
</svg>
'''


def main():
    try:
        data = fetch()
        if not data["solved"] and not data["cal"]:
            raise RuntimeError("empty stats; refusing to overwrite")
        svg = build_svg(data)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, RuntimeError, KeyError, ValueError) as e:
        print(f"[leetcode_card] skip regeneration: {e}", file=sys.stderr)
        sys.exit(0)

    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(svg)
    print(f"[leetcode_card] wrote {OUT}: {data['solved']} solved, "
          f"{data['active_days']} active days, {data['submissions']} submissions")


if __name__ == "__main__":
    main()
