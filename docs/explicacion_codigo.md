# Explicación paso a paso del código

**Unidad 1 — Extracción y procesamiento de texto**
Extracción de metadatos y sinopsis de Lectulandia con Playwright + BeautifulSoup

Este documento explica **qué hace cada parte del código y por qué está hecha así**.
El código vive en dos archivos equivalentes:

| Archivo | Para qué sirve |
|---|---|
| `src/scraper_lectulandia_colab.ipynb` | Notebook para ejecutar en **Google Colab** (API asincrónica de Playwright). |
| `src/scraper.py` | El mismo programa como script de línea de comandos (API sincrónica). |

Los dos hacen exactamente lo mismo y comparten las funciones de análisis del HTML.
La diferencia está sólo en cómo se maneja `asyncio`, que se explica en el paso 6.

---

## Idea general: quién hace qué

El trabajo se reparte entre cuatro herramientas, y es importante no confundir sus roles:

```
        ┌──────────────┐   HTML ya    ┌────────────────┐   datos     ┌────────┐   libros.csv
 URL ──►│  Playwright  │─ renderizado►│ BeautifulSoup  │─ sueltos ──►│ pandas │──────────────►
        │  (navegar)   │              │   (analizar)   │             │(ordenar)│
        └──────────────┘              └────────────────┘             └────────┘
```

* **Playwright** *no* entiende de libros: sólo abre un navegador Chromium real, va a
  una dirección, espera a que el sitio termine de armarse y devuelve el HTML.
* **BeautifulSoup** *no* navega: recibe ese texto HTML y busca dentro de él dónde
  están el título, los autores, los géneros y la sinopsis.
* **pandas** *no* toca la web: toma las filas ya extraídas, las limpia, saca
  duplicados y las exporta a CSV.

**¿Por qué Playwright y no simplemente `requests`?** Porque el sitio arma parte de su
contenido con JavaScript en el navegador. `requests` devolvería el HTML "crudo", tal
como sale del servidor, y varios datos podrían faltar. Playwright ejecuta ese
JavaScript, así que el HTML que entrega es el que realmente ve una persona.

---

## Paso 0 — Instalación de dependencias

```python
!pip install -q playwright beautifulsoup4 lxml pandas nest_asyncio
!playwright install chromium
!playwright install-deps chromium
```

Hay que entender que son **tres cosas distintas**:

1. `pip install playwright` instala la **librería de Python** (el "control remoto").
2. `playwright install chromium` descarga el **navegador** propiamente dicho
   (unos 130 MB). Sin este paso el programa falla con
   `Executable doesn't exist at ...`.
3. `playwright install-deps` instala las **librerías del sistema operativo** que
   Chromium necesita para arrancar dentro de la máquina virtual de Colab
   (fuentes, bibliotecas gráficas, etc.).

`lxml` es el analizador de HTML que usa BeautifulSoup; es bastante más rápido y más
tolerante con el HTML mal formado que el analizador que trae Python de fábrica.

---

## Paso 1 — Configuración

Todas las constantes que podrían cambiar están juntas al principio, en lugar de
repartidas por el código. Si el grupo cambiara de categoría, alcanza con tocar dos
líneas y nada más se rompe.

```python
CATEGORIA_URL        = "https://ww3.lectulandia.co/genero/intriga/"
N_LIBROS_OBJETIVO    = 100      # la Parte 2 exige entre 50 y 100 fichas
PAUSA_MIN, PAUSA_MAX = 1.5, 3.0 # pausa aleatoria entre visitas
TIMEOUT_MS           = 45_000
HEADLESS             = True
VALOR_FALTANTE       = ""       # representación consistente de campos ausentes
```

Dos decisiones que conviene justificar en la defensa del trabajo:

* **`HEADLESS = True`** — el navegador corre sin abrir ventana. En Colab es
  obligatorio (no hay pantalla), y además consume mucha menos memoria. Es
  exactamente lo que pide la consigna con *"puede ejecutarse sin mostrar la ventana
  del navegador"*.
* **`VALOR_FALTANTE = ""`** — se fija **un único** valor para "este dato no está".
  Sin esta decisión terminaríamos con una mezcla de `None`, `NaN`, `"N/A"` y `"-"`
  en el CSV, que es justamente lo que el control mínimo de *"campos ausentes
  representados de manera consistente"* busca evitar.

