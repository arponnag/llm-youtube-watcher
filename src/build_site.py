from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = ROOT / "data" / "videos.json"
SITE_DIR = ROOT / "site"
INDEX_FILE = SITE_DIR / "index.html"


HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>LLM YouTube Watcher</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 24px; color: #1f2937; }
    h1 { margin-bottom: 4px; }
    .meta { color: #4b5563; margin-bottom: 18px; }
    table { border-collapse: collapse; width: 100%; font-size: 14px; }
    th, td { border: 1px solid #d1d5db; padding: 8px; vertical-align: top; text-align: left; }
    th { background: #f3f4f6; }
    tr:nth-child(even) { background: #fafafa; }
    .topics { font-weight: 600; color: #111827; }
    .tiny { color: #6b7280; font-size: 12px; }
    a { color: #2563eb; text-decoration: none; }
    a:hover { text-decoration: underline; }
  </style>
</head>
<body>
  <h1>LLM Creator Watch Table</h1>
  <p class="meta">Auto-generated from YouTube channel feeds and captions/transcripts.</p>
  <p class="meta">Generated at: __GENERATED_AT__ | Rows: __ROW_COUNT__</p>
  <table>
    <thead>
      <tr>
        <th>Video</th>
        <th>Speaker</th>
        <th>Topics</th>
        <th>How Channel Relates to LLM Themes</th>
        <th>What They Actually Say (Transcript-Aware)</th>
      </tr>
    </thead>
    <tbody>
      __ROWS__
    </tbody>
  </table>
</body>
</html>
"""


def esc(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def build_row(row: dict) -> str:
    topics = ", ".join(row.get("topics", []))
    transcript_source = row.get("transcript_source", "none")
    transcript_note = transcript_source if row.get("transcript_available") else "unavailable"
    return f"""<tr>
  <td>
    <a href="{esc(row.get("video_url", "#"))}" target="_blank" rel="noopener">{esc(row.get("video_title", "Untitled"))}</a>
    <div class="tiny">{esc(row.get("channel_name", ""))} | {esc(row.get("published", ""))}</div>
  </td>
  <td>{esc(row.get("speaker", ""))}</td>
  <td><span class="topics">{esc(topics)}</span></td>
  <td>{esc(row.get("relation_to_llm_ecosystem", ""))}</td>
  <td>
    {esc(row.get("summary", ""))}
    <div class="tiny">Summary source: {esc(row.get("summary_source", "none"))} | Transcript: {esc(str(transcript_note))}</div>
  </td>
</tr>"""


def run() -> None:
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    if not DATA_FILE.exists():
        raise FileNotFoundError(f"Missing data file: {DATA_FILE}")
    payload = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    rows_html = "\n".join(build_row(r) for r in payload.get("rows", []))
    html = (
        HTML_TEMPLATE.replace("__GENERATED_AT__", esc(payload.get("generated_at_utc", "")))
        .replace("__ROW_COUNT__", str(payload.get("row_count", 0)))
        .replace("__ROWS__", rows_html)
    )
    INDEX_FILE.write_text(html, encoding="utf-8")
    (SITE_DIR / "videos.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"Wrote {INDEX_FILE}")


if __name__ == "__main__":
    run()
