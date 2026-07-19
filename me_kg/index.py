from __future__ import annotations
import json, pathlib, re, difflib
from .config import Config
from .schema import EdgeType, NodeType

INDEX_FILE = "vault-index.json"
_SLUG_RE = re.compile(r"^\[\[([^\]]+)\]\]$")
_EDGE_KEYS = {e.value for e in EdgeType}
_STATUS_KEYS = {"status"}
_NORMALIZE_TITLE_RE = re.compile(r"[^a-z0-9]+")

def _norm_title(s: str) -> str:
    return _NORMALIZE_TITLE_RE.sub(" ", (s or "").lower()).strip()

def _norm_url(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"^https?://(www\.)?", "", s)
    s = s.rstrip("/")
    return s

def build(cfg: Config) -> dict:
    idx: dict = {"nodes": {}, "edges": []}
    for md in cfg.vault_dir.rglob("*.md"):
        text = md.read_text(errors="ignore")
        if not text.startswith("---"):
            continue
        end = text.find("\n---", 4)
        if end == -1:
            continue
        front = _yaml_safe(text[4:end])
        slug = front.get("slug") or md.stem
        idx["nodes"][slug] = {
            "type": front.get("type"),
            "title": front.get("title", md.stem),
            "norm_title": _norm_title(front.get("title", "")),
            "status": front.get("status"),
            "doi": _norm_url(front.get("doi", "")) or None,
            "url": _norm_url(front.get("url", "")) or None,
            "tags": front.get("tags", []),
            "path": str(md.relative_to(cfg.vault_dir)),
            "embedding": None,
        }
        for k, v in front.items():
            if k in ("type", "title", "slug", "created", "updated", "tags",
                     "status", "doi", "url"):
                continue
            if k not in _EDGE_KEYS:
                continue
            targets = v if isinstance(v, list) else [v]
            for t in targets:
                m = _SLUG_RE.match(str(t).strip())
                idx["edges"].append({"from": slug, "type": k,
                                     "to": m.group(1) if m else str(t)})
    (cfg.state_dir / INDEX_FILE).write_text(json.dumps(idx, indent=2))
    return idx

def _yaml_safe(s: str) -> dict:
    import yaml
    try:
        return yaml.safe_load(s) or {}
    except Exception:
        return {}

def load(cfg: Config) -> dict:
    f = cfg.state_dir / INDEX_FILE
    if not f.exists():
        return build(cfg)
    return json.loads(f.read_text())

def context_lines(idx: dict, *, max_nodes: int = 400) -> str:
    if len(idx["nodes"]) > max_nodes:
        names = list(idx["nodes"])[:max_nodes]
    else:
        names = list(idx["nodes"])
    return "\n".join(
        f"{n}  ({idx['nodes'][n].get('type','?')}: {idx['nodes'][n].get('title','')})"
        for n in names
    )

def match_node(idx: dict, *, slug: str | None = None, title: str | None = None,
               url: str | None = None, doi: str | None = None,
               fuzzy_threshold: float = 0.86) -> str | None:
    """Return the slug of an existing node matching any identifier, or None."""
    if slug and slug in idx["nodes"]:
        return slug
    nu = _norm_url(url) if url else None
    nd = _norm_url(doi) if doi else None
    nt = _norm_title(title) if title else None
    for s, n in idx["nodes"].items():
        if nu and (n.get("url") == nu or n.get("doi") == nu):
            return s
        if nd and (n.get("doi") == nd or n.get("url") == nd):
            return s
    if nt:
        for s, n in idx["nodes"].items():
            if n.get("norm_title") and n["norm_title"] == nt:
                return s
        best, best_r = None, 0.0
        for s, n in idx["nodes"].items():
            if not n.get("norm_title"):
                continue
            r = difflib.SequenceMatcher(None, nt, n["norm_title"]).ratio()
            if r > best_r:
                best, best_r = s, r
        if best_r >= fuzzy_threshold:
            return best
    return None

def resolve_spawn(idx: dict, title: str, type_: str | None = None,
                  threshold: float = 0.86) -> str | None:
    """If a concept/tag/person with a near-identical title already exists,
    return its slug so the agent's `spawn` is dropped and the edge points to
    the existing node instead. Fuzzy for now; embeddings later."""
    nt = _norm_title(title)
    if not nt:
        return None
    candidates = [(s, n) for s, n in idx["nodes"].items()
                  if (type_ is None or n.get("type") == type_)
                  and n.get("norm_title")]
    exact = next((s for s, n in candidates if n["norm_title"] == nt), None)
    if exact:
        return exact
    best, best_r = None, 0.0
    for s, n in candidates:
        r = difflib.SequenceMatcher(None, nt, n["norm_title"]).ratio()
        if r > best_r:
            best, best_r = s, r
    return best if best_r >= threshold else None