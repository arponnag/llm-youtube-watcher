# LLM YouTube Watcher

Automated pipeline that monitors popular LLM-focused YouTube channels, extracts what speakers actually say from captions/transcripts, classifies LLM topics, and publishes a continuously updated public table.

## Problem Fit

This implementation satisfies the brief by delivering:

- **Who is speaking**: explicit `speaker` metadata per channel.
- **What they cover**: topic classification from transcript text (not title-only).
- **How channels relate**: `relation_to_llm_ecosystem` column.
- **Evidence-based rows**: summary and transcript availability/source per video.
- **Live public output**: GitHub Pages static site that auto-refreshes on schedule.

## Architecture

1. **Watch channels** (`channels.yaml`)
2. **Fetch latest videos** from YouTube RSS feed per channel
3. **Ingest transcript evidence**
   - Try YouTube captions via `youtube-transcript-api`
   - Fallback to AI transcription (OpenAI Whisper + `yt-dlp`) when enabled
4. **Derive analytics**
   - Topic tags from transcript/title keyword map
   - Transcript-aware short summary (OpenAI; fallback heuristic)
5. **Publish artifacts**
   - `data/videos.json` (normalized data)
   - `site/index.html` + `site/videos.json` (public view + supporting payload)
6. **Continuously refresh**
   - Hourly GitHub Action updates data and redeploys GitHub Pages

## Data Model (Per Row)

Key fields written to `data/videos.json`:

- `channel_name`, `channel_handle`, `speaker`
- `relation_to_llm_ecosystem`
- `video_id`, `video_title`, `video_url`, `published`
- `topics` (list)
- `transcript_available`, `transcript_source`
- `summary`, `summary_source`
- `transcript_excerpt` (for auditability)

## Quick Start (Local)

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python src/pipeline.py
python src/build_site.py
```

Open `site/index.html` in a browser.

## Detailed Local Setup (Windows PowerShell)

Use this if you want a clean, repeatable setup from scratch:

```powershell
# 1) Move into the project
cd I:\Project

# 2) Create and activate virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 3) Install dependencies
python -m pip install --upgrade pip
pip install -r requirements.txt

# 4) Run pipeline and build site
python src/pipeline.py
python src/build_site.py
```

After running:

- dataset output: `data/videos.json`
- reviewer site: `site/index.html`
- site payload: `site/videos.json`

## End-to-End Run Checklist

Use this checklist whenever you regenerate outputs:

1. Verify channels are configured in `channels.yaml`.
2. Run `python src/pipeline.py`.
3. Confirm `data/videos.json` was updated.
4. Run `python src/build_site.py`.
5. Open `site/index.html` and confirm:
   - generated timestamp is current,
   - rows are present,
   - transcript source and summary source columns are populated.

## Dependency Policy

`requirements.txt` uses minimum versions (`>=`) that are known to work with this project.

Current minimums:

- `feedparser>=6.0.12`
- `PyYAML>=6.0.3`
- `youtube-transcript-api>=1.2.4`
- `openai>=2.34.0`
- `yt-dlp>=2026.3.17`

If you need stricter reproducibility for CI or production, pin exact versions (`==`) in a lock file or a separate frozen requirements file.

## Configuration

- Channel list: `channels.yaml`
- Environment variables:
  - `OPENAI_API_KEY` (optional, recommended)
  - `OPENAI_MODEL` (optional, default `gpt-4.1-mini`)
  - `MAX_VIDEOS_PER_CHANNEL` (optional, default `8`)

Without `OPENAI_API_KEY`, the system still runs using YouTube captions and fallback summaries.

## Deploy Public Site (GitHub Pages)

Workflow: `.github/workflows/update-and-deploy.yml`

- Triggers:
  - hourly schedule
  - manual dispatch
- Steps:
  - install dependencies
  - run watcher pipeline
  - build static site
  - commit refreshed artifacts
  - deploy to GitHub Pages

### Setup Steps

1. Push this project to a **public GitHub repository**.
2. In repository settings:
   - Pages source = **GitHub Actions**
   - Add repo secret `OPENAI_API_KEY` (optional but strongly recommended)
3. Run workflow **Update LLM Watcher and Deploy** once manually.
4. Use the workflow output URL as the live public page.

## GitHub Push Setup (Common Fix)

If `git push` fails with:

`git@github.com: Permission denied (publickey).`

your remote is using SSH and your local machine likely does not have a registered SSH key yet.

Quick fix (use HTTPS remote):

```powershell
git remote set-url origin https://github.com/<your-user>/<your-repo>.git
git push -u origin main
```

This avoids SSH-key setup and works with standard GitHub sign-in/token auth.

## Troubleshooting

### No OpenAI key configured

- behavior: pipeline still runs
- effect: fallback summaries are used instead of model-generated summaries
- action: set `OPENAI_API_KEY` for higher-quality transcript-aware summaries

### Transcript missing for some videos

- behavior: row still appears, but transcript coverage decreases
- likely causes: captions unavailable, region/video restrictions, transient fetch issues
- action: rerun pipeline; optionally enable OpenAI + `yt-dlp` fallback path

### Empty or stale site output

- verify `python src/pipeline.py` succeeded before `python src/build_site.py`
- check that `data/videos.json` has recent `generated_at_utc`
- rebuild site and refresh browser cache

## Big-Scale Refinement Plan

Current build is production-leaning for small/medium channel sets. For large-scale expansion (100s to 1000s channels):

- **Ingestion**
  - move from RSS-only polling to queue-based ingestion
  - incremental checkpoints per channel/video
  - idempotent upserts by `video_id`
- **Storage**
  - migrate JSON to managed DB (`PostgreSQL`/`BigQuery`)
  - keep historical snapshots for trend analysis
- **Transcription**
  - async transcription workers with retry queues
  - cache transcript hashes to avoid repeat costs
- **Classification & Summaries**
  - model-based multi-label topic classifier
  - faithfulness checks against transcript spans
- **Serving**
  - API + frontend pagination/filtering
  - static export remains for low-cost public viewing
- **Reliability**
  - structured logs, metrics, alerts
  - dead-letter queue for failed videos
  - SLA dashboard: freshness, transcript coverage, processing latency

## Demo Walkthrough Script

For reviewer walkthrough:

1. Show `channels.yaml` (source list + relation metadata)
2. Show `src/pipeline.py` (collection, transcript ingestion, summary/topic generation)
3. Show `src/build_site.py` (table build)
4. Open live GitHub Pages URL and highlight:
   - generated timestamp
   - transcript source
   - summary source
5. Trigger workflow manually and confirm update cycle

## Repository Structure

- `src/pipeline.py` - collection + transcript + NLP enrichment
- `src/build_site.py` - HTML/static payload generation
- `channels.yaml` - watched channels and speaker/relation metadata
- `data/videos.json` - normalized output dataset
- `site/index.html` - public table
- `site/videos.json` - raw supporting payload for reviewers
- `REPORT.md` - detailed methodology report
