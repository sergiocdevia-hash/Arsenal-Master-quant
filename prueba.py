import requests
def enviar(m):
 requests.post(f"https://telegram.org", json={"chat_id": "8802485032", "text": m, "parse_mode": "Markdown"})
enviar("⚠️ *ALERTAS DE CIBERSEGURIDAD*\n🚨 *Ataque detectado en vivo*\n📝 *Detalle:* Fuerza Bruta")
enviar("🔥 *ALERTA CRÍTICA EXTREMA*\n⛔ *Inyección SQL en ejecución*")
print("[INFO] ¡Alertas enviadas!")
