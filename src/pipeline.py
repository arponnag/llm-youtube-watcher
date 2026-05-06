from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from collections import Counter
from typing import Dict, List
from urllib.parse import parse_qs, urlparse

import feedparser
import yaml
from openai import OpenAI
from youtube_transcript_api import YouTubeTranscriptApi


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
CHANNELS_FILE = ROOT / "channels.yaml"
OUTPUT_FILE = DATA_DIR / "videos.json"
MAX_VIDEOS_PER_CHANNEL = int(os.getenv("MAX_VIDEOS_PER_CHANNEL", "8"))
MIN_TRANSCRIPT_CHARS = int(os.getenv("MIN_TRANSCRIPT_CHARS", "120"))
MIN_TRANSCRIPT_COVERAGE = float(os.getenv("MIN_TRANSCRIPT_COVERAGE", "0.6"))
FAIL_ON_LOW_TRANSCRIPT_COVERAGE = os.getenv("FAIL_ON_LOW_TRANSCRIPT_COVERAGE", "0") == "1"

TOPIC_KEYWORDS: Dict[str, List[str]] = {
    "Agents": ["agent", "autonomous", "workflow", "tool use", "browser use"],
    "RAG": ["rag", "retrieval", "vector database", "embedding"],
    "Fine-tuning": ["fine-tuning", "finetuning", "instruction tuning", "lora"],
    "Reasoning Models": ["reasoning", "chain-of-thought", "o1", "thinking model"],
    "Multimodal": ["vision", "audio", "image", "video", "multimodal"],
    "Infrastructure": ["inference", "latency", "serving", "gpu", "quantization"],
    "Open Source Models": ["llama", "mistral", "qwen", "open-source", "open weights"],
    "Safety & Governance": ["safety", "alignment", "policy", "regulation", "risk"],
    "Benchmarks & Eval": ["benchmark", "eval", "evaluation", "leaderboard"],
    "Product News": ["launch", "release", "announcement", "api", "feature"],
}


@dataclass
class Channel:
    name: str
    handle: str
    channel_id: str
    speaker: str
    relation_to_llm_ecosystem: str


