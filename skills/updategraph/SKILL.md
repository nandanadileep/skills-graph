---
name: updategraph
description: Use when the user talks about reading papers/articles/books, learning topics, working on projects, having ideas, or asks to update their personal knowledge graph. Drives the me-kg CLI which ingests content (PDF, URL, free text, or the current repo) into their Obsidian-formatted markdown vault and commits to git. Front-load triggers: "I read", "I'm reading", "I just learned", "this paper", "update graph", "add to graph", "/updategraph", "/note", "/read".
---

# updategraph — personal knowledge graph ingestion

The user maintains a personal knowledge graph as a vault of markdown files with
typed edges (`cites`, `relates_to_concept`, `uses`, `implements`, `part_of`,
`idea_from`, `discusses`, `mentions_person`, `tagged`, `depends_on`,
`built_with`, `extends`, `author_of`). Nodes are typed: `paper`, `project`,
`note`, `idea`, `book`, `article`, `person`, `concept`, `tag`.

The vault lives at `notes/` inside the user's `me-kg` checkout (the same
folder opened in Obsidian). All updates go through the **`me-kg`** CLI, which:

1. Extracts raw content from the source (PDF text + OCR, repo README + git log,
   raw text, fetched URL).
2. Calls a Zen LLM agent to produce nodes + typed edges as validated JSON.
3. Writes markdown with YAML frontmatter + inline `[[wikilinks]]`.

**Auto-commit to git is OFF by default.** Vault files write to disk silently and
Obsidian sees them immediately (it watches the folder). The user explicitly runs
`me-kg sync` when they want a git backup. Do NOT mention git push in your
follow-up unless they ran `me-kg sync`.

## CRITICAL RULES

- **Never edit vault markdown by hand.** Always route through `me-kg`. The
  schema is enforced by pydantic; manual edits break the agent's context.
- **Never commit `me-kg.toml`** (it can hold secrets). The CLI already gitignores it.
- If `me-kg` errors with "ZEN_API_KEY not set", tell the user to
  `export ZEN_API_KEY=...` in their shell or set `zen_api_key` in `me-kg.toml`.
- Don't paraphrase what the user said into the vault yourself — pass their
  words through `me-kg note` so the agent keeps their voice.
- **Do not run `me-kg sync` unless the user explicitly asks.** Vault writes
  are local-first; git backup is a manual step they choose.

## Commands

### When the user is in ANY repo and says something like "update the graph", "log this project", "/updategraph"

Run this from the repo's root:

```bash
me-kg project .
```

Then briefly tell the user: the node title, the concepts spawned, the edges
added. The output of the command already prints this.

### When the user describes reading/learning/thinking in free prose, or invokes /note with text

If their message includes a path ending in `.pdf`:

```bash
me-kg paper "<path>"
```

If it includes a URL (starts with `http://` or `https://`):

```bash
me-kg url "<url>"
```

Otherwise treat the entire message as a free-form note:

```bash
me-kg note "<the user's message verbatim>"
```

### When the user wants to think out loud in their editor

```bash
me-kg jot
```

Opens `$EDITOR`, ingests on save. Don't run this for them — suggest it.

### When the user asks "what's in my graph?" or "what have I read recently?"

```bash
me-kg graph
```

Show them the summary. Don't enumerate every node unless asked.

## Routing examples

| User says | You run |
|---|---|
| "I just read the ReAct paper at ~/Downloads/react.pdf" | `me-kg paper ~/Downloads/react.pdf` |
| "Reading http://arxiv.org/abs/2401.00001 — interesting" | `me-kg url http://arxiv.org/abs/2401.00001` |
| "I had an idea: eval-driven dev should replay frozen trajectories" | `me-kg note "I had an idea: eval-driven dev should replay frozen trajectories"` |
| "update the graph" (cwd is a repo) | `me-kg project .` |
| "what's in my graph lately?" | `me-kg graph` |

## After running

Report concisely:
- 1 line: the node type + title created/updated
- 1 line: number of edges + spawned concepts
- (optional) the file path so they can open it in Obsidian

Do **not** paste the full markdown back at them — they'll see it in Obsidian.

## If it fails

- `ZEN_API_KEY not set` → tell the user to export it or set `zen_api_key` in `me-kg.toml` and rerun. Don't retry silently.
- Schema validation error → report the error message, suggest the user retry with clearer input. Do not patch the output yourself.
- Git push rejected → tell the user; don't force-push.