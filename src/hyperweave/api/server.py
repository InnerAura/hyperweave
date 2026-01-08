"""
HyperWeave FastAPI Server.

Main FastAPI application for the HyperWeave Living Artifact Protocol API v3.3.
"""

import os
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from hyperweave.api.routers import (
    badge,
    grammar,
    ontology,
    specimens,
    validate,
)

# ─────────────────────────────────────────────────────────────
# CONFIGURATION (Environment-based)
# ─────────────────────────────────────────────────────────────

# CORS configuration from environment
# Default: Allow localhost for development
# Production: Set CORS_ORIGINS env var to comma-separated list
_cors_origins_env = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:8080")
ALLOWED_ORIGINS: list[str] = [origin.strip() for origin in _cors_origins_env.split(",") if origin.strip()]

# Security: Never allow credentials with wildcard origins
_has_wildcard = "*" in ALLOWED_ORIGINS
ALLOW_CREDENTIALS = not _has_wildcard  # Only allow credentials with explicit origins


# Create FastAPI app
app = FastAPI(
    title="HyperWeave Living Artifact API",
    version="3.3.0",
    description="""
    Ontology-integrated Living Artifact generation API.

    **Key Features:**
    - Ontology query endpoints for primitive discovery
    - Specimen-based generation (golden path)
    - ThemeDNA fingerprint for reproducibility
    - Series constraint validation

    **The Ontology:**
    BADGE = SHAPE × SEAM × FINISH × STATE × MOTION × CONTENT
    """,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS middleware - Secure configuration
# CVE-2025-49596: Never use allow_credentials=True with allow_origins=["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=ALLOW_CREDENTIALS,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Request-ID"],
)


# Exception handlers
@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    """Handle ValueError exceptions."""
    return JSONResponse(
        status_code=400,
        content={"error": "Bad Request", "detail": str(exc)},
    )


@app.exception_handler(KeyError)
async def key_error_handler(request: Request, exc: KeyError) -> JSONResponse:
    """Handle KeyError exceptions."""
    return JSONResponse(
        status_code=404,
        content={"error": "Not Found", "detail": f"Resource not found: {exc}"},
    )


# Include routers
# IMPORTANT: v3 API routers MUST be registered BEFORE grammar router
# The grammar router uses a catch-all pattern /{data_source:path}/{style_chain}
# which would intercept /v3/ontology paths if registered first.
# FastAPI matches routes in registration order.

# v3 API routers (more specific - register FIRST)
app.include_router(badge.router, prefix="/v3", tags=["Badge Generation"])
app.include_router(ontology.router, prefix="/v3", tags=["Ontology"])
app.include_router(specimens.router, prefix="/v3", tags=["Specimens"])
app.include_router(validate.router, prefix="/v3", tags=["Validation"])

# URL Grammar router (catch-all - register LAST)
app.include_router(grammar.router, tags=["URL Grammar"])


@app.get("/")
async def root() -> dict[str, str]:
    """API root endpoint."""
    return {
        "name": "HyperWeave Living Artifact API",
        "version": "3.3.0",
        "ontology_version": "7.0.0",
        "docs": "/docs",
        "formula": "BADGE = THEME(state) × CONTENT × MOTION",
    }


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy", "version": "3.3.0"}


def main() -> None:
    """Run the FastAPI server."""
    import uvicorn

    uvicorn.run(
        "hyperweave.api.server:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )


if __name__ == "__main__":
    main()
