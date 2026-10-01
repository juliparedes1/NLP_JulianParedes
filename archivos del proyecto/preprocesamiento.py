#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unidad 2 - Representacion vectorial de texto (TP2, Parte A)
Prepara las DOS versiones del texto que necesitan los modelos del TP.

Por que dos versiones
---------------------
El preprocesamiento pertenece al MODELO, no al corpus:

  * texto_crudo   -> sinopsis tal cual, con mayusculas, tildes y puntuacion.
                     Lo consume el modelo de oracion (SBERT), que fue entrenado
                     sobre texto natural y usa el orden y las palabras
                     funcionales. Limpiarlo seria destructivo.

  * texto_limpio  -> minusculas, sin puntuacion, sin stopwords, sin numeros.
    tokens           Lo consumen TF-IDF (linea de base) y Word2Vec propio, que
                     son modelos de bolsa de palabras: no miran el orden, y las
                     palabras muy frecuentes solo les agregan ruido.

Cada decision de limpieza es una perdida de informacion deliberada. Las que se
tomaron aca, con su justificacion, estan en las constantes de configuracion.

Uso:
    python src/preprocesamiento.py                  # prepara y guarda
    python src/preprocesamiento.py --top 30         # muestra 30 palabras frecuentes
    python src/preprocesamiento.py --sin-guardar    # solo diagnostico

