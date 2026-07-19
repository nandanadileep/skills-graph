# me-kg

Personal knowledge graph: sources → agent → typed-edge markdown vault.

The vault is plain markdown + YAML frontmatter, in an Obsidian-friendly layout,
git-tracked. A Zen-agent (`opencode` API) does the semantically hard part —
extracting nodes and typed edges from raw content. Deterministic code does the
boring reliable part — parsing PDFs, git logs, validating schema, writing
files, committing.

## Sources

- `me-kg paper foo.pdf` — drop a research paper.
- `me-kg project ./some-repo` — scan your own repo.
- `me-kg note "raw thought..."` — free-form note with optional `--tag`.
- `me-kg jot` — opens `$EDITOR`, ingests on save.
- `me-kg url https://...` — fetch + ingest an article.
- `me-kg watch ~/Dropbox` — (planned) auto-ingest dropped PDFs/repos.
- `me-kg rebuild` — rebuild `.me-kg/vault-index.json` from markdown.
- `me-kg graph` — print graph summary.

## Setup

```bash
cd me-kg
python -m venv .venv && source .venv/bin/activate
pip install -e .
export ZEN_API_KEY=...           # from https://opencode.ai/auth
me-kg paper ~/Downloads/whatever.pdf
```

## Schema

Fixed vocabulary (see `me_kg/schema.py`):

- **Nodes:** paper, project, note, idea, book, article, person, concept, tag.
- **Edges:** cites, extends, relates_to_concept, uses, implements, author_of,
  part_of, idea_from, discusses, mentions_person, tagged, depends_on, built_with.

Add a new type by editing `schema.py` only — the agent's prompt is derived from
the same enum.

## Layout

```
notes/{papers,projects,notes,ideas,people,concepts,tags}/*.md
.me-kg/vault-index.json        # cache for agent context
.me-kg/state.json
```

## Agent contract

The agent returns strict JSON validated by `pydantic`. On failure we fall back
to a cheaper model then skip — never write broken markdown. Every successful
ingest commits + pushes to git.

## Privacy

Free Zen models (Big Pickle, DeepSeek V4 Flash Free, etc.) may retain submitted
data per the [Zen docs](https://opencode.ai/docs/zen). For published research
that's fine; for private ideas set `private_mode = true` in `me-kg.toml`
(planned: routes to a paid zero-retention model and trims content).