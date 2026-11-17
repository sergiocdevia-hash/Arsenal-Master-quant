import os
import sys
import json
import time
import requests
from datetime import datetime, timedelta, timezone

API_KEY = (os.getenv("API_FOOTBALL_KEY") or "").strip()
if not API_KEY:
    print("ERROR: Falta API_FOOTBALL_KEY.")
    sys.exit(1)

HEADERS = {"x-apisports-key": API_KEY}
DOMINIO = "v3.football.api-sports.io"

PAUSA_SEGUNDOS = 7.0
MAX_CONSULTAS_TURNO = 22
MAX_PARTIDOS_VIP = 10

PRIORIDAD_LIGAS = {
    # Nivel 1: Selecciones, Mundial, Euro, Copa America, Champions y Libertadores
    1: 1, 4: 1, 5: 1, 9: 1, 32: 1, 34: 1, 2: 1, 13: 1,
    # Nivel 2: Europa League, Conference, Sudamericana y Top 5 Europa
    3: 2, 848: 2, 11: 2, 39: 2, 140: 2, 135: 2, 78: 2, 61: 2,
    # Nivel 3: America Principal y Ligas Europeas Fuertes
    239: 3, 71: 3, 128: 3, 262: 3, 88: 3, 94: 3, 203: 3, 144: 3, 6: 3, 10: 3, 536: 3,
    # Nivel 4: Copas Nacionales, Segundas Top y Resto de America
    40: 4, 45: 4, 48: 4, 141: 4, 143: 4, 137: 4, 79: 4, 81: 4,
    179: 4, 207: 4, 218: 4, 241: 4, 72: 4, 265: 4, 281: 4, 268: 4, 242: 4, 253: 4
}

