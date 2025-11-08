from fastapi.testclient import TestClient

from app.main import create_app
from minesweeper.persistence import InMemoryPersistence


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

    r = c.post("/api/minesweeper/abandon", headers=headers)
    assert r.status_code == 200
    s4 = r.json()
    assert s4["status"] == "abandoned"

    # After abandon, can start a new game
    r = c.post("/api/minesweeper/start", json={"board_width": 4, "board_height": 4, "num_mines": 2}, headers=headers)
    assert r.status_code == 200
