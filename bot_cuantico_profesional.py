import os
import sys
import json
import math
import requests
from datetime import datetime

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
    print("ERROR: Faltan TELEGRAM_TOKEN o TELEGRAM_CHAT_ID")
    sys.exit(1)

def ajuste_dixon_coles(goles_l, goles_v, lambda_l, lambda_v, rho=-0.075):
    if goles_l == 0 and goles_v == 0:
        return 1 - (lambda_l * lambda_v * rho)
    elif goles_l == 1 and goles_v == 0:
        return 1 + (lambda_v * rho)
    elif goles_l == 0 and goles_v == 1:
        return 1 + (lambda_l * rho)
    elif goles_l == 1 and goles_v == 1:
        return 1 - rho
    return 1

def calcular_cuota_empate(lambda_l=1.35, lambda_v=1.15):
    prob_empate = 0.0
    for x in range(6):
        for y in range(6):
            p_x = (math.exp(-lambda_l) * (lambda_l ** x)) / math.factorial(x)
            p_y = (math.exp(-lambda_v) * (lambda_v ** y)) / math.factorial(y)
            if x == y:
                prob_empate += (p_x * p_y) * ajuste_dixon_coles(x, y, lambda_l, lambda_v)
    return round(1 / prob_empate, 2) if prob_empate > 0 else 3.20

def enviar_telegram(mensaje):
    host = "api.telegram.org"
    ruta = f"/bot{TELEGRAM_TOKEN}/sendMessage"
    url_final = "https://" + host + ruta
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": mensaje,
        "parse_mode": "Markdown"
    }
    try:
        resp = requests.post(url_final, json=payload, timeout=15)
        if resp.status_code == 200:
            print("EXITO: Boletin publicado en Flash futbol VIP")
        else:
            print(f"ERROR Telegram ({resp.status_code}): {resp.text}")
            sys.exit(1)
    except Exception as e:
        print(f"ERROR de conexion: {e}")
        sys.exit(1)

def ejecutar_sistema():
    fecha_hoy = datetime.now().strftime("%Y-%m-%d")
    archivo_partidos = os.path.join("predicciones", f"partidos_{fecha_hoy}.json")

    if not os.path.exists(archivo_partidos):
        print(f"ERROR: No existe {archivo_partidos}")
        sys.exit(1)

    with open(archivo_partidos, "r", encoding="utf-8") as f:
        datos = json.load(f)

    lista_partidos = datos.get("response", [])
    if not lista_partidos:
        print("AVISO: No hay partidos hoy.")
        return

    destacados = lista_partidos[:8]
    cuota_ref = calcular_cuota_empate()

    lineas = [
        "🔥 *FLASH FÚTBOL VIP - CARTELERA CUÁNTICA* ⚽",
        f"📅 *Fecha:* `{fecha_hoy}`",
        f"📊 *Partidos analizados hoy:* {len(lista_partidos)}",
        "━━━━━━━━━━━━━━━━━━━━\n"
    ]

    for item in destacados:
        liga = item["league"]["name"]
        pais = item["league"]["country"]
        local = item["teams"]["home"]["name"]
        visitante = item["teams"]["away"]["name"]
        hora_utc = item["fixture"]["date"][11:16]

        lineas.append(f"🏆 *{liga}* ({pais})")
        lineas.append(f"⚔️ {local} vs {visitante}")
        lineas.append(f"⏰ Hora UTC: `{hora_utc}` | 📐 Cuota Ref. X: `@{cuota_ref}`\n")

    lineas.append("━━━━━━━━━━━━━━━━━━━━")
    lineas.append("🚀 *¡VAMOS POR EL VERDE!* 💸")

    mensaje_final = "\n".join(lineas)
    enviar_telegram(mensaje_final)

if __name__ == "__main__":
    ejecutar_sistema()
