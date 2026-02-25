"""
fetch_hyrox.py
==============
Recolhe resultados HYROX da plataforma MikaTiming — SEM browser.

Abordagem:
  1. Chama getSearchFields (JSON) para obter a lista de eventos e códigos.
  2. Faz GET à página de resultados (HTML) para cada evento/sexo.
  3. Extrai os atletas dos <li class="list-group-item"> e pagina com &page=N.

Corre:
    python fetch_hyrox.py
"""

import csv
import json
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# ── Configuração ───────────────────────────────────────────────────────────────

SEASON_BASES = [
    ("Season 1", "https://results.hyrox.com/season-1/"),
    ("Season 2", "https://results.hyrox.com/season-2/"),
    ("Season 3", "https://results.hyrox.com/season-3/"),
    ("Season 4", "https://results.hyrox.com/season-4/"),
    ("Season 5", "https://results.hyrox.com/season-5/"),
    ("Season 6", "https://results.hyrox.com/season-6/"),
    ("Season 7", "https://results.hyrox.com/season-7/"),
    ("Season 8", "https://results.hyrox.com/season-8/"),
]

OUTPUT_FILE   = Path(__file__).parent / "hyrox_results.csv"
PER_PAGE      = 25          # O site mostra 25 resultados por página
MAX_PAGES     = 4           # Máximo de páginas por evento/sexo (4×25 = top 100)
REQUEST_DELAY = 1.0         # Pausa entre pedidos (em segundos)
ONLY_OPEN     = True        # Apenas categoria HYROX Open (não PRO/Doubles/etc.)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# Prefixos dos códigos de evento → nome da categoria
CATEGORY_PREFIXES = {
    "HPRO_": "HYROX PRO",
    "HDP_":  "HYROX PRO DOUBLES",
    "HD_":   "HYROX DOUBLES",
    "HMR_":  "HYROX TEAM RELAY",
    "HA_":   "HYROX ADAPTIVE",
    "HY1_":  "HYROX YOUNGSTARS",
    "HG_":   "HYROX GORUCK",
    "HE_":   "HYROX ELITE",
    "WCHE":  "WCHE ELITE",
    "H_":    "HYROX",          # Open — deve ser o último (prefixo mais curto)
}

# API usa "M" e "W" (não "F") — apenas Males
GENDERS = [("M", "Men")]

FIELDNAMES = [
    "season", "event_main_group", "event_code", "event_label",
    "category", "gender",
    "rank", "athlete", "nationality", "age_group",
    "total_time",
]

# ── Funções auxiliares ────────────────────────────────────────────────────────

def polite_get(url: str, params: dict = None, **kwargs) -> requests.Response:
    """GET com pausa para não sobrecarregar o servidor."""
    time.sleep(REQUEST_DELAY)
    r = requests.get(url, params=params, headers=HEADERS, timeout=30, **kwargs)
    r.raise_for_status()
    return r


def category_from_code(code: str) -> str:
    for prefix, name in CATEGORY_PREFIXES.items():
        if code.upper().startswith(prefix):
            return name
    return "HYROX"


# ── Passo 1: obter lista de eventos via JSON API ─────────────────────────────

def get_event_groups(base_url: str) -> list[dict]:
    """Chama getSearchFields para obter event_main_group e events."""
    r = polite_get(f"{base_url}index.php", params={
        "content": "ajax2",
        "func": "getSearchFields",
        "options[lang]": "EN_CAP",
        "options[pid]": "start",
    })
    try:
        data = r.json()
    except Exception:
        return []

    # Navegar: branches.lists.fields.event_main_group.data
    try:
        emg_data = data["branches"]["lists"]["fields"]["event_main_group"]["data"]
    except (KeyError, TypeError):
        return []

    return [{"value": item["v"][0], "text": item["v"][1]} for item in emg_data if item.get("v")]


