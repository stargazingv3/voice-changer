from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


app = FastAPI(title="Voice Changer Server", version="0.1.0")

# Allow local dev from Tauri/webview and localhost
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


# Import side-effect: registers websocket routes
try:
    from server.stream.ws import router as ws_router  # noqa: E402

    app.include_router(ws_router)
except Exception as exc:  # pragma: no cover
    # Keep API bootable even if stream module has errors during early dev
    @app.get("/stream_unavailable")
    def stream_unavailable() -> dict:
        return {"error": f"stream module not loaded: {exc}"}


