import os
import requests

TOKEN_TELEGRAM = "9254580288:AAHHJNrOghUXXuAxmoEWACRzLSWidKhasJA"
CHAT_ID_DESTINO = "https://t.me"

def enviar_alerta_telegram(mensaje):
    url = f"https://telegram.org{TOKEN_TELEGRAM}/sendMessage"
    payload = {
        "chat_id": CHAT_ID_DESTINO,
        "text": mensaje,
        "parse_mode": "Markdown"
    }
    try:
        respuesta = requests.post(url, json=payload)
        if respuesta.status_code == 200:
            print("[INFO] Alerta enviada a Telegram con éxito.")
        else:
            print(f"[ERROR] Código de estado: {respuesta.status_code} - {respuesta.text}")
    except Exception as e:
        print(f"[ERROR] Falla de conexión a internet: {e}")

def analizar_logs_instantaneo(archivo_logs):
    print("🤖 [SISTEMA] Analizando registros del servidor de forma instantánea...")
    
    with open(archivo_logs, "w") as f:
        f.write("ERROR: Failed login attempt from IP 192.168.1.99\n")
        f.write("CRITICAL: SELECT * FROM users WHERE username = 'admin' UNION SELECT null, null--\n")

    with open(archivo_logs, "r") as f:
        for linea in f:
            if "failed login" in linea.lower() or "password incorrect" in linea.lower():
                alerta = (
                    "⚠️ *ALERTAS DE CIBERSEGURIDAD*\n"
                    "🚨 *Intento de Ataque detectado en vivo*\n"
                    f"📝 *Detalle:* Acceso denegado (Fuerza Bruta)\n"
                    f"🔍 *Registro:* `{linea.strip()}`"
                )
                enviar_alerta_telegram(alerta)
                
            if "select" in linea.lower() and "union" in linea.lower():
                alerta = (
                    "🔥 *ALERTA CRÍTICA EXTREMA*\n"
                    "⛔ *Posible Inyección SQL en ejecución*\n"
                    "💀 *Peligro:* Intentan extraer la Base de Datos.\n"
                    f"🔍 *Registro:* `{linea.strip()}`"
                )
                enviar_alerta_telegram(alerta)

if __name__ == "__main__":
    analizar_logs_instantaneo("servidor.log")
