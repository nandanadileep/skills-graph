from __future__ import annotations
import os, typer, json, pathlib, textwrap
from rich import print, console
from typing import Optional
from .config import Config
from .agent import Agent
from .schema import validate, NodeType, Status, IngestResult, NodeRef, Edge
from . import extractors as ext
from .writer import write as write_node
from .index import build as build_index, load as load_index, context_lines, match_node, resolve_spawn
from .git import commit as git_commit
from .agent.prompts import PROMPT_BASE

app = typer.Typer(help="me-kg: personal knowledge graph", no_args_is_help=True)
console = console.Console()

SCHEMA_HINT = textwrap.dedent("""\
{
  "node": {"type": "paper|project|note|idea|book|article|person|concept|tag",
           "slug": "kebab-case-id",
           "title": "...",
           "status": "to-read|reading|read|abandoned   (paper/book/article only; omit otherwise)",
           "summary": "<200 words first-person",
           "attributes": {"authors": ["..."], "url": "...", "doi": "...", "year": "..."}},
  "action": "create|update",
  "edges": [{"type": "<edge type from vocab>", "to": "<slug or [[slug]]>"}],
  "spawn": [{"type": "concept|person|...", "slug": "...", "title": "...",
             "summary": "..."}],
  "body_markdown": "the note body, in my voice, with [[inline-links]], no frontmatter"
}""")

STUB_RULES = """
STUB VS FULL RULES:
- If the input has only a title/name and essentially no other content
  (no abstract, no topics, no commentary), emit a STUB:
    * status = 'reading' for paper/book/article
    * NO edges that are guesswork. NO spawned concepts. body_markdown = "" or one short line.
    * action = 'create' (or 'update' if you are amending a stub).
- If the input has real content (abstract, topics, notes, your commentary,
  repo README, PDF text), emit a FULL node with edges and spawns as appropriate.

STATUS RULES (strict — do not infer):
- Set status='reading' ONLY when the user says they are currently reading it,
  or just started, or are "on" it.
- Set status='read' ONLY when the user EXPLICITLY says they finished it
  ("finished", "done with", "read it", "completed"). The presence of topics
  or notes does NOT mean finished — they may be reading and taking notes.
- Set status='abandoned' ONLY when the user explicitly says they stopped
  ("gave up", "abandoned", "skipped", "stopped reading").
- Set status='to-read' ONLY when the user says they plan to read it
  ("want to read", "on my list", "to-read").
- If updating an existing paper/book/article and you have no new explicit
  status signal from the user, OMIT status from the output entirely; the
  existing status will be preserved.
Never invent edges from a title alone.
"""

UPSERT_RULES = """
UPSERT RULES (critical — read carefully):
- "EXISTING VAULT NODES" lists current node slugs + titles. If you can match
  the entity you are describing to one of those (by title, DOI, URL, or
  recognizable phrasing), set action="update" AND emit the node.slug equal to
  the EXISTING slug (not a fresh one). Patch its status and add new edges.
- For genuinely new entities, action="create" with a fresh slug.
- When in doubt, reuse the existing slug. Duplicates are worse than a missed edge.
"""

DEDUP_RULES = """
SPAWN DEDUP RULES:
- Before listing a concept/tag/person in `spawn`, scan EXISTING VAULT NODES
  for one with the same meaning (case-insensitive). Reuse it as an edge
  target instead of spawning. Only spawn if no equivalent exists.
  e.g. "LLM Agents" and "Agentic LLM Systems" are NOT distinct; reuse whichever
  slug already exists.
"""

_STATUS_KEYWORDS = {
    "to-read": ["want to read", "to read", "to-read", "on my list", "plan to read", "queue", "backlog"],
    "reading": ["reading", "i'm on", "i am on", "started", "picking up", "on paper"],
    "read": ["finished", "done with", "completed", "wrapped up", "re-read", "reread", "read it", "done reading"],
    "abandoned": ["gave up", "abandoned", "skipped", "stopped reading", "dropped", "ditched"],
}

def _detect_status(text: str) -> str | None:
    t = (text or "").lower()
    found = set()
    for status, kws in _STATUS_KEYWORDS.items():
        for kw in kws:
            if kw in t:
                found.add(status)
                break
    if not found:
        return None
    order = {"to-read": 0, "reading": 1, "read": 2, "abandoned": 3}
    if "abandoned" in found:
        return "abandoned"
    return max(found, key=lambda s: order[s])

