"""
generate_brief.py
-----------------
Calls the Anthropic API with the built-in web_search tool.
Claude searches the agreed 26 source list, synthesises incidents, and returns
structured JSON. The script writes the result to docs/data/brief.json which
is served by GitHub Pages.

Run locally:  ANTHROPIC_API_KEY=sk-... python generate_brief.py
Run via CI:   triggered automatically by .github/workflows/refresh_brief.yml
"""

import anthropic
import json
import os
import re
import sys
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

AGREED_SOURCES = [
    # Industry / Threat Intelligence
    "crowdstrike.com/blog",
    "cloud.google.com/blog/topics/threat-intelligence",
    "unit42.paloaltonetworks.com",
    "microsoft.com/en-us/security/blog",
    "blog.talosintelligence.com",
    "recordedfuture.com/research",
    "darkreading.com",
    "krebsonsecurity.com",
    # Government
    "cisa.gov/news-events/cybersecurity-advisories",
    "ic3.gov",
    "justice.gov/news",
    "home.treasury.gov/news",
    "fincen.gov/resources/advisories",
    "nsa.gov/Press-Room/Cybersecurity-Advisories-Guidance",
    "ncsc.gov.uk/news",
    "cyber.gov.au/about-us/news",
    "enisa.europa.eu/news",
    # News
    "reuters.com/technology/cybersecurity",
    "bloomberg.com/technology",
    "therecord.media",
    # Regulatory
    "efts.sec.gov",        # EDGAR 8-K Item 1.05
    "sec.gov/litigation",
    "dfs.ny.gov/enforcement",
    # Trusted voices
    "risky.biz",
    "isc.sans.edu",
    "cyberscoop.com",
]

SYSTEM_PROMPT = """You are a senior cyber threat intelligence analyst producing a daily briefing
for corporate executives. Your audience understands business risk but does not use vendor
threat-actor codenames.

SEARCH INSTRUCTIONS:
- Search exclusively across the following agreed source domains:
  {sources}
- Focus on cyber attacks, data breaches, ransomware incidents, and nation-state
  intrusions reported in the last 48 hours first, then up to 14 days if fewer
  than 6 significant incidents are found in the past 48 hours.
- Run multiple targeted searches across different source categories.
- Deduplicate: if multiple sources cover the same incident, merge into one entry.

ATTACKER NAMING RULES — CRITICAL:
- NEVER use proprietary vendor codenames (e.g. Fancy Bear, Lazarus Group,
  Sandworm, MuddyWater, Volt Typhoon, Salt Typhoon, Handala Hack, Laundry Bear,
  APT28, APT41, etc.).
- ALWAYS use plain executive language:
  - "Russia — GRU military intelligence"
  - "Russia — FSB intelligence service"
  - "Russia — state-linked espionage group"
  - "Iran — Ministry of Intelligence (MOIS)"
  - "Iran — state-directed hacktivist proxies"
  - "China — state-suspected espionage group"
  - "North Korea — state-sponsored, financially motivated"
  - "Criminal gang — ransomware"
  - "Criminal gang — data extortion"
  - "Unknown"

OUTPUT FORMAT:
Return ONLY a JSON object inside <BRIEF> tags — no other text before or after:

<BRIEF>
{{
  "generated_at": "ISO-8601 timestamp",
  "period_searched": "human-readable description e.g. March 15-17, 2026",
  "incident_count": 0,
  "incidents": [
    {{
      "id": "1",
      "date": "YYYY-MM-DD or descriptive e.g. Early Mar 2026",
      "date_sort": "YYYY-MM-DD for sorting (use best estimate)",
      "victim": "Organization or sector name",
      "industry": "Industry sector",
      "attacker": "Plain-language attacker description per rules above",
      "attacker_origin": "russia|iran|china|north_korea|criminal|unknown",
      "motivation": "Financial|Espionage|Disruption|IP theft|Political|Unclear",
      "vector": "How the attack was carried out — one concise sentence",
      "impact": "What happened and known consequences — one to two concise sentences",
      "ongoing": "Y|N",
      "severity": "critical|high|medium|low",
      "sources": ["source name or domain"]
    }}
  ]
}}
</BRIEF>
""".format(sources="\n  ".join(f"- {s}" for s in AGREED_SOURCES))