En Colab aparece además una línea que no está en el script:

```python
nest_asyncio.apply()
```

Colab ya tiene un *event loop* de asyncio funcionando (es lo que le permite atender
la interfaz mientras ejecuta celdas). Playwright asincrónico quiere crear el suyo, y
sin este parche el programa falla con `This event loop is already running`.
`nest_asyncio` permite anidar loops y resuelve el conflicto.

---

## Paso 2 — Limpieza de texto

```python
ESPACIOS = re.compile(r"\s+")

def limpiar(texto):
    if texto is None:
        return VALOR_FALTANTE
    texto = str(texto).replace("\xa0", " ")
    return ESPACIOS.sub(" ", texto).strip()
```

Es una función corta pero hace tres cosas importantes:

1. **`\xa0` → espacio normal.** El HTML usa `&nbsp;` (espacio duro) para que el
   navegador no corte la línea ahí. Al extraer el texto, Python lo recibe como el
   carácter `\xa0`, que *parece* un espacio pero no lo es: `"a\xa0b".split()` se
   comporta distinto de lo esperado y el CSV queda con caracteres raros.
2. **`\s+` → un solo espacio.** Las sinopsis del sitio vienen con sangrías y saltos
   de línea del maquetado. Un salto de línea dentro de un campo CSV es una fuente
   clásica de archivos rotos.
3. **`.strip()`** saca los espacios de los extremos.

Con esto ya quedan cubiertos dos de los siete controles mínimos.

```python
def unir(valores, sep="; "):
    limpios = [limpiar(v) for v in valores]
    limpios = [v for v in limpios if v]
    return sep.join(dict.fromkeys(limpios)) or VALOR_FALTANTE
```

Un libro puede tener varios autores o varios géneros, pero el CSV tiene **una celda
por campo**. Se resuelve uniéndolos con `"; "`.

* Se eligió `;` y no `,` porque la coma es el separador del CSV: usarla obligaría a
  entrecomillar y complicaría leer el archivo después.
* `dict.fromkeys(...)` elimina repetidos **conservando el orden**. Un `set` también
  quitaría repetidos, pero desordenaría los autores, y no queremos que el mismo
  libro salga distinto en dos corridas.
* El `or VALOR_FALTANTE` final convierte la lista vacía en `""`, respetando la
  convención del paso 1.

---

## Paso 3 — Encontrar las fichas en el listado

De cada página de la categoría sólo nos interesan **las direcciones de las fichas**.

```python
RE_FICHA = re.compile(r"^/(?:book|libro)/[^/]+/?$")

def extraer_urls_listado(html, base=BASE_URL):
    soup = BeautifulSoup(html, "lxml")
    urls = []
    for a in soup.select("a[href]"):
        href = a["href"].split("?")[0].split("#")[0]
        absoluta = urljoin(base, href)
        if RE_FICHA.match(urlparse(absoluta).path):
            urls.append(absoluta)
    return list(dict.fromkeys(urls))
```

**La decisión de diseño más importante de esta función** es no buscar los enlaces por
su clase CSS (algo como `.card a` o `.book-item a`), sino por **la forma de la ruta**.
Las clases del maquetado cambian cuando el sitio se rediseña y el scraper deja de
funcionar de un día para el otro; en cambio la estructura de las direcciones
(`/book/<slug>/`) es parte de cómo está organizado el sitio y es mucho más estable.

La expresión regular se lee así:

| Parte | Significado |
|---|---|
| `^/` | la ruta arranca en la raíz del sitio |
| `(?:book\|libro)` | acepta cualquiera de las dos variantes, sin capturarla |
| `/[^/]+` | exactamente un tramo más, sin barras adentro |
| `/?$` | una barra final opcional, y ahí termina |

Ese `[^/]+` seguido de `$` es lo que descarta rutas más profundas como
`/book/slug/capitulo/`, que no son fichas de libro.

Después se normaliza cada enlace, y cada paso evita un duplicado distinto:

* `.split("?")[0]` saca la *query string*: `/book/x/?utm=1` y `/book/x/` son el mismo libro.
* `.split("#")[0]` saca el fragmento: `/book/x/#comentarios` también.
* `urljoin` convierte `/book/x/` en `https://ww3.lectulandia.co/book/x/`, porque en el
  CSV queremos direcciones completas que se puedan abrir.
