# Unidad 1 — Extracción y procesamiento de texto

Extracción de metadatos y sinopsis de libros con **Playwright** y **BeautifulSoup**,
para construir un corpus que se usará luego en tareas de procesamiento de texto y en
un recomendador de libros.

---

## Integrantes del grupo

| Integrante | Rol / aporte |
|---|---|
| Gimbatti Tomas| |
| Longo Valentino| |
| Nasini Rodrigo| |
| Paredes Julian| |

---

## Categoría seleccionada

| | |
|---|---|
| **Categoría** | Thriller / Intriga |
| **URL** | https://ww3.lectulandia.co/genero/intriga/ |
| **Cantidad de libros extraídos** | 100 |
| **Criterio de selección** | Los primeros 100 libros del listado de la categoría, recorriendo la paginación en el orden que presenta el sitio |
| **Fecha de extracción** | *(completar tras la corrida)* |

---

## Estructura del repositorio

```
README.md
requirements.txt
src/
  scraper.py                          # versión de línea de comandos
  scraper_lectulandia_colab.ipynb     # versión para Google Colab
data/
  libros.csv                          # dataset final (entregable)
  libros_parcial.csv                  # guardado incremental (intermedio)
docs/
  diseno_extraccion.md                # Parte 1: análisis previo
  explicacion_codigo.md               # explicación paso a paso del código
```

---

## Campos del dataset

| Campo | Descripción |
|---|---|
| `titulo` | Título del libro |
| `autores` | Autor o autores, separados por `; ` |
| `generos` | Género o géneros, separados por `; ` |
| `serie` | Serie a la que pertenece, si corresponde |
| `sinopsis` | Texto completo de la sinopsis |
| `url_libro` | Dirección de la ficha (clave del dataset) |
| `categoria_origen` | Categoría seleccionada por el grupo |
| `fecha_extraccion` | Fecha en que se obtuvo el registro |
| `url_portada` | Dirección de la imagen de portada (campo opcional) |

Los campos ausentes se representan siempre con la cadena vacía.

---

## Instrucciones de instalación

### Opción A — Google Colab (recomendada)

No requiere instalar nada en la computadora.

1. Abrir [Google Colab](https://colab.research.google.com/).
2. `Archivo → Subir cuaderno` y elegir `src/scraper_lectulandia_colab.ipynb`.
3. La primera celda instala todas las dependencias dentro de la sesión.

### Opción B — Instalación local

Requiere **Python 3.9 o superior**.

```bash
python -m venv .venv
```

Activar el entorno virtual — en Windows:

```bash
.venv\Scripts\activate
```

En Linux o macOS:

```bash
source .venv/bin/activate
```

Instalar las dependencias de Python:

```bash
pip install -r requirements.txt
```

Descargar el navegador que usa Playwright (paso aparte, obligatorio):

```bash
playwright install chromium
```

---

## Instrucciones para ejecutar el programa

### En Colab

`Entorno de ejecución → Ejecutar todo`. El notebook instala las dependencias,
recorre la categoría, arma el dataset, verifica los controles mínimos y descarga
`libros.csv`.

La corrida completa tarda entre **6 y 10 minutos** para 100 libros, por las pausas
entre visitas. Si la sesión se interrumpe, basta con volver a ejecutar la celda de
scraping: el proceso retoma desde lo ya guardado en `data/libros_parcial.csv`.

### Desde la línea de comandos

Extraer 100 libros (valor por defecto):

```bash
python src/scraper.py
```

Extraer otra cantidad:

```bash
python src/scraper.py --n 60
```

Ver el navegador mientras trabaja (útil para depurar los selectores):

```bash
python src/scraper.py --no-headless
```

Rearmar `libros.csv` desde el CSV parcial, sin volver a navegar:

```bash
python src/scraper.py --solo-dataset
```

---

## Controles mínimos

El programa verifica automáticamente, antes de exportar:

- [x] No existen registros duplicados por `url_libro`
- [x] Todos los registros tienen título
- [x] Todos los registros tienen una URL válida
- [x] Más del 80 % de los registros tiene sinopsis
- [x] No quedan espacios ni saltos de línea innecesarios
- [x] Los campos ausentes se representan de manera consistente (siempre `""`)
- [x] La cantidad obtenida está entre 50 y 100 libros

Si alguno falla, la ejecución se detiene en lugar de generar un CSV defectuoso.

---

## Principales dificultades encontradas

1. **Playwright y asyncio dentro de Colab.** Colab ya tiene un *event loop* de
   asyncio en marcha, así que la API sincrónica de Playwright falla con
   `It looks like you are using Playwright Sync API inside the asyncio loop`. Se
   resolvió usando la API asincrónica más `nest_asyncio.apply()` en el notebook, y
   dejando la versión sincrónica para el script de línea de comandos.

2. **El navegador se instala aparte de la librería.** `pip install playwright` sólo
   instala el paquete de Python; sin `playwright install chromium` el programa falla
   con `Executable doesn't exist`. En Colab hace falta además `playwright
   install-deps` para las bibliotecas del sistema.

3. **Los rótulos venían pegados a los datos.** El sitio guarda el rótulo
   (`"Autor: "`, `"Generos: "`) dentro del mismo `<div>` que el dato, de modo que un
   `.get_text()` directo devolvía `"Autor: David McCloskey"`. Se resolvió eliminando
   el `<span class="tagTitle">` con `decompose()` antes de leer el texto.

4. **Selectores frágiles en el listado.** Buscar los enlaces a las fichas por su
   clase CSS ataba el scraper al maquetado del momento. Se pasó a filtrarlos por la
   forma de la ruta (`/book/<slug>/`), que es mucho más estable.

5. **URL que parecían distintas y eran el mismo libro.** Las variantes con
   *query string* (`?utm=…`) y con fragmento (`#comentarios`) generaban duplicados.
   Se normaliza cada enlace antes de compararlo.

6. **Párrafos de la sinopsis pegados entre sí.** Un `get_text()` sobre el bloque
   completo unía los párrafos sin separación (`"...del primero.Empieza el
   segundo..."`). Se recorren los `<p>` uno por uno y se unen con un espacio.

7. **Espacios duros y saltos de línea del maquetado.** Las sinopsis llegaban con
   `&nbsp;` (`\xa0`) y saltos de línea que rompían el CSV. Se normaliza todo el texto
   antes de escribirlo.

8. **Riesgo de perder una corrida larga.** Extraer 100 libros lleva varios minutos y
   Colab puede desconectarse. Se implementó el guardado incremental más la
   reanudación automática a partir del CSV parcial.

---

## Alcance y consideraciones

Este trabajo se limita a **metadatos y sinopsis públicas**. **No se descargan libros,
ni archivos EPUB, PDF u otros contenidos**, ni se registran enlaces de descarga, tal
como indica la consigna. Se incorpora una pausa aleatoria entre visitas para no
sobrecargar el servidor del sitio.
