"""
Detecta se um texto colado na aba "Plano Alimentar / Treino" é um plano
alimentar ou um plano de treino, para decidir qual parser/template usar.

Heurística simples baseada em palavras-chave características de cada
formato (ajustar conforme mais exemplos reais aparecerem).
"""

from __future__ import annotations

import re

WEEKDAY_RE = re.compile(
    r"\b(SEGUNDA|TER[ÇC]A|QUARTA|QUINTA|SEXTA|S[ÁA]BADO|DOMINGO)([\s-]*FEIRA)?\b",
    re.IGNORECASE,
)
MEAL_KEYWORDS = ("REFEIÇÃO", "REFEICAO", "ESCOLHER 1", "ESCOLHER 2", "CARB CYCLING")
WORKOUT_KEYWORDS = ("SÉRIES", "SERIES", "REPETIÇÕES", "REPETICOES", "AQUECIMENTO")


def detect_doc_type(text: str) -> str:
    """Retorna "meal_plan" ou "workout"."""
    upper = text.upper()
    has_meal_markers = any(k in upper for k in MEAL_KEYWORDS)
    has_workout_markers = bool(WEEKDAY_RE.search(upper)) or any(
        k in upper for k in WORKOUT_KEYWORDS
    )

    if has_workout_markers and not has_meal_markers:
        return "workout"
    if has_meal_markers and not has_workout_markers:
        return "meal_plan"
    if has_workout_markers and has_meal_markers:
        # Ambíguo: dias da semana costumam ser um sinal mais forte de treino.
        return "workout" if WEEKDAY_RE.search(upper) else "meal_plan"
    return "meal_plan"
