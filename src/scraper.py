#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unidad 1 - Extraccion y procesamiento de texto
Extraccion de metadatos y sinopsis de Lectulandia con Playwright + BeautifulSoup.

Version de linea de comandos del notebook `scraper_lectulandia_colab.ipynb`.
Usa la API sincronica de Playwright, que es la adecuada fuera de un notebook.

Uso:
    python src/scraper.py                     # 100 libros de la categoria por defecto
    python src/scraper.py --n 60              # cantidad distinta
    python src/scraper.py --no-headless       # mostrando la ventana del navegador

Solo se extraen metadatos y sinopsis publicas. No se descargan libros,
ni archivos EPUB, PDF u otros contenidos.
"""

import argparse
import csv
import random
import re
import sys
import time
from datetime import date
from pathlib import Path
from urllib.parse import urljoin, urlparse

import pandas as pd
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

# --------------------------------------------------------------------------- #
# Configuracion
# --------------------------------------------------------------------------- #
BASE_URL = "https://ww3.lectulandia.co"
CATEGORIA_NOMBRE = "Thriller / Intriga"
CATEGORIA_URL = "https://ww3.lectulandia.co/genero/intriga/"

N_LIBROS_OBJETIVO = 100        # la Parte 2 exige entre 50 y 100 fichas
MAX_PAGINAS = 25               # tope de paginas de listado a recorrer
PAUSA_MIN, PAUSA_MAX = 1.5, 3.0  # pausa aleatoria entre visitas, en segundos
TIMEOUT_MS = 45_000            # tiempo maximo de espera por pagina
VALOR_FALTANTE = ""            # representacion consistente de campos ausentes

RAIZ = Path(__file__).resolve().parent.parent
DATA_DIR = RAIZ / "data"
CSV_PARCIAL = DATA_DIR / "libros_parcial.csv"   # guardado incremental
CSV_FINAL = DATA_DIR / "libros.csv"             # entregable

COLUMNAS = [
    "titulo", "autores", "generos", "serie", "sinopsis",
    "url_libro", "categoria_origen", "fecha_extraccion", "url_portada",
]
FECHA_EXTRACCION = date.today().isoformat()

USER_AGENT = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")


# --------------------------------------------------------------------------- #
# Limpieza de texto
# --------------------------------------------------------------------------- #
ESPACIOS = re.compile(r"\s+")


def limpiar(texto):
    """Colapsa espacios y saltos de linea, y recorta los extremos.

    Devuelve VALOR_FALTANTE ("") cuando no hay texto util, de modo que todos los
    campos ausentes del dataset se representen siempre de la misma manera.
    """
    if texto is None:
        return VALOR_FALTANTE
    texto = str(texto).replace("\xa0", " ")     # espacio duro -> espacio normal
    return ESPACIOS.sub(" ", texto).strip()


def unir(valores, sep="; "):
    """Une una lista de valores (autores, generos) en un solo campo del CSV."""
    limpios = [limpiar(v) for v in valores]
    limpios = [v for v in limpios if v]
    return sep.join(dict.fromkeys(limpios)) or VALOR_FALTANTE


# --------------------------------------------------------------------------- #
# Analisis del HTML con BeautifulSoup
# --------------------------------------------------------------------------- #
# Una ficha de libro tiene una ruta del tipo /book/<slug>/ (o /libro/<slug>/)
RE_FICHA = re.compile(r"^/(?:book|libro)/[^/]+/?$")


def extraer_urls_listado(html, base=BASE_URL):
    """Devuelve las URL absolutas y sin repetir de las fichas de una pagina."""
    soup = BeautifulSoup(html, "lxml")
    urls = []
    for a in soup.select("a[href]"):
        href = a["href"].split("?")[0].split("#")[0]   # sin query ni fragmento
        absoluta = urljoin(base, href)
        if RE_FICHA.match(urlparse(absoluta).path):
            urls.append(absoluta)
    return list(dict.fromkeys(urls))                   # sin duplicados, en orden


def url_pagina(n):
    """URL de la n-esima pagina del listado de la categoria."""
    return CATEGORIA_URL if n == 1 else f"{CATEGORIA_URL.rstrip('/')}/page/{n}/"


def _bloque(soup, id_div):
    """Devuelve el <div id="..."> sin su rotulo (<span class="tagTitle">)."""
    div = soup.find("div", id=id_div)
    if div is None:
        return None
    for span in div.select("span.tagTitle"):
        span.decompose()          # elimina "Autor:", "Generos:", etc.
    return div


def _valores_enlazados(soup, id_div):
    """Texto de los <a> de un bloque (autores, generos, serie), unidos con '; '."""
    div = _bloque(soup, id_div)
    if div is None:
        return VALOR_FALTANTE
    enlaces = [a.get_text() for a in div.select("a")]
    return unir(enlaces) if enlaces else limpiar(div.get_text())


def parsear_ficha(html, url):
    """Extrae los metadatos y la sinopsis de una ficha. Devuelve un dict-fila."""
    soup = BeautifulSoup(html, "lxml")

    # Titulo:  <div id="title"><h1>...</h1></div>   (plan B: primer <h1>)
    div_titulo = soup.find("div", id="title")
    titulo = limpiar(div_titulo.get_text()) if div_titulo else VALOR_FALTANTE
    if not titulo:
        h1 = soup.find("h1")
        titulo = limpiar(h1.get_text()) if h1 else VALOR_FALTANTE

    # Autores / generos / serie: enlaces dentro de su <div id="...">
    autores = _valores_enlazados(soup, "autor")
    generos = _valores_enlazados(soup, "genero")
    serie = _valores_enlazados(soup, "serie")

    # Sinopsis: <div id="sinopsis"> con uno o varios <p>
    sinopsis = VALOR_FALTANTE
    div_sinopsis = _bloque(soup, "sinopsis")
    if div_sinopsis is not None:
        parrafos = [limpiar(p.get_text()) for p in div_sinopsis.find_all("p")]
        parrafos = [p for p in parrafos if p]
        sinopsis = " ".join(parrafos) if parrafos else limpiar(div_sinopsis.get_text())
        if sinopsis.lower().startswith("sinopsis"):      # rotulo suelto
            sinopsis = limpiar(sinopsis[len("sinopsis"):])
    if not sinopsis:                                     # plan B
        meta = soup.find("meta", attrs={"name": "description"})
        sinopsis = limpiar(meta.get("content")) if meta else VALOR_FALTANTE

    # Portada (campo opcional): solo la URL de la imagen
    url_portada = VALOR_FALTANTE
    img = soup.select_one("div#cover img, .thumbnail img, article img")
    if img and img.get("src"):
        url_portada = urljoin(BASE_URL, img["src"])

    return {
        "titulo": titulo,
        "autores": autores,
        "generos": generos,
        "serie": serie,
        "sinopsis": sinopsis,
        "url_libro": url,
        "categoria_origen": CATEGORIA_NOMBRE,
        "fecha_extraccion": FECHA_EXTRACCION,
        "url_portada": url_portada,
    }


# --------------------------------------------------------------------------- #
# Navegacion con Playwright y persistencia incremental
# --------------------------------------------------------------------------- #
def obtener_html(page, url, intentos=3):
    """Navega a `url` y devuelve su HTML renderizado, o None si falla.

    Reintenta ante fallos transitorios con espera creciente, de modo que un
    libro problematico no interrumpa la corrida completa.
    """
    for intento in range(1, intentos + 1):
        try:
            page.goto(url, timeout=TIMEOUT_MS, wait_until="domcontentloaded")
            page.wait_for_timeout(800)
            return page.content()
        except Exception as e:
            print(f"      ! intento {intento}/{intentos} fallo ({type(e).__name__}) en {url}")
            time.sleep(2 * intento)          # espera creciente
    return None


def urls_ya_guardadas(ruta=CSV_PARCIAL):
    """URL ya extraidas en corridas anteriores (permite reanudar sin duplicar)."""
    if not ruta.exists():
        return set()
    try:
        return set(pd.read_csv(ruta, dtype=str)["url_libro"].dropna())
    except Exception:
        return set()


def guardar_fila(fila, ruta=CSV_PARCIAL):
    """Agrega una fila al CSV parcial (guardado incremental)."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    es_nuevo = not ruta.exists()
    with open(ruta, "a", newline="", encoding="utf-8") as f:
        escritor = csv.DictWriter(f, fieldnames=COLUMNAS)
        if es_nuevo:
            escritor.writeheader()
        escritor.writerow(fila)


