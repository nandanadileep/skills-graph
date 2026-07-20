from __future__ import annotations
import os, re, json, httpx
from typing import Any
from ..config import Config

JSON_INSTRUCTION = (
    "Respond with ONLY a single JSON object, no markdown fences, no prose. "
    "The object MUST validate against this schema:\n{s}"
)

def _messages(system: str, user: str) -> list[dict[str, str]]:
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]

def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object found in model output")
    return json.loads(text[start : end + 1])

class Agent:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        if "ZEN_API_KEY" not in os.environ:
            raise RuntimeError("ZEN_API_KEY not set")
        self.key = os.environ["ZEN_API_KEY"]

    def complete(self, system: str, user: str, *, json_mode: bool = True, model: str | None = None) -> str:
        model = model or self.cfg.primary_model
        headers = {"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"}
        body = {
            "model": model,
            "messages": _messages(system, user),
            "temperature": 0.2,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        with httpx.Client(timeout=httpx.Timeout(300.0, connect=10.0)) as c:
            r = c.post(self.cfg.zen_endpoint, headers=headers, json=body)
            r.raise_for_status()
            data = r.json()
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as e:
            raise RuntimeError(f"unexpected zen response: {data}") from e

    def extract(self, system: str, user: str) -> dict:
        from rich import print as rprint
        import time
        last = None
        for model in (self.cfg.primary_model, self.cfg.fallback_model):
            t0 = time.time()
            rprint(f"[dim]agent: calling {model}...[/]")
            try:
                raw = self.complete(system, user, json_mode=True, model=model)
                rprint(f"[dim]agent: {model} returned in {time.time()-t0:.0f}s[/]")
                return _extract_json(raw)
            except Exception as e:
                rprint(f"[dim]agent: {model} failed: {e!r}[/]")
                last = e
        raise RuntimeError(f"agent extraction failed: {last}")