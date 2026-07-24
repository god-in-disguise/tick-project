from fastapi import FastAPI

from tick_mvp.config import get_settings


app = FastAPI(title="TICK MVP API")


@app.get("/health")
def health() -> dict[str, object]:
    settings = get_settings()
    return {
        "ok": True,
        "env": settings.tick_env,
        "venue": settings.default_venue,
        "chainId": settings.arb_chain_id,
    }


@app.get("/ready")
def ready() -> dict[str, object]:
    return {"ok": True}

