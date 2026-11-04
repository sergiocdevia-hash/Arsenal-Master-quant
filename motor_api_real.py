import os
import sys
import json
import requests
from datetime import datetime

# 1. Carga segura del Token desde las Variables de Entorno (Secrets en la nube)
API_KEY = os.getenv("API_FOOTBALL_KEY")
if not API_KEY:
    print("❌ ERROR: No se encontró la API_FOOTBALL_KEY en las variables de entorno.")
    sys.exit(1)

# 2. Cabeceras oficiales completas para API-Sports / API-Football
headers = {
    "x-rapidapi-key": API_KEY,
    "x-rapidapi-host": "v3.football.api-sports.io"
}

# 3. Fecha automática del día actual (Formato: AAAA-MM-DD)
fecha_hoy = datetime.now().strftime("%Y-%m-%d")
print(f"⚽ Consultando partidos para la fecha: {fecha_hoy}...")

# 4. URL oficial corregida con endpoint de fixtures y parámetro de fecha
url = f"https://api-sports.io{fecha_hoy}"

try:
    # Realiza la petición con un tiempo de espera límite de 15 segundos
    respuesta = requests.get(url, headers=headers, timeout=15)
    print(f"🔷 Código de respuesta del servidor: {respuesta.status_code}")

    if respuesta.status_code != 200:
        print(f"❌ Error API: {respuesta.text}")
        sys.exit(1)

    datos = respuesta.json()

    # 5. Estructuración y guardado del archivo de resultados
    carpeta_destino = "predicciones"
    os.makedirs(carpeta_destino, exist_ok=True)

    nombre_archivo = os.path.join(carpeta_destino, f"partidos_{fecha_hoy}.json")
    with open(nombre_archivo, "w", encoding="utf-8") as archivo:
        json.dump(datos, archivo, indent=4, ensure_ascii=False)

    print(f"✅ ¡Operación exitosa! Archivo guardado en: {nombre_archivo}")

except Exception as e:
    print(f"❌ Error crítico en el proceso: {e}")
    sys.exit(1)
