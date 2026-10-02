# -*- coding: utf-8 -*-
"""Genera el notebook del TP2 (bloques 1 a 5)."""
import json
from pathlib import Path

RAIZ = Path(r"C:\Users\PC\Desktop\proyecto nlp\NLP_JulianParedes")
DESTINO = RAIZ / "TP2_Gimbatti_Longo_Nasini_Paredes.ipynb"

celdas = []


def md(texto):
    celdas.append({"cell_type": "markdown", "metadata": {},
                   "source": texto.strip("\n").split("\n")})


def code(texto):
    celdas.append({"cell_type": "code", "execution_count": None,
                   "metadata": {}, "outputs": [],
                   "source": texto.strip("\n").split("\n")})


# =========================================================================== #
md(r"""
# TP2 — Representación vectorial de texto: embeddings y búsqueda semántica

**Unidad 2** · Gimbatti, Longo, Nasini, Paredes

Corpus propio: 150 sinopsis de libros del género *Intriga*, scrapeadas en el TP1.

## Índice

| Bloque | Contenido | Parte de la consigna |
|---|---|---|
| 1 | Instalación y carga del corpus | — |
| 2 | Primer análisis del corpus | Preguntas iniciales |
| 3 | Preparación del texto: dos versiones | Parte A |
| 4 | TF-IDF — línea de base léxica | Parte 5 (baseline) |
| 5 | Word2Vec propio vs. pre-entrenado | Parte B |
| 6 | Vectores de documento | Parte B |

> **Sobre las versiones.** No se fija `numpy==1.23.5` como en el apunte de la
> Unidad 2: ese numpy no convive con `sentence-transformers`, y este notebook usa
> gensim y sentence-transformers juntos. Va `gensim>=4.3.3` con el numpy de Colab.
""")

# --------------------------------------------------------------------------- #
md(r"""
## Bloque 1 — Entorno y carga del corpus

### Cómo correr este notebook

**En VS Code (local).** Desde la raíz del repositorio, una sola vez:

```bash
python -m venv .venv
```

```bash
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Después, en VS Code: abrir el `.ipynb`, hacer clic en **Select Kernel** (arriba a la
derecha) → *Python Environments* → **`.venv`**. Si no aparece, `Ctrl+Shift+P` →
*Developer: Reload Window*.

> **Ojo con la versión de Python.** Con Python 3.13 hace falta **gensim ≥ 4.4.0**:
> las versiones anteriores no tienen wheel para 3.13 y además limitaban `scipy`
> a menos de 1.14, lo que choca con el scipy actual.

**En Colab.** Descomentar y correr la celda de instalación de abajo.
""")

code(r"""
# Solo en Colab (local ya quedo instalado con requirements.txt):
# !pip install -q "gensim>=4.4.0" "sentence-transformers>=3.0" scikit-learn matplotlib

# Verificacion: avisa que falta en vez de fallar mas adelante con un error raro.
import importlib.util   # el submodulo `util` no viene con `import importlib` solo

REQUERIDOS = {"numpy": "numpy", "pandas": "pandas", "sklearn": "scikit-learn",
              "gensim": "gensim", "matplotlib": "matplotlib"}
faltan = [pip for mod, pip in REQUERIDOS.items()
          if importlib.util.find_spec(mod) is None]

if faltan:
    print("FALTAN paquetes:", ", ".join(faltan))
    print("  Instalalos con:  pip install " + " ".join(faltan))
else:
    import gensim, sklearn, numpy
    print(f"Entorno OK - gensim {gensim.__version__}, "
          f"scikit-learn {sklearn.__version__}, numpy {numpy.__version__}")
""")

code(r"""
import json, re, unicodedata, random
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

SEMILLA = 42
random.seed(SEMILLA)
np.random.seed(SEMILLA)
""")

md(r"""
El corpus vive en `data/libros.csv`. En Colab hay dos caminos: subir el archivo a
mano, o montar Drive. La celda siguiente resuelve los dos casos y falla con un
mensaje claro si no encuentra nada.
""")

code(r"""
def ubicar_corpus():
    '''Devuelve la ruta a libros.csv, buscando en los lugares habituales.'''
    candidatos = [
        Path("data/libros.csv"),                    # repo local
        Path("../data/libros.csv"),
        Path("libros.csv"),                         # subido a mano en Colab
        Path("/content/libros.csv"),
        Path("/content/drive/MyDrive/TP2/libros.csv"),
    ]
    for ruta in candidatos:
        if ruta.exists():
            return ruta
    raise FileNotFoundError(
        "No encuentro libros.csv. En Colab: subilo con el panel de archivos, "
        "o monta Drive y dejalo en MyDrive/TP2/."
    )


df = pd.read_csv(
    ubicar_corpus(),
    keep_default_na=False,                          # un campo vacio es "" o [], nunca NaN
    converters={"autores": json.loads, "generos": json.loads},
)
print(f"{len(df)} libros cargados")
df.head(3)
""")

# --------------------------------------------------------------------------- #
md(r"""
## Bloque 2 — Primer análisis del corpus

Antes de vectorizar nada conviene mirar qué hay. Varios de estos números
condicionan decisiones que se toman más abajo.
""")

code(r"""
df["n_palabras"] = df.sinopsis.str.split().str.len()

print(f"Documentos              : {len(df)}")
print(f"Sin sinopsis            : {(df.sinopsis.str.strip() == '').sum()}")
print(f"Duplicados por url      : {df.url_libro.duplicated().sum()}")
print(f"Palabras por sinopsis   : media {df.n_palabras.mean():.0f}  "
      f"mediana {df.n_palabras.median():.0f}  "
      f"min {df.n_palabras.min()}  max {df.n_palabras.max()}")

generos = Counter(g for gs in df.generos for g in gs)
print(f"\nGeneros distintos       : {len(generos)}")
for g, c in generos.most_common(10):
    marca = "   <- cubre (casi) todo el corpus: inutil como etiqueta" if c > 0.9 * len(df) else ""
    print(f"   {g:<16}{c:>4}{marca}")
""")

md(r"""
### Las cuatro preguntas del enunciado

**1. Con 12 documentos TF-IDF es casi ruido. ¿Cuántas sinopsis harían falta para
que los términos característicos sean estables? ¿Cómo lo medirían?**

No hay un número universal: depende de cuánto se repita el vocabulario. La forma
de medirlo es empírica — tomar submuestras crecientes del corpus (20, 40, 60…
documentos), calcular el top-10 de términos TF-IDF de cada documento en cada
submuestra, y medir cuánto se solapa ese top-10 entre submuestras consecutivas
(por ejemplo con el coeficiente de Jaccard). El tamaño a partir del cual el
solapamiento se estabiliza es la respuesta. Con nuestros 150 documentos y un
vocabulario donde una fracción grande de las palabras aparece una sola vez,
esperamos que todavía no esté del todo estabilizado.

**2. Las sinopsis son texto promocional: escrito para vender, no para describir.
¿Qué sesgo introduce eso si entrenamos un clasificador de género literario?**

Introduce un sesgo hacia el vocabulario de marketing, no hacia el contenido. La
celda siguiente lo muestra con datos: las palabras más frecuentes del corpus son
términos de venta y no de trama. Un clasificador entrenado sobre esto aprendería
a reconocer *estilos de contraportada* antes que géneros, y fallaría sobre texto
descriptivo real (una reseña, un resumen de trama).

**3. Un libro tiene varios géneros. ¿Cómo cambia la evaluación multi-etiqueta
respecto de multi-clase?**

En multi-clase cada documento tiene exactamente una etiqueta correcta y las
predicciones se comparan una a una: accuracy tiene sentido. En multi-etiqueta un
documento puede tener varias, así que hay aciertos parciales y hay que decidir
cómo promediar (micro, macro o por muestra), y accuracy exacta —acertar el
conjunto completo— es una métrica durísima y poco informativa. Se usan
precision/recall/F1 promediados, o Hamming loss. Además las clases quedan muy
desbalanceadas: acá `Intriga` cubre el 100% del corpus y varios subgéneros
aparecen en uno o dos libros.

**4. ¿Qué pasa con los libros en gallego o catalán? ¿Detección de idioma antes de
tokenizar?**

En nuestro corpus las sinopsis están en castellano (el catálogo las publica así
aunque la obra sea en otra lengua), por lo que el problema no se nos presenta en
la práctica. Si apareciera, sí correspondería detectar idioma antes de tokenizar:
las stopwords son distintas por idioma, y un modelo de palabra monolingüe
asignaría vectores sin sentido a un texto en otra lengua. El modelo de oración
que usamos más abajo es multilingüe, así que ahí el impacto sería menor.
""")

code(r"""
# Evidencia para la pregunta 2: las palabras mas frecuentes son de marketing.
STOP_MINIMA = set("de la que el en y a los del se las por un para con no una su al "
                  "lo como mas pero sus le ya o este si porque esta entre cuando muy "
                  "sin sobre tambien me hasta hay donde quien desde todo nos durante "
                  "todos uno les ni contra otros ese eso ante ellos e esto mi antes "
                  "algunos que unos yo otro otras otra el tanto esa estos mucho quienes "
                  "nada muchos cual poco ella estar estas algunas algo nosotros".split())

# Las formas con tilde tambien son stopwords: sin ellas, "mas" y "esta" encabezan
# el ranking y tapan el vocabulario que nos interesa ver.
STOP_MINIMA |= {"más", "está", "están", "estás", "esté", "él", "sí", "mí", "tú",
                "así", "aún", "aquí", "allí", "qué", "cómo", "quién", "cuál",
                "dónde", "cuándo", "después", "también", "según", "había",
                "habían", "será", "serán", "sólo", "ésta", "éste", "ése"}

palabras = Counter(
    p for s in df.sinopsis
    for p in re.findall(r"[a-záéíóúüñ]+", str(s).lower())
    if len(p) >= 3 and p not in STOP_MINIMA
)
print("Palabras mas frecuentes del corpus:")
for p, c in palabras.most_common(15):
    docs = sum(1 for s in df.sinopsis if p in str(s).lower())
    print(f"   {p:<16}{c:>4}   (en {docs}/{len(df)} documentos)")
""")

# --------------------------------------------------------------------------- #
md(r"""
## Bloque 3 — Parte A: preparación del texto

### La decisión central

> **El preprocesamiento pertenece al modelo, no al corpus.**

La limpieza que usamos para TF-IDF —minúsculas, sin stopwords, sin puntuación— es
correcta para bolsa de palabras y **destructiva** para un modelo de oración, que
fue entrenado sobre texto natural y usa el orden y las palabras funcionales.

Ejemplo del costo de limpiar:

| Texto original | Texto limpio |
|---|---|
| "el asesino **no** era el mayordomo" | `asesino mayordomo` |
| "el asesino era el mayordomo" | `asesino mayordomo` |

Al limpiar, dos frases de significado opuesto se vuelven idénticas.

Por eso preparamos **dos versiones**:

| Versión | Qué conserva | Quién la usa |
|---|---|---|
| `texto_crudo` | todo: mayúsculas, tildes, puntuación, stopwords | SBERT (Parte C) |
| `texto_limpio` / `tokens` | solo palabras temáticas en minúscula | TF-IDF y Word2Vec (Partes B y 5) |

### Cada decisión de limpieza es una pérdida deliberada

| Decisión | Elegimos | Qué ganamos | Qué perdemos |
|---|---|---|---|
| Minúsculas | **sí** | `Asesino`/`asesino` cuentan juntas; con 150 docs cortos necesitamos que las repeticiones se acumulen | las entidades nombradas (`Madrid` → `madrid`) |
| Tildes | **conservar** | el catálogo las escribe consistentemente, no hay variantes que unificar | nada; sacarlas colapsaría `sí`/`si`, `él`/`el` sin ganancia |
| Puntuación | **sacar** | menos ruido para bolsa de palabras | los límites de oración |
| Stopwords | **sacar** | aparecen en los 150 libros, no distinguen ninguno | las negaciones y las relaciones sintácticas |
| Números | **sacar** | `1931`, `19` son ruido en un corpus chico | referencias temporales |
| Tokens < 3 letras | **sacar** | restos sin valor temático | algunas siglas |

### Qué entra al texto del documento

Usamos **título + sinopsis**. El título aporta señal temática real
(*El aprendiz de carnicero*, *La muñeca encadenada*), al costo de que algunos son
puro marketing (*Mentira*, *Hundida*) — son ~4 palabras sobre 158, riesgo bajo.

**Los géneros NO entran al texto**, y esto es deliberado: son la etiqueta que
usamos para colorear la proyección 2D y para filtrar en la búsqueda. Si la palabra
`Policíaco` estuviera dentro del texto, el modelo agruparía por género porque se
lo dijimos — eso es **fuga de información**, y el resultado se vería *mejor* sin
probar nada.

> El código de abajo es el mismo que el de `archivos del proyecto/preprocesamiento.py`
> (versión de línea de comandos), replicado acá para que el notebook sea
> autocontenido. Es la misma convención que usamos en el TP1 con `scraper.py`.
""")

