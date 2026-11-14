import os
import sys
import json
import requests
from datetime import datetime, timedelta, timezone

API_KEY = (os.getenv("API_FOOTBALL_KEY") or "").strip()
if not API_KEY:
    print("ERROR: Falta API_FOOTBALL_KEY.")
    sys.exit(1)

HEADERS = {"x-apisports-key": API_KEY}
DOMINIO = "v3.football.api-sports.io"

LIGAS_VIP = {
    5, 536, 6, 34, 10,
    2, 3, 39, 40, 140, 141,
    135, 78, 79, 61, 144,
    262, 71, 72, 239, 241
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

    consultas = 0

    try:
        url_hoy = f"https://{DOMINIO}/fixtures?date={fecha_hoy}"
        resp = requests.get(url_hoy, headers=HEADERS, timeout=25)
        consultas += 1
        if resp.status_code != 200:
            print(f"Error HTTP {resp.status_code}: {resp.text}")
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
            if p.get("league", {}).get("id") in LIGAS_VIP
        ]

        if turno == "APERTURA" and not resultados_ayer:
            try:
                r_ayer = requests.get(f"https://{DOMINIO}/fixtures?date={fecha_ayer}", headers=HEADERS, timeout=15)
                consultas += 1
                if r_ayer.status_code == 200:
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
                print(f"Aviso auditoría ayer: {e_aud}")

        # Descarga masiva de cuotas del día en una sola petición (ahorra hasta 11 peticiones)
        if len(cuotas_cache) < len(partidos_vip):
            try:
                r_odds = requests.get(f"https://{DOMINIO}/odds?date={fecha_hoy}&bookmaker=4", headers=HEADERS, timeout=15)
                consultas += 1
                if r_odds.status_code == 200:
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

            if contador_vip < 12:
                contador_vip += 1

                if fid not in cuotas_cache:
                    try:
                        r_odd = requests.get(f"https://{DOMINIO}/odds?fixture={fid}", headers=HEADERS, timeout=10)
                        consultas += 1
                        if r_odd.status_code == 200:
                            odd_list = r_odd.json().get("response", [])
                            primer_odd = next(iter(odd_list), None)
                            if isinstance(primer_odd, dict):
                                cuotas_cache[fid] = primer_odd.get("bookmakers", [])
                    except Exception:
                        pass

                if turno == "EUROPA" and fid not in alineaciones_cache:
                    try:
                        r_lin = requests.get(f"https://{DOMINIO}/fixtures/lineups?fixture={fid}", headers=HEADERS, timeout=10)
                        consultas += 1
                        if r_lin.status_code == 200:
                            lin_list = r_lin.json().get("response", [])
                            if isinstance(lin_list, list) and len(lin_list) >= 2:
                                alineaciones_cache[fid] = True
                    except Exception:
                        pass
                elif id_loc and id_vis and fid not in h2h_cache:
                    try:
                        r_h2h = requests.get(
                            f"https://{DOMINIO}/fixtures/headtohead?h2h={id_loc}-{id_vis}&last=5",
                            headers=HEADERS,
                            timeout=10
                        )
                        consultas += 1
                        if r_h2h.status_code == 200:
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

        print(f"OK Turno {turno}: {len(partidos_enriquecidos)} partidos VIP | Consultas nuevas: {consultas}")

    except Exception as e:
        print(f"Error crítico en motor_api_real.py: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
