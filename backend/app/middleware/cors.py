from fastapi.middleware.cors import CORSMiddleware

CORS_SETTINGS = {
    "allow_origins": [
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
    ],
    "allow_credentials": True,
    "allow_methods": ["*"],
    "allow_headers": ["*"],
}


def add_cors_middleware(app):
    """Add CORS middleware to FastAPI app."""
    app.add_middleware(CORSMiddleware, **CORS_SETTINGS)
