# me-kg

Personal knowledge graph: sources → agent → typed-edge markdown vault.

The vault is plain markdown + YAML frontmatter, in an Obsidian-friendly layout,
git-tracked. A Zen-agent (`opencode` API) does the semantically hard part —
extracting nodes and typed edges from raw content. Deterministic code does the
boring reliable part — parsing PDFs, git logs, validating schema, writing
files, committing.

### Prerequisites

- **python3** (3.11+)
- **Obsidian** (optional — for browsing the graph visually. The vault is plain markdown, readable anywhere.)
- A Zen API key from [opencode.ai/auth](https://opencode.ai/auth)

## Setup

```bash
# 1. Clone
git clone https://github.com/nandanadileep/skills-graph.git ~/me-kg
cd ~/me-kg

# 2. Install
python3 -m venv .venv && source .venv/bin/activate
pip install -e .

# 3. Set your Zen API key (get one at https://opencode.ai/auth)
cp me-kg.toml.example me-kg.toml
# Edit me-kg.toml → uncomment and set: zen_api_key = "sk-..."

# 4. Install the opencode skill (one-time, works across all projects)
mkdir -p ~/.config/opencode/skills
ln -s ~/me-kg/skills/updategraph ~/.config/opencode/skills/updategraph

# 5. Open the vault in Obsidian
# Point Obsidian at ~/me-kg/notes as a vault
```

Done. Now open opencode anywhere and just talk — "I'm reading this paper...", "update this graph", etc.

## Usage

### Via opencode (after skill is installed)

Just talk to opencode — the skill routes to the right command:

| You say in opencode | What happens |
|---|---|
| "I'm reading this paper ~/Downloads/react.pdf" | `me-kg paper ~/Downloads/react.pdf` |
| "Reading https://arxiv.org/abs/..." | `me-kg url https://arxiv.org/abs/...` |
| "I had an idea: X should do Y" | `me-kg note "I had an idea: X should do Y"` |
| "update the graph" (in a repo) | `me-kg project .` |
| "what's in my graph lately?" | `me-kg graph` |

Triggers: "I read", "I'm reading", "I just learned", "this paper", "update graph",
"add to graph", "/updategraph", "/note", "/read".

The agent creates the note, spawns concepts, wires edges — then tells you what it
did. Open Obsidian (point it at `~/me-kg/notes`) to browse the graph.

### Direct CLI

| Command | Description |
|---|---|
| `me-kg paper foo.pdf` | Ingest a research paper (PDF). |
| `me-kg project ./repo` | Scan your own repo — extracts README, git log, deps. |
| `me-kg note "raw thought..."` | Ingest a free-form note, idea, or reading mention. |
| `me-kg url https://...` | Fetch and ingest a web article/blog post. |
| `me-kg jot` | Open `$EDITOR`, ingests note on save. |

### Inspect the graph

| Command | Description |
|---|---|
| `me-kg graph` | Print total nodes, edges, type and status breakdown, sample edges. |
| `me-kg rebuild` | Rebuild the vault index from markdown files. |
| `me-kg orphans` | List nodes with few or no edges — good for weekly cleanup. |
| `me-kg communities` | Detect Louvain communities and write cluster summaries. |

### Backup (manual)

```bash
me-kg sync          # disabled by default — vault is local-first
```
Auto-commit is off. Set `auto_commit = true` in `me-kg.toml` if you want the CLI
to git commit after every write. `sync` is a no-op unless you set it up.

## Config (`me-kg.toml`)

```toml
[me-kg]
zen_api_key = "sk-..."              # avoids needing to export every time
# primary_model = "big-pickle"      # Zen model for extraction
# fallback_model = "deepseek-v4-flash-free"
# auto_commit = true                # git commit after every write
# private_mode = false              # routes to zero-retention model (planned)
```

`me-kg.toml` is gitignored — it can hold secrets.

## Schema

Fixed vocabulary (see `me_kg/schema.py`):

- **Nodes:** paper, project, note, idea, book, article, person, concept, tag.
- **Edges:** cites, extends, relates_to_concept, uses, implements, author_of,
  part_of, idea_from, discusses, mentions_person, tagged, depends_on,
  built_with, member_of.

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
to a cheaper model then skip — never write broken markdown. Git commits are
opt-in via `auto_commit` in config.

## Privacy

Free Zen models (Big Pickle, DeepSeek V4 Flash Free, etc.) may retain submitted
data per the [Zen docs](https://opencode.ai/docs/zen). For published research
that's fine; for private ideas set `private_mode = true` in `me-kg.toml`
(planned: routes to a paid zero-retention model and trims content).