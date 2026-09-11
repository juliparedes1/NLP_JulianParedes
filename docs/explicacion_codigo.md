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

> **Versión 2.** Después de una prueba parcial con 10 libros se corrigieron dos
> errores de extracción, `autores` y `generos` pasaron a ser **listas**, y se
> agregaron el modo prueba y las advertencias de calidad. El diagnóstico completo
> está en la sección [Cambios de la versión 2](#cambios-de-la-versión-2-análisis-de-la-prueba-con-10-libros),
> y cada parte modificada está marcada con **(v2)** a lo largo del documento.

---

## Idea general: quién hace qué

El trabajo se reparte entre cuatro herramientas, y es importante no confundir sus roles:

```
        ┌──────────────┐   HTML ya    ┌────────────────┐   datos     ┌────────┐   libros.csv
 URL ──►│  Playwright  │─ renderizado►│ BeautifulSoup  │─ sueltos ──►│ pandas │──────────────►
        │  (navegar)   │              │   (analizar)   │             │(ordenar)│  libros.json
        └──────────────┘              └────────────────┘             └────────┘
```

* **Playwright** *no* entiende de libros: sólo abre un navegador Chromium real, va a
  una dirección, espera a que el sitio termine de armarse y devuelve el HTML.
* **BeautifulSoup** *no* navega: recibe ese texto HTML y busca dentro de él dónde
  están el título, los autores, los géneros y la sinopsis.
* **pandas** *no* toca la web: toma las filas ya extraídas, las limpia, saca
  duplicados y las exporta.

**¿Por qué Playwright y no simplemente `requests`?** Porque el sitio arma parte de su
contenido con JavaScript en el navegador. `requests` devolvería el HTML "crudo", tal
como sale del servidor, y varios datos podrían faltar. Playwright ejecuta ese
JavaScript, así que el HTML que entrega es el que realmente ve una persona.

---

## Cambios de la versión 2: análisis de la prueba con 10 libros

La prueba parcial (`python src/scraper.py --n 10`) terminó con:

```
ATENCION: hay controles minimos que no se cumplen. Revisar antes de entregar.
```

Al pasar los controles sobre el CSV generado, y al revisar los datos a mano, apareció
**una causa del aviso y dos errores silenciosos** que los controles no detectaban.

### 1. La causa del aviso: el control de cantidad

```
  OK   Sin duplicados por url_libro
  OK   Todos los registros tienen titulo
  OK   Todas las URL son validas
  OK   La mayoria tiene sinopsis (>80%)
  OK   Sin espacios ni saltos de linea sobrantes
  OK   Campos ausentes representados igual
FALLA  Cantidad entre 50 y 100 libros         <-- 10 libros
```

Seis de los siete controles pasaban. El único que fallaba era la cantidad, lo cual
**es esperable en una prueba de 10 libros**: el rango 50–100 está fijo porque es lo
que exige la consigna para la entrega. El problema real era de comunicación: el
mensaje final no decía *qué* control fallaba, y parecía un error de los datos.

**Solución:**

* **Modo prueba.** Si se piden menos de 50 libros (`--n 10` en el script, o
  `N_LIBROS_OBJETIVO = 10` en el notebook), el control de cantidad se marca `OMIT.`
  en lugar de `FALLA`, con una nota que recuerda correr con 100 para la entrega.
* **El mensaje final lista por nombre** los controles que no se cumplen:

```
ATENCION: no se cumplen estos controles minimos:
  - Cantidad entre 50 y 100 libros
Revisar antes de entregar.
```

### 2. Error silencioso: portadas equivocadas

| Libro | Portada guardada |
|---|---|
| Misteriosa noche de paz | `.../Sophie%20Hannah/Misteriosa%20noche%20de%20paz%20(12)/small.jpg` ✔ |
| Yo no soy Sherlock Holmes | `.../Sophie%20Hannah/Misteriosa%20noche%20de%20paz%20(12)/small.jpg` ✘ |
| Réquiem | `.../Sophie%20Hannah/Misteriosa%20noche%20de%20paz%20(12)/small.jpg` ✘ |
| … (6 libros más, igual) | ✘ |
| Maldito Mr. White | `.../Anny%20Peterson/Maldito%20Mr%20White%20(20)/small.jpg` ✔ |

**9 de 10 libros tenían la portada de otro libro** (sólo había 2 direcciones
distintas). La causa estaba en el selector de respaldo:

```python
img = soup.select_one("div#cover img, .thumbnail img, article img")   # versión 1
```

`article img` es demasiado genérico: la página tiene otros bloques (por ejemplo, un
listado de novedades) donde cada libro es un `<article>`, y `select_one` devuelve el
**primero del documento**, que no era el libro de la ficha. Ningún control lo
detectaba porque la portada es un campo opcional y la dirección era válida.

**Solución:** la portada sólo se acepta si su dirección (o su texto alternativo)
**contiene el título del libro**. El sitio arma la ruta de la imagen con el autor y
el título (`/Anny%20Peterson/Maldito%20Mr%20White%20(20)/`), así que eso sirve como
comprobación. Si ninguna imagen coincide, el campo queda vacío: **una portada
ausente es preferible a una equivocada**. Detalle en el [paso 4](#la-portada-v2).

### 3. Error silencioso: oraciones pegadas en las sinopsis

```
"...a tiempo para celebrar la navidad?19 de diciembre..."
"Mi trabajo es mentir, pero contigo no voy a hacerlo.Respeto demasiado tu inteligencia.O quizás..."
```

**28 casos en 8 de los 10 libros.** El sitio separa los renglones de la sinopsis con
`<br>`, y `get_text()` concatena los fragmentos de texto sin agregar nada entre
ellos: `hacerlo.<br>Respeto` → `"hacerlo.Respeto"`. La versión 1 separaba bien los
`<p>`, pero no los `<br>`.

Para el procesamiento de texto de las próximas unidades esto es grave: un
tokenizador ve `hacerlo.Respeto` como **una sola palabra**, y un separador de
oraciones no encuentra el corte. Tampoco lo detectaba ningún control: no hay espacios
de más, sino **de menos**.

**Solución:** antes de extraer el texto, cada `<br>` se reemplaza por un salto de
línea, y se agrega otro antes y después de cada bloque (`<p>`, `<div>`, …). Detalle
en el [paso 4](#la-sinopsis-v2).

> **Importante:** este error no se puede corregir sobre el CSV ya generado, porque el
> texto se guardó pegado y ya no se sabe dónde estaban los cortes. Hay que **volver a
> extraer**: `python src/scraper.py --reiniciar` o `REINICIAR = True` en el notebook.
> Las portadas, en cambio, sí se corrigen solas al armar el dataset (paso 8).

### 4. Advertencias de calidad para que no vuelva a pasar

Los dos errores silenciosos pasaron desapercibidos porque ningún control los buscaba.
Se agregaron dos **advertencias** que no bloquean la entrega pero los hacen visibles:

```
Advertencias de calidad (no bloquean la entrega):
AVISO  Sinopsis sin oraciones pegadas      28 casos en 8 libros
  OK   Portadas sin repetir entre libros
```

### 5. Autores y géneros como listas

A pedido del grupo, `autores` y `generos` pasaron de texto (`"Intriga; Novela"`) a
**listas** (`["Intriga", "Novela"]`), porque un libro puede tener varios. Esto afecta
a varias partes del código (pasos 2, 4, 5, 8, 9, 10 y 11), todas marcadas con
**(v2)**.

### Resumen de los cambios

| Cambio | Dónde | Por qué |
|---|---|---|
| `autores` y `generos` como listas | pasos 2, 4, 5, 8–11 | pedido del grupo: un libro puede tener varios |
| Se exporta también `libros.json` | paso 10 | el formato natural para arrays |
| Portada validada contra el título | paso 4 | 9 de 10 portadas eran de otro libro |
| Sinopsis respetando los `<br>` | paso 4 | 28 oraciones pegadas en 8 de 10 libros |
| Red de seguridad de portadas | paso 8 | corrige también los CSV de la versión 1 |
| Modo prueba | paso 9 | una prueba de 10 libros no debe "fallar" |
| El aviso final nombra el control | paso 9 | antes no se sabía cuál fallaba |
| Advertencias de calidad | paso 9 | detectar errores silenciosos |
| Opción `--reiniciar` / `REINICIAR` | pasos 1 y 7 | forzar la reextracción tras cambiar el código |
| `keep_default_na=False` al leer | pasos 5 y 8 | celdas vacías como `""`, no `NaN` |
| Salida tolerante en la consola de Windows | script | un título con `ł` o `ō` cortaba la corrida |

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
CATEGORIA_URL          = "https://ww3.lectulandia.co/genero/intriga/"
N_LIBROS_OBJETIVO      = 100      # para una prueba rápida, p. ej. 10 (modo prueba)
MIN_LIBROS, MAX_LIBROS = 50, 100  # rango exigido por la consigna          (v2)
REINICIAR              = False    # True = borra el CSV parcial             (v2)
PAUSA_MIN, PAUSA_MAX   = 1.5, 3.0 # pausa aleatoria entre visitas
TIMEOUT_MS             = 45_000
HEADLESS               = True
VALOR_FALTANTE         = ""       # campo de texto ausente (listas: [])
COLUMNAS_LISTA         = ["autores", "generos"]                            # (v2)
```

Decisiones que conviene justificar en la defensa del trabajo:

* **`HEADLESS = True`** — el navegador corre sin abrir ventana. En Colab es
  obligatorio (no hay pantalla), y además consume mucha menos memoria. Es
  exactamente lo que pide la consigna con *"puede ejecutarse sin mostrar la ventana
  del navegador"*.
* **`VALOR_FALTANTE = ""`** — se fija **un único** valor para "este dato no está".
  Sin esta decisión terminaríamos con una mezcla de `None`, `NaN`, `"N/A"` y `"-"`
  en el CSV, que es justamente lo que el control mínimo de *"campos ausentes
  representados de manera consistente"* busca evitar. **(v2)** Para los campos de
  lista la regla equivalente es la lista vacía `[]`.
* **`MIN_LIBROS` y `MAX_LIBROS`** **(v2)** — el rango de la consigna quedó como
  constante aparte de `N_LIBROS_OBJETIVO`. Así se puede pedir 10 libros para probar
  sin tocar el rango de la entrega; si el objetivo es menor que `MIN_LIBROS`, el
  programa entra en **modo prueba** (paso 9).
* **`REINICIAR`** **(v2)** — el programa normalmente *retoma* desde el CSV parcial y
  no vuelve a visitar los libros ya guardados. Eso es útil ante una desconexión, pero
  después de corregir el código de extracción hay que forzar la reextracción. En el
  script es la opción `--reiniciar`.
* **`COLUMNAS_LISTA`** **(v2)** — los campos que se manejan como listas. Todo el
  código que distingue texto de listas consulta esta constante, en lugar de repetir
  los nombres de las columnas.

En Colab aparece además una línea que no está en el script:

```python
nest_asyncio.apply()
```

Colab ya tiene un *event loop* de asyncio funcionando (es lo que le permite atender
la interfaz mientras ejecuta celdas). Playwright asincrónico quiere crear el suyo, y
sin este parche el programa falla con `This event loop is already running`.
`nest_asyncio` permite anidar loops y resuelve el conflicto.

---

## Paso 2 — Limpieza de texto y manejo de listas

### `limpiar()`

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
   carácter `\xa0`, que *parece* un espacio pero no lo es.
2. **`\s+` → un solo espacio.** Las sinopsis del sitio vienen con sangrías y saltos
   de línea del maquetado. Un salto de línea dentro de un campo CSV es una fuente
   clásica de archivos rotos.
3. **`.strip()`** saca los espacios de los extremos.

Con esto ya quedan cubiertos dos de los siete controles mínimos.

### Listas **(v2)**

Un libro puede tener varios autores o varios géneros, así que esos campos son
**listas de Python** mientras el programa trabaja. El problema es que un CSV sólo
guarda texto, una celda por campo. Hacen falta funciones para ir y volver:

```python
def lista_limpia(valores):
    limpios = [limpiar(v) for v in valores]
    return list(dict.fromkeys(v for v in limpios if v))
```

Limpia cada elemento, descarta los vacíos y elimina repetidos. `dict.fromkeys(...)`
elimina repetidos **conservando el orden**: un `set` también quitaría repetidos, pero
desordenaría los autores, y el primer autor de un libro suele ser el principal.

```python
def a_json(lista):
    return json.dumps(lista, ensure_ascii=False)
```

Convierte la lista en texto para guardarla en **una** celda del CSV:
`["Javier Cosnava", "Teresa Ortiz-Tagle"]`.

* **¿Por qué JSON?** Porque es un formato estándar: se lee con `json.loads` en
  Python, con `JSON.parse` en JavaScript, y con casi cualquier herramienta. Si en
  cambio se guardara `str(lista)`, Python escribiría `['Javier Cosnava', ...]` con
  comillas simples, que **no** es JSON válido.
* **`ensure_ascii=False`** deja las tildes legibles (`"Policíaco"`); sin eso se
  guardaría `"Polic\u00edaco"`.
* **¿Por qué ya no se usa `"; "`?** Porque un texto unido obliga a quien lo lea a
  saber qué separador se usó, y se rompe si algún nombre lo contiene. Una lista JSON
  no tiene esa ambigüedad.

```python
def a_lista(valor):
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
```

El camino inverso: celda del CSV → lista. Acepta el formato nuevo (JSON) y **también
el formato viejo** `"Intriga; Novela"`. Esa compatibilidad permite reutilizar un CSV
parcial generado con la versión 1 sin que el programa falle.

`unir()` se conserva para un solo caso: la **serie**, que sigue siendo texto porque
un libro pertenece a una sola serie.

### Comparación de textos **(v2)**

```python
def clave_comparacion(texto):
    texto = unicodedata.normalize("NFKD", unquote(texto or ""))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", texto.lower())

def portada_coincide(titulo, url_imagen):
    clave = clave_comparacion(titulo)[:20]
    return bool(clave) and clave in clave_comparacion(url_imagen)
```

Sirve para verificar que una imagen corresponde a un libro (paso 4). Para poder
comparar el título `"Maldito Mr. White"` con la dirección
`.../Maldito%20Mr%20White%20(20)/small.jpg`, las dos cosas se reducen a una "clave"
sin diferencias de forma:

| Paso | Qué hace | Ejemplo |
|---|---|---|
| `unquote` | decodifica la URL | `Maldito%20Mr` → `Maldito Mr` |
| `normalize("NFKD")` + `combining` | separa y quita las tildes | `Réquiem` → `Requiem` |
| `.lower()` | minúsculas | `Requiem` → `requiem` |
| `re.sub(r"[^a-z0-9]", "")` | quita espacios y signos | `maldito mr. white` → `malditomrwhite` |

Así `"malditomrwhite"` aparece dentro de `"...annypetersonmalditomrwhite20smalljpg"`
aunque el sitio haya quitado el punto de `Mr.`. Se comparan sólo los **primeros 20
caracteres** del título porque en los títulos largos la ruta de la imagen puede
venir abreviada.

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
La prueba con 10 libros confirmó que las fichas del sitio siguen ese patrón
(`https://ww3.lectulandia.co/book/el-novio/`).

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
<div id="sinopsis" class="realign"><span>Sinopsis</span> Renglón 1.<br>Renglón 2.</div>
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
porque cada `id` aparece una sola vez y cada `soup` se usa para un único libro.

### Autores y géneros como listas **(v2)**

Autores, géneros y serie tienen la misma estructura (varios `<a>` dentro de un `div`
con id), así que comparten una función, que ahora devuelve una **lista**:

```python
def _valores_enlazados(soup, id_div):
    div = _bloque(soup, id_div)
    if div is None:
        return []
    enlaces = [a.get_text() for a in div.select("a")]
    return lista_limpia(enlaces if enlaces else [div.get_text()])
```

```python
autores = _valores_enlazados(soup, "autor")         # ["Javier Cosnava", "Teresa Ortiz-Tagle"]
generos = _valores_enlazados(soup, "genero")        # ["Intriga", "Novela", "Policíaco"]
serie   = unir(_valores_enlazados(soup, "serie"))   # "Los casos de Héracles y Agatha"
```

* Si el bloque no existe, se devuelve `[]` (la representación de "ausente" para las
  listas), no `""`.
* Si el bloque existe pero el valor **no** está enlazado, se toma igual el texto plano
  como único elemento, en vez de perder el dato.
* `lista_limpia` descarta repetidos: si la ficha enlaza dos veces el mismo género,
  aparece una sola vez.
* La serie se une en un texto porque un libro pertenece a una sola serie.

### La sinopsis **(v2)**

Así se extraía en la versión 1:

```python
parrafos = [limpiar(p.get_text()) for p in div_sinopsis.find_all("p")]
sinopsis = " ".join(parrafos) if parrafos else limpiar(div_sinopsis.get_text())
```

Esto separaba bien los `<p>`, pero la prueba con 10 libros mostró que el sitio separa
los renglones con **`<br>`**, y en ese caso `get_text()` pega un renglón con el
siguiente (`hacerlo.<br>Respeto` → `"hacerlo.Respeto"`). La versión 2 usa una función
que respeta todos los cortes:

```python
def _texto_con_saltos(nodo):
    for br in nodo.find_all("br"):
        br.replace_with("\n")
    for bloque in nodo.find_all(["p", "div", "li", "blockquote",
                                 "h1", "h2", "h3", "h4", "h5", "h6"]):
        bloque.insert_before("\n")
        bloque.append("\n")
    return limpiar(nodo.get_text())
```

1. **Cada `<br>` se reemplaza por un salto de línea** real en el árbol.
2. **Se agrega un salto antes y después de cada bloque**. "Antes" también es
   necesario: sin eso, un texto suelto seguido de un `<p>` quedaría pegado
   (`"¿Será capaz?<p>Nuevo párrafo"` → `"¿Será capaz?Nuevo párrafo"`). Las propias
   pruebas del código detectaron ese caso.
3. **`limpiar()` reduce todos esos saltos a un único espacio**, así que no quedan
   saltos de línea en el CSV.

¿Por qué no usar simplemente `get_text(" ")`, que pone un espacio entre todos los
fragmentos? Porque separaría también las **etiquetas en línea**, como la cursiva:
`dijo <i>Poirot</i>, a las…` quedaría `"dijo Poirot , a las…"`, con un espacio antes
de la coma. La función propia sólo separa donde el HTML realmente corta el renglón.

Además, el rótulo `Sinopsis` (que viene en un `<span>` **sin** la clase `tagTitle`)
ahora se elimina explícitamente antes de extraer el texto:

```python
for rotulo in div_sinopsis.find_all(["span", "strong", "h2", "h3", "h4"]):
    if limpiar(rotulo.get_text()).lower().rstrip(":") == "sinopsis":
        rotulo.decompose()
```

### La portada **(v2)**

La versión 1 usaba un selector con respaldos cada vez más genéricos:

```python
img = soup.select_one("div#cover img, .thumbnail img, article img")   # versión 1
```

En la prueba real, 9 de 10 libros recibieron la portada de *Misteriosa noche de paz*:
`article img` encontraba primero una imagen de otro bloque de la página. La lección
es que **un respaldo genérico que puede coincidir con datos de otro registro es peor
que no tener respaldo**. La versión 2 verifica cada candidata contra el título:

```python
def _portada(soup, titulo):
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
```

* Primero se prueba **`og:image`**, la imagen que la página declara como propia para
  redes sociales; después, todas las `<img>` en orden.
* **Sólo se acepta una imagen si su dirección o su texto alternativo contiene el
  título** (`portada_coincide`, paso 2).
* `data-src` cubre las imágenes de carga diferida (*lazy loading*), que guardan la
  dirección real ahí en lugar de en `src`.
* Si ninguna coincide, el campo queda vacío. Como la portada es un campo opcional, un
  vacío es aceptable; una portada ajena, en cambio, contaminaría el recomendador.

### Planes B

Los dos campos críticos tienen una alternativa por si una ficha usa otro maquetado:

```python
if not titulo:                                  # plan B del título
    h1 = soup.find("h1")
    titulo = limpiar(h1.get_text()) if h1 else VALOR_FALTANTE

if not sinopsis:                                # plan B de la sinopsis
    meta = soup.find("meta", attrs={"name": "description"})
    sinopsis = limpiar(meta.get("content")) if meta else VALOR_FALTANTE
```

A diferencia de `article img`, estos respaldos son seguros: el primer `<h1>` y la
etiqueta `<meta name="description">` siempre describen **la página actual**, no otro
libro.

La función devuelve un diccionario con las claves exactas de `COLUMNAS`.

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
  saturado, reintentar de inmediato empeora las cosas.
* **Devolver `None` en vez de lanzar una excepción.** Quien llama decide qué hacer:
  contar el error y seguir con el próximo libro.

### Guardar sobre la marcha

```python
def guardar_fila(fila, ruta=CSV_PARCIAL):
    es_nuevo = not ruta.exists()
    fila = {k: (a_json(v) if isinstance(v, list) else v) for k, v in fila.items()}   # (v2)
    with open(ruta, "a", newline="", encoding="utf-8") as f:
        escritor = csv.DictWriter(f, fieldnames=COLUMNAS)
        if es_nuevo:
            escritor.writeheader()
        escritor.writerow(fila)
```

Se abre en modo `"a"` (*append*) y se escribe **cada libro apenas se obtiene**. Es lo
que pide la consigna con *"guarde los resultados incrementalmente"*: si Colab se
desconecta en el libro 87, los 86 anteriores ya están en disco.

* **(v2)** Antes de escribir, las listas se convierten a JSON con `a_json`. Sin esa
  línea, `csv.DictWriter` llamaría a `str()` sobre la lista y guardaría
  `['Intriga', 'Novela']`, con comillas simples, que no es JSON válido.
* `newline=""` es **obligatorio** al escribir CSV en Windows. Sin eso, aparece una
  línea en blanco entre cada fila.
* `encoding="utf-8"` asegura que las tildes y las eñes se guarden bien.

### Poder retomar

```python
def urls_ya_guardadas(ruta=CSV_PARCIAL):
    if not ruta.exists():
        return set()
    try:
        return set(pd.read_csv(ruta, dtype=str, keep_default_na=False)["url_libro"])
    except Exception:
        return set()
```

Al arrancar se relee el CSV parcial y se arma un **conjunto** con lo ya extraído. Esto
da dos cosas al mismo tiempo: **evitar duplicados** durante la corrida y **reanudar**
si se vuelve a ejecutar.

Se usa un `set` y no una lista porque preguntarle `if url in vistos` a un conjunto es
inmediato, mientras que a una lista la obliga a recorrerla entera cada vez.

**Consecuencia importante (v2):** como el programa retoma, **no vuelve a visitar**
los libros ya guardados. Si se corrige el código de extracción, esos libros conservan
los errores anteriores. Para eso existe `--reiniciar` / `REINICIAR = True` (paso 7).

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
(`n_pagina <= max_paginas`) evita un bucle infinito si algo sale mal.

**La pausa es aleatoria, no fija:** `random.uniform(1.5, 3.0)` cumple el requisito de
*"incorpore una pausa entre las páginas visitadas"*, reparte mejor la carga sobre el
servidor y genera un patrón de tráfico menos artificial. Con ~2,25 segundos
promedio, 100 libros llevan unos 4 minutos de pausas, más el tiempo de carga.

**Tres filtros descartan datos malos antes de escribirlos:** que `obtener_html`
haya devuelto `None`, que `parsear_ficha` haya lanzado una excepción, y que la
fila salga sin título. Los tres suman al contador `errores` y siguen adelante.

### La diferencia entre el notebook y el script

| | Notebook (Colab) | Script (`scraper.py`) |
|---|---|---|
| API | `playwright.async_api` | `playwright.sync_api` |
| Llamadas | `await page.goto(...)` | `page.goto(...)` |
| Pausa | `await asyncio.sleep(...)` | `time.sleep(...)` |
| Extra | `nest_asyncio.apply()` | `sys.stdout.reconfigure(errors="replace")` **(v2)** |

Colab **ya está corriendo un event loop**, y la API sincrónica de Playwright falla ahí
con `It looks like you are using Playwright Sync API inside the asyncio loop`.

**(v2)** El script agrega una línea propia: la consola de Windows usa la tabla de
caracteres cp1252, y si un título tuviera un carácter fuera de ella (por ejemplo, el
autor *Stanisław Lem*), el `print` del progreso lanzaría `UnicodeEncodeError` y
**cortaría la corrida**. Con `errors="replace"` ese carácter se muestra como `?` en
pantalla; el CSV no se ve afectado porque se escribe en UTF-8.

---

## Paso 7 — Ejecución

```python
if REINICIAR and CSV_PARCIAL.exists():        # (v2)
    CSV_PARCIAL.unlink()
    print(f"Se borró {CSV_PARCIAL.name}: la extracción empieza de cero.\n")

await scrapear()
```

Colab permite usar `await` directamente en una celda. Si la sesión se corta, se
vuelve a ejecutar esta misma celda y el proceso retoma gracias a `urls_ya_guardadas()`.

**(v2)** Con `REINICIAR = True` se borra antes el CSV parcial. En el script:

```bash
python src/scraper.py --reiniciar
```

---

## Paso 8 — Limpieza final con pandas

Cada fila ya se limpió al escribirla, pero se repasa el dataset completo: algunos
problemas **sólo se ven mirando el conjunto**, como un duplicado.

```python
df = pd.read_csv(CSV_PARCIAL, dtype=str, keep_default_na=False)          # (v2)
for col in COLUMNAS:
    if col not in df.columns:
        df[col] = VALOR_FALTANTE
df = df[COLUMNAS].fillna(VALOR_FALTANTE)

for col in COLUMNAS:
    df[col] = df[col].map(a_lista if col in COLUMNAS_LISTA else limpiar)  # (v2)

df = df[df["titulo"] != ""]
df = df[df["url_libro"].str.startswith("http")]
df = df.drop_duplicates(subset="url_libro", keep="first")
clave = df["titulo"] + "|" + df["autores"].map(a_json)                   # (v2)
df = df[~clave.duplicated(keep="first")]
df = df.head(N_LIBROS_OBJETIVO).reset_index(drop=True)
```

* **`dtype=str`** obliga a pandas a leer todo como texto. Sin esto, un título como
  `"1984"` se convertiría en el número 1984.
* **`keep_default_na=False`** **(v2)** hace que una celda vacía llegue como `""` y no
  como `NaN`. Además evita que pandas interprete como "dato faltante" textos como
  `"NA"`, `"None"` o `"null"`, que podrían ser títulos reales.
* **`.map(a_lista ...)`** **(v2)** convierte el JSON de `autores` y `generos` en
  listas de Python. El resto de las columnas pasa por `limpiar()`.
* **Dos deduplicaciones, no una.** La primera, por `url_libro`, es la que exige la
  consigna. La segunda, por `titulo` + `autores`, atrapa el mismo libro publicado
  bajo dos direcciones distintas.
* **(v2) Las listas no son "hasheables".** pandas detecta duplicados calculando un
  *hash* de cada valor, y las listas de Python no lo admiten porque se pueden
  modificar. `drop_duplicates(subset=["titulo", "autores"])` fallaría con
  `TypeError: unhashable type: 'list'`. Por eso se arma una clave de texto
  equivalente, uniendo el título con los autores serializados en JSON.

### Red de seguridad de portadas **(v2)**

```python
coincide = pd.Series([portada_coincide(t, u) for t, u in zip(df["titulo"], df["url_portada"])],
                     index=df.index, dtype=bool)
ajenas = (df["url_portada"] != "") & ~coincide
df.loc[ajenas, "url_portada"] = VALOR_FALTANTE
```

Se vuelve a verificar cada portada contra el título de su libro, y se vacían las que
no corresponden. Parece redundante con el paso 4, pero cumple dos funciones:

1. **Corrige los CSV parciales de la versión 1** sin volver a navegar. Aplicada sobre
   la prueba de 10 libros, vació las 8 portadas ajenas y conservó las 2 correctas.
2. Protege el dataset aunque en el futuro se cambie el código de extracción.

Se usa una lista por comprensión en lugar de `df.apply(..., axis=1)` porque, si el
DataFrame quedara vacío, `apply` devolvería un DataFrame en lugar de una Serie y la
negación `~` fallaría.

---

## Paso 9 — Controles mínimos **(v2)**

Los siete controles de la consigna, verificados por código en lugar de a ojo:

```python
en_rango = MIN_LIBROS <= len(df) <= MAX_LIBROS
controles = {
    "Sin duplicados por url_libro":              df["url_libro"].duplicated().sum() == 0,
    "Todos los registros tienen título":         (df["titulo"].str.len() > 0).all(),
    "Todas las URL son válidas":                 df["url_libro"].str.match(r"^https?://").all(),
    "La mayoría tiene sinopsis (>80%)":          (df["sinopsis"].str.len() > 0).mean() > 0.80,
    "Sin espacios ni saltos de línea sobrantes": not any(texto_sucio(v) for v in valores),
    "Campos ausentes representados igual ('' o [])": ausentes_ok,
    "Cantidad entre 50 y 100 libros":            None if (prueba and not en_rango) else en_rango,
}
```

### Qué cambió

**Modo prueba.** Cada control vale `True` (cumple), `False` (falla) o, sólo el de
cantidad, **`None` (omitido)**. Vale `None` cuando se trata de una prueba (menos de
50 libros pedidos) y la cantidad queda fuera del rango. Así se ve en pantalla:

```
OMIT.  Cantidad entre 50 y 100 libros

(Corrida de prueba con 10 libros: el control de cantidad se omite.
 Para la entrega, correr sin --n para extraer 100.)
```

Fuera del modo prueba el control sigue siendo estricto: una corrida de entrega con
menos de 50 libros **debe** fallar.

**La función devuelve qué controles fallan**, en lugar de un simple `True`/`False`:

```python
return [nombre for nombre, ok in controles.items() if ok is False]
```

Se usa `ok is False` y no `not ok` a propósito: `not None` también es verdadero, y el
control omitido se contaría como fallido. Con esa lista, el mensaje final nombra los
controles que no se cumplen, que era justamente lo que faltaba en la prueba.

**Los controles contemplan las listas.** El de espacios revisa también **cada
elemento** de cada lista:

```python
valores  = [v for c in columnas_texto for v in df[c]]
valores += [x for c in COLUMNAS_LISTA for lista in df[c] for x in lista]
```

y el de campos ausentes exige que las columnas de texto tengan sólo `str` y las de
lista sólo `list` (ni `None` ni `NaN`):

```python
ausentes_ok = (all(isinstance(v, str)  for c in columnas_texto for v in df[c])
               and all(isinstance(v, list) for c in COLUMNAS_LISTA for v in df[c]))
```

### Advertencias de calidad (nuevas)

```python
pegadas  = df["sinopsis"].str.count(PATRON_ORACION_PEGADA)
portadas = df.loc[df["url_portada"] != "", "url_portada"]
```

No bloquean la entrega, pero detectan los dos errores silenciosos de la versión 1:

* **Oraciones pegadas**: el patrón `[a-záéíóúüñ][.?!…][A-ZÁÉÍÓÚÜÑ¿¡0-9]` busca una
  minúscula, un signo de cierre y una mayúscula o número **sin espacio en el
  medio**, como `hacerlo.Respeto` o `navidad?19`. Se exige minúscula antes del signo
  para no confundir siglas como `EE.UU.`.
* **Portadas repetidas**: dos libros distintos con la misma portada son señal
  segura de que el selector tomó una imagen ajena.

Son advertencias y no controles porque pueden tener falsos positivos (un error de
tipeo en la sinopsis original del sitio también contaría como "oración pegada").

### El `assert` final

```python
fallidos = controles_minimos(df, prueba=MODO_PRUEBA)
assert not fallidos, f"No se cumplen estos controles mínimos: {fallidos}. Revisar antes de entregar."
```

Si un control falla, **la ejecución se detiene** en vez de exportar en silencio un
CSV defectuoso, y el mensaje dice cuál.

*(Nota: el control de espacios de la versión 1 usaba `df.map(...)`, que en pandas
anterior a 2.1 se llamaba `applymap`. La versión 2 recorre los valores directamente,
así que funciona con cualquier versión.)*

---

## Paso 10 — Exportación **(v2)**

```python
salida = df[COLUMNAS].copy()
for col in COLUMNAS_LISTA:
    salida[col] = salida[col].map(a_json)          # lista -> array JSON en la celda
salida.to_csv(CSV_FINAL, index=False, encoding="utf-8")

with open(JSON_FINAL, "w", encoding="utf-8") as f:
    json.dump(df[COLUMNAS].to_dict(orient="records"), f, ensure_ascii=False, indent=2)
```

Se generan dos archivos con el mismo contenido:

**`libros.csv`** — el entregable que pide la consigna. Las listas se guardan como
array JSON dentro de la celda. Así queda una fila (el módulo `csv` duplica las
comillas internas, que es la forma estándar de escaparlas):

```
Yo no soy Sherlock Holmes,"[""Javier Cosnava"", ""Teresa Ortiz-Tagle""]","[""Intriga"", ""Novela"", ""Policíaco""]",...
```

Se trabaja sobre una **copia** (`salida`) para que `df` conserve las listas y se pueda
seguir usando en la exploración del paso 11.

**`libros.json`** — el mismo dataset con los arrays **nativos**:

```json
{
  "titulo": "Yo no soy Sherlock Holmes",
  "autores": ["Javier Cosnava", "Teresa Ortiz-Tagle"],
  "generos": ["Intriga", "Novela", "Policíaco"],
  ...
}
```

Se escribe con `json.dump` y no con `df.to_json()`, porque pandas escapa las barras
de las direcciones (`"https:\/\/ww3.lectulandia.co\/book\/..."`). Es JSON válido pero
difícil de leer.

### Cómo leer el dataset en las próximas unidades

```python
import json
import pandas as pd

# Desde el CSV: `converters` aplica json.loads a cada celda de esas columnas
df = pd.read_csv("data/libros.csv", keep_default_na=False,
                 converters={"autores": json.loads, "generos": json.loads})

# Desde el JSON: las listas ya vienen como listas
df = pd.read_json("data/libros.json")
```

El notebook hace esa lectura de ida y vuelta como comprobación, y verifica que las
listas releídas sean idénticas a las originales.

---

## Paso 11 — Exploración del corpus

No lo pide la consigna, pero da material para el informe y sirve como control de
sanidad: si las sinopsis promediaran 3 palabras, algo estaría fallando en el parser.

```python
df["n_palabras_sinopsis"] = df["sinopsis"].str.split().str.len()

print(df["autores"].explode().value_counts().head(10))    # (v2)
print(df["generos"].explode().value_counts().head(10))    # (v2)
print((df["autores"].map(len) > 1).sum())                 # libros con varios autores
```

`explode()` convierte cada elemento de una lista en su propia fila. Con las listas,
esto sale directo: un libro con tres géneros aporta una unidad a cada uno. En la
versión 1 había que separar primero el texto con `.str.split("; ")`.

**(v2)** Las listas también corrigen una métrica: `Autores distintos` pasó de 10 a
**11** en la prueba, porque *Yo no soy Sherlock Holmes* tiene dos autores. Antes la
pareja `"Javier Cosnava; Teresa Ortiz-Tagle"` contaba como un único autor.

Para la completitud por campo se usa `len()`, que funciona igual para texto y para
listas: `len("") == 0` y `len([]) == 0`.

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
| Evita registros duplicados | conjunto `vistos` + doble deduplicación |
| Guarda los resultados incrementalmente | `guardar_fila()` en modo *append* |
| Genera el archivo final `libros.csv` | `salida.to_csv(CSV_FINAL)` (+ `libros.json`) |
| No descarga libros ni archivos | sólo se leen metadatos; ninguna descarga en el código |