def get_event_codes(base_url: str, event_main_group: str) -> list[dict]:
    """Chama getSearchFields para um evento específico → devolve event codes."""
    r = polite_get(f"{base_url}index.php", params={
        "content": "ajax2",
        "func": "getSearchFields",
        "options[b][lists][event_main_group]": event_main_group,
        "options[b][lists][event]": "",
        "options[b][lists][ranking]": "time_finish_netto",
        "options[lang]": "EN_CAP",
        "options[pid]": "start",
    })
    try:
        data = r.json()
    except Exception:
        return []

    # Navegar: branches.lists.fields.event.data  OU  .event  directo
    try:
        ev_data = data["branches"]["lists"]["fields"]["event"]["data"]
    except (KeyError, TypeError):
        # Tentar no topo do JSON
        try:
            ev_data = data["event"]["data"]
        except (KeyError, TypeError):
            return []

    result = []
    for item in ev_data:
        v = item.get("v")
        if v and len(v) >= 2:
            result.append({"value": v[0], "text": v[1]})
    return result


# ── Passo 2: obter e parsear página de resultados ────────────────────────────

def get_results_page(base_url: str, event_main_group: str,
                     event_code: str, sex: str, page: int = 1) -> requests.Response:
    """Faz GET à página de resultados (HTML)."""
    return polite_get(base_url, params={
        "event": event_code,
        "event_main_group": event_main_group,
        "pid": "list",
        "pidp": "ranking_nav",
        "ranking": "time_finish_netto",
        "search[sex]": sex,
        "page": page,
    })


def parse_total_count(soup: BeautifulSoup) -> int:
    """Extrai o total de resultados, ex: '1883 Results'."""
    el = soup.find(class_="list-info__text str_num")
    if el:
        m = re.search(r"(\d[\d,]*)", el.get_text())
        if m:
            return int(m.group(1).replace(",", ""))
    return 0


def parse_result_rows(soup: BeautifulSoup) -> list[dict]:
    """Extrai linhas de atletas dos <li class='list-group-item row'>."""
    rows = soup.find_all("li", class_=lambda c: c and "list-group-item" in c and "row" in c)
    athletes = []
    for row in rows:
        # Remover labels de mobile (visible-xs, visible-sm)
        for label in row.find_all(class_=re.compile(r"visible-xs|visible-sm")):
            label.decompose()

        rank_el  = row.find(class_=re.compile(r"place-primary"))
        name_el  = row.find(class_=re.compile(r"type-fullname"))
        nat_el   = row.find("span", class_="nation__abbr")
        age_el   = row.find(class_=re.compile(r"type-age_class"))
        time_el  = row.find(class_=re.compile(r"type-time"))

        rank = rank_el.get_text(strip=True) if rank_el else ""
        name = name_el.get_text(strip=True) if name_el else ""
        nat  = nat_el.get_text(strip=True) if nat_el else ""
        age  = age_el.get_text(strip=True) if age_el else ""
        tot  = time_el.get_text(strip=True) if time_el else ""

        # A primeira row pode ser o header ("Rank", "Name", etc.)
        if rank.lower() in ("rank", ""):
            continue
        if not name:
            continue

        athletes.append({
            "rank": rank,
            "athlete": name,
            "nationality": nat,
            "age_group": age,
            "total_time": tot,
        })
    return athletes


# ── Passo 3: recolher tudo ────────────────────────────────────────────────────

