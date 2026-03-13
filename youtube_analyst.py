#!/usr/bin/env python3
"""
Crypto Intel — YouTube Analyst (Agent 1)
Fetches latest videos from key crypto/macro channels, extracts transcripts,
and synthesizes analyst views into a daily report.
"""

import os
import sys
import json
import re
import datetime
import subprocess
import tempfile
import textwrap
from openai import OpenAI

# ── Config ───────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPORTS_DIR = os.path.join(BASE_DIR, "reports")
os.makedirs(REPORTS_DIR, exist_ok=True)

# How far back to look for videos (hours)
LOOKBACK_HOURS = 96  # 4 days — some channels post every few days

# Channels to monitor
CHANNELS = [
    {
        "handle": "@GarethSolowayProTrader",
        "name": "Gareth Soloway",
        "focus": "Technical analysis, macro, Bitcoin price targets",
        "url": "https://www.youtube.com/@GarethSolowayProTrader",
    },
    {
        "handle": "@CTOLARSSON",
        "name": "CTO Larsson",
        "focus": "Bitcoin cycles, long-term cycle theory, historical patterns",
        "url": "https://www.youtube.com/@CTOLARSSON",
    },
    {
        "handle": "@MilkRoadDaily",
        "name": "Milk Road",
        "focus": "Crypto news, opportunities, market narrative",
        "url": "https://www.youtube.com/@MilkRoadDaily",
    },
    # Jordi Visser doesn't have his own channel — monitor channels that feature him
    {
        "handle": "@KyleChasseCrypto",
        "name": "Kyle Chasse (Jordi Visser tracker)",
        "focus": "Macro, AI + crypto thesis — flag if Jordi Visser appears",
        "url": "https://www.youtube.com/@KyleChasseCrypto",
        "guest_watch": ["Jordi Visser", "Jordi"],
    },
    {
        "handle": "@scottmelker",
        "name": "Wolf of All Streets (Jordi Visser tracker)",
        "focus": "Macro, Bitcoin — flag if Jordi Visser appears",
        "url": "https://www.youtube.com/@scottmelker",
        "guest_watch": ["Jordi Visser", "Jordi"],
    },
    {
        "handle": "@RaoulGMI",
        "name": "Raoul Pal / Real Vision (Jordi Visser tracker)",
        "focus": "Macro, exponential age — flag if Jordi Visser appears",
        "url": "https://www.youtube.com/@RaoulGMI",
        "guest_watch": ["Jordi Visser", "Jordi"],
    },
]

# ── Helpers ──────────────────────────────────────────────────────────────────

def log(msg):
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def today_str():
    return datetime.date.today().isoformat()

