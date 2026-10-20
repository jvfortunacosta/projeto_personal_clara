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

Segundo formato real ("BEATRIZ MOREIRA"), com blocos separados por "⸻":

  NOME DO CLIENTE
  PLANO DE TREINAMENTO – FASE 1
  Altura: ... / Peso: ... / Nível: ... / Objetivo: ... / Frequência: ...
  FOCO DO TREINAMENTO            <- bloco extra do cabeçalho + lista "* ..."
  ⸻
  SEGUNDA – QUADRÍCEPS + GLÚTEOS
  AQUECIMENTO / ATIVAÇÃO         <- sub-seções compostas ("/" ou "+")
  * Nome – 2x15
  TREINO
  1. Nome – 4x12/12/10/10        <- repetições por série separadas por "/"
  ABDÔMEN
  OBSERVAÇÕES                    <- observações de CADA dia (não do plano)
  * ...
  ⸻ ... (repete por dia)
  ⸻
  CARDIO                         <- blocos informativos finais: título em
  SEGUNDA A SEXTA                   caixa alta logo após "⸻", sem exercícios,
  * ...                             com subtítulos em caixa alta
  ⸻
  DESCANSO ENTRE AS SÉRIES
  * ...
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from parser_meal_plan import SEPARATOR_RE, strip_bold

LABEL_VALUE_RE = re.compile(r"^[➢\-•]?\s*([A-Za-zÀ-ú][\w À-ú]{1,30}):\s*(.*)$")
BULLET_PREFIX_RE = re.compile(r"^[-•*]\s+")
_DAY_NAMES = (
    r"SEGUNDA|TER[ÇC]A|QUARTA|QUINTA|SEXTA|S[ÁA]BADO|DOMINGO|"
    r"MONDAY|TUESDAY|WEDNESDAY|THURSDAY|FRIDAY|SATURDAY|SUNDAY"
)
DAY_HEADER_RE = re.compile(rf"^({_DAY_NAMES})" r"([\s-]*FEIRA)?\s*[-–—]?\s*(.*)$")
# Variante tolerante a "Title Case" (ex.: "Wednesday — Back + Glutes"), usada
# quando a linha não está em CAIXA ALTA: exige o travessão logo após o nome
# do dia para reduzir falsos positivos em texto corrido.
DAY_HEADER_TITLECASE_RE = re.compile(
    rf"^({_DAY_NAMES})" r"([\s-]*FEIRA)?\s*[-–—]\s*(.+)$", re.IGNORECASE
)
EXERCISE_SERIES_RE = re.compile(r"^(.+?)\s*[-–—]\s*(\d+)\s*s[ée]ries?\s*$", re.IGNORECASE)
# Repetições: número, faixa ("10-12") e/ou sequência por série ("12/12/10/10").
EXERCISE_COMPACT_RE = re.compile(
    r"^(.+?)\s*[-–—]\s*(\d+)\s*[x×]\s*"
    r"(\d+(?:\s*[-–—]\s*\d+)?(?:\s*/\s*\d+(?:\s*[-–—]\s*\d+)?)*)\s*(.*)$",
    re.IGNORECASE,
)
REPS_BULLET_LINE_RE = re.compile(r"^\d+(\s*[•·]\s*\d+)+$")


def match_day_header(line: str) -> re.Match | None:
    if is_all_caps_header(line):
        match = DAY_HEADER_RE.match(line.upper())
        if match:
            return match
    return DAY_HEADER_TITLECASE_RE.match(line)

KNOWN_DAY_SUBLABELS = {
    "AQUECIMENTO",
    "ABDÔMEN",
    "ABDOMEN",
    "CARDIO",
    "ATIVAÇÃO",
    "ATIVACAO",
    "TREINO",
}
BARE_OBSERVATIONS = {"OBSERVAÇÕES", "OBSERVACOES"}
KNOWN_FINAL_SECTIONS = {
    "CARDIO SEMANAL",
    "OBSERVAÇÕES IMPORTANTES",
    "OBSERVACOES IMPORTANTES",
} | BARE_OBSERVATIONS


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


