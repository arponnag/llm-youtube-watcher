import unittest
from unittest.mock import patch

from src.pipeline import Channel, normalize_entry, topics_from_text


class TestPipelineLogic(unittest.TestCase):
    def test_topics_from_text_matches_multiple_keywords(self) -> None:
        topics = topics_from_text(
            text="We benchmarked inference latency and improved RAG retrieval quality.",
            title="Agent workflow update",
        )
        self.assertIn("Agents", topics)
        self.assertIn("RAG", topics)
        self.assertIn("Infrastructure", topics)

    def test_topics_from_text_defaults_to_general(self) -> None:
        topics = topics_from_text(
            text="Today we discussed creator interviews and community updates.",
            title="Channel update",
        )
        self.assertEqual(["General LLM Commentary"], topics)

    @patch("src.pipeline.summarize_with_llm", return_value=("", "none"))
    @patch("src.pipeline.fetch_transcript_with_ytdlp", return_value=("", "none"))
    @patch("src.pipeline.fetch_transcript_text", return_value=("RAG systems help retrieval quality.", "youtube_captions_manual"))
    def test_normalize_entry_uses_fallback_summary_source(
        self, _fetch_mock, _transcribe_mock, _summarize_mock
    ) -> None:
        channel = Channel(
            name="Test Channel",
            handle="@test",
            channel_id="abc123",
            speaker="Test Speaker",
            relation_to_llm_ecosystem="Covers practical LLM engineering workflows.",
        )
        item = {
            "link": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "title": "Testing fallback summaries",
            "published": "2026-05-06T00:00:00+00:00",
        }

        row = normalize_entry(channel, item)
        self.assertEqual("fallback", row["summary_source"])
        self.assertTrue(row["summary"])


if __name__ == "__main__":
    unittest.main()
