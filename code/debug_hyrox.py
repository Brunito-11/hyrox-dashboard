"""
debug_hyrox.py
==============
Corre em modo invisível (headless), intercepta as chamadas à API
e guarda o HTML da página em ficheiros para análise.

Corre:
    python debug_hyrox.py

Ficheiros gerados:
    debug_requests.txt  — todas as chamadas à API
    debug_page.html     — HTML da página depois de carregar
"""

import time
from pathlib import Path
from playwright.sync_api import sync_playwright

TARGET_URL = "https://results.hyrox.com/season-9/"
OUT_REQUESTS = Path(__file__).parent / "debug_requests.txt"
OUT_HTML     = Path(__file__).parent / "debug_page.html"

api_calls = []

def on_request(request):
    url = request.url
    if any(x in url for x in ["mikatiming", "api", "json", "result", "data", "search", "timing"]):
        line = f"REQUEST  [{request.method}] {url}"
        api_calls.append(line)
        print(f"  {line}")

def on_response(response):
    url = response.url
    ct  = response.headers.get("content-type", "")
    if "json" in ct or any(x in url for x in ["mikatiming", "api", "result", "data", "timing"]):
        try:
            body = response.body()[:300]
            line = f"RESPONSE [{response.status}] {url}\n   CT: {ct}\n   Body: {body}\n"
            api_calls.append(line)
            print(f"  RESPONSE {response.status}: {url}")
            print(f"    {body[:200]}\n")
        except Exception:
            pass

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    page    = browser.new_page()

    page.on("request",  on_request)
    page.on("response", on_response)

    print(f"A carregar {TARGET_URL} ...")
    page.goto(TARGET_URL, wait_until="domcontentloaded")
    print("A aguardar 15s para o JS carregar os resultados...")
    time.sleep(15)

    # Guarda HTML completo
    html = page.content()
    OUT_HTML.write_text(html, encoding="utf-8")
    print(f"\nHTML guardado em: {OUT_HTML} ({len(html)} chars)")

    # Guarda chamadas à API
    OUT_REQUESTS.write_text("\n".join(api_calls), encoding="utf-8")
    print(f"Chamadas à API guardadas em: {OUT_REQUESTS}")

    # Mostra elementos encontrados na página
    print("\n── Elementos na página ──")
    for sel in ["table", "tbody tr", ".list-table", "[class*='result']",
                "[class*='list']", "[class*='row']", "[class*='entry']"]:
        els = page.query_selector_all(sel)
        if els:
            print(f"  {sel:30s} → {len(els)} elementos")
            if sel in ("table", ".list-table"):
                for el in els[:2]:
                    print(f"    class='{el.get_attribute('class') or ''}'")

    browser.close()

print("\nDiagnóstico concluído!")
print(f"Abre o ficheiro debug_requests.txt para ver as chamadas à API.")
