"""Engine version registry — the "deploy stronger engines" half of the loop.

Phase 8 closes the continual loop: ``collect -> train -> deploy -> repeat``.
Training only *promotes* a candidate to a new deployed version when it beats the
incumbent by a real margin (gating in ``pipeline.py``), so the deployed strength
is monotonic and honest — no noisy regressions. This is the local mirror of the
TRD ``engine_versions`` table.

Layout (``training/deployed/``)::

    deployed/
      registry.json          # {current: N, versions: [ {version, kind, vector,
                             #  benchmark_winrate, source_games, created_at}, ...]}

The current champion is ``versions[current-1]``. ``current == 0`` means nothing
has been deployed yet, and callers fall back to the hand-tuned default.
"""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path

from engine import Genome, NNGenome, DEFAULT_GENOME

DEFAULT_ROOT = Path(__file__).resolve().parent / "deployed"


def _registry_path(root: Path) -> Path:
    return Path(root) / "registry.json"


def load_registry(root: str | Path = DEFAULT_ROOT) -> dict:
    path = _registry_path(Path(root))
    if not path.exists():
        return {"current": 0, "versions": []}
    return json.loads(path.read_text(encoding="utf-8"))


def current_champion(root: str | Path = DEFAULT_ROOT) -> dict | None:
    """The currently deployed version entry, or ``None`` if nothing deployed."""
    reg = load_registry(root)
    cur = reg.get("current", 0)
    if cur <= 0 or cur > len(reg["versions"]):
        return None
    return reg["versions"][cur - 1]


def current_genome(root: str | Path = DEFAULT_ROOT, kind: str = "scalar"):
    """Reconstruct the deployed champion genome, or the hand-tuned default.

    Returns ``(genome, kind)``. With nothing deployed, returns the default
    scalar genome (or a request for the given ``kind`` is honoured only by the
    deployed entry; a fresh pool starts from the default scalar baseline).
    """
    champ = current_champion(root)
    if champ is None:
        return DEFAULT_GENOME, "scalar"
    k = champ.get("kind", "scalar")
    genome = NNGenome.from_vector(champ["vector"]) if k == "nn" else Genome.from_vector(champ["vector"])
    return genome, k


def promote(
    root: str | Path,
    kind: str,
    vector: list,
    benchmark_winrate: float,
    vs_incumbent: float,
    source_games: int,
    notes: str = "",
) -> dict:
    """Append a new deployed version and make it current. Returns its entry."""
    root = Path(root)
    reg = load_registry(root)
    version = len(reg["versions"]) + 1
    entry = {
        "version": version,
        "kind": kind,
        "vector": list(vector),
        "benchmark_winrate": round(float(benchmark_winrate), 4),  # vs the fixed default
        "vs_incumbent": round(float(vs_incumbent), 4),            # vs the previous champion
        "source_games": int(source_games),
        "created_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "notes": notes,
    }
    reg["versions"].append(entry)
    reg["current"] = version
    root.mkdir(parents=True, exist_ok=True)
    _registry_path(root).write_text(json.dumps(reg, indent=2), encoding="utf-8")
    return entry
