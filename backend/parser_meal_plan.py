"""
Parser de planos alimentares colados em texto puro (formato WhatsApp).

Suposições assumidas sobre o formato de entrada (a confirmar com exemplos reais):

- Seções (categorias como "HIGH CARB", ou seções finais como "CARDIO") são
  separadas por uma linha contendo apenas o caractere "⸻" (ou sequências de
  "-", "_", "=", "~" repetidas, tratadas como equivalentes).
- Um título em CAIXA ALTA sozinho numa linha, dentro de uma seção, é o nome
  da seção (ex: "HIGH CARB", "CARDIO", "ORIENTAÇÕES").
- Dentro de uma categoria (HIGH CARB / MODERATE-LOW CARB), as refeições
  começam com uma linha "REFEIÇÃO <n> - <nome>" (aceita -, – ou — como
  separador, e ':' opcional).
- Dentro de uma refeição, um bloco "<Categoria> — escolher <n>:" (ex:
  "Proteína — escolher 1:") é seguido por linhas de opção (bullets) até a
  próxima linha em branco dupla, próximo cabeçalho de bloco, ou fim da
  refeição.
- Itens que não pertencem a nenhum bloco "escolher N" são tratados como
  itens fixos da refeição.
- "Opção 1" / "Opção 2" (ou "OU" sozinho numa linha) demarcam variantes
  alternativas completas da mesma refeição.
- Marcações de negrito do WhatsApp usam um ou dois asteriscos (*texto* ou
  **texto**); são removidas ao interpretar rótulos, mas preservadas no
  texto literal dos itens (não removemos negrito no meio de uma frase).
- Seções finais (CARDIO, PASSOS, REFEIÇÃO LIVRE, ORIENTAÇÕES, ...) não têm
  "REFEIÇÃO" dentro e são tratadas como listas de texto livre.

Essas suposições estão isoladas em constantes/regex no topo do arquivo para
facilitar ajuste assim que tivermos um exemplo real colado pela personal.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Regras de reconhecimento (ajustar aqui quando confirmarmos o formato real)
# ---------------------------------------------------------------------------

SEPARATOR_RE = re.compile(r"^(⸻+|[\-_=~*]{2,})$")
BOLD_RE = re.compile(r"\*{1,2}(.+?)\*{1,2}")
MEAL_HEADER_RE = re.compile(
    r"^REFEI[ÇC][ÃA]O\s*(\d+)\s*[-–—:]*\s*(.*)$", re.IGNORECASE
)
CHOICE_GROUP_RE = re.compile(
    r"^(.+?)\s*[-–—]\s*escolher\s*(\d+)\s*:?\s*$", re.IGNORECASE
)
VARIANT_RE = re.compile(r"^op[cç][ãa]o\s*(\d+)\b[:\-–—]*\s*(.*)$", re.IGNORECASE)
BULLET_PREFIX_RE = re.compile(r"^[-•*]\s+")
# Rótulo livre terminando em ":" sem "escolher N" (ex.: "Opção prática:"),
# usado para agrupar itens sem contagem explícita de escolha.
GENERIC_LABEL_RE = re.compile(r"^(.+):\s*$")
# "Label: valor" no preâmbulo do plano (ex.: "Objetivo: reduzir gordura...").
LABEL_VALUE_RE = re.compile(r"^([A-Za-zÀ-ú][\w À-ú]{1,30}):\s*(.+)$")

# Palavras genéricas de "título de documento" (não nome de pessoa), usadas
# para decidir qual dos dois lados de "X — Y" na primeira linha é o nome do
# cliente. A ordem varia entre personals: já vimos tanto "MIGUEL — NOVA FASE
# DE DEFINIÇÃO" (nome primeiro) quanto "PLANO ALIMENTAR — LÍVIA CAETANO"
# (tipo de documento primeiro).
GENERIC_TITLE_WORDS = {
    "PLANO", "ALIMENTAR", "TREINO", "DIETA", "CARDÁPIO", "CARDAPIO",
    "NUTRICIONAL", "NUTRICAO", "NUTRIÇÃO", "FASE", "DEFINIÇÃO", "DEFINICAO",
    "CUTTING", "BULKING", "MANUTENÇÃO", "MANUTENCAO", "HIPERTROFIA",
    "EMAGRECIMENTO", "CYCLING", "CARB", "NOVA", "NOVO", "SEMANA",
    "PROGRAMA", "PROTOCOLO", "META", "INICIAL", "SEMANAL", "MENSAL",
}


def _looks_like_generic_title(segment: str) -> bool:
    words = re.findall(r"[A-ZÀ-Ú]+", segment.upper())
    if not words:
        return False
    hits = sum(1 for w in words if w in GENERIC_TITLE_WORDS)
    return hits > 0 and hits >= len(words) / 2

# Nomes de seções finais conhecidas (texto livre, sem refeições numeradas).
KNOWN_FREE_SECTIONS = {
    "CARDIO",
    "PASSOS",
    "REFEIÇÃO LIVRE",
    "REFEICAO LIVRE",
    "ORIENTAÇÕES",
    "ORIENTACOES",
    "OBSERVAÇÕES",
    "OBSERVACOES",
}


def strip_bold(text: str) -> str:
    """Remove marcadores de negrito (*texto* ou **texto**) preservando o conteúdo."""
    return BOLD_RE.sub(r"\1", text).strip()


def is_all_caps_header(line: str) -> bool:
    """
    Heurística: linha "de cabeçalho" = sem letras minúsculas, tem pelo menos
    uma letra, e não é uma linha de bullet.
    """
    if not line or BULLET_PREFIX_RE.match(line):
        return False
    letters = [c for c in line if c.isalpha()]
    if not letters:
        return False
    return all(c.isupper() for c in letters)


# ---------------------------------------------------------------------------
# Modelo de dados
# ---------------------------------------------------------------------------


@dataclass
class Field:
    label: str
    value: str


@dataclass
class ChoiceGroup:
    label: str
    choose_count: int | None  # None quando não há "escolher N" explícito
    options: list[str] = field(default_factory=list)


@dataclass
class MealVariant:
    label: str | None  # ex.: "Opção 1", None se for a única variante
    # Itens fixos (str) e grupos "escolher N" (ChoiceGroup) na MESMA lista,
    # na ordem em que aparecem no texto original — importante porque um
    # item fixo pode vir depois de um ou mais grupos de escolha (ex.: um
    # "+" com um item extra após "Proteína"/"Carboidrato").
    blocks: list = field(default_factory=list)


@dataclass
class Meal:
    number: int
    name: str
    variants: list[MealVariant] = field(default_factory=list)


@dataclass
class Category:
    name: str
    description: str = ""
    meals: list[Meal] = field(default_factory=list)


@dataclass
class FreeSection:
    name: str
    lines: list[str] = field(default_factory=list)


@dataclass
class MealPlan:
    raw_title: str
    client_name: str
    phase: str
    subtitle: str = ""  # ex.: "CARB CYCLING"
    intro_fields: list[Field] = field(default_factory=list)  # ex.: "Objetivo: ..."
    intro_lines: list[str] = field(default_factory=list)
    categories: list[Category] = field(default_factory=list)
    free_sections: list[FreeSection] = field(default_factory=list)
    unparsed_warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def _split_sections(lines: list[str]) -> tuple[list[str], list[list[str]]]:
    """
    Divide as linhas em (linhas do preâmbulo/título, [blocos de seção]).
    Cada bloco de seção é a lista de linhas entre dois separadores.
    """
    blocks: list[list[str]] = [[]]
    for line in lines:
        if SEPARATOR_RE.match(line.strip()):
            blocks.append([])
        else:
            blocks[-1].append(line)

    # Remove blocos totalmente vazios (separadores consecutivos)
    blocks = [b for b in blocks if any(l.strip() for l in b)]

    if not blocks:
        return [], []

    preamble = blocks[0]
    sections = blocks[1:]
    return preamble, sections


def _parse_preamble(
    preamble_lines: list[str],
) -> tuple[str, str, str, str, list[Field], list[str]]:
    """
    Interpreta as linhas antes do primeiro separador: título/nome do
    cliente (1ª linha), e opcionalmente um subtítulo em caixa alta (ex.:
    "CARB CYCLING") e/ou linhas "Label: valor" (ex.: "Objetivo: ...").
    """
    text_lines = [l.strip() for l in preamble_lines if l.strip()]
    if not text_lines:
        return "", "", "", "", [], []

    raw_title = strip_bold(text_lines[0])
    client_name, phase = raw_title, ""
    for sep in (" — ", " – ", " - "):
        if sep in raw_title:
            part_a, part_b = raw_title.split(sep, 1)
            part_a, part_b = part_a.strip(), part_b.strip()
            # O nome do cliente pode vir antes ou depois do separador,
            # dependendo de como a personal escreve o título. O lado que
            # "parece" um título genérico de documento (ex.: "PLANO
            # ALIMENTAR") não é o nome — o outro lado é.
            if _looks_like_generic_title(part_a) and not _looks_like_generic_title(part_b):
                client_name, phase = part_b, part_a
            else:
                client_name, phase = part_a, part_b
            break

    subtitle = ""
    intro_fields: list[Field] = []
    intro_lines: list[str] = []
    for raw_line in text_lines[1:]:
        line = strip_bold(raw_line)
        label_match = LABEL_VALUE_RE.match(line)
        if label_match:
            intro_fields.append(
                Field(label=label_match.group(1).strip(), value=label_match.group(2).strip())
            )
        elif is_all_caps_header(line) and not subtitle:
            subtitle = line
        else:
            intro_lines.append(line)

    return raw_title, client_name, phase, subtitle, intro_fields, intro_lines


def _parse_meal_block(meal_lines: list[str]) -> list[MealVariant]:
    """Interpreta o corpo de uma refeição (após a linha REFEIÇÃO N - nome)."""
    variants: list[MealVariant] = []
    current = MealVariant(label=None)
    variants.append(current)
    current_group: ChoiceGroup | None = None

    for raw_line in meal_lines:
        line = raw_line.strip()
        if not line:
            # Linha em branco encerra o grupo "escolher N" atual, mas só se
            # ele já tiver opções coletadas — o cabeçalho do grupo (ex.:
            # "Proteína — escolher 1:") costuma vir seguido de uma linha em
            # branco ANTES da lista de opções, então não podemos encerrar o
            # grupo nesse momento. Depois que o grupo já tem conteúdo, uma
            # linha em branco indica que o que vem a seguir é outra coisa
            # (outro grupo, ou um item fixo avulso).
            if current_group is not None and current_group.options:
                current_group = None
            continue

        stripped_bold = strip_bold(line)

        if stripped_bold == "+":
            # "+" sozinho apenas introduz um item extra fixo depois de um
            # ou mais grupos "escolher N" (ex.: "+ 150g de legumes"); não é
            # conteúdo em si, só encerra o grupo de escolha atual.
            current_group = None
            continue

        if stripped_bold.upper() == "OU":
            # "OU" sozinho numa linha normalmente separa dois blocos
            # "Opção N" explícitos (tratados abaixo). Não criamos uma
            # variante aqui para não gerar uma "Opção" vazia no meio do
            # plano — apenas encerramos o grupo de escolha atual.
            current_group = None
            continue

        variant_match = VARIANT_RE.match(stripped_bold)
        if variant_match:
            current = MealVariant(label=f"Opção {variant_match.group(1)}")
            variants.append(current)
            current_group = None
            continue

        group_match = CHOICE_GROUP_RE.match(stripped_bold)
        if group_match:
            current_group = ChoiceGroup(
                label=group_match.group(1).strip(),
                choose_count=int(group_match.group(2)),
            )
            current.blocks.append(current_group)
            continue

        if BULLET_PREFIX_RE.match(line):
            item = strip_bold(BULLET_PREFIX_RE.sub("", line))
            if current_group is not None:
                current_group.options.append(item)
            else:
                current.blocks.append(item)
            continue

        generic_label_match = GENERIC_LABEL_RE.match(stripped_bold)
        if generic_label_match:
            # Rótulo livre terminando em ":" sem "escolher N" explícito
            # (ex.: "Opção prática:") — agrupa os itens seguintes sob esse
            # rótulo em vez de misturá-los soltos na lista de itens fixos.
            current_group = ChoiceGroup(
                label=generic_label_match.group(1).strip(), choose_count=None
            )
            current.blocks.append(current_group)
            continue

        # Linha sem marcador de bullet e sem bater em nenhum padrão:
        # tratamos como item fixo em texto livre (ex: observação da refeição).
        if current_group is not None:
            current_group.options.append(stripped_bold)
        else:
            current.blocks.append(stripped_bold)

    # Remove variantes vazias (ex.: geradas por um "OU" solto sem conteúdo).
    variants = [v for v in variants if v.blocks]
    if not variants:
        variants = [MealVariant(label=None)]
    return variants


def _parse_category_section(name: str, lines: list[str]) -> Category:
    category = Category(name=name)
    preamble_lines: list[str] = []
    current_meal_lines: list[str] = []
    current_meal_number: int | None = None
    current_meal_name: str = ""
    seen_first_meal = False

    def flush():
        nonlocal current_meal_lines, current_meal_number, current_meal_name
        if current_meal_number is not None:
            variants = _parse_meal_block(current_meal_lines)
            category.meals.append(
                Meal(
                    number=current_meal_number,
                    name=current_meal_name,
                    variants=variants,
                )
            )
        current_meal_lines = []

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            if seen_first_meal:
                # Preserva a linha em branco (usada por _parse_meal_block
                # para encerrar grupos "escolher N") em vez de descartá-la.
                current_meal_lines.append(raw_line)
            continue
        header_match = MEAL_HEADER_RE.match(strip_bold(line))
        if header_match:
            flush()
            seen_first_meal = True
            current_meal_number = int(header_match.group(1))
            current_meal_name = header_match.group(2).strip()
            continue
        if not seen_first_meal:
            # Texto descritivo da categoria, antes da primeira refeição
            # (ex.: "Usar nos dias de treinos mais pesados: ...").
            preamble_lines.append(strip_bold(line))
            continue
        current_meal_lines.append(raw_line)

    flush()
    category.description = " ".join(preamble_lines)
    return category


def _parse_free_section(name: str, lines: list[str]) -> FreeSection:
    items: list[str] = []
    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        if BULLET_PREFIX_RE.match(line):
            items.append(strip_bold(BULLET_PREFIX_RE.sub("", line)))
        else:
            items.append(strip_bold(line))
    return FreeSection(name=name, lines=items)


def _build_single_meal(header_line: str, body_lines: list[str]) -> Meal:
    header_match = MEAL_HEADER_RE.match(strip_bold(header_line.strip()))
    number = int(header_match.group(1))
    name = header_match.group(2).strip()
    variants = _parse_meal_block(body_lines)
    return Meal(number=number, name=name, variants=variants)


def parse_meal_plan(raw_text: str) -> MealPlan:
    """
    Interpreta o texto bruto colado.

    Cada bloco de texto entre duas linhas separadoras ("⸻" ou similar) pode
    representar, na prática, coisas diferentes dependendo de como a personal
    formata (não temos ainda um exemplo real 100% confirmado):

      (a) um cabeçalho de categoria "solto" (ex.: só a linha "HIGH CARB"),
          seguido, em blocos separados, por cada refeição individualmente;
      (b) um bloco único contendo o cabeçalho da categoria E todas as suas
          refeições juntas, sem separador entre elas;
      (c) uma refeição "solta" (bloco começando com "REFEIÇÃO N - ..."),
          pertencente à categoria mais recente já vista;
      (d) uma seção final de texto livre (CARDIO, PASSOS, ORIENTAÇÕES...).

    Tratamos os quatro casos com uma pequena máquina de estados abaixo,
    mantendo a "categoria atual" enquanto percorremos os blocos.
    """
    # Normaliza quebras de linha e remove espaços à direita.
    lines = [l.rstrip() for l in raw_text.replace("\r\n", "\n").split("\n")]

    preamble, section_blocks = _split_sections(lines)
    raw_title, client_name, phase, subtitle, intro_fields, intro_lines = _parse_preamble(
        preamble
    )

    plan = MealPlan(
        raw_title=raw_title,
        client_name=client_name,
        phase=phase,
        subtitle=subtitle,
        intro_fields=intro_fields,
        intro_lines=intro_lines,
    )
    current_category: Category | None = None

    for block in section_blocks:
        text_lines = [l for l in block if l.strip()]
        if not text_lines:
            continue

        first = strip_bold(text_lines[0].strip())
        rest = text_lines[1:]

        # Corpo do bloco preservando linhas em branco (usadas para separar
        # um grupo "escolher N" de um item fixo avulso logo depois).
        header_idx = next(i for i, l in enumerate(block) if l.strip())
        rest_raw = block[header_idx + 1 :]

        # (c) Bloco solto de refeição -> entra na categoria atual. Quando não
        # há categoria nenhuma (plano sem divisão em categorias, o caso mais
        # comum fora de carb cycling), usamos um nome vazio: o template não
        # desenha a faixa preta de categoria nesse caso.
        if MEAL_HEADER_RE.match(first):
            if current_category is None:
                current_category = Category(name="")
                plan.categories.append(current_category)
            current_category.meals.append(_build_single_meal(first, rest_raw))
            continue

        if is_all_caps_header(first):
            normalized_name = first.upper()
            has_meal_header_in_rest = any(
                MEAL_HEADER_RE.match(strip_bold(l.strip())) for l in rest
            )

            # (d) Seção final de texto livre conhecida.
            if normalized_name in KNOWN_FREE_SECTIONS:
                plan.free_sections.append(_parse_free_section(first, rest))
                current_category = None
                continue

            # (b) Categoria com as refeições já no mesmo bloco.
            if has_meal_header_in_rest:
                current_category = _parse_category_section(first, rest_raw)
                plan.categories.append(current_category)
                continue

            # (a) Cabeçalho de categoria sozinho no bloco.
            if not rest:
                current_category = Category(name=first)
                plan.categories.append(current_category)
                continue

            # Cabeçalho em caixa alta sem refeições numeradas dentro: é uma
            # seção de texto livre legítima (a personal usa nomes de seção
            # variados — CARDIO, PIPOCA, HIDRATAÇÃO, SUPLEMENTAÇÃO, etc. —
            # não dá pra prever todos, então qualquer cabeçalho em caixa
            # alta sem refeições numeradas vira texto livre silenciosamente,
            # sem gerar aviso).
            plan.free_sections.append(_parse_free_section(first, rest))
            continue

        # Bloco sem cabeçalho reconhecível: não descartamos, sinalizamos.
        plan.free_sections.append(_parse_free_section("SEÇÃO SEM TÍTULO", text_lines))
        plan.unparsed_warnings.append(
            f"Bloco sem cabeçalho em caixa alta identificado, começando com: "
            f"\"{first[:60]}\""
        )

    return plan