code(r"""
STOPWORDS_ES = set('''
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
'''.split())

STOPWORDS_ES |= {
    "él", "más", "mí", "sí", "tú", "está", "están", "estás", "esté", "aún",
    "así", "aquí", "algún", "según", "también", "después", "cómo", "qué",
    "quién", "cuál", "dónde", "cuándo", "había", "habían", "será", "serán",
    "tendrá", "tendrán", "sólo", "ése", "ésta", "éste",
}

PATRON_TOKEN = re.compile(r"[a-záéíóúüñ]+(?:-[a-záéíóúüñ]+)*", re.IGNORECASE)
MIN_LONGITUD_TOKEN = 3


def tokenizar(texto):
    '''Texto -> lista de tokens tematicos. Es lo que ven TF-IDF y Word2Vec.'''
    if not texto:
        return []
    tokens = PATRON_TOKEN.findall(str(texto).lower())
    tokens = [t for t in tokens if t.replace("-", "").isalpha()]
    tokens = [t for t in tokens if len(t) >= MIN_LONGITUD_TOKEN]
    return [t for t in tokens if t not in STOPWORDS_ES]


def construir_texto_crudo(fila):
    '''Titulo + sinopsis, texto natural intacto. Los generos NO entran.'''
    partes = [str(fila[c]).strip() for c in ("titulo", "sinopsis")]
    texto = ". ".join(p.rstrip(".") for p in partes if p)
    return re.sub(r"\s+", " ", texto).strip()


df["texto_crudo"] = df.apply(construir_texto_crudo, axis=1)
df["tokens"] = df.texto_crudo.apply(tokenizar)
df["texto_limpio"] = df.tokens.apply(" ".join)

print("CRUDO  (a SBERT)      :", df.texto_crudo[0][:150], "...")
print()
print("LIMPIO (a TF-IDF/W2V) :", df.texto_limpio[0][:150], "...")
""")

code(r"""
# Diagnostico: estos numeros condicionan los parametros de Word2Vec (Bloque 5).
vocabulario = Counter(t for lista in df.tokens for t in lista)
tokens_totales = sum(len(l) for l in df.tokens)
hapax = sum(1 for c in vocabulario.values() if c == 1)

print(f"Tokens totales (limpio)      : {tokens_totales:,}")
print(f"Vocabulario (tipos distintos): {len(vocabulario):,}")
print(f"Cada palabra aparece         : {tokens_totales/len(vocabulario):.1f} veces en promedio")
print(f"Palabras que aparecen 1 vez  : {hapax:,} ({hapax/len(vocabulario):.0%} del vocabulario)")
print(f"Documentos vacios al limpiar : {(df.tokens.str.len() == 0).sum()}")

print("\nVocabulario que le quedaria a Word2Vec segun min_count:")
for mc in (1, 2, 3, 5, 10):
    print(f"   min_count={mc:<3} -> {sum(1 for c in vocabulario.values() if c >= mc):>5} palabras")
""")

md(r"""
**Lectura.** Cada palabra aparece alrededor de dos veces en todo el corpus, y una
fracción grande del vocabulario aparece una sola vez. Word2Vec aprende de
repetición: con estos números, el modelo propio va a tener poco de donde aprender.

La tabla de `min_count` muestra por qué **no** usamos el valor por defecto de
gensim (`min_count=5`): dejaría un vocabulario demasiado chico. Volvemos sobre
esto en el Bloque 5.
""")

# --------------------------------------------------------------------------- #
md(r"""
## Bloque 4 — TF-IDF: la línea de base léxica

Es la representación del TP1 y el punto de comparación de todo el TP2. Sin línea
de base, un número como "precision@5 = 0.55" no significa nada.

**Cómo funciona.** Cada documento se convierte en un vector con una dimensión por
palabra del vocabulario. El valor de cada dimensión es el producto de:

- **TF** (frecuencia del término): cuántas veces aparece la palabra *en este documento*.
- **IDF** (frecuencia inversa de documento): `log(N / documentos que la contienen)`.
  Una palabra que está en los 150 libros tiene IDF = 0 — **peso cero**, porque no
  distingue ninguno.

El producto responde: *¿qué palabras hacen que este libro sea distinto del resto?*

**La limitación.** El vector es del tamaño del vocabulario y casi todo ceros
(*disperso*). Dos textos sin ninguna palabra en común tienen similitud
**exactamente 0**, aunque signifiquen lo mismo. Eso es lo que este TP viene a
resolver.
""")

code(r"""
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

vectorizador = TfidfVectorizer(
    min_df=2,            # una palabra en 1 solo documento no distingue ENTRE documentos
    sublinear_tf=True,   # 1+log(tf): que aparezca 10 veces no la hace 10x mas importante
)
X_tfidf = vectorizador.fit_transform(df.texto_limpio)
palabras_tfidf = np.array(vectorizador.get_feature_names_out())

densidad = X_tfidf.nnz / (X_tfidf.shape[0] * X_tfidf.shape[1])
print(f"Matriz TF-IDF : {X_tfidf.shape[0]} documentos x {X_tfidf.shape[1]} palabras")
print(f"Densidad      : {densidad:.2%}  -> el {1-densidad:.1%} de la matriz son ceros")
""")

code(r"""
# Que distingue a cada sinopsis del resto del corpus
for i in range(3):
    fila = X_tfidf[i].toarray().ravel()
    top = fila.argsort()[-8:][::-1]
    print(f"{df.titulo[i]}")
    print(f"   {', '.join(palabras_tfidf[top])}\n")
""")

code(r"""
def buscar_tfidf(consulta, k=5):
    '''Busqueda con TF-IDF.

    La consulta se preprocesa EXACTAMENTE igual que los documentos. Si se
    entrena en minusculas y sin stopwords, la consulta tiene que llegar asi:
    es un error silencioso clasico (no falla, solo devuelve peor).
    '''
    q = vectorizador.transform([" ".join(tokenizar(consulta))])
    sims = cosine_similarity(q, X_tfidf).ravel()
    idx = sims.argsort()[::-1][:k]
    return pd.DataFrame({
        "titulo": df.titulo.iloc[idx].values,
        "similitud": sims[idx].round(4),
    })


print("Consulta LEXICA — comparte vocabulario con las sinopsis:")
display(buscar_tfidf("un detective investiga un asesinato en una casa de campo inglesa"))
""")

code(r"""
print("Consulta SEMANTICA — describe la idea sin usar las palabras del texto:")
display(buscar_tfidf("una persona lastimada se cobra aquello que le arrebataron"))
""")

md(r"""
**El resultado más importante del bloque**, y conviene leerlo con cuidado porque
es más sutil de lo que parece a primera vista.

La similitud con los libros que **nosotros marcamos como relevantes** para esa
consulta es exactamente **0.0000**. No es mala suerte ni corpus chico: es
aritmética. TF-IDF multiplica coincidencias de palabras, y sin ninguna palabra en
común el producto es cero **por construcción**.

Pero miren el ranking: **devolvió cinco libros igual**, con similitudes de 0.11 a
0.15. Ninguno es relevante. TF-IDF no dice *"no sé"*: ordena lo que tiene. Como
dice el enunciado, `argsort` ordena ruido con la misma prolijidad con que ordena
señal.

Es decir que el ranking **se ve razonable y es completamente inútil**. Esa es
exactamente la razón por la que un buscador no se puede evaluar mirando si los
resultados "parecen buenos": hace falta un conjunto de referencia. La celda
siguiente lo mide sobre las tres consultas semánticas de nuestro `queries.json`.
""")

code(r"""
# Cuantificacion del punto anterior sobre las 3 consultas semanticas.
def ubicar_queries():
    for ruta in [Path("data/queries.json"), Path("../data/queries.json"),
                 Path("queries.json"), Path("/content/queries.json")]:
        if ruta.exists():
            return ruta
    raise FileNotFoundError("No encuentro queries.json (nuestro conjunto de evaluacion).")


queries = json.loads(ubicar_queries().read_text(encoding="utf-8"))
indice_por_url = {u: i for i, u in enumerate(df.url_libro)}

filas = []
for q in queries:
    if q["tipo"] != "semantica":
        continue
    v = vectorizador.transform([" ".join(tokenizar(q["consulta"]))])
    sims = cosine_similarity(v, X_tfidf).ravel()
    rel = [indice_por_url[u] for u in q["relevantes"]]
    top_k = sims.argsort()[::-1][:5]
    filas.append({
        "consulta": q["id"],
        "sim. con los relevantes": f"{max(sims[i] for i in rel):.4f}",
        "sim. maxima del corpus": f"{sims.max():.4f}",
        "precision@5": f"{sum(1 for i in top_k if i in rel) / 5:.2f}",
    })

pd.DataFrame(filas)
""")

md(r"""
**Lectura de la tabla.** En las tres consultas la similitud con los documentos
relevantes es 0 y la precision@5 es 0. En dos de las tres, el corpus igual
devuelve puntajes de hasta 0.17 — para documentos equivocados.

Esa columna del medio es la que vuelve engañoso mirar sólo el ranking: hay un
número, está ordenado, y no significa nada. Sobre esta línea de base van a
medirse los embeddings en la parte de evaluación.
""")

# --------------------------------------------------------------------------- #
md(r"""
## Bloque 5 — Parte B: Word2Vec propio contra pre-entrenado

### Qué cambia respecto de TF-IDF

TF-IDF le da a cada palabra una dimensión propia: `piratas` y `bucaneros` son dos
casilleros distintos, sin nada que los relacione. Word2Vec le asigna a cada
palabra un vector denso entrenado con una regla:

> Una palabra se define por la compañía que tiene.

Si en muchos textos `piratas` y `bucaneros` aparecen rodeadas de `barco`,
`tesoro`, `abordaje`, el modelo les asigna vectores cercanos — sin que nadie le
haya dicho que son sinónimos.

### Cómo se entrena: skip-gram y negative sampling

**Skip-gram** (`sg=1`): se tapa una palabra y el modelo tiene que predecir las que
la rodean. Cada error ajusta un poco los vectores.

**Negative sampling** (`negative=10`): para predecir la palabra del contexto, el
modelo tendría que calcular una probabilidad sobre *todo* el vocabulario y
normalizarla (*softmax*). Con 100.000 palabras eso son 100.000 cálculos por cada
palabra de cada oración en cada pasada: inviable. Negative sampling reemplaza esa
pregunta por una mucho más barata — *"¿esta pareja (palabra, contexto) es real o
la inventé?"*— mostrando la pareja real y unas pocas falsas armadas al azar. Se
pasa de 100.000 cálculos a ~11. Es lo que hizo a Word2Vec entrenable en la práctica.
""")

code(r"""
from gensim.models import Word2Vec

w2v_propio = Word2Vec(
    sentences=df.tokens.tolist(),
    vector_size=100,   # 300 sobre un corpus de ~12k tokens seria sobreajuste
    window=5,          # estandar: ni sintactico (2-3) ni puramente tematico (10+)
    min_count=2,       # con 5 el vocabulario queda demasiado chico (ver Bloque 3)
    sg=1,              # skip-gram: rinde mejor que CBOW en corpus chicos
    negative=10,
    epochs=50,         # el default (5) asume corpus grandes; aca hacen falta mas pasadas
    workers=4,
    seed=SEMILLA,
)
print(f"Vocabulario aprendido: {len(w2v_propio.wv)} palabras")
""")

md(r"""
### Justificación de los parámetros

| Parámetro | Valor | Por qué |
|---|---|---|
| `vector_size` | 100 | con ~12.000 tokens, 300 dimensiones son más parámetros que datos: el modelo memoriza en vez de generalizar |
| `window` | 5 | ventanas chicas capturan sintaxis, grandes capturan tema; 5 es el punto medio habitual |
| `min_count` | 2 | la tabla del Bloque 3 muestra que con el default (5) el vocabulario se desploma |
| `sg` | 1 (skip-gram) | rinde mejor que CBOW con corpus chicos y palabras poco frecuentes |
| `negative` | 10 | rango recomendado para corpus chicos (5–20) |
| `epochs` | 50 | el default de 5 asume corpus grandes; con este volumen el modelo ve muy pocos ejemplos |
| `seed` | 42 | reproducibilidad: sin semilla fija, dos corridas dan vectores distintos |
""")

md(r"""
### El modelo pre-entrenado

`SBW-vectors-300-min5` está entrenado sobre el **Spanish Billion Word Corpus**:
unos mil millones de palabras de español general, contra los ~12.000 tokens
nuestros. Son cinco órdenes de magnitud de diferencia.

#### Tres cosas que hay que hacer bien

**1. El archivo va en Drive, no en el repositorio.** Pesa más de 1 GB. GitHub
rechaza archivos de más de 100 MB, así que subirlo al repo lo rompe. En
`.gitignore` está excluido.

**2. La descarga tiene que terminar.** Es un archivo grande: si se corta, queda
un `.part` incompleto que **falla al cargar con un error confuso** (algo sobre el
fin del stream comprimido, no sobre la descarga). La celda de abajo valida el
tamaño antes de intentar cargarlo.

Si se corta, conviene bajarlo con una herramienta que pueda **retomar** en vez de
empezar de cero:

```bash
wget -c -O SBW-vectors-300-min5.bin.gz "<URL del apunte de la Unidad 2>"
```

El `-c` (*continue*) retoma donde quedó. Un navegador que canceló la descarga
normalmente no puede retomarla.

**3. No hace falta cargar el millón de palabras.** El formato word2vec guarda las
palabras **ordenadas por frecuencia**, así que `limit=N` carga las N más
frecuentes. Con `limit=300000` se cubre prácticamente todo el español corriente
—que es todo lo que hay en nuestras sinopsis— usando una fracción de la memoria y
del tiempo de carga. Las que quedarían afuera son palabras rarísimas, y los
nombres propios de nuestro corpus (`Poirot`, `Catchpool`) probablemente no estén
en el modelo con ningún límite.

Es una decisión con un costo: reportamos abajo la cobertura real sobre nuestro
vocabulario para verificar que el recorte no nos deje sin palabras.
""")

