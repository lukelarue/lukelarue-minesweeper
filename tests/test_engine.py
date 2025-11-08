import re
from minesweeper.game_engine import generate_new_game, apply_reveal, apply_flag, to_client_view


def count_mines(layout: str) -> int:
    return layout.count("M")


def test_generate_new_game_counts():
    s = generate_new_game(8, 8, 10, rng_seed=42)
    assert s.width == 8 and s.height == 8
    assert count_mines(s.mine_layout) == 10
    assert set(s.revealed_mask) == {"0"}
    assert set(s.flag_mask) == {"0"}


def test_reveal_mine_loses():
    s = generate_new_game(5, 5, 3, rng_seed=1)
    i = s.mine_layout.index("M")
    row, col = divmod(i, s.width)
    s2, res = apply_reveal(s, row, col)
    assert res["hit_mine"] is True
    assert s2.status == "lost"


def test_reveal_zero_floods():
    s = generate_new_game(6, 6, 5, rng_seed=7)
    # find a zero cell
    idx = next(i for i, ch in enumerate(s.mine_layout) if ch == "0")
    r, c = divmod(idx, s.width)
    s2, res = apply_reveal(s, r, c)
    assert res["cleared_cells"] >= 1
    # revealed mask should have ones where cleared
    assert s2.revealed_mask.count("1") >= res["cleared_cells"]


def test_repeated_reveal_noop():
    s = generate_new_game(5, 5, 3, rng_seed=9)
    idx = next(i for i, ch in enumerate(s.mine_layout) if ch != "M")
    r, c = divmod(idx, s.width)
    s2, res1 = apply_reveal(s, r, c)
    s3, res2 = apply_reveal(s2, r, c)
    assert res2["cleared_cells"] == 0
    assert s3.revealed_mask == s2.revealed_mask


def test_flag_toggle_and_no_flag_on_revealed():
    s = generate_new_game(5, 5, 3, rng_seed=2)
    # toggle flag
    s2, res = apply_flag(s, 0, 0)
    assert res["flags_total"] == 1
    s3, res = apply_flag(s2, 0, 0)
    assert res["flags_total"] == 0
    # reveal then attempt to flag
    s4, _ = apply_reveal(s3, 1, 1)
    s5, res = apply_flag(s4, 1, 1)
    assert res["flags_total"] == 0


def test_to_client_view_hides_mines_while_active():
    s = generate_new_game(5, 5, 3, rng_seed=3)
    board = to_client_view(s)
    assert all(cell != "M" for row in board for cell in row)
