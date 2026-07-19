---
type: project
title: Issue Radar
slug: issue-radar
languages:
- python
- javascript
- typescript
built_with:
- '[[fastapi]]'
- '[[httpx]]'
- '[[jinja2]]'
- '[[uvicorn]]'
created: '2026-07-19'
updated: '2026-07-19'
---

My project for finding interesting GitHub issues to work on. It takes your GitHub profile, generates semantic queries from your merged PRs and languages, then uses GitHub's hybrid search to find open, unassigned issues.

The key insight: you can't use `stars:` in the search query directly — it degrades into a text token. So I batch-fetch stars with GraphQL and filter client-side. Also learned that PR titles need repo-specific identifiers stripped before they become search queries, or they poison the embedding.

Built with [[fastapi]] for the web UI, [[httpx]] for async GitHub API calls. Results are cached for 6 hours since semantic search is rate-limited.

Core files:
- `engine.py` — the matching pipeline: profile → queries → search → score
- `main.py` — FastAPI app with in-memory cache
- `spike.py` — zero-dependency CLI prototype for validation

Future: multi-user OAuth support, SQLite caching for repeat visits.
