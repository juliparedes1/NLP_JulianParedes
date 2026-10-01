#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unidad 1 - Extraccion y procesamiento de texto
Extraccion de metadatos y sinopsis de Lectulandia con Playwright + BeautifulSoup.

Version de linea de comandos del notebook `scraper_lectulandia_colab.ipynb`.
Usa la API sincronica de Playwright, que es la adecuada fuera de un notebook.

Uso:
    python src/scraper.py                     # 100 libros de la categoria por defecto
    python src/scraper.py --n 10              # corrida de prueba (omite el control de cantidad)
    python src/scraper.py --reiniciar         # borra el CSV parcial y empieza de cero
    python src/scraper.py --no-headless       # mostrando la ventana del navegador
    python src/scraper.py --solo-dataset      # rearma libros.csv sin volver a navegar

Solo se extraen metadatos y sinopsis publicas. No se descargan libros,
ni archivos EPUB, PDF u otros contenidos.
"""

import argparse
import csv
import json
import random
import re
import sys
import time
import unicodedata
from datetime import date
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse

import pandas as pd
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

# --------------------------------------------------------------------------- #
# Configuracion
# --------------------------------------------------------------------------- #
BASE_URL = "https://ww3.lectulandia.co"
CATEGORIA_NOMBRE = "Thriller / Intriga"
CATEGORIA_URL = "https://ww3.lectulandia.co/genero/intriga/"

N_LIBROS_OBJETIVO = 150          # cantidad a extraer en la corrida de entrega
MIN_LIBROS, MAX_LIBROS = 100, 150 # rango exigido por la consigna (Parte 2)
MAX_PAGINAS = 25                 # tope de paginas de listado a recorrer
PAUSA_MIN, PAUSA_MAX = 1.5, 3.0  # pausa aleatoria entre visitas, en segundos
TIMEOUT_MS = 45_000              # tiempo maximo de espera por pagina
VALOR_FALTANTE = ""              # campo de texto ausente (los de lista usan [])

RAIZ = Path(__file__).resolve().parent.parent
DATA_DIR = RAIZ / "data"
CSV_PARCIAL = DATA_DIR / "libros_parcial.csv"   # guardado incremental
CSV_FINAL = DATA_DIR / "libros.csv"             # entregable
JSON_FINAL = DATA_DIR / "libros.json"           # mismo dataset, con arrays nativos

COLUMNAS = [
    "titulo", "autores", "generos", "serie", "sinopsis",
    "url_libro", "categoria_origen", "fecha_extraccion", "url_portada",
]
COLUMNAS_LISTA = ["autores", "generos"]   # campos multivaluados: se guardan como array
FECHA_EXTRACCION = date.today().isoformat()

USER_AGENT = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")


# --------------------------------------------------------------------------- #
# Limpieza de texto y manejo de listas
# --------------------------------------------------------------------------- #
ESPACIOS = re.compile(r"\s+")
# Minuscula + signo de cierre + mayuscula/numero, sin espacio: "hacerlo.Respeto"
PATRON_ORACION_PEGADA = r"[a-záéíóúüñ][.?!…][A-ZÁÉÍÓÚÜÑ¿¡0-9]"


def limpiar(texto):
    """Colapsa espacios y saltos de linea, y recorta los extremos.

    Devuelve VALOR_FALTANTE ("") cuando no hay texto util, de modo que todos los
    campos de texto ausentes se representen siempre de la misma manera.
    """
    if texto is None:
        return VALOR_FALTANTE
    texto = str(texto).replace("\xa0", " ")     # espacio duro -> espacio normal
    return ESPACIOS.sub(" ", texto).strip()


def lista_limpia(valores):
    """Limpia una lista de valores: sin vacios ni repetidos, conservando el orden."""
    limpios = [limpiar(v) for v in valores]
    return list(dict.fromkeys(v for v in limpios if v))


def unir(valores, sep="; "):
    """Une varios valores en un solo texto (se usa para `serie`)."""
    return sep.join(lista_limpia(valores)) or VALOR_FALTANTE


def a_json(lista):
    """Serializa una lista como array JSON, para guardarla en una celda del CSV."""
    return json.dumps(lista, ensure_ascii=False)


def a_lista(valor):
    """Convierte una celda del CSV en lista.

    Acepta el formato actual (array JSON: '["Intriga", "Novela"]') y, por
    compatibilidad con corridas anteriores, el formato viejo separado por punto
    y coma ('Intriga; Novela').
    """
    if isinstance(valor, list):
        return lista_limpia(valor)
    texto = limpiar(valor)
    if not texto:
        return []
    if texto.startswith("["):
        try:
            return lista_limpia(json.loads(texto))
        except json.JSONDecodeError:
            pass
    return lista_limpia(texto.split(";"))


def clave_comparacion(texto):
    """Minusculas, sin tildes ni signos: 'Mr.%20White (20)' -> 'mrwhite20'."""
    texto = unicodedata.normalize("NFKD", unquote(texto or ""))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", texto.lower())


def portada_coincide(titulo, url_imagen):
    """True si la direccion de la imagen contiene el titulo del libro.

    Se comparan los primeros 20 caracteres normalizados, porque el sitio
    abrevia los titulos largos y quita signos en la ruta de la imagen.
    """
    clave = clave_comparacion(titulo)[:20]
    return bool(clave) and clave in clave_comparacion(url_imagen)


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
    """Lista con el texto de los <a> de un bloque (autores, generos, serie)."""
    div = _bloque(soup, id_div)
    if div is None:
        return []
    enlaces = [a.get_text() for a in div.select("a")]
    return lista_limpia(enlaces if enlaces else [div.get_text()])


def _texto_con_saltos(nodo):
    """Texto de un nodo respetando los cortes de renglon del HTML.

    get_text() pega el final de un renglon con el comienzo del siguiente cuando
    estan separados por <br>: 'hacerlo.<br>Respeto' -> 'hacerlo.Respeto'.
    Por eso cada <br> se reemplaza por un salto de linea y se agrega otro antes
    y despues de cada bloque (texto suelto seguido de un <p> tambien se pegaria);
    limpiar() despues los reduce a un unico espacio.
    No se usa get_text(" ") porque tambien separaria las etiquetas en linea:
    '<i>Poirot</i>,' quedaria 'Poirot ,'.
    """
    for br in nodo.find_all("br"):
        br.replace_with("\n")
    for bloque in nodo.find_all(["p", "div", "li", "blockquote",
                                 "h1", "h2", "h3", "h4", "h5", "h6"]):
        bloque.insert_before("\n")
        bloque.append("\n")
    return limpiar(nodo.get_text())


def _portada(soup, titulo):
    """URL de la portada del libro, verificada contra su titulo.

    Solo se acepta una imagen cuya direccion o texto alternativo contenga el
    titulo. Si ninguna coincide, el campo queda vacio: una portada ausente es
    preferible a la portada de otro libro.
    """
    candidatos = []
    og = soup.find("meta", attrs={"property": "og:image"})
    if og and og.get("content"):
        candidatos.append((og["content"], ""))
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src") or ""
        candidatos.append((src, img.get("alt", "")))
    for src, alt in candidatos:
        if src and (portada_coincide(titulo, src) or portada_coincide(titulo, alt)):
            return urljoin(BASE_URL, src)
    return VALOR_FALTANTE


def parsear_ficha(html, url):
    """Extrae los metadatos y la sinopsis de una ficha. Devuelve un dict-fila."""
    soup = BeautifulSoup(html, "lxml")

    # Titulo:  <div id="title"><h1>...</h1></div>   (plan B: primer <h1>)
    div_titulo = soup.find("div", id="title")
    titulo = limpiar(div_titulo.get_text()) if div_titulo else VALOR_FALTANTE
    if not titulo:
        h1 = soup.find("h1")
        titulo = limpiar(h1.get_text()) if h1 else VALOR_FALTANTE

    # Autores y generos: listas.  Serie: texto (un libro pertenece a una sola serie)
    autores = _valores_enlazados(soup, "autor")
    generos = _valores_enlazados(soup, "genero")
    serie = unir(_valores_enlazados(soup, "serie"))

    # Sinopsis: <div id="sinopsis">, con renglones separados por <br> o <p>
    sinopsis = VALOR_FALTANTE
    div_sinopsis = _bloque(soup, "sinopsis")
    if div_sinopsis is not None:
        for rotulo in div_sinopsis.find_all(["span", "strong", "h2", "h3", "h4"]):
            if limpiar(rotulo.get_text()).lower().rstrip(":") == "sinopsis":
                rotulo.decompose()                       # quita el rotulo "Sinopsis"
        sinopsis = _texto_con_saltos(div_sinopsis)
        if sinopsis.lower().startswith("sinopsis"):      # rotulo suelto
            sinopsis = limpiar(sinopsis[len("sinopsis"):].lstrip(":"))
    if not sinopsis:                                     # plan B
        meta = soup.find("meta", attrs={"name": "description"})
        sinopsis = limpiar(meta.get("content")) if meta else VALOR_FALTANTE

    return {
        "titulo": titulo,
        "autores": autores,
        "generos": generos,
        "serie": serie,
        "sinopsis": sinopsis,
        "url_libro": url,
        "categoria_origen": CATEGORIA_NOMBRE,
        "fecha_extraccion": FECHA_EXTRACCION,
        "url_portada": _portada(soup, titulo),   # campo opcional
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
        return set(pd.read_csv(ruta, dtype=str, keep_default_na=False)["url_libro"])
    except Exception:
        return set()


def guardar_fila(fila, ruta=CSV_PARCIAL):
    """Agrega una fila al CSV parcial (guardado incremental).

    Las listas se escriben como arrays JSON. Sin esta conversion, el modulo csv
    escribiria la representacion de Python (['a', 'b'], con comillas simples),
    que no es JSON valido.
    """
    ruta.parent.mkdir(parents=True, exist_ok=True)
    es_nuevo = not ruta.exists()
    fila = {k: (a_json(v) if isinstance(v, list) else v) for k, v in fila.items()}
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
# Limpieza final, controles minimos y exportacion (pandas)
# --------------------------------------------------------------------------- #
def construir_dataset(objetivo=N_LIBROS_OBJETIVO):
    """Lee el CSV parcial, lo limpia, deduplica y devuelve el DataFrame final.

    En el DataFrame resultante `autores` y `generos` son listas de Python.
    """
    # keep_default_na=False: una celda vacia se lee como "" y no como NaN
    df = pd.read_csv(CSV_PARCIAL, dtype=str, keep_default_na=False)
    print(f"Filas leidas del CSV parcial: {len(df)}")

    for col in COLUMNAS:
        if col not in df.columns:
            df[col] = VALOR_FALTANTE
    df = df[COLUMNAS].fillna(VALOR_FALTANTE)

    for col in COLUMNAS:
        df[col] = df[col].map(a_lista if col in COLUMNAS_LISTA else limpiar)

    antes = len(df)
    df = df[df["titulo"] != ""]                                # exige titulo
    df = df[df["url_libro"].str.startswith("http")]            # exige URL valida
    df = df.drop_duplicates(subset="url_libro", keep="first")  # control exigido
    # Las listas no son "hasheables": drop_duplicates(["titulo", "autores"])
    # fallaria con TypeError. Se compara con una clave de texto equivalente.
    clave = df["titulo"] + "|" + df["autores"].map(a_json)
    df = df[~clave.duplicated(keep="first")]
    df = df.head(objetivo).reset_index(drop=True)
    print(f"Filas descartadas por vacias o duplicadas: {antes - len(df)}")

    # Red de seguridad: se vacia toda portada que no corresponda a su libro.
    # Tambien corrige CSV parciales generados con la version anterior.
    coincide = pd.Series(
        [portada_coincide(t, u) for t, u in zip(df["titulo"], df["url_portada"])],
        index=df.index, dtype=bool,
    )
    ajenas = (df["url_portada"] != "") & ~coincide
    if ajenas.any():
        print(f"Portadas que no corresponden a su libro, se vacian: {ajenas.sum()}")
        df.loc[ajenas, "url_portada"] = VALOR_FALTANTE

    print(f"Dataset final: {len(df)} libros")
    return df


def controles_minimos(df, prueba=False):
    """Verifica los siete controles exigidos por la consigna.

    Devuelve la lista de controles que NO se cumplen (vacia = todo en orden).
    Con prueba=True (corridas de menos de MIN_LIBROS libros) el control de
    cantidad se informa como OMITIDO en lugar de fallar, porque en una prueba
    es esperable. Ademas informa advertencias de calidad que no bloquean.
    """
    columnas_texto = [c for c in COLUMNAS if c not in COLUMNAS_LISTA]

    def texto_sucio(v):
        return isinstance(v, str) and (v != v.strip() or "\n" in v or "  " in v)

    # Se revisan las celdas de texto y tambien cada elemento de las listas
    valores = [v for c in columnas_texto for v in df[c]]
    valores += [x for c in COLUMNAS_LISTA for lista in df[c] for x in lista]

    ausentes_ok = (all(isinstance(v, str) for c in columnas_texto for v in df[c])
                   and all(isinstance(v, list) for c in COLUMNAS_LISTA for v in df[c]))

    en_rango = MIN_LIBROS <= len(df) <= MAX_LIBROS
    controles = {
        "Sin duplicados por url_libro": df["url_libro"].duplicated().sum() == 0,
        "Todos los registros tienen titulo": (df["titulo"].str.len() > 0).all(),
        "Todas las URL son validas": df["url_libro"].str.match(r"^https?://").all(),
        "La mayoria tiene sinopsis (>80%)": (df["sinopsis"].str.len() > 0).mean() > 0.80,
        "Sin espacios ni saltos de linea sobrantes": not any(texto_sucio(v) for v in valores),
        "Campos ausentes representados igual ('' o [])": ausentes_ok,
        f"Cantidad entre {MIN_LIBROS} y {MAX_LIBROS} libros":
            None if (prueba and not en_rango) else en_rango,
    }

    pegadas = df["sinopsis"].str.count(PATRON_ORACION_PEGADA)
    portadas = df.loc[df["url_portada"] != "", "url_portada"]
    advertencias = {
        "Sinopsis sin oraciones pegadas":
            (pegadas.sum() == 0, f"{pegadas.sum()} casos en {(pegadas > 0).sum()} libros"),
        "Portadas sin repetir entre libros":
            (not portadas.duplicated().any(), f"{portadas.duplicated().sum()} repetidas"),
    }

    ancho = max(len(k) for k in list(controles) + list(advertencias))
    for nombre, ok in controles.items():
        estado = "OMIT." if ok is None else ("  OK " if ok else "FALLA")
        print(f"{estado}  {nombre:<{ancho}}")

    print("\nAdvertencias de calidad (no bloquean la entrega):")
    for nombre, (ok, detalle) in advertencias.items():
        print(f"{'  OK ' if ok else 'AVISO'}  {nombre:<{ancho}}  {'' if ok else detalle}")

    con_sinopsis = df["sinopsis"].str.len() > 0
    print()
    print(f"Libros            : {len(df)}")
    print(f"Con sinopsis      : {con_sinopsis.sum()} ({con_sinopsis.mean():.1%})")
    print(f"Con serie         : {(df['serie'] != '').sum()}")
    print(f"Con portada       : {(df['url_portada'] != '').sum()}")
    print(f"Autores distintos : {df['autores'].explode().nunique()}")
    print(f"Generos distintos : {df['generos'].explode().nunique()}")

    if controles[f"Cantidad entre {MIN_LIBROS} y {MAX_LIBROS} libros"] is None:
        print(f"\n(Corrida de prueba con {len(df)} libros: el control de cantidad se "
              f"omite. Para la entrega, correr sin --n para extraer {N_LIBROS_OBJETIVO}.)")
    return [nombre for nombre, ok in controles.items() if ok is False]


def exportar(df):
    """Guarda libros.csv (listas como arrays JSON) y libros.json (arrays nativos)."""
    salida = df[COLUMNAS].copy()
    for col in COLUMNAS_LISTA:
        salida[col] = salida[col].map(a_json)
    salida.to_csv(CSV_FINAL, index=False, encoding="utf-8")

    # Se usa json.dump y no df.to_json, que escaparia las barras: "https:\/\/..."
    with open(JSON_FINAL, "w", encoding="utf-8") as f:
        json.dump(df[COLUMNAS].to_dict(orient="records"), f, ensure_ascii=False, indent=2)

    print(f"Guardado: {CSV_FINAL}  ({len(df)} filas)")
    print(f"Guardado: {JSON_FINAL}")


# --------------------------------------------------------------------------- #
def main():
    # La consola de Windows usa cp1252: un titulo con un caracter fuera de esa
    # tabla (p. ej. "Stanisław") haria fallar el print y cortaria la corrida.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")

    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--n", type=int, default=N_LIBROS_OBJETIVO,
                        help=f"cantidad de libros a extraer (por defecto {N_LIBROS_OBJETIVO}; "
                             f"con menos de {MIN_LIBROS} se considera una prueba)")
    parser.add_argument("--max-paginas", type=int, default=MAX_PAGINAS,
                        help="tope de paginas de listado a recorrer")
    parser.add_argument("--no-headless", action="store_true",
                        help="mostrar la ventana del navegador")
    parser.add_argument("--reiniciar", action="store_true",
                        help="borrar el CSV parcial y extraer todo de nuevo")
    parser.add_argument("--solo-dataset", action="store_true",
                        help="omitir el scraping y rearmar libros.csv desde el CSV parcial")
    args = parser.parse_args()

    prueba = args.n < MIN_LIBROS
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if args.reiniciar and CSV_PARCIAL.exists():
        CSV_PARCIAL.unlink()
        print(f"Se borro {CSV_PARCIAL.name}: la extraccion empieza de cero.\n")

    if not args.solo_dataset:
        scrapear(objetivo=args.n, max_paginas=args.max_paginas,
                 headless=not args.no_headless)

    if not CSV_PARCIAL.exists():
        print(f"No existe {CSV_PARCIAL}: no hay nada para procesar.")
        return 1

    print("\n--- Limpieza y deduplicacion ---")
    df = construir_dataset(objetivo=args.n)

    print("\n--- Controles minimos ---")
    fallidos = controles_minimos(df, prueba=prueba)

    print()
    exportar(df)

    if fallidos:
        print("\nATENCION: no se cumplen estos controles minimos:")
        for nombre in fallidos:
            print(f"  - {nombre}")
        print("Revisar antes de entregar.")
        return 1
    print("\nTodos los controles minimos se cumplen.")
    return 0


if __name__ == "__main__":
    sys.exit(main())