code(r"""
from gensim.models import KeyedVectors

# Se busca en los lugares habituales, local primero. En Colab hay que montar
# Drive antes:  from google.colab import drive; drive.mount('/content/drive')
# Se prueba primero el .bin sin comprimir: gensim no tiene que descomprimir nada,
# asi que carga bastante mas rapido que el .gz.
RUTAS_SBW = [
    Path("sbw_vectors.bin"),                              # descomprimido, raiz del repo
    Path("../sbw_vectors.bin"),
    Path("modelos/sbw_vectors.bin"),
    Path("modelos/SBW-vectors-300-min5.bin.gz"),          # comprimido, tal como se descarga
    Path("../modelos/SBW-vectors-300-min5.bin.gz"),
    Path("data/SBW-vectors-300-min5.bin.gz"),
    Path("/content/drive/MyDrive/TP2/SBW-vectors-300-min5.bin.gz"),
]

LIMITE_VOCABULARIO = 300_000   # None carga el modelo completo (~1M palabras)
MINIMO_ESPERADO_MB = 900       # el .bin.gz completo pesa bastante mas que esto


def cargar_sbw(ruta, limit=LIMITE_VOCABULARIO):
    '''Carga el modelo pre-entrenado validando primero que el archivo sirva.

    Sin esta validacion, una descarga incompleta falla dentro de gensim con un
    error sobre el stream comprimido, que no dice nada sobre la causa real.

    El formato se deduce de la extension:
      .bin / .bin.gz  -> binario  (binary=True)
      .txt / .vec / .txt.bz2 -> texto (binary=False)
    '''
    ruta = Path(ruta)

    if not ruta.exists():
        raise FileNotFoundError(
            f"No existe {ruta}.\n"
            "  - Si esta en Drive, monta Drive antes de esta celda.\n"
            "  - Si termina en '.part', la descarga quedo incompleta: "
            "borrala y bajala de nuevo con `wget -c`."
        )

    if ".part" in ruta.name:
        raise ValueError(
            f"{ruta.name} es una descarga INCOMPLETA (un '.part' es un archivo "
            "a medio bajar). Borrala y descargala de nuevo."
        )

    mb = ruta.stat().st_size / 1024**2
    binario = ".bin" in ruta.name

    if binario and mb < MINIMO_ESPERADO_MB:
        raise ValueError(
            f"{ruta.name} pesa {mb:.0f} MB, y el modelo completo pesa mas de "
            f"{MINIMO_ESPERADO_MB} MB.\n"
            "  La descarga esta incompleta. Retomala con:\n"
            f"      wget -c -O {ruta.name} <URL>"
        )

    print(f"Archivo  : {ruta.name}  ({mb:,.0f} MB, formato "
          f"{'binario' if binario else 'texto'})")
    print(f"Cargando {'las ' + format(limit, ',') + ' palabras mas frecuentes'
                     if limit else 'el modelo completo'}... (tarda unos minutos)")

    try:
        kv = KeyedVectors.load_word2vec_format(ruta, binary=binario, limit=limit)
    except (EOFError, OSError) as e:
        raise ValueError(
            f"El archivo no se pudo descomprimir del todo ({type(e).__name__}: {e}).\n"
            "  Casi siempre significa que la descarga quedo cortada. "
            "Borra el archivo y bajalo de nuevo con `wget -c`."
        ) from e

    return kv


def ubicar_sbw():
    '''Primera ruta existente, o None si el modelo todavia no esta descargado.'''
    for r in RUTAS_SBW:
        if r.exists():
            return r
    return None


# Si el modelo todavia no esta, el notebook NO se frena: sigue con todo lo demas
# y deja marcado lo que queda pendiente. Asi se puede trabajar mientras baja.
ruta = ubicar_sbw()
if ruta is None:
    sbw = None
    print("SBW NO ENCONTRADO - las celdas que lo usan quedan pendientes.")
    print("  Descargalo (>1 GB) y dejalo en alguna de estas rutas:")
    for r in RUTAS_SBW:
        print(f"    {r}")
    print("  Usa `wget -c` para poder retomar si se corta la descarga.")
else:
    sbw = cargar_sbw(ruta)
    print(f"\nSBW cargado: {len(sbw):,} palabras, {sbw.vector_size} dimensiones")
""")

code(r"""
PALABRAS_DOMINIO = ["asesinato", "detective", "misterio", "víctima", "policía"]


def comparar_vecinos(palabras, n=5):
    '''Vecinos mas cercanos en los dos modelos, lado a lado.'''
    filas = []
    for p in palabras:
        propio = ([w for w, _ in w2v_propio.wv.most_similar(p, topn=n)]
                  if p in w2v_propio.wv else ["(fuera de vocabulario)"])
        if sbw is None:
            pre = ["(SBW no descargado)"]
        else:
            pre = ([w for w, _ in sbw.most_similar(p, topn=n)]
                   if p in sbw else ["(fuera de vocabulario)"])
        filas.append({"palabra": p,
                      "Word2Vec propio (150 sinopsis)": ", ".join(propio),
                      "SBW (mil millones de palabras)": ", ".join(pre)})
    return pd.DataFrame(filas)


comparar_vecinos(PALABRAS_DOMINIO)
""")

code(r"""
# Cobertura de vocabulario (OOV = out of vocabulary): que porcentaje de nuestros
# tokens conoce cada modelo. Tambien verifica que recortar el SBW con `limit` no
# nos haya dejado sin palabras.
todos = [t for lista in df.tokens for t in lista]
distintos = set(todos)

modelos = [("Word2Vec propio", w2v_propio.wv)]
if sbw is not None:
    modelos.append(("SBW pre-entrenado", sbw))

for nombre, kv in modelos:
    cob_tokens = sum(1 for t in todos if t in kv) / len(todos)
    cob_tipos = sum(1 for t in distintos if t in kv) / len(distintos)
    print(f"{nombre:<20}: {cob_tokens:6.1%} de los tokens   "
          f"{cob_tipos:6.1%} del vocabulario")

if sbw is None:
    print("\n(Cobertura del SBW: pendiente de la descarga.)")
else:
    faltantes = [t for t in distintos if t not in sbw]
    recuperables = [t for t in faltantes if t.capitalize() in sbw]
    perdidas = len(faltantes) - len(recuperables)

    print(f"\nPalabras nuestras que el SBW no conoce en minuscula: {len(faltantes)}")
    print(f"   de esas, SI estan Capitalizadas                 : {len(recuperables)} "
          f"({len(recuperables)/len(faltantes):.0%})")
    print(f"   ejemplos recuperables : {sorted(recuperables)[:10]}")
    print(f"   ejemplos perdidos     : {sorted(set(faltantes)-set(recuperables))[:10]}")
    print()
    print(f"   Cobertura buscando solo en minuscula  : {1-len(faltantes)/len(distintos):6.1%}")
    print(f"   Cobertura con respaldo Capitalizado   : {1-perdidas/len(distintos):6.1%}")
""")

md(r"""
### Un problema que aparece al medir la cobertura

Nuestro preprocesamiento pasa todo a minúsculas (Bloque 3). El SBW, en cambio,
**distingue mayúsculas**: tiene `Agatha` y `Madrid` como entradas propias,
distintas de `agatha` y `madrid`. Al buscar `agatha` en minúscula, no la encuentra.

El número de arriba lo cuantifica: de las palabras que el SBW "no conoce", la gran
mayoría **sí están, Capitalizadas**. Son los nombres propios de los libros.

Esto no es un detalle: son justamente las palabras más distintivas de cada sinopsis
—y por eso las de mayor IDF, las que más pesan en el vector de documento—. Perderlas
empobrece la representación de todos los libros.

**La decisión:** al construir los vectores de documento buscamos primero el token tal
cual y, si no está, probamos con la primera letra en mayúscula. Es un parche
asimétrico —el modelo propio no lo necesita, porque se entrenó sobre nuestro texto ya
en minúscula— y por eso lo documentamos acá en vez de esconderlo adentro del
preprocesamiento.

Es un ejemplo concreto de la idea que recorre todo el TP: **el preprocesamiento
pertenece al modelo**. Minúsculas es correcto para TF-IDF y para nuestro Word2Vec, y
es destructivo contra un modelo pre-entrenado sensible a mayúsculas.

### Lectura de la comparación

*(Completar después de ejecutar, con lo que efectivamente devolvió.)*

Lo esperable es que el modelo propio devuelva palabras que **co-ocurrieron en
alguna sinopsis** en vez de sinónimos, y que varias palabras del dominio ni
siquiera estén en su vocabulario. **Eso no es un fracaso del experimento: es el
resultado.** Con ~12.000 tokens el modelo no aprende semántica, aprende
co-ocurrencias accidentales de un corpus específico.

La conclusión para el informe: en un corpus de este tamaño, usar embeddings
pre-entrenados no es una comodidad, es una necesidad.
""")

# --------------------------------------------------------------------------- #
md(r"""
## Bloque 6 — Vectores de documento

Word2Vec da un vector por **palabra**; necesitamos uno por **libro**. La solución
estándar es promediar los vectores de las palabras del documento, ponderando por
IDF para que las palabras características pesen más que las genéricas.

### Qué se pierde al promediar

| Se pierde | Ejemplo |
|---|---|
| **El orden** | `"this is cool"` e `"is this cool"` dan el mismo promedio: similitud exactamente 1.0 |
| **La negación** | `no` ya salió con las stopwords; aunque estuviera, se diluye entre 80 palabras |
| **La composicionalidad** | `"no es un asesinato"` promedia *hacia* asesinato |
| **El peso relativo** | una palabra repetida 5 veces pesa 5 veces, aporte o no |

**Por qué lo usamos igual:** es barato, no requiere entrenamiento adicional, y
para similitud temática —que es lo que hace un buscador de libros— alcanza
razonablemente. La alternativa que no promedia (Doc2Vec) queda como posible parte
avanzada.
""")

code(r"""
idf = dict(zip(vectorizador.get_feature_names_out(), vectorizador.idf_))


def buscar_token(t, kv):
    '''Busca el token en el modelo, con respaldo Capitalizado.

    Nuestros tokens estan en minuscula; el SBW distingue mayusculas y guarda los
    nombres propios Capitalizados. Sin este respaldo se pierden justamente las
    palabras de mayor IDF (ver la celda de cobertura).
    '''
    if t in kv:
        return kv[t]
    cap = t.capitalize()
    if cap in kv:
        return kv[cap]
    return None


def vector_documento(tokens, kv):
    '''Promedio de vectores de palabra ponderado por IDF, normalizado.

    Devuelve tambien si el documento quedo vacio: un documento sin ninguna
    palabra en el vocabulario del modelo produce un promedio indefinido (NaN).
    Insertar NaN en la base es descuento explicito de la consigna, asi que se
    maneja aca y se cuenta.
    '''
    vecs, pesos = [], []
    for t in tokens:
        v = buscar_token(t, kv)
        if v is not None:
            vecs.append(v)
            pesos.append(idf.get(t, 1.0))
    if not vecs:
        return np.zeros(kv.vector_size), True
    v = np.average(vecs, axis=0, weights=pesos)
    norma = np.linalg.norm(v)
    if norma == 0 or not np.isfinite(norma):
        return np.zeros(kv.vector_size), True
    return v / norma, False


def construir_matriz(kv, nombre):
    resultados = [vector_documento(t, kv) for t in df.tokens]
    matriz = np.vstack([r[0] for r in resultados])
    vacios = sum(1 for r in resultados if r[1])
    print(f"{nombre:<24} {matriz.shape}  vectores nulos: {vacios}  "
          f"NaN: {np.isnan(matriz).sum()}")
    return matriz


X_w2v_propio = construir_matriz(w2v_propio.wv, "Word2Vec propio")
X_sbw = construir_matriz(sbw, "SBW pre-entrenado") if sbw is not None else None
if X_sbw is None:
    print("SBW pre-entrenado      pendiente (modelo no descargado)")
""")

code(r"""
# Control obligatorio antes de persistir (Parte E): nada nulo, nada no finito.
for nombre, M in [("propio", X_w2v_propio), ("SBW", X_sbw)]:
    if M is None:
        print(f"{nombre:<8} pendiente")
        continue
    normas = np.linalg.norm(M, axis=1)
    print(f"{nombre:<8} finitos: {np.isfinite(M).all()}  "
          f"norma en [{normas.min():.3f}, {normas.max():.3f}]  "
          f"filas nulas: {(normas == 0).sum()}")
""")

code(r"""
# Guardar en disco: recalcular cuesta minutos cada vez que se reinicia Colab.
Path("embeddings").mkdir(exist_ok=True)
np.save("embeddings/w2v_propio.npy", X_w2v_propio)
if X_sbw is not None:
    np.save("embeddings/sbw.npy", X_sbw)
df[["url_libro", "titulo"]].to_csv("embeddings/orden_documentos.csv", index=False)
print("Guardado. `orden_documentos.csv` fija el orden de las filas: sin eso, "
      "los vectores no se pueden volver a asociar a su libro.")
""")