def load_channels() -> List[Channel]:
    with CHANNELS_FILE.open("r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    return [Channel(**c) for c in config["channels"]]


def extract_video_id(link: str) -> str:
    parsed = urlparse(link)
    if parsed.hostname in {"youtu.be"}:
        return parsed.path.strip("/")
    query = parse_qs(parsed.query)
    if "v" in query and query["v"]:
        return query["v"][0]
    raise ValueError(f"Could not parse video id from {link}")


def fetch_recent_videos(channel_id: str) -> List[dict]:
    feed_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    feed = feedparser.parse(feed_url)
    return feed.entries[:MAX_VIDEOS_PER_CHANNEL]


def fetch_transcript_text(video_id: str) -> tuple[str, str]:
    """
    Returns (transcript_text, transcript_source).
    """
    try:
        transcripts = YouTubeTranscriptApi.list_transcripts(video_id)
        preferred = None
        try:
            preferred = transcripts.find_manually_created_transcript(["en"])
        except Exception:
            try:
                preferred = transcripts.find_generated_transcript(["en"])
            except Exception:
                preferred = next(iter(transcripts), None)
        if preferred:
            chunks = preferred.fetch()
            text = " ".join(chunk.get("text", "").strip() for chunk in chunks).strip()
            if text:
                source = "youtube_captions_manual" if not preferred.is_generated else "youtube_captions_auto"
                return text, source
    except Exception:
        pass
    return "", "none"


def fetch_transcript_with_ytdlp(video_url: str, video_id: str) -> tuple[str, str]:
    """
    Fetches subtitles via yt-dlp when youtube-transcript-api is unavailable.
    Returns (transcript_text, transcript_source).
    """
    subtitles_dir = DATA_DIR / "tmp_subtitles"
    subtitles_dir.mkdir(parents=True, exist_ok=True)
    subtitle_template = subtitles_dir / f"{video_id}.%(ext)s"
    cmd_primary = [
        "yt-dlp",
        "--skip-download",
        "--write-auto-subs",
        "--write-subs",
        "--sub-langs",
        "en.*,en",
        "--sub-format",
        "vtt",
        "--output",
        str(subtitle_template),
        video_url,
    ]
    cmd_fallback = [
        "yt-dlp",
        "--skip-download",
        "--write-auto-subs",
        "--write-subs",
        "--sub-langs",
        "all,-live_chat",
        "--sub-format",
        "vtt",
        "--output",
        str(subtitle_template),
        video_url,
    ]
    try:
        proc_primary = subprocess.run(cmd_primary, capture_output=True, text=True, check=False)
        candidates = sorted(subtitles_dir.glob(f"{video_id}*.vtt"))
        if not candidates:
            proc_fallback = subprocess.run(cmd_fallback, capture_output=True, text=True, check=False)
            candidates = sorted(subtitles_dir.glob(f"{video_id}*.vtt"))
            if proc_primary.returncode != 0 and proc_fallback.returncode != 0:
                return "", "none"
        if not candidates:
            return "", "none"
        raw = candidates[0].read_text(encoding="utf-8", errors="ignore")
        lines: List[str] = []
        for line in raw.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith(("WEBVTT", "Kind:", "Language:", "NOTE")):
                continue
            if "-->" in stripped:
                continue
            if stripped.isdigit():
                continue
            cleaned = re.sub(r"<[^>]+>", "", stripped)
            cleaned = re.sub(r"\[[^\]]+\]", "", cleaned).strip()
            if cleaned:
                lines.append(cleaned)
        text = re.sub(r"\s+", " ", " ".join(lines)).strip()
        if text:
            return text, "yt_dlp_subtitles"
    except Exception:
        return "", "none"
    finally:
        for file in subtitles_dir.glob(f"{video_id}*"):
            try:
                file.unlink()
            except Exception:
                pass
    return "", "none"


def summarize_with_llm(transcript_text: str, title: str) -> tuple[str, str]:
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key or len(transcript_text) < 100:
        return "", "none"
    client = OpenAI(api_key=api_key, base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"))
    clip = transcript_text[:10000]
    prompt = (
        "You summarize creator commentary on LLM topics.\n"
        f"Video title: {title}\n"
        "Transcript excerpt follows.\n"
        f"{clip}\n\n"
        "Return one concise sentence (max 35 words) focused on what the speaker says."
    )
    try:
        resp = client.responses.create(
            model=os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"),
            input=prompt,
            temperature=0.2,
            max_output_tokens=100,
        )
        text = (resp.output_text or "").strip()
        text = re.sub(r"\s+", " ", text)
        return text, "deepseek"
    except Exception:
        return "", "none"


def topics_from_text(text: str, title: str) -> List[str]:
    haystack = f"{title}\n{text}".lower()
    matches = []
    for topic, keywords in TOPIC_KEYWORDS.items():
        if any(keyword in haystack for keyword in keywords):
            matches.append(topic)
    if not matches:
        matches.append("General LLM Commentary")
    return matches[:4]


def infer_topics_with_llm(transcript_text: str, title: str) -> List[str]:
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        return []
    client = OpenAI(api_key=api_key, base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"))
    clip = transcript_text[:3500]
    allowed = list(TOPIC_KEYWORDS.keys())
    prompt = (
        "Classify this video into up to 4 topics from the allowed list.\n"
        f"Allowed topics: {', '.join(allowed)}\n"
        f"Title: {title}\n"
        f"Transcript excerpt: {clip}\n\n"
        'Return strict JSON only in this shape: {"topics":["Topic A","Topic B"]}'
    )
    try:
        resp = client.responses.create(
            model=os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"),
            input=prompt,
            temperature=0.2,
            max_output_tokens=100,
        )
        parsed = json.loads((resp.output_text or "").strip() or "{}")
        raw_topics = parsed.get("topics", [])
        if not isinstance(raw_topics, list):
            return []
        filtered = [t for t in raw_topics if isinstance(t, str) and t in TOPIC_KEYWORDS]
        deduped = []
        for topic in filtered:
            if topic not in deduped:
                deduped.append(topic)
        return deduped[:4]
    except Exception:
        return []


def fallback_summary(transcript_text: str, title: str, topics: List[str]) -> str:
    if transcript_text:
        sentence = transcript_text[:260].replace("\n", " ").strip()
        return f"{sentence}..."
    return f"Discusses {', '.join(topics[:2])} in the context of '{title}'."


def infer_channel_relations(rows: List[dict]) -> Dict[str, str]:
    grouped: Dict[str, List[dict]] = {}
    for row in rows:
        grouped.setdefault(row.get("channel_name", ""), []).append(row)
    inferred: Dict[str, str] = {}
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        return inferred
    client = OpenAI(api_key=api_key, base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"))
    for channel_name, channel_rows in grouped.items():
        sample = channel_rows[:6]
        sample_lines = []
        for row in sample:
            topics = ", ".join(row.get("topics", [])[:3])
            sample_lines.append(f"- {row.get('video_title', '')} | topics: {topics}")
        prompt = (
            "Write one concise sentence (max 26 words) describing how this YouTube channel relates to LLM themes.\n"
            f"Channel: {channel_name}\n"
            "Recent videos:\n"
            f"{chr(10).join(sample_lines)}\n\n"
            "Focus on practical relation to LLM ecosystem themes."
        )
        try:
            resp = client.responses.create(
                model=os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"),
                input=prompt,
                temperature=0.2,
                max_output_tokens=70,
            )
            text = re.sub(r"\s+", " ", (resp.output_text or "").strip())
            if text:
                inferred[channel_name] = text
        except Exception:
            continue
    return inferred


def infer_channel_relations_from_evidence(rows: List[dict]) -> Dict[str, str]:
    """
    Evidence-first fallback: derive channel relation text from observed topics/transcript availability.
    """
    grouped: Dict[str, List[dict]] = {}
    for row in rows:
        if "error" in row:
            continue
        grouped.setdefault(row.get("channel_name", ""), []).append(row)
    inferred: Dict[str, str] = {}
    for channel_name, channel_rows in grouped.items():
        topic_counter: Counter[str] = Counter()
        transcript_available = 0
        for row in channel_rows:
            topic_counter.update([str(t) for t in row.get("topics", []) if isinstance(t, str)])
            if row.get("transcript_available"):
                transcript_available += 1
        top_topics = [topic for topic, _ in topic_counter.most_common(3)]
        if not top_topics:
            top_topics = ["General LLM Commentary"]
        coverage = transcript_available / len(channel_rows) if channel_rows else 0.0
        relation = (
            f"Recent coverage centers on {', '.join(top_topics)} "
            f"based on transcript evidence from {transcript_available}/{len(channel_rows)} videos."
        )
        inferred[channel_name] = relation
    return inferred


def normalize_entry(channel: Channel, item: dict) -> dict:
    video_url = item.get("link", "")
    video_id = extract_video_id(video_url)
    transcript_text, transcript_source = fetch_transcript_text(video_id)
    if not transcript_text:
        transcript_text, transcript_source = fetch_transcript_with_ytdlp(video_url, video_id)
    topics = infer_topics_with_llm(transcript_text, item.get("title", "")) or topics_from_text(
        transcript_text, item.get("title", "")
    )
    if len(transcript_text) < MIN_TRANSCRIPT_CHARS:
        summary = "Insufficient transcript evidence for reliable summary."
        effective_summary_source = "insufficient_transcript"
    else:
        ai_summary, summary_source = summarize_with_llm(transcript_text, item.get("title", ""))
        summary = ai_summary or fallback_summary(transcript_text, item.get("title", ""), topics)
        effective_summary_source = summary_source if ai_summary else "fallback"
    published = item.get("published", "")

    return {
        "channel_name": channel.name,
        "channel_handle": channel.handle,
        "speaker": channel.speaker,
        "relation_to_llm_ecosystem": channel.relation_to_llm_ecosystem,
        "configured_relation_to_llm_ecosystem": channel.relation_to_llm_ecosystem,
        "relation_source": "configured_seed",
        "video_id": video_id,
        "video_title": item.get("title", ""),
        "video_url": video_url,
        "published": published,
        "topics": topics,
        "transcript_available": bool(transcript_text),
        "transcript_source": transcript_source,
        "summary": summary,
        "summary_source": effective_summary_source,
        "transcript_excerpt": transcript_text[:800],
    }


def run() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    channels = load_channels()
    rows: List[dict] = []
    for channel in channels:
        items = fetch_recent_videos(channel.channel_id)
        for item in items:
            try:
                rows.append(normalize_entry(channel, item))
            except Exception as exc:
                rows.append(
                    {
                        "channel_name": channel.name,
                        "speaker": channel.speaker,
                        "video_title": item.get("title", ""),
                        "video_url": item.get("link", ""),
                        "error": str(exc),
                    }
                )
    inferred_relations_llm = infer_channel_relations(rows)
    inferred_relations_fallback = infer_channel_relations_from_evidence(rows)
    for row in rows:
        channel_name = row.get("channel_name", "")
        llm_relation = inferred_relations_llm.get(channel_name, "")
        fallback_relation = inferred_relations_fallback.get(channel_name, "")
        if llm_relation:
            row["relation_to_llm_ecosystem"] = llm_relation
            row["relation_source"] = "inferred_llm"
        elif fallback_relation:
            row["relation_to_llm_ecosystem"] = fallback_relation
            row["relation_source"] = "inferred_fallback"
        else:
            row["relation_to_llm_ecosystem"] = row.get("configured_relation_to_llm_ecosystem", "")
            row["relation_source"] = "configured_seed"
    rows.sort(key=lambda x: x.get("published", ""), reverse=True)
    valid_rows = [r for r in rows if "error" not in r]
    transcript_covered = sum(1 for r in valid_rows if r.get("transcript_available"))
    transcript_coverage = (transcript_covered / len(valid_rows)) if valid_rows else 0.0
    transcript_source_counts: Dict[str, int] = {}
    summary_source_counts: Dict[str, int] = {}
    relation_source_counts: Dict[str, int] = {}
    for row in valid_rows:
        t_source = str(row.get("transcript_source", "none"))
        s_source = str(row.get("summary_source", "none"))
        r_source = str(row.get("relation_source", "none"))
        transcript_source_counts[t_source] = transcript_source_counts.get(t_source, 0) + 1
        summary_source_counts[s_source] = summary_source_counts.get(s_source, 0) + 1
        relation_source_counts[r_source] = relation_source_counts.get(r_source, 0) + 1
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "row_count": len(rows),
        "quality_metrics": {
            "transcript_coverage": round(transcript_coverage, 4),
            "transcript_source_counts": transcript_source_counts,
            "summary_source_counts": summary_source_counts,
            "relation_source_counts": relation_source_counts,
            "min_transcript_chars": MIN_TRANSCRIPT_CHARS,
            "min_transcript_coverage_target": MIN_TRANSCRIPT_COVERAGE,
        },
        "rows": rows,
    }
    OUTPUT_FILE.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(rows)} rows to {OUTPUT_FILE}")
    print(
        "Transcript coverage:",
        f"{transcript_covered}/{len(valid_rows)} ({transcript_coverage:.1%})",
        "| sources:",
        transcript_source_counts,
        "| summaries:",
        summary_source_counts,
        "| relations:",
        relation_source_counts,
    )
    if FAIL_ON_LOW_TRANSCRIPT_COVERAGE and transcript_coverage < MIN_TRANSCRIPT_COVERAGE:
        raise RuntimeError(
            f"Transcript coverage {transcript_coverage:.1%} below threshold {MIN_TRANSCRIPT_COVERAGE:.1%}"
        )


if __name__ == "__main__":
    run()
