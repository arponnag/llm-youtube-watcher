# Problem Statement

Design and host an automated monitoring system for popular LLM-focused YouTube creators that continuously produces a reviewer-friendly table containing:

1. who is speaking,
2. what LLM topics they discuss,
3. how each creator/channel relates to broader LLM themes,
4. evidence grounded in transcript/caption content rather than video title alone.

# Methodology

## 1) Source Selection and Channel Metadata

- Target channels are defined in `channels.yaml`.
- Each channel includes:
  - canonical channel id
  - speaker attribution
  - a seed relation description used only as a last-resort fallback

Speaker attribution is stable from configuration, while relation output is now evidence-first and source-labeled.

## 2) Collection Pipeline

- The pipeline (`src/pipeline.py`) polls YouTube RSS feeds by channel id.
- It collects the latest `N` videos per channel (`MAX_VIDEOS_PER_CHANNEL`).
- Videos are normalized into a single schema and sorted by publish date.

## 3) Transcript / Caption Evidence

The pipeline follows a reliability-first sequence:

1. attempt manual English captions,
2. fallback to auto-generated English captions,
3. fallback to subtitle extraction with `yt-dlp` (English first, then broader subtitle fallback).

Each record stores `transcript_available` and `transcript_source` for auditability.

## 4) Topic Classification

- Rule-based multi-label tagging uses deterministic keyword groups:
  - Agents
  - RAG
  - Fine-tuning
  - Reasoning Models
  - Multimodal
  - Infrastructure
  - Open Source Models
  - Safety & Governance
  - Benchmarks & Eval
  - Product News
- If no topic hits, default is `General LLM Commentary`.

## 5) Transcript-Aware Summarization

- If `DEEPSEEK_API_KEY` is configured, the pipeline summarizes transcript excerpts with a DeepSeek-compatible endpoint prompt focused on speaker claims.
- If not, it falls back to deterministic transcript-based/excerpt summary behavior.

This keeps output operational under constrained environments while improving fidelity when AI is available.

## 6) Channel-Relation Inference and Transparency

The `relation_to_llm_ecosystem` field is generated with explicit source tracking:

1. `inferred_llm`: sentence inferred from each channel's recent videos when model inference succeeds.
2. `inferred_fallback`: deterministic sentence inferred from observed topic distribution + transcript coverage when LLM inference is unavailable.
3. `configured_seed`: seeded text from `channels.yaml`, used only when neither inference path can produce output.

Each row includes:

- `relation_to_llm_ecosystem`
- `configured_relation_to_llm_ecosystem`
- `relation_source`

Run-level metrics include `quality_metrics.relation_source_counts` for auditability.

## 7) Public Output and Refresh

- Dataset output: `data/videos.json`
- Browser output: `site/index.html`
- Supporting payload: `site/videos.json`
- Automation: GitHub Actions workflow (`.github/workflows/update-and-deploy.yml`) runs hourly + manual trigger and deploys to GitHub Pages.

# Evaluation Dataset (if applicable)

- Dataset consists of recent uploads from configured LLM channels in `channels.yaml`.
- Each run creates a timestamped snapshot with metadata:
  - `generated_at_utc`
  - `row_count`
  - enriched `rows`

# Evaluation Methods (if applicable)

1. **Transcript coverage**
   - metric: `transcript_available = true` ratio
   - objective: maximize rows based on spoken evidence
2. **Topic precision (human spot-check)**
   - sample videos per topic and compare tags with transcript excerpts
3. **Summary faithfulness**
   - confirm summary claims are present in transcript excerpt
4. **Freshness / update latency**
   - compare latest channel upload times vs last generated timestamp
5. **Pipeline reliability**
   - monitor rows with `error` fields and failed transcript acquisition

# Experimental Results

Local pipeline execution produced:

- successful feed retrieval across configured channels,
- normalized output dataset generation,
- static table build suitable for browser review,
- transcript-source annotations per row,
- relation-source annotations per row (`inferred_llm`, `inferred_fallback`, `configured_seed`),
- scheduled deployment workflow ready for public hosting.

Artifacts generated during local run:

- `data/videos.json`
- `site/index.html`
- `site/videos.json`

# Big-Scale Plan

To evolve from assessment prototype to large-scale production:

## Data & Storage

- Replace JSON artifact storage with `PostgreSQL` or `BigQuery`.
- Add historical partitioning for longitudinal trend analytics.

## Ingestion Throughput

- Use a queue system (e.g., Pub/Sub, SQS, or RabbitMQ).
- Separate feed polling from transcript/transcription workers.

## Cost and Performance Controls

- Deduplicate by `video_id` and transcript checksum.
- Trigger transcription only when captions are missing.
- Batch summary generation and cache outputs.

## Quality and Governance

- Add confidence scores for topic assignment.
- Add summary citation spans (timestamp-level, if available).
- Add moderation guardrails before publication.

## Observability

- Structured logs + metrics + alerting:
  - transcript coverage
  - processing latency
  - failed job count
  - deployment freshness

# Risks and Mitigations

- **Caption unavailability**: mitigated by `yt-dlp` subtitle fallback.
- **API unavailability/rate limits**: mitigated by deterministic fallbacks for summaries, topics, and channel relation inference.
- **Platform/API changes**: mitigated by modular adapters and integration tests.

# Reproducibility Notes

Run locally:

1. create/activate virtual env
2. set `DEEPSEEK_API_KEY` in terminal environment
3. run `.\run-local.ps1 -DeepSeekApiKey $env:DEEPSEEK_API_KEY` (or run pipeline + build manually)
4. open `site/index.html`

For public continuous output:

1. push repository to GitHub,
2. enable Pages (GitHub Actions source),
3. set `DEEPSEEK_API_KEY` in repo secrets,
4. run workflow manually once, then rely on schedule.
