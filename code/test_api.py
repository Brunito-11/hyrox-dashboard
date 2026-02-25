"""
test_api.py — Testa a API MikaTiming e guarda as respostas em ficheiros.
Corre: python test_api.py
"""
import requests
from pathlib import Path

BASE = "https://results.hyrox.com/season-8/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "X-Requested-With": "XMLHttpRequest",
}

def fetch(url, params=None, label=""):
    r = requests.get(url, params=params, headers=HEADERS, timeout=20)
    print(f"\n── {label} ──")
    print(f"  URL:    {r.url[:120]}")
    print(f"  Status: {r.status_code}")
    print(f"  CT:     {r.headers.get('content-type','')}")
    print(f"  Tamanho: {len(r.text)} chars")
    print(f"  Início:  {r.text[:400]}")
    return r.text

# 1. Página HTML principal
html = fetch(BASE, label="Página HTML principal")
Path("test_page.html").write_text(html, encoding="utf-8")
print(f"  <select> encontrados: {html.count('<select')}")

# 2. getSearchFields sem evento
txt = fetch(BASE, params={
    "content": "ajax2",
    "func": "getSearchFields",
    "options[lang]": "EN_CAP",
    "options[pid]": "start",
}, label="getSearchFields (sem evento)")
Path("test_fields_empty.txt").write_text(txt, encoding="utf-8")

# 3. getSearchFields com evento (Taipei 2026 descoberto no debug)
txt = fetch(BASE, params={
    "content": "ajax2",
    "func": "getSearchFields",
    "options[b][lists][event_main_group]": "2026 Taipei",
    "options[b][lists][event]": "ALL_EVENT_GROUP_2026",
    "options[b][lists][ranking]": "time_finish_netto",
    "options[b][lists][sex]": "",
    "options[lang]": "EN_CAP",
    "options[pid]": "start",
}, label="getSearchFields (com evento Taipei 2026)")
Path("test_fields_taipei.txt").write_text(txt, encoding="utf-8")
print(f"  <select> encontrados: {txt.count('<select')}")

# 4. Tenta index.php
txt = fetch(f"{BASE}index.php", params={
    "content": "ajax2",
    "func": "getSearchFields",
    "options[lang]": "EN_CAP",
    "options[pid]": "start",
}, label="index.php getSearchFields")
Path("test_indexphp.txt").write_text(txt, encoding="utf-8")

print("\n\nFicheiros gerados: test_page.html, test_fields_empty.txt, test_fields_taipei.txt, test_indexphp.txt")