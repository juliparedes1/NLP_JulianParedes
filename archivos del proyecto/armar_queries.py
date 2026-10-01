# -*- coding: utf-8 -*-
"""Construye data/queries.json a partir de indices del corpus."""
import json, sys
from pathlib import Path
import pandas as pd

RAIZ = Path(r"C:\Users\PC\Desktop\proyecto nlp\NLP_JulianParedes")
df = pd.read_csv(RAIZ / "data/libros.csv", keep_default_na=False,
                 converters={"generos": json.loads})

# (id, consulta, [indices relevantes], tipo, nota)
BORRADOR = [
 ("q01", "un detective investiga un asesinato en una casa de campo inglesa llena de sospechosos",
  [55, 126, 96, 0], "lexica",
  "Caso clasico de mansion cerrada. Comparte vocabulario directo con las sinopsis."),

 ("q02", "Hércules Poirot y Agatha Christie resuelven un caso",
  [0, 1, 83], "lexica",
  "Consulta por nombres propios: el mejor escenario posible para TF-IDF."),

 ("q03", "una pareja de aristócratas ingleses investiga crímenes en el Londres de los años veinte",
  [5, 22, 19, 30, 37, 49], "mixta",
  "Serie Dora & Rex. Sirve para ver si los modelos agrupan una saga."),

 ("q04", "un chico desaparece y el caso se reabre décadas después",
  [12, 14, 46, 143], "lexica",
  "Desaparicion antigua reabierta en el presente."),

 ("q05", "un espía se infiltra en una organización para descubrir a un traidor",
  [88, 64, 130, 91, 37], "mixta",
  "Espionaje. Ojo: q03 tambien incluye el 37, es un solapamiento deliberado."),

 ("q06", "una forense examina un cadáver en la sala de autopsias",
  [17, 142, 46, 106], "lexica",
  "Vocabulario tecnico forense."),

 ("q07", "un crimen ocurrido en las Islas Canarias",
  [72, 123, 95, 131, 132], "lexica",
  "Consulta geografica: el lugar esta escrito en la sinopsis."),

 ("q08", "una escritora famosa en el centro de un misterio",
  [8, 10, 110, 137], "mixta",
  "Mundo literario. Parte del vocabulario coincide, parte no."),

 ("q09", "un individuo que elige a sus presas y repite el mismo patrón",
  [6, 86, 26, 35, 136], "semantica",
  "SIN SOLAPAMIENTO: describe un asesino en serie sin usar 'asesino', "
  "'serie', 'victima' ni 'matar'. TF-IDF no puede ganar por construccion."),

 ("q10", "una persona lastimada se cobra aquello que le arrebataron",
  [133, 141, 139, 136], "semantica",
  "SIN SOLAPAMIENTO (0/5 tokens): describe venganza sin usar 'venganza', "
  "'vengar' ni 'matar'. Redactada con ortografia correcta: el cero es "
  "distancia semantica real, no un error de tipeo."),

 ("q11", "objetos de gran valor que cambian de manos por medios turbios",
  [50, 98, 24, 117], "semantica",
  "SIN SOLAPAMIENTO: describe robo sin usar 'robo', 'ladron' ni 'robado'."),

 ("q12", "un incendio destruye un edificio y entre los restos aparece un cuerpo",
  [32, 115, 146, 42], "lexica",
  "Fuego + hallazgo de cadaver."),
]

salida = []
for qid, consulta, idxs, tipo, nota in BORRADOR:
    for i in idxs:
        if i >= len(df):
            sys.exit(f"{qid}: indice {i} fuera de rango")
    salida.append({
        "id": qid,
        "consulta": consulta,
        "relevantes": [df.url_libro[i] for i in idxs],
        "titulos_relevantes": [df.titulo[i] for i in idxs],   # solo para revisar a ojo
        "tipo": tipo,
        "nota": nota,
    })

destino = RAIZ / "data/queries.json"
destino.write_text(json.dumps(salida, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"Escrito: {destino}  ({len(salida)} consultas, "
      f"{sum(len(q['relevantes']) for q in salida)} juicios de relevancia)")
