#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unidad 2 - TP2: diagnostico de la conexion a Supabase (Partes E y F)

Verifica lo que hace falta ANTES de escribir una sola tabla:

  1. que exista `.env` y traiga DATABASE_URL
  2. que la conexion funcione
  3. que la extension pgvector este instalada
  4. que la version de pgvector soporte indices HNSW (hace falta >= 0.5.0)

Nunca imprime la contrasena ni la cadena de conexion completa: todo lo que sale
por pantalla esta enmascarado, para que se pueda pegar el resultado donde sea
sin filtrar credenciales.

Uso:
    python "archivos del proyecto/probar_conexion.py"
"""

import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ARCHIVO_ENV = RAIZ / ".env"

VERSION_MINIMA_HNSW = (0, 5, 0)


# --------------------------------------------------------------------------- #
def enmascarar(texto):
    """Reemplaza la contrasena de cualquier URL de Postgres que aparezca.

    Se aplica tambien a los mensajes de error: psycopg a veces incluye la cadena
    de conexion en la excepcion, y esa salida se suele copiar y pegar.
    """
    texto = str(texto)
    texto = re.sub(r"(postgresql://[^:/@\s]+:)[^@\s]+(@)", r"\1***\2", texto)
    return texto


def abortar(mensaje, *sugerencias):
    print(f"\n[X] {enmascarar(mensaje)}")
    for s in sugerencias:
        print(f"    - {s}")
    sys.exit(1)


# --------------------------------------------------------------------------- #
def main():
    print("=" * 66)
    print("DIAGNOSTICO DE LA CONEXION A SUPABASE")
    print("=" * 66)

    # --- 1. credenciales ---------------------------------------------------- #
    if not ARCHIVO_ENV.exists():
        abortar(
            f"No existe {ARCHIVO_ENV.name} en la raiz del repositorio.",
            "Copia `.env.ejemplo` a `.env` y completa DATABASE_URL.",
            "La cadena esta en Supabase -> Connect -> Session pooler.",
        )

    try:
        from dotenv import dotenv_values
    except ImportError:
        abortar("Falta python-dotenv.", "pip install -r requirements.txt")

    url = (dotenv_values(ARCHIVO_ENV) or {}).get("DATABASE_URL", "").strip()
    if not url or "TU_PASSWORD" in url or "xxxxxxxx" in url:
        abortar(
            "DATABASE_URL esta vacia o todavia tiene los valores de la plantilla.",
            "Editar `.env` y pegar la cadena real del panel de Supabase.",
        )

    host = re.sub(r"^.*@", "", url).split("/")[0]
    print(f"[ok] .env encontrado   host: {host}")
    if ":6543" in host:
        print("     (aviso) puerto 6543 = transaction pooler: no admite sentencias")
        print("             preparadas. Se conecta con prepare_threshold=None.")

    # --- 2. conexion -------------------------------------------------------- #
    try:
        import psycopg
    except ImportError:
        abortar("Falta psycopg.", "pip install -r requirements.txt")

    kwargs = {"prepare_threshold": None} if ":6543" in host else {}
    try:
        conexion = psycopg.connect(url, connect_timeout=15, **kwargs)
    except Exception as e:
        texto = str(e).lower()
        pistas = []
        if "unreachable" in texto or "could not translate" in texto:
            pistas = [
                "La conexion directa (db.<ref>.supabase.co) es solo IPv6 en el plan gratuito.",
                "Usar la cadena del SESSION POOLER (aws-0-<region>.pooler.supabase.com:5432).",
            ]
        elif "password" in texto or "authentication" in texto:
            pistas = [
                "Contrasena incorrecta. Supabase -> Settings -> Database -> Reset database password.",
                "Si la contrasena tiene @ : / o #, hay que codificarla en la URL.",
            ]
        elif "timeout" in texto:
            pistas = [
                "El proyecto gratuito se pausa a los 7 dias sin actividad.",
                "Reactivarlo desde el panel (tarda ~30 segundos) y reintentar.",
            ]
        abortar(f"No se pudo conectar: {e}", *pistas)

    print("[ok] conexion establecida")

    # --- 3. pgvector -------------------------------------------------------- #
    with conexion, conexion.cursor() as cur:
        cur.execute("SELECT current_database(), version()")
        base, version_pg = cur.fetchone()
        print(f"[ok] base: {base}")
        print(f"     {version_pg.split(',')[0]}")

        cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
        cur.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
        fila = cur.fetchone()
        if not fila:
            abortar(
                "La extension pgvector no quedo instalada.",
                "Supabase -> Database -> Extensions -> habilitar `vector`.",
            )

        version_vector = fila[0]
        print(f"[ok] pgvector {version_vector}")

        partes = tuple(int(x) for x in re.findall(r"\d+", version_vector)[:3])
        if partes < VERSION_MINIMA_HNSW:
            abortar(
                f"pgvector {version_vector} no soporta indices HNSW "
                f"(hace falta >= {'.'.join(map(str, VERSION_MINIMA_HNSW))}).",
                "La consigna pide HNSW. Actualizar la extension desde el panel.",
            )
        print("[ok] soporta indices HNSW")

        # Que operadores/opclases hay disponibles: la consigna evalua que la
        # opclass del indice corresponda al operador de distancia que se usa.
        cur.execute("""
            SELECT opcname FROM pg_opclass
            WHERE opcname LIKE 'vector_%' ORDER BY opcname
        """)
        print(f"     opclases: {', '.join(r[0] for r in cur.fetchall())}")

        cur.execute("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public' ORDER BY table_name
        """)
        tablas = [r[0] for r in cur.fetchall()]
        print(f"[ok] tablas existentes en `public`: {tablas if tablas else '(ninguna)'}")

    print("\n" + "=" * 66)
    print("TODO LISTO. Se puede correr el Bloque 9 del notebook.")
    print("=" * 66)


if __name__ == "__main__":
    main()