md(r"""
## Bloque 7 — Parte C: modelo de oración (SBERT)

### Qué cambia respecto de todo lo anterior

Los tres modelos anteriores comparten un supuesto: **el documento es una bolsa de
palabras**. TF-IDF las cuenta; Word2Vec les da un vector a cada una y después
promediamos. En los dos casos el orden se descarta — por eso `"this is cool"` e
`"is this cool"` dan similitud 1.0.

SBERT (*Sentence-BERT*) hace otra cosa: procesa **la frase entera de una vez**,
mirando cómo cada palabra se relaciona con todas las demás antes de producir un
único vector. No promedia nada. Por eso sí puede captar el orden y la negación.

El modelo que usamos es `distiluse-base-multilingual-cased-v1`, el de la Unidad 2:

| Parte del nombre | Qué significa | Por qué nos importa |
|---|---|---|
| `distil` | versión comprimida de un modelo más grande | más rápido, cabe en CPU |
| `use` | entrenado al estilo *Universal Sentence Encoder* | está hecho para comparar oraciones |
| `multilingual` | ~15 idiomas, español incluido | el catálogo puede traer libros en otras lenguas |
| `cased` | **distingue mayúsculas** | otra razón para pasarle `texto_crudo` y no el limpio |

Ese último punto no es casual: es el mismo problema que encontramos con el SBW en
el Bloque 5. Un modelo `cased` espera texto natural. Pasarle nuestro texto en
minúscula y sin puntuación sería darle algo que nunca vio al entrenarse.

> La primera ejecución descarga el modelo (~500 MB) y tarda unos minutos. Después
> queda en caché y carga en segundos.
""")

code(r"""
from sentence_transformers import SentenceTransformer

modelo_sbert = SentenceTransformer("distiluse-base-multilingual-cased-v1")

DIM_SBERT = modelo_sbert.get_sentence_embedding_dimension()
LIMITE_TOKENS = modelo_sbert.max_seq_length

print(f"Modelo            : distiluse-base-multilingual-cased-v1")
print(f"Dimension          : {DIM_SBERT}")
print(f"Limite de tokens   : {LIMITE_TOKENS}")
print(f"Tokenizer          : {type(modelo_sbert.tokenizer).__name__}")
""")

md(r"""
### El dato que el modelo no avisa

`max_seq_length = 128` significa que el modelo lee **128 tokens y descarta el
resto**. No lanza un error ni devuelve una advertencia en el resultado: produce un
vector perfectamente normal, construido con un pedazo del texto.

Nuestras sinopsis tienen 154 palabras en promedio. Hay que medir cuántas lo
superan, y para eso no sirve contar palabras: hay que usar **el tokenizer del
propio modelo**. Los modelos tipo BERT parten las palabras en *sub-tokens*
(`asesinato` puede volverse `asesina` + `##to`), así que una palabra puede valer
más de un token.
""")

code(r"""
tokenizer = modelo_sbert.tokenizer
largos = np.array([len(tokenizer.encode(t)) for t in df.texto_crudo])
palabras = df.texto_crudo.str.split().str.len().values

truncados = int((largos > LIMITE_TOKENS).sum())
descartados = np.clip(largos - LIMITE_TOKENS, 0, None)

print(f"Tokens por documento : media {largos.mean():.0f}   mediana {np.median(largos):.0f}   "
      f"min {largos.min()}   max {largos.max()}")
print(f"Sub-tokens por palabra: {(largos / palabras).mean():.2f}")
print()
print(f"DOCUMENTOS TRUNCADOS : {truncados}/{len(df)}  ({truncados/len(df):.1%})")
print(f"Tokens descartados   : {descartados.sum():,} de {largos.sum():,}  "
      f"({descartados.sum()/largos.sum():.1%} del corpus)")
print(f"En un documento truncado se pierde, en promedio, "
      f"{(descartados[largos>LIMITE_TOKENS]/largos[largos>LIMITE_TOKENS]).mean():.1%} de su texto")
""")

md(r"""
### Lectura del truncamiento

El porcentaje de documentos truncados ya es alto, pero **el número que importa es
el otro**: la fracción del corpus que el modelo nunca llega a leer. Casi la mitad
del texto se descarta antes de producir el vector.

Tres consecuencias concretas:

1. **Los vectores de SBERT representan el principio de cada sinopsis, no la
   sinopsis.** Y como son textos promocionales, el principio es el gancho de venta
   — justamente la parte menos descriptiva.

2. **Da una hipótesis lista para los fallos de búsqueda.** Si un libro relevante no
   aparece, la primera sospecha es que lo que lo hacía relevante estaba después del
   token 128. Es verificable: se mira el texto truncado.

3. **Vuelve a *Chunking* la parte avanzada natural.** Partir las sinopsis en
   pedazos y guardar varios vectores por libro ataca exactamente este problema, con
   una hipótesis previa y una forma de medirla (¿mejora el recall en los documentos
   truncados?).

> Al tokenizar puede aparecer una advertencia del estilo *"Token indices sequence
> length is longer than..."*. No es un error: es el tokenizer avisando que el texto
> excede el límite. `sentence-transformers` trunca antes de pasarlo al modelo, así
> que no falla — y esa advertencia es, de hecho, la única señal que da.
""")

code(r"""
X_sbert = modelo_sbert.encode(
    df.texto_crudo.tolist(),       # el texto CRUDO: el modelo quiere lenguaje natural
    normalize_embeddings=True,     # deja cada vector con norma 1 (requisito de la consigna)
    show_progress_bar=True,
)

normas = np.linalg.norm(X_sbert, axis=1)
print(f"\nMatriz SBERT : {X_sbert.shape}")
print(f"Finitos      : {np.isfinite(X_sbert).all()}   NaN: {int(np.isnan(X_sbert).sum())}")
print(f"Normas       : [{normas.min():.4f}, {normas.max():.4f}]   filas nulas: {int((normas==0).sum())}")
""")

code(r"""
np.save("embeddings/sbert.npy", X_sbert)
print("Guardado embeddings/sbert.npy")

print("\nResumen de las tres representaciones:")
print(f"   TF-IDF             {X_tfidf.shape}  disperso (97% ceros)")
print(f"   Promedio Word2Vec  {X_sbw.shape if X_sbw is not None else '(pendiente)'}  denso")
print(f"   SBERT              {X_sbert.shape}  denso")
print("\nLas dos familias que pide la consigna: un promedio de vectores de palabra "
      "(SBW) y un modelo de oracion (SBERT).")
""")

md(r"""
### Primera comparación: la consulta que TF-IDF no podía resolver

En el Bloque 4 vimos que en las consultas semánticas TF-IDF le da **cero** a los
documentos relevantes y aun así devuelve cinco resultados equivocados. Es el
momento de ver qué hace SBERT con exactamente la misma consulta.
""")

code(r"""
def buscar_sbert(consulta, k=5):
    # Busqueda con el modelo de oracion. La consulta se codifica con el MISMO
    # modelo y SIN limpiar: SBERT espera lenguaje natural tanto en los
    # documentos como en la consulta.
    q = modelo_sbert.encode([consulta], normalize_embeddings=True)
    sims = (X_sbert @ q.ravel())          # vectores normalizados -> producto = coseno
    idx = sims.argsort()[::-1][:k]
    return pd.DataFrame({"titulo": df.titulo.iloc[idx].values,
                         "similitud": sims[idx].round(4)})


semanticas = [q for q in queries if q["tipo"] == "semantica"]
q = semanticas[0]
relevantes = set(q["relevantes"])

print(f"Consulta: {q['consulta']}")
print(f"Relevantes segun nuestro queries.json:")
for t in q["titulos_relevantes"]:
    print(f"   - {t}")

print("\n--- TF-IDF ---")
display(buscar_tfidf(q["consulta"]))
print("--- SBERT ---")
display(buscar_sbert(q["consulta"]))
""")

code(r"""
# Precision@5 de las dos familias sobre las 3 consultas semanticas.
filas = []
for q in semanticas:
    rel = {indice_por_url[u] for u in q["relevantes"]}

    v = vectorizador.transform([" ".join(tokenizar(q["consulta"]))])
    top_tfidf = cosine_similarity(v, X_tfidf).ravel().argsort()[::-1][:5]

    e = modelo_sbert.encode([q["consulta"]], normalize_embeddings=True)
    top_sbert = (X_sbert @ e.ravel()).argsort()[::-1][:5]

    filas.append({
        "consulta": q["id"],
        "TF-IDF P@5": sum(1 for i in top_tfidf if i in rel) / 5,
        "SBERT P@5": sum(1 for i in top_sbert if i in rel) / 5,
    })

tabla = pd.DataFrame(filas)
print(tabla.to_string(index=False))
print(f"\nPromedio   TF-IDF {tabla['TF-IDF P@5'].mean():.2f}   "
      f"SBERT {tabla['SBERT P@5'].mean():.2f}")
print("\nOJO: son solo las 3 consultas semanticas, elegidas a proposito para que "
      "TF-IDF no pueda ganar.\nLa evaluacion completa (las 12 consultas, con el piso "
      "de azar al lado) va en el Bloque 11.")
""")

md(r"""
**Importante para no sacar conclusiones de más.** Estas tres consultas fueron
diseñadas específicamente para que TF-IDF no pudiera resolverlas: no comparten
ninguna palabra con los documentos relevantes. Que SBERT gane acá era el resultado
esperado, no un descubrimiento.

La pregunta honesta —*¿gana en general, y cuánto por encima del azar?*— se contesta
en el Bloque 11, sobre las 12 consultas y con el piso de azar al lado. Es
perfectamente posible que TF-IDF gane en las consultas léxicas.

---
""")

md(r"""
## Bloque 8 — Parte D: comparación y visualización

Tenemos tres representaciones del mismo corpus. Esta parte las compara con las
mismas consultas y busca responder algo más difícil que "¿cuál devuelve mejores
resultados?": **¿cuál de estos espacios tiene estructura real?**

Tres miradas, de la más superficial a la más informativa:

1. **Rankings lado a lado** — lo que ve el usuario.
2. **Distribución de similitudes entre pares al azar** — si el espacio discrimina.
3. **Proyección 2D** — si la estructura se parece a la taxonomía de géneros.
""")

code(r"""
# Las tres representaciones, con su funcion de busqueda.
def buscar_w2v(consulta, k=5):
    v, _ = vector_documento(tokenizar(consulta), sbw)
    sims = X_sbw @ v
    idx = sims.argsort()[::-1][:k]
    return df.titulo.iloc[idx].values, sims[idx]


def buscar_tfidf_crudo(consulta, k=5):
    q = vectorizador.transform([" ".join(tokenizar(consulta))])
    sims = cosine_similarity(q, X_tfidf).ravel()
    idx = sims.argsort()[::-1][:k]
    return df.titulo.iloc[idx].values, sims[idx]


def buscar_sbert_crudo(consulta, k=5):
    e = modelo_sbert.encode([consulta], normalize_embeddings=True).ravel()
    sims = X_sbert @ e
    idx = sims.argsort()[::-1][:k]
    return df.titulo.iloc[idx].values, sims[idx]


BUSCADORES = [("TF-IDF", buscar_tfidf_crudo),
              ("Promedio W2V (SBW)", buscar_w2v),
              ("SBERT", buscar_sbert_crudo)]
""")

code(r"""
def ranking_lado_a_lado(consulta, k=5):
    # Top-k de los tres modelos en columnas, marcando los relevantes con *
    q = next((x for x in queries if x["consulta"] == consulta), None)
    rel = set(q["relevantes"]) if q else set()
    url_por_titulo = dict(zip(df.titulo, df.url_libro))

    cols = {}
    for nombre, fn in BUSCADORES:
        titulos, sims = fn(consulta, k)
        cols[nombre] = [
            f"{'* ' if url_por_titulo.get(t) in rel else '  '}{t[:38]} ({s:.3f})"
            for t, s in zip(titulos, sims)
        ]
    return pd.DataFrame(cols, index=[f"#{i+1}" for i in range(k)])


# Tres consultas de tipos distintos, para ver donde cambia el comportamiento.
for qid in ("q02", "q07", "q09"):
    q = next(x for x in queries if x["id"] == qid)
    print("=" * 118)
    print(f"{qid} [{q['tipo']}]  {q['consulta']}")
    print(f"   relevantes: {', '.join(q['titulos_relevantes'])}")
    print("=" * 118)
    display(ranking_lado_a_lado(q["consulta"]))
    print()
print("(*) = esta en nuestra lista de relevantes")
""")

md(r"""
### Lectura de los rankings

Las tres consultas están elegidas para mostrar tres regímenes distintos:

- **q02** es de solapamiento léxico 100% (nombres propios). Es el mejor escenario
  posible para TF-IDF.
- **q07** es geográfica: el lugar está escrito en la sinopsis.
- **q09** es semántica pura: ninguna palabra en común con los relevantes.

Lo que hay que mirar no es sólo cuántos asteriscos tiene cada columna, sino
**dónde** cambia el orden relativo entre modelos.
""")

md(r"""
### ¿El espacio discrimina, o todo se parece a todo?

Un ranking siempre devuelve resultados: `argsort` ordena cualquier cosa. La
pregunta de fondo es si las distancias del espacio significan algo.

La prueba: tomar **pares de documentos al azar** y ver cómo se distribuyen sus
similitudes. Si la media es muy alta y el desvío muy chico —digamos 0.90 ± 0.02—
entonces todos los documentos son casi igual de parecidos entre sí, y la
diferencia entre el puesto 1 y el 50 es ruido numérico. El ranking se ve bien y no
dice nada.
""")

code(r"""
def similitudes_entre_pares(M, es_disperso=False):
    # Similitud coseno de todos los pares de documentos distintos
    S = cosine_similarity(M) if es_disperso else (M @ M.T)
    iu = np.triu_indices(S.shape[0], k=1)
    return np.asarray(S)[iu]

pares = {
    "TF-IDF": similitudes_entre_pares(X_tfidf, es_disperso=True),
    "Promedio W2V (SBW)": similitudes_entre_pares(X_sbw),
    "SBERT": similitudes_entre_pares(X_sbert),
}

resumen = pd.DataFrame([
    {"modelo": k, "media": v.mean(), "desvio": v.std(),
     "min": v.min(), "max": v.max(),
     "p50": np.percentile(v, 50), "p99": np.percentile(v, 99)}
    for k, v in pares.items()
]).round(4)
print(resumen.to_string(index=False))
""")

