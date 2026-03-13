# Crypto Intel Pipeline

Automated crypto intelligence collection and analysis pipeline. Collects news, market data, and social posts every 6 hours, then synthesizes them into a formatted intelligence report.

## Scripts

| Script | Purpose |
|--------|---------|
| `setup.sh` | Create venv, install deps, set up directories |
| `feed_collector.py` | Collect RSS feeds, CoinGecko, CoinGlass, Reddit, X posts |
| `analysis_agent.py` | Analyze collected data and produce an intel report via OpenAI |
| `run_crypto_intel.sh` | Run feed collector with logging |
| `run_analysis.sh` | Run analysis agent with logging |

## Setup

```bash
chmod +x setup.sh && ./setup.sh
export OPENAI_API_KEY='your-key-here'
```

## Usage

```bash
# Collect feeds
./run_crypto_intel.sh

# Generate report (run after collection)
./run_analysis.sh
```

## Cron Schedule

Run collection every 6 hours, analysis 1 hour later:

```cron
# Feed collection at 00:00, 06:00, 12:00, 18:00 UTC
0 0,6,12,18 * * * cd /Users/oberon/.openclaw/workspace/projects/crypto-intel && ./run_crypto_intel.sh

# Analysis at 01:00, 07:00, 13:00, 19:00 UTC
0 1,7,13,19 * * * cd /Users/oberon/.openclaw/workspace/projects/crypto-intel && ./run_analysis.sh
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | Yes (for analysis) | OpenAI API key for report generation |

## Data Format

Feed data is saved to `data/feeds-YYYY-MM-DD-HH.json`:

```json
{
  "collected_at": "ISO timestamp",
  "rss_articles": [{"source": "", "title": "", "link": "", "published": "", "summary": ""}],
  "market_data": {"prices": {}, "trending": [], "top_movers": []},
  "derivatives": {"liquidations": {}, "funding": {}},
  "reddit_posts": [{"subreddit": "", "title": "", "url": "", "score": 0}],
  "x_posts": [{"text": "", "author": "", "url": ""}],
  "errors": []
}
```

`data/latest-feeds.json` is a symlink to the most recent collection.

Reports are saved to `reports/report-YYYY-MM-DD-HH.md` and `reports/latest-report.md`.

## Adding New RSS Sources

Edit `RSS_FEEDS` dict in `feed_collector.py`:

```python
RSS_FEEDS = {
    # ...existing feeds...
    "New Source": "https://example.com/feed",
}
```

Sources are fetched with retry logic (3 attempts, 2s delay) and 1s delay between feeds. A failed source won't crash the pipeline.

## Directory Structure

```
crypto-intel/
├── data/              # Feed JSON files
├── logs/              # Collection and analysis logs
├── reports/           # Generated intel reports
├── feed_collector.py  # Feed collection script
├── analysis_agent.py  # AI analysis script
├── run_crypto_intel.sh
├── run_analysis.sh
├── setup.sh
└── youtube_analyst.py # Separate YouTube analysis (unrelated)
```