def _safe_extract(cfg: Config, system: str, content: str) -> IngestResult:
    if "ZEN_API_KEY" not in os.environ:
        raise SystemExit("ERROR: ZEN_API_KEY not set. Export it in your shell before starting opencode:\n  export ZEN_API_KEY=...")
    idx = load_index(cfg)
    ctx = context_lines(idx)
    system_full = (PROMPT_BASE + "\n\n" + STUB_RULES + "\n\n" + UPSERT_RULES
                   + "\n\n" + DEDUP_RULES
                   + "\n\nEXISTING VAULT NODES (reuse slugs where they fit):\n" + ctx
                   + "\n\nSCHEMA:\n" + SCHEMA_HINT + "\n\n" + system)
    agent = Agent(cfg)
    try:
        payload = agent.extract(system_full, content)
        result = validate(payload)
    except SystemExit:
        raise
    except Exception as e:
        raise SystemExit(f"ERROR: agent extraction failed: {e}")

    matched = match_node(
        idx,
        slug=result.node.slug,
        title=result.node.title,
        url=result.node.attributes.get("url"),
        doi=result.node.attributes.get("doi"),
    )
    if matched and matched != result.node.slug:
        result.node.slug = matched
        result.action = "update"

    if result.node.type.value in ("paper", "book", "article"):
        detected = _detect_status(content)
        if detected:
            from .schema import Status
            result.node.status = Status(detected)
        elif result.action == "update":
            existing = idx["nodes"].get(result.node.slug, {})
            cur = existing.get("status")
            if cur:
                from .schema import Status
                result.node.status = Status(cur)
            else:
                result.node.status = None
        else:
            from .schema import Status
            if result.node.status is None:
                result.node.status = Status.reading

    deduped_spawns: list[NodeRef] = []
    for sp in result.spawn or []:
        existing = resolve_spawn(idx, sp.title, type_=sp.type.value)
        if existing:
            for e in result.edges:
                if _strip_brackets(e.to) == sp.slug:
                    e.to = f"[[{existing}]]"
        else:
            deduped_spawns.append(sp)
    result.spawn = deduped_spawns
    return result

def _strip_brackets(s: str) -> str:
    import re
    m = re.match(r"^\[\[([^\]]+)\]\]$", str(s).strip())
    return m.group(1) if m else str(s).strip()

def _write_and_commit(cfg: Config, result: IngestResult, source_tag: str = "") -> pathlib.Path:
    path = write_node(cfg, result, matched_slug=result.node.slug if result.action == "update" else None)
    build_index(cfg)
    git_commit(cfg, [path], f"me-kg: {result.action} {result.node.type.value} '{result.node.slug}'{source_tag}")
    print(f"[bold green]{result.action}[/] {path}")
    status_str = f"  status: {result.node.status.value}" if result.node.status else ""
    print(f"  edges: {len(result.edges)}  spawned: {len(result.spawn)}{status_str}")
    return path

def _run_extract(cfg: Config, system: str, content: str) -> pathlib.Path:
    result = _safe_extract(cfg, system, content)
    return _write_and_commit(cfg, result)

PAPER_SYS = "SOURCE TYPE: paper (PDF). Extract title, authors, year, venue if visible. Pull out the 3-7 core concepts as separate concept spawns. Connect to existing concepts/projects where they fit (relates_to_concept, cites existing papers). If it builds on something you already know, add an 'extends' edge. status = 'reading' if the user is reading it now, 'read' if they finished."

@app.command()
def paper(path: str, ocr: bool = True):
    """Ingest a research paper PDF."""
    cfg = Config.load()
    text, meta = ext.extract_pdf(path, ocr=ocr)
    if not text.strip():
        raise SystemExit("PDF yielded no text (OCR disabled or failed)")
    payload = f"PDF METADATA:\n{json.dumps(meta, indent=2)}\n\nPDF CONTENT (truncated):\n{text[:16000]}"
    _run_extract(cfg, PAPER_SYS, payload)

PROJECT_SYS = "SOURCE TYPE: project (your own git repo). Treat it as the user's own project. Extract name, primary languages, status (active/dormant/archived based on recent commits), the libraries/frameworks it 'built_with', dependencies as 'depends_on'. Spawn concepts for the core technical ideas. Add 'implements' edges to papers/concepts if the README mentions any. The note body should reflect the user's voice about WHY this exists and what's interesting, not a sales pitch."

@app.command()
def project(path: str, max_log: int = 50):
    """Ingest a project from a git repo."""
    cfg = Config.load()
    text, meta = ext.extract_repo(path, max_log=max_log)
    payload = f"REPO META:\n{json.dumps(meta, indent=2)}\n\nCONTENT:\n{text[:16000]}"
    _run_extract(cfg, PROJECT_SYS, payload)

