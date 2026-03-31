from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from openai import OpenAI

load_dotenv()

SYSTEM_INSTRUCTIONS = """Du svarar på frågor om Kyrkoordningen för Svenska kyrkan.

Regler:
1. Behandla text_type="provision" som bindande bestämmelser.
2. Behandla text_type="intro" som kontext/tolkning.
3. Svara aldrig att intro-text ensam är bindande norm.
4. Citera alltid med citation_label i svaret när möjligt.
5. Om bindande bestämmelse saknas i underlaget, säg det tydligt.
"""


def _require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def build_client() -> OpenAI:
    api_key = _require_env("OPENAI_API_KEY")
    return OpenAI(api_key=api_key)


def build_vector_store_ids() -> list[str]:
    value = _require_env("OPENAI_VECTOR_STORE_ID")
    return [item.strip() for item in value.split(",") if item.strip()]


class AskRequest(BaseModel):
    question: str = Field(min_length=1, description="User question in Swedish or English.")
    model: str = Field(default="gpt-4.1-mini")


class AskResponse(BaseModel):
    answer: str
    model: str
    vector_store_ids: list[str]
    response_id: str | None = None


app = FastAPI(title="Kyrkoordningen RAG API", version="1.0.0")


@app.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True}


@app.post("/ask", response_model=AskResponse)
def ask(payload: AskRequest) -> AskResponse:
    try:
        client = build_client()
        vector_store_ids = build_vector_store_ids()
    except RuntimeError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error

    response = client.responses.create(
        model=payload.model,
        input=[
            {"role": "system", "content": [{"type": "input_text", "text": SYSTEM_INSTRUCTIONS}]},
            {"role": "user", "content": [{"type": "input_text", "text": payload.question}]},
        ],
        tools=[{"type": "file_search", "vector_store_ids": vector_store_ids}],
    )

    answer = (response.output_text or "").strip()
    if not answer:
        answer = "Jag kunde inte skapa ett svar från underlaget."

    return AskResponse(
        answer=answer,
        model=payload.model,
        vector_store_ids=vector_store_ids,
        response_id=response.id,
    )
