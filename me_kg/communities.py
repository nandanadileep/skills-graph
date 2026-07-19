from __future__ import annotations
import json, os, sys, pathlib, subprocess, yaml, datetime
from typing import Any
import networkx as nx
try:
    from community import community_louvain
except ImportError:
    community_louvain = None

from .config import Config
from .index import load as load_index, build as build_index
from .agent import Agent
from .writer import FRONTMATTER_FENCE

CLUSTER_DIR = "clusters"
CLUSTER_TYPE = "tag"
MIN_COMMUNITY_SIZE = 3
RESOLUTION = 1.2

COMMUNITY_SYSTEM = (
    "You partition a user's knowledge graph into thematic communities using "
    "Louvain. You receive a single community's members (titles, types, "
    "summaries). Propose: (a) a 2-4 word slug for it, kebab-case, that names "
    "the THEME not the members; (b) a human-readable title; (c) a 1-2 "
    "sentence summary of what this community is about, in third person. "
    "Output STRICT JSON: {\"slug\":\"...\",\"title\":\"...\",\"summary\":\"...\"}. "
    "Do not include markdown fences. Do not include anything else."
)

def _node_weight(edge_type: str) -> float:
    weights = {
        "extends": 1.0, "implements": 1.0, "cites": 0.8,
        "relates_to_concept": 0.6, "uses": 0.6, "idea_from": 0.7,
        "built_with": 0.5, "depends_on": 0.5,
        "part_of": 0.4, "tagged": 0.2, "discusses": 0.3,
        "member_of": 0.0, "mentions_person": 0.4, "author_of": 0.4,
    }
    return weights.get(edge_type, 0.2)

def detect_communities(cfg: Config, *, resolution: float = RESOLUTION) -> dict[int, list[str]]:
    idx = load_index(cfg)
    G = nx.Graph()
    for slug in idx["nodes"]:
        G.add_node(slug)
    for e in idx["edges"]:
        a, b = e["from"], e["to"]
        if a == b or a not in idx["nodes"] or b not in idx["nodes"]:
            continue
        w = _node_weight(e["type"])
        if w <= 0:
            continue
        if G.has_edge(a, b):
            G[a][b]["weight"] += w
        else:
            G.add_edge(a, b, weight=w)
    if G.number_of_edges() == 0:
        return {}
    if community_louvain is None:
        partitions: dict[str, int] = nx.algorithms.community.greedy_modularity_communities(G)
        comms: dict[int, list[str]] = {}
        for i, comm in enumerate(partitions):
            comms[i] = list(comm)
    else:
        partitions = community_louvain.best_partition(G, resolution=resolution, random_state=42)
        comms: dict[int, list[str]] = {}
        for slug, cid in partitions.items():
            comms.setdefault(cid, []).append(slug)
    return {cid: members for cid, members in comms.items()
            if len(members) >= MIN_COMMUNITY_SIZE}

def _gather_members(idx: dict, members: list[str]) -> str:
    lines = []
    for s in members:
        n = idx["nodes"].get(s, {})
        title = n.get("title", s)
        type_ = n.get("type", "?")
        lines.append(f"- {type_} :: {s} :: {title}")
    return "\n".join(lines)

def name_community(cfg: Config, members_desc: str) -> dict[str, str]:
    agent = Agent(cfg)
    raw = agent.complete(COMMUNITY_SYSTEM, members_desc, json_mode=True)
    start = raw.find("{"); end = raw.rfind("}")
    if start == -1 or end == -1:
        raise RuntimeError(f"agent returned no JSON: {raw[:200]}")
    return json.loads(raw[start:end + 1])

def _frontmatter(s: str) -> dict:
    text = pathlib.Path(s).read_text(errors="ignore")
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 4)
    if end == -1:
        return {}
    import yaml
    return yaml.safe_load(text[4:end]) or {}