* `dict.fromkeys` elimina los repetidos que quedan dentro de la misma página (es
  común que la portada y el título del mismo libro sean dos enlaces distintos).

```python
def url_pagina(n):
    return CATEGORIA_URL if n == 1 else f"{CATEGORIA_URL.rstrip('/')}/page/{n}/"
```

La paginación del sitio sigue el patrón `.../genero/intriga/page/2/`, salvo la
primera página, que no lleva sufijo.

---

## Paso 4 — Extraer los datos de la ficha

Los selectores salen de inspeccionar la ficha con las herramientas de desarrollo del
navegador (F12). El sitio guarda cada dato en un `<div>` con **id propio**, y le
antepone un rótulo:

```html
<div id="title"><h1>TÍTULO</h1></div>
<div id="autor"    class="realign"><span class="tagTitle">Autor: </span>  <a class="dinSource" ...>AUTOR</a></div>
<div id="genero"   class="realign"><span class="tagTitle">Generos: </span><a class="dinSource" ...>Intriga</a> <a ...>Novela</a></div>
<div id="sinopsis" class="realign"><span>Sinopsis</span> <p>…</p></div>
```

Que cada dato tenga un `id` es una buena noticia: los `id` son **únicos por página** y
suelen sobrevivir a los rediseños mejor que las clases.

### El problema del rótulo

Si sobre el bloque del autor hiciéramos directamente `.get_text()`, obtendríamos
`"Autor: David McCloskey"` en lugar de `"David McCloskey"`. El rótulo forma parte del
mismo `div`. La solución es eliminarlo antes de leer:

```python
def _bloque(soup, id_div):
    div = soup.find("div", id=id_div)
    if div is None:
        return None
    for span in div.select("span.tagTitle"):
        span.decompose()          # elimina "Autor:", "Generos:", etc.
    return div
```

`decompose()` **borra el nodo del árbol**, de forma permanente. Es seguro hacerlo
porque cada `id` aparece una sola vez y cada `soup` se usa para un único libro; no
estamos rompiendo nada que se necesite después.

### Un solo patrón para tres campos

Autores, géneros y serie tienen la misma estructura (varios `<a>` dentro de un `div`
con id), así que comparten una función:

```python
def _valores_enlazados(soup, id_div):
    div = _bloque(soup, id_div)
    if div is None:
        return VALOR_FALTANTE
    enlaces = [a.get_text() for a in div.select("a")]
    return unir(enlaces) if enlaces else limpiar(div.get_text())
```

El `else` del final es un detalle que evita perder datos: si el bloque existe pero el
valor **no** está enlazado (pasa con `serie` en algunas fichas), se toma igual el
texto plano en vez de devolver vacío.

### La sinopsis

```python
div_sinopsis = _bloque(soup, "sinopsis")
if div_sinopsis is not None:
    parrafos = [limpiar(p.get_text()) for p in div_sinopsis.find_all("p")]
    parrafos = [p for p in parrafos if p]
    sinopsis = " ".join(parrafos) if parrafos else limpiar(div_sinopsis.get_text())
    if sinopsis.lower().startswith("sinopsis"):
        sinopsis = limpiar(sinopsis[len("sinopsis"):])
```

Se recorren los `<p>` uno por uno y se unen con un espacio, en vez de hacer un
`get_text()` sobre todo el bloque. La razón: `get_text()` pega los párrafos sin
separación y produce cosas como `"...final del primero.Empieza el segundo..."`.

La última condición saca el rótulo `Sinopsis` cuando viene en un `<span>` sin la
clase `tagTitle`, que `_bloque()` no alcanza a eliminar.

### Planes B

Cada campo crítico tiene una alternativa por si una ficha usa otro maquetado:

```python
if not titulo:                                  # plan B del título
    h1 = soup.find("h1")
    titulo = limpiar(h1.get_text()) if h1 else VALOR_FALTANTE

if not sinopsis:                                # plan B de la sinopsis
    meta = soup.find("meta", attrs={"name": "description"})
    sinopsis = limpiar(meta.get("content")) if meta else VALOR_FALTANTE
```

El primer `<h1>` de una página es casi siempre su título, y la etiqueta
`<meta name="description">` suele contener la sinopsis (los sitios la ponen ahí para
Google). Gracias a estos respaldos, una ficha con estructura distinta se recupera
igual en vez de perderse.

