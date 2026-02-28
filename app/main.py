from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.database import init_db
from app.routers import files, messages, tickets, users


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Support WebApp", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 404:
        path = request.url.path
        # Known API prefixes where legitimate 404s can occur
        if path.startswith(("/tickets", "/files", "/auth")):
            return JSONResponse(status_code=404, content={"detail": exc.detail})
        # Path outside all known routes — treat as access denied (e.g. path traversal)
        return JSONResponse(status_code=403, content={"detail": "Access denied"})
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


# API routers
app.include_router(users.router)
app.include_router(tickets.router)
app.include_router(messages.router)
app.include_router(files.router)

# Serve frontend static files
_frontend_dir = Path(__file__).parent.parent / "frontend"
if _frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(_frontend_dir), html=True), name="frontend")
