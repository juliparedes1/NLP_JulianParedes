# Diseño de la extracción — Parte 1

**Unidad 1 — Extracción y procesamiento de texto**
Extracción de metadatos y sinopsis con Playwright y BeautifulSoup

---

## 1. Categoría seleccionada

| | |
|---|---|
| **Nombre de la categoría** | Thriller / Intriga |
| **URL de la categoría** | https://ww3.lectulandia.co/genero/intriga/ |
| **Cantidad de libros a extraer** | 100 |
| **Criterio de selección de páginas** | Se recorren las páginas del listado en el orden en que las presenta el sitio (de la más reciente a la más antigua), empezando por la página 1 y avanzando por la paginación `/page/N/` hasta completar los 100 libros. No se aplica ningún filtro adicional: se toman los primeros 100 títulos de la categoría, sin descartar por autor, serie ni año. |

> **Nota sobre la cantidad.** La presentación general del trabajo plantea entre 100 y
> 200 libros, mientras que la Parte 2 (implementación) exige obtener entre 50 y 100
> fichas y los controles mínimos verifican ese rango. Se fijó **100** por ser el único
> valor que satisface las dos condiciones a la vez. El parámetro
> `N_LIBROS_OBJETIVO` está centralizado en la configuración, de modo que ampliar el
> corpus más adelante requiere cambiar un solo número.

---

## 2. Datos que se extraerán

| Campo | Descripción | Tipo | Obligatorio |
|---|---|---|---|
| `titulo` | Título del libro | texto | Sí |
| `autores` | Autor o autores | **lista** (array) | No |
| `generos` | Género o géneros | **lista** (array) | No |
| `serie` | Serie a la que pertenece, si corresponde | texto | No |
| `sinopsis` | Texto completo de la sinopsis | texto | No |
| `url_libro` | Dirección de la ficha | URL | Sí (clave) |
| `categoria_origen` | Categoría seleccionada por el grupo | texto | Sí |
| `fecha_extraccion` | Fecha en que se obtuvo el registro (ISO `AAAA-MM-DD`) | fecha | Sí |
| `url_portada` | Dirección de la imagen de portada (**campo opcional**) | URL | No |

**Convenciones del dataset**

* Los campos con varios valores (`autores`, `generos`) son **listas**. En
  `libros.csv` cada celda guarda un **array JSON**, por ejemplo
  `["Javier Cosnava", "Teresa Ortiz-Tagle"]`; en `libros.json` se guardan como arrays
  nativos. Se eligió JSON (y no un texto unido por `"; "`) porque es un formato
  estándar, sin ambigüedad sobre el separador, que se lee directamente con
  `json.loads`.
* Los campos ausentes se representan **siempre** igual: la cadena vacía (`""`) en
  los campos de texto y la lista vacía (`[]`) en los de lista. Nunca `None`, `NaN`,
  `"N/A"` ni `"-"`.
* Todo el texto se normaliza: sin saltos de línea, sin espacios dobles y sin espacios
  al principio ni al final.
* `url_libro` es la **clave** del dataset: no puede haber dos registros con el mismo valor.

> **Alcance.** Sólo se extraen metadatos y sinopsis públicas. **No se descargan
> libros, ni archivos EPUB, PDF u otros contenidos**, ni se registran enlaces de
> descarga, conforme a lo indicado en la consigna.

---

## 3. Localización de los datos

Los selectores se obtuvieron inspeccionando el HTML de las fichas con las
herramientas de desarrollo del navegador (F12 → *Inspeccionar*).

### 3.1 Página de listado de la categoría

| Dato | Tipo de página | Etiqueta HTML | Selector propuesto |
|---|---|---|---|
| URL de cada ficha | Listado de categoría | `<a href="/book/el-reclutador/">` | `a[href]` filtrando las rutas que cumplen `^/(?:book\|libro)/[^/]+/?$` |
| Página siguiente | Listado de categoría | paginación del sitio | Se construye la URL directamente: `.../genero/intriga/page/N/` |

**Criterio.** Los enlaces a las fichas no se buscan por su clase CSS, sino por **la
forma de la ruta**. Las clases del maquetado cambian con cada rediseño del sitio; la
estructura de las direcciones es mucho más estable. Cada enlace se normaliza con
`urljoin()` (para volverlo absoluto) y se le quitan la *query string* y el fragmento,
de modo que `/book/x/?utm=1`, `/book/x/#comentarios` y `/book/x/` cuenten como un
único libro.

### 3.2 Ficha individual del libro