> **Sobre la portada:** se guarda únicamente **la dirección** de la imagen, nunca la
> imagen. Es un campo opcional que la consigna permite.

La función devuelve un diccionario con las claves exactas de `COLUMNAS`, lo que
permite escribirlo directo con `csv.DictWriter` sin conversiones intermedias.

---

## Paso 5 — Navegación y guardado incremental

### Traer el HTML sin morir en el intento

```python
async def obtener_html(page, url, intentos=3):
    for intento in range(1, intentos + 1):
        try:
            await page.goto(url, timeout=TIMEOUT_MS, wait_until="domcontentloaded")
            await page.wait_for_timeout(800)
            return await page.content()
        except Exception as e:
            print(f"      ! intento {intento}/{intentos} falló ({type(e).__name__}) en {url}")
            await asyncio.sleep(2 * intento)          # espera creciente
    return None
```

Esta función es la que cumple el requisito de **"controlar errores sin detener
completamente la ejecución"**. Tres detalles:

* **`wait_until="domcontentloaded"`** en lugar del valor por defecto (`load`).
  `load` espera a que terminen de cargar *todas* las imágenes y la publicidad, lo que
  puede tardar muchísimo y a veces nunca ocurre. `domcontentloaded` espera sólo a que
  el HTML esté armado, que es lo único que necesitamos.
* **La espera creciente** (`2 * intento`: 2 s, 4 s, 6 s). Si el servidor está
  saturado, reintentar de inmediato empeora las cosas; dar cada vez más tiempo es la
  estrategia habitual.
* **Devolver `None` en vez de lanzar una excepción.** Quien llama decide qué hacer:
  contar el error y seguir con el próximo libro. Así una sola ficha rota no tira
  abajo una corrida de una hora.

### Guardar sobre la marcha

```python
def guardar_fila(fila, ruta=CSV_PARCIAL):
    es_nuevo = not ruta.exists()
    with open(ruta, "a", newline="", encoding="utf-8") as f:
        escritor = csv.DictWriter(f, fieldnames=COLUMNAS)
        if es_nuevo:
            escritor.writeheader()
        escritor.writerow(fila)
```

Se abre en modo `"a"` (*append*) y se escribe **cada libro apenas se obtiene**, en vez
de acumular todo en memoria y guardar al final. Es lo que pide la consigna con
*"guarde los resultados incrementalmente"*, y tiene una ventaja muy concreta: si
Colab se desconecta en el libro 87, los 86 anteriores ya están en disco.

Dos detalles técnicos:

* `newline=""` es **obligatorio** al escribir CSV en Windows. Sin eso, el módulo `csv`
  escribe `\r\n` y Windows lo vuelve a traducir, dejando una línea en blanco entre
  cada fila.
* `encoding="utf-8"` asegura que las tildes y las eñes se guarden bien.

### Poder retomar

```python
def urls_ya_guardadas(ruta=CSV_PARCIAL):
    if not ruta.exists():
        return set()
    try:
        return set(pd.read_csv(ruta, dtype=str)["url_libro"].dropna())
    except Exception:
        return set()
```

Al arrancar se relee el CSV parcial y se arma un **conjunto** con lo ya extraído. Esto
da dos cosas al mismo tiempo:

* **Evitar duplicados** durante la corrida (el requisito de la consigna).
* **Reanudar**: si se vuelve a ejecutar, sigue desde donde quedó en vez de empezar de
  cero.

Se usa un `set` y no una lista porque preguntarle `if url in vistos` a un conjunto es
inmediato, mientras que a una lista de 100 elementos la obliga a recorrerlos todos
cada vez.

---

## Paso 6 — El orquestador

Es la función que ordena todo lo anterior siguiendo la estrategia declarada en la
Parte 1. Su esqueleto:

```python
while len(vistos) < objetivo and n_pagina <= max_paginas:   # (1) (2)
    html_listado = await obtener_html(pagina_web, url_pagina(n_pagina))   # (3)
    fichas = extraer_urls_listado(html_listado)                           # (4) (5)

    for url in fichas:
        if len(vistos) >= objetivo: break
        if url in vistos: continue                                        # (9)

        await asyncio.sleep(random.uniform(PAUSA_MIN, PAUSA_MAX))         # pausa
        html_ficha = await obtener_html(pagina_web, url)                  # (6)
        fila = parsear_ficha(html_ficha, url)                             # (7)

        if not fila["titulo"]: continue                                   # (8)
        guardar_fila(fila)                                                # (10)
        vistos.add(url)
    n_pagina += 1
```

