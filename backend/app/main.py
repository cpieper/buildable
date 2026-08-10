from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI(title="What2Build", version="0.1.0")

    @app.get("/api/health", tags=["system"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
