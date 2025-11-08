from dataclasses import dataclass, replace
from typing import Tuple, List
import random
from collections import deque


@dataclass(frozen=True)
class GameState:
    width: int
    height: int
    num_mines: int
    mine_layout: str
    revealed_mask: str
    flag_mask: str
    status: str
    moves_count: int


def index(row: int, col: int, width: int) -> int:
    return row * width + col


def coords(idx: int, width: int) -> Tuple[int, int]:
    return divmod(idx, width)


def generate_new_game(width: int, height: int, num_mines: int, rng_seed: int | None = None) -> GameState:
    n = width * height
    if num_mines < 0 or num_mines > n:
        raise ValueError("invalid mine count")
    rng = random.Random(rng_seed)
    mines = set(rng.sample(range(n), num_mines))
    nums = [0] * n
    for i in range(n):
        if i in mines:
            continue
        r, c = coords(i, width)
        cnt = 0
        for nr in range(max(0, r - 1), min(height, r + 2)):
            for nc in range(max(0, c - 1), min(width, c + 2)):
                if nr == r and nc == c:
                    continue
                if index(nr, nc, width) in mines:
                    cnt += 1
        nums[i] = cnt
    layout = ["M" if i in mines else str(nums[i]) for i in range(n)]
    revealed = "0" * n
    flags = "0" * n
    return GameState(width, height, num_mines, "".join(layout), revealed, flags, "active", 0)


def _neighbors(r: int, c: int, w: int, h: int):
    for nr in range(max(0, r - 1), min(h, r + 2)):
        for nc in range(max(0, c - 1), min(w, c + 2)):
            if nr == r and nc == c:
                continue
            yield nr, nc


def _count(mask: str) -> int:
    return mask.count("1")


def is_win(mine_layout: str, revealed_mask: str) -> bool:
    if len(mine_layout) != len(revealed_mask):
        return False
    for i, ch in enumerate(mine_layout):
        if ch != "M" and revealed_mask[i] != "1":
            return False
    return True


def apply_reveal(s: GameState, row: int, col: int):
    if s.status != "active":
        return s, {
            "hit_mine": False,
            "cleared_cells": 0,
            "status_after": s.status,
            "revealed_total": _count(s.revealed_mask),
            "flags_total": _count(s.flag_mask),
        }
    if not (0 <= row < s.height and 0 <= col < s.width):
        raise ValueError("out of bounds")
    i = index(row, col, s.width)
    if s.revealed_mask[i] == "1" or s.flag_mask[i] == "1":
        return s, {
            "hit_mine": False,
            "cleared_cells": 0,
            "status_after": s.status,
            "revealed_total": _count(s.revealed_mask),
            "flags_total": _count(s.flag_mask),
        }
    ml = s.mine_layout
    rev = list(s.revealed_mask)
    cleared = 0
    hit = False
    if ml[i] == "M":
        hit = True
        if rev[i] != "1":
            rev[i] = "1"
            cleared = 1
        new_rev = "".join(rev)
        new_status = "lost"
        ns = replace(s, revealed_mask=new_rev, status=new_status, moves_count=s.moves_count + 1)
        return ns, {
            "hit_mine": True,
            "cleared_cells": cleared,
            "status_after": new_status,
            "revealed_total": _count(new_rev),
            "flags_total": _count(s.flag_mask),
        }
    q = deque()
    q.append((row, col))
    while q:
        r, c = q.popleft()
        ii = index(r, c, s.width)
        if rev[ii] == "1" or s.flag_mask[ii] == "1":
            continue
        rev[ii] = "1"
        cleared += 1
        if ml[ii] == "0":
            for nr, nc in _neighbors(r, c, s.width, s.height):
                jj = index(nr, nc, s.width)
                if rev[jj] != "1" and s.flag_mask[jj] != "1":
                    q.append((nr, nc))
    new_rev = "".join(rev)
    new_status = "won" if is_win(ml, new_rev) else "active"
    ns = replace(s, revealed_mask=new_rev, status=new_status, moves_count=s.moves_count + 1)
    return ns, {
        "hit_mine": False,
        "cleared_cells": cleared,
        "status_after": new_status,
        "revealed_total": _count(new_rev),
        "flags_total": _count(s.flag_mask),
    }


def apply_flag(s: GameState, row: int, col: int):
    if s.status != "active":
        return s, {
            "hit_mine": False,
            "cleared_cells": 0,
            "status_after": s.status,
            "revealed_total": _count(s.revealed_mask),
            "flags_total": _count(s.flag_mask),
        }
    if not (0 <= row < s.height and 0 <= col < s.width):
        raise ValueError("out of bounds")
    i = index(row, col, s.width)
    if s.revealed_mask[i] == "1":
        return s, {
            "hit_mine": False,
            "cleared_cells": 0,
            "status_after": s.status,
            "revealed_total": _count(s.revealed_mask),
            "flags_total": _count(s.flag_mask),
        }
    flags = list(s.flag_mask)
    flags[i] = "0" if flags[i] == "1" else "1"
    new_flags = "".join(flags)
    ns = replace(s, flag_mask=new_flags, moves_count=s.moves_count + 1)
    return ns, {
        "hit_mine": False,
        "cleared_cells": 0,
        "status_after": ns.status,
        "revealed_total": _count(s.revealed_mask),
        "flags_total": _count(new_flags),
    }


def to_client_view(s: GameState) -> List[List[str]]:
    board: List[List[str]] = []
    for r in range(s.height):
        row: List[str] = []
        for c in range(s.width):
            i = index(r, c, s.width)
            ch = s.mine_layout[i]
            if s.status != "active" and ch == "M":
                cell = "M"
            elif s.revealed_mask[i] == "1":
                cell = ch
            else:
                cell = "F" if s.flag_mask[i] == "1" else "H"
            row.append(cell)
        board.append(row)
    return board
