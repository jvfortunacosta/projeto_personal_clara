"""
Parser de planos de treino colados em texto puro.

Baseado no primeiro exemplo real recebido ("TREINO MARIA HELENA"), que tem
esta estrutura:

  NOME DO CLIENTE
  PESO: ...
  ALTURA: ...
  IDADE: ...

  PLANO DE TREINO (título, às vezes com traços decorativos depois)
  Objetivo: ...
  Treinos: ...
  Cardio: ...
  Tempo total: ...

  SEGUNDA-FEIRA - GRUPO MUSCULAR
  Aquecimento
  <exercícios de aquecimento em formato compacto: "Nome – NxM texto">
  <exercícios principais: "Nome (equipamento) - N séries" seguido de uma
   linha de repetições por série, ou uma linha só com números separados
   por "•", e opcionalmente uma linha de dica/observação>
  Abdômen
  <exercícios de abdômen em formato compacto>
  Cardio
  <linhas livres de detalhe: duração, aparelho, inclinação, velocidade>

  ... (repete por dia da semana)

  CARDIO SEMANAL
  <linhas livres: "Dia: duração", "Meta diária: ...">

  Observações Importantes
  <linhas livres>

O exemplo real já mostrou inconsistências (ex.: "Aquecimento" às vezes na
mesma linha que o equipamento ("Aquecimento - Mini Band"), às vezes em
linhas separadas; traço "-" vs "–" usados sem padrão claro), então os
detectores abaixo são propositalmente tolerantes. Ajustar aqui conforme
mais exemplos reais chegarem.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from parser_meal_plan import SEPARATOR_RE, strip_bold

LABEL_VALUE_RE = re.compile(r"^[➢\-•]?\s*([A-Za-zÀ-ú][\w À-ú]{1,30}):\s*(.*)$")
DAY_HEADER_RE = re.compile(
    r"^(SEGUNDA|TER[ÇC]A|QUARTA|QUINTA|SEXTA|S[ÁA]BADO|DOMINGO)"
    r"([\s-]*FEIRA)?\s*[-–—]?\s*(.*)$"
)
EXERCISE_SERIES_RE = re.compile(r"^(.+?)\s*[-–—]\s*(\d+)\s*s[ée]ries?\s*$", re.IGNORECASE)
EXERCISE_COMPACT_RE = re.compile(
    r"^(.+?)\s*[-–—]\s*(\d+)\s*[x×]\s*(\d+)\s*(.*)$", re.IGNORECASE
)
REPS_BULLET_LINE_RE = re.compile(r"^\d+(\s*[•·]\s*\d+)+$")

KNOWN_DAY_SUBLABELS = {"AQUECIMENTO", "ABDÔMEN", "ABDOMEN", "CARDIO"}
KNOWN_FINAL_SECTIONS = {
    "CARDIO SEMANAL",
    "OBSERVAÇÕES IMPORTANTES",
    "OBSERVACOES IMPORTANTES",
    "OBSERVAÇÕES",
    "OBSERVACOES",
}


def is_all_caps_header(line: str) -> bool:
    if not line:
        return False
    letters = [c for c in line if c.isalpha()]
    if not letters:
        return False
    return all(c.isupper() for c in letters)


def _strip_trailing_decoration(line: str) -> str:
    """Remove traços decorativos no fim de um título (ex.: "PLANO DE TREINO —----")."""
    return re.sub(r"[-–—\s]+$", "", line).strip()


def _final_section_key(line: str) -> str | None:
    normalized = _strip_trailing_decoration(line).upper()
    return normalized if normalized in KNOWN_FINAL_SECTIONS else None


# ---------------------------------------------------------------------------
# Modelo de dados
# ---------------------------------------------------------------------------


@dataclass
class Field:
    label: str
    value: str


@dataclass
class DayItem:
    kind: str  # "label" | "exercise" | "text"
    label: str = ""
    name: str = ""
    series_count: int | None = None
    reps: list[str] = field(default_factory=list)
    note: str | None = None
    text: str = ""


@dataclass
class WorkoutDay:
    day_name: str
    focus: str
    items: list[DayItem] = field(default_factory=list)


@dataclass
class WorkoutPlan:
    client_name: str
    client_fields: list[Field] = field(default_factory=list)
    plan_title: str = ""
    plan_fields: list[Field] = field(default_factory=list)
    days: list[WorkoutDay] = field(default_factory=list)
    weekly_summary_title: str = ""
    weekly_summary_lines: list[str] = field(default_factory=list)
    observations_title: str = ""
    observations_lines: list[str] = field(default_factory=list)
    unparsed_warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def parse_workout(raw_text: str) -> WorkoutPlan:
    lines = [l.rstrip() for l in raw_text.replace("\r\n", "\n").split("\n")]

    plan = WorkoutPlan(client_name="")
    phase = "client"  # client -> plan_info -> days -> final
    current_day: WorkoutDay | None = None
    current_final_lines: list[str] | None = None
    pending_exercise: DayItem | None = None

    def close_pending_exercise() -> None:
        nonlocal pending_exercise
        pending_exercise = None

    def make_day(day_match: re.Match) -> WorkoutDay:
        day_word = day_match.group(1).capitalize()
        suffix = "-feira" if day_match.group(2) else ""
        return WorkoutDay(day_name=day_word + suffix, focus=day_match.group(3).strip())

    for raw_line in lines:
        line = raw_line.strip()

        if not line or SEPARATOR_RE.match(line):
            # Linha em branco/separador: encerra a coleta de reps do
            # exercício atual (mas não muda de fase).
            close_pending_exercise()
            continue

        clean = strip_bold(line)

        # Detecção de seção final, válida assim que estivermos dentro dos
        # dias de treino (também cobre a troca entre "CARDIO SEMANAL" e
        # "Observações Importantes" quando já estamos na fase final).
        if phase in ("days", "final"):
            final_key = _final_section_key(clean)
            if final_key:
                close_pending_exercise()
                phase = "final"
                if "CARDIO" in final_key:
                    plan.weekly_summary_title = clean
                    current_final_lines = plan.weekly_summary_lines
                else:
                    plan.observations_title = clean
                    current_final_lines = plan.observations_lines
                continue

        if phase == "final":
            if current_final_lines is None:
                current_final_lines = plan.observations_lines
            current_final_lines.append(clean)
            continue

        if phase == "client":
            label_match = LABEL_VALUE_RE.match(clean)
            if label_match:
                plan.client_fields.append(
                    Field(label=label_match.group(1).strip(), value=label_match.group(2).strip())
                )
                continue
            if not plan.client_name:
                plan.client_name = clean
                continue
            # Primeira linha sem "label:" depois do nome do cliente: título
            # do plano (ex.: "PLANO DE TREINO"), possivelmente com traços.
            plan.plan_title = _strip_trailing_decoration(clean)
            phase = "plan_info"
            continue

        if phase == "plan_info":
            day_match = DAY_HEADER_RE.match(clean.upper()) if is_all_caps_header(clean) else None
            if day_match:
                current_day = make_day(day_match)
                plan.days.append(current_day)
                phase = "days"
                continue
            label_match = LABEL_VALUE_RE.match(clean)
            if label_match:
                plan.plan_fields.append(
                    Field(label=label_match.group(1).strip(), value=label_match.group(2).strip())
                )
                continue
            plan.unparsed_warnings.append(
                f"Linha não reconhecida no bloco de informações do plano: \"{clean[:60]}\""
            )
            continue

        # phase == "days"
        day_match = DAY_HEADER_RE.match(clean.upper()) if is_all_caps_header(clean) else None
        if day_match:
            close_pending_exercise()
            current_day = make_day(day_match)
            plan.days.append(current_day)
            continue

        if current_day is None:
            plan.unparsed_warnings.append(f"Linha fora de qualquer dia de treino: \"{clean[:60]}\"")
            continue

        # Cabeçalho de sub-seção do dia (Aquecimento / Abdômen / Cardio),
        # às vezes com conteúdo extra na mesma linha ("Cardio - 35 minutos").
        if " - " in clean or " – " in clean or " — " in clean:
            head_part, remainder = re.split(r"\s[-–—]\s", clean, maxsplit=1)
        else:
            head_part, remainder = clean, ""

        if head_part.strip().upper() in KNOWN_DAY_SUBLABELS:
            close_pending_exercise()
            current_day.items.append(DayItem(kind="label", label=head_part.strip()))
            if remainder.strip():
                current_day.items.append(DayItem(kind="text", text=remainder.strip()))
            continue

        series_match = EXERCISE_SERIES_RE.match(clean)
        if series_match:
            close_pending_exercise()
            pending_exercise = DayItem(
                kind="exercise",
                name=series_match.group(1).strip(),
                series_count=int(series_match.group(2)),
            )
            current_day.items.append(pending_exercise)
            continue

        compact_match = EXERCISE_COMPACT_RE.match(clean)
        if compact_match:
            close_pending_exercise()
            sets_str, reps_str, trailer = (
                compact_match.group(2),
                compact_match.group(3),
                compact_match.group(4).strip(),
            )
            text = f"{sets_str}x{reps_str}" + (f" {trailer}" if trailer else "")
            current_day.items.append(
                DayItem(
                    kind="exercise",
                    name=compact_match.group(1).strip(),
                    series_count=int(sets_str),
                    reps=[text],
                )
            )
            continue

        if pending_exercise is not None:
            if REPS_BULLET_LINE_RE.match(clean):
                pending_exercise.reps.extend(p.strip() for p in re.split(r"[•·]", clean))
                continue
            # Qualquer linha começando com número é tratada como repetição
            # de uma série (ex.: "12 repetições", "10 repetições em cada
            # perna", "12 cada braço"). O resto vira nota/dica do exercício
            # em coleta (ex.: "Segure 2 segundos no topo.").
            if clean[:1].isdigit():
                pending_exercise.reps.append(clean)
                continue
            pending_exercise.note = (
                f"{pending_exercise.note} {clean}".strip() if pending_exercise.note else clean
            )
            continue

        # Linha solta dentro do dia, fora de qualquer exercício em coleta
        # (ex.: "Mini Band", "Esteira", "Inclinação: 10-12%").
        current_day.items.append(DayItem(kind="text", text=clean))

    return plan
