from __future__ import annotations
import os, typer, json, pathlib, textwrap
from rich import print, console
from typing import Optional
from .config import Config
from .agent import Agent
from .schema import validate, NodeType
from . import extractors as ext
from .writer import write as write_node
from .index import build as build_index, load as load_index, context_lines
from .git import commit as git_commit
from .agent.prompts import PROMPT_BASE

app = typer.Typer(help="me-kg: personal knowledge graph", no_args_is_help=True)
console = console.Console()

SCHEMA_HINT = textwrap.dedent("""\
{
  "node": {"type": "paper|project|note|idea|book|article|person|concept|tag",
           "slug": "kebab-case-id",
           "title": "...",
           "summary": "<200 words first-person",
           "attributes": {"authors": ["..."], "url": "...", "year": "..."}},
  "edges": [{"type": "<edge type from vocab>", "to": "<slug or [[slug]]>"}],
  "spawn": [{"type": "concept|person|...", "slug": "...", "title": "...",
             "summary": "..."}],
  "body_markdown": "the note body, in my voice, with [[inline-links]], no frontmatter"
}""")

def _run_extract(cfg: Config, system: str, content: str) -> pathlib.Path:
    if "ZEN_API_KEY" not in os.environ:
        raise SystemExit("ERROR: ZEN_API_KEY not set. Export it in your shell before starting opencode:\n  export ZEN_API_KEY=...")
    idx = load_index(cfg)
    ctx = context_lines(idx)
    system_full = PROMPT_BASE + "\n\nEXISTING VAULT NODES (reuse slugs where they fit):\n" + ctx + "\n\nSCHEMA:\n" + SCHEMA_HINT + "\n\n" + system
    try:
        agent = Agent(cfg)
        payload = agent.extract(system_full, content)
        result = validate(payload)
    except SystemExit:
        raise
    except Exception as e:
        raise SystemExit(f"ERROR: agent extraction failed: {e}")
    path = write_node(cfg, result)
    build_index(cfg)
    git_commit(cfg, [path], f"me-kg: ingest {result.node.type.value} '{result.node.slug}'")
    print(f"[bold green]wrote[/] {path}")
    print(f"  edges: {len(result.edges)}  spawned: {len(result.spawn)}")
    return path

PAPER_SYS = "SOURCE TYPE: paper (PDF). Extract title, authors, year, venue if visible. Pull out the 3-7 core concepts as separate concept spawns. Connect to existing concepts/projects where they fit (relates_to_concept, cites existing papers). If it builds on something you already know, add an 'extends' edge."

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

NOTE_SYS = "SOURCE TYPE: raw note/thought/idea/quote/link. Decide the most fitting node type (note, idea, sometimes article/book if it clearly refers to one). Extract key concept spawns only if they are explicit and strong. Use 'idea_from' or 'discusses' edges to other nodes where the connection is obvious. Keep the user's voice in body_markdown verbatim-ish; do not invent facts not in the input."

@app.command()
def note(text: str, tag: list[str] = typer.Option([])):
    """Ingest a free-form thought or note."""
    cfg = Config.load()
    payload = text + (f"\n\nRAW TAGS: {tag}" if tag else "")
    _run_extract(cfg, NOTE_SYS, payload)

@app.command(name="jot")
def jot():
    """Open $EDITOR (or vi) and capture a quick note on save."""
    import tempfile, os, subprocess
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
    _run_extract(cfg, NOTE_SYS + "\nIf this is clearly an article/blog post emit 'article' node.", payload)

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
    print("\nsample edges:")
    for e in idx["edges"][:20]:
        typer.echo(f"  {e['from']} -[{e['type']}]-> {e['to']}")

@app.command()
def watch(folder: str, interval: int = 10):
    """Watch a folder for new PDFs and git repos to ingest. (Phase 2 stub.)"""
    print(f"[yellow]watch[/] not yet implemented (planned). For now run `me-kg paper <pdf>` / `me-kg project <repo>` explicitly.")

if __name__ == "__main__":
    app()