No requiere instalar nada mas alla de pandas: la tokenizacion se hace con
expresiones regulares y la lista de stopwords esta embebida. Eso lo hace
reproducible en Colab sin descargas previas (nltk.download, spacy download).
"""

import argparse
import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

import pandas as pd

# --------------------------------------------------------------------------- #
# Configuracion: cada valor es una decision justificada
# --------------------------------------------------------------------------- #

# Campos que componen el texto del documento.
# OJO: `generos` NO entra. Es la etiqueta que se usa para colorear la proyeccion
# 2D y para filtrar por metadata. Meterla dentro del texto seria fuga de
# informacion (data leakage): el modelo agruparia por genero porque se lo
# dijimos, no porque lo dedujo.
CAMPOS_TEXTO = ["titulo", "sinopsis"]

# Pasar a minusculas: con ~100 documentos cortos necesitamos que las
# repeticiones se acumulen ("Asesino" y "asesino" deben ser la misma palabra).
# Costo: se pierden las entidades nombradas (Madrid -> madrid).
A_MINUSCULAS = True

# Conservar las tildes: el catalogo las escribe de forma consistente, asi que no
# hay variantes que unificar. Sacarlas solo perderia informacion (si/si, el/el).
QUITAR_TILDES = False

# Longitud minima de token: descarta restos de la limpieza sin valor tematico.
MIN_LONGITUD_TOKEN = 3

# Descartar tokens con digitos: "1931", "19" son ruido en un corpus chico.
SOLO_ALFABETICOS = True

RAIZ = Path(__file__).resolve().parent.parent
DATA_DIR = RAIZ / "data"
CSV_ENTRADA = DATA_DIR / "libros.csv"
CSV_SALIDA = DATA_DIR / "corpus_preparado.csv"

# --------------------------------------------------------------------------- #
# Stopwords del espanol
# --------------------------------------------------------------------------- #
# Palabras funcionales de alta frecuencia. Aparecen en practicamente todos los
# documentos, de modo que no distinguen ninguno: para bolsa de palabras son
# ruido. Se sacan SOLO de la version limpia; la cruda las conserva porque SBERT
# las necesita (un "no" cambia el significado de la oracion).
STOPWORDS_ES = set("""
a al algo algun alguna algunas alguno algunos ante antes aquel aquella aquellas
aquellos aqui asi aun aunque bajo bien cada casi como con contra cual cuales
cuando cuanto cuanta cuantas cuantos de del demas desde donde dos durante e el
ella ellas ellos en entre era erais eramos eran eras eres es esa esas ese eso
esos esta estaba estaban estado estais estamos estan estar estas este esto estos
estoy fue fueron fui fuimos ha habia habian han has hasta hay he hemos hube
incluso la las le les lo los mas me mi mia mias mio mios mis mismo mucha muchas
mucho muchos muy nada ni ninguna ninguno no nos nosotras nosotros nuestra
nuestras nuestro nuestros o os otra otras otro otros para pero poco pocas pocos
por porque que quien quienes se sea sean segun ser si sido siempre sin sobre sois
solo somos son soy su sus suya suyas suyo suyos tal tambien tampoco tan tanta
tantas tanto tantos te tendra tendran tenemos tener tengo ti tiene tienen toda
todas todo todos tu tus tuya tuyas tuyo tuyos un una unas uno unos usted ustedes
va vamos van varias varios vaya ver vosotras vosotros voy vuestra vuestras
vuestro vuestros y ya yo
""".split())

# Variantes con tilde, porque el texto las trae y no las quitamos.
STOPWORDS_ES |= {
    "él", "más", "mí", "sí", "tú", "está", "están", "estás", "esté", "aún",
    "así", "aquí", "algún", "según", "también", "después", "cómo", "qué",
    "quién", "cuál", "dónde", "cuándo", "había", "habían", "será", "serán",
    "tendrá", "tendrán", "sólo", "ése", "ésta", "éste",
}

# Tokens = secuencias de letras (incluye tildes y enye). Deja afuera numeros,
# signos de puntuacion y simbolos. El guion interno se conserva para no partir
# palabras compuestas.
PATRON_TOKEN = re.compile(r"[a-záéíóúüñ]+(?:-[a-záéíóúüñ]+)*", re.IGNORECASE)
ESPACIOS = re.compile(r"\s+")


# --------------------------------------------------------------------------- #
# Carga
# --------------------------------------------------------------------------- #
def cargar_corpus(ruta=CSV_ENTRADA):
    """Lee libros.csv devolviendo `autores` y `generos` como listas de Python.

    `keep_default_na=False` evita que pandas convierta las celdas vacias en NaN:
    en este dataset un campo ausente es "" o [], nunca un flotante NaN.
    """
    if not Path(ruta).exists():
        sys.exit(f"No encuentro {ruta}. Corre primero el scraper del TP1.")

    df = pd.read_csv(
        ruta,
        keep_default_na=False,
        converters={"autores": json.loads, "generos": json.loads},
    )
    return df


# --------------------------------------------------------------------------- #
# Version CRUDA (para SBERT)
# --------------------------------------------------------------------------- #
def construir_texto_crudo(fila):
    """Une titulo y sinopsis conservando el texto natural.

    Lo unico que se toca es el espaciado, y solo porque el scraper ya dejo el
    texto limpio de `&nbsp;` y saltos de linea. Mayusculas, tildes, comas,
    puntos y palabras funcionales quedan intactas: son justamente lo que un
    modelo de oracion usa para entender la frase.

    El punto entre titulo y sinopsis no es cosmetico: le marca al modelo que son
    dos unidades distintas.
    """
    partes = [str(fila.get(campo, "")).strip() for campo in CAMPOS_TEXTO]
    partes = [p for p in partes if p]
    texto = ". ".join(p.rstrip(".") for p in partes)
    return ESPACIOS.sub(" ", texto).strip()


# --------------------------------------------------------------------------- #
# Version LIMPIA (para TF-IDF y Word2Vec)
# --------------------------------------------------------------------------- #
def quitar_tildes(texto):
    """Descompone cada caracter acentuado y descarta el acento (á -> a).

    No se usa por defecto (QUITAR_TILDES = False). Queda disponible para poder
    mostrar el efecto de la decision contraria si hace falta justificarla.
    """
    descompuesto = unicodedata.normalize("NFD", texto)
    return "".join(c for c in descompuesto if unicodedata.category(c) != "Mn")


def tokenizar(texto):
    """Convierte un texto en la lista de tokens que veran TF-IDF y Word2Vec.

    Pasos, en orden, y lo que cuesta cada uno:
      1. minusculas          -> se pierden las entidades nombradas
      2. (opcional) tildes   -> se perderian si/si, el/el.  Desactivado.
      3. extraer palabras    -> se pierden puntuacion, numeros y limites de oracion
      4. filtrar por largo   -> se pierden restos sin valor tematico
      5. quitar stopwords    -> se pierden las negaciones y la sintaxis
    """
    if not texto:
        return []

    if A_MINUSCULAS:
        texto = texto.lower()
    if QUITAR_TILDES:
        texto = quitar_tildes(texto)

    tokens = PATRON_TOKEN.findall(texto)

    if SOLO_ALFABETICOS:
        tokens = [t for t in tokens if t.replace("-", "").isalpha()]

    tokens = [t for t in tokens if len(t) >= MIN_LONGITUD_TOKEN]
    tokens = [t for t in tokens if t not in STOPWORDS_ES]
    return tokens


# --------------------------------------------------------------------------- #
# Armado del corpus preparado
# --------------------------------------------------------------------------- #
def preparar_corpus(df):
    """Agrega al DataFrame las columnas que consume el resto del TP.

    Columnas nuevas:
      texto_crudo    str        -> entra a SBERT
      tokens         list[str]  -> entra a Word2Vec (espera listas de tokens)
      texto_limpio   str        -> entra a TF-IDF (espera un string por documento)
      n_palabras_crudo / n_tokens_limpio -> para el diagnostico
    """
    df = df.copy()
    df["texto_crudo"] = df.apply(construir_texto_crudo, axis=1)
    df["tokens"] = df["texto_crudo"].apply(tokenizar)
    df["texto_limpio"] = df["tokens"].apply(" ".join)
    df["n_palabras_crudo"] = df["texto_crudo"].str.split().str.len()
    df["n_tokens_limpio"] = df["tokens"].str.len()
    return df


def guardar(df, ruta=CSV_SALIDA):
    """Guarda el corpus preparado. `tokens` se serializa como array JSON.

    Un CSV solo guarda texto, asi que la lista de tokens se escribe como JSON y
    se relee con converters={"tokens": json.loads}, igual que autores/generos.
    """
    salida = df.copy()
    salida["autores"] = salida["autores"].apply(lambda v: json.dumps(v, ensure_ascii=False))
    salida["generos"] = salida["generos"].apply(lambda v: json.dumps(v, ensure_ascii=False))
    salida["tokens"] = salida["tokens"].apply(lambda v: json.dumps(v, ensure_ascii=False))
    Path(ruta).parent.mkdir(parents=True, exist_ok=True)
    salida.to_csv(ruta, index=False, encoding="utf-8")
    return ruta


# --------------------------------------------------------------------------- #
# Diagnostico del corpus
# --------------------------------------------------------------------------- #
def diagnostico(df, top=20):
    """Imprime los numeros que hay que mirar ANTES de entrenar nada.

    No es decoracion: varios de estos valores son los que despues hay que
    justificar en el informe (tamano del corpus, vocabulario disponible para
    Word2Vec, riesgo de truncamiento en SBERT, desbalance de generos).
    """
    n = len(df)
    tokens_totales = int(df["n_tokens_limpio"].sum())
    vocabulario = Counter(t for lista in df["tokens"] for t in lista)

    print("=" * 62)
    print("DIAGNOSTICO DEL CORPUS")
    print("=" * 62)
    print(f"Documentos                  : {n}")
    if n < 100:
        print("  !! La consigna del TP2 pide entre 100 y 200 libros.")
        print("     Corre:  python src/scraper.py --reiniciar")
    print(f"Tokens totales (limpio)     : {tokens_totales:,}")
    print(f"Vocabulario (tipos distintos): {len(vocabulario):,}")
    if tokens_totales:
        print(f"Razon tipo/token            : {len(vocabulario) / tokens_totales:.3f}")
    print(f"Palabras por doc (crudo)    : media {df['n_palabras_crudo'].mean():.0f}  "
          f"min {df['n_palabras_crudo'].min()}  max {df['n_palabras_crudo'].max()}")
    print(f"Tokens por doc (limpio)     : media {df['n_tokens_limpio'].mean():.0f}  "
          f"min {df['n_tokens_limpio'].min()}  max {df['n_tokens_limpio'].max()}")

    vacios = int((df["n_tokens_limpio"] == 0).sum())
    print(f"Documentos vacios tras limpiar: {vacios}"
          + ("   <- hay que excluirlos antes de vectorizar" if vacios else ""))

    print(f"\nPalabras con frecuencia 1   : {sum(1 for c in vocabulario.values() if c == 1):,} "
          f"({sum(1 for c in vocabulario.values() if c == 1) / max(len(vocabulario), 1):.0%} del vocabulario)")
    print("  -> Word2Vec con min_count=5 las descarta todas. Con un corpus chico")
    print("     esto define cuanto vocabulario le queda al modelo propio.")

    print(f"\nTOP {top} palabras del corpus (ya sin stopwords):")
    for palabra, cuenta in vocabulario.most_common(top):
        docs = sum(1 for lista in df["tokens"] if palabra in lista)
        print(f"   {palabra:<18} {cuenta:>4}   (en {docs}/{n} documentos)")

    generos = Counter(g for lista in df["generos"] for g in lista)
    print(f"\nGENEROS (etiqueta para colorear y filtrar; el modelo NO la ve):")
    for genero, cuenta in generos.most_common():
        marca = "  <- cubre todo el corpus" if cuenta == n else ""
        print(f"   {genero:<18} {cuenta:>4} libros{marca}")
    print("  -> Los generos que cubren el 100% no sirven ni para colorear ni para")
    print("     filtrar, y disparan el piso de azar. Los subgeneros son los utiles.")

    # Estimacion de truncamiento en SBERT. El conteo exacto de tokens lo hace el
    # tokenizer del modelo (Parte C); aca solo se estima para anticipar el
    # problema: en espanol un modelo tipo BERT usa ~1.5-1.8 subtokens por palabra.
    limite_palabras = 128 / 1.6
    truncados = int((df["n_palabras_crudo"] > limite_palabras).sum())
    print(f"\nESTIMACION de truncamiento en SBERT (limite 128 tokens):")
    print(f"   ~{truncados}/{n} documentos superarian el limite ({truncados / max(n, 1):.0%})")
    print("  -> Es una estimacion. En la Parte C hay que medirlo con el tokenizer")
    print("     real del modelo. El modelo trunca en silencio: no avisa.")
    print("=" * 62)


# --------------------------------------------------------------------------- #
def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--entrada", default=str(CSV_ENTRADA))
    parser.add_argument("--salida", default=str(CSV_SALIDA))
    parser.add_argument("--top", type=int, default=20,
                        help="cuantas palabras frecuentes mostrar")
    parser.add_argument("--sin-guardar", action="store_true",
                        help="solo imprime el diagnostico")
    args = parser.parse_args()

    df = preparar_corpus(cargar_corpus(args.entrada))
    diagnostico(df, top=args.top)

    print("\nEJEMPLO - las dos versiones del primer documento")
    print("-" * 62)
    fila = df.iloc[0]
    print(f"CRUDO  (a SBERT)      : {fila['texto_crudo'][:220]}...")
    print(f"LIMPIO (a TF-IDF/W2V) : {fila['texto_limpio'][:220]}...")
    print(f"\nTokens del documento 1 ({fila['n_tokens_limpio']}): {fila['tokens'][:15]} ...")

    if not args.sin_guardar:
        ruta = guardar(df, args.salida)
        print(f"\nGuardado: {ruta}")
        print("Releer con:")
        print('  pd.read_csv(ruta, keep_default_na=False,')
        print('              converters={"autores": json.loads, "generos": json.loads,')
        print('                          "tokens": json.loads})')


if __name__ == "__main__":
    main()