def cargar_previo(ruta):
    if os.path.exists(ruta):
        try:
            with open(ruta, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception:
            pass
    return {}

def hacer_peticion(url, estado_cuota, timeout=15):
    if estado_cuota["usadas"] >= MAX_CONSULTAS_TURNO:
        return None
    if estado_cuota["restantes_api"] is not None and estado_cuota["restantes_api"] <= 12:
        return None

    resp = requests.get(url, headers=HEADERS, timeout=timeout)
    estado_cuota["usadas"] += 1

    rem = resp.headers.get("x-ratelimit-requests-remaining")
    if rem is not None and str(rem).isdigit():
        estado_cuota["restantes_api"] = int(rem)

    time.sleep(PAUSA_SEGUNDOS)
    return resp
def main():
    tz_col = timezone(timedelta(hours=-5))
    ahora_col = datetime.now(tz_col)
    fecha_hoy = ahora_col.strftime("%Y-%m-%d")
    fecha_ayer = (ahora_col - timedelta(days=1)).strftime("%Y-%m-%d")
    hora_actual = ahora_col.hour

    if hora_actual < 6:
        turno = "APERTURA"
    elif hora_actual < 14:
        turno = "EUROPA"
    else:
        turno = "AMERICA"

    print(f"Iniciando Turno {turno} | Fecha Colombia: {fecha_hoy}")

    carpeta_destino = "predicciones"
    os.makedirs(carpeta_destino, exist_ok=True)
    nombre_archivo = os.path.join(carpeta_destino, f"partidos_{fecha_hoy}.json")
    previo = cargar_previo(nombre_archivo)

    cuotas_cache = previo.get("cuotas_vip", {}) if isinstance(previo.get("cuotas_vip"), dict) else {}
    h2h_cache = previo.get("h2h_vip", {}) if isinstance(previo.get("h2h_vip"), dict) else {}
    alineaciones_cache = previo.get("alineaciones_vip", {}) if isinstance(previo.get("alineaciones_vip"), dict) else {}
    resultados_ayer = previo.get("resultados_ayer", {}) if isinstance(previo.get("resultados_ayer"), dict) else {}

    estado_cuota = {"usadas": 0, "restantes_api": None}

    try:
        url_hoy = f"https://{DOMINIO}/fixtures?date={fecha_hoy}"
        resp = hacer_peticion(url_hoy, estado_cuota, timeout=25)
        if resp is None or resp.status_code != 200:
            code = resp.status_code if resp is not None else "LIMITE"
            print(f"Error HTTP {code}")
            if previo.get("partidos"):
                print("Usando respaldo guardado de hoy.")
                sys.exit(0)
            sys.exit(1)

        datos = resp.json()
        errores = datos.get("errors")
        if errores:
            print(f"Error API-Sports: {errores}")
            if previo.get("partidos"):
                print("Usando respaldo guardado de hoy para continuar sin detener el bot.")
                sys.exit(0)
            sys.exit(1)

        todos_partidos = datos.get("response", [])
        partidos_vip = [
            p for p in todos_partidos
            if p.get("league", {}).get("id") in PRIORIDAD_LIGAS
        ]

        partidos_vip.sort(
            key=lambda p: (
                PRIORIDAD_LIGAS.get(p.get("league", {}).get("id"), 99),
                p.get("fixture", {}).get("timestamp", 0)
            )
        )

        if turno == "APERTURA" and not resultados_ayer:
            try:
                r_ayer = hacer_peticion(f"https://{DOMINIO}/fixtures?date={fecha_ayer}", estado_cuota, timeout=15)
                if r_ayer is not None and r_ayer.status_code == 200:
                    for item in r_ayer.json().get("response", []):
                        fid_ayer = str(item.get("fixture", {}).get("id", ""))
                        st_ayer = item.get("fixture", {}).get("status", {}).get("short", "")
                        goals = item.get("goals", {})
                        if fid_ayer and st_ayer in ("FT", "AET", "PEN"):
                            resultados_ayer[fid_ayer] = {
                                "gl": goals.get("home", 0),
                                "gv": goals.get("away", 0)
                            }
            except Exception as e_aud:
                print(f"Aviso auditoria ayer: {e_aud}")

        faltan_cuotas = any(
            str(p.get("fixture", {}).get("id", "")) not in cuotas_cache
            for p in partidos_vip[:MAX_PARTIDOS_VIP]
        )
        if partidos_vip and faltan_cuotas:
            try:
                r_odds = hacer_peticion(f"https://{DOMINIO}/odds?date={fecha_hoy}&bookmaker=4", estado_cuota, timeout=20)
                if r_odds is not None and r_odds.status_code == 200:
                    for odd_item in r_odds.json().get("response", []):
                        ofid = str(odd_item.get("fixture", {}).get("id", ""))
                        if ofid and odd_item.get("bookmakers"):
                            cuotas_cache[ofid] = odd_item.get("bookmakers", [])
            except Exception:
                pass

        partidos_enriquecidos = []
        contador_vip = 0

        for p in partidos_vip:
            fid = str(p.get("fixture", {}).get("id", ""))
            estado = p.get("fixture", {}).get("status", {}).get("short", "")
            id_loc = p.get("teams", {}).get("home", {}).get("id")
            id_vis = p.get("teams", {}).get("away", {}).get("id")

            if not fid or estado in ("FT", "AET", "PEN"):
                continue

            if contador_vip >= MAX_PARTIDOS_VIP:
                break
            contador_vip += 1

            if fid not in cuotas_cache:
                try:
                    r_odd = hacer_peticion(f"https://{DOMINIO}/odds?fixture={fid}", estado_cuota, timeout=10)
                    if r_odd is not None and r_odd.status_code == 200:
                        odd_list = r_odd.json().get("response", [])
                        primer_odd = next(iter(odd_list), None)
                        if isinstance(primer_odd, dict):
                            cuotas_cache[fid] = primer_odd.get("bookmakers", [])
                except Exception:
                    pass

            if turno == "EUROPA" and fid not in alineaciones_cache:
                try:
                    r_lin = hacer_peticion(f"https://{DOMINIO}/fixtures/lineups?fixture={fid}", estado_cuota, timeout=10)
                    if r_lin is not None and r_lin.status_code == 200:
                        lin_list = r_lin.json().get("response", [])
                        if isinstance(lin_list, list) and len(lin_list) >= 2:
                            alineaciones_cache[fid] = True
                except Exception:
                    pass
            elif id_loc and id_vis and fid not in h2h_cache:
                try:
                    r_h2h = hacer_peticion(
                        f"https://{DOMINIO}/fixtures/headtohead?h2h={id_loc}-{id_vis}&last=5",
                        estado_cuota,
                        timeout=10
                    )
                    if r_h2h is not None and r_h2h.status_code == 200:
                        h2h_cache[fid] = r_h2h.json().get("response", [])
                except Exception:
                    pass

            p["bookmakers"] = cuotas_cache.get(fid, [])
            p["h2h"] = h2h_cache.get(fid, [])
            partidos_enriquecidos.append(p)

        datos["turno_actual"] = turno
        datos["partidos"] = partidos_enriquecidos
        datos["cuotas_vip"] = cuotas_cache
        datos["h2h_vip"] = h2h_cache
        datos["alineaciones_vip"] = alineaciones_cache
        datos["resultados"] = resultados_ayer
        datos["resultados_ayer"] = resultados_ayer

        with open(nombre_archivo, "w", encoding="utf-8") as archivo:
            json.dump(datos, archivo, indent=4, ensure_ascii=False)

        rest_txt = estado_cuota["restantes_api"] if estado_cuota["restantes_api"] is not None else "N/A"
        print(f"OK Turno {turno}: {len(partidos_enriquecidos)} partidos VIP | Consultas turno: {estado_cuota['usadas']} | Restantes API hoy: {rest_txt}")

    except Exception as e:
        print(f"Error critico en motor_api_real.py: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
    
