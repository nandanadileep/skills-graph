from __future__ import annotations
import json, pathlib, re
from .config import Config
from .schema import EdgeType

_EDGE_KEYS = {e.value for e in EdgeType}

INDEX_FILE = "vault-index.json"
_SLUG_RE = re.compile(r"^\[\[([^\]]+)\]\]$")

def build(cfg: Config) -> dict:
    idx: dict[str, dict] = {"nodes": {}, "edges": []}
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
            "tags": front.get("tags", []),
            "path": str(md.relative_to(cfg.vault_dir)),
        }
        for k, v in front.items():
            if k in ("type", "title", "slug", "created", "updated", "tags"):
                continue
            if k not in _EDGE_KEYS:
                continue
            targets = v if isinstance(v, list) else [v]
            for t in targets:
                m = _SLUG_RE.match(str(t).strip())
                idx["edges"].append({"from": slug, "type": k, "to": m.group(1) if m else str(t)})
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