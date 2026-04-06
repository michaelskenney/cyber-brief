---
name: Keep docs updated with every change
description: CLAUDE.md and README must be updated whenever the architecture, pipeline, or project structure changes
type: feedback
---

Always update CLAUDE.md and README.md to reflect the current state of the project after making architectural or structural changes. Don't rely on stale documentation — verify against the actual codebase.

**Why:** The project iterates quickly with frequent approach changes. Stale docs caused Claude to describe an outdated architecture (Anthropic API + GitHub Actions) when the project had already moved to Exa + Claude Code CLI + launchd. This wastes time and erodes trust.

**How to apply:** After any change that affects how the pipeline works, what files exist, what APIs are used, or how the project is scheduled/deployed, update both CLAUDE.md (for Claude Code context) and README.md (for human readers) as part of the same piece of work. Don't treat doc updates as a separate follow-up task.