NOTE_SYS = "SOURCE TYPE: raw note/thought/idea/quote/link. Decide the most fitting node type (note, idea, sometimes article/book/paper if it clearly refers to one). If the user mentions a paper/book/article by title, create a paper/book/article node with status='reading' and connect from a note via 'discusses' if the user's message is itself a note. Extract key concept spawns only if they are explicit and strong. Use 'idea_from' or 'discusses' edges to other nodes where the connection is obvious. Keep the user's voice in body_markdown verbatim-ish; do not invent facts not in the input. Apply STUB VS FULL RULES strictly — a bare 'reading X' with nothing else is a STUB."

@app.command()
def note(text: str, tag: list[str] = typer.Option([])):
    """Ingest a free-form thought or note."""
    cfg = Config.load()
    payload = text + (f"\n\nRAW TAGS: {tag}" if tag else "")
    _run_extract(cfg, NOTE_SYS, payload)

@app.command(name="jot")
def jot():
    """Open $EDITOR (or vi) and capture a quick note on save."""
    import tempfile, subprocess
    editor = os.environ.get("EDITOR", "vi")
    with tempfile.NamedTemporaryFile("w+", suffix=".md", delete=False) as f:
        f.write("")
        tmp = f.name
    subprocess.run([editor, tmp], check=True)
    content = pathlib.Path(tmp).read_text()
    if content.strip():
        note(content)

@app.command()
def url(link: str):
    """Fetch a web article and ingest it."""
    import httpx, re
    cfg = Config.load()
    html = httpx.get(link, follow_redirects=True, timeout=30).text
    body = re.sub(r"<script.*?</script>", "", html, flags=re.S)
    body = re.sub(r"<[^>]+>", " ", body)
    payload = f"URL: {link}\n\n{body[:16000]}"
    _run_extract(cfg, NOTE_SYS + "\nIf this is clearly an article/blog post emit 'article' node (or 'paper' if it's a paper).", payload)

@app.command()
def rebuild():
    """Rebuild vault-index.json from markdown."""
    cfg = Config.load()
    idx = build_index(cfg)
    print(f"[bold]index rebuilt[/]: {len(idx['nodes'])} nodes, {len(idx['edges'])} edges")

@app.command()
def graph():
    """Print the graph summary."""
    cfg = Config.load()
    idx = load_index(cfg)
    print(f"nodes: {len(idx['nodes'])}  edges: {len(idx['edges'])}")
    by_type: dict[str, int] = {}
    for n in idx["nodes"].values():
        by_type[n.get("type", "?")] = by_type.get(n.get("type", "?"), 0) + 1
    for t, c in sorted(by_type.items()):
        print(f"  {t:10s} {c}")
    by_status: dict[str, int] = {}
    for n in idx["nodes"].values():
        s = n.get("status")
        if s:
            by_status[s] = by_status.get(s, 0) + 1
    if by_status:
        print("\nstatus:")
        for s, c in sorted(by_status.items()):
            print(f"  {s:12s} {c}")
    print("\nsample edges:")
    for e in idx["edges"][:20]:
        typer.echo(f"  {e['from']} -[{e['type']}]-> {e['to']}")

@app.command()
def orphans(threshold: int = 1, json_out: bool = False):
    """Report nodes with <= threshold edges. Weekly cleanup nudge.

    The node itself is always counted as 'existing'; we count the number of
    edges (incoming or outgoing) that touch it. Stub nodes (no body, status
    'reading' or 'to-read') are flagged separately.
    """
    cfg = Config.load()
    idx = load_index(cfg)
    degree: dict[str, int] = {s: 0 for s in idx["nodes"]}
    for e in idx["edges"]:
        degree[e["from"]] = degree.get(e["from"], 0) + 1
        degree[e["to"]] = degree.get(e["to"], 0) + 1
    orphans = []
    for s, n in idx["nodes"].items():
        if degree.get(s, 0) <= threshold:
            orphans.append({"slug": s, "type": n.get("type"),
                            "title": n.get("title", s), "degree": degree.get(s, 0),
                            "status": n.get("status")})
    orphans.sort(key=lambda o: (o["degree"], o["type"] or "", o["slug"]))
    if json_out:
        typer.echo(json.dumps(orphans, indent=2))
        return
    if not orphans:
        print(f"[green]no orphan nodes[/] (threshold <= {threshold})")
        return
    print(f"[bold]orphaned nodes[/] (degree <= {threshold}): {len(orphans)}")
    for o in orphans:
        status_str = f"  [dim]{o['status']}[/]" if o.get("status") else ""
        print(f"  {o['type'] or '?':8s}  deg={o['degree']}  [[{o['slug']}]]{status_str}")
        print(f"           {o['title']}")

@app.command()
def watch(folder: str, interval: int = 10):
    """Watch a folder for new PDFs and git repos to ingest. (Phase 2 stub.)"""
    print(f"[yellow]watch[/] not yet implemented (planned). For now run `me-kg paper <pdf>` / `me-kg project <repo>` explicitly.")

if __name__ == "__main__":
    app()