def scrapear(objetivo=N_LIBROS_OBJETIVO, max_paginas=MAX_PAGINAS, headless=True):
    """Recorre la categoria y extrae fichas hasta alcanzar `objetivo` libros."""
    vistos = urls_ya_guardadas()          # evita duplicados y permite reanudar
    nuevos = 0
    errores = 0
    print(f"Registros previos: {len(vistos)} | objetivo: {objetivo}\n")

    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=headless)
        contexto = navegador.new_context(
            user_agent=USER_AGENT,
            locale="es-AR",
            viewport={"width": 1280, "height": 800},
        )
        pagina_web = contexto.new_page()

        n_pagina = 1
        while len(vistos) < objetivo and n_pagina <= max_paginas:
            listado = url_pagina(n_pagina)
            print(f"[Listado] pagina {n_pagina}: {listado}")

            html_listado = obtener_html(pagina_web, listado)
            if html_listado is None:
                errores += 1
                n_pagina += 1
                continue

            fichas = extraer_urls_listado(html_listado)
            print(f"          {len(fichas)} fichas encontradas")
            if not fichas:
                print("          Sin fichas: se detiene el recorrido de listados.")
                break

            for url in fichas:
                if len(vistos) >= objetivo:
                    break
                if url in vistos:                      # ya extraido: no duplicar
                    continue

                time.sleep(random.uniform(PAUSA_MIN, PAUSA_MAX))  # pausa

                html_ficha = obtener_html(pagina_web, url)
                if html_ficha is None:
                    errores += 1
                    continue

                try:
                    fila = parsear_ficha(html_ficha, url)
                except Exception as e:
                    print(f"      ! error al analizar {url}: {type(e).__name__}: {e}")
                    errores += 1
                    continue

                if not fila["titulo"]:                 # validacion minima
                    print(f"      ! ficha sin titulo, se descarta: {url}")
                    errores += 1
                    continue

                guardar_fila(fila)                     # guardado incremental
                vistos.add(url)
                nuevos += 1
                print(f"      [{len(vistos):3d}/{objetivo}] {fila['titulo'][:60]}")

            n_pagina += 1

        contexto.close()
        navegador.close()

    print(f"\nFin. Nuevos: {nuevos} | Total: {len(vistos)} | Errores tolerados: {errores}")
    return nuevos


