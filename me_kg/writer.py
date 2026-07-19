from __future__ import annotations
import re, json, pathlib, yaml, datetime
from typing import Iterable
from .schema import IngestResult, EdgeType, NodeType, Status

FRONTMATTER_FENCE = "---\n"
_SLUG_RE = re.compile(r"^\[\[([^\]]+)\]\]$")

def _slugify(s: str) -> str:
    s = re.sub(r"[^\w\s-]", "", (s or "").lower()).strip()
    return re.sub(r"[\s_-]+", "-", s) or "untitled"

def _today() -> str:
    return datetime.date.today().isoformat()

def _render(node_dict: dict, body: str, *, today: str) -> str:
    fm = dict(node_dict)
    fm.setdefault("created", today)
    fm["updated"] = today
    fm_str = yaml.safe_dump(fm, sort_keys=False, allow_unicode=True, width=100).strip()
    body = (body or "").strip()
    return f"{FRONTMATTER_FENCE}{fm_str}\n{FRONTMATTER_FENCE}\n{body}\n"

def _frontmatter(path: pathlib.Path) -> tuple[dict, str]:
    text = path.read_text(errors="ignore")
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 4)
    if end == -1:
        return {}, text
    front = yaml.safe_load(text[4:end]) or {}
    body = text[end + 4:].lstrip("\n")
    return front, body

def _subfolder(node_type: str) -> str:
    return {
        "paper": "papers", "project": "projects", "note": "notes",
        "idea": "ideas", "book": "notes", "article": "notes",
        "person": "people", "concept": "concepts", "tag": "tags",
    }.get(node_type, "notes")

def _edge_keys(attrs_or_frontmatter: dict, *, include_status: bool = False) -> Iterable[str]:
    skip = {"type", "title", "slug", "created", "updated", "tags", "doi", "url", "authors", "year", "venue", "summary", "name", "path", "package", "languages", "status"}
    for k in attrs_or_frontmatter:
        if k in skip:
            continue
        if k in _EDGE_VALUES:
            yield k

_EDGE_VALUES = {e.value for e in EdgeType}

def _edge_targets_to_list(v) -> list[str]:
    if v is None:
        return []
    if isinstance(v, list):
        return v
    return [v]

def _strip_brackets(s: str) -> str:
    m = _SLUG_RE.match(str(s).strip())
    return m.group(1) if m else str(s).strip()

def _linkify_one(slug: str) -> str:
    return f"[[{slug}]]"

def _merge_edges(existing: dict, new_edges: list) -> dict:
    """Merge new typed edges into existing frontmatter (dict). De-dupes on
    target slug per edge-type."""
    by_type: dict[str, set[str]] = {}
    for k in list(existing.keys()):
        if k in _EDGE_VALUES:
            tgt = {_strip_brackets(t) for t in _edge_targets_to_list(existing[k])}
            by_type[k] = tgt
            del existing[k]
    for e in new_edges or []:
        by_type.setdefault(e.type.value, set()).add(_strip_brackets(e.to))
    for k, slugs in by_type.items():
        if not slugs:
            continue
        if len(slugs) == 1:
            existing[k] = _linkify_one(next(iter(slugs)))
        else:
            existing[k] = [_linkify_one(s) for s in sorted(slugs)]
    return existing

def _maybe_downgrade_status(existing_front: dict, new_status: str | None) -> str | None:
    """Status progression: to-read < reading < read  (+ abandoned is terminal).
    Don't let a fresh stub 'reading' overwrite an existing 'read'."""
    if not new_status:
        return existing_front.get("status")
    order = {"to-read": 0, "reading": 1, "read": 2, "abandoned": 3}
    cur = existing_front.get("status")
    if not cur:
        return new_status
    if cur == "abandoned" and new_status != "abandoned":
        return cur
    if new_status == "abandoned" and cur != "abandoned":
        return new_status
    if order.get(new_status, 0) >= order.get(cur, 0):
        return new_status
    return cur

def write(cfg, result: IngestResult, *, matched_slug: str | None = None) -> pathlib.Path:
    """Write or upsert the node. If matched_slug is given (an existing node
    matched on title/DOI/URL), merge into that file instead of creating a new
    one and instead of trusting the agent's slug."""
    today = _today()
    node = result.node
    sub = _subfolder(node.type.value)
    folder = cfg.vault_dir / sub
    folder.mkdir(parents=True, exist_ok=True)

    effective_slug = matched_slug or node.slug
    path = folder / f"{effective_slug}.md"

    if path.exists() and matched_slug:
        action = "update"
    elif path.exists() and not matched_slug:
        action = "update"
    else:
        action = "create"

    # Build minimal.fm dict from the agent's node + attributes.
    fm: dict = {
        "type": node.type.value,
        "title": node.title,
        "slug": effective_slug,
    }
    if node.status and node.type.value in ("paper", "book", "article"):
        fm["status"] = node.status.value if isinstance(node.status, Status) else str(node.status)
    for k, v in (node.attributes or {}).items():
        if k == "status" and node.type.value in ("paper", "book", "article"):
            fm["status"] = v
            continue
        fm.setdefault(k, v)

    if action == "update" and path.exists():
        existing_front, existing_body = _frontmatter(path)
        merged = dict(existing_front)
        merged.update({"type": fm.get("type", existing_front.get("type")),
                       "title": fm.get("title", existing_front.get("title")),
                       "slug": effective_slug})
        if "status" in fm:
            merged["status"] = _maybe_downgrade_status(existing_front, fm.get("status"))
        for k, v in fm.items():
            if k in ("type", "title", "slug", "status"):
                continue
            if k not in merged or not merged.get(k):
                merged[k] = v
        merged = _merge_edges(merged, result.edges)
        body_new = (result.body_markdown or "").strip()
        body = existing_body.strip()
        if body_new and body_new not in body:
            body = (body + "\n\n---\n\n" + body_new).strip() if body else body_new
        path.write_text(_render(merged, body, today=today))
    else:
        fm = _merge_edges(fm, result.edges)
        path.write_text(_render(fm, result.body_markdown or "", today=today))

    for spawned in result.spawn or []:
        spawn_folder = cfg.vault_dir / _subfolder(spawned.type.value)
        spawn_folder.mkdir(parents=True, exist_ok=True)
        sp_path = spawn_folder / f"{spawned.slug}.md"
        if sp_path.exists():
            continue
        sp_fm: dict = {
            "type": spawned.type.value,
            "title": spawned.title,
            "slug": spawned.slug,
        }
        if spawned.summary:
            sp_fm["summary"] = spawned.summary
        sp_path.write_text(_render(sp_fm, spawned.summary or "", today=today))

    return path