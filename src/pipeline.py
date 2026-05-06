from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
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


def transcribe_with_openai_audio(video_url: str, video_id: str) -> tuple[str, str]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return "", "none"
    with tempfile.TemporaryDirectory() as tmp:
        audio_path = Path(tmp) / f"{video_id}.m4a"
        cmd = [
            "yt-dlp",
            "-f",
            "bestaudio[ext=m4a]/bestaudio",
            "--no-playlist",
            "--extract-audio",
            "--audio-format",
            "m4a",
            "--output",
            str(audio_path),
            video_url,
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if proc.returncode != 0 or not audio_path.exists():
                return "", "none"
            client = OpenAI(api_key=api_key)
            with audio_path.open("rb") as f:
                transcript = client.audio.transcriptions.create(model="whisper-1", file=f)
            text = (getattr(transcript, "text", "") or "").strip()
            if text:
                return text, "openai_whisper"
        except Exception:
            return "", "none"
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


def summarize_with_openai(transcript_text: str, title: str) -> tuple[str, str]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or len(transcript_text) < 100:
        return "", "none"
    client = OpenAI(api_key=api_key)
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
            model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
            input=prompt,
            temperature=0.2,
            max_output_tokens=100,
        )
        text = (resp.output_text or "").strip()
        text = re.sub(r"\s+", " ", text)
        return text, "openai"
    except Exception:
        return "", "none"


def fallback_summary(transcript_text: str, title: str, topics: List[str]) -> str:
    if transcript_text:
        sentence = transcript_text[:260].replace("\n", " ").strip()
        return f"{sentence}..."
    return f"Discusses {', '.join(topics[:2])} in the context of '{title}'."


def normalize_entry(channel: Channel, item: dict) -> dict:
    video_url = item.get("link", "")
    video_id = extract_video_id(video_url)
    transcript_text, transcript_source = fetch_transcript_text(video_id)
    if not transcript_text:
        transcript_text, transcript_source = transcribe_with_openai_audio(video_url, video_id)
    topics = topics_from_text(transcript_text, item.get("title", ""))
    ai_summary, summary_source = summarize_with_openai(transcript_text, item.get("title", ""))
    summary = ai_summary or fallback_summary(transcript_text, item.get("title", ""), topics)
    published = item.get("published", "")

    return {
        "channel_name": channel.name,
        "channel_handle": channel.handle,
        "speaker": channel.speaker,
        "relation_to_llm_ecosystem": channel.relation_to_llm_ecosystem,
        "video_id": video_id,
        "video_title": item.get("title", ""),
        "video_url": video_url,
        "published": published,
        "topics": topics,
        "transcript_available": bool(transcript_text),
        "transcript_source": transcript_source,
        "summary": summary,
        "summary_source": summary_source,
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
    rows.sort(key=lambda x: x.get("published", ""), reverse=True)
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "row_count": len(rows),
        "rows": rows,
    }
    OUTPUT_FILE.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(rows)} rows to {OUTPUT_FILE}")


if __name__ == "__main__":
    run()