def _clean_line(line: str) -> str:
    return BULLET_PREFIX_RE.sub("", strip_bold(line))


def _is_day_sublabel(head: str) -> bool:
    """Sub-seção do dia, simples ("Aquecimento") ou composta
    ("AQUECIMENTO / ATIVAÇÃO")."""
    parts = re.split(r"\s*[/+]\s*", head.strip().upper())
    return all(p in KNOWN_DAY_SUBLABELS for p in parts)


def _is_exercise_line(clean: str) -> bool:
    return bool(EXERCISE_SERIES_RE.match(clean) or EXERCISE_COMPACT_RE.match(clean))


def _is_bare_observations(clean: str) -> bool:
    return _strip_trailing_decoration(clean).upper() in BARE_OBSERVATIONS


def _uses_per_day_observations(lines: list[str]) -> bool:
    """Formato em que cada dia tem seu próprio "OBSERVAÇÕES" (plano da
    Beatriz), em vez de um único bloco de observações no fim: depois de um
    "OBSERVAÇÕES" dentro dos dias ainda aparece outro dia com exercícios."""
    stage = 0  # 0: antes dos dias, 1: nos dias, 2: após OBSERVAÇÕES, 3: dia após OBSERVAÇÕES
    for raw in lines:
        clean = _clean_line(raw.strip())
        if not clean:
            continue
        if stage in (0, 2) and match_day_header(clean):
            stage += 1
        elif stage == 1 and _is_bare_observations(clean):
            stage = 2
        elif stage == 3 and _is_exercise_line(clean):
            return True
    return False


def _block_has_exercises(lines: list[str], start: int) -> bool:
    """Diz se o bloco que começa em `start` (até o próximo separador "⸻")
    tem alguma linha de exercício."""
    for raw in lines[start + 1 :]:
        line = raw.strip()
        if SEPARATOR_RE.match(line):
            return False
        if _is_exercise_line(_clean_line(line)):
            return True
    return False


# ---------------------------------------------------------------------------
# Modelo de dados
# ---------------------------------------------------------------------------


@dataclass
class Field:
    label: str
    value: str


@dataclass
class FreeGroup:
    subtitle: str = ""
    lines: list[str] = field(default_factory=list)


@dataclass
class FreeSection:
    """Bloco de texto livre com título (ex.: "FOCO DO TREINAMENTO",
    "CARDIO", "DESCANSO ENTRE AS SÉRIES"), opcionalmente dividido por
    subtítulos (ex.: "SEGUNDA A SEXTA", "SÁBADO")."""

    title: str
    groups: list[FreeGroup] = field(default_factory=list)

    def add_line(self, line: str) -> None:
        if not self.groups:
            self.groups.append(FreeGroup())
        self.groups[-1].lines.append(line)


