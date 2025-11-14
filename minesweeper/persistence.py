from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple
import os

try:
    from google.cloud import firestore  # type: ignore
except Exception:  # pragma: no cover
    firestore = None  # type: ignore

from .game_engine import (
    GameState,
    generate_new_game,
    apply_reveal as engine_reveal,
    apply_flag as engine_flag,
    to_client_view,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _seq_id(n: int) -> str:
    return f"{n:06d}"


def _to_state(doc: Dict[str, Any]) -> GameState:
    return GameState(
        width=doc["board_width"],
        height=doc["board_height"],
        num_mines=doc["num_mines"],
        mine_layout=doc["mine_layout"],
        revealed_mask=doc["revealed_mask"],
        flag_mask=doc["flag_mask"],
        status=doc["status"],
        moves_count=doc.get("moves_count", 0),
        mines_placed=doc.get("mines_placed", False),
        rng_seed=doc.get("rng_seed"),
    )


def _count_flags(mask: str) -> int:
    return mask.count("1")


def _count_revealed(mask: str) -> int:
    return mask.count("1")


class InMemoryPersistence:
    """Simple in-memory persistence for tests and local dev."""

    def __init__(self) -> None:
        self.games: Dict[str, Dict[str, Any]] = {}
        self.moves: Dict[str, list[Dict[str, Any]]] = {}
        self.stats_totals: Dict[str, Dict[str, Any]] = {}
        self.stats_by_option: Dict[str, Dict[str, Dict[str, Any]]] = {}

    def _ensure_user(self, user_id: str) -> None:
        if user_id not in self.moves:
            self.moves[user_id] = []

    def _stats_key(self, width: int, height: int, num_mines: int) -> str:
        return f"{width}x{height}x{num_mines}"

    def _ensure_stats(self, user_id: str) -> None:
        if user_id not in self.stats_totals:
            self.stats_totals[user_id] = {"played": 0, "wins": 0, "losses": 0, "aborts": 0}
        if user_id not in self.stats_by_option:
            self.stats_by_option[user_id] = {}

    def _update_stats(self, user_id: str, game: Dict[str, Any], outcome: str) -> None:
        width = int(game["board_width"])
        height = int(game["board_height"])
        num_mines = int(game["num_mines"])
        key = self._stats_key(width, height, num_mines)
        self._ensure_stats(user_id)
        totals = self.stats_totals[user_id]
        options = self.stats_by_option[user_id]
        option = options.get(key)
        if option is None:
            option = {
                "board_width": width,
                "board_height": height,
                "num_mines": num_mines,
                "played": 0,
                "wins": 0,
                "losses": 0,
                "aborts": 0,
            }
            options[key] = option
        totals["played"] = int(totals.get("played", 0)) + 1
        option["played"] = int(option.get("played", 0)) + 1
        if outcome == "win":
            totals["wins"] = int(totals.get("wins", 0)) + 1
            option["wins"] = int(option.get("wins", 0)) + 1
        elif outcome == "loss":
            totals["losses"] = int(totals.get("losses", 0)) + 1
            option["losses"] = int(option.get("losses", 0)) + 1
        elif outcome == "abort":
            totals["aborts"] = int(totals.get("aborts", 0)) + 1
            option["aborts"] = int(option.get("aborts", 0)) + 1

    def get_game(self, user_id: str) -> Optional[Dict[str, Any]]:
        return self.games.get(user_id)

    def start_game(
        self,
        user_id: str,
        width: int,
        height: int,
        num_mines: int,
        rng_seed: Optional[int] = None,
    ) -> Dict[str, Any]:
        existing = self.games.get(user_id)
        if existing and existing.get("status") == "active":
            raise ValueError("active_game_exists")

        state = generate_new_game(width, height, num_mines, rng_seed=rng_seed)
        now = _now()
        doc = {
            "status": state.status,
            "created_at": now,
            "updated_at": now,
            "finished_at": None,
            "board_width": width,
            "board_height": height,
            "num_mines": num_mines,
            "moves_count": 0,
            "mine_layout": state.mine_layout,
            "revealed_mask": state.revealed_mask,
            "flag_mask": state.flag_mask,
            "mines_placed": state.mines_placed,
            "rng_seed": state.rng_seed,
            "first_reveal_at": None,
            "result_time_ms": None,
            "final_score": None,
            "end_result": None,
        }
        self.games[user_id] = doc
        self.moves[user_id] = []
        return doc

    def _append_move(self, user_id: str, game: Dict[str, Any], move: Dict[str, Any]) -> None:
        self._ensure_user(user_id)
        self.moves[user_id].append(move)

    def reveal(self, user_id: str, row: int, col: int) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        game = self.games.get(user_id)
        if not game:
            raise KeyError("game_not_found")
        if game["status"] != "active":
            # still log a no-op move
            now = _now()
            last_ts = self.moves[user_id][-1]["timestamp"] if self.moves.get(user_id) else game["created_at"]
            move = {
                "seq": (game.get("moves_count", 0) + 1),
                "action": "reveal",
                "row": row,
                "col": col,
                "timestamp": now,
                "hit_mine": False,
                "cleared_cells": 0,
                "flags_total": _count_flags(game["flag_mask"]),
                "revealed_total": _count_revealed(game["revealed_mask"]),
                "status_after": game["status"],
                "ms_since_game_start": int((now - (game.get("first_reveal_at") or game["created_at"])).total_seconds() * 1000) if game.get("first_reveal_at") else None,
                "ms_since_prev_move": int((now - last_ts).total_seconds() * 1000) if last_ts else None,
            }
            self._append_move(user_id, game, move)
            game["updated_at"] = now
            return game, move

        s = _to_state(game)
        new_state, result = engine_reveal(s, row, col)
        now = _now()
        # update doc
        game["revealed_mask"] = new_state.revealed_mask
        game["status"] = new_state.status
        game["mine_layout"] = new_state.mine_layout
        game["mines_placed"] = new_state.mines_placed
        game["moves_count"] = new_state.moves_count
        game["updated_at"] = now
        if game.get("first_reveal_at") is None and result.get("cleared_cells", 0) > 0:
            game["first_reveal_at"] = now
        finishing_now = False
        if new_state.status in ("won", "lost") and game.get("finished_at") is None:
            finishing_now = True
            game["finished_at"] = now
            if game.get("first_reveal_at"):
                game["result_time_ms"] = int((now - game["first_reveal_at"]).total_seconds() * 1000)
            game["end_result"] = "win" if new_state.status == "won" else "lose"
        if finishing_now:
            outcome = "win" if new_state.status == "won" else "loss"
            self._update_stats(user_id, game, outcome)

        last_ts = self.moves[user_id][-1]["timestamp"] if self.moves.get(user_id) else game["created_at"]
        move = {
            "seq": (game.get("moves_count", 0) + 1),
            "action": "reveal",
            "row": row,
            "col": col,
            "timestamp": now,
            "hit_mine": result["hit_mine"],
            "cleared_cells": result["cleared_cells"],
            "flags_total": result["flags_total"],
            "revealed_total": result["revealed_total"],
            "status_after": result["status_after"],
            "ms_since_game_start": int((now - (game.get("first_reveal_at") or now)).total_seconds() * 1000) if game.get("first_reveal_at") else None,
            "ms_since_prev_move": int((now - last_ts).total_seconds() * 1000) if last_ts else None,
        }
        self._append_move(user_id, game, move)
        return game, move

    def mark_error(self, user_id: str, reason: str) -> Dict[str, Any]:
        game = self.games.get(user_id)
        if not game:
            raise KeyError("game_not_found")
        now = _now()
        game["status"] = "error"
        game["updated_at"] = now
        if not game.get("finished_at"):
            game["finished_at"] = now
        game["end_result"] = "error"
        last_ts = self.moves[user_id][-1]["timestamp"] if self.moves.get(user_id) else game["created_at"]
        move = {
            "seq": (game.get("moves_count", 0) + 1),
            "action": "error",
            "row": None,
            "col": None,
            "timestamp": now,
            "hit_mine": False,
            "cleared_cells": 0,
            "flags_total": _count_flags(game["flag_mask"]),
            "revealed_total": _count_revealed(game["revealed_mask"]),
            "status_after": game["status"],
            "ms_since_game_start": int((now - (game.get("first_reveal_at") or now)).total_seconds() * 1000) if game.get("first_reveal_at") else None,
            "ms_since_prev_move": int((now - last_ts).total_seconds() * 1000) if last_ts else None,
            "error_reason": reason,
        }
        self._append_move(user_id, game, move)
        return game

    def flag(self, user_id: str, row: int, col: int) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        game = self.games.get(user_id)
        if not game:
            raise KeyError("game_not_found")
        s = _to_state(game)
        new_state, result = engine_flag(s, row, col)
        now = _now()
        game["flag_mask"] = new_state.flag_mask
        game["status"] = new_state.status
        game["moves_count"] = new_state.moves_count
        game["updated_at"] = now

        last_ts = self.moves[user_id][-1]["timestamp"] if self.moves.get(user_id) else game["created_at"]
        move = {
            "seq": (game.get("moves_count", 0) + 1),
            "action": "flag",
            "row": row,
            "col": col,
            "timestamp": now,
            "hit_mine": False,
            "cleared_cells": 0,
            "flags_total": result["flags_total"],
            "revealed_total": result["revealed_total"],
            "status_after": result["status_after"],
            "ms_since_game_start": int((now - (game.get("first_reveal_at") or now)).total_seconds() * 1000) if game.get("first_reveal_at") else None,
            "ms_since_prev_move": int((now - last_ts).total_seconds() * 1000) if last_ts else None,
        }
        self._append_move(user_id, game, move)
        return game, move

    def abandon(self, user_id: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        game = self.games.get(user_id)
        if not game:
            raise KeyError("game_not_found")
        now = _now()
        game["status"] = "abandoned"
        game["updated_at"] = now
        finishing_now = not game.get("finished_at")
        if finishing_now:
            game["finished_at"] = now
        game["end_result"] = "abort"
        if finishing_now:
            self._update_stats(user_id, game, "abort")
        last_ts = self.moves[user_id][-1]["timestamp"] if self.moves.get(user_id) else game["created_at"]
        move = {
            "seq": (game.get("moves_count", 0) + 1),
            "action": "abandon",
            "row": None,
            "col": None,
            "timestamp": now,
            "hit_mine": False,
            "cleared_cells": 0,
            "flags_total": _count_flags(game["flag_mask"]),
            "revealed_total": _count_revealed(game["revealed_mask"]),
            "status_after": game["status"],
            "ms_since_game_start": int((now - (game.get("first_reveal_at") or now)).total_seconds() * 1000) if game.get("first_reveal_at") else None,
            "ms_since_prev_move": int((now - last_ts).total_seconds() * 1000) if last_ts else None,
        }
        self._append_move(user_id, game, move)
        return game, move

    def get_stats(self, user_id: str) -> Dict[str, Any]:
        totals = self.stats_totals.get(user_id)
        if totals is None:
            totals = {"played": 0, "wins": 0, "losses": 0, "aborts": 0}
        wins = int(totals.get("wins", 0) or 0)
        losses = int(totals.get("losses", 0) or 0)
        aborts = int(totals.get("aborts", 0) or 0)
        played = int(totals.get("played", 0) or 0)
        denom = wins + losses + aborts
        win_pct = float(wins) / denom if denom > 0 else 0.0
        by_option_map = self.stats_by_option.get(user_id) or {}
        by_option_list = []
        for key, opt in by_option_map.items():
            owins = int(opt.get("wins", 0) or 0)
            olosses = int(opt.get("losses", 0) or 0)
            oaborts = int(opt.get("aborts", 0) or 0)
            oplayed = int(opt.get("played", 0) or 0)
            o_denom = owins + olosses + oaborts
            o_win_pct = float(owins) / o_denom if o_denom > 0 else 0.0
            by_option_list.append(
                {
                    "key": key,
                    "board_width": int(opt.get("board_width", 0) or 0),
                    "board_height": int(opt.get("board_height", 0) or 0),
                    "num_mines": int(opt.get("num_mines", 0) or 0),
                    "played": oplayed,
                    "wins": owins,
                    "losses": olosses,
                    "aborts": oaborts,
                    "winPct": o_win_pct,
                }
            )
        return {
            "totals": {
                "played": played,
                "wins": wins,
                "losses": losses,
                "aborts": aborts,
                "winPct": win_pct,
            },
            "byOption": by_option_list,
        }

    def to_client(self, game: Dict[str, Any]) -> Dict[str, Any]:
        s = _to_state(game)
        board = to_client_view(s)
        return {
            "status": game["status"],
            "board": board,
            "board_width": game["board_width"],
            "board_height": game["board_height"],
            "moves_count": game.get("moves_count", 0),
            "flags_total": _count_flags(game["flag_mask"]),
            "revealed_total": _count_revealed(game["revealed_mask"]),
            "num_mines": game["num_mines"],
            "end_result": game.get("end_result"),
        }


class FirestorePersistence:
    """Firestore-backed persistence using Native mode.

    Uses FIRESTORE_EMULATOR_HOST if present; otherwise connects to production.
    """

    def __init__(self, client: Optional[Any] = None) -> None:
        if client is not None:
            self.client = client
        else:
            if firestore is None:
                raise RuntimeError("google-cloud-firestore not available")
            self.client = firestore.Client(project=os.environ.get("GOOGLE_CLOUD_PROJECT"))

    def _game_ref(self, user_id: str):
        return self.client.collection("minesweeperGames").document(user_id)

    def _moves_ref(self, user_id: str):
        return self._game_ref(user_id).collection("moves")

    def _stats_ref(self, user_id: str):
        return self.client.collection("minesweeperStats").document(user_id)

    def _stats_option_ref(self, user_id: str, key: str):
        return self._stats_ref(user_id).collection("byOption").document(key)

    def _stats_key(self, width: int, height: int, num_mines: int) -> str:
        return f"{width}x{height}x{num_mines}"

    def _update_stats_tx(self, tx, user_id: str, game: Dict[str, Any], outcome: str, now: datetime) -> None:
        width = int(game.get("board_width"))
        height = int(game.get("board_height"))
        num_mines = int(game.get("num_mines"))
        key = self._stats_key(width, height, num_mines)
        sref = self._stats_ref(user_id)
        totals_update: Dict[str, Any] = {
            "played": firestore.Increment(1),
            "updated_at": now,
        }
        if outcome == "win":
            totals_update["wins"] = firestore.Increment(1)
        elif outcome == "loss":
            totals_update["losses"] = firestore.Increment(1)
        elif outcome == "abort":
            totals_update["aborts"] = firestore.Increment(1)
        tx.set(sref, totals_update, merge=True)
        oref = self._stats_option_ref(user_id, key)
        option_update: Dict[str, Any] = {
            "board_width": width,
            "board_height": height,
            "num_mines": num_mines,
            "played": firestore.Increment(1),
            "updated_at": now,
        }
        if outcome == "win":
            option_update["wins"] = firestore.Increment(1)
        elif outcome == "loss":
            option_update["losses"] = firestore.Increment(1)
        elif outcome == "abort":
            option_update["aborts"] = firestore.Increment(1)
        tx.set(oref, option_update, merge=True)

    def get_game(self, user_id: str) -> Optional[Dict[str, Any]]:
        doc = self._game_ref(user_id).get()
        if not doc.exists:
            return None
        data = doc.to_dict()
        return data

    def start_game(
        self,
        user_id: str,
        width: int,
        height: int,
        num_mines: int,
        rng_seed: Optional[int] = None,
    ) -> Dict[str, Any]:
        @firestore.transactional
        def _tx(tx):  # type: ignore
            gref = self._game_ref(user_id)
            snap = gref.get(transaction=tx)
            if snap.exists:
                data = snap.to_dict()
                if data and data.get("status") == "active":
                    raise ValueError("active_game_exists")
            state = generate_new_game(width, height, num_mines, rng_seed=rng_seed)
            now = _now()
            doc = {
                "status": state.status,
                "created_at": now,
                "updated_at": now,
                "finished_at": None,
                "board_width": width,
                "board_height": height,
                "num_mines": num_mines,
                "moves_count": 0,
                "mine_layout": state.mine_layout,
                "revealed_mask": state.revealed_mask,
                "flag_mask": state.flag_mask,
                "mines_placed": state.mines_placed,
                "rng_seed": state.rng_seed,
                "first_reveal_at": None,
                "result_time_ms": None,
                "final_score": None,
                "end_result": None,
            }
            tx.set(gref, doc)
            # Optionally clear moves: Firestore doesn't support list, so delete all docs in subcollection lazily in client if needed.
            return doc

        return _tx(self.client.transaction())

    def mark_error(self, user_id: str, reason: str) -> Dict[str, Any]:
        if firestore is None:
            raise RuntimeError("google-cloud-firestore not available")

        @firestore.transactional  # type: ignore
        def _tx(tx):
            gref = self._game_ref(user_id)
            snap = gref.get(transaction=tx)
            if not snap.exists:
                raise KeyError("game_not_found")
            game = snap.to_dict()
            assert game is not None
            now = _now()
            update = {
                "status": "error",
                "updated_at": now,
                "end_result": "error",
            }
            if not game.get("finished_at"):
                update["finished_at"] = now
            tx.update(gref, update)
            moves_count = int(game.get("moves_count", 0)) + 1
            last_ts = game.get("updated_at") or game.get("created_at")
            move = {
                "seq": moves_count,
                "action": "error",
                "row": None,
                "col": None,
                "timestamp": now,
                "hit_mine": False,
                "cleared_cells": 0,
                "flags_total": _count_flags(game["flag_mask"]),
                "revealed_total": _count_revealed(game["revealed_mask"]),
                "status_after": "error",
                "ms_since_game_start": int((now - (game.get("first_reveal_at") or now)).total_seconds() * 1000) if game.get("first_reveal_at") else None,
                "ms_since_prev_move": int((now - last_ts).total_seconds() * 1000) if last_ts else None,
                "error_reason": reason,
            }
            self._write_move(tx, user_id, game, move)
            merged = dict(game)
            merged.update(update)
            merged["moves_count"] = moves_count
            return merged

        return _tx(self.client.transaction())

    def _write_move(self, tx, user_id: str, game: Dict[str, Any], move: Dict[str, Any]) -> None:
        seq = int(move["seq"])
        mref = self._moves_ref(user_id).document(_seq_id(seq))
        tx.set(mref, move)

    def reveal(self, user_id: str, row: int, col: int) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        if firestore is None:
            raise RuntimeError("google-cloud-firestore not available")

        @firestore.transactional  # type: ignore
        def _tx(tx):
            gref = self._game_ref(user_id)
            snap = gref.get(transaction=tx)
            if not snap.exists:
                raise KeyError("game_not_found")
            game = snap.to_dict()
            assert game is not None
            s = _to_state(game)
            new_state, result = engine_reveal(s, row, col)
            now = _now()
            update: Dict[str, Any] = {
                "revealed_mask": new_state.revealed_mask,
                "status": new_state.status,
                "updated_at": now,
                "moves_count": new_state.moves_count,
            }
            if game.get("first_reveal_at") is None and result.get("cleared_cells", 0) > 0:
                update["first_reveal_at"] = now
            finishing_now = False
            if new_state.status in ("won", "lost") and not game.get("finished_at"):
                finishing_now = True
                update["finished_at"] = now
                if game.get("first_reveal_at"):
                    update["result_time_ms"] = int((now - game["first_reveal_at"]).total_seconds() * 1000)
                update["end_result"] = "win" if new_state.status == "won" else "lose"
            # reflect mines placement changes
            update["mine_layout"] = new_state.mine_layout
            update["mines_placed"] = new_state.mines_placed

            tx.update(gref, update)

            # Build move doc (use action sequence independent of engine moves_count)
            moves_count = int(game.get("moves_count", 0)) + 1
            last_ts = game.get("updated_at") or game.get("created_at")
            move = {
                "seq": moves_count,
                "action": "reveal",
                "row": row,
                "col": col,
                "timestamp": now,
                "hit_mine": result["hit_mine"],
                "cleared_cells": result["cleared_cells"],
                "flags_total": result["flags_total"],
                "revealed_total": result["revealed_total"],
                "status_after": result["status_after"],
                "ms_since_game_start": int((now - (game.get("first_reveal_at") or now)).total_seconds() * 1000) if game.get("first_reveal_at") else None,
                "ms_since_prev_move": int((now - last_ts).total_seconds() * 1000) if last_ts else None,
            }
            self._write_move(tx, user_id, game, move)
            # Compose in-memory view for response
            merged = dict(game)
            merged.update(update)
            merged["moves_count"] = new_state.moves_count
            if finishing_now:
                outcome = "win" if new_state.status == "won" else "loss"
                self._update_stats_tx(tx, user_id, merged, outcome, now)
            return merged, move

        return _tx(self.client.transaction())

    def flag(self, user_id: str, row: int, col: int) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        if firestore is None:
            raise RuntimeError("google-cloud-firestore not available")

        @firestore.transactional  # type: ignore
        def _tx(tx):
            gref = self._game_ref(user_id)
            snap = gref.get(transaction=tx)
            if not snap.exists:
                raise KeyError("game_not_found")
            game = snap.to_dict()
            assert game is not None
            s = _to_state(game)
            new_state, result = engine_flag(s, row, col)
            now = _now()
            update: Dict[str, Any] = {
                "flag_mask": new_state.flag_mask,
                "status": new_state.status,
                "updated_at": now,
                "moves_count": new_state.moves_count,
            }
            tx.update(gref, update)
            moves_count = int(game.get("moves_count", 0)) + 1
            last_ts = game.get("updated_at") or game.get("created_at")
            move = {
                "seq": moves_count,
                "action": "flag",
                "row": row,
                "col": col,
                "timestamp": now,
                "hit_mine": False,
                "cleared_cells": 0,
                "flags_total": result["flags_total"],
                "revealed_total": result["revealed_total"],
                "status_after": result["status_after"],
                "ms_since_game_start": int((now - (game.get("first_reveal_at") or now)).total_seconds() * 1000) if game.get("first_reveal_at") else None,
                "ms_since_prev_move": int((now - last_ts).total_seconds() * 1000) if last_ts else None,
            }
            self._write_move(tx, user_id, game, move)
            merged = dict(game)
            merged.update(update)
            merged["moves_count"] = new_state.moves_count
            return merged, move

        return _tx(self.client.transaction())

    def abandon(self, user_id: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        if firestore is None:
            raise RuntimeError("google-cloud-firestore not available")

        @firestore.transactional  # type: ignore
        def _tx(tx):
            gref = self._game_ref(user_id)
            snap = gref.get(transaction=tx)
            if not snap.exists:
                raise KeyError("game_not_found")
            game = snap.to_dict()
            assert game is not None
            now = _now()
            update = {
                "status": "abandoned",
                "updated_at": now,
            }
            finishing_now = not game.get("finished_at")
            if finishing_now:
                update["finished_at"] = now
            update["end_result"] = "abort"
            tx.update(gref, update)
            moves_count = int(game.get("moves_count", 0)) + 1
            last_ts = game.get("updated_at") or game.get("created_at")
            move = {
                "seq": moves_count,
                "action": "abandon",
                "row": None,
                "col": None,
                "timestamp": now,
                "hit_mine": False,
                "cleared_cells": 0,
                "flags_total": _count_flags(game["flag_mask"]),
                "revealed_total": _count_revealed(game["revealed_mask"]),
                "status_after": "abandoned",
                "ms_since_game_start": int((now - (game.get("first_reveal_at") or now)).total_seconds() * 1000) if game.get("first_reveal_at") else None,
                "ms_since_prev_move": int((now - last_ts).total_seconds() * 1000) if last_ts else None,
            }
            self._write_move(tx, user_id, game, move)
            merged = dict(game)
            merged.update(update)
            merged["moves_count"] = moves_count
            if finishing_now:
                self._update_stats_tx(tx, user_id, merged, "abort", now)
            return merged, move

        return _tx(self.client.transaction())

    def get_stats(self, user_id: str) -> Dict[str, Any]:
        sref = self._stats_ref(user_id)
        snap = sref.get()
        if snap.exists:
            data = snap.to_dict() or {}
        else:
            data = {}
        played = int(data.get("played", 0) or 0)
        wins = int(data.get("wins", 0) or 0)
        losses = int(data.get("losses", 0) or 0)
        aborts = int(data.get("aborts", 0) or 0)
        denom = wins + losses + aborts
        win_pct = float(wins) / denom if denom > 0 else 0.0
        by_option_list: list[Dict[str, Any]] = []
        options_coll = sref.collection("byOption")
        for opt_snap in options_coll.stream():
            opt = opt_snap.to_dict() or {}
            width = int(opt.get("board_width", 0) or 0)
            height = int(opt.get("board_height", 0) or 0)
            num_mines = int(opt.get("num_mines", 0) or 0)
            o_played = int(opt.get("played", 0) or 0)
            o_wins = int(opt.get("wins", 0) or 0)
            o_losses = int(opt.get("losses", 0) or 0)
            o_aborts = int(opt.get("aborts", 0) or 0)
            o_denom = o_wins + o_losses + o_aborts
            o_win_pct = float(o_wins) / o_denom if o_denom > 0 else 0.0
            key = self._stats_key(width, height, num_mines)
            by_option_list.append(
                {
                    "key": key,
                    "board_width": width,
                    "board_height": height,
                    "num_mines": num_mines,
                    "played": o_played,
                    "wins": o_wins,
                    "losses": o_losses,
                    "aborts": o_aborts,
                    "winPct": o_win_pct,
                }
            )
        return {
            "totals": {
                "played": played,
                "wins": wins,
                "losses": losses,
                "aborts": aborts,
                "winPct": win_pct,
            },
            "byOption": by_option_list,
        }

    def to_client(self, game: Dict[str, Any]) -> Dict[str, Any]:
        s = _to_state(game)
        board = to_client_view(s)
        return {
            "status": game["status"],
            "board": board,
            "board_width": game["board_width"],
            "board_height": game["board_height"],
            "moves_count": game.get("moves_count", 0),
            "flags_total": _count_flags(game["flag_mask"]),
            "revealed_total": _count_revealed(game["revealed_mask"]),
            "num_mines": game["num_mines"],
            "end_result": game.get("end_result"),
        }