| Dato | Tipo de página | Etiqueta HTML | Selector propuesto |
|---|---|---|---|
| **Título** | Ficha individual | `<div id="title"><h1>TÍTULO</h1></div>` | `div#title` → `.get_text()` · *plan B:* primer `h1` de la página |
| **Autores** | Ficha individual | `<div id="autor" class="realign"><span class="tagTitle">Autor: </span><a class="dinSource" href="/autor/david-mccloskey/" rel="tag">AUTOR</a></div>` | `div#autor a` → **lista** con el texto de cada `<a>`, sin repetidos |
| **Géneros** | Ficha individual | `<div id="genero" class="realign"><span class="tagTitle">Generos: </span><a class="dinSource" href="/genero/intriga/" rel="tag">Intriga</a> &nbsp; <a class="dinSource" href="/genero/novela/" rel="tag">Novela</a></div>` | `div#genero a` → **lista** con el texto de cada `<a>`, sin repetidos |
| **Serie** | Ficha individual | `<div id="serie" class="realign">…</div>` (no está en todas las fichas) | `div#serie a` → texto; si no hay enlaces, texto plano del `div`; si el `div` no existe, `""` |
| **Sinopsis** | Ficha individual | `<div id="sinopsis" class="realign"><span>Sinopsis</span> Renglón 1.<br>Renglón 2.</div>` | `div#sinopsis` → texto completo, convirtiendo cada `<br>` y cada bloque (`<p>`, `<div>`…) en un espacio · *plan B:* `meta[name="description"]` |
| **Portada** *(opcional)* | Ficha individual | `<meta property="og:image">` o `<img src="…">` | `meta[property="og:image"]` y luego cada `img`: se acepta **sólo** la imagen cuya dirección o `alt` contiene el título del libro; si ninguna coincide, `""` |

**Tratamiento del rótulo.** Los bloques `#autor` y `#genero` incluyen una etiqueta
descriptiva dentro de `<span class="tagTitle">` (`"Autor: "`, `"Generos: "`). Si se
leyera el `div` completo, ese rótulo quedaría dentro del dato
(`"Autor: David McCloskey"`). Antes de extraer el texto se elimina ese `span` con
`decompose()`. Es seguro porque cada `id` aparece una sola vez por página.

**Planes B.** Los dos campos críticos tienen una alternativa por si alguna ficha usa
otro maquetado: el título cae en el primer `<h1>` de la página, y la sinopsis en la
etiqueta `<meta name="description">`. Así una ficha con estructura distinta se
recupera igual en lugar de perderse.

### 3.3 Ajustes tras la prueba parcial (versión 2)

Una prueba con 10 libros mostró dos problemas de localización que obligaron a
corregir los selectores propuestos originalmente:

| Dato | Selector original | Problema observado | Selector corregido |
|---|---|---|---|
| Portada | `div#cover img, .thumbnail img, article img` | 9 de 10 libros recibieron la portada de otro libro: `article img` coincidía primero con una imagen de otro bloque de la página. | Se valida cada imagen contra el título del libro (ver tabla 3.2). |
| Sinopsis | `div#sinopsis p`, unidos con espacios | 28 oraciones pegadas en 8 de 10 libros (`"hacerlo.Respeto"`): el sitio separa los renglones con `<br>`, no con `<p>`. | Texto completo del `div`, convirtiendo `<br>` y bloques en espacios. |

**Lección de diseño:** un selector de respaldo genérico que puede coincidir con
datos de **otro** registro es peor que no tener respaldo, porque el error no se ve.
Los planes B del título y la sinopsis siguen siendo seguros: el primer `<h1>` y la
etiqueta `meta description` siempre describen la página actual.

---

## 4. Estrategia de extracción

1. **Abrir la página de la categoría con Playwright.** Se inicia un navegador
   Chromium en modo *headless* (sin ventana) y se navega a la URL de la categoría.
   Se usa un navegador real, y no una simple petición HTTP, porque el sitio arma
   parte de su contenido con JavaScript.
2. **Recorrer las páginas necesarias.** Se avanza por la paginación
   (`/page/2/`, `/page/3/`, …) hasta reunir 100 libros, con un tope de 25 páginas
   como red de seguridad contra bucles infinitos.
3. **Obtener el HTML mediante Playwright.** Con `wait_until="domcontentloaded"`, que
   espera a que el DOM esté armado sin esperar imágenes ni publicidad. Ante un fallo
   (timeout, corte de red, error del servidor) se **reintenta hasta 3 veces con
   espera creciente** de 2, 4 y 6 segundos.
