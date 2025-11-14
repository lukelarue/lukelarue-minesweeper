import os
import logging
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
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
    board_width: int = Field(..., ge=2, le=40)
    board_height: int = Field(..., ge=2, le=40)
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

    @app.on_event("startup")
    async def _log_persistence():
        try:
            klass = app.state.persistence.__class__.__name__
        except Exception:
            klass = str(type(app.state.persistence))
        use_inmem = os.getenv("USE_INMEMORY", "0").lower() in ("1", "true", "yes")
        emulator = os.getenv("FIRESTORE_EMULATOR_HOST")
        project = os.getenv("GOOGLE_CLOUD_PROJECT")
        logging.getLogger("uvicorn.error").info(
            f"[minesweeper] Persistence={klass} USE_INMEMORY={int(use_inmem)} FIRESTORE_EMULATOR_HOST={emulator or '-'} GOOGLE_CLOUD_PROJECT={project or '-'}"
        )

    def get_user_id(req: Request) -> str:
        # Detect Cloud Run to set safer defaults in production
        is_cloud_run = bool(os.getenv("K_SERVICE") or os.getenv("K_REVISION") or os.getenv("K_CONFIGURATION"))
        trust_x_user_id = os.getenv("TRUST_X_USER_ID", "0" if is_cloud_run else "1").lower() in ("1", "true", "yes")
        allow_anon = os.getenv("ALLOW_ANON", "0" if is_cloud_run else "1").lower() in ("1", "true", "yes")
        default_uid = os.getenv("DEFAULT_USER_ID", "local-user")
        logger = logging.getLogger("uvicorn.error")

        # 1) Prefer Google/IAP style headers when present (production)
        iap_email = (
            req.headers.get("X-Goog-Authenticated-User-Email")
            or req.headers.get("X-Authenticated-User-Email")
            or req.headers.get("X-Forwarded-Email")
        )
        if iap_email:
            # Format often: "accounts.google.com:email@example.com"
            if ":" in iap_email:
                iap_email = iap_email.split(":", 1)[1]
            logger.info(
                f"[minesweeper] get_user_id via=iap_email user_id={iap_email} "
                f"is_cloud_run={int(is_cloud_run)} trust_x_user_id={int(trust_x_user_id)} allow_anon={int(allow_anon)}"
            )
            return iap_email
        forwarded_user = req.headers.get("X-Forwarded-User")
        if forwarded_user:
            logger.info(
                f"[minesweeper] get_user_id via=forwarded_user user_id={forwarded_user} "
                f"is_cloud_run={int(is_cloud_run)} trust_x_user_id={int(trust_x_user_id)} allow_anon={int(allow_anon)}"
            )
            return forwarded_user

        # 2) Only trust explicit header in dev or if explicitly enabled
        uid = req.headers.get("X-User-Id")
        if uid and trust_x_user_id:
            logger.info(
                f"[minesweeper] get_user_id via=x-user-id user_id={uid} "
                f"is_cloud_run={int(is_cloud_run)} trust_x_user_id={int(trust_x_user_id)} allow_anon={int(allow_anon)}"
            )
            return uid

        # 3) Dev fallback (only if explicitly allowed)
        if allow_anon:
            logger.info(
                f"[minesweeper] get_user_id via=anon-fallback user_id={default_uid} "
                f"is_cloud_run={int(is_cloud_run)} trust_x_user_id={int(trust_x_user_id)} allow_anon={int(allow_anon)}"
            )
            return default_uid

        logger.warning(
            f"[minesweeper] get_user_id missing user id is_cloud_run={int(is_cloud_run)} "
            f"trust_x_user_id={int(trust_x_user_id)} allow_anon={int(allow_anon)}"
        )
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
            # Treat other ValueErrors as bad requests (validation/boundary errors)
            raise HTTPException(status_code=400, detail=str(e))
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
            # Capture certain engine errors as final end_result=error
            if str(e) == "insufficient_space_for_mines":
                try:
                    app.state.persistence.mark_error(user_id, str(e))
                except Exception:
                    pass
            raise HTTPException(status_code=400, detail=str(e))
        resp = app.state.persistence.to_client(game) | {"game_id": user_id}
        if isinstance(_move, dict) and "row" in _move and "col" in _move:
            try:
                resp["last_move"] = {
                    "row": int(_move.get("row")) if _move.get("row") is not None else None,
                    "col": int(_move.get("col")) if _move.get("col") is not None else None,
                    "hit_mine": bool(_move.get("hit_mine")),
                }
            except Exception:
                pass
        return resp

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

    @app.get(f"{API_BASE}/stats")
    def get_stats(user_id: str = Depends(get_user_id)):
        stats = app.state.persistence.get_stats(user_id)
        return stats

    # Static frontend
    frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
    if frontend_dir.exists():
        app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")

    return app


app = create_app()
