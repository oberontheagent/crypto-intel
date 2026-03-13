#!/usr/bin/env python3
"""Crypto Intel Feed Collector — collects news, market data, and social posts."""

import json
import os
import sys
import time
import logging
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path

import feedparser
import requests
from bs4 import BeautifulSoup
from dateutil import parser as dateparser

# --- Config ---

NZT = timezone(timedelta(hours=13))
NOW = datetime.now(NZT)
STAMP = NOW.strftime("%Y-%m-%d-%H")
DATA_DIR = Path(__file__).parent / "data"
LOG_DIR = Path(__file__).parent / "logs"

RSS_FEEDS = {
    "CoinTelegraph": "https://cointelegraph.com/rss",
    "The Block": "https://www.theblock.co/rss.xml",
    "Decrypt": "https://decrypt.co/feed",
    "Bitcoin Magazine": "https://bitcoinmagazine.com/feed",
    "The Defiant": "https://thedefiant.io/feed",
    "CryptoSlate": "https://cryptoslate.com/feed/",
    "Bankless": "https://bankless.substack.com/feed",
    "Unchained": "https://unchainedcrypto.com/feed/",
    "Protos": "https://protos.com/feed/",
    "Messari News": "https://messari.io/rss/news",
}

REDDIT_FEEDS = {
    "CryptoCurrency": "https://www.reddit.com/r/CryptoCurrency/top.rss?t=day",
    "Bitcoin": "https://www.reddit.com/r/Bitcoin/hot.rss",
    "ethereum": "https://www.reddit.com/r/ethereum/hot.rss",
}

COINGECKO_TRENDING = "https://api.coingecko.com/api/v3/search/trending"
COINGECKO_MARKETS = "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=percent_change_24h_desc&per_page=10&page=1&sparkline=false"
COINGECKO_PRICES = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,solana&vs_currencies=usd&include_24hr_change=true"

COINGECKO_GLOBAL = "https://api.coingecko.com/api/v3/global"
COINGECKO_FEAR_GREED = "https://api.alternative.me/fng/?limit=3"  # Fear & Greed Index (free, no key)
COINGECKO_TOP_VOLUME = "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=volume_desc&per_page=10&page=1&sparkline=false"
# CoinGlass requires paid API — placeholder for future upgrade
# COINGLASS_LIQUIDATIONS = "https://open-api.coinglass.com/public/v2/liquidation_history"
# COINGLASS_FUNDING = "https://open-api.coinglass.com/public/v2/funding"

COINGECKO_API_KEY = os.environ.get("COINGECKO_API_KEY", "")
HEADERS = {"User-Agent": "CryptoIntelBot/1.0 (news aggregation)"}
COINGECKO_HEADERS = {
    **HEADERS,
    **({"x-cg-demo-api-key": COINGECKO_API_KEY} if COINGECKO_API_KEY else {}),
}

MAX_RETRIES = 3
RETRY_DELAY = 2
RSS_DELAY = 1

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("feed_collector")