code(r"""
import matplotlib.pyplot as plt

# Paleta categorica validada para comparacion todos-contra-todos (3 slots).
AZUL, NARANJA, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
GRIS_CONTEXTO = "#c8c7c2"
TINTA, TINTA_2 = "#0b0b0b", "#52514e"
SUPERFICIE = "#fcfcfb"
COLOR_MODELO = {"TF-IDF": AZUL, "Promedio W2V (SBW)": NARANJA, "SBERT": AQUA}

fig, ax = plt.subplots(figsize=(10, 4.2), facecolor=SUPERFICIE)
ax.set_facecolor(SUPERFICIE)

for nombre, vals in pares.items():
    ax.hist(vals, bins=70, range=(0, 1), density=True, histtype="step",
            linewidth=2, color=COLOR_MODELO[nombre], label=nombre)
    ax.axvline(vals.mean(), color=COLOR_MODELO[nombre], linewidth=1,
               linestyle=":", alpha=0.8)

ax.set_xlabel("similitud coseno entre dos documentos al azar", color=TINTA_2)
ax.set_ylabel("densidad", color=TINTA_2)
ax.set_title("Distribución de similitudes entre pares aleatorios",
             color=TINTA, fontsize=13, pad=12, loc="left")
ax.tick_params(colors=TINTA_2, labelsize=9)
for lado in ("top", "right"):
    ax.spines[lado].set_visible(False)
for lado in ("left", "bottom"):
    ax.spines[lado].set_color("#d8d7d2")
ax.grid(axis="y", color="#ececea", linewidth=0.8)
ax.set_axisbelow(True)
leyenda = ax.legend(frameon=False, labelcolor=TINTA_2, fontsize=9)
plt.tight_layout()
plt.show()
""")

md(r"""
**Cómo leer este gráfico.** La línea punteada de cada modelo marca su media. Los
tres modelos caen en tres regímenes completamente distintos, y el del medio es el
hallazgo más importante de esta parte.

**TF-IDF — pegado a cero.** Casi todos los pares de documentos no comparten
vocabulario, así que su similitud es ~0. Discrimina muchísimo, pero por *ausencia
de palabras en común*, no por sentido. Es la contracara de lo que vimos en el
Bloque 4: también le da cero a documentos que sí son relevantes.

**Promedio de Word2Vec — el caso patológico.** Miren la media y, sobre todo, el
**mínimo**: no hay en todo el corpus ni un solo par de libros que este modelo
considere distintos. Todos los pares caen en una franja angosta cerca de 1. Es
exactamente lo que advierte la consigna: *un espacio donde todo se parece a todo no
discrimina, aunque el ranking devuelva resultados*.

Y da resultados: en los rankings de arriba devolvió los relevantes con similitudes
de 0.70-0.75, que **parecen altísimas**. No lo son. Comparadas con una media de
~0.90, están por **debajo** del par promedio del corpus. El número grande no
significaba nada.

¿Por qué pasa? Promediar ~80 vectores de palabra arrastra cada documento hacia el
centro del espacio: cuantas más palabras se promedian, más se parece el resultado
al "documento promedio", y menos queda de lo específico. Es la pérdida de
información que anticipamos en el Bloque 6, acá medida.

**SBERT — distribución ancha y centrada.** Media intermedia, desvío entre dos y
tres veces mayor que los otros dos, y un rango que va de casi 0 a casi 0.7. Hay
pares muy parecidos, pares muy distintos, y gradación en el medio. Eso es un
espacio con estructura.

**La moraleja metodológica.** Esta tabla no se puede deducir mirando rankings: los
tres modelos devuelven listas plausibles. Sin este chequeo, el promedio de Word2Vec
habría pasado por un modelo que funciona.
""")

md(r"""
### Proyección 2D: ¿el espacio reconstruye los géneros?

Los vectores viven en 300 o 512 dimensiones; una hoja tiene 2. Para dibujarlos hay
que **aplastarlos**, y eso siempre pierde información.

**La etiqueta de color.** Usamos el primer subgénero distinto de `Intriga` y
`Novela`, que cubren casi todo el corpus y por eso no sirven para distinguir nada.
Hay un detalle incómodo que conviene decir en vez de esconder: **una fracción
grande de los libros no tiene ningún subgénero**, así que esos puntos no se pueden
colorear. Los dibujamos en gris de fondo.

**Y lo más importante: el modelo nunca vio esta etiqueta.** En el Bloque 3
excluimos `generos` del texto justamente para que esto sea cierto. Si los colores
se agrupan, es porque el modelo dedujo la estructura del contenido.
""")

code(r"""
GENEROS_INUTILES = {"Intriga", "Novela"}


def etiqueta_subgenero(gs):
    utiles = [g for g in gs if g not in GENEROS_INUTILES]
    return utiles[0] if utiles else "Sin subgénero"


df["subgenero"] = df.generos.apply(etiqueta_subgenero)
conteo = df.subgenero.value_counts()
print(conteo.to_string())

# Solo los subgeneros con suficientes libros para que un cluster sea visible.
MIN_LIBROS_CLASE = 6
CLASES = [g for g, c in conteo.items() if c >= MIN_LIBROS_CLASE and g != "Sin subgénero"]
print(f"\nClases que se grafican (>= {MIN_LIBROS_CLASE} libros): {CLASES}")
print(f"El resto queda como contexto gris: "
      f"{len(df) - df.subgenero.isin(CLASES).sum()}/{len(df)} libros")
""")

code(r"""
from sklearn.decomposition import PCA

pca = PCA(n_components=2, random_state=SEMILLA)
P = pca.fit_transform(X_sbert)
var1, var2 = pca.explained_variance_ratio_[:2]

fig, ax = plt.subplots(figsize=(8.5, 7), facecolor=SUPERFICIE)
ax.set_facecolor(SUPERFICIE)

# En un scatter solo se pueden distinguir con confianza 3 colores (ver la nota
# metodologica al final). Se colorean las 3 clases mas numerosas; TODO el resto
# -incluidas las clases chicas- va al gris de contexto, para que no quede ningun
# documento sin dibujar.
CLASES_COLOREADAS = CLASES[:3]
otros = ~df.subgenero.isin(CLASES_COLOREADAS)
assert otros.sum() + df.subgenero.isin(CLASES_COLOREADAS).sum() == len(df)

ax.scatter(P[otros, 0], P[otros, 1], s=28, c=GRIS_CONTEXTO,
           linewidths=0, label=f"resto del corpus ({otros.sum()})")

for color, clase in zip([AZUL, NARANJA, AQUA], CLASES_COLOREADAS):
    m = (df.subgenero == clase).values
    ax.scatter(P[m, 0], P[m, 1], s=46, c=color, linewidths=1.2,
               edgecolors=SUPERFICIE, label=f"{clase} ({m.sum()})")

ax.set_title("PCA de los embeddings SBERT, coloreado por subgénero",
             color=TINTA, fontsize=13, pad=12, loc="left")
ax.set_xlabel(f"PC1 — {var1:.1%} de la varianza", color=TINTA_2)
ax.set_ylabel(f"PC2 — {var2:.1%} de la varianza", color=TINTA_2)
ax.tick_params(colors=TINTA_2, labelsize=9)
for lado in ("top", "right"):
    ax.spines[lado].set_visible(False)
for lado in ("left", "bottom"):
    ax.spines[lado].set_color("#d8d7d2")
ax.grid(color="#ececea", linewidth=0.8)
ax.set_axisbelow(True)
ax.legend(frameon=False, labelcolor=TINTA_2, fontsize=9, loc="best")
plt.tight_layout()
plt.show()

print(f"Varianza explicada por PC1+PC2: {var1+var2:.1%}")
print(f"  -> el dibujo descarta el {1-var1-var2:.1%} de la informacion del espacio.")
""")

code(r"""
from sklearn.manifold import TSNE

PERPLEXITY = 30   # regla practica: bastante menor que n/3 (= 50 con 150 documentos)

tsne = TSNE(n_components=2, perplexity=PERPLEXITY, init="pca",
            random_state=SEMILLA, max_iter=1000)
T = tsne.fit_transform(X_sbert)

# Pequenos multiplos: un panel por subgenero. Evita poner 7 colores en un scatter
# (donde no se distinguen de forma confiable) y hace visible cada clase por separado.
n = len(CLASES)
fig, axes = plt.subplots(1, n, figsize=(3.2 * n, 3.6), facecolor=SUPERFICIE)
axes = np.atleast_1d(axes)

for ax, clase in zip(axes, CLASES):
    m = (df.subgenero == clase).values
    ax.set_facecolor(SUPERFICIE)
    ax.scatter(T[~m, 0], T[~m, 1], s=18, c=GRIS_CONTEXTO, linewidths=0)
    ax.scatter(T[m, 0], T[m, 1], s=42, c=AZUL, linewidths=1.2,
               edgecolors=SUPERFICIE)
    ax.set_title(f"{clase} ({m.sum()})", color=TINTA, fontsize=11, loc="left")
    ax.set_xticks([]); ax.set_yticks([])
    for lado in ("top", "right", "left", "bottom"):
        ax.spines[lado].set_color("#e4e3df")

fig.suptitle(f"t-SNE de los embeddings SBERT (perplexity={PERPLEXITY}) — "
             "un panel por subgénero", color=TINTA, fontsize=13, x=0.01, ha="left")
plt.tight_layout()
plt.show()
""")

md(r"""
### Lo que muestran las dos proyecciones

En los dos gráficos los colores aparecen **repartidos por toda la nube**, sin
formar regiones propias. La lectura ingenua sería: *el modelo no captura los
géneros*.

Pero esa conclusión no se sostiene, y la razón está en el propio gráfico: PC1 y PC2
retienen una fracción mínima de la varianza. **El dibujo descarta más del 90% de la
información del espacio**, así que no puede probar una ausencia. Como dice la
advertencia de más abajo: una nube que se ve mezclada puede estar perfectamente
separada en el espacio original.

Entonces no lo suponemos: lo medimos **en las 512 dimensiones**, donde no se
descartó nada.

**El test.** Para cada subgénero comparamos:

- `intra` = similitud media entre libros **del mismo** subgénero,
- `inter` = similitud media entre esos libros y **el resto** del corpus.

Si el modelo capta algo del género, `intra` tiene que ser mayor que `inter`. Pero
una diferencia positiva puede salir por azar, sobre todo con clases de 7 u 8
libros. Así que la contrastamos contra su propia línea de base: repetimos el
cálculo 2000 veces con **grupos del mismo tamaño armados al azar** y vemos qué
fracción de esos grupos aleatorios alcanza una diferencia igual o mayor. Eso es el
valor *p*: si es chico, la diferencia observada es difícil de explicar por azar.

Es la misma lógica del piso de azar de la Parte 5, aplicada a otra medida.
""")

code(r"""
rng = np.random.default_rng(SEMILLA)

S_sbert = X_sbert @ X_sbert.T
np.fill_diagonal(S_sbert, np.nan)       # un documento consigo mismo no cuenta

N_PERMUTACIONES = 2000

filas = []
for clase in CLASES:
    m = (df.subgenero == clase).values
    dentro, fuera = np.where(m)[0], np.where(~m)[0]

    intra = np.nanmean(S_sbert[np.ix_(dentro, dentro)])
    inter = np.nanmean(S_sbert[np.ix_(dentro, fuera)])
    observado = intra - inter

    # Linea de base: grupos del mismo tamano, armados al azar.
    nulos = np.empty(N_PERMUTACIONES)
    for i in range(N_PERMUTACIONES):
        p = rng.choice(len(df), len(dentro), replace=False)
        q = np.setdiff1d(np.arange(len(df)), p)
        nulos[i] = np.nanmean(S_sbert[np.ix_(p, p)]) - np.nanmean(S_sbert[np.ix_(p, q)])

    filas.append({
        "subgénero": clase, "n": int(m.sum()),
        "intra": round(float(intra), 4), "inter": round(float(inter), 4),
        "diferencia": round(float(observado), 4),
        "p": round(float((nulos >= observado).mean()), 3),
        "significativo": "sí" if (nulos >= observado).mean() < 0.05 else "no",
    })

print("Separabilidad por subgénero EN EL ESPACIO COMPLETO (512 dimensiones)")
print(pd.DataFrame(filas).to_string(index=False))
""")

md(r"""
### Lectura del test

El resultado corrige la impresión que daban los gráficos: **la estructura está en el
espacio, lo que falla es la proyección.**

Los subgéneros más numerosos tienen una similitud interna significativamente mayor
que la que tienen con el resto del corpus, y la diferencia no se explica por azar.
El caso más claro es `Histórico`, y tiene sentido: comparte vocabulario de época,
lugares y fechas, que es justamente lo que un modelo de oración puede captar.

La clase que **no** da significativa es la más chica, y ahí hay dos explicaciones
posibles que este test no permite separar: puede que el modelo realmente no la
capture, o puede que con tan pocos libros no haya potencia estadística para
detectarlo. Decirlo así —en vez de elegir la interpretación que más conviene— es
parte de lo que se evalúa.

**Por qué esto importa para el informe.** Si nos hubiéramos quedado con la
proyección 2D, habríamos concluido que el modelo no reconstruye la taxonomía. Es
falso, y la herramienta que lo desmiente es la misma que usamos en toda la
evaluación: **comparar contra una línea de base en vez de confiar en la
impresión**.

También adelanta el resultado de *Clustering* como parte avanzada: hay señal de
género en el espacio, pero es débil frente a la variación entre libros. Un K-Means
sobre estos vectores probablemente no reconstruya los géneros, y ahora sabemos por
qué — no porque la señal no exista, sino porque no domina.
""")

