"""The experience pool — one growing store of games (Phase 8 / GSD §3).

Both sources feed the same pool:

- **self-play** — engines grinding games (the ``collect`` step), and
- **human** — users' games (from the viewer / Supabase ``games`` table).

The pool is the substrate the offline trainer learns from. For a *self-play
GA* "learning from the pool" doesn't mean gradient descent on game records — it
means evolution is grounded in the **positions that actually occur**: we sample
opening lines from pooled games and evolve/benchmark from them, so as real human
games accumulate the engine is increasingly tuned to positions players reach.

Layout on disk (default ``training/pool/``)::

    pool/
      manifest.json          # lightweight index (one small entry per game)
      games/g-000001.json    # per-game record: metadata + UCI moves + PGN

The per-game PGN is the language-agnostic artifact (PROJECT_GUIDE.md: PGN for games),
so the same files round-trip to Supabase / the frontend.
"""

from __future__ import annotations

import datetime as _dt
import json
import random
from dataclasses import dataclass, asdict
from pathlib import Path

import chess

from chess_io import game_to_pgn

SOURCES = ("self_play", "human")
DEFAULT_ROOT = Path(__file__).resolve().parent / "pool"


@dataclass
class GameEntry:
    id: str
    source: str
    result: str
    plies: int
    white: str
    black: str
    created_at: str
    file: str


class ExperiencePool:
    """A growing, on-disk pool of games fed by self-play and human play."""

    def __init__(self, root: str | Path = DEFAULT_ROOT) -> None:
        self.root = Path(root)
        self.games_dir = self.root / "games"
        self.manifest_path = self.root / "manifest.json"
        self._index: list[GameEntry] = self._load_index()

    # --- ingest --------------------------------------------------------- #
    def add_board(
        self,
        board: chess.Board,
        source: str = "self_play",
        white: str = "White",
        black: str = "Black",
    ) -> GameEntry:
        """Add a finished game from a :class:`chess.Board` (replays its stack)."""
        if source not in SOURCES:
            raise ValueError(f"source must be one of {SOURCES}, got {source!r}")
        moves = [m.uci() for m in board.move_stack]
        pgn = str(game_to_pgn(board, white_name=white, black_name=black,
                              mode="self_play" if source == "self_play" else "human"))
        return self._write(source, board.result(claim_draw=True), moves, pgn, white, black)

    def add_pgn(self, pgn_text: str, source: str = "human") -> GameEntry:
        """Add a game from raw PGN text (e.g. a human game from the viewer)."""
        if source not in SOURCES:
            raise ValueError(f"source must be one of {SOURCES}, got {source!r}")
        import io
        import chess.pgn

        game = chess.pgn.read_game(io.StringIO(pgn_text))
        if game is None:
            raise ValueError("could not parse PGN")
        board = game.board()
        moves = []
        for move in game.mainline_moves():
            moves.append(move.uci())
            board.push(move)
        white = game.headers.get("White", "White")
        black = game.headers.get("Black", "Black")
        result = game.headers.get("Result", board.result(claim_draw=True))
        return self._write(source, result, moves, pgn_text, white, black)

    # --- query ---------------------------------------------------------- #
    def size(self) -> int:
        return len(self._index)

    def count_by_source(self) -> dict[str, int]:
        counts = {s: 0 for s in SOURCES}
        for e in self._index:
            counts[e.source] = counts.get(e.source, 0) + 1
        return counts

    def sample_openings(self, n: int, plies: int = 8, rng: random.Random | None = None) -> list[list[str]]:
        """Sample up to ``n`` distinct opening lines (first ``plies`` UCI moves).

        Games shorter than ``plies`` are skipped. Returns ``[]`` when the pool
        can't supply any — the caller should then fall back to synthetic
        openings so training still runs on a fresh pool.
        """
        rng = rng or random.Random()
        eligible = [e for e in self._index if e.plies >= plies]
        if not eligible:
            return []
        picks = rng.sample(eligible, min(n, len(eligible)))
        openings: list[list[str]] = []
        seen: set[tuple] = set()
        for entry in picks:
            moves = self._read_moves(entry)[:plies]
            key = tuple(moves)
            if len(moves) == plies and key not in seen:
                seen.add(key)
                openings.append(moves)
        return openings

    def stats(self) -> dict:
        by = self.count_by_source()
        return {
            "total": self.size(),
            "by_source": by,
            "root": str(self.root),
        }

    # --- internals ------------------------------------------------------ #
    def _write(self, source, result, moves, pgn, white, black) -> GameEntry:
        self.games_dir.mkdir(parents=True, exist_ok=True)
        gid = f"g-{self.size() + 1:06d}"
        fname = f"games/{gid}.json"
        entry = GameEntry(
            id=gid, source=source, result=result, plies=len(moves),
            white=white, black=black,
            created_at=_dt.datetime.now().isoformat(timespec="seconds"),
            file=fname,
        )
        record = {**asdict(entry), "moves": moves, "pgn": pgn}
        (self.root / fname).write_text(json.dumps(record), encoding="utf-8")
        self._index.append(entry)
        self._save_index()
        return entry

    def _read_moves(self, entry: GameEntry) -> list[str]:
        data = json.loads((self.root / entry.file).read_text(encoding="utf-8"))
        return data.get("moves", [])

    def _load_index(self) -> list[GameEntry]:
        if not self.manifest_path.exists():
            return []
        data = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        return [GameEntry(**e) for e in data.get("games", [])]

    def _save_index(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        payload = {"games": [asdict(e) for e in self._index]}
        self.manifest_path.write_text(json.dumps(payload), encoding="utf-8")
