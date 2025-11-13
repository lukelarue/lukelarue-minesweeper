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


def test_isolation_between_two_users_via_x_user_id():
    c = make_client()
    h1 = {"X-User-Id": "user_a"}
    h2 = {"X-User-Id": "user_b"}
    # Start for both
    r1 = c.post("/api/minesweeper/start", json={"board_width": 4, "board_height": 4, "num_mines": 2}, headers=h1)
    assert r1.status_code == 200
    r2 = c.post("/api/minesweeper/start", json={"board_width": 4, "board_height": 4, "num_mines": 2}, headers=h2)
    assert r2.status_code == 200
    # Make a move as user_a
    m1 = c.post("/api/minesweeper/reveal", json={"row": 0, "col": 0}, headers=h1)
    assert m1.status_code == 200
    s1 = c.get("/api/minesweeper/state", headers=h1).json()
    s2 = c.get("/api/minesweeper/state", headers=h2).json()
    # user_a should have at least one move; user_b should remain unaffected
    assert s1["moves_count"] >= 1
    assert s2["moves_count"] == 0
    assert s1["game_id"] != s2["game_id"]


def test_isolation_with_google_headers():
    c = make_client()
    g1 = {"X-Goog-Authenticated-User-Email": "accounts.google.com:alice@example.com"}
    g2 = {"X-Goog-Authenticated-User-Email": "accounts.google.com:bob@example.com"}
    r1 = c.post("/api/minesweeper/start", json={"board_width": 5, "board_height": 5, "num_mines": 5}, headers=g1)
    assert r1.status_code == 200
    r2 = c.post("/api/minesweeper/start", json={"board_width": 5, "board_height": 5, "num_mines": 5}, headers=g2)
    assert r2.status_code == 200
    # Reveal as alice; bob should not be affected
    c.post("/api/minesweeper/reveal", json={"row": 0, "col": 0}, headers=g1)
    s_alice = c.get("/api/minesweeper/state", headers=g1).json()
    s_bob = c.get("/api/minesweeper/state", headers=g2).json()
    assert s_alice["moves_count"] >= 1
    assert s_bob["moves_count"] == 0
    assert s_alice["game_id"] != s_bob["game_id"]
