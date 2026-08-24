"""Renderização dos templates Jinja2 + geração de PDF via Playwright/Chromium."""

from __future__ import annotations

import base64
from functools import lru_cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from playwright.sync_api import sync_playwright

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
LOGO_PATH = TEMPLATES_DIR / "assets" / "logo.png"

_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(["html"]),
)


@lru_cache(maxsize=1)
def _logo_data_uri() -> str:
    """Logo em data URI (base64), para não depender de resolução de caminho
    relativo dentro do HTML renderizado pelo Playwright. Retorna string
    vazia se o arquivo ainda não existir (templates caem no placeholder)."""
    if not LOGO_PATH.exists():
        return ""
    encoded = base64.b64encode(LOGO_PATH.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def render_html(template_name: str, **context) -> str:
    template = _env.get_template(template_name)
    return template.render(logo_data_uri=_logo_data_uri(), **context)


def html_to_pdf_bytes(html_content: str, css_filename: str) -> bytes:
    css_path = TEMPLATES_DIR / css_filename
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page()
            page.set_content(html_content, wait_until="load")
            page.add_style_tag(path=str(css_path))
            return page.pdf(print_background=True, prefer_css_page_size=True)
        finally:
            browser.close()


def render_meal_plan_pdf(plan, brand_name: str) -> bytes:
    html_content = render_html("meal_plan.html", plan=plan, brand_name=brand_name)
    return html_to_pdf_bytes(html_content, "meal_plan.css")


def render_meal_plan_preview(plan, brand_name: str) -> str:
    html_content = render_html("meal_plan.html", plan=plan, brand_name=brand_name)
    css_content = (TEMPLATES_DIR / "meal_plan.css").read_text(encoding="utf-8")
    return f"<style>{css_content}</style>\n{html_content}"


def render_workout_pdf(plan, brand_name: str) -> bytes:
    html_content = render_html("treino.html", plan=plan, brand_name=brand_name)
    return html_to_pdf_bytes(html_content, "treino.css")


def render_workout_preview(plan, brand_name: str) -> str:
    html_content = render_html("treino.html", plan=plan, brand_name=brand_name)
    css_content = (TEMPLATES_DIR / "treino.css").read_text(encoding="utf-8")
    return f"<style>{css_content}</style>\n{html_content}"


def render_checkin_pdf(checkin, brand_name: str) -> bytes:
    html_content = render_html("checkin.html", checkin=checkin, brand_name=brand_name)
    return html_to_pdf_bytes(html_content, "checkin.css")


def render_checkin_preview(checkin, brand_name: str) -> str:
    html_content = render_html("checkin.html", checkin=checkin, brand_name=brand_name)
    css_content = (TEMPLATES_DIR / "checkin.css").read_text(encoding="utf-8")
    return f"<style>{css_content}</style>\n{html_content}"
