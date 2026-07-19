from __future__ import annotations
import os, tomllib, pathlib, dataclasses

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_STATE_DIR = ROOT / ".me-kg"
DEFAULT_VAULT = ROOT / "notes"

@dataclasses.dataclass
class Config:
    vault_dir: pathlib.Path = DEFAULT_VAULT
    state_dir: pathlib.Path = DEFAULT_STATE_DIR
    zen_endpoint: str = "https://opencode.ai/zen/v1/chat/completions"
    primary_model: str = "big-pickle"
    fallback_model: str = "deepseek-v4-flash-free"
    auto_commit: bool = True
    private_mode: bool = False

    @classmethod
    def load(cls, path: pathlib.Path | None = None) -> "Config":
        cfg = cls()
        path = path or (ROOT / "me-kg.toml")
        if path.exists():
            data = tomllib.loads(path.read_text())
            for k, v in data.get("me-kg", {}).items():
                if k in ("vault_dir", "state_dir"):
                    setattr(cfg, k, pathlib.Path(v).expanduser())
                else:
                    setattr(cfg, k, v)
        if not os.environ.get("ZEN_API_KEY"):
            import warnings
            warnings.warn("ZEN_API_KEY not set — agent commands will fail; rebuild/graph still work.")
        cfg.vault_dir.mkdir(parents=True, exist_ok=True)
        cfg.state_dir.mkdir(parents=True, exist_ok=True)
        for sub in ("papers", "projects", "notes", "ideas", "people", "concepts", "tags"):
            (cfg.vault_dir / sub).mkdir(exist_ok=True)
        return cfg