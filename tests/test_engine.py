import re
import pytest
from minesweeper.game_engine import generate_new_game, apply_reveal, apply_flag, to_client_view, index


def count_mines(layout: str) -> int:
    return layout.count("M")


def test_generate_new_game_counts_and_first_click_places_mines():
    s = generate_new_game(8, 8, 10, rng_seed=42)
    assert s.width == 8 and s.height == 8
    assert count_mines(s.mine_layout) == 0
    assert s.mines_placed is False
    assert set(s.revealed_mask) == {"0"}
    assert set(s.flag_mask) == {"0"}

    s2, res = apply_reveal(s, 0, 0)
    assert s2.mines_placed is True
    assert count_mines(s2.mine_layout) == 10
    safe = {(0, 0), (0, 1), (1, 0), (1, 1)}
    for r, c in safe:
        i = index(r, c, s2.width)
        assert s2.mine_layout[i] != "M"


def test_reveal_mine_loses():
    s = generate_new_game(5, 5, 3, rng_seed=1)
    s1, _ = apply_reveal(s, 0, 0)
    i = s1.mine_layout.index("M")
    row, col = divmod(i, s1.width)
    s2, res = apply_reveal(s1, row, col)
    assert res["hit_mine"] is True
    assert s2.status == "lost"


def test_reveal_zero_floods():
    s = generate_new_game(6, 6, 5, rng_seed=7)
    s1, _ = apply_reveal(s, 0, 0)
    # find a zero cell
    idx = next(i for i, ch in enumerate(s1.mine_layout) if ch == "0" and s1.revealed_mask[i] == "0")
    r, c = divmod(idx, s1.width)
    s2, res = apply_reveal(s1, r, c)
    assert res["cleared_cells"] >= 1
    # revealed mask should have ones where cleared
    assert s2.revealed_mask.count("1") >= res["cleared_cells"]


def test_repeated_reveal_noop():
    s = generate_new_game(5, 5, 3, rng_seed=9)
    s2, res1 = apply_reveal(s, 0, 0)
    s3, res2 = apply_reveal(s2, 0, 0)
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


def test_first_click_safe_area_exclusion():
    s = generate_new_game(10, 10, 20, rng_seed=123)
    r0, c0 = 4, 4
    s1, _ = apply_reveal(s, r0, c0)
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            rr, cc = r0 + dr, c0 + dc
            if 0 <= rr < s1.height and 0 <= cc < s1.width:
                i = index(rr, cc, s1.width)
                assert s1.mine_layout[i] != "M"


def test_insufficient_space_for_mines_error():
    s = generate_new_game(3, 3, 5, rng_seed=5)
    with pytest.raises(ValueError) as exc:
        apply_reveal(s, 1, 1)
    assert str(exc.value) == "insufficient_space_for_mines"
