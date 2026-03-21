Today is {{DATE}}.

Read the fetch summary and all source files in `data/raw/{{DATE}}/` to understand what content was retrieved.

Then analyze all articles for reportable cyber incidents. For each incident:

1. **Deduplicate** — if multiple sources cover the same incident, merge into one entry
2. **Apply attacker naming rules** — NEVER use vendor codenames (Fancy Bear, Lazarus Group, APT28, Volt Typhoon, etc.). ALWAYS use plain executive language:
   - "Russia — GRU military intelligence"
   - "Russia — FSB intelligence service"
   - "China — state-suspected espionage group"
   - "North Korea — state-sponsored, financially motivated"
   - "Criminal gang — ransomware"
   - "Unknown"
   (See CLAUDE.md for the full naming rules)
3. **Assign severity** — `critical`, `high`, `medium`, or `low`
4. **Assign motivation** — exactly one of: `Financial`, `Espionage`, `Disruption`, `IP theft`, `Political`, `Unclear`
5. **Assign attacker_origin** — exactly one of: `russia`, `iran`, `china`, `north_korea`, `criminal`, `unknown`
6. **Determine ongoing status** — `Y` or `N`

Write the result to `docs/data/brief.json` using this exact schema:

```json
{
  "generated_at": "ISO-8601 UTC timestamp",
  "period_searched": "Human-readable date range, e.g. March 19-21, 2026",
  "incident_count": 0,
  "incidents": [
    {
      "id": "1",
      "date": "Display date, e.g. Mar 20",
      "date_sort": "YYYY-MM-DD",
      "victim": "Organization or sector name",
      "industry": "Industry sector",
      "attacker": "Plain-language attacker description",
      "attacker_origin": "russia|iran|china|north_korea|criminal|unknown",
      "motivation": "Financial|Espionage|Disruption|IP theft|Political|Unclear",
      "vector": "How the attack was carried out — one concise sentence",
      "impact": "What happened — one to two concise sentences",
      "ongoing": "Y|N",
      "severity": "critical|high|medium|low",
      "sources": ["source domain or name"]
    }
  ]
}
```

Sort incidents by `date_sort` descending (most recent first). Set `incident_count` to the length of the incidents array. Set `generated_at` to the current UTC time.

After writing `brief.json`, append a single JSON line to `docs/data/usage_log.jsonl` with this format:

```json
{"timestamp": "ISO-8601", "date": "{{DATE}}", "pipeline": "exa+claude-code", "sources_fetched": N, "sources_failed": N, "total_articles": N, "incident_count": N, "model": "claude-opus-4-6"}
```

Read the `_fetch_summary.json` to get the sources_fetched, sources_failed, and total_articles values.