Los números remiten a los diez pasos de la estrategia de extracción del diseño.

**La condición doble del `while`** es una red de seguridad. La primera parte
(`len(vistos) < objetivo`) es la que normalmente corta el ciclo; la segunda
(`n_pagina <= max_paginas`) evita un bucle infinito si algo sale mal — por ejemplo, si
el sitio devolviera siempre la misma página, o si hubiera menos libros de los
esperados en la categoría.

**La pausa es aleatoria, no fija:**

```python
await asyncio.sleep(random.uniform(PAUSA_MIN, PAUSA_MAX))   # entre 1,5 y 3 segundos
```

Cumple el requisito de *"incorpore una pausa entre las páginas visitadas"*. Que sea
aleatoria en lugar de un `sleep(2)` fijo tiene dos motivos: reparte mejor la carga
sobre el servidor y genera un patrón de tráfico menos artificial. Con ~2,25 segundos
promedio, 100 libros llevan unos 4 minutos de pausas, más el tiempo de carga: entre 6
y 10 minutos en total.

**Tres filtros descartan datos malos antes de escribirlos:** que `obtener_html`
haya devuelto `None`, que `parsear_ficha` haya lanzado una excepción, y que la
fila salga sin título. Los tres suman al contador `errores` y siguen adelante.

### La diferencia entre el notebook y el script

Es lo único que realmente cambia entre los dos archivos:

| | Notebook (Colab) | Script (`scraper.py`) |
|---|---|---|
| API | `playwright.async_api` | `playwright.sync_api` |
| Llamadas | `await page.goto(...)` | `page.goto(...)` |
| Pausa | `await asyncio.sleep(...)` | `time.sleep(...)` |
| Extra | `nest_asyncio.apply()` | — |

El motivo es que Colab **ya está corriendo un event loop**. La API sincrónica de
Playwright intenta crear el suyo propio y falla con
`It looks like you are using Playwright Sync API inside the asyncio loop`. Fuera del
notebook ese problema no existe, y la API sincrónica es más simple de leer.

---

## Paso 7 — Ejecución

```python
await scrapear()
```

Colab permite usar `await` directamente en una celda, sin envolverlo en
`asyncio.run()`. Si la sesión se corta, se vuelve a ejecutar esta misma celda y el
proceso retoma gracias a `urls_ya_guardadas()`.

---

## Paso 8 — Limpieza final con pandas

Cada fila ya se limpió al escribirla, pero se repasa el dataset completo. La razón es
que algunos problemas **sólo se ven mirando el conjunto**: un duplicado no se detecta
mirando una fila sola.

```python
df = pd.read_csv(CSV_PARCIAL, dtype=str)

for col in COLUMNAS:
    if col not in df.columns:
        df[col] = VALOR_FALTANTE
df = df[COLUMNAS].fillna(VALOR_FALTANTE)

for col in COLUMNAS:
    df[col] = df[col].map(limpiar)

df = df[df["titulo"] != ""]
df = df[df["url_libro"].str.startswith("http")]
df = df.drop_duplicates(subset="url_libro", keep="first")
df = df.drop_duplicates(subset=["titulo", "autores"], keep="first")
df = df.head(N_LIBROS_OBJETIVO).reset_index(drop=True)
```

Decisiones a destacar:

* **`dtype=str`** obliga a pandas a leer todo como texto. Sin esto, pandas "adivina"
  los tipos y estropea datos: un título como `"1984"` se convertiría en el número
  1984, y una serie llamada `"NaN"` desaparecería.
* **`.fillna(VALOR_FALTANTE)`** convierte los `NaN` que pandas crea en las celdas
  vacías del CSV a la cadena vacía, manteniendo la convención única del paso 1.
* **`df[COLUMNAS]`** reordena las columnas al orden acordado y descarta cualquier
  columna extra.
* **Dos deduplicaciones, no una.** La primera, por `url_libro`, es la que exige la
  consigna. La segunda, por `titulo` + `autores`, atrapa un caso que la primera deja
  pasar: el mismo libro publicado bajo dos direcciones distintas (reediciones,
  cambios de portada). `keep="first"` conserva la primera aparición.

---

