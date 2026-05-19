"""
UK 49s Lunchtime & Teatime — Scraper + Analyser + Web Dashboard
Run:  python app.py
Then open http://localhost:5000

The scraper targets https://49s.events/lunchtime (and /teatime).
If the live site is unreachable a block of realistic seeded data is used
so the dashboard is always fully functional.
"""

import re
import random
import itertools
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

import requests
from bs4 import BeautifulSoup
from flask import Flask, jsonify, render_template_string

app = Flask(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# COLOUR MAP
# ─────────────────────────────────────────────────────────────────────────────

COLOUR_RANGES = [
    (1,   9,  "Red"),
    (10,  19, "Orange"),
    (20,  29, "Yellow"),
    (30,  39, "Green"),
    (40,  49, "Blue"),
    (50,  59, "Brown"),
    (60,  99, "Purple"),
]

COLOUR_HEX = {
    "Red":     "#c9392a",
    "Orange":  "#d06a20",
    "Yellow":  "#b89000",
    "Green":   "#2e8f5e",
    "Blue":    "#2e68b5",
    "Brown":   "#7a4e2c",
    "Purple":  "#7040b0",
    "Unknown": "#555555",
}


def classify_colour(n: int) -> str:
    for lo, hi, colour in COLOUR_RANGES:
        if lo <= n <= hi:
            return colour
    return "Unknown"


# ─────────────────────────────────────────────────────────────────────────────
# DATA MODEL
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class DrawResult:
    date_raw:   str
    date:       Optional[datetime]
    numbers:    list
    booster:    Optional[int]
    detail_url: Optional[str]


# ─────────────────────────────────────────────────────────────────────────────
# SEEDED DEMO DATA  (realistic UK 49s distributions)
# ─────────────────────────────────────────────────────────────────────────────

_FREQ_WEIGHTS = {
    1:4,2:5,3:6,4:5,5:7,6:8,7:6,8:5,9:4,
    10:6,11:7,12:8,13:5,14:6,15:7,16:8,17:5,18:6,19:4,
    20:7,21:5,22:6,23:8,24:7,25:6,26:5,27:4,28:7,29:6,
    30:5,31:7,32:6,33:8,34:5,35:6,36:7,37:5,38:4,39:6,
    40:7,41:8,42:6,43:5,44:7,45:6,46:5,47:4,48:6,49:7,
}


def _seeded_draw(rng, date: datetime) -> DrawResult:
    population = list(_FREQ_WEIGHTS.keys())
    weights    = list(_FREQ_WEIGHTS.values())
    chosen, remaining_pop, remaining_wts = [], population[:], weights[:]
    while len(chosen) < 7:
        pick = rng.choices(remaining_pop, weights=remaining_wts, k=1)[0]
        idx  = remaining_pop.index(pick)
        remaining_pop.pop(idx)
        remaining_wts.pop(idx)
        chosen.append(pick)
    main_balls = sorted(chosen[:6])
    booster    = chosen[6]

    def ordinal(d):
        return str(d) + ("th" if 11 <= d <= 13 else {1:"st",2:"nd",3:"rd"}.get(d % 10,"th"))

    date_raw = date.strftime(f"%A {ordinal(date.day)} %B %Y")
    return DrawResult(date_raw=date_raw, date=date,
                      numbers=main_balls, booster=booster, detail_url=None)


def _generate_demo_draws(n: int = 30) -> list:
    rng   = random.Random(42)
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    return [_seeded_draw(rng, today - timedelta(days=i)) for i in range(n)]


# ─────────────────────────────────────────────────────────────────────────────
# SCRAPER
# ─────────────────────────────────────────────────────────────────────────────

BASE_URL      = "https://49s.events"
LUNCHTIME_URL = f"{BASE_URL}/lunchtime"
TEATIME_URL   = f"{BASE_URL}/teatime"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
}


def _parse_date(raw: str) -> Optional[datetime]:
    cleaned = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", raw).strip()
    parts   = cleaned.split()
    if len(parts) >= 4:
        cleaned = " ".join(parts[1:])
    try:
        return datetime.strptime(cleaned, "%d %B %Y")
    except ValueError:
        return None


def _parse_numbers(cell_text: str):
    nums = [int(n) for n in re.findall(r"\d+", cell_text)]
    if not nums or "?" in cell_text:
        return [], None
    if len(nums) >= 7:
        return nums[:6], nums[6]
    return nums, None


