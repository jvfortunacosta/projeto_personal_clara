# Formatador de Planos (Personal Trainer)

Ferramenta local para colar planos alimentares, treinos e check-ins semanais
(texto bruto do WhatsApp) e gerar PDFs formatados.

## Stack

- Backend: FastAPI (Python) + Playwright/Chromium (HTML/CSS → PDF) + Jinja2
- Frontend: HTML/CSS/JS puro, sem build step, servido pelo próprio backend
- Sem banco de dados, sem login — uso local, um documento por vez

## Como rodar

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 -m playwright install chromium   # download único do navegador (~150MB)
uvicorn main:app --reload --port 8000
```

Abra http://localhost:8000 no navegador.

> Trocamos WeasyPrint por Playwright/Chromium porque o WeasyPrint depende de
> bibliotecas nativas (Pango/GObject) instaladas via Homebrew, que nem
> sempre está disponível. O Playwright só precisa do pip install + um
> download único do Chromium, sem dependências de sistema, e dá fidelidade
> total de CSS moderno.

## Estrutura

```
backend/
  main.py               # rotas FastAPI (parse / preview / pdf)
  doc_detect.py          # heurística que decide "plano alimentar" x "treino"
  parser_meal_plan.py    # parser do plano alimentar (texto -> estrutura)
  parser_treino.py       # parser do plano de treino (texto -> estrutura)
  parser_checkin.py      # parser do check-in semanal
  pdf_generator.py       # renderiza os templates Jinja2 e gera PDF via Playwright
templates/
  meal_plan.html / meal_plan.css   # template do PDF de plano alimentar
  treino.html / treino.css         # template do PDF de treino
  checkin.html / checkin.css       # template do PDF de check-in
frontend/
  index.html / style.css / app.js  # interface com as duas abas
```

Os templates HTML/CSS ficam separados do código para facilitar a troca do
visual quando o modelo real de PDF da personal for fornecido — basta editar
o `.css` correspondente (e o `.html`, se a estrutura visual mudar) sem tocar
no parser ou no backend.

## Aba "Plano Alimentar / Treino"

Essa aba aceita os dois formatos de texto (plano alimentar ou treino) e usa
uma heurística (`backend/doc_detect.py`) para decidir automaticamente qual
parser/template aplicar — baseada em palavras-chave como "REFEIÇÃO"/
"escolher 1" (plano alimentar) vs. dias da semana/"séries"/"repetições"
(treino). Há um seletor na interface para forçar um dos dois tipos caso a
detecção erre.

## Estado dos parsers

**Plano alimentar** (`parser_meal_plan.py`): baseado na estrutura descrita
em conversa (título, seções separadas por "⸻", refeições numeradas, blocos
"escolher 1", seções finais de texto livre). Ainda não recebemos um texto
real de plano alimentar colado — os exemplos usados para testar foram
hipotéticos. As regras de reconhecimento estão centralizadas no topo do
arquivo para facilitar ajuste quando um exemplo real chegar.

**Treino** (`parser_treino.py`): baseado em um exemplo real recebido (PDF
"TREINO MARIA HELENA", marca Clara Isabella Personal Trainer). Reconhece:
nome do cliente + campos (peso/altura/idade), bloco de informações do plano
(objetivo/treinos/cardio/tempo total), dias da semana com foco muscular,
exercícios em dois formatos (`Nome - N séries` + linha(s) de repetições, ou
formato compacto `Nome – NxM`), notas/dicas por exercício, seção de cardio
por dia, resumo semanal de cardio e observações finais. O texto original
tinha inconsistências de formatação (ex.: "Aquecimento" às vezes na mesma
linha do equipamento, às vezes em linha separada) — o parser tolera ambos os
casos, mas outras variações ainda não vistas podem exigir ajuste.

Em ambos os parsers, textos que não se encaixarem nos padrões esperados
aparecem sinalizados no próprio PDF (caixa de aviso amarela) em vez de
serem descartados silenciosamente.

## Visual do PDF

O template de treino já foi ajustado para se aproximar da identidade visual
real mostrada no exemplo (barra escura no topo, faixas pretas para títulos
de seção, bullets com seta "➢"). O logo e a marca d'água ainda são
placeholders — quando você tiver o arquivo de logo real, é só trocar o bloco
`.logo-placeholder` em `templates/treino.css`/`meal_plan.css`/`checkin.css`
por uma imagem. Os templates de plano alimentar e check-in ainda usam uma
paleta genérica (verde/azul) — avise se quiser que sigam a mesma identidade
visual do treino.