## Paso 9 — Controles mínimos

Los siete controles de la consigna, verificados por código en lugar de a ojo:

```python
controles = {
    "Sin duplicados por url_libro":              df["url_libro"].duplicated().sum() == 0,
    "Todos los registros tienen título":         (df["titulo"].str.len() > 0).all(),
    "Todas las URL son válidas":                 df["url_libro"].str.match(r"^https?://").all(),
    "La mayoría tiene sinopsis (>80%)":          (df["sinopsis"].str.len() > 0).mean() > 0.80,
    "Sin espacios ni saltos de línea sobrantes": sin_espacios_raros,
    "Campos ausentes representados igual":       df.isna().sum().sum() == 0,
    "Cantidad entre 50 y 100 libros":            50 <= len(df) <= 100,
}
assert controles_minimos(df), "Hay controles mínimos que no se cumplen: revisar antes de entregar."
```

El control de espacios merece una mirada, porque es el menos obvio:

```python
sin_espacios_raros = not df.map(
    lambda v: isinstance(v, str) and (v != v.strip() or "\n" in v or "  " in v)
).to_numpy().any()
```

`df.map(...)` aplica la función a **cada celda** del DataFrame y devuelve una tabla de
`True`/`False`; `.any()` pregunta si alguna dio `True`. Se marcan tres síntomas:
espacios en los extremos (`v != v.strip()`), saltos de línea (`"\n" in v`) y espacios
dobles (`"  " in v`). Si ninguna celda tiene ninguno, el control pasa.

*(Nota: en versiones de pandas anteriores a la 2.1 este método se llamaba
`applymap`. Colab trae pandas 2.x, así que `map` es el correcto.)*

El `assert` final es deliberado: si un control falla, **la ejecución se detiene** en
vez de exportar en silencio un CSV defectuoso. Es preferible enterarse en Colab que
después de la entrega.

---

## Paso 10 — Exportación

```python
df.to_csv(CSV_FINAL, index=False, encoding="utf-8")
```

* **`index=False`** evita que pandas agregue una primera columna con la numeración de
  filas, que no forma parte del dataset y ensucia el archivo.
* **`encoding="utf-8"`** para que las tildes se guarden correctamente.

Después, `files.download()` dispara la descarga al equipo. Va dentro de un
`try/except` para que el notebook también funcione fuera de Colab, donde
`google.colab` no existe.

---

## Paso 11 — Exploración del corpus

No lo pide la consigna, pero da material para el informe y sirve como control de
sanidad: si las sinopsis promediaran 3 palabras, algo estaría fallando en el parser.

```python
df["n_palabras_sinopsis"] = df["sinopsis"].str.split().str.len()

generos = df["generos"].str.split("; ").explode().str.strip()
print(generos[generos != ""].value_counts().head(10))
```

`explode()` es la operación interesante: convierte cada elemento de una lista en su
propia fila. Como el campo `generos` guarda varios valores unidos por `"; "`, primero
se separa en lista y después se "explota", de modo que un libro con tres géneros
aporte una unidad a cada uno. Sin esto, `value_counts()` contaría la combinación
`"Intriga; Novela"` como si fuera un género único.

---

## Resumen: dónde se cumple cada requisito

| Requisito de la consigna | Dónde está resuelto |
|---|---|
| Inicia Chromium mediante Playwright | `chromium.launch()` en `scrapear()` |
| Puede ejecutarse sin mostrar la ventana | `HEADLESS = True` |
| Recorre la categoría seleccionada | ciclo `while` sobre `url_pagina(n)` |
| Obtiene entre 50 y 100 fichas | `N_LIBROS_OBJETIVO = 100` + control mínimo |
| Utiliza BeautifulSoup para extraer los datos | `extraer_urls_listado()`, `parsear_ficha()` |
| Incorpora una pausa entre las páginas | `random.uniform(PAUSA_MIN, PAUSA_MAX)` |
| Controla errores sin detener la ejecución | reintentos en `obtener_html()`, `try/except` por ficha |
| Evita registros duplicados | conjunto `vistos` + doble `drop_duplicates()` |
| Guarda los resultados incrementalmente | `guardar_fila()` en modo *append* |
| Genera el archivo final `libros.csv` | `df.to_csv(CSV_FINAL)` |
| No descarga libros ni archivos | sólo se leen metadatos; ninguna descarga en el código |
