from __future__ import annotations

import dataclasses
import re
import unicodedata
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from doc_detect import detect_doc_type
from parser_checkin import parse_checkin
from parser_meal_plan import parse_meal_plan
from parser_treino import parse_workout
from pdf_generator import (
    render_checkin_pdf,
    render_checkin_preview,
    render_meal_plan_pdf,
    render_meal_plan_preview,
    render_workout_pdf,
    render_workout_preview,
)

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

app = FastAPI(title="Formatador de Planos - Personal Trainer")


class TextPayload(BaseModel):
    text: str
    brand_name: Optional[str] = None
    # "auto" (padrão) deixa a ferramenta decidir; "meal_plan" ou "workout"
    # força o tipo, para quando a detecção automática errar.
    doc_type: Optional[str] = None


def _pdf_filename(prefix: str, client_name: str) -> str:
    """Monta o nome do arquivo baixado. O header Content-Disposition só
    aceita latin-1, então nomes com travessões, emojis etc. (comuns em
    texto colado de outros apps) quebravam a resposta com um 500 — aqui
    normalizamos para um slug ASCII seguro."""
    base = (client_name or "cliente").strip().lower()
    ascii_base = unicodedata.normalize("NFKD", base).encode("ascii", "ignore").decode("ascii")
    ascii_base = re.sub(r"[^a-z0-9]+", "-", ascii_base).strip("-")
    return f"{prefix}-{ascii_base or 'cliente'}.pdf"


def _resolve_doc_type(payload: TextPayload) -> str:
    if payload.doc_type in ("meal_plan", "workout"):
        return payload.doc_type
    return detect_doc_type(payload.text)


@app.post("/api/plan/parse")
def api_plan_parse(payload: TextPayload) -> JSONResponse:
    doc_type = _resolve_doc_type(payload)
    if doc_type == "workout":
        data = dataclasses.asdict(parse_workout(payload.text))
    else:
        data = dataclasses.asdict(parse_meal_plan(payload.text))
    return JSONResponse({"doc_type": doc_type, "data": data})


@app.post("/api/plan/preview", response_class=HTMLResponse)
def api_plan_preview(payload: TextPayload) -> HTMLResponse:
    doc_type = _resolve_doc_type(payload)
    if doc_type == "workout":
        plan = parse_workout(payload.text)
        html = render_workout_preview(plan, payload.brand_name or "")
    else:
        plan = parse_meal_plan(payload.text)
        html = render_meal_plan_preview(plan, payload.brand_name or "")
    # Um pequeno rótulo indicando o tipo detectado, útil para conferência
    # rápida antes de baixar o PDF.
    label = "Treino" if doc_type == "workout" else "Plano Alimentar"
    banner = (
        f'<div style="background:#eef;color:#334;font:11px sans-serif;'
        f'padding:4px 8px;border-bottom:1px solid #ccd;">'
        f"Tipo detectado: {label}</div>"
    )
    return HTMLResponse(banner + html)


@app.post("/api/plan/pdf")
def api_plan_pdf(payload: TextPayload) -> Response:
    doc_type = _resolve_doc_type(payload)
    if doc_type == "workout":
        plan = parse_workout(payload.text)
        pdf_bytes = render_workout_pdf(plan, payload.brand_name or "")
        client_name = plan.client_name
        prefix = "treino"
    else:
        plan = parse_meal_plan(payload.text)
        pdf_bytes = render_meal_plan_pdf(plan, payload.brand_name or "")
        client_name = plan.client_name
        prefix = "plano"

    filename = _pdf_filename(prefix, client_name)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Doc-Type": doc_type,
        },
    )


@app.post("/api/checkin/parse")
def api_checkin_parse(payload: TextPayload) -> JSONResponse:
    checkin = parse_checkin(payload.text)
    return JSONResponse(dataclasses.asdict(checkin))


@app.post("/api/checkin/preview", response_class=HTMLResponse)
def api_checkin_preview(payload: TextPayload) -> HTMLResponse:
    checkin = parse_checkin(payload.text)
    html = render_checkin_preview(checkin, payload.brand_name or "")
    return HTMLResponse(html)


@app.post("/api/checkin/pdf")
def api_checkin_pdf(payload: TextPayload) -> Response:
    checkin = parse_checkin(payload.text)
    pdf_bytes = render_checkin_pdf(checkin, payload.brand_name or "")
    filename = _pdf_filename("checkin", checkin.client_name)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