@dataclass
class DayItem:
    kind: str  # "label" | "exercise" | "text" | "bullet"
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
    plan_sections: list[FreeSection] = field(default_factory=list)
    days: list[WorkoutDay] = field(default_factory=list)
    weekly_summary_title: str = ""
    weekly_summary_lines: list[str] = field(default_factory=list)
    observations_title: str = ""
    observations_lines: list[str] = field(default_factory=list)
    extra_sections: list[FreeSection] = field(default_factory=list)
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
    per_day_observations = _uses_per_day_observations(lines)
    after_separator = False
    current_plan_section: FreeSection | None = None
    current_free_section: FreeSection | None = None
    in_day_observations = False

    def close_pending_exercise() -> None:
        nonlocal pending_exercise
        pending_exercise = None

    def make_day(day_match: re.Match) -> WorkoutDay:
        day_word = day_match.group(1).capitalize()
        suffix = "-feira" if day_match.group(2) else ""
        return WorkoutDay(day_name=day_word + suffix, focus=day_match.group(3).strip())

    for idx, raw_line in enumerate(lines):
        line = raw_line.strip()

        if not line or SEPARATOR_RE.match(line):
            # Linha em branco/separador: encerra a coleta de reps do
            # exercício atual (mas não muda de fase).
            close_pending_exercise()
            if line:
                after_separator = True
            continue

        block_start = after_separator
        after_separator = False
        clean = _clean_line(line)

        # Formato com "OBSERVAÇÕES" em cada dia: vira sub-seção do dia atual
        # em vez de seção final do documento.
        if (
            phase == "days"
            and per_day_observations
            and not block_start
            and current_day is not None
            and _is_bare_observations(clean)
        ):
            close_pending_exercise()
            current_day.items.append(DayItem(kind="label", label=clean))
            in_day_observations = True
            continue

        # Detecção de seção final, válida assim que estivermos dentro dos
        # dias de treino (também cobre a troca entre "CARDIO SEMANAL" e
        # "Observações Importantes" quando já estamos na fase final).
        if phase in ("days", "final"):
            final_key = _final_section_key(clean)
            if final_key:
                close_pending_exercise()
                phase = "final"
                current_free_section = None
                if "CARDIO" in final_key:
                    plan.weekly_summary_title = clean
                    current_final_lines = plan.weekly_summary_lines
                else:
                    plan.observations_title = clean
                    current_final_lines = plan.observations_lines
                continue

        # Bloco informativo depois dos dias (ex.: "⸻ / CARDIO" com a rotina
        # da semana, "⸻ / DESCANSO ENTRE AS SÉRIES"): título em caixa alta
        # logo após um separador, num bloco sem nenhum exercício.
        if (
            phase in ("days", "final")
            and block_start
            and is_all_caps_header(clean)
            and not match_day_header(clean)
            and not _block_has_exercises(lines, idx)
        ):
            close_pending_exercise()
            phase = "final"
            current_free_section = FreeSection(title=_strip_trailing_decoration(clean))
            plan.extra_sections.append(current_free_section)
            continue

        if phase == "final":
            if current_free_section is not None:
                if is_all_caps_header(clean):
                    current_free_section.groups.append(FreeGroup(subtitle=clean))
                else:
                    current_free_section.add_line(clean)
                continue
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
            # Planos sem título/campos entre o nome do cliente e os dias
            # (vai direto de "Nome do cliente" para "Segunda-feira - ...").
            day_match = match_day_header(clean)
            if day_match:
                current_day = make_day(day_match)
                plan.days.append(current_day)
                phase = "days"
                continue
            # Primeira linha sem "label:" depois do nome do cliente: título
            # do plano (ex.: "PLANO DE TREINO"), possivelmente com traços.
            plan.plan_title = _strip_trailing_decoration(clean)
            phase = "plan_info"
            continue

        if phase == "plan_info":
            day_match = match_day_header(clean)
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
            # Bloco extra no cabeçalho (ex.: "FOCO DO TREINAMENTO" seguido
            # de uma lista): título em caixa alta + as linhas seguintes.
            if is_all_caps_header(clean):
                current_plan_section = FreeSection(title=_strip_trailing_decoration(clean))
                plan.plan_sections.append(current_plan_section)
                continue
            if current_plan_section is not None:
                current_plan_section.add_line(clean)
                continue
            plan.unparsed_warnings.append(
                f"Linha não reconhecida no bloco de informações do plano: \"{clean[:60]}\""
            )
            continue

        # phase == "days"
        day_match = match_day_header(clean)
        if day_match:
            close_pending_exercise()
            in_day_observations = False
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

        if _is_day_sublabel(head_part):
            close_pending_exercise()
            in_day_observations = False
            current_day.items.append(DayItem(kind="label", label=head_part.strip()))
            if remainder.strip():
                current_day.items.append(DayItem(kind="text", text=remainder.strip()))
            continue

        if in_day_observations:
            current_day.items.append(DayItem(kind="bullet", text=clean))
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
