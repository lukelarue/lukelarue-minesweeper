import os
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from minesweeper.persistence import InMemoryPersistence, FirestorePersistence

load_dotenv(dotenv_path=Path('.env.local'))

API_BASE = "/api/minesweeper"


def choose_persistence():
    use_inmem = os.getenv("USE_INMEMORY", "0").lower() in ("1", "true", "yes")
    emulator = os.getenv("FIRESTORE_EMULATOR_HOST")
    if use_inmem:
        return InMemoryPersistence()
    try:
        if emulator:
            return FirestorePersistence()
        # default to Firestore in production
        return FirestorePersistence()
    except Exception:
        # Fallback to in-memory if firestore client not available
        return InMemoryPersistence()


class StartBody(BaseModel):
    board_width: int = Field(..., ge=2, le=100)
    board_height: int = Field(..., ge=2, le=100)
    num_mines: int = Field(..., ge=1)


class MoveBody(BaseModel):
    row: int = Field(..., ge=0)
    col: int = Field(..., ge=0)


def create_app(persistence=None) -> FastAPI:
    app = FastAPI(title="Minesweeper Service", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"]
    )

    app.state.persistence = persistence or choose_persistence()

    def get_user_id(req: Request) -> str:
        uid = req.headers.get("X-User-Id")
        if uid:
            return uid
        allow_anon = os.getenv("ALLOW_ANON", "1").lower() in ("1", "true", "yes")
        default_uid = os.getenv("DEFAULT_USER_ID", "local-user")
        if allow_anon:
            return default_uid
        raise HTTPException(status_code=401, detail="missing user id")

    @app.post(f"{API_BASE}/start")
    def start_game(body: StartBody, user_id: str = Depends(get_user_id)):
        try:
            doc = app.state.persistence.start_game(
                user_id,
                body.board_width,
                body.board_height,
                body.num_mines,
            )
        except ValueError as e:
            if str(e) == "active_game_exists":
                raise HTTPException(status_code=409, detail="active game exists")
            raise
        return app.state.persistence.to_client(doc) | {"game_id": user_id}

    @app.get(f"{API_BASE}/state")
    def get_state(user_id: str = Depends(get_user_id)):
        game = app.state.persistence.get_game(user_id)
        if not game:
            raise HTTPException(status_code=404, detail="no game")
        return app.state.persistence.to_client(game) | {"game_id": user_id}

    @app.post(f"{API_BASE}/reveal")
    def reveal(body: MoveBody, user_id: str = Depends(get_user_id)):
        game = app.state.persistence.get_game(user_id)
        if not game:
            raise HTTPException(status_code=404, detail="no game")
        try:
            game, _move = app.state.persistence.reveal(user_id, body.row, body.col)
        except KeyError:
            raise HTTPException(status_code=404, detail="no game")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return app.state.persistence.to_client(game) | {"game_id": user_id}

    @app.post(f"{API_BASE}/flag")
    def flag(body: MoveBody, user_id: str = Depends(get_user_id)):
        game = app.state.persistence.get_game(user_id)
        if not game:
            raise HTTPException(status_code=404, detail="no game")
        try:
            game, _move = app.state.persistence.flag(user_id, body.row, body.col)
        except KeyError:
            raise HTTPException(status_code=404, detail="no game")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return app.state.persistence.to_client(game) | {"game_id": user_id}

    @app.post(f"{API_BASE}/abandon")
    def abandon(user_id: str = Depends(get_user_id)):
        game = app.state.persistence.get_game(user_id)
        if not game:
            raise HTTPException(status_code=404, detail="no game")
        game, _move = app.state.persistence.abandon(user_id)
        return app.state.persistence.to_client(game) | {"game_id": user_id}

    # Static frontend
    frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
    if frontend_dir.exists():
        app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")

    return app


app = create_app()