def run(cfg: Config, *, resolution: float = RESOLUTION,
        force: bool = False, dry_run: bool = False) -> None:
    idx = load_index(cfg)
    comms = detect_communities(cfg, resolution=resolution)
    if not comms:
        from rich import print
        print("[yellow]no communities detected[/] (need at least "
              f"{MIN_COMMUNITY_SIZE} nodes per community).")
        return
    cluster_dir = cfg.vault_dir / CLUSTER_DIR
    cluster_dir.mkdir(parents=True, exist_ok=True)
    existing = {p.stem: p for p in cluster_dir.glob("*.md")}
    written = []
    used_slugs = set()
    for cid, members in comms.items():
        desc = _gather_members(idx, members)
        if dry_run:
            continue
        if not force and "ZEN_API_KEY" in os.environ:
            try:
                meta = name_community(cfg, desc)
                slug = meta.get("slug", f"community-{cid}").strip().lower()
                title = meta.get("title", f"Community {cid}")
                summary = meta.get("summary", "")
            except Exception as e:
                slug, title, summary = f"community-{cid}", f"Community {cid}", ""
        else:
            slug, title, summary = f"community-{cid}", f"Community {cid}", ""
        if slug in used_slugs:
            slug = f"{slug}-{cid}"
        used_slugs.add(slug)
        path = cluster_dir / f"{slug}.md"
        # member links
        member_links = [f"[[{m}]]" for m in sorted(members)]
        fm = {
            "type": "tag",
            "title": title,
            "slug": slug,
            "created": datetime.date.today().isoformat(),
            "updated": datetime.date.today().isoformat(),
            "size": len(members),
            "summary": summary,
            "member_of": member_links if len(member_links) > 1
                         else (member_links[0] if member_links else ""),
        }
        fm_str = yaml.safe_dump(fm, sort_keys=False, allow_unicode=True, width=100).strip()
        body = f"# {title}\n\n{summary}\n\n## Members ({len(members)})\n" + \
               "\n".join(f"- [[{m}]]" for m in sorted(members))
        path.write_text(f"{FRONTMATTER_FENCE}{fm_str}\n{FRONTMATTER_FENCE}\n{body}\n")
        written.append((path, members))
        existing.pop(slug, None)
        # write member_of back-edge on each member file
        for m in members:
            _backedge_member_of(cfg, m, slug)
    # remove orphan cluster files no longer present
    for slug, p in existing.items():
        if slug.startswith("community-") or force:
            p.unlink(missing_ok=True)
    # backedges into member files so the reverse edge appears in graph view too
    build_index(cfg)
    from rich import print
    print(f"[bold green]clustered[/]: {len(written)} communities")
    for path, members in written:
        print(f"  {path.name:40s}  ({len(members)} members)")

def _backedge_member_of(cfg: Config, member_slug: str, cluster_slug: str) -> None:
    idx_path = cfg.state_dir / "vault-index.json"
    idx = json.loads(idx_path.read_text()) if idx_path.exists() else {"nodes": {}}
    rel = idx["nodes"].get(member_slug, {}).get("path")
    if not rel:
        return
    p = cfg.vault_dir / rel
    if not p.exists():
        return
    text = p.read_text(errors="ignore")
    if not text.startswith("---"):
        return
    end = text.find("\n---", 4)
    if end == -1:
        return
    front = yaml.safe_load(text[4:end]) or {}
    body = text[end + 4:].lstrip("\n")
    cur = front.get("member_of")
    targets: set[str] = set()
    if isinstance(cur, list):
        for t in cur:
            t = str(t).strip()
            targets.add(t[2:-2] if t.startswith("[[") else t)
    elif isinstance(cur, str):
        t = cur.strip()
        targets.add(t[2:-2] if t.startswith("[[") else t)
    targets.add(cluster_slug)
    if len(targets) == 1:
        front["member_of"] = f"[[{next(iter(targets))}]]"
    else:
        front["member_of"] = [f"[[{t}]]" for t in sorted(targets)]
    fm_str = yaml.safe_dump(front, sort_keys=False, allow_unicode=True, width=100).strip()
    p.write_text(f"{FRONTMATTER_FENCE}{fm_str}\n{FRONTMATTER_FENCE}\n{body}\n")