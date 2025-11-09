from fastapi.testclient import TestClient

from app.main import create_app
from minesweeper.persistence import InMemoryPersistence
import pytest


def make_client():
    app = create_app(persistence=InMemoryPersistence())
    return TestClient(app)


def test_start_and_state_and_409():
    c = make_client()
    headers = {"X-User-Id": "u1"}
    r = c.post("/api/minesweeper/start", json={"board_width": 5, "board_height": 5, "num_mines": 5}, headers=headers)
    assert r.status_code == 200
    s = c.get("/api/minesweeper/state", headers=headers).json()
    assert s["board_width"] == 5 and s["board_height"] == 5
    r2 = c.post("/api/minesweeper/start", json={"board_width": 5, "board_height": 5, "num_mines": 5}, headers=headers)
    assert r2.status_code == 409


def test_reveal_and_flag_and_abandon():
    c = make_client()
    headers = {"X-User-Id": "u2"}
    c.post("/api/minesweeper/start", json={"board_width": 4, "board_height": 4, "num_mines": 2}, headers=headers)
    s1 = c.get("/api/minesweeper/state", headers=headers).json()
    assert s1["moves_count"] == 0

    r = c.post("/api/minesweeper/reveal", json={"row": 0, "col": 0}, headers=headers)
    assert r.status_code == 200
    s2 = r.json()
    assert s2["moves_count"] >= 1

    r = c.post("/api/minesweeper/flag", json={"row": 1, "col": 1}, headers=headers)
    assert r.status_code == 200
    s3 = r.json()
    # flags_total is present for convenience
    assert "flags_total" in s3
    assert s3["moves_count"] == s2["moves_count"]

    r = c.post("/api/minesweeper/abandon", headers=headers)
    assert r.status_code == 200
    s4 = r.json()
    assert s4["status"] == "abandoned"

    # After abandon, can start a new game
    r = c.post("/api/minesweeper/start", json={"board_width": 4, "board_height": 4, "num_mines": 2}, headers=headers)
    assert r.status_code == 200


def test_noop_reveals_do_not_increase_moves():
    c = make_client()
    headers = {"X-User-Id": "u5"}
    c.post("/api/minesweeper/start", json={"board_width": 5, "board_height": 5, "num_mines": 3}, headers=headers)
    r1 = c.post("/api/minesweeper/reveal", json={"row": 0, "col": 0}, headers=headers)
    s1 = r1.json()
    r2 = c.post("/api/minesweeper/reveal", json={"row": 0, "col": 0}, headers=headers)
    s2 = r2.json()
    assert s2["moves_count"] == s1["moves_count"]
    c.post("/api/minesweeper/flag", json={"row": 1, "col": 1}, headers=headers)
    r3 = c.post("/api/minesweeper/reveal", json={"row": 1, "col": 1}, headers=headers)
    s3 = r3.json()
    assert s3["moves_count"] == s2["moves_count"]


def test_start_boundary_validation_400():
    c = make_client()
    headers = {"X-User-Id": "u3"}
    r = c.post("/api/minesweeper/start", json={"board_width": 3, "board_height": 3, "num_mines": 6}, headers=headers)
    assert r.status_code == 400
    assert "too_many_mines_for_board" in r.text


def test_reveal_insufficient_space_for_mines_400():
    c = make_client()
    headers = {"X-User-Id": "u4"}
    r = c.post("/api/minesweeper/start", json={"board_width": 3, "board_height": 3, "num_mines": 5}, headers=headers)
    assert r.status_code == 200
    r2 = c.post("/api/minesweeper/reveal", json={"row": 1, "col": 1}, headers=headers)
    assert r2.status_code == 400
    assert "insufficient_space_for_mines" in r2.text