def fetch_with_retry(url, headers=None, timeout=15):
    """GET with retry logic."""
    hdrs = {**HEADERS, **(headers or {})}
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(url, headers=hdrs, timeout=timeout)
            resp.raise_for_status()
            return resp
        except Exception as e:
            log.warning(f"Attempt {attempt}/{MAX_RETRIES} failed for {url}: {e}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)
    return None


# --- RSS ---

def collect_rss():
    articles = []
    errors = []
    for source, url in RSS_FEEDS.items():
        log.info(f"Fetching RSS: {source}")
        try:
            resp = fetch_with_retry(url)
            if resp is None:
                errors.append(f"RSS:{source} — all retries failed")
                continue
            feed = feedparser.parse(resp.text)
            for entry in feed.entries[:15]:
                articles.append({
                    "source": source,
                    "title": entry.get("title", ""),
                    "link": entry.get("link", ""),
                    "published": entry.get("published", ""),
                    "summary": (entry.get("summary", "") or "")[:500],
                })
        except Exception as e:
            errors.append(f"RSS:{source} — {e}")
        time.sleep(RSS_DELAY)
    return articles, errors


# --- CoinGecko ---

def collect_coingecko():
    market = {}
    errors = []

    log.info("Fetching CoinGecko prices")
    resp = fetch_with_retry(COINGECKO_PRICES, headers=COINGECKO_HEADERS)
    if resp:
        market["prices"] = resp.json()
    else:
        errors.append("CoinGecko:prices — failed")
    time.sleep(1)

    log.info("Fetching CoinGecko trending")
    resp = fetch_with_retry(COINGECKO_TRENDING, headers=COINGECKO_HEADERS)
    if resp:
        data = resp.json()
        coins = data.get("coins", [])
        market["trending"] = [
            {"name": c["item"]["name"], "symbol": c["item"]["symbol"], "rank": c["item"].get("market_cap_rank")}
            for c in coins[:10]
        ]
    else:
        errors.append("CoinGecko:trending — failed")
    time.sleep(1)

    log.info("Fetching CoinGecko markets")
    resp = fetch_with_retry(COINGECKO_MARKETS, headers=COINGECKO_HEADERS)
    if resp:
        data = resp.json()
        if isinstance(data, list):
            market["top_movers"] = [
                {"name": c["name"], "symbol": c["symbol"], "price": c.get("current_price"),
                 "change_24h": c.get("price_change_percentage_24h")}
                for c in data[:10]
            ]
        else:
            market["top_movers"] = []
            errors.append("CoinGecko:markets — unexpected response format")
    else:
        errors.append("CoinGecko:markets — failed")

    log.info("Fetching CoinGecko global market data")
    resp = fetch_with_retry(COINGECKO_GLOBAL, headers=COINGECKO_HEADERS)
    if resp:
        gdata = resp.json().get("data", {})
        market["global"] = {
            "total_market_cap_usd": gdata.get("total_market_cap", {}).get("usd"),
            "total_volume_usd": gdata.get("total_volume", {}).get("usd"),
            "btc_dominance": gdata.get("market_cap_percentage", {}).get("btc"),
            "eth_dominance": gdata.get("market_cap_percentage", {}).get("eth"),
            "market_cap_change_24h": gdata.get("market_cap_change_percentage_24h_usd"),
            "active_coins": gdata.get("active_cryptocurrencies"),
        }
    else:
        errors.append("CoinGecko:global — failed")
    time.sleep(1)

    log.info("Fetching CoinGecko top by volume")
    resp = fetch_with_retry(COINGECKO_TOP_VOLUME, headers=COINGECKO_HEADERS)
    if resp and isinstance(resp.json(), list):
        market["top_by_volume"] = [
            {"name": c["name"], "symbol": c["symbol"],
             "price": c.get("current_price"), "volume_24h": c.get("total_volume"),
             "change_24h": c.get("price_change_percentage_24h")}
            for c in resp.json()[:10]
        ]
    else:
        errors.append("CoinGecko:top_volume — failed")
    time.sleep(1)

    return market, errors


# --- Fear & Greed Index ---

def collect_fear_greed():
    log.info("Fetching Fear & Greed Index")
    errors = []
    try:
        resp = fetch_with_retry(COINGECKO_FEAR_GREED)
        if resp:
            data = resp.json().get("data", [])
            return [{"value": d["value"], "classification": d["value_classification"],
                     "timestamp": d["timestamp"]} for d in data[:3]], errors
        errors.append("Fear&Greed — request failed")
    except Exception as e:
        errors.append(f"Fear&Greed — {e}")
    return [], errors


# --- CoinMarketCap ---

def collect_coinmarketcap():
    articles = []
    errors = []
    log.info("Fetching CoinMarketCap headlines")
    url = "https://coinmarketcap.com/headlines/news/"
    resp = fetch_with_retry(url)
    if resp is None:
        errors.append("CoinMarketCap — request failed")
        return articles, errors
    try:
        soup = BeautifulSoup(resp.text, "html.parser")
        for a in soup.find_all("a", href=True):
            title = a.get_text(strip=True)
            href = a["href"]
            if title and len(title) > 20 and "/headlines/" in href:
                full_url = href if href.startswith("http") else f"https://coinmarketcap.com{href}"
                articles.append({"source": "CoinMarketCap", "title": title, "link": full_url, "published": "", "summary": ""})
        if not articles:
            errors.append("CoinMarketCap — no articles found (may be JS-rendered)")
    except Exception as e:
        errors.append(f"CoinMarketCap — parse error: {e}")
    return articles, errors


# --- Collective Shift ---

def collect_collective_shift():
    articles = []
    errors = []
    log.info("Fetching Collective Shift")

    # Try RSS first
    for url in ["https://collectiveshift.io/feed/", "https://collectiveshift.io/news/"]:
        resp = fetch_with_retry(url)
        if resp and "xml" in resp.headers.get("content-type", "").lower():
            feed = feedparser.parse(resp.text)
            for entry in feed.entries[:10]:
                articles.append({
                    "source": "Collective Shift",
                    "title": entry.get("title", ""),
                    "link": entry.get("link", ""),
                    "published": entry.get("published", ""),
                    "summary": (entry.get("summary", "") or "")[:500],
                })
            if articles:
                return articles, errors

    # Fallback: scrape
    resp = fetch_with_retry("https://collectiveshift.io/")
    if resp:
        try:
            soup = BeautifulSoup(resp.text, "html.parser")
            for a in soup.find_all("a", href=True):
                title = a.get_text(strip=True)
                href = a["href"]
                if title and len(title) > 15 and ("article" in href or "news" in href or "research" in href):
                    full_url = href if href.startswith("http") else f"https://collectiveshift.io{href}"
                    articles.append({"source": "Collective Shift", "title": title, "link": full_url, "published": "", "summary": ""})
            if not articles:
                errors.append("Collective Shift — no articles found")
        except Exception as e:
            errors.append(f"Collective Shift — scrape error: {e}")
    else:
        errors.append("Collective Shift — request failed")
    return articles, errors


# --- Reddit ---

def collect_reddit():
    posts = []
    errors = []
    for sub, url in REDDIT_FEEDS.items():
        log.info(f"Fetching Reddit: r/{sub}")
        resp = fetch_with_retry(url)
        if resp is None:
            errors.append(f"Reddit:r/{sub} — failed")
            continue
        try:
            feed = feedparser.parse(resp.text)
            for entry in feed.entries[:10]:
                posts.append({
                    "subreddit": sub,
                    "title": entry.get("title", ""),
                    "url": entry.get("link", ""),
                    "score": 0,
                })
        except Exception as e:
            errors.append(f"Reddit:r/{sub} — {e}")
        time.sleep(RSS_DELAY)
    return posts, errors


# --- X/Twitter via xurl ---

def collect_x_posts():
    posts = []
    errors = []

    searches = [
        '(#Bitcoin OR #Ethereum OR #DeFi OR #crypto) -is:retweet lang:en',
        'from:WuBlockchain OR from:lookonchain OR from:glassnode -is:retweet',
    ]
    counts = [20, 15]

    for query, n in zip(searches, counts):
        log.info(f"Fetching X posts: {query[:50]}...")
        try:
            result = subprocess.run(
                ["xurl", "search", query, "-n", str(n)],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode != 0:
                errors.append(f"xurl — exit {result.returncode}: {result.stderr.strip()[:200]}")
                continue
            for line in result.stdout.strip().splitlines():
                try:
                    obj = json.loads(line)
                    posts.append({
                        "text": obj.get("text", obj.get("full_text", "")),
                        "author": obj.get("user", {}).get("screen_name", obj.get("author", "")),
                        "url": obj.get("url", ""),
                    })
                except json.JSONDecodeError:
                    # xurl may output URLs or non-JSON — treat as URL
                    if line.startswith("http"):
                        posts.append({"text": "", "author": "", "url": line.strip()})
        except FileNotFoundError:
            errors.append("xurl — command not found, skipping X posts")
            break
        except subprocess.TimeoutExpired:
            errors.append("xurl — timeout")
        except Exception as e:
            errors.append(f"xurl — {e}")

    return posts, errors


# --- Main ---

def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    all_errors = []

    log.info("=== Crypto Intel Feed Collection Starting ===")

    rss_articles, errs = collect_rss()
    all_errors.extend(errs)

    cmc_articles, errs = collect_coinmarketcap()
    all_errors.extend(errs)
    rss_articles.extend(cmc_articles)

    cs_articles, errs = collect_collective_shift()
    all_errors.extend(errs)
    rss_articles.extend(cs_articles)

    market_data, errs = collect_coingecko()
    all_errors.extend(errs)

    fear_greed, errs = collect_fear_greed()
    all_errors.extend(errs)

    reddit_posts, errs = collect_reddit()
    all_errors.extend(errs)

    x_posts, errs = collect_x_posts()
    all_errors.extend(errs)

    output = {
        "collected_at": NOW.isoformat(),
        "rss_articles": rss_articles,
        "market_data": market_data,
        "fear_greed": fear_greed,
        "derivatives": {"note": "CoinGlass requires paid API — upgrade planned"},
        "reddit_posts": reddit_posts,
        "x_posts": x_posts,
        "errors": all_errors,
    }

    out_file = DATA_DIR / f"feeds-{STAMP}.json"
    with open(out_file, "w") as f:
        json.dump(output, f, indent=2, default=str)
    log.info(f"Saved feed data to {out_file}")

    # Symlink latest (full)
    latest = DATA_DIR / "latest-feeds.json"
    if latest.is_symlink() or latest.exists():
        latest.unlink()
    latest.symlink_to(out_file.name)
    log.info(f"Symlinked latest-feeds.json -> {out_file.name}")

    # Save condensed version for analysis agent (titles + links only, no summaries)
    condensed = {
        "collected_at": output["collected_at"],
        "rss_articles": [
            {"source": a["source"], "title": a["title"], "link": a["link"], "published": a.get("published", "")}
            for a in output["rss_articles"][:80]
        ],
        "market_data": output["market_data"],
        "fear_greed": output["fear_greed"],
        "reddit_posts": [
            {"subreddit": p["subreddit"], "title": p["title"], "url": p["url"]}
            for p in output["reddit_posts"][:20]
        ],
        "x_posts": output["x_posts"][:20],
        "errors": output["errors"],
    }
    condensed_file = DATA_DIR / "latest-feeds-condensed.json"
    with open(condensed_file, "w") as f:
        json.dump(condensed, f, indent=2, default=str)
    log.info(f"Saved condensed feed data to {condensed_file}")

    log.info(f"Collection complete: {len(rss_articles)} articles, {len(reddit_posts)} reddit posts, {len(x_posts)} X posts, {len(all_errors)} errors")
    if all_errors:
        log.warning(f"Errors encountered: {all_errors}")

    return 0 if len(all_errors) < len(RSS_FEEDS) else 1


if __name__ == "__main__":
    sys.exit(main())
