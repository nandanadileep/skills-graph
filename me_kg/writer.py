from __future__ import annotations
import re, json, pathlib, yaml
from typing import Iterable
from .schema import IngestResult, EdgeType

FRONTMATTER_FENCE = "---\n"

def _slug(s: str) -> str:
    s = re.sub(r"[^\w\s-]", "", s.lower()).strip()
    return re.sub(r"[\s_-]+", "-", s)

def render(result: IngestResult, *, today: str) -> str:
    fm: dict = {
        "type": result.node.type.value,
        "title": result.node.title,
        "slug": result.node.slug,
        "created": today,
        "updated": today,
    }
    for k, v in result.node.attributes.items():
        fm.setdefault(k, v)
    edges_by_type: dict[str, list[str]] = {}
    for e in result.edges:
        edges_by_type.setdefault(e.type.value, []).append(f"[[{e.to}]]")
    for k, v in edges_by_type.items():
        fm[k] = v if len(v) > 1 else v[0]
    fm_str = yaml.safe_dump(fm, sort_keys=False, allow_unicode=True, width=100).strip()
    body = result.body_markdown.strip()
    return f"{FRONTMATTER_FENCE}{fm_str}\n{FRONTMATTER_FENCE}\n{body}\n"

def write(cfg, result: IngestResult, source_tag: str = "") -> pathlib.Path:
    sub = {
        "paper": "papers", "project": "projects", "note": "notes",
        "idea": "ideas", "book": "notes", "article": "notes",
        "person": "people", "concept": "concepts", "tag": "tags",
    }[result.node.type.value]
    folder = cfg.vault_dir / sub
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{result.node.slug}.md"
    today = __import__("datetime").date.today().isoformat()
    path.write_text(render(result, today=today))
    for spawned in result.spawn:
        sp = IngestResult(node=spawned, edges=[], spawn=[], body_markdown="")
        sub2 = {
            "paper": "papers", "project": "projects", "note": "notes",
            "idea": "ideas", "book": "notes", "article": "notes",
            "person": "people", "concept": "concepts", "tag": "tags",
        }[spawned.type.value]
        target = cfg.vault_dir / sub2 / f"{spawned.slug}.md"
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            sp_path = cfg.vault_dir / sub2
            (sp_path / f"{spawned.slug}.md").write_text(render(sp, today=today))
    return path