USER_PROMPT = """Today is {today}.

Search the agreed source list for publicly reported cyber attacks, data breaches,
ransomware incidents, and nation-state intrusions. Prioritise the most recent
48 hours, then expand to 14 days if needed to reach at least 6 incidents.

Run targeted searches such as:
- Recent cyber attacks and breaches
- Ransomware incidents this week
- Nation-state cyber espionage news
- CISA advisories recent
- DOJ cybercrime press releases
- therecord.media cyber news
- Krebs on Security latest

Return the structured JSON inside <BRIEF> tags.
""".format(today=datetime.now(timezone.utc).strftime("%A, %B %d, %Y"))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def generate():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY environment variable not set.", file=sys.stderr)
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    print("Calling Claude API with web search...")
    messages = [{"role": "user", "content": USER_PROMPT}]
    final_text = ""

    # Usage tracking — accumulate token counts across all API calls
    usage_log = []  # per-call records
    total_input_tokens = 0
    total_output_tokens = 0

    # Web search is a server-side tool — the API executes searches internally.
    # When the server-side loop hits its iteration limit, stop_reason is
    # "pause_turn". We re-send the conversation to let it continue.
    # No tool_result messages needed — the API handles everything.
    max_continuations = 5
    for attempt in range(max_continuations):
        print(f"  API call {attempt + 1}/{max_continuations}...")
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=messages,
        )

        # Track token usage for this call
        call_usage = {
            "call": attempt + 1,
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "stop_reason": response.stop_reason,
        }
        # Capture any additional usage fields the API provides
        # (e.g. cache_creation_input_tokens, cache_read_input_tokens)
        for attr in ("cache_creation_input_tokens", "cache_read_input_tokens"):
            val = getattr(response.usage, attr, None)
            if val:
                call_usage[attr] = val
        usage_log.append(call_usage)
        total_input_tokens += response.usage.input_tokens
        total_output_tokens += response.usage.output_tokens

        print(f"  stop_reason: {response.stop_reason}")
        print(f"  tokens: {response.usage.input_tokens:,} in / {response.usage.output_tokens:,} out")

        # Collect all text blocks from this response
        text_parts = [b.text for b in response.content if hasattr(b, "text") and b.text]
        if text_parts:
            print(f"  Got {len(text_parts)} text block(s), {sum(len(t) for t in text_parts)} chars")

        if response.stop_reason == "end_turn":
            final_text = " ".join(text_parts)
            break

        if response.stop_reason == "pause_turn":
            # Server-side tool loop hit its iteration limit.
            # Re-send user message + assistant response to continue.
            messages = [
                {"role": "user", "content": USER_PROMPT},
                {"role": "assistant", "content": response.content},
            ]
            print("  Continuing (pause_turn)...")
            continue

        # Any other stop reason — take whatever text is available
        final_text = " ".join(text_parts)
        print(f"  Unexpected stop_reason: {response.stop_reason}")
        break

    # Print usage summary
    print(f"\n--- API Usage Summary ---")
    print(f"  API calls made: {len(usage_log)}")
    print(f"  Total input tokens:  {total_input_tokens:,}")
    print(f"  Total output tokens: {total_output_tokens:,}")
    print(f"  Total tokens:        {total_input_tokens + total_output_tokens:,}")
    print(f"-------------------------\n")

    if not final_text:
        print("ERROR: No text content returned from API.", file=sys.stderr)
        print(f"Last stop_reason: {response.stop_reason}", file=sys.stderr)
        # Dump content block types for debugging
        for i, b in enumerate(response.content):
            print(f"  Block {i}: type={b.type}", file=sys.stderr)
        sys.exit(1)

    # Extract JSON from <BRIEF> tags
    match = re.search(r"<BRIEF>([\s\S]*?)</BRIEF>", final_text)
    if not match:
        # Try bare JSON fallback
        match = re.search(r'\{[\s\S]*"incidents"[\s\S]*\}', final_text)
        if not match:
            print("ERROR: Could not extract structured JSON from response.", file=sys.stderr)
            print("Raw response snippet:", final_text[:500], file=sys.stderr)
            sys.exit(1)
        data = json.loads(match.group(0))
    else:
        data = json.loads(match.group(1).strip())

    # Ensure generated_at is set
    data["generated_at"] = datetime.now(timezone.utc).isoformat()

    # Sort incidents by date_sort descending (most recent first)
    data["incidents"].sort(key=lambda x: x.get("date_sort", "0000-00-00"), reverse=True)
    data["incident_count"] = len(data["incidents"])

    # Write output
    output_path = os.path.join(os.path.dirname(__file__), "docs", "data", "brief.json")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"SUCCESS: {len(data['incidents'])} incidents written to {output_path}")
    print(f"Period: {data.get('period_searched', 'unknown')}")
    for inc in data["incidents"]:
        print(f"  [{inc['severity'].upper():8}] {inc['date']:12} {inc['victim']}")

    # Append usage record to JSONL log for historical tracking
    usage_record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model": "claude-sonnet-4-6",
        "api_calls": len(usage_log),
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "total_tokens": total_input_tokens + total_output_tokens,
        "incident_count": len(data["incidents"]),
        "calls": usage_log,
    }
    usage_log_path = os.path.join(os.path.dirname(__file__), "docs", "data", "usage_log.jsonl")
    with open(usage_log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(usage_record) + "\n")
    print(f"Usage logged to {usage_log_path}")


if __name__ == "__main__":
    generate()