def get_latest_video(channel_url, lookback_hours=LOOKBACK_HOURS):
    """Get the most recent non-short video from a channel within lookback window."""
    cutoff = datetime.datetime.now() - datetime.timedelta(hours=lookback_hours)

    # Step 1: Get video IDs from channel (fast)
    try:
        result = subprocess.run(
            ["yt-dlp", "--get-id", "--playlist-items", "1:8", "--no-warnings", channel_url],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode != 0 or not result.stdout.strip():
            return None
        video_ids = [v.strip() for v in result.stdout.strip().split("\n") if v.strip()]
    except subprocess.TimeoutExpired:
        log(f"  Timeout getting IDs from: {channel_url}")
        return None
    except Exception as e:
        log(f"  Error: {e}")
        return None

    # Step 2: Get metadata for each video until we find one that fits
    for vid_id in video_ids:
        try:
            meta = subprocess.run(
                [
                    "yt-dlp",
                    "--print", "%(title)s\t%(upload_date)s\t%(duration)s",
                    "--no-warnings",
                    "--no-playlist",
                    f"https://www.youtube.com/watch?v={vid_id}",
                ],
                capture_output=True, text=True, timeout=20
            )
            if meta.returncode != 0 or not meta.stdout.strip():
                continue

            parts = meta.stdout.strip().split("\t")
            if len(parts) < 3:
                continue
            title, upload_date_str, duration = parts[0], parts[1], parts[2]

            # Parse upload date
            try:
                upload_date = datetime.datetime.strptime(upload_date_str, "%Y%m%d")
            except ValueError:
                continue

            # Skip if too old
            if upload_date < cutoff - datetime.timedelta(days=1):
                continue

            # Skip Shorts (< 3 min)
            try:
                if int(duration) < 180:
                    continue
            except (ValueError, TypeError):
                pass

            return {
                "id": vid_id,
                "title": title,
                "upload_date": upload_date.strftime("%Y-%m-%d"),
                "url": f"https://www.youtube.com/watch?v={vid_id}",
                "duration_sec": int(duration) if duration.isdigit() else 0,
            }

        except subprocess.TimeoutExpired:
            continue
        except Exception:
            continue

    return None

def get_transcript(video_id, max_chars=12000):
    """Download and parse VTT transcript for a video."""
    with tempfile.TemporaryDirectory() as tmpdir:
        out_path = os.path.join(tmpdir, "transcript")
        try:
            result = subprocess.run(
                [
                    "yt-dlp",
                    "--skip-download",
                    "--write-auto-subs",
                    "--sub-lang", "en",
                    "--no-warnings",
                    "-o", out_path,
                    f"https://www.youtube.com/watch?v={video_id}",
                ],
                capture_output=True, text=True, timeout=30
            )
        except subprocess.TimeoutExpired:
            return None

        # Find the VTT file
        vtt_files = [f for f in os.listdir(tmpdir) if f.endswith(".vtt")]
        if not vtt_files:
            return None

        with open(os.path.join(tmpdir, vtt_files[0])) as f:
            content = f.read()

    # Parse VTT: strip timing lines, HTML tags, deduplicate
    lines = content.split("\n")
    text_lines = []
    for line in lines:
        line = line.strip()
        if not line or "-->" in line or line.isdigit() or line.startswith("WEBVTT") \
                or line.startswith("Kind:") or line.startswith("Language:"):
            continue
        line = re.sub(r"<[^>]+>", "", line)
        if line:
            text_lines.append(line)

    deduped = []
    for line in text_lines:
        if not deduped or line != deduped[-1]:
            deduped.append(line)

    transcript = " ".join(deduped)
    return transcript[:max_chars] if len(transcript) > max_chars else transcript

def analyze_transcript(channel_name, channel_focus, title, transcript, client):
    """Send transcript to LLM for structured analysis."""
    system_prompt = textwrap.dedent("""
        You are a financial research analyst specializing in cryptocurrency and macro markets.
        Analyze the YouTube video transcript provided and extract actionable intelligence.

        For the video, identify:
        1. **Bias**: Bullish, Bearish, or Neutral — and confidence (High/Medium/Low)
        2. **Timeframe**: Short-term (days), medium-term (weeks), or long-term (months)
        3. **Key Levels**: Any support/resistance prices mentioned (BTC, ETH, or other assets)
        4. **Specific Calls**: Price predictions, trade setups, or recommendations
        5. **Key Themes**: Main narrative or argument being made (2-4 bullet points)
        6. **Risks**: What could invalidate their thesis

        Be objective. Report what the analyst said, not your own opinion.
        Format as structured markdown. Be concise — max 300 words.
    """).strip()

    user_msg = f"""
Channel: {channel_name}
Channel Focus: {channel_focus}
Video Title: {title}

TRANSCRIPT:
{transcript}
""".strip()

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg},
            ],
            max_tokens=600,
            temperature=0.3,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"Analysis failed: {e}"

def synthesize_reports(analyses, client):
    """Combine individual channel analyses into a unified bias report."""
    if not analyses:
        return "No new videos found — no synthesis available."

    combined = "\n\n---\n\n".join(
        f"## {a['channel']}\n**Video:** {a['title']}\n\n{a['analysis']}"
        for a in analyses
    )

    system_prompt = textwrap.dedent("""
        You are a senior crypto market analyst. You've received reports from multiple YouTube analysts.
        Synthesize them into a unified daily bias assessment.

        Output format (strict markdown):

        ## DAILY BIAS
        🟢 BULLISH / 🟡 NEUTRAL / 🔴 BEARISH
        **Confidence:** High/Medium/Low
        **Timeframe:** Day/Week

        ## REASONING
        [2-3 sentences on the consensus view]

        ## WHERE THEY AGREE
        - [Point 1]
        - [Point 2]

        ## WHERE THEY DIVERGE
        - [Any disagreements]

        ## KEY LEVELS TO WATCH
        - BTC: [Support] / [Resistance]
        - [Other assets if mentioned]

        ## NOTABLE CALLS
        - [Any specific trade setups or predictions worth flagging]

        Be direct and actionable. Max 250 words.
    """).strip()

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": combined},
            ],
            max_tokens=500,
            temperature=0.3,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"Synthesis failed: {e}"

