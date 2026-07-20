from __future__ import annotations
import subprocess, pathlib, re

def extract_repo(path: str, *, max_log: int = 50) -> tuple[str, dict]:
    p = pathlib.Path(path).expanduser().resolve()
    if not p.is_dir():
        raise SystemExit(f"{p} is not a directory")
    is_git = (p / ".git").exists()
    readme = ""
    for name in ("README.md", "README.mdx", "README.txt", "README"):
        f = p / name
        if f.exists():
            readme = f.read_text(errors="ignore")[:8000]
            break
    log = ""
    dirty = False
    if is_git:
        log = subprocess.run(
            ["git", "-C", str(p), "log", f"-n{max_log}",
             "--format=%h %ad %s  @%an", "--date=short"],
            capture_output=True, text=True,
        ).stdout
        status = subprocess.run(
            ["git", "-C", str(p), "status", "--porcelain"],
            capture_output=True, text=True,
        ).stdout.strip()
        dirty = bool(status)
    pkg = _guess_pkg(p)
    langs = _guess_langs(p)
    sections = [f"# Project: {p.name}", f"\n## README\n{readme}"]
    if log:
        sections.append(f"\n## Recent commits\n{log}")
    sections.append(f"\n## Languages\n{', '.join(langs)}")
    blob = "\n".join(sections) + "\n"
    return blob, {
        "name": p.name,
        "path": str(p),
        "package": pkg,
        "languages": langs,
        "dirty": dirty,
        "is_git": is_git,
    }

_HEURISTICS = {
    "py": "python", "ts": "typescript", "tsx": "typescript", "js": "javascript",
    "rs": "rust", "go": "go", "swift": "swift", "kt": "kotlin", "rb": "ruby",
}

def _guess_langs(p: pathlib.Path) -> list[str]:
    seen: dict[str, int] = {}
    for f in p.rglob("*"):
        if not f.is_file() or ".git" in f.parts or "node_modules" in f.parts:
            continue
        if f.suffix.lstrip(".") in _HEURISTICS:
            lang = _HEURISTICS[f.suffix.lstrip(".")]
            seen[lang] = seen.get(lang, 0) + 1
    return [k for k, _ in sorted(seen.items(), key=lambda x: -x[1])][:5]

def _guess_pkg(p: pathlib.Path) -> str | None:
    for f, key in (("pyproject.toml", "project.name"), ("package.json", "name"),
                   ("Cargo.toml", "package.name"), ("go.mod", None)):
        if (p / f).exists():
            return f
    return None