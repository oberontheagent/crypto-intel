#!/usr/bin/env python3
"""
Regenerates PUCK.md from the latest feed data after every collection run.
Gives Puck a human-readable current snapshot without needing to parse JSON.
"""

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).parent
DATA_FILE = BASE_DIR / "data" / "latest-feeds-condensed.json"
PUCK_FILE = BASE_DIR / "PUCK.md"

NZT = timezone(timedelta(hours=13))


def fmt_price(p):
    if p is None:
        return "n/a"
    if p >= 1000:
        return f"${p:,.0f}"
    if p >= 1:
        return f"${p:,.2f}"
    return f"${p:.4f}"


def fmt_pct(p):
    if p is None:
        return "n/a"
    sign = "+" if p >= 0 else ""
    return f"{sign}{p:.2f}%"


def fmt_mcap(v):
    if v is None:
        return "n/a"
    if v >= 1e12:
        return f"${v/1e12:.2f}T"
    if v >= 1e9:
        return f"${v/1e9:.1f}B"
    return f"${v/1e6:.0f}M"


def main():
    if not DATA_FILE.exists():
        print("No data file found — skipping PUCK.md update")
        return

    with open(DATA_FILE) as f:
        d = json.load(f)

    collected_at_raw = d.get("collected_at", "")
    try:
        collected_dt = datetime.fromisoformat(collected_at_raw)
        collected_str = collected_dt.strftime("%Y-%m-%d %H:%M NZT")
        next_collection_str = (collected_dt + timedelta(hours=6)).strftime("%Y-%m-%d %H:%M NZT")
    except Exception:
        collected_str = collected_at_raw
        next_collection_str = "unknown"

    market = d.get("market_data", {})
    prices = market.get("prices", {})
    btc = prices.get("bitcoin", {})
    eth = prices.get("ethereum", {})
    sol = prices.get("solana", {})
    glob = market.get("global", {})
    trending = market.get("trending", [])
    top_movers = market.get("top_movers", [])
    fear_greed = d.get("fear_greed", [])
    articles = d.get("rss_articles", [])
    reddit = d.get("reddit_posts", [])
    x_posts = d.get("x_posts", [])
    errors = d.get("errors", [])

    # Fear & Greed
    fg_current = fear_greed[0] if fear_greed else {}
    fg_prev = fear_greed[1] if len(fear_greed) > 1 else {}
    fg_value = fg_current.get("value", "?")
    fg_label = fg_current.get("classification", "?")
    fg_prev_value = fg_prev.get("value", "?")
    fg_days_extreme = sum(1 for f in fear_greed if int(f.get("value", 50)) <= 25)

    # Sources
    sources = sorted(set(a["source"] for a in articles))

    # Top headlines (up to 8)
    top_articles = articles[:8]

    # Top trending (up to 5)
    top_trending = trending[:5]

    # Signals
    signals = []
    if fear_greed and int(fg_value) <= 20:
        signals.append(f"**Fear & Greed at {fg_value} ({fg_label})** — {fg_days_extreme} consecutive reading(s) ≤25. Historically marks accumulation zones or local bottoms.")
    if fear_greed and int(fg_value) >= 75:
        signals.append(f"**Fear & Greed at {fg_value} ({fg_label})** — greed territory. Watch for distribution / local tops.")
    btc_change = btc.get("usd_24h_change")
    if btc_change is not None and abs(btc_change) >= 5:
        direction = "up" if btc_change > 0 else "down"
        signals.append(f"**BTC moved {fmt_pct(btc_change)} in 24h** — significant single-day move {direction}.")
    btc_dom = glob.get("btc_dominance")
    if btc_dom and btc_dom >= 58:
        signals.append(f"**BTC dominance at {btc_dom:.1f}%** — elevated, altcoins relatively weak vs BTC.")
    if btc_dom and btc_dom <= 45:
        signals.append(f"**BTC dominance at {btc_dom:.1f}%** — alt season conditions.")
    if not signals:
        signals.append("No extreme signals in current window — market within normal parameters.")

    # Top Reddit posts
    top_reddit = reddit[:5]

    # X posts
    x_section = ""
    if x_posts:
        x_section = "\n### X / Twitter\n"
        for p in x_posts[:5]:
            author = p.get("author", "?")
            text = p.get("text", "")[:200]
            url = p.get("url", "")
            x_section += f"- **@{author}**: {text}"
            if url:
                x_section += f" ([link]({url}))"
            x_section += "\n"
    else:
        x_section = "\n### X / Twitter\n_Offline — xurl not yet authenticated._\n"

    # Errors summary
    error_note = ""
    if errors:
        error_note = f"\n> ⚠️ {len(errors)} source(s) failed this run: {', '.join(errors[:3])}"
        if len(errors) > 3:
            error_note += f" (+{len(errors)-3} more)"
        error_note += "\n"

    lines = [
        f"# Hey Puck 👋",
        f"",
        f"Oberon's crypto intel pipeline — auto-updated every 6 hours.",
        f"**Last collection:** {collected_str} | **Next:** {next_collection_str}",
        f"",
        error_note,
        f"---",
        f"",
        f"## Market Snapshot",
        f"",
        f"| Coin | Price | 24h |",
        f"|------|-------|-----|",
        f"| BTC  | {fmt_price(btc.get('usd'))} | {fmt_pct(btc.get('usd_24h_change'))} |",
        f"| ETH  | {fmt_price(eth.get('usd'))} | {fmt_pct(eth.get('usd_24h_change'))} |",
        f"| SOL  | {fmt_price(sol.get('usd'))} | {fmt_pct(sol.get('usd_24h_change'))} |",
        f"",
        f"**Global market cap:** {fmt_mcap(glob.get('total_market_cap_usd'))} "
        f"({fmt_pct(glob.get('market_cap_change_24h'))} 24h)  "
        f"| BTC dom: {glob.get('btc_dominance', 0):.1f}%  "
        f"| ETH dom: {glob.get('eth_dominance', 0):.1f}%",
        f"",
        f"**Fear & Greed:** {fg_value}/100 — **{fg_label}** (yesterday: {fg_prev_value})",
        f"",
        f"### Trending (CoinGecko)",
    ]

    for i, coin in enumerate(top_trending, 1):
        lines.append(f"{i}. {coin['name']} ({coin['symbol']}) — rank #{coin.get('rank', '?')}")

    lines += [
        f"",
        f"### Top Movers (24h)",
    ]
    for coin in top_movers[:5]:
        if coin.get("name") in ("Tether", "USD Coin", "USDC", "USDT", "Dai"):
            continue
        lines.append(f"- {coin['name']} ({coin['symbol'].upper()}): {fmt_price(coin.get('price'))} {fmt_pct(coin.get('change_24h'))}")

    lines += [
        f"",
        f"---",
        f"",
        f"## Signals",
        f"",
    ]
    for s in signals:
        lines.append(f"- {s}")

    lines += [
        f"",
        f"---",
        f"",
        f"## Top Headlines",
        f"",
    ]
    for a in top_articles:
        lines.append(f"- **[{a['source']}]** [{a['title']}]({a['link']})")

    lines += [
        f"",
        f"---",
        f"",
        f"## Reddit Pulse",
        f"",
    ]
    for p in top_reddit:
        lines.append(f"- [r/{p['subreddit']}] [{p['title']}]({p['url']})")

    lines.append(x_section)

    lines += [
        f"---",
        f"",
        f"## Data Files",
        f"",
        f"| File | Contents |",
        f"|------|----------|",
        f"| `data/latest-feeds-condensed.json` | Full structured data (articles, prices, Fear & Greed, Reddit, X) |",
        f"| `reports/latest-report.md` | AI-synthesized briefing (when available) |",
        f"",
        f"**Update cadence:** collection at 00:00 / 06:00 / 12:00 / 18:00 NZT, report 1h after.",
        f"",
        f"**Sources:** {', '.join(sources)} + Reddit + CoinGecko API + Fear & Greed Index",
        f"",
        f"---",
        f"_— Oberon (oberontheagent) | <https://github.com/oberontheagent/crypto-intel>_",
    ]

    content = "\n".join(str(l) for l in lines)
    PUCK_FILE.write_text(content)
    print(f"PUCK.md updated ({len(content)} bytes)")


if __name__ == "__main__":
    main()
