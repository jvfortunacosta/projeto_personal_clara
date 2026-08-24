"""
Parser de check-ins semanais em formato pergunta/resposta.

Suposição (a confirmar): o texto colado alterna entre uma linha de pergunta
e uma ou mais linhas de resposta, em um destes dois formatos:

1) Pergunta em negrito na própria linha, resposta na(s) linha(s) seguinte(s):
     *Peso atual:*
     78kg

2) Pergunta e resposta na mesma linha, separadas por ":":
     Peso atual: 78kg

O parser tenta o formato (1) quando a linha inteira está em negrito; caso
contrário cai para o formato (2) quando há ":" na linha. Linhas que não se
encaixam em nenhum dos dois formatos são anexadas à resposta da pergunta
anterior (útil para respostas em múltiplas linhas).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

BOLD_LINE_RE = re.compile(r"^\*{1,2}(.+?)\*{1,2}\s*:?\s*$")
INLINE_QA_RE = re.compile(r"^([^:]{1,60}):\s*(.+)$")


@dataclass
class QAPair:
    question: str
    answer: str = ""


@dataclass
class CheckIn:
    raw_title: str
    client_name: str
    pairs: list[QAPair] = field(default_factory=list)


def parse_checkin(raw_text: str) -> CheckIn:
    lines = [l.strip() for l in raw_text.replace("\r\n", "\n").split("\n")]
    lines = [l for l in lines if l]

    if not lines:
        return CheckIn(raw_title="", client_name="")

    raw_title = lines[0]
    client_name = raw_title
    body_lines = lines[1:] if len(lines) > 1 else []

    # Se a primeira linha já parecer pergunta/resposta, tratamos como corpo
    # e deixamos o título genérico.
    if BOLD_LINE_RE.match(raw_title) or INLINE_QA_RE.match(raw_title):
        body_lines = lines
        raw_title = "Check-in Semanal"
        client_name = ""

    checkin = CheckIn(raw_title=raw_title, client_name=client_name)
    current: QAPair | None = None

    for line in body_lines:
        bold_match = BOLD_LINE_RE.match(line)
        if bold_match:
            current = QAPair(question=bold_match.group(1).strip().rstrip(":").strip())
            checkin.pairs.append(current)
            continue

        inline_match = INLINE_QA_RE.match(line)
        if inline_match:
            current = QAPair(
                question=inline_match.group(1).strip(),
                answer=inline_match.group(2).strip(),
            )
            checkin.pairs.append(current)
            continue

        if current is not None:
            current.answer = f"{current.answer} {line}".strip()
        else:
            current = QAPair(question="", answer=line)
            checkin.pairs.append(current)

    return checkin