# --------------------------------------------------------------------------- #
# Limpieza final y controles minimos (pandas)
# --------------------------------------------------------------------------- #
def construir_dataset(objetivo=N_LIBROS_OBJETIVO):
    """Lee el CSV parcial, lo limpia, deduplica y devuelve el DataFrame final."""
    df = pd.read_csv(CSV_PARCIAL, dtype=str)
    print(f"Filas leidas del CSV parcial: {len(df)}")

    for col in COLUMNAS:
        if col not in df.columns:
            df[col] = VALOR_FALTANTE
    df = df[COLUMNAS].fillna(VALOR_FALTANTE)

    for col in COLUMNAS:
        df[col] = df[col].map(limpiar)

    antes = len(df)
    df = df[df["titulo"] != ""]                                # exige titulo
    df = df[df["url_libro"].str.startswith("http")]            # exige URL valida
    df = df.drop_duplicates(subset="url_libro", keep="first")  # control exigido
    df = df.drop_duplicates(subset=["titulo", "autores"], keep="first")
    df = df.head(objetivo).reset_index(drop=True)

    print(f"Filas descartadas por vacias o duplicadas: {antes - len(df)}")
    print(f"Dataset final: {len(df)} libros")
    return df


def controles_minimos(df):
    """Verifica los siete controles exigidos por la consigna. Devuelve bool."""
    sin_espacios_raros = not df.map(
        lambda v: isinstance(v, str) and (v != v.strip() or "\n" in v or "  " in v)
    ).to_numpy().any()

    controles = {
        "Sin duplicados por url_libro": df["url_libro"].duplicated().sum() == 0,
        "Todos los registros tienen titulo": (df["titulo"].str.len() > 0).all(),
        "Todas las URL son validas": df["url_libro"].str.match(r"^https?://").all(),
        "La mayoria tiene sinopsis (>80%)": (df["sinopsis"].str.len() > 0).mean() > 0.80,
        "Sin espacios ni saltos de linea sobrantes": sin_espacios_raros,
        "Campos ausentes representados igual": df.isna().sum().sum() == 0,
        "Cantidad entre 50 y 100 libros": 50 <= len(df) <= 100,
    }
    ancho = max(len(k) for k in controles)
    for nombre, ok in controles.items():
        print(f"{'  OK ' if ok else 'FALLA'}  {nombre:<{ancho}}")
    print()
    print(f"Libros            : {len(df)}")
    con_sinopsis = (df["sinopsis"].str.len() > 0)
    print(f"Con sinopsis      : {con_sinopsis.sum()} ({con_sinopsis.mean():.1%})")
    print(f"Con serie         : {(df['serie'].str.len() > 0).sum()}")
    print(f"Autores distintos : {df['autores'].nunique()}")
    return all(controles.values())


# --------------------------------------------------------------------------- #
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=N_LIBROS_OBJETIVO,
                        help="cantidad de libros a extraer (por defecto 100)")
    parser.add_argument("--max-paginas", type=int, default=MAX_PAGINAS,
                        help="tope de paginas de listado a recorrer")
    parser.add_argument("--no-headless", action="store_true",
                        help="mostrar la ventana del navegador")
    parser.add_argument("--solo-dataset", action="store_true",
                        help="omitir el scraping y rearmar libros.csv desde el CSV parcial")
    args = parser.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if not args.solo_dataset:
        scrapear(objetivo=args.n, max_paginas=args.max_paginas,
                 headless=not args.no_headless)

    if not CSV_PARCIAL.exists():
        print(f"No existe {CSV_PARCIAL}: no hay nada para procesar.")
        return 1

    print("\n--- Limpieza y deduplicacion ---")
    df = construir_dataset(objetivo=args.n)

    print("\n--- Controles minimos ---")
    ok = controles_minimos(df)

    df.to_csv(CSV_FINAL, index=False, encoding="utf-8")
    print(f"\nGuardado: {CSV_FINAL}  ({len(df)} filas)")

    if not ok:
        print("\nATENCION: hay controles minimos que no se cumplen. Revisar antes de entregar.")
        return 1
    print("Todos los controles minimos se cumplen.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