4. **Analizar ese HTML con BeautifulSoup**, usando `lxml` como analizador.
5. **Extraer las URL de las fichas**, filtrando por la forma de la ruta, volviéndolas
   absolutas y eliminando repetidos.
6. **Visitar cada ficha con Playwright**, con una **pausa aleatoria de entre 1,5 y 3
   segundos** antes de cada visita, para no sobrecargar el servidor.
7. **Extraer los metadatos y la sinopsis con BeautifulSoup**, según los selectores
   de la sección 3.
8. **Limpiar y validar los datos.** Se colapsan espacios y saltos de línea, se
   convierten los espacios duros (`&nbsp;`) en espacios normales, se descartan las
   fichas que quedaron sin título y se vacía toda portada que no corresponda a su
   libro.
9. **Eliminar libros duplicados.** Durante la corrida, mediante un conjunto de URL ya
   visitadas; al final, con una doble deduplicación por `url_libro` y por la
   combinación `titulo` + `autores`.
10. **Guardar el resultado en un archivo CSV.** La escritura es **incremental**: cada
    libro se guarda apenas se obtiene, de modo que una desconexión no haga perder el
    trabajo ya hecho. Al terminar se arma el `data/libros.csv` definitivo (con los
    campos de lista como arrays JSON) y una copia `data/libros.json` con arrays
    nativos.

**Corridas de prueba.** Para validar los selectores antes de la corrida completa se
puede extraer una cantidad menor (por ejemplo 10 libros). En ese caso el control de
cantidad se informa como omitido en lugar de fallar. Como el programa retoma desde el
CSV parcial, después de corregir el código hay que volver a extraer desde cero
(`--reiniciar`).

### Manejo de errores

| Situación | Respuesta del programa |
|---|---|
| Timeout o error de red al cargar una página | Reintenta 3 veces con espera creciente; si falla, la saltea y sigue |
| Página de listado inaccesible | Suma un error y pasa a la página siguiente |
| Falla el análisis de una ficha | Registra el error, descarta esa ficha y continúa |
| Ficha sin título | Se descarta el registro (no cumple el mínimo exigido) |
| Categoría con menos libros de los esperados | El ciclo corta al no encontrar más fichas |
| Sesión de Colab interrumpida | Al reejecutar, retoma desde el CSV parcial |

Ninguna de estas situaciones detiene la ejecución completa: se contabilizan y se
informan al final.

---

## 5. Controles mínimos previstos

Se verifican por código antes de exportar el archivo final. Si alguno falla, la
ejecución se detiene en lugar de generar un CSV defectuoso.

| Control | Cómo se verifica |
|---|---|
| No existen registros duplicados por `url_libro` | `df["url_libro"].duplicated().sum() == 0` |
| Todos los registros tienen título | `(df["titulo"].str.len() > 0).all()` |
| Todos los registros tienen una URL válida | `df["url_libro"].str.match(r"^https?://").all()` |
| La mayoría de los registros tiene sinopsis | proporción de sinopsis no vacías `> 80 %` |
| Se eliminaron espacios y saltos de línea innecesarios | ninguna celda (ni ningún elemento de las listas) con `\n`, espacios dobles ni espacios en los extremos |
| Los campos ausentes se representan de manera consistente | los campos de texto contienen sólo `str` (ausente = `""`) y los de lista sólo `list` (ausente = `[]`) |
| La cantidad obtenida está entre 50 y 100 libros | `50 <= len(df) <= 100` (se omite en corridas de prueba de menos de 50 libros) |

Si algún control falla, el programa indica **por nombre** cuál no se cumple.

**Advertencias de calidad** (no bloquean la entrega, pero detectan errores que los
controles mínimos no ven):

| Advertencia | Cómo se verifica |
|---|---|
| Sinopsis sin oraciones pegadas | ninguna coincidencia del patrón minúscula + `.?!…` + mayúscula/número sin espacio (`"hacerlo.Respeto"`) |
| Portadas sin repetir entre libros | ninguna `url_portada` repetida entre libros distintos |

---

## 6. Herramientas

| Herramienta | Rol |
|---|---|
| **Playwright** | Abre Chromium, recorre las páginas de la categoría y visita las fichas. Ejecuta el JavaScript del sitio y devuelve el HTML renderizado. |
| **BeautifulSoup** (+ `lxml`) | Analiza ese HTML y localiza los datos mediante selectores CSS. |
| **pandas** | Organiza, limpia, deduplica, valida y exporta el dataset. |
| **Git** | Registra el trabajo en el repositorio personal de cada integrante. |
