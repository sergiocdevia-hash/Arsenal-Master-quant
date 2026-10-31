import os
import sys
import json
import requests
from datetime import datetime

# 1. CARGA SEGURA DE LA API KEY desde los Secrets
API_KEY = os.getenv("API_FOOTBALL_KEY")

if not API_KEY:
    print("❌ ERROR: No se encontró la API_FOOTBALL_KEY en las variables de entorno.")
    sys.exit(1)

# 2. CONFIGURACIÓN DE CABECERAS OFICIALES
headers = {
    "x-rapidapi-key": API_KEY,
    "x-apisports-key": API_KEY,
    "x-rapidapi-host": "v3.football.api-sports.io"
}

# 3. OBTENCIÓN DE LA FECHA AUTOMÁTICA
fecha_hoy = datetime.now().strftime("%Y-%m-%d")
print(f"⚽ Consultando partidos para la fecha: {fecha_hoy}...")

# 4. URL CORREGIDA (Sin errores de unión de texto)
url = f"https://api-sports.io{fecha_hoy}"

# 5. PETICIÓN CON CONTROL DE ERRORES
try:
    respuesta = requests.get(url, headers=headers, timeout=15)
    
    print(f"🔹 Código de respuesta del servidor: {respuesta.status_code}")
    
    if respuesta.status_code != 200:
        print(f"❌ Error del servidor de la API: {respuesta.text}")
        sys.exit(1)
        
    if not respuesta.text.strip():
        print("❌ El servidor de la API devolvió una respuesta vacía.")
        sys.exit(1)
        
    datos = respuesta.json()
    
    if "errors" in datos and datos["errors"]:
        print(f"⚠️ Alerta de la API: {json.dumps(datos['errors'])}")
        if "token" in str(datos["errors"]).lower() or "key" in str(datos["errors"]).lower():
            sys.exit(1)

    # 6. CREACIÓN DE LA CARPETA Y GUARDADO
    carpeta_destino = "predicciones"
    os.makedirs(carpeta_destino, exist_ok=True)
    
    nombre_archivo = os.path.join(carpeta_destino, f"partidos_{fecha_hoy}.json")
    
    with open(nombre_archivo, "w", encoding="utf-8") as archivo:
        json.dump(datos, archivo, indent=4, ensure_ascii=False)
        
    print(f"✅ ¡Operación exitosa! Archivo guardado correctamente en: {nombre_archivo}")

except json.JSONDecodeError as e:
    print(f"❌ Error crítico de formato JSON: {e}")
    sys.exit(1)
    
except requests.exceptions.RequestException as e:
    print(f"❌ Error de conexión de red: {e}")
    sys.exit(1)
