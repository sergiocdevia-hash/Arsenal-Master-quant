import os
import sys
import json
import requests
from datetime import datetime

# 1. CARGA SEGURA DE LA API KEY (Conexión directa con tus Secrets de GitHub)
API_KEY = os.getenv("API_FOOTBALL_KEY")

if not API_KEY:
    print("❌ ERROR: No se encontró la API_FOOTBALL_KEY en las variables de entorno.")
    sys.exit(1)

# 2. CONFIGURACIÓN DE CABECERAS OFICIALES DE API-FOOTBALL
# Se incluyen ambos formatos comunes para garantizar compatibilidad total
headers = {
    "x-rapidapi-key": API_KEY,
    "x-apisports-key": API_KEY,
    "x-rapidapi-host": "v3.football.api-sports.io"
}

# 3. OBTENCIÓN DE LA FECHA AUTOMÁTICA EN FORMATO YYYY-MM-DD (Año-Mes-Día)
fecha_hoy = datetime.now().strftime("%Y-%m-%d")
print(f"⚽ Consultando partidos para la fecha: {fecha_hoy}...")

# URL para traer todos los partidos del día
url = f"https://api-sports.io{fecha_hoy}"

# 4. PETICIÓN ROBUSTA CON CONTROL DE ERRORES
try:
    respuesta = requests.get(url, headers=headers, timeout=15)
    
    print(f"🔹 Código de respuesta del servidor: {respuesta.status_code}")
    
    if respuesta.status_code != 200:
        print(f"❌ Error del servidor de la API: {respuesta.text}")
        sys.exit(1)
        
    # Verificar si el contenido recibido está vacío antes de decodificar
    if not respuesta.text.strip():
        print("❌ El servidor de la API devolvió una respuesta vacía.")
        sys.exit(1)
        
    datos = respuesta.json()
    
    # Verificar si la API devolvió mensajes de error internos (Ej: Sin suscripción o límite)
    if "errors" in datos and datos["errors"]:
        print(f"⚠️ Alerta de la API: {json.dumps(datos['errors'])}")
        # Si es un error crítico de autenticación, detenemos el script de forma limpia
        if "token" in str(datos["errors"]).lower() or "key" in str(datos["errors"]).lower():
            sys.exit(1)

    # 5. CREACIÓN AUTOMÁTICA DE LA CARPETA Y GUARDADO DE PREDICCIONES
    # Creamos la carpeta de predicciones si no existe en el repositorio
    carpeta_destino = "predicciones"
    os.makedirs(carpeta_destino, exist_ok=True)
    
    # Nombre del archivo basado en la fecha de hoy
    nombre_archivo = os.path.join(carpeta_destino, f"partidos_{fecha_hoy}.json")
    
    # Guardamos los datos en formato JSON limpio y ordenado
    with open(nombre_archivo, "w", encoding="utf-8") as archivo:
        json.dump(datos, archivo, indent=4, ensure_ascii=False)
        
    print(f"✅ ¡Operación exitosa! Archivo guardado correctamente en: {nombre_archivo}")

except json.JSONDecodeError as e:
    print(f"❌ Error crítico de formato: La API no entregó un JSON válido. Detalle: {e}")
    print(f"Contenido crudo recibido: {respuesta.text[:300]}")
    sys.exit(1)
    
except requests.exceptions.RequestException as e:
    print(f"❌ Error de conexión de red al intentar acceder a la API: {e}")
    sys.exit(1)