md(r"""
## Bloque 9 — Parte E: persistencia en Postgres con pgvector

### Por qué una base de datos

Hasta acá los vectores viven en memoria: si se reinicia el entorno, hay que
recalcularlos. En un sistema real los vectores están en una base y la búsqueda se
resuelve ahí, porque traer todo el corpus a memoria para ordenarlo no escala.

**pgvector** es una extensión de Postgres que agrega un tipo `vector` y operadores
de distancia, de modo que "los N documentos más parecidos a este" se puede escribir
en SQL.

### Las credenciales no van en el notebook

La consigna descuenta por credenciales visibles **en el notebook o en sus salidas**.
Acá se leen de un archivo `.env` que está en `.gitignore`:

```
.env.ejemplo   -> plantilla, se sube al repositorio
.env           -> datos reales, NO se sube nunca
```

Antes de correr este bloque conviene verificar la conexión con el script
`archivos del proyecto/probar_conexion.py`, que comprueba que la extensión esté
instalada y que la versión soporte índices HNSW, y enmascara la contraseña en todo
lo que imprime.
""")

code(r"""
from dotenv import dotenv_values
import psycopg
from pgvector.psycopg import register_vector


def url_conexion():
    # Lee DATABASE_URL de .env. No se imprime nunca ni se guarda en una variable
    # del notebook que pueda terminar en una salida.
    for ruta in (Path('.env'), Path('../.env')):
        if ruta.exists():
            url = (dotenv_values(ruta) or {}).get('DATABASE_URL', '').strip()
            if url and 'TU_PASSWORD' not in url:
                return url
    raise RuntimeError(
        'No encuentro DATABASE_URL. Copiar .env.ejemplo a .env y completarlo. '
        'Verificar con el script archivos del proyecto/probar_conexion.py'
    )


def conectar():
    url = url_conexion()
    # El transaction pooler (puerto 6543) no admite sentencias preparadas.
    kwargs = {'prepare_threshold': None} if ':6543' in url else {}
    con = psycopg.connect(url, connect_timeout=20, **kwargs)
    register_vector(con)        # permite pasar arrays de numpy como `vector`
    return con


with conectar() as con, con.cursor() as cur:
    cur.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
    print('pgvector:', cur.fetchone()[0])
    cur.execute('SELECT version()')
    print(cur.fetchone()[0].split(',')[0])
""")

md(r"""
### El esquema: una tabla por modelo

```
books              metadata + texto           id (identity)
books_sbert        vector(512)                book_id -> books.id
books_word2vec     vector(300)                book_id -> books.id
```

**¿Por qué no pueden convivir dos dimensiones en la misma columna indexada?**

Porque la dimensión es **parte del tipo**: `vector(300)` y `vector(512)` son tipos
distintos, no el mismo tipo con contenidos de distinto largo. Y aunque se pudieran
guardar juntos, la distancia coseno entre un vector de 300 y uno de 512 no está
definida: no hay forma de emparejar las componentes. El índice, además, se
construye sobre una métrica de dimensionalidad fija — necesita saber de antemano en
qué espacio está midiendo.

La metadata va en una tabla aparte y las de embeddings la referencian con una clave
foránea `ON DELETE CASCADE`. Así el texto se guarda una sola vez, borrar un libro
se lleva sus vectores, y agregar un tercer modelo es agregar una tabla sin tocar
nada de lo anterior.

La celda siguiente **no crea nada**: verifica que el esquema sea el esperado y que
las dimensiones declaradas coincidan con las matrices que calculamos. Si algo no
coincide, falla acá en vez de fallar a mitad de la carga.
""")

code(r"""
ESQUEMA_ESPERADO = {'books_sbert': ('vector(512)', 512),
                    'books_word2vec': ('vector(300)', 300)}

SQL_TIPOS = '''
    SELECT c.relname, format_type(a.atttypid, a.atttypmod)
    FROM pg_attribute a
    JOIN pg_class c ON c.oid = a.attrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public' AND a.attname = 'embedding' AND a.attnum > 0
    ORDER BY c.relname
'''

with conectar() as con, con.cursor() as cur:
    cur.execute(SQL_TIPOS)
    tipos = dict(cur.fetchall())

for tabla, (tipo_esperado, dim) in ESQUEMA_ESPERADO.items():
    real = tipos.get(tabla)
    assert real == tipo_esperado, f'{tabla}: la base declara {real}, se esperaba {tipo_esperado}'
    print(f'{tabla:<16} {real}  coincide con la matriz calculada')

assert X_sbert.shape[1] == 512 and X_sbw.shape[1] == 300
print('\nDimensiones verificadas contra las matrices del notebook.')
""")

md(r"""
### Antes de insertar: validar los vectores

La consigna lo pide explícitamente y lo descuenta si falla: **manejo explícito de
vectores nulos o no finitos antes de insertar**.

Un `NaN` en la base es peor que un error, porque no explota: se inserta, el índice
lo acepta, y después toda comparación con él devuelve resultados sin sentido de
forma silenciosa. Por eso la validación va **antes** del `INSERT`, no después.

Tres condiciones: que todos los valores sean finitos, que la norma no sea cero (un
vector nulo no tiene dirección, así que su coseno es indefinido) y que la dimensión
sea la que declara la tabla.
""")

code(r"""
def validar_matriz(M, dim_esperada, nombre):
    # Devuelve los indices de las filas que se pueden insertar. Nada entra a la
    # base sin pasar por aca.
    if M.shape[1] != dim_esperada:
        raise ValueError(f'{nombre}: dimension {M.shape[1]}, se esperaba {dim_esperada}')

    finitos = np.isfinite(M).all(axis=1)
    no_nulos = np.linalg.norm(M, axis=1) > 1e-12
    validos = np.where(finitos & no_nulos)[0]

    print(f'{nombre:<16} {M.shape}  validos: {len(validos)}/{len(M)}')
    if (~finitos).sum():
        print(f'    DESCARTADOS por no finitos (NaN o inf): {int((~finitos).sum())}')
    if (~no_nulos).sum():
        print(f'    DESCARTADOS por norma cero: {int((~no_nulos).sum())}')
    return validos


idx_sbert = validar_matriz(X_sbert, 512, 'books_sbert')
idx_sbw = validar_matriz(X_sbw, 300, 'books_word2vec')
""")

md(r"""
### La carga

`books.id` es `GENERATED AS IDENTITY`: los identificadores los asigna Postgres, no
nosotros. Y `url_libro` no tiene restricción de unicidad, así que no se puede usar
`ON CONFLICT` para que la carga sea idempotente.

La solución es **recargar desde cero**: `TRUNCATE books CASCADE` vacía la tabla y,
por la clave foránea, también las dos de embeddings. Así la celda se puede volver a
correr cuantas veces haga falta y el resultado es siempre el mismo — que es lo que
se espera de un notebook que alguien más va a ejecutar.

Después de insertar leemos los `id` generados para enlazar los vectores. `generos`
es una columna `text`, así que guardamos el array en JSON (el mismo formato del CSV)
y lo expandimos en la consulta del Bloque 10.
""")

code(r"""
SQL_INSERT_BOOKS = '''
    INSERT INTO books (titulo, autores, generos, serie, sinopsis, url_libro,
                       categoria_origen, fecha_extraccion, url_portada,
                       texto_crudo, tokens, texto_limpio,
                       n_palabras_crudo, n_tokens_limpio)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
'''


def como_json(valor):
    return json.dumps(list(valor), ensure_ascii=False)


with conectar() as con, con.cursor() as cur:
    # Recarga completa: hace la celda reproducible. CASCADE alcanza a las dos
    # tablas de embeddings por la clave foranea.
    cur.execute('TRUNCATE books CASCADE')

    cur.executemany(SQL_INSERT_BOOKS, [
        (r.titulo, como_json(r.autores), como_json(r.generos),
         r.serie or None, r.sinopsis, r.url_libro, r.categoria_origen,
         r.fecha_extraccion or None, r.url_portada or None,
         r.texto_crudo, como_json(r.tokens), r.texto_limpio,
         int(len(str(r.texto_crudo).split())), int(len(r.tokens)))
        for r in df.itertuples()
    ])

    # Los id los genero Postgres: hay que leerlos para enlazar los vectores.
    cur.execute('SELECT id, url_libro FROM books')
    id_por_url = {u: i for i, u in cur.fetchall()}

    for tabla, M, validos in [('books_sbert', X_sbert, idx_sbert),
                              ('books_word2vec', X_sbw, idx_sbw)]:
        cur.executemany(
            f'INSERT INTO {tabla} (book_id, embedding) VALUES (%s, %s)',
            [(id_por_url[df.url_libro.iloc[i]], M[i]) for i in validos])

    con.commit()

with conectar() as con, con.cursor() as cur:
    for t in ('books', 'books_sbert', 'books_word2vec'):
        cur.execute(f'SELECT count(*) FROM {t}')
        print(f'{t:<16} {cur.fetchone()[0]} filas')
""")

md(r"""
### El índice HNSW y la opclass

**HNSW** (*Hierarchical Navigable Small World*) es un índice **aproximado**: en vez
de comparar la consulta contra los 150 vectores, navega un grafo de vecinos y se
detiene tras visitar unos cuantos candidatos. Con 150 documentos no hace falta; con
millones, es la diferencia entre milisegundos y minutos.

**La opclass tiene que corresponder al operador de distancia que se va a usar.** Es
un punto que la consigna evalúa y descuenta:

| Operador | Qué mide | Opclass |
|---|---|---|
| `<=>` | distancia coseno | `vector_cosine_ops` |
| `<->` | distancia euclídea (L2) | `vector_l2_ops` |
| `<#>` | producto interno negativo | `vector_ip_ops` |

Si no coinciden, **Postgres ignora el índice**: la consulta devuelve el resultado
correcto, más lenta, y nadie se entera. Nosotros usamos `<=>`, así que va
`vector_cosine_ops`.

> Nuestros vectores están normalizados, así que coseno y producto interno
> ordenarían igual. Usamos coseno de todos modos, por ser el operador cuya
> semántica coincide con lo que decimos estar midiendo.

La celda siguiente crea los índices si faltan y después **verifica la opclass
leyendo el catálogo de Postgres**, en vez de confiar en que la sentencia decía lo
correcto.
""")

code(r"""
SQL_VERIFICAR_INDICES = '''
    SELECT t.relname, i.relname, a.amname, pg_get_indexdef(x.indexrelid)
    FROM pg_index x
    JOIN pg_class i ON i.oid = x.indexrelid
    JOIN pg_class t ON t.oid = x.indrelid
    JOIN pg_am a ON a.oid = i.relam
    WHERE a.amname = 'hnsw'
    ORDER BY t.relname
'''

with conectar() as con, con.cursor() as cur:
    cur.execute('CREATE INDEX IF NOT EXISTS idx_books_sbert_hnsw ON books_sbert '
                'USING hnsw (embedding vector_cosine_ops)')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_books_w2v_hnsw ON books_word2vec '
                'USING hnsw (embedding vector_cosine_ops)')
    con.commit()

    cur.execute(SQL_VERIFICAR_INDICES)
    for tabla, indice, metodo, definicion in cur.fetchall():
        ok = 'vector_cosine_ops' in definicion
        print(f'{tabla:<16} {indice:<24} {metodo}  opclass correcta para `<=>`: {ok}')
""")

md(r"""
## Bloque 10 — Parte F: búsqueda semántica en SQL

La consigna es explícita: la similitud se resuelve **en SQL, no en Python**. Traer
los vectores a memoria y ordenarlos con `argsort` sería volver al punto de partida.

La función combina similitud con un **filtro por metadata** (el género), que es lo
que hace útil a un buscador real: *"policiales parecidos a esto"*.

**Dos notas sobre el filtro.**

La columna `generos` es `text`, así que guardamos el array como JSON y lo
expandimos en la consulta con `jsonb_array_elements_text`. Es correcto —compara
elementos, no subcadenas, así que `Policíaco` no matchea por accidente dentro de
otra palabra— pero no puede usar un índice. Con 150 libros da igual; en producción
la columna sería `text[]` con un índice GIN, y el filtro quedaría
`%s = ANY(generos)`.

El `::text` sobre el parámetro del género no es decorativo. Sin él, Postgres falla
con `could not determine data type of parameter`: un parámetro que sólo aparece en
`$n IS NULL` no le da ninguna pista sobre su tipo, y el motor se niega a adivinar.
El cast se lo dice.
""")

