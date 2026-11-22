"""Local HTTP entry point for grounded answers."""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from .answering import MAX_QUESTION, create_service, normalize_question

WEB_DIR = Path(__file__).resolve().parents[1] / "web"


class AskRequest(BaseModel):
    question: str = Field(max_length=MAX_QUESTION, min_length=1)

    @field_validator("question")
    @classmethod
    def strip_question(cls, question):
        return normalize_question(question)


def create_app(service=None):
    @asynccontextmanager
    async def lifespan(app):
        app.state.service = service if service is not None else create_service()
        yield

    app = FastAPI(title="AeroDoc", lifespan=lifespan)
    app.mount("/assets", StaticFiles(directory=WEB_DIR), name="assets")

    @app.get("/", include_in_schema=False)
    def demo():
        return FileResponse(WEB_DIR / "index.html")

    @app.exception_handler(RequestValidationError)
    async def invalid_question(request, error):
        return JSONResponse(status_code=422, content={"error_code": "invalid_request"})

    @app.get("/health")
    def health():
        return {"status": "ok", "retrieval": app.state.service.identity["retrieval"]}

    @app.post("/ask")
    def ask(payload: AskRequest):
        result = app.state.service.ask(payload.question)
        status = {
            "budget_exceeded": 429,
            "provider_error": {"timeout": 504, "rate_limit": 503}.get(result.get("error_code"), 502),
        }.get(result["status"], 200)
        return JSONResponse(result, status_code=status)

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
