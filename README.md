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
   - Fallback to `yt-dlp` subtitle extraction when captions are unavailable
4. **Derive analytics**
   - Topic tags inferred by DeepSeek (keyword fallback if inference fails)
   - Channel-to-LLM relation sentence inferred from each channel's recent videos
   - Transcript-aware short summary (DeepSeek by default; fallback heuristic)
   - Quality gate marks rows as `insufficient_transcript` when transcript evidence is too short
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

# 2) Create and activate virtual environment (first run only)
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 3) Add your API key for this terminal session
$env:DEEPSEEK_API_KEY="your_real_key_here"

# 4) One-command local run (installs deps, builds dataset + site)
.\run-local.ps1 -DeepSeekApiKey $env:DEEPSEEK_API_KEY
```

If PowerShell blocks script execution:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

Manual alternative (without wrapper script):

```powershell
python -m pip install -r requirements.txt
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
  - `openai>=2.34.0` (SDK client used for DeepSeek-compatible endpoint calls)
- `yt-dlp>=2026.3.17`

If you need stricter reproducibility for CI or production, pin exact versions (`==`) in a lock file or a separate frozen requirements file.

For this repository, a reproducible lock file is included at `requirements-lock.txt`.

- flexible install (development): `pip install -r requirements.txt`
- reproducible install (CI/release): `pip install -r requirements-lock.txt`

## Basic Regression Tests

Run lightweight unit tests for topic classification and fallback summary behavior:

```powershell
python -m unittest discover -s tests -p "test_*.py"
```

## Configuration

- Channel list: `channels.yaml`
- Environment variables:
  - `DEEPSEEK_API_KEY` (recommended default provider)
  - `DEEPSEEK_MODEL` (optional, default `deepseek-v4-flash`)
  - `DEEPSEEK_BASE_URL` (optional, default `https://api.deepseek.com`)
  - `MAX_VIDEOS_PER_CHANNEL` (optional, default `8`)
  - `MIN_TRANSCRIPT_CHARS` (optional, default `120`; below this, summary is marked insufficient)
  - `MIN_TRANSCRIPT_COVERAGE` (optional, default `0.6`; used with strict mode)
  - `FAIL_ON_LOW_TRANSCRIPT_COVERAGE` (optional, `1` to fail run when coverage is below threshold)

Without `DEEPSEEK_API_KEY`, the system still runs using YouTube captions and fallback summaries.

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
   - Add repo secret `DEEPSEEK_API_KEY` (recommended)
3. Run workflow **Update LLM Watcher and Deploy** once manually.
4. Use the workflow output URL as the live public page.

## GitHub Pages Reliability Notes

If the GitHub Pages site looks stale, blank, or inconsistent, common causes are:

- Pages is serving an older artifact due to deployment lag/caching.
- The workflow succeeded at build steps but deployment step failed or timed out.
- `data/videos.json` was not refreshed (pipeline failed silently on upstream network/API issues).
- API-dependent steps fell back to non-LLM behavior, reducing output quality and making content appear "wrong" rather than "broken".
- Browser cache/CDN cache still serves an earlier `site/videos.json`.

What we already tried in this project:

- Added transcript fallback via `yt-dlp` so runs continue when direct transcript APIs fail.
- Added quality metrics (`transcript_coverage`, source counts) in `data/videos.json` to make failures visible.
- Kept strict mode configurable (`FAIL_ON_LOW_TRANSCRIPT_COVERAGE`) so CI can fail on low coverage when needed.
- Confirmed local end-to-end generation works (`pipeline.py` + `build_site.py`) and produces fresh `site/` artifacts.
- Kept GitHub Actions deployment as the Pages source and documented manual rerun as a recovery path.

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

### No DeepSeek key configured

- behavior: pipeline still runs
- effect: fallback summaries are used instead of model-generated summaries
- action: set `DEEPSEEK_API_KEY` for higher-quality transcript-aware summaries

### Regional note (Hong Kong)

- OpenAI services are not always readily available or consistently accessible from Hong Kong.
- Recommended default for this repo is DeepSeek (`DEEPSEEK_API_KEY`) to keep deployments reliable in that region.

### Transcript missing for some videos

- behavior: row still appears, but transcript coverage decreases
- likely causes: captions unavailable, region/video restrictions, transient fetch issues
- action: rerun pipeline; `yt-dlp` subtitle fallback is applied automatically (English first, then all available subtitles)
- diagnostics: run logs print transcript coverage and source distribution (`youtube_captions_manual`, `youtube_captions_auto`, `yt_dlp_subtitles`, `none`)

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
