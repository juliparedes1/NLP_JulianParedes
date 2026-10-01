#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unidad 2 - TP2, Parte 5: conjunto de evaluacion (queries.json)

El conjunto de evaluacion es la unica parte del TP que no se puede automatizar:
hay que leer sinopsis y decidir a mano que libro es relevante para que consulta.
Lo que SI se puede automatizar es el trabajo alrededor, que es lo que hace este
modulo:

    --hoja      genera una planilla para leer el corpus rapido y marcar
    --validar   revisa el queries.json ya escrito y avisa de los problemas
                que despues arruinan la evaluacion

El chequeo importante es el de PISO DE AZAR. precision@k solo significa algo
comparado contra lo que da elegir libros al azar, y ese piso depende de cuan
grandes sean los conjuntos de relevantes. Si marcas 45 relevantes sobre 150
libros, el azar ya acierta el 30% y un modelo con 0.35 no demostro nada. Este
modulo calcula el piso ANTES de correr ningun modelo, que es cuando todavia se
puede corregir.

Uso:
    python src/queries_tp2.py --hoja
    python src/queries_tp2.py --validar
    python src/queries_tp2.py --validar --k 10
"""

import argparse
import json
import random
import sys
from pathlib import Path

import pandas as pd

from preprocesamiento import cargar_corpus, tokenizar

RAIZ = Path(__file__).resolve().parent.parent
DATA_DIR = RAIZ / "data"
CSV_CORPUS = DATA_DIR / "libros.csv"
JSON_QUERIES = DATA_DIR / "queries.json"
CSV_HOJA = DATA_DIR / "hoja_queries.csv"

MIN_CONSULTAS = 10      # minimo que pide la consigna
MIN_RELEVANTES = 3      # menos que esto hace la metrica muy inestable
MAX_RELEVANTES = 8      # mas que esto dispara el piso de azar
SORTEOS_AZAR = 1000     # repeticiones para estimar el piso

# Generos que cubren practicamente todo el corpus: no sirven como etiqueta.
GENEROS_INUTILES = {"Intriga", "Novela"}


# --------------------------------------------------------------------------- #
# --hoja : planilla para leer el corpus y marcar relevantes
# --------------------------------------------------------------------------- #
def generar_hoja(df, palabras=30, ruta=CSV_HOJA):
    """Genera un CSV liviano para leer los 150 libros sin abrir 150 sinopsis.

    Trae lo justo para decidir de que trata cada libro: titulo, subgeneros y el
    arranque de la sinopsis (que en texto promocional es donde esta el gancho,
    o sea el tema). La columna `temas` queda vacia a proposito: se completa a
    mano mientras se lee, y es lo que despues se agrupa en consultas.
    """
    hoja = pd.DataFrame({
        "idx": range(len(df)),
        "titulo": df["titulo"],
        "subgeneros": df["generos"].apply(
            lambda gs: "/".join(g for g in gs if g not in GENEROS_INUTILES) or "-"),
        "inicio_sinopsis": df["sinopsis"].apply(
            lambda s: " ".join(str(s).split()[:palabras])),
        "temas": "",          # <- completar a mano al leer
        "url_libro": df["url_libro"],
    })
    Path(ruta).parent.mkdir(parents=True, exist_ok=True)
    hoja.to_csv(ruta, index=False, encoding="utf-8-sig")  # BOM: Excel abre bien
    return ruta


# --------------------------------------------------------------------------- #
# --validar : los chequeos que salvan la evaluacion
# --------------------------------------------------------------------------- #
def piso_de_azar(n_corpus, n_relevantes, k, sorteos=SORTEOS_AZAR, rng=None):
    """Estima precision@k de elegir k libros al azar.

    El valor esperado es n_relevantes/n_corpus, pero se simula igual porque es
    exactamente lo que hay que hacer en el notebook para la fila "azar" de la
    tabla: muestrear muchas veces y promediar, no calcular la formula.
    """
    rng = rng or random.Random(42)
    indices = range(n_corpus)
    relevantes = set(range(n_relevantes))   # cuales son da igual, solo cuantos
    aciertos = 0
    for _ in range(sorteos):
        elegidos = rng.sample(indices, min(k, n_corpus))
        aciertos += sum(1 for e in elegidos if e in relevantes) / min(k, n_corpus)
    return aciertos / sorteos


def solapamiento_lexico(consulta, urls_relevantes, textos_por_url):
    """Fraccion de las palabras de la consulta que aparecen en algun relevante.

    Es la medida de si TF-IDF TIENE ALGUNA CHANCE con esta consulta. TF-IDF
    puntua por coincidencia de palabras: si el solapamiento es 0, su puntaje es
    exactamente 0 por construccion, y la consulta queda reservada para los
    modelos semanticos. La consigna pide al menos una consulta asi.
    """
    tokens_consulta = set(tokenizar(consulta))
    if not tokens_consulta:
        return 0.0

    tokens_relevantes = set()
    for url in urls_relevantes:
        tokens_relevantes |= set(textos_por_url.get(url, []))

    return len(tokens_consulta & tokens_relevantes) / len(tokens_consulta)


def validar(df, queries, k=5):
    """Recorre el conjunto de evaluacion y reporta todo lo que puede fallar."""
    n = len(df)
    urls_corpus = set(df["url_libro"])
    textos_por_url = dict(zip(df["url_libro"],
                              df["sinopsis"].apply(lambda s: tokenizar(str(s)))))

    problemas, avisos = [], []

    print("=" * 74)
    print(f"VALIDACION DE queries.json   (corpus: {n} libros, k={k})")
    print("=" * 74)

    # --- estructura general ------------------------------------------------ #
    if len(queries) < MIN_CONSULTAS:
        problemas.append(f"Hay {len(queries)} consultas; la consigna pide {MIN_CONSULTAS} como minimo.")

    ids = [q.get("id", f"<sin id #{i}>") for i, q in enumerate(queries)]
    repetidos = {i for i in ids if ids.count(i) > 1}
    if repetidos:
        problemas.append(f"Ids repetidos: {sorted(repetidos)}")

    # --- consulta por consulta --------------------------------------------- #
    print(f"\n{'id':<6}{'rel':>4}{'piso':>8}{'solap':>8}  tipo         consulta")
    print("-" * 74)

    pisos, sin_solapamiento = [], 0

    for q in queries:
        qid = q.get("id", "?")
        texto = q.get("consulta", "")
        relevantes = q.get("relevantes", [])

        faltantes = [u for u in relevantes if u not in urls_corpus]
        if faltantes:
            problemas.append(
                f"{qid}: {len(faltantes)} url(s) de relevantes no estan en el corpus. "
                f"Primera: {faltantes[0]}")

        validos = [u for u in relevantes if u in urls_corpus]
        if len(set(validos)) != len(validos):
            avisos.append(f"{qid}: hay urls repetidas en `relevantes`.")

        piso = piso_de_azar(n, len(validos), k)
        pisos.append(piso)
        solap = solapamiento_lexico(texto, validos, textos_por_url)
        if solap == 0:
            sin_solapamiento += 1

        tipo = "SEMANTICA" if solap < 0.15 else ("mixta" if solap < 0.45 else "lexica")

        print(f"{qid:<6}{len(validos):>4}{piso:>8.2f}{solap:>8.0%}  {tipo:<12} {texto[:34]}")

        if len(validos) < MIN_RELEVANTES:
            avisos.append(f"{qid}: solo {len(validos)} relevantes. Con menos de "
                          f"{MIN_RELEVANTES} la metrica salta mucho entre corridas.")
        if len(validos) > MAX_RELEVANTES:
            avisos.append(f"{qid}: {len(validos)} relevantes elevan el piso de azar a "
                          f"{piso:.2f}. Achicar el conjunto a los mas claros.")

    # --- resumen ------------------------------------------------------------ #
    print("-" * 74)
    piso_global = sum(pisos) / len(pisos) if pisos else 0
    print(f"\nPISO DE AZAR GLOBAL (precision@{k}) : {piso_global:.3f}")
    print(f"  -> Cualquier modelo tiene que superar {piso_global:.3f} para haber")
    print("     demostrado algo. Esta fila va SIEMPRE en la tabla del informe.")
    if piso_global > 0.30:
        avisos.append(f"El piso de azar ({piso_global:.2f}) es alto: los conjuntos de "
                      "relevantes son demasiado grandes y achatan las diferencias "
                      "entre modelos. Conviene quedarse con los relevantes mas claros.")

    print(f"\nConsultas sin solapamiento lexico   : {sin_solapamiento}")
    print("  -> En estas TF-IDF saca exactamente 0 por construccion: es donde se")
    print("     ve la diferencia entre representacion lexica y semantica.")
    if sin_solapamiento == 0:
        problemas.append("No hay ninguna consulta sin solapamiento lexico. La consigna "
                         "pide al menos una. Sin eso no se puede mostrar en que gana "
                         "un embedding sobre TF-IDF.")

    cubiertos = {u for q in queries for u in q.get("relevantes", []) if u in urls_corpus}
    print(f"\nLibros marcados como relevantes en alguna consulta: {len(cubiertos)}/{n} "
          f"({len(cubiertos)/max(n,1):.0%})")

    # --- salida ------------------------------------------------------------- #
    print()
    if problemas:
        print("PROBLEMAS (hay que corregirlos):")
        for p in problemas:
            print(f"  [X] {p}")
    if avisos:
        print("\nAVISOS (revisar, no bloquean):")
        for a in avisos:
            print(f"  [!] {a}")
    if not problemas and not avisos:
        print("Sin problemas. El conjunto de evaluacion esta listo.")
    print("=" * 74)

    return not problemas


# --------------------------------------------------------------------------- #
def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--hoja", action="store_true",
                        help="genera data/hoja_queries.csv para leer y marcar")
    parser.add_argument("--validar", action="store_true",
                        help="revisa data/queries.json")
    parser.add_argument("--k", type=int, default=5,
                        help="k de precision@k para estimar el piso (default 5)")
    parser.add_argument("--corpus", default=str(CSV_CORPUS))
    parser.add_argument("--queries", default=str(JSON_QUERIES))
    args = parser.parse_args()

    if not args.hoja and not args.validar:
        parser.error("elegir --hoja o --validar")

    df = cargar_corpus(args.corpus)

    if args.hoja:
        ruta = generar_hoja(df)
        print(f"Planilla generada: {ruta}")
        print(f"  {len(df)} libros. Abrila en Excel, leela y completa la columna `temas`.")
        print("  Despues agrupa los temas repetidos: cada grupo es una consulta.")

    if args.validar:
        ruta = Path(args.queries)
        if not ruta.exists():
            sys.exit(f"No existe {ruta}. Escribilo primero (ver plantilla en el README).")
        queries = json.loads(ruta.read_text(encoding="utf-8"))
        ok = validar(df, queries, k=args.k)
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
