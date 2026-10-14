from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.core.version import app_version
from app.health import libs, run_checks

router = APIRouter()
api = APIRouter(prefix="/api/v1")


@router.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}


@api.get("/version")
async def get_version(request: Request) -> dict:
    state = request.app.state
    return {
        "app": app_version(),
        "git_sha": state.settings.git_sha[:7],
        "scoring": state.scoring.version,
        "f0_engine": f"{state.f0.name}-{state.f0.version}",
    }


@api.get("/health")
async def get_health(request: Request) -> JSONResponse:
    status, components = await run_checks(request.app.state)
    body = {"status": status, "app": app_version(), "components": components, "libs": libs()}
    return JSONResponse(body, status_code=503 if status == "down" else 200)
