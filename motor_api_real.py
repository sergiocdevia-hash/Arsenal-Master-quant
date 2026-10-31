import os
import requests
import json
from datetime import datetime

fecha_hoy = datetime.now().strftime("%Y-%m-%d")
API_KEY = os.getenv("API_FOOTBALL_KEY")
URL = "https://rapidapi.com"
QUERYSTRING = {"date": fecha_hoy}
HEADERS = {
    "x-rapidapi-host": "://rapidapi.com",
    "x-rapidapi-key": API_KEY
}

def procesar_jornada_limpia():
    print(f"Consultando la API para la fecha: {fecha_hoy}...")
    try:
        response = requests.get(URL, headers=HEADERS, params=QUERYSTRING)
        if response.status_code != 200:
            print("Error API")
            return
            
        datos_api = response.json()
        partidos_recibidos = datos_api.get("response", [])
        ligas_agrupadas = {}
        
        for item in partidos_recibidos:
            nombre_liga = f"{item['league']['country']} - {item['league']['name']}"
            eq_local = item["teams"]["home"]["name"]
            eq_vis = item["teams"]["away"]["name"]
            
            partido_formateado = {
                "local": eq_local,
                "visitante": eq_vis,
                "prediccion": "COBERTURA TOTAL LOCAL", 
                "cuota": "1.80",
                "stake": "1.25",
                "xg_l": "1.50",
                "xg_v": "1.10",
                "verdicto": "MERCADO ESTABLE",
                "prob_bayesiana": "L: 55% | E: 20%"
            }
            
            if nombre_liga not in ligas_agrupadas:
                ligas_agrupadas[nombre_liga] = []
            ligas_agrupadas[nombre_liga].append(partido_formateado)
            
        with open("partidos_hoy.json", "w", encoding="utf-8") as f:
            json.dump(ligas_agrupadas, f, ensure_ascii=False, indent=4)
        print("¡Archivo de hoy generado con éxito!")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    procesar_jornada_limpia()
