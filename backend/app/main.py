from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import init_db
from .routers import boundaries, connectors, days, potholes, projects, roadworks, strava

app = FastAPI(title="GPX Route Editor")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.get("/api/health")
def health():
    return {"status": "ok"}


app.include_router(projects.router, prefix="/api")
app.include_router(days.router, prefix="/api")
app.include_router(connectors.router, prefix="/api")
app.include_router(roadworks.router, prefix="/api")
app.include_router(strava.router, prefix="/api")
app.include_router(potholes.router, prefix="/api")
app.include_router(boundaries.router, prefix="/api")