# ── Main ─────────────────────────────────────────────────────────────────────

def run():
    log("=" * 60)
    log(f"YouTube Analyst — {today_str()}")
    log("=" * 60)

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        log("ERROR: OPENAI_API_KEY not set")
        sys.exit(1)
    client = OpenAI(api_key=api_key)

    analyses = []
    jordi_appearances = []
    skipped = []

    for ch in CHANNELS:
        log(f"\nChecking: {ch['name']} ({ch['handle']})")
        video = get_latest_video(ch["url"])

        if not video:
            log(f"  No recent video found (last {LOOKBACK_HOURS}h)")
            skipped.append(ch["name"])
            continue

        log(f"  Found: \"{video['title']}\" ({video['upload_date']})")

        # Check for guest watch (Jordi Visser appearances on other channels)
        guest_watch = ch.get("guest_watch", [])
        if guest_watch:
            is_guest = any(g.lower() in video["title"].lower() for g in guest_watch)
            if not is_guest:
                log(f"  Skipping — no guest match in title ({', '.join(guest_watch)})")
                skipped.append(f"{ch['name']} (no guest match)")
                continue
            else:
                log(f"  🎯 Guest match found: {', '.join(guest_watch)}")
                jordi_appearances.append(video)

        log(f"  Fetching transcript...")
        transcript = get_transcript(video["id"])
        if not transcript:
            log(f"  No transcript available")
            skipped.append(f"{ch['name']} (no transcript)")
            continue

        log(f"  Transcript: {len(transcript)} chars — analyzing...")
        analysis = analyze_transcript(
            ch["name"], ch["focus"], video["title"], transcript, client
        )

        analyses.append({
            "channel": ch["name"],
            "title": video["title"],
            "url": video["url"],
            "upload_date": video["upload_date"],
            "analysis": analysis,
            "is_jordi": bool(guest_watch and any(
                g.lower() in video["title"].lower() for g in guest_watch
            )),
        })
        log(f"  ✓ Analysis complete")

    # Synthesize
    log("\nSynthesizing...")
    primary_analyses = [a for a in analyses if not a.get("is_jordi")]
    synthesis = synthesize_reports(primary_analyses or analyses, client)

    # Build report
    report_date = today_str()
    report_lines = [
        f"# 📺 YouTube Analyst Report — {report_date}",
        "",
        synthesis,
        "",
        "---",
        "",
    ]

    if jordi_appearances:
        report_lines += [
            "## 🎯 JORDI VISSER APPEARANCE",
            "",
        ]
        for v in jordi_appearances:
            jordi_analysis = next((a for a in analyses if a["url"] == v["url"]), None)
            report_lines += [
                f"**[{v['title']}]({v['url']})**",
                f"*Published: {v['upload_date']}*",
                "",
            ]
            if jordi_analysis:
                report_lines.append(jordi_analysis["analysis"])
            report_lines.append("")

    report_lines += ["## CHANNEL BREAKDOWNS", ""]
    for a in analyses:
        if not a.get("is_jordi"):
            report_lines += [
                f"### {a['channel']}",
                f"**[{a['title']}]({a['url']})**  ",
                f"*{a['upload_date']}*",
                "",
                a["analysis"],
                "",
            ]

    if skipped:
        report_lines += [
            "---",
            f"*Skipped (no recent video or no transcript): {', '.join(skipped)}*",
        ]

    report = "\n".join(report_lines)

    # Save
    report_path = os.path.join(REPORTS_DIR, f"{report_date}-youtube.md")
    with open(report_path, "w") as f:
        f.write(report)
    log(f"\nReport saved: {report_path}")

    # Also save JSON for downstream agents
    json_path = os.path.join(BASE_DIR, "youtube_report.json")
    with open(json_path, "w") as f:
        json.dump({
            "date": report_date,
            "analyses": analyses,
            "synthesis": synthesis,
            "jordi_appearances": jordi_appearances,
            "skipped": skipped,
        }, f, indent=2)

    log(f"JSON saved: {json_path}")
    log(f"\nChannels analyzed: {len(analyses)} | Skipped: {len(skipped)}")
    if jordi_appearances:
        log(f"🎯 Jordi Visser appearances: {len(jordi_appearances)}")

    print("\n" + "=" * 60)
    print(report)
    print("=" * 60)
    return report_path

if __name__ == "__main__":
    run()