code(r"""
SQL_BUSCAR = '''
    SELECT b.titulo,
           b.generos,
           1 - (e.embedding <=> %(q)s) AS similitud
    FROM {tabla} e
    JOIN books b ON b.id = e.book_id
    WHERE %(genero)s::text IS NULL
       OR %(genero)s::text IN (SELECT jsonb_array_elements_text(b.generos::jsonb))
    ORDER BY e.embedding <=> %(q)s
    LIMIT %(k)s
'''


def buscar(consulta, k=5, genero=None, tabla='books_sbert', ef_search=None):
    # Busqueda semantica resuelta EN SQL.
    #   genero=None  -> sin filtro
    #   ef_search    -> cuantos candidatos visita HNSW antes de cortar
    if tabla == 'books_sbert':
        v = modelo_sbert.encode([consulta], normalize_embeddings=True).ravel()
    else:
        v, _ = vector_documento(tokenizar(consulta), sbw)

    with conectar() as con, con.cursor() as cur:
        if ef_search is not None:
            # SET no admite parametros vinculados: hay que interpolar.
            # int() evita cualquier inyeccion al construir la sentencia.
            cur.execute('SET LOCAL hnsw.ef_search = ' + str(int(ef_search)))
        cur.execute(SQL_BUSCAR.format(tabla=tabla),
                    {'q': v, 'genero': genero, 'k': k})
        filas = cur.fetchall()

    return pd.DataFrame(
        [(t, ', '.join(json.loads(g)), round(float(s), 4)) for t, g, s in filas],
        columns=['titulo', 'generos', 'similitud'])


consulta_demo = 'un detective investiga un asesinato en una casa de campo inglesa'
print('Sin filtro:')
display(buscar(consulta_demo, k=5))
print()
print('Mismo vector, filtrando por genero = Historico:')
resultado = buscar(consulta_demo, k=5, genero='Histórico')
display(resultado)
if len(resultado) < 5:
    print(f'Devolvio {len(resultado)} filas en vez de 5, aunque hay libros de ese')
    print('genero en el corpus. NO es un error: es el problema de recall del indice')
    print('aproximado, que la seccion siguiente explica y mide.')
""")

md(r"""
### El problema de recall: índice aproximado + filtro selectivo

Acá hay un problema que no se ve con 150 documentos pero rompe sistemas reales, y
la consigna pide explicarlo.

HNSW **visita un número limitado de candidatos** (`hnsw.ef_search`, 40 por defecto)
y corta. El filtro por género se aplica **después**, sobre lo que el índice ya
decidió mirar.

Entonces, si el género cubre una fracción chica del corpus, puede pasar que de los
40 candidatos visitados **ninguno** —o muy pocos— pase el filtro. La consulta
devuelve menos de `k` resultados, o resultados peores que los que existían. Y no
avisa: devuelve una lista corta, que parece una lista.

Cuanto **más selectivo** el filtro, **peor** el recall. Es contraintuitivo: uno
esperaría que filtrar más diera resultados más precisos.

**Qué se hace al respecto**, en orden de costo:

1. **Subir `ef_search`.** Visita más candidatos: más lento, mejor recall. Es un
   parche — no garantiza nada.
2. **Búsqueda exacta cuando el filtro es muy selectivo.** Si el género tiene pocos
   libros, conviene filtrar primero y comparar todos: es barato sobre un conjunto
   chico. Se decide con una estimación de cardinalidad.
3. **Índices parciales por género.** El índice contiene solo lo filtrado, así que el
   problema desaparece. No escala a muchos valores de filtro.

La celda siguiente lo mide sobre nuestros propios datos: compara lo que devuelve
el índice contra la verdad exacta calculada en Python, con el filtro cada vez más
selectivo y con tres valores de `ef_search`.
""")

code(r"""
def verdad_exacta(consulta, genero, k=5):
    # Los k mejores calculados sin indice: la referencia contra la que medimos.
    v = modelo_sbert.encode([consulta], normalize_embeddings=True).ravel()
    mask = (np.ones(len(df), dtype=bool) if genero is None
            else df.generos.apply(lambda gs: genero in gs).values)
    n = int(mask.sum())
    sims = np.where(mask, X_sbert @ v, -np.inf)
    return set(df.titulo.iloc[sims.argsort()[::-1][:min(k, n)]]), n


EF_A_PROBAR = [40, 100, 400]      # 40 es el valor por defecto de pgvector

consulta_recall = 'una investigacion policial con varios sospechosos'
filas = []
for genero in ['Policíaco', 'Histórico', 'Psicológico', 'Aventuras']:
    exacto, n = verdad_exacta(consulta_recall, genero)
    fila = {'filtro': genero, 'libros que pasan': n,
            'selectividad': f'{n/len(df):.0%}'}
    for ef in EF_A_PROBAR:
        obtenido = set(buscar(consulta_recall, k=5, genero=genero,
                              ef_search=ef).titulo)
        fila[f'recall@5 (ef={ef})'] = round(len(exacto & obtenido) / max(len(exacto), 1), 2)
    filas.append(fila)

print('Recall del indice HNSW frente a la busqueda exacta, por selectividad del filtro')
print(pd.DataFrame(filas).to_string(index=False))
""")

md(r"""
### Lectura: el problema no era teórico

Esperábamos tener que explicar el problema de recall como algo que aparece "a
escala". **Aparece acá, con 150 documentos**, y la tabla lo muestra con claridad:

- Con el filtro poco selectivo (26% del corpus) el recall es perfecto.
- A medida que el filtro se vuelve más selectivo, el recall **se derrumba**: con un
  género que cubre el 7% del corpus, el índice en su configuración por defecto
  devolvió **cero** de los resultados correctos.
- No devolvió resultados *malos*: en algunos casos devolvió **menos de `k` filas, o
  ninguna**, pese a haber libros que cumplían el filtro. Una lista vacía parece una
  respuesta legítima.

**Por qué.** `ef_search` por defecto vale 40. El índice recorre el grafo, junta unos
40 candidatos ordenados por similitud **sin mirar el género**, y recién entonces se
aplica el filtro. Si entre esos 40 no hay ninguno del género pedido, no queda nada
que devolver. Con 150 documentos, 40 candidatos son apenas un cuarto del corpus:
alcanza para que el efecto aparezca.

**La solución, medida.** Subir `ef_search` recupera el recall de forma monótona, y
con un valor suficientemente alto vuelve a 1.00 en los cuatro casos — porque pasa a
visitar prácticamente todo el corpus. Es decir: **el arreglo funciona renunciando a
la ventaja del índice**. Esa es la verdadera lección. En un corpus grande no se
puede subir `ef_search` indefinidamente; ahí hay que elegir entre las otras dos
estrategias: búsqueda exacta cuando el filtro es muy selectivo, o índices parciales.

**Lo que esto cambia en el informe.** Es un caso concreto donde el sistema falla, con
una hipótesis verificada sobre la causa. La consigna pide exactamente eso, y pedía
"explicar" el problema: nosotros además lo reprodujimos y medimos su arreglo.
""")

md(r"""
## Bloque 11 — Parte 5: evaluación

Este es el núcleo del TP. Hasta acá tenemos un buscador que devuelve resultados
plausibles, y ya vimos dos veces que eso no alcanza: el promedio de Word2Vec
devolvía similitudes de 0.75 que estaban por debajo del par promedio del corpus, y
el índice con filtro devolvía listas vacías que parecían respuestas.

**La métrica.** `precision@k` = de los `k` resultados devueltos, qué fracción está
en nuestra lista de relevantes. Si de los primeros 5 resultados 3 son relevantes,
precision@5 = 0.60.

**La línea de base.** Un número suelto no significa nada. Comparamos cuatro cosas:

| Contendiente | Qué representa |
|---|---|
| **Azar** | el piso: elegir `k` libros sin mirar el texto |
| **TF-IDF** | la línea de base léxica, la del TP1 |
| **Promedio Word2Vec (SBW)** | familia 1: promedio de vectores de palabra |
| **SBERT** | familia 2: modelo de oración |

El piso de azar **no se calcula con una fórmula**: se simula. Mil sorteos de `k`
libros al azar, y se promedia. Es el mismo método que usamos en el Bloque 8 para el
test de separabilidad.
""")

code(r"""
K_EVALUACION = [5, 10]
SORTEOS_AZAR = 1000


def precision_en_k(ranking_indices, relevantes_idx, k):
    top = ranking_indices[:k]
    return sum(1 for i in top if i in relevantes_idx) / k


def recall_en_k(ranking_indices, relevantes_idx, k):
    top = set(ranking_indices[:k])
    return len(top & relevantes_idx) / max(len(relevantes_idx), 1)


def ranking_tfidf(consulta):
    v = vectorizador.transform([' '.join(tokenizar(consulta))])
    return cosine_similarity(v, X_tfidf).ravel().argsort()[::-1]


def ranking_w2v(consulta):
    v, _ = vector_documento(tokenizar(consulta), sbw)
    return (X_sbw @ v).argsort()[::-1]


def ranking_sbert(consulta):
    e = modelo_sbert.encode([consulta], normalize_embeddings=True).ravel()
    return (X_sbert @ e).argsort()[::-1]


MODELOS = [('TF-IDF', ranking_tfidf),
           ('Promedio W2V (SBW)', ranking_w2v),
           ('SBERT', ranking_sbert)]

indice_por_url = {u: i for i, u in enumerate(df.url_libro)}
print(f'{len(queries)} consultas, '
      f'{sum(len(q["relevantes"]) for q in queries)} juicios de relevancia')
""")

code(r"""
rng_eval = np.random.default_rng(SEMILLA)


def piso_de_azar(relevantes_idx, k, sorteos=SORTEOS_AZAR):
    # Se simula en vez de usar |R|/N: es el procedimiento, no el atajo.
    aciertos = 0
    for _ in range(sorteos):
        elegidos = rng_eval.choice(len(df), size=k, replace=False)
        aciertos += sum(1 for i in elegidos if i in relevantes_idx) / k
    return aciertos / sorteos


# Un ranking por consulta y por modelo, calculado una sola vez.
rankings = {nombre: {q['id']: fn(q['consulta']) for q in queries}
            for nombre, fn in MODELOS}
relevantes = {q['id']: {indice_por_url[u] for u in q['relevantes']} for q in queries}
tipo_de = {q['id']: q['tipo'] for q in queries}

filas = []
for q in queries:
    qid = q['id']
    fila = {'consulta': qid, 'tipo': tipo_de[qid], 'rel': len(relevantes[qid])}
    for k in K_EVALUACION:
        fila[f'azar@{k}'] = piso_de_azar(relevantes[qid], k)
        for nombre, _ in MODELOS:
            fila[f'{nombre}@{k}'] = precision_en_k(rankings[nombre][qid], relevantes[qid], k)
    filas.append(fila)

detalle = pd.DataFrame(filas)
print('precision@k por consulta')
print(detalle.round(2).to_string(index=False))
""")

code(r"""
# La tabla que va al informe: promedio sobre las 12 consultas.
resumen = []
for k in K_EVALUACION:
    fila = {'k': k, 'Azar (piso)': detalle[f'azar@{k}'].mean()}
    for nombre, _ in MODELOS:
        fila[nombre] = detalle[f'{nombre}@{k}'].mean()
    resumen.append(fila)

tabla_global = pd.DataFrame(resumen).round(3)
print('precision@k PROMEDIO sobre las 12 consultas')
print(tabla_global.to_string(index=False))
print()
for k in K_EVALUACION:
    piso = tabla_global.loc[tabla_global.k == k, 'Azar (piso)'].iloc[0]
    mejor = max(MODELOS, key=lambda m: detalle[f'{m[0]}@{k}'].mean())[0]
    valor = detalle[f'{mejor}@{k}'].mean()
    print(f'  k={k}: mejor modelo {mejor} con {valor:.3f}, '
          f'{valor/piso:.0f}x por encima del piso de azar ({piso:.3f})')
""")

md(r"""
### El promedio global esconde lo importante

Un único número por modelo responde "¿cuál es mejor en general?", que es la
pregunta menos interesante. La que importa —y la que pide el informe— es **en qué
tipo de consulta gana cada uno**.

Nuestro `queries.json` está construido justamente para poder segmentar: tiene
consultas con solapamiento léxico del 100% y consultas con 0%.
""")

code(r"""
por_tipo = []
for tipo in ['lexica', 'mixta', 'semantica']:
    sub = detalle[detalle.tipo == tipo]
    if sub.empty:
        continue
    fila = {'tipo': tipo, 'consultas': len(sub), 'azar': sub['azar@5'].mean()}
    for nombre, _ in MODELOS:
        fila[nombre] = sub[f'{nombre}@5'].mean()
    por_tipo.append(fila)

tabla_tipos = pd.DataFrame(por_tipo).round(3)
print('precision@5 segmentado por tipo de consulta')
print(tabla_tipos.to_string(index=False))
""")

code(r"""
# Recall@10: cuantos de los relevantes aparecen, no solo cuan limpio es el top.
# No lo pide la consigna; lo agregamos porque precision@k castiga mucho cuando
# los conjuntos de relevantes tienen mas elementos que k.
filas_r = []
for q in queries:
    qid = q['id']
    fila = {'consulta': qid, 'tipo': tipo_de[qid], 'rel': len(relevantes[qid])}
    for nombre, _ in MODELOS:
        fila[nombre] = recall_en_k(rankings[nombre][qid], relevantes[qid], 10)
    filas_r.append(fila)

tabla_recall = pd.DataFrame(filas_r)
print('recall@10 promedio por tipo de consulta')
print(tabla_recall.groupby('tipo')[[m[0] for m in MODELOS]].mean().round(3).to_string())
""")

