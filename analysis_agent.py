#!/usr/bin/env python3
"""Crypto Intel Analysis Agent — synthesizes feed data into an intelligence report."""

import json
import os
import sys
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

from openai import OpenAI

NZT = timezone(timedelta(hours=13))
NOW = datetime.now(NZT)
STAMP = NOW.strftime("%Y-%m-%d-%H")
DATA_DIR = Path(__file__).parent / "data"
REPORTS_DIR = Path(__file__).parent / "reports"
NEXT_COLLECTION = (NOW + timedelta(hours=6)).strftime("%Y-%m-%d %H:%M NZT")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("analysis_agent")


def load_feed_data():
    latest = DATA_DIR / "latest-feeds.json"
    if not latest.exists():
        log.error("No feed data found at data/latest-feeds.json — run feed_collector.py first")
        sys.exit(1)
    with open(latest) as f:
        return json.load(f)


def build_prompt(data):
    date_str = NOW.strftime("%A, %d %B %Y | %H:%M NZT")

    articles_text = ""
    for a in data.get("rss_articles", [])[:60]:
        articles_text += f"- [{a['source']}] {a['title']}\n  {a.get('link', '')}\n  {a.get('summary', '')[:200]}\n\n"

    market_text = json.dumps(data.get("market_data", {}), indent=2, default=str)
    fear_greed_text = json.dumps(data.get("fear_greed", []), indent=2, default=str)

    reddit_text = ""
    for p in data.get("reddit_posts", [])[:20]:
        reddit_text += f"- [r/{p['subreddit']}] {p['title']} ({p.get('url', '')})\n"

    x_text = ""
    for p in data.get("x_posts", [])[:20]:
        x_text += f"- @{p.get('author', '?')}: {p.get('text', '')[:280]} ({p.get('url', '')})\n"

    n_articles = len(data.get("rss_articles", []))
    n_sources = len(set(a["source"] for a in data.get("rss_articles", [])))
    n_xposts = len(data.get("x_posts", []))

    prompt = f"""You are a crypto intelligence analyst. Analyze the following data and produce a formatted Discord-ready intelligence report.

**Current date/time:** {date_str}

**NEWS ARTICLES ({n_articles} total from {n_sources} publications):**
{articles_text}

**MARKET DATA (CoinGecko — prices, trending, top movers, global market cap, top by volume):**
{market_text}

**FEAR & GREED INDEX (last 3 readings):**
{fear_greed_text}

**REDDIT POSTS:**
{reddit_text}

**X/TWITTER POSTS ({n_xposts}):**
{x_text}

**ERRORS DURING COLLECTION:**
{json.dumps(data.get("errors", []))}

---

Produce the report in EXACTLY this format (use Discord formatting, no markdown tables):

🔍 **CRYPTO INTEL REPORT** — {date_str}
━━━━━━━━━━━━━━━━━━━━━━━━━━

📰 **TOP STORIES**
• [headline] ([source link])
  ↳ [1-line significance]
(list 3-5 most important stories)

📈 **MARKET SNAPSHOT**
• BTC: $X (+Y%)  ETH: $X (+Y%)  SOL: $X (+Y%)
• Trending: [top trending coins from CoinGecko data]
• Sentiment: [Bullish/Bearish/Neutral] — [1-line reasoning]

📊 **MARKET STRUCTURE**
• Global market cap: $X (+Y% 24h)  BTC dom: X%  ETH dom: X%
• Fear & Greed: [value/100] — [classification] (vs [yesterday's value])
• Top volume coins: [top 3 by 24h volume]

🔮 **ANALYST TAKES**
• [Notable X post or analyst view with attribution]
(If no X data available, note that X monitoring is offline)

⚡ **EMERGING THEMES**
• [Theme 1 — brief explanation]
• [Theme 2 — brief explanation]
• [Theme 3 — brief explanation]

📡 Sources: {n_articles} articles · {n_sources} publications · {n_xposts} X posts
Next collection: {NEXT_COLLECTION}

IMPORTANT RULES:
- Use real data from the inputs above, do NOT fabricate prices or stories
- If data is missing for a section, say so honestly
- Keep it concise — this is a briefing, not an essay
- No markdown tables — Discord doesn't render them well
- Include source links where available
- Any Polymarket-relevant angles should be mentioned in Emerging Themes
"""
    return prompt


def generate_report(data):
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        log.error("OPENAI_API_KEY not set")
        sys.exit(1)

    client = OpenAI(api_key=api_key)
    prompt = build_prompt(data)

    # Try models in order of preference
    for model in ["o4-mini", "gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"]:
        try:
            log.info(f"Generating report with model: {model}")
            if model.startswith("o"):
                # o-series models use different params
                response = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                )
            else:
                response = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": "You are a crypto intelligence analyst producing concise briefings."},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.3,
                    max_tokens=3000,
                )
            return response.choices[0].message.content
        except Exception as e:
            log.warning(f"Model {model} failed: {e}")
            continue

    log.error("All models failed")
    sys.exit(1)


def main():
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    log.info("=== Crypto Intel Analysis Starting ===")

    data = load_feed_data()
    log.info(f"Loaded feed data collected at {data.get('collected_at', 'unknown')}")

    report = generate_report(data)

    # Save timestamped report
    report_file = REPORTS_DIR / f"report-{STAMP}.md"
    with open(report_file, "w") as f:
        f.write(report)
    log.info(f"Report saved to {report_file}")

    # Save latest report (overwrite)
    latest_file = REPORTS_DIR / "latest-report.md"
    with open(latest_file, "w") as f:
        f.write(report)
    log.info(f"Latest report saved to {latest_file}")

    # Print to stdout
    print("\n" + "=" * 60)
    print(report)
    print("=" * 60 + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
