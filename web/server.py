"""Local web viewer for the Darwin's Gambit engine (dev tool).

A tiny stdlib-only HTTP server that bridges the browser board to the *real*
Python engine in ``../training``. python-chess is the single source of truth for
rules (legal moves, SAN, game-over); the engine supplies its moves.

This is a LOCAL development viewer — heavy/engine compute runs here on your
machine, never in a Vercel function. The production frontend will instead read
static artifacts (weights.json / PGN). This server just lets you see and play
the engine right now.

Run:
    cd web
    python server.py            # opens http://localhost:8000 in your browser
    python server.py --port 8080 --no-browser
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# Make the engine importable from ../training.
ROOT = Path(__file__).resolve().parent
TRAINING = ROOT.parent / "training"
sys.path.insert(0, str(TRAINING))

import chess  # noqa: E402  (after sys.path tweak)

from engine import (  # noqa: E402
    Engine, evaluate, describe_termination, game_result, is_game_over,
    Genome, DEFAULT_GENOME, NNGenome,
)
from opponent_model import OpponentModel, AdaptiveEngine  # noqa: E402
from experience_pool import ExperiencePool  # noqa: E402

WEB_DIR = ROOT
DEFAULT_DEPTH = 3
MAX_DEPTH = 5  # guard rail so the UI can't ask for an absurd search

# Production: when the frontend is hosted separately (e.g. Vercel) and this
# engine runs as a backend (e.g. Render), the browser makes cross-origin calls.
# Allow them. Default "*" (the API is unauthenticated — it only computes chess
# moves); set DARWIN_CORS_ORIGIN to your site to lock it down. Local play
# (same-origin) is unaffected.
CORS_ORIGIN = os.environ.get("DARWIN_CORS_ORIGIN", "*")

# --- Phase 7: per-user adaptive opponent (Mode F3) ----------------------- #
# The model is per-user and persists between games. In production this is a
# Supabase ``opponent_models`` row; for this local viewer we keep an in-memory
# cache backed by one JSON file per user under web/opponent_models/.
MODELS_DIR = WEB_DIR / "opponent_models"
_MODELS: dict[str, OpponentModel] = {}
# Reentrant: api_adaptive_learn holds the lock and then calls _get_model, which
# also takes it. A plain Lock would self-deadlock there.
_MODELS_LOCK = threading.RLock()


def _safe_user(user: str) -> str:
    """A filesystem-safe filename for a user id (Supabase ids are uuid-ish)."""
    keep = "".join(c if c.isalnum() or c in "-_" else "_" for c in str(user))
    return keep[:64] or "local"


def _get_model(user: str) -> OpponentModel:
    with _MODELS_LOCK:
        if user in _MODELS:
            return _MODELS[user]
        path = MODELS_DIR / f"{_safe_user(user)}.json"
        if path.exists():
            model = OpponentModel.from_dict(json.loads(path.read_text(encoding="utf-8")))
        else:
            model = OpponentModel(user_id=user)
        _MODELS[user] = model
        return model


def _save_model(model: OpponentModel) -> None:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    path = MODELS_DIR / f"{_safe_user(model.user_id)}.json"
    path.write_text(json.dumps(model.to_dict()), encoding="utf-8")


def _adaptive_base() -> tuple[object, int]:
    """The fixed strong base for the adaptive engine: the evolved champion if
    one exists, else the hand-tuned default. The per-user layer sits on top."""
    best = None
    for o in OPPONENTS["by_id"].values():
        if o.get("kind") == "nn" or "genome" not in o:
            continue
        depth = int(o.get("depth", 1))
        if best is None or depth > best[1]:
            best = (Genome.from_vector(o["genome"]), depth)
    if best is None:
        return DEFAULT_GENOME, 3
    genome, depth = best
    return genome, max(2, min(MAX_DEPTH, depth))


def _load_opponents() -> dict:
    """Load the trained difficulty ladder (web/opponents.json), or fall back.

    The fallback ladder uses the hand-tuned default genome so "Play vs Engine"
    still works before any GA run exists — it just isn't *trained* yet. Run
    ``training/make_opponents.py`` to generate the evolved ladder.
    """
    path = WEB_DIR / "opponents.json"
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        by_id = {o["id"]: o for o in data.get("opponents", [])}
        default, trained = data.get("default"), bool(by_id)
    else:
        by_id = {f"depth{d}": {
            "id": f"depth{d}", "label": f"Depth {d}", "depth": d,
            "genome": DEFAULT_GENOME.to_vector(),
            "blurb": "Hand-tuned default weights (no evolved run found yet)."}
            for d in (1, 2, 3, 4)}
        default, trained = "depth3", False

    # Auto-add the evolved neural-net (Phase 6) if its weights are present.
    # Drop a cloud-trained nn_weights.json into web/ and it appears as an opponent.
    nn_path = WEB_DIR / "nn_weights.json"
    if nn_path.exists():
        try:
            nn = json.loads(nn_path.read_text(encoding="utf-8"))
            weights = nn["weights"] if isinstance(nn, dict) else nn
            by_id["neural"] = {
                "id": "neural", "label": "Neural Net (evolved)", "kind": "nn",
                "genome": weights, "depth": 2,
                "blurb": "An evolved neural-net evaluator (Phase 6). Its strength "
                         "reflects how long it trained — replace nn_weights.json with "
                         "a bigger cloud run to make it stronger.",
            }
        except Exception:  # noqa: BLE001 - a bad weights file shouldn't break the app
            pass

    return {"default": default, "by_id": by_id, "trained": trained, "has_nn": "neural" in by_id}


OPPONENTS = _load_opponents()


def _status(board: chess.Board) -> dict:
    """A JSON snapshot of the position the frontend renders from."""
    over = is_game_over(board)
    king_sq = board.king(board.turn) if board.is_check() else None
    return {
        "fen": board.fen(),
        "turn": "white" if board.turn == chess.WHITE else "black",
        "game_over": over,
        "result": game_result(board) if over else None,
        "termination": describe_termination(board),
        "in_check": board.is_check(),
        "check_square": chess.square_name(king_sq) if king_sq is not None else None,
        "last_move": board.peek().uci() if board.move_stack else None,
        # Static eval from White's perspective, centipawns — drives the eval bar.
        "eval": evaluate(board),
    }


class Handler(BaseHTTPRequestHandler):
    # --- low-level helpers ------------------------------------------------- #
    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", CORS_ORIGIN)
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

    def do_OPTIONS(self) -> None:  # noqa: N802 (CORS preflight)
        self.send_response(204)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _send_json(self, obj: dict, status: int = 200) -> None:
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path, content_type: str) -> None:
        try:
            data = path.read_bytes()
        except FileNotFoundError:
            self.send_error(404, "Not found")
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self._cors()
        self.end_headers()
        self.wfile.write(data)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", 0) or 0)
        if not length:
            return {}
        raw = self.rfile.read(length)
        return json.loads(raw or b"{}")

    def _board(self, data: dict) -> chess.Board:
        """Rebuild the board from the *move history*, not just a FEN.

        This is what makes draw-by-repetition work: python-chess detects
        threefold repetition (e.g. perpetual check) by walking the move stack,
        which a FEN alone doesn't carry. The frontend sends every move from the
        start, so we replay them and the full history is preserved. (Falls back
        to a FEN/startpos for the very first request or legality probes.)
        """
        moves = data.get("moves")
        if moves:
            board = chess.Board()
            for uci in moves:
                board.push(chess.Move.from_uci(uci))
            return board
        return chess.Board(data.get("fen") or chess.STARTING_FEN)

    def _depth(self, data: dict) -> int:
        try:
            return max(1, min(MAX_DEPTH, int(data.get("depth", DEFAULT_DEPTH))))
        except (TypeError, ValueError):
            return DEFAULT_DEPTH

    def _engine_for(self, data: dict) -> Engine:
        """Build the engine for an opponent id, or the default at given depth.

        With an ``opponent`` id we play that rung's *evolved* genome at its
        depth (Play vs Trained AI). Without one, we use the hand-tuned default
        at the requested depth (e.g. Watch AI vs AI).
        """
        # Variety: pick among near-best moves so e.g. AI-vs-AI plays a fresh
        # game each run instead of repeating one deterministic line.
        margin = 30 if data.get("variety") else 0
        opp = OPPONENTS["by_id"].get(data.get("opponent"))
        if opp:
            depth = max(1, min(MAX_DEPTH, int(opp.get("depth", DEFAULT_DEPTH))))
            if opp.get("kind") == "nn":
                genome = NNGenome.from_vector(opp["genome"])
            else:
                genome = Genome.from_vector(opp["genome"])
            return Engine(genome=genome, depth=depth,
                          name=opp.get("label", "Trained AI"), random_margin=margin)
        return Engine(depth=self._depth(data), name="Darwin", random_margin=margin)

    # --- routing ----------------------------------------------------------- #
    def do_GET(self) -> None:  # noqa: N802 (http.server API)
        route = self.path.split("?", 1)[0]
        static = {
            "/": (WEB_DIR / "index.html", "text/html; charset=utf-8"),
            "/index.html": (WEB_DIR / "index.html", "text/html; charset=utf-8"),
            "/style.css": (WEB_DIR / "style.css", "text/css; charset=utf-8"),
            "/app.js": (WEB_DIR / "app.js", "application/javascript; charset=utf-8"),
            "/app-config.js": (WEB_DIR / "app-config.js", "application/javascript; charset=utf-8"),
            # Phase 5 auth + storage (Supabase, client-side).
            "/auth.js": (WEB_DIR / "auth.js", "application/javascript; charset=utf-8"),
            "/supabase-config.js": (WEB_DIR / "supabase-config.js", "application/javascript; charset=utf-8"),
            # Phase 3 evolution showcase (static replay of showcase.json).
            "/showcase": (WEB_DIR / "showcase.html", "text/html; charset=utf-8"),
            "/showcase.html": (WEB_DIR / "showcase.html", "text/html; charset=utf-8"),
            "/showcase.css": (WEB_DIR / "showcase.css", "text/css; charset=utf-8"),
            "/showcase.js": (WEB_DIR / "showcase.js", "application/javascript; charset=utf-8"),
            "/showcase.json": (WEB_DIR / "showcase.json", "application/json; charset=utf-8"),
            "/tournament.json": (WEB_DIR / "tournament.json", "application/json; charset=utf-8"),
        }
        if route in static:
            self._send_file(*static[route])
        else:
            self.send_error(404, "Not found")

    def do_POST(self) -> None:  # noqa: N802
        route = self.path.split("?", 1)[0]
        try:
            data = self._read_json()
            if route == "/api/new":
                self._send_json(self.api_new(data))
            elif route == "/api/legal":
                self._send_json(self.api_legal(data))
            elif route == "/api/move":
                self._send_json(self.api_move(data))
            elif route == "/api/engine":
                self._send_json(self.api_engine(data))
            elif route == "/api/opponents":
                self._send_json(self.api_opponents(data))
            elif route == "/api/adaptive_learn":
                self._send_json(self.api_adaptive_learn(data))
            elif route == "/api/adaptive_profile":
                self._send_json(self.api_adaptive_profile(data))
            elif route == "/api/pool_add":
                self._send_json(self.api_pool_add(data))
            else:
                self.send_error(404, "Not found")
        except Exception as exc:  # noqa: BLE001 - report errors as JSON to the UI
            self._send_json({"error": str(exc)}, status=400)

    # --- API methods ------------------------------------------------------- #
    def api_new(self, data: dict) -> dict:
        board = chess.Board()
        return {"ok": True, **_status(board)}

    def api_legal(self, data: dict) -> dict:
        """Legal destination squares from a given square (for highlighting)."""
        board = self._board(data)
        square = data.get("square")
        targets = []
        if square:
            from_sq = chess.parse_square(square)
            for move in board.legal_moves:
                if move.from_square == from_sq:
                    targets.append(
                        {
                            "to": chess.square_name(move.to_square),
                            "promotion": move.promotion is not None,
                            "capture": board.is_capture(move),
                        }
                    )
        return {"ok": True, "square": square, "targets": targets}

    def api_move(self, data: dict) -> dict:
        """Apply a human move (UCI like 'e2e4' or 'e7e8q')."""
        board = self._board(data)
        move = chess.Move.from_uci(data["uci"])
        if move not in board.legal_moves:
            return {"ok": False, "error": "illegal move", **_status(board)}
        san = board.san(move)
        board.push(move)
        return {"ok": True, "san": san, "uci": move.uci(), **_status(board)}

    def api_opponents(self, data: dict) -> dict:
        """The difficulty ladder for the UI (without the raw genome vectors)."""
        opps = [
            {"id": o["id"], "label": o["label"], "depth": o.get("depth"),
             "blurb": o.get("blurb", "")}
            for o in OPPONENTS["by_id"].values()
        ]
        return {"ok": True, "default": OPPONENTS["default"],
                "trained": OPPONENTS["trained"], "opponents": opps}

    def api_adaptive_move(self, data: dict, board: chess.Board) -> dict:
        """Mode F3: the fixed-strong base engine + this user's exploit layer."""
        user = str(data.get("user") or "local")
        model = _get_model(user)
        genome, depth = _adaptive_base()
        engine = AdaptiveEngine(model, genome=genome, depth=depth)
        move = engine.select_move(board)
        if move is None:
            return {"ok": False, "error": "no move", **_status(board)}
        san = board.san(move)
        board.push(move)
        return {
            "ok": True, "san": san, "uci": move.uci(), "depth": depth,
            "adaptive": True, "profile": model.summary(), **_status(board),
        }

    def api_adaptive_learn(self, data: dict) -> dict:
        """Fold a finished game into the user's model (call once per game end)."""
        user = str(data.get("user") or "local")
        moves = [chess.Move.from_uci(u) for u in data.get("moves", [])]
        user_color = chess.WHITE if data.get("user_color", "white") == "white" else chess.BLACK
        with _MODELS_LOCK:
            model = _get_model(user)
            model.observe_game(moves, user_color)
            _save_model(model)
        return {"ok": True, "profile": model.summary()}

    def api_adaptive_profile(self, data: dict) -> dict:
        """The user's current opponent-model summary (for the UI)."""
        user = str(data.get("user") or "local")
        return {"ok": True, "profile": _get_model(user).summary()}

    def api_pool_add(self, data: dict) -> dict:
        """Add a finished human game to the experience pool (GSD §3).

        Closes the loop: human play feeds the same pool the offline pipeline
        (training/pipeline.py) later trains on. Best-effort and never required
        for play to work.
        """
        moves = data.get("moves") or []
        if not moves:
            return {"ok": False, "error": "no moves"}
        board = chess.Board()
        for uci in moves:
            board.push(chess.Move.from_uci(uci))
        pool = ExperiencePool()  # default root: training/pool
        entry = pool.add_board(
            board, source="human",
            white=str(data.get("white", "You")),
            black=str(data.get("black", "Engine")),
        )
        return {"ok": True, "id": entry.id, "pool_size": pool.size()}

    def api_engine(self, data: dict) -> dict:
        """Ask the engine for its move in the given position."""
        board = self._board(data)
        if is_game_over(board):
            return {"ok": False, "error": "game over", **_status(board)}
        if data.get("adaptive"):
            return self.api_adaptive_move(data, board)
        engine = self._engine_for(data)
        result = engine.analyse(board)
        if result.move is None:
            return {"ok": False, "error": "no move", **_status(board)}
        san = board.san(result.move)
        board.push(result.move)
        return {
            "ok": True,
            "san": san,
            "uci": result.move.uci(),
            "depth": result.depth,
            "nodes": result.nodes,
            **_status(board),
        }

    # Quieter console: one concise line per request.
    def log_message(self, fmt: str, *args) -> None:  # noqa: A002
        sys.stderr.write("  %s\n" % (fmt % args))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Darwin's Gambit web viewer / engine API")
    # In production (Render etc.) PORT/HOST come from the environment; locally
    # they default to a browser-friendly localhost:8000.
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8000)))
    parser.add_argument("--host", default=os.environ.get("HOST", "localhost"))
    parser.add_argument("--no-browser", action="store_true", help="don't auto-open the browser")
    args = parser.parse_args(argv)

    # A hosted backend binds 0.0.0.0 and must not try to open a browser.
    hosted = "PORT" in os.environ
    host = "0.0.0.0" if hosted else args.host

    server = ThreadingHTTPServer((host, args.port), Handler)
    url = f"http://{host}:{args.port}"
    print(f"Darwin's Gambit running at {url}  (CORS origin: {CORS_ORIGIN})")
    print("Press Ctrl+C to stop.")

    if not args.no_browser and not hosted:
        threading.Timer(0.6, lambda: webbrowser.open(f"http://localhost:{args.port}")).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
