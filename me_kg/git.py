from __future__ import annotations
import subprocess, pathlib
from .config import Config

def commit(cfg: Config, paths: list[pathlib.Path], message: str) -> None:
    if not cfg.auto_commit:
        return
    root = cfg.vault_dir.parent
    subprocess.run(["git", "-C", str(root), "add", "--", *(str(p) for p in paths)], check=False)
    subprocess.run(["git", "-C", str(root), "commit", "-m", message], check=False)
    subprocess.run(["git", "-C", str(root), "push"], check=False)