def load_done_keys(filepath: Path) -> set:
    """Carrega combinações já recolhidas (event_code, gender)."""
    done = set()
    if filepath.exists():
        with open(filepath, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                done.add((row.get("event_code", ""), row.get("gender", "")))
    return done


def scrape_combo(base_url, season, event_main_group, event_code,
                 event_label, category, gender, done_keys, writer, csvfile):
    key = (event_code, gender)
    if key in done_keys:
        print(f"      [skip] Já feito: {event_label} / {gender}")
        return

    print(f"      A recolher: {event_label} / {category} / {gender} ...", end=" ", flush=True)

    # Página 1 — obter total e primeiros resultados
    try:
        r = get_results_page(base_url, event_main_group, event_code, gender, page=1)
    except Exception as e:
        print(f"ERRO: {e}")
        return

    soup = BeautifulSoup(r.text, "html.parser")
    total_count = parse_total_count(soup)
    if total_count == 0:
        print("0 resultados")
        return

    total_pages = (total_count + PER_PAGE - 1) // PER_PAGE
    fetch_pages = min(total_pages, MAX_PAGES)
    print(f"{total_count} resultados ({total_pages} págs, a recolher {fetch_pages})")

    collected = 0

    for page_num in range(1, fetch_pages + 1):
        if page_num > 1:
            try:
                r = get_results_page(base_url, event_main_group, event_code, gender, page=page_num)
            except Exception as e:
                print(f"        Erro pág. {page_num}: {e}")
                break
            soup = BeautifulSoup(r.text, "html.parser")

        athletes = parse_result_rows(soup)
        for a in athletes:
            writer.writerow({
                "season": season,
                "event_main_group": event_main_group,
                "event_code": event_code,
                "event_label": event_label,
                "category": category,
                "gender": gender,
                **a,
            })
        csvfile.flush()
        collected += len(athletes)

        if page_num % 10 == 0:
            print(f"        ... pág. {page_num}/{total_pages} ({collected} recolhidos)")

    done_keys.add(key)
    print(f"        -> {collected} linhas guardadas")


def main():
    done_keys = load_done_keys(OUTPUT_FILE)
    print(f"Já recolhidos: {len(done_keys)} combinações (serão ignoradas).\n")

    write_header = not OUTPUT_FILE.exists() or OUTPUT_FILE.stat().st_size == 0

    with open(OUTPUT_FILE, "a", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=FIELDNAMES, extrasaction="ignore")
        if write_header:
            writer.writeheader()

        for season, base_url in SEASON_BASES:
            print(f"\n{'='*60}")
            print(f"{season}  ({base_url})")
            print(f"{'='*60}")

            # ── Obter lista de event_main_groups ─────────────────────────
            try:
                event_groups = get_event_groups(base_url)
            except Exception as e:
                print(f"  Erro ao carregar eventos: {e}")
                continue

            if not event_groups:
                print(f"  Nenhum evento encontrado (temporada inactiva?).")
                continue

            print(f"  {len(event_groups)} eventos encontrados")

            # ── Para cada evento (cidade/ano) ────────────────────────────
            for eg in event_groups:
                emg_value = eg["value"]
                emg_text  = eg["text"]
                print(f"\n  [{emg_text}]")

                # Obter event codes via getSearchFields
                try:
                    event_opts = get_event_codes(base_url, emg_value)
                except Exception as e:
                    print(f"    Erro event codes: {e}")
                    continue

                if not event_opts:
                    print(f"    Sem códigos de evento")
                    continue

                # Filtrar apenas HYROX Open se ONLY_OPEN=True
                if ONLY_OPEN:
                    event_opts = [o for o in event_opts
                                  if category_from_code(o["value"]) == "HYROX"]

                if not event_opts:
                    print(f"    Sem eventos Open — a ignorar")
                    continue

                # Preferir OVERALL (resultados globais combinados de vários dias)
                overall = [o for o in event_opts if "OVERALL" in o["value"].upper()]
                non_overall = [o for o in event_opts if "OVERALL" not in o["value"].upper()]

                # Se existem OVERALL, usar esses; se não, usar todos
                use_opts = overall if overall else non_overall
                print(f"    Eventos: {[o['text'] for o in use_opts]}")

                for ev in use_opts:
                    ev_code     = ev["value"]
                    ev_label    = ev["text"]
                    ev_category = category_from_code(ev_code)

                    for sex_code, sex_label in GENDERS:
                        scrape_combo(
                            base_url, season, emg_value, ev_code,
                            ev_label, ev_category, sex_code,
                            done_keys, writer, csvfile,
                        )

    print(f"\nConcluído! Dados guardados em {OUTPUT_FILE}")


if __name__ == "__main__":
    main()