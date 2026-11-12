import os
import sys
import json
import requests
from datetime import datetime

# 1. Carga segura del Token desde las Variables de Entorno
API_KEY = os.getenv("API_FOOTBALL_KEY")
if not API_KEY:
    print("❌ ERROR: No se encontró la API_FOOTBALL_KEY en las variables de entorno.")
    sys.exit(1)

# 2. Cabecera oficial DIRECTA de API-Sports (NO RapidAPI)
headers = {
    "x-apisports-key": API_KEY
}

# 3. Fecha automática del día actual (formato AAAA-MM-DD)
fecha_hoy = datetime.now().strftime("%Y-%m-%d")
print(f"⚽ Consultando partidos de fútbol para la fecha: {fecha_hoy}...")

dominio = "v3.football.api-sports.io"
url = f"https://{dominio}/fixtures?date={fecha_hoy}"

try:
    respuesta = requests.get(url, headers=headers, timeout=15)
    print(f"📡 Código de respuesta del servidor: {respuesta.status_code}")

    if respuesta.status_code != 200:
        print(f"❌ Error devuelto por la API: {respuesta.text}")
        sys.exit(1)

    datos = respuesta.json()

    # Verificar si la API devolvió algún error interno (ej. llave inválida)
    if datos.get("errors"):
        print(f"❌ La API reportó un problema: {datos['errors']}")
        sys.exit(1)

    # 5. Creación segura de directorios y guardado del archivo JSON
    carpeta_destino = "predicciones"
    os.makedirs(carpeta_destino, exist_ok=True)

    nombre_archivo = os.path.join(carpeta_destino, f"partidos_{fecha_hoy}.json")

    with open(nombre_archivo, "w", encoding="utf-8") as archivo:
        json.dump(datos, archivo, indent=4, ensure_ascii=False)

    print(f"✅ ¡Operación exitosa! Se encontraron {datos.get('results', 0)} partidos. Guardado en: {nombre_archivo}")

except Exception as e:
    print(f"❌ Error crítico durante la ejecución del proceso: {e}")
    sys.exit(1)