def scrape(url: str) -> tuple:
    """Returns (draws, live:bool). Falls back to demo data on any failure."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=12)
        resp.raise_for_status()
        soup  = BeautifulSoup(resp.text, "html.parser")
        table = soup.find("table")
        if not table:
            raise ValueError("No table found")
        results = []
        for row in table.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) < 2:
                continue
            date_raw         = cells[0].get_text(strip=True)
            numbers, booster = _parse_numbers(cells[1].get_text(" ", strip=True))
            link_tag         = cells[2].find("a") if len(cells) > 2 else None
            detail_url       = BASE_URL + link_tag["href"] if link_tag else None
            if not numbers:
                continue
            results.append(DrawResult(
                date_raw   = date_raw,
                date       = _parse_date(date_raw),
                numbers    = numbers,
                booster    = booster,
                detail_url = detail_url,
            ))
        if results:
            return results, True
        raise ValueError("Empty result set")
    except Exception:
        return _generate_demo_draws(30), False


# ─────────────────────────────────────────────────────────────────────────────
# ANALYSER
# ─────────────────────────────────────────────────────────────────────────────

def analyse(draws: list) -> dict:
    if not draws:
        return {}

    all_main    = [n for d in draws for n in d.numbers]
    all_booster = [d.booster for d in draws if d.booster is not None]
    freq        = Counter(all_main + all_booster)

    hot  = [n for n, _ in freq.most_common(10)]
    cold = [n for n, _ in reversed(freq.most_common())][:10]

    colour_dist = Counter(classify_colour(n) for n in all_main)
    digit_dist  = Counter(n % 10 for n in all_main)

    # ── Set generation from latest draw ──
    latest = draws[0]
    balls  = latest.numbers[:6] + ([latest.booster] if latest.booster else [])
    while len(balls) < 7:
        balls.append(balls[-1] if balls else 1)

    # Extract tens/units digits from each ball — keeps values in sensible range
    tens  = [b // 10 for b in balls]
    units = [b % 10  for b in balls]
    dsums = [t + u   for t, u in zip(tens, units)]   # digit-sums (0..13)

    today = datetime.now().day

    # ── S1: sums of pairs and triplets of digit-sums ──
    S1 = []
    for i in range(len(dsums)):
        for j in range(i+1, len(dsums)):
            s = dsums[i] + dsums[j]
            if 1 <= s <= 49:
                S1.append(s)
            # add ball itself
            if 1 <= balls[i] <= 49:
                S1.append(balls[i])

    # ── S2: range-nudge of ball values ──
    S2 = []
    for n in balls:
        if 20 <= n <= 29:   S2.append(n + 10)
        elif 30 <= n <= 39: S2.extend([n + 10, n - 10])
        elif 40 <= n <= 49: S2.append(n - 10)
        elif n < 20:        S2.append(n + 10)
        else:               S2.append(n)

    # ── S3: calendar vicinity ──
    S3 = [today - 2, today - 1, today, today + 1, today + 2]

    # ── S5: difference-based combos ──
    S5 = []
    for i in range(len(balls)):
        for j in range(i+1, len(balls)):
            diff = abs(balls[i] - balls[j])
            s    = balls[i] + balls[j]
            if 1 <= diff <= 49: S5.append(diff)
            if 1 <= s    <= 49: S5.append(s)

    def valid49(lst):
        return sorted({n for n in lst if 1 <= n <= 49})

    sets = {
        "S1 — Digit-pair sums":   valid49(S1),
        "S2 — Range-nudged":      valid49(S2),
        "S3 — Calendar vicinity": valid49(S3),
        "S5 — Ball differences":  valid49(S5),
    }

    # Group entries
    all_entries = []
    for label, nums in sets.items():
        tag = label.split("—")[0].strip()
        for n in nums:
            all_entries.append((n, tag))

    colour_groups, digit_groups = {}, {}
    for n, lbl in all_entries:
        colour = classify_colour(n)
        tag    = f"{n}({lbl})"
        colour_groups.setdefault(colour, []).append(tag)
        digit_groups.setdefault(n % 10, []).append(tag)

    return {
        "total_draws"   : len(draws),
        "hot"           : hot,
        "cold"          : cold,
        "freq"          : {str(k): v for k, v in freq.most_common(49)},
        "colour_dist"   : dict(colour_dist),
        "digit_dist"    : {str(k): v for k, v in sorted(digit_dist.items())},
        "sets"          : sets,
        "combos_colour" : _triplets(colour_groups),
        "combos_digit"  : _triplets(digit_groups),
        "suggested"     : _build_suggestions(hot, sets, freq),
        "latest_numbers": latest.numbers,
        "latest_booster": latest.booster,
        "latest_date"   : latest.date_raw,
    }


def _triplets(groups: dict) -> list:
    out = []
    for key, members in sorted(groups.items(), key=lambda kv: str(kv[0])):
        unique = list(dict.fromkeys(members))
        if len(unique) < 3:
            continue
        combos = list(itertools.combinations(unique, 3))[:8]
        out.append({"group": str(key), "members": unique, "combos": [list(c) for c in combos]})
    return out


def _build_suggestions(hot: list, sets: dict, freq: Counter) -> list:
    sugs = []

    sugs.append({
        "label"  : "🔥 Pure Hot — top 6 most frequent",
        "numbers": sorted(hot[:6]),
        "reason" : "The 6 numbers that appeared most often across all analysed draws.",
    })

    set_nums = sorted({n for nums in sets.values() for n in nums})
    overlap  = [n for n in hot if n in set_nums][:3]
    fill     = [n for n in hot if n not in overlap]
    combo    = sorted((overlap + fill)[:6])
    if len(combo) == 6:
        sugs.append({
            "label"  : "🎯 Hot × Set Overlap",
            "numbers": combo,
            "reason" : "Numbers that are both historically frequent AND derived by set formula analysis.",
        })

    colour_pick, seen = [], set()
    for n, _ in freq.most_common():
        c = classify_colour(n)
        if c not in seen and 1 <= n <= 49:
            colour_pick.append(n); seen.add(c)
        if len(colour_pick) == 6: break
    if len(colour_pick) == 6:
        sugs.append({
            "label"  : "🌈 Balanced Colour Mix",
            "numbers": sorted(colour_pick),
            "reason" : "The most frequent number from each colour band — full range coverage.",
        })

    low  = sorted([n for n in freq if 1  <= n <= 16], key=lambda x: -freq[x])[:2]
    mid  = sorted([n for n in freq if 17 <= n <= 32], key=lambda x: -freq[x])[:2]
    high = sorted([n for n in freq if 33 <= n <= 49], key=lambda x: -freq[x])[:2]
    spread = sorted(low + mid + high)
    if len(spread) == 6:
        sugs.append({
            "label"  : "⚖️ Low-Mid-High Spread",
            "numbers": spread,
            "reason" : "2 numbers from each third of the range — avoids clustering.",
        })

    set_scored = sorted(set_nums, key=lambda x: -freq.get(x, 0))
    if len(set_scored) >= 6:
        sugs.append({
            "label"  : "📐 Set-Derived Combo",
            "numbers": sorted(set_scored[:6]),
            "reason" : "Numbers from arithmetic set formulas, ranked by historical frequency.",
        })

    evens = [n for n in hot if n % 2 == 0][:3]
    odds  = [n for n in hot if n % 2 == 1][:3]
    eo    = sorted(evens + odds)
    if len(eo) == 6:
        sugs.append({
            "label"  : "♟ Even-Odd Balance (3 + 3)",
            "numbers": eo,
            "reason" : "3 even + 3 odd from the hot list — balanced parity appears frequently.",
        })

    return sugs


# ─────────────────────────────────────────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route("/api/data")
def api_data():
    lt_draws, lt_live = scrape(LUNCHTIME_URL)
    tt_draws, _       = scrape(TEATIME_URL)
    analysis          = analyse(lt_draws)

    def serialize(draws, limit=25):
        return [{"date": d.date_raw, "numbers": d.numbers,
                 "booster": d.booster, "detail_url": d.detail_url}
                for d in draws[:limit]]

    return jsonify({
        "lunchtime" : serialize(lt_draws, 25),
        "teatime"   : serialize(tt_draws, 10),
        "analysis"  : analysis,
        "colour_hex": COLOUR_HEX,
        "fetched_at": datetime.now().strftime("%d %b %Y · %H:%M"),
        "live"      : lt_live,
    })


# ─────────────────────────────────────────────────────────────────────────────
# HTML TEMPLATE
# ─────────────────────────────────────────────────────────────────────────────

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>UK 49s Intelligence Dashboard</title>
<link rel="preconnect" href="https://fonts.googleapis.com"/>
<link href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=DM+Sans:wght@300;400;500;600&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet"/>
<style>
:root{
  --bg:#090b10;--surface:#111318;--card:#13161f;--card2:#161a26;
  --border:#232839;--accent:#f0c040;--accent2:#4a8fdd;
  --green:#3dbf82;--red:#e05858;--text:#dde1ee;--muted:#596080;
  --radius:14px;
  --fh:"Bebas Neue",sans-serif;--fb:"DM Sans",sans-serif;--fm:"JetBrains Mono",monospace;
}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
html{scroll-behavior:smooth}
body{background:var(--bg);color:var(--text);font-family:var(--fb);font-size:15px;line-height:1.6;min-height:100vh}

header{background:linear-gradient(135deg,#0b0d13,#111521);border-bottom:1px solid var(--border);padding:20px 36px 16px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px}
.logo{font-family:var(--fh);font-size:2.6rem;letter-spacing:3px;color:var(--accent);line-height:1}
.logo em{color:var(--text);font-style:normal}
.tagline{font-size:10px;color:var(--muted);font-family:var(--fm);letter-spacing:1.5px;margin-top:2px}
.header-right{display:flex;align-items:center;gap:14px;flex-wrap:wrap}
.data-badge{display:flex;align-items:center;gap:6px;padding:5px 12px;border-radius:20px;border:1px solid var(--border);font-size:11px;font-family:var(--fm);color:var(--muted)}
.data-badge .dot{width:7px;height:7px;border-radius:50%;background:var(--muted)}
.data-badge.live{color:var(--green);border-color:var(--green)}
.data-badge.live .dot{background:var(--green);box-shadow:0 0 6px var(--green);animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
#fetch-time{color:var(--muted);font-family:var(--fm);font-size:11px}
.btn{padding:8px 20px;border-radius:8px;border:none;cursor:pointer;font-family:var(--fh);font-size:1rem;letter-spacing:1px;transition:opacity .2s,transform .15s}
.btn:hover{opacity:.82;transform:translateY(-1px)}
.btn:disabled{opacity:.3;cursor:default;transform:none}
.btn-primary{background:var(--accent);color:#000}

nav{display:flex;gap:4px;padding:10px 36px;background:var(--surface);border-bottom:1px solid var(--border);position:sticky;top:0;z-index:50;overflow-x:auto}
.tab{padding:7px 18px;border-radius:6px;border:1px solid transparent;font-family:var(--fb);font-size:13px;font-weight:500;cursor:pointer;color:var(--muted);background:transparent;transition:all .2s;white-space:nowrap}
.tab.active{background:var(--accent);color:#000;border-color:var(--accent)}
.tab:hover:not(.active){border-color:var(--border);color:var(--text)}

main{padding:26px 36px;max-width:1460px;margin:0 auto}
.section{display:none;animation:fadeIn .3s}
.section.active{display:block}
@keyframes fadeIn{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:20px}
.grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}
@media(max-width:900px){.grid2,.grid3{grid-template-columns:1fr}}

.card{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:22px;margin-bottom:20px}
.card-title{font-family:var(--fh);font-size:1.3rem;letter-spacing:1px;color:var(--accent);margin-bottom:14px;border-bottom:1px solid var(--border);padding-bottom:8px;display:flex;align-items:center;justify-content:space-between;gap:10px}
.card-sub{font-size:10px;color:var(--muted);font-family:var(--fm);font-weight:400;letter-spacing:.5px}

.ball{width:36px;height:36px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-family:var(--fm);font-weight:600;font-size:12px;box-shadow:0 2px 8px rgba(0,0,0,.5);flex-shrink:0;border:2px solid rgba(255,255,255,.1)}
.ball-sm{width:28px;height:28px;font-size:10px}
.ball-lg{width:52px;height:52px;font-size:18px}
.ball-row{display:flex;flex-wrap:wrap;gap:7px;align-items:center}
.booster-sep{color:var(--muted);font-size:16px;margin:0 2px;opacity:.5}

.hero{background:linear-gradient(135deg,#13161f,#0e1020);border:1px solid rgba(240,192,64,.2);border-radius:var(--radius);padding:28px;margin-bottom:22px;display:flex;flex-direction:column;align-items:center;text-align:center;position:relative;overflow:hidden}
.hero::before{content:'';position:absolute;inset:0;background:radial-gradient(ellipse at 50% 0%,rgba(240,192,64,.06),transparent 70%);pointer-events:none}
.hero-eyebrow{font-size:10px;color:var(--muted);font-family:var(--fm);letter-spacing:2px;margin-bottom:6px;text-transform:uppercase}
.hero-date{font-size:12px;color:var(--accent);margin-bottom:16px;font-family:var(--fm)}
.hero-title{font-family:var(--fh);font-size:1.6rem;letter-spacing:2px;margin-bottom:20px}

.rtable{width:100%;border-collapse:collapse;font-size:13px}
.rtable th{text-align:left;padding:8px 12px;background:var(--surface);color:var(--muted);font-family:var(--fm);font-size:10px;text-transform:uppercase;letter-spacing:1px;border-bottom:1px solid var(--border)}
.rtable td{padding:8px 12px;border-bottom:1px solid var(--border);vertical-align:middle}
.rtable tr:last-child td{border-bottom:none}
.rtable tr:hover td{background:rgba(255,255,255,.02)}
.rtable a{color:var(--accent2);text-decoration:none;font-size:11px}
.rtable a:hover{text-decoration:underline}
.date-cell{font-size:11px;color:var(--muted);white-space:nowrap;font-family:var(--fm)}

.stats-row{display:flex;gap:14px;flex-wrap:wrap;margin-bottom:20px}
.stat-box{flex:1;min-width:90px;background:var(--card);border:1px solid var(--border);border-radius:10px;padding:14px;text-align:center}
.stat-val{font-family:var(--fh);font-size:2rem;color:var(--accent);line-height:1}
.stat-lbl{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:1px;margin-top:4px;font-family:var(--fm)}

.hc-wrap{display:flex;gap:20px;flex-wrap:wrap}
.hc-col{flex:1;min-width:160px}
.hc-label{font-size:10px;text-transform:uppercase;letter-spacing:1.5px;margin-bottom:8px;font-family:var(--fm)}
.hc-label.hot{color:var(--red)}
.hc-label.cold{color:var(--accent2)}

.freq-wrap{display:grid;grid-template-columns:repeat(auto-fill,minmax(44px,1fr));gap:5px}
.freq-cell{display:flex;flex-direction:column;align-items:center;gap:3px;padding:6px 4px;border-radius:7px;background:var(--surface);border:1px solid var(--border);transition:border-color .2s;cursor:default}
.freq-cell:hover{border-color:var(--accent)}
.freq-num{font-family:var(--fm);font-size:11px;font-weight:600}
.freq-bar{width:24px;border-radius:3px;min-height:3px}
.freq-cnt{font-size:9px;color:var(--muted)}

.digit-wrap{display:flex;gap:8px;align-items:flex-end;padding-top:8px}
.digit-col{display:flex;flex-direction:column;align-items:center;gap:4px;flex:1}
.digit-bar{width:100%;border-radius:4px 4px 0 0;min-height:4px;background:var(--accent)}
.digit-lbl{font-family:var(--fm);font-size:11px;color:var(--muted)}
.digit-cnt{font-size:10px;color:var(--text);font-family:var(--fm)}

.colour-wrap{display:flex;flex-wrap:wrap;gap:8px}
.colour-badge{padding:5px 13px;border-radius:20px;font-size:12px;font-weight:500;font-family:var(--fm)}

.sug-item{background:var(--card2);border:1px solid var(--border);border-radius:10px;padding:18px;margin-bottom:12px;transition:border-color .25s,transform .2s}
.sug-item:hover{border-color:var(--accent);transform:translateY(-2px)}
.sug-label{font-weight:600;font-size:14px;margin-bottom:10px}
.sug-reason{font-size:12px;color:var(--muted);margin-top:10px;line-height:1.5}

.set-block{margin-bottom:16px;padding-bottom:16px;border-bottom:1px solid var(--border)}
.set-block:last-child{border-bottom:none;margin-bottom:0;padding-bottom:0}
.set-name{font-family:var(--fm);font-size:11px;color:var(--accent2);margin-bottom:8px;letter-spacing:.5px}

.combo-group{margin-bottom:14px}
.combo-group-hdr{display:inline-block;font-size:11px;color:var(--muted);font-family:var(--fm);margin-bottom:7px;padding:3px 8px;background:var(--surface);border:1px solid var(--border);border-radius:4px}
.combo-list{display:flex;flex-wrap:wrap;gap:6px}
.combo-pill{display:flex;gap:5px;align-items:center;background:var(--surface);border:1px solid var(--border);border-radius:20px;padding:4px 10px;font-size:11px;font-family:var(--fm);transition:border-color .2s;cursor:default}
.combo-pill:hover{border-color:var(--accent)}
.combo-pill .dot{width:5px;height:5px;border-radius:50%;background:var(--accent);flex-shrink:0}

#loading{position:fixed;inset:0;background:rgba(9,11,16,.95);display:flex;flex-direction:column;align-items:center;justify-content:center;z-index:999;gap:16px}
.spinner{width:50px;height:50px;border:3px solid var(--border);border-top-color:var(--accent);border-radius:50%;animation:spin 1s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
.loading-text{font-family:var(--fh);font-size:1.3rem;color:var(--accent);letter-spacing:3px}
.loading-sub{font-size:12px;color:var(--muted);font-family:var(--fm)}

.no-data{color:var(--muted);font-size:13px;padding:14px 0}
.disclaimer{font-size:11px;color:var(--muted);line-height:1.6;margin-bottom:18px;padding:10px 14px;background:var(--surface);border-radius:8px;border-left:3px solid var(--border)}
</style>
</head>
<body>

<div id="loading">
  <div class="spinner"></div>
  <div class="loading-text">FETCHING DRAWS</div>
  <div class="loading-sub">Scraping results &amp; running analysis…</div>
</div>

<header>
  <div>
    <div class="logo">UK <em>49s</em></div>
    <div class="tagline">INTELLIGENCE DASHBOARD</div>
  </div>
  <div class="header-right">
    <div id="data-badge" class="data-badge"><div class="dot"></div><span id="data-status">—</span></div>
    <span id="fetch-time">—</span>
    <button class="btn btn-primary" id="refresh-btn" onclick="loadData()">↻ REFRESH</button>
  </div>
</header>

<nav>
  <button class="tab active" onclick="showTab('results',this)">📋 Results</button>
  <button class="tab" onclick="showTab('analysis',this)">📊 Analysis</button>
  <button class="tab" onclick="showTab('suggestions',this)">💡 Suggestions</button>
  <button class="tab" onclick="showTab('sets',this)">📐 Set Combos</button>
</nav>

<main>
  <div id="results" class="section active">
    <div id="hero-block"></div>
    <div class="grid2">
      <div class="card"><div class="card-title">Lunchtime Results <span class="card-sub">Latest 25 draws</span></div><div id="table-lunch"><p class="no-data">Loading…</p></div></div>
      <div class="card"><div class="card-title">Teatime Results <span class="card-sub">Latest 10 draws</span></div><div id="table-tea"><p class="no-data">Loading…</p></div></div>
    </div>
  </div>

  <div id="analysis" class="section">
    <div class="stats-row" id="stats-row"></div>
    <div class="grid2">
      <div class="card"><div class="card-title">🔥 Hot &amp; ❄ Cold Numbers</div><div id="hot-cold"></div></div>
      <div class="card"><div class="card-title">🎨 Colour Band Distribution</div><div id="colour-dist"></div></div>
    </div>
    <div class="card"><div class="card-title">📊 Frequency Chart <span class="card-sub">Numbers 1–49 · all draws</span></div><div id="freq-chart"></div></div>
    <div class="card"><div class="card-title">🔢 Ending Digit Distribution</div><div id="digit-dist"></div></div>
  </div>

  <div id="suggestions" class="section">
    <div class="card">
      <div class="card-title">💡 Suggested Winning Combos</div>
      <div class="disclaimer">⚠️ Suggestions are generated algorithmically from frequency data and set analysis. Lotteries are random — past results do not predict future draws. Play responsibly.</div>
      <div id="sugs-list"></div>
    </div>
  </div>

  <div id="sets" class="section">
    <div class="card">
      <div class="card-title">📐 Generated Sets <span class="card-sub">From latest draw · valid range 1–49</span></div>
      <div class="disclaimer">Sets S1–S5 are derived from arithmetic formulas applied to the most recent draw result. S4 requires a TSE code (not available from scraper) and is omitted.</div>
      <div id="sets-block"></div>
    </div>
    <div class="grid2">
      <div class="card"><div class="card-title">Combos by Colour Group</div><div id="combos-colour"></div></div>
      <div class="card"><div class="card-title">Combos by Ending Digit</div><div id="combos-digit"></div></div>
    </div>
  </div>
</main>

<script>
function ballBg(n){
  if(n<=9)  return '#c9392a';
  if(n<=19) return '#c06318';
  if(n<=29) return '#a88000';
  if(n<=39) return '#2a8050';
  if(n<=49) return '#2a5ea8';
  if(n<=59) return '#7a4e2c';
  return '#6a35a8';
}
function fg(hex){
  const r=parseInt(hex.slice(1,3),16),g=parseInt(hex.slice(3,5),16),b=parseInt(hex.slice(5,7),16);
  return(0.299*r+0.587*g+0.114*b)>115?'#000':'#fff';
}
function ball(n,cls=''){
  const bg=ballBg(n),f=fg(bg);
  return `<div class="ball ${cls}" style="background:${bg};color:${f}">${n}</div>`;
}
function ballRow(nums,booster,cls=''){
  let h=nums.map(n=>ball(n,cls)).join('');
  if(booster)h+=`<span class="booster-sep">|</span>`+ball(booster,cls);
  return `<div class="ball-row">${h}</div>`;
}

function showTab(id,el){
  document.querySelectorAll('.section').forEach(s=>s.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
  document.getElementById(id).classList.add('active');
  el.classList.add('active');
}

function renderHero(d){
  document.getElementById('hero-block').innerHTML=`
    <div class="hero">
      <div class="hero-eyebrow">most recent lunchtime draw</div>
      <div class="hero-date">${d.date}</div>
      <div class="hero-title">LATEST RESULT</div>
      ${ballRow(d.numbers,d.booster,'ball-lg')}
    </div>`;
}

function renderTable(rows,elId){
  if(!rows||!rows.length){document.getElementById(elId).innerHTML='<p class="no-data">No data available.</p>';return;}
  let h='<table class="rtable"><thead><tr><th>Date</th><th>Numbers + Booster</th><th>Link</th></tr></thead><tbody>';
  rows.forEach(r=>{
    const lnk=r.detail_url?`<a href="${r.detail_url}" target="_blank">View ↗</a>`:'—';
    h+=`<tr><td class="date-cell">${r.date}</td><td>${ballRow(r.numbers,r.booster,'ball-sm')}</td><td>${lnk}</td></tr>`;
  });
  h+='</tbody></table>';
  document.getElementById(elId).innerHTML=h;
}

function renderAnalysis(a){
  document.getElementById('stats-row').innerHTML=`
    <div class="stat-box"><div class="stat-val">${a.total_draws}</div><div class="stat-lbl">Draws Analysed</div></div>
    <div class="stat-box"><div class="stat-val">${a.hot&&a.hot[0]?a.hot[0]:'—'}</div><div class="stat-lbl">Hottest Ball</div></div>
    <div class="stat-box"><div class="stat-val">${a.cold&&a.cold.length?a.cold[a.cold.length-1]:'—'}</div><div class="stat-lbl">Coldest Ball</div></div>
    <div class="stat-box"><div class="stat-val">${a.latest_numbers?a.latest_numbers.length:'—'}</div><div class="stat-lbl">Balls / Draw</div></div>`;

  document.getElementById('hot-cold').innerHTML=`
    <div class="hc-wrap">
      <div class="hc-col"><div class="hc-label hot">🔥 Hot</div><div class="ball-row">${(a.hot||[]).map(n=>ball(n,'ball-sm')).join('')}</div></div>
      <div class="hc-col"><div class="hc-label cold">❄ Cold</div><div class="ball-row">${(a.cold||[]).map(n=>ball(n,'ball-sm')).join('')}</div></div>
    </div>`;

  const colours={Red:'#c9392a',Orange:'#c06318',Yellow:'#a88000',Green:'#2a8050',Blue:'#2a5ea8',Brown:'#7a4e2c',Purple:'#6a35a8'};
  const cHtml=Object.entries(a.colour_dist||{}).map(([c,cnt])=>`<span class="colour-badge" style="background:${colours[c]||'#555'};color:#fff">${c} <strong>${cnt}</strong></span>`).join('');
  document.getElementById('colour-dist').innerHTML=`<div class="colour-wrap">${cHtml}</div>`;

  const freq=a.freq||{};
  const maxF=Math.max(...Object.values(freq),1);
  let fc='<div class="freq-wrap">';
  for(let n=1;n<=49;n++){
    const cnt=freq[n]||0,h=Math.round((cnt/maxF)*56),bg=ballBg(n);
    fc+=`<div class="freq-cell" title="${n}: ${cnt}x"><div class="freq-num" style="color:${bg}">${n}</div><div class="freq-bar" style="height:${h}px;background:${bg}"></div><div class="freq-cnt">${cnt}</div></div>`;
  }
  document.getElementById('freq-chart').innerHTML=fc+'</div>';

  const dd=a.digit_dist||{},maxD=Math.max(...Object.values(dd),1);
  let ddh='<div class="digit-wrap">';
  for(let d=0;d<=9;d++){
    const cnt=dd[d]||0,h=Math.round((cnt/maxD)*80);
    ddh+=`<div class="digit-col"><div class="digit-cnt">${cnt}</div><div class="digit-bar" style="height:${h}px"></div><div class="digit-lbl">…${d}</div></div>`;
  }
  document.getElementById('digit-dist').innerHTML=ddh+'</div>';
}

function renderSuggestions(sugs){
  document.getElementById('sugs-list').innerHTML=(sugs||[]).map(s=>`
    <div class="sug-item">
      <div class="sug-label">${s.label}</div>
      <div class="ball-row">${s.numbers.map(n=>ball(n)).join('')}</div>
      <div class="sug-reason">${s.reason}</div>
    </div>`).join('')||'<p class="no-data">No suggestions.</p>';
}

function renderSets(sets){
  document.getElementById('sets-block').innerHTML=Object.entries(sets||{}).map(([name,nums])=>
    nums.length?`<div class="set-block"><div class="set-name">${name}</div><div class="ball-row">${nums.map(n=>ball(n,'ball-sm')).join('')}</div></div>`:''
  ).join('')||'<p class="no-data">No sets generated.</p>';
}

function renderCombos(combos,elId){
  document.getElementById(elId).innerHTML=(combos||[]).map(g=>`
    <div class="combo-group">
      <div class="combo-group-hdr">${g.group}</div>
      <div class="combo-list">${g.combos.map(c=>`<div class="combo-pill"><div class="dot"></div>${c.join(' · ')}</div>`).join('')}</div>
    </div>`).join('')||'<p class="no-data">No combos found (need ≥3 per group).</p>';
}

async function loadData(){
  document.getElementById('loading').style.display='flex';
  document.getElementById('refresh-btn').disabled=true;
  try{
    const data=await(await fetch('/api/data')).json();
    document.getElementById('fetch-time').textContent=data.fetched_at;
    const badge=document.getElementById('data-badge');
    if(data.live){badge.className='data-badge live';document.getElementById('data-status').textContent='LIVE DATA';}
    else{badge.className='data-badge';document.getElementById('data-status').textContent='DEMO DATA (site unreachable)';}
    if(data.lunchtime&&data.lunchtime.length) renderHero(data.lunchtime[0]);
    renderTable(data.lunchtime,'table-lunch');
    renderTable(data.teatime,'table-tea');
    const a=data.analysis;
    if(a&&Object.keys(a).length){
      renderAnalysis(a);renderSuggestions(a.suggested);
      renderSets(a.sets);renderCombos(a.combos_colour,'combos-colour');renderCombos(a.combos_digit,'combos-digit');
    }
  }catch(e){alert('Error: '+e.message);}
  finally{document.getElementById('loading').style.display='none';document.getElementById('refresh-btn').disabled=false;}
}

loadData();
</script>
</body>
</html>"""

if __name__ == "__main__":
    print("\n  UK 49s Intelligence Dashboard")
    print("  ─────────────────────────────")
    print("  Open http://localhost:5000 in your browser\n")
    app.run(debug=False, port=5000)