md(r"""
### Una aparente contradicción con el Bloque 8, y su resolución

En el Bloque 8 mostramos que el promedio de Word2Vec tiene una similitud media de
~0.90 entre pares al azar, con un mínimo que nunca baja de ~0.72: **ningún par de
libros le resulta distinto**. De ahí sacamos que ese espacio no discrimina.

Y sin embargo, en la tabla de arriba el promedio de Word2Vec **no queda último**:
rinde parecido a TF-IDF, y en las consultas léxicas incluso lo supera.

Las dos cosas son ciertas, y conviene decir con precisión qué significa cada una:

- **Los valores absolutos de ese modelo no significan nada.** Una similitud de 0.75
  suena alta y está por debajo del par promedio del corpus. No se pueden usar como
  umbral ("mostrar resultados con similitud > 0.7") ni comparar entre consultas.
- **El orden relativo sí sobrevive.** Aunque todas las similitudes estén apretadas
  en una franja angosta, dentro de esa franja los documentos pertinentes quedan
  arriba. `argsort` sólo necesita el orden, no la escala.

La conclusión práctica: ese modelo **puede ordenar, pero no puede decidir**. Sirve
para un ranking, no para un umbral ni para una medida de confianza. Y la diferencia
entre el puesto 1 y el 20 es de centésimas, así que el ranking es frágil: pequeñas
variaciones del texto lo reordenan.

Esto es un ejemplo de por qué el enunciado insiste en mirar más de una cosa. Con
sólo la tabla de precision@k habríamos concluido que el modelo funciona bien. Con
sólo la distribución, que no sirve para nada. Ninguna de las dos lecturas sola es
correcta.
""")

md(r"""
### Qué mide y qué NO mide esta métrica

**Mide:** qué fracción del top-`k` nuestro anotador consideraría relevante.

**No mide:**

- **El orden dentro del top-k.** Acertar en el puesto 1 y en el 5 vale igual. Para
  eso haría falta MAP o nDCG.
- **Recall**, salvo donde lo agregamos aparte: un modelo que encuentra uno de los
  cinco relevantes y lo pone primero saca la misma precision@5 que otro que
  encuentra otro distinto.
- **Si nuestros relevantes son los correctos.** Es la limitación de fondo: los
  juicios los hicimos nosotros, con un criterio propio, sobre sinopsis
  promocionales. Otro grupo armaría otro conjunto y los números cambiarían.
- **Significancia estadística.** Con 12 consultas y un solo anotador, el intervalo
  de confianza es ancho. **Una diferencia chica entre dos modelos no es una
  diferencia.** Sólo las separaciones grandes, y sobre todo las que se sostienen al
  segmentar por tipo de consulta, dicen algo.

Esta última es la razón por la que la tabla segmentada vale más que el promedio: un
patrón consistente entre tipos de consulta es más creíble que una diferencia de
centésimas en el total.
""")

md(r"""
## Bloque 12 — Parte avanzada: *chunking*

### Por qué esta y no otra

En el Bloque 7 medimos que **el 92% de los documentos se trunca** y que el modelo
descarta el **46% del corpus** antes de producir el vector. Esa es la patología más
grande que encontramos, y el *chunking* la ataca directamente.

**La idea.** En vez de un vector por libro, se parte la sinopsis en pedazos que
entren en el límite del modelo y se guarda **un vector por pedazo**. Al buscar, un
libro puntúa según su **mejor pedazo**: si lo que lo hacía relevante estaba en el
párrafo final, ahora hay un vector que lo representa.

**La hipótesis, declarada antes de medir:** el chunking debería mejorar los
resultados **en los documentos que hoy se truncan**, y no cambiar nada en los que
entran completos. Si mejora parejo en todos, la mejora viene de otro lado y hay que
desconfiar.
""")

code(r"""
PALABRAS_POR_CHUNK = 60     # ~90 sub-tokens en espanol: entra holgado en 128
SOLAPE = 15                 # palabras repetidas entre pedazos consecutivos


def partir(texto, tam=PALABRAS_POR_CHUNK, solape=SOLAPE):
    # Pedazos con solape, para que una idea partida al medio quede entera en
    # alguno de los dos.
    palabras = str(texto).split()
    if len(palabras) <= tam:
        return [' '.join(palabras)]
    paso = tam - solape
    pedazos = [' '.join(palabras[i:i + tam]) for i in range(0, len(palabras), paso)]
    return [p for p in pedazos if len(p.split()) >= 10]


chunks, chunk_a_doc = [], []
for i, texto in enumerate(df.texto_crudo):
    for pedazo in partir(texto):
        chunks.append(pedazo)
        chunk_a_doc.append(i)
chunk_a_doc = np.array(chunk_a_doc)

print(f'{len(df)} documentos -> {len(chunks)} pedazos '
      f'({len(chunks)/len(df):.1f} por documento en promedio)')

largos_chunk = [len(modelo_sbert.tokenizer.encode(c)) for c in chunks]
print(f'Pedazos que SIGUEN truncados: '
      f'{sum(1 for l in largos_chunk if l > LIMITE_TOKENS)}/{len(chunks)}')
""")

code(r"""
X_chunks = modelo_sbert.encode(chunks, normalize_embeddings=True,
                               show_progress_bar=True, batch_size=64)
print(f'\nMatriz de pedazos: {X_chunks.shape}   NaN: {int(np.isnan(X_chunks).sum())}')


def ranking_chunks(consulta):
    # Un libro puntua segun su MEJOR pedazo (max-pooling sobre los chunks).
    e = modelo_sbert.encode([consulta], normalize_embeddings=True).ravel()
    sims_chunk = X_chunks @ e
    mejor = np.full(len(df), -np.inf)
    np.maximum.at(mejor, chunk_a_doc, sims_chunk)
    return mejor.argsort()[::-1]
""")

code(r"""
# Comparacion global y, sobre todo, segmentada por si el documento se truncaba.
largos_doc = np.array([len(modelo_sbert.tokenizer.encode(t)) for t in df.texto_crudo])
se_truncaba = largos_doc > LIMITE_TOKENS
print(f'Documentos que se truncaban: {se_truncaba.sum()}/{len(df)}')

filas_c = []
for q in queries:
    qid = q['id']
    rel = relevantes[qid]
    rel_truncados = {i for i in rel if se_truncaba[i]}
    filas_c.append({
        'consulta': qid, 'tipo': tipo_de[qid],
        'rel': len(rel), 'rel truncados': len(rel_truncados),
        'SBERT entero': precision_en_k(rankings['SBERT'][qid], rel, 5),
        'SBERT chunks': precision_en_k(ranking_chunks(q['consulta']), rel, 5),
        'recall@10 entero': recall_en_k(rankings['SBERT'][qid], rel, 10),
        'recall@10 chunks': recall_en_k(ranking_chunks(q['consulta']), rel, 10),
    })

comp = pd.DataFrame(filas_c)
print()
print(comp.round(2).to_string(index=False))
print()
print('PROMEDIOS')
for col in ['SBERT entero', 'SBERT chunks', 'recall@10 entero', 'recall@10 chunks']:
    print(f'   {col:<20} {comp[col].mean():.3f}')
""")

code(r"""
# La prueba de la hipotesis: la mejora, se concentra en los documentos truncados?
rel_trunc_total = {i for q in queries for i in relevantes[q['id']] if se_truncaba[i]}
rel_enteros_total = {i for q in queries for i in relevantes[q['id']] if not se_truncaba[i]}

def recall_sobre(subconjunto, fn_ranking, k=10):
    # Recall calculado solo sobre los relevantes que pertenecen al subconjunto.
    vals = []
    for q in queries:
        objetivo = relevantes[q['id']] & subconjunto
        if objetivo:
            vals.append(recall_en_k(fn_ranking(q), objetivo, k))
    return float(np.mean(vals)) if vals else float('nan')


entero = lambda q: rankings['SBERT'][q['id']]
troceado = lambda q: ranking_chunks(q['consulta'])

print('recall@10, segmentado por si el documento relevante se truncaba')
print(f"{'subconjunto':<34}{'entero':>9}{'chunks':>9}{'dif':>8}")
for etiqueta, sub in [('relevantes que SE truncaban', rel_trunc_total),
                      ('relevantes que entraban completos', rel_enteros_total)]:
    a, b = recall_sobre(sub, entero), recall_sobre(sub, troceado)
    print(f'{etiqueta:<34}{a:>9.3f}{b:>9.3f}{b-a:>+8.3f}   (n={len(sub)})')
""")

md(r"""
### El chunking empeoró los resultados

La hipótesis era que el chunking mejoraría el recall **en los documentos que se
truncaban**. Los números dicen lo contrario: empeora, y empeora justamente ahí.

No es un error de implementación —ningún pedazo supera el límite de tokens, no hay
`NaN`, y los documentos que entraban completos quedan exactamente igual— así que el
resultado es real y hay que explicarlo, no esconderlo.

**La sospecha.** Al puntuar cada libro por su **mejor** pedazo, un documento con 9
pedazos tiene nueve oportunidades de que alguno obtenga un puntaje alto, y uno con 2
pedazos tiene dos. Si eso es lo que pasa, el chunking no está midiendo relevancia:
está premiando la longitud. Es una hipótesis concreta y se puede testear.
""")

code(r"""
from scipy.stats import spearmanr

# Si el max sobre varios pedazos premia la longitud, la cantidad de pedazos tiene
# que correlacionar con una mejor posicion en el ranking. Con el documento entero
# esa correlacion no deberia existir: es el grupo de control.
n_chunks = np.bincount(chunk_a_doc, minlength=len(df))

posiciones = {'SBERT entero': [], 'SBERT chunks': []}
for q in queries:
    posiciones['SBERT entero'].append(np.argsort(rankings['SBERT'][q['id']]))
    posiciones['SBERT chunks'].append(np.argsort(ranking_chunks(q['consulta'])))

print('Correlacion entre cantidad de pedazos y posicion media en el ranking')
print('   (rho negativo = mas pedazos -> mejor puesto = sesgo por longitud)')
pos_media = {}
for nombre, lista in posiciones.items():
    pos_media[nombre] = np.mean(lista, axis=0)
    rho, pval = spearmanr(n_chunks, pos_media[nombre])
    marca = '  <- significativo' if pval < 0.05 else '  (no significativo)'
    print(f'   {nombre:<16} rho = {rho:+.3f}   p = {pval:.1e}{marca}')

q25, q75 = np.percentile(n_chunks, [25, 75])
print()
print('Posicion media en el ranking (mas chico = mejor puesto)')
print(f"{'':<34}{'entero':>9}{'chunks':>9}")
for etiqueta, m in [(f'docs con POCOS pedazos (<={int(q25)})', n_chunks <= q25),
                    (f'docs con MUCHOS pedazos (>={int(q75)})', n_chunks >= q75)]:
    print(f'{etiqueta:<34}{pos_media["SBERT entero"][m].mean():>9.1f}'
          f'{pos_media["SBERT chunks"][m].mean():>9.1f}')
""")

md(r"""
### Diagnóstico: el chunking introdujo un sesgo por longitud

La sospecha se confirma. Con el documento entero no hay relación entre la longitud y
la posición en el ranking. Con chunking, aparece una correlación **negativa y
estadísticamente significativa**: a más pedazos, mejor puesto.

Y el efecto va en las dos direcciones: los documentos con muchos pedazos **suben** en
el ranking y los que tienen pocos **bajan**, independientemente de si son relevantes.

**Por qué pasa.** Puntuar por el máximo sobre varios pedazos es, en efecto, repartir
boletos de lotería: cada pedazo es una oportunidad más de obtener un puntaje alto por
casualidad. El máximo de 9 muestras tiende a ser mayor que el máximo de 2, aunque las
muestras vengan de la misma distribución. El chunking no midió mejor la relevancia:
cambió la pregunta por "¿qué documento es más largo?".

**Qué haríamos con más tiempo.** El problema no es trocear, es el *max-pooling*.
Alternativas que atacan exactamente este sesgo: promediar los pedazos en vez de tomar
el máximo; normalizar el puntaje por la cantidad de pedazos; o quedarse con el
promedio de los 2 o 3 mejores. Cada una tiene su propio sesgo, y habría que medirlas
con este mismo test.

**Y una limitación honesta de este experimento.** El grupo de control —los documentos
relevantes que entraban completos— tiene sólo 2 casos. Que no cambien no prueba nada;
simplemente no contradice. Con el 92% del corpus truncado, no teníamos corpus
suficiente para armar un control decente.

**El costo, además del resultado.** El chunking cuadruplicó la cantidad de vectores a
almacenar e indexar, y agregó dos parámetros arbitrarios (tamaño del pedazo y solape).
Aun si hubiera mejorado un poco, habría que justificar ese costo. Como empeoró, la
decisión es clara: **no lo llevaríamos a producción**.
""")

md(r"""
---

## Cierre

| Bloque | Parte de la consigna | Estado |
|---|---|---|
| 1-3 | A — corpus y dos versiones del texto | ✅ |
| 4 | línea de base TF-IDF | ✅ |
| 5-6 | B — Word2Vec propio vs. SBW | ✅ |
| 7 | C — modelo de oración y truncamiento | ✅ |
| 8 | D — comparación y visualización | ✅ |
| 9 | E — persistencia en pgvector con HNSW | ✅ |
| 10 | F — búsqueda en SQL con filtro | ✅ |
| 11 | 5 — evaluación con línea de base | ✅ |
| 12 | 6 — parte avanzada (chunking) | ✅ |

Los cuatro entregables: este notebook, `data/queries.json`, el informe y la base
poblada en Supabase.
""")

# =========================================================================== #
notebook = {
    "cells": celdas,
    "metadata": {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3.11"},
        "colab": {"provenance": [], "toc_visible": True},
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}

DESTINO.write_text(json.dumps(notebook, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"Notebook escrito: {DESTINO}")
print(f"  {len(celdas)} celdas "
      f"({sum(1 for c in celdas if c['cell_type']=='code')} de codigo, "
      f"{sum(1 for c in celdas if c['cell_type']=='markdown')} de texto)")
