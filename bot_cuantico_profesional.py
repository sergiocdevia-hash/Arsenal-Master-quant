import os
import sys
import json
import math
import csv
import io
import random
import requests
from datetime import datetime, timedelta, timezone

API_KEY = os.getenv("API_FOOTBALL_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
DOMINIO_WEB = "sergiocdevia-hash.github.io"
URL_WEB_VIP = f"https://{DOMINIO_WEB}/Arsenal-Master-quant/www/"

if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
    print("ERROR: Faltan TELEGRAM_TOKEN o TELEGRAM_CHAT_ID.")
    sys.exit(1)

LIGAS_VIP_IDS = {
    5: "UEFA NATIONS LEAGUE",
    536: "CONCACAF NATIONS LEAGUE",
    6: "COPA AFRICANA DE NACIONES",
    34: "ELIMINATORIAS CONMEBOL",
    10: "AMISTOSOS INTERNACIONALES",
    2: "UEFA CHAMPIONS LEAGUE",
    3: "UEFA EUROPA LEAGUE",
    39: "PREMIER LEAGUE (INGLATERRA)",
    40: "CHAMPIONSHIP (INGLATERRA)",
    140: "LALIGA EA SPORTS (ESPANA)",
    141: "LALIGA 2 (ESPANA)",
    135: "SERIE A (ITALIA)",
    78: "BUNDESLIGA (ALEMANIA)",
    79: "2. BUNDESLIGA (ALEMANIA)",
    61: "LIGUE 1 (FRANCIA)",
    144: "JUPILER PRO LEAGUE (BELGICA)",
    262: "LIGA MX (MEXICO)",
    71: "SERIE A (BRASIL)",
    72: "SERIE B (BRASIL)",
    239: "LIGA BETPLAY (COLOMBIA)",
    241: "COPA COLOMBIA"
}


def cargar_calibracion():
    ruta = os.path.join("predicciones", "calibracion.json")
    default = {"peso_modelo": 0.60, "peso_asia": 0.40, "factor_goles": 1.00}
    if os.path.exists(ruta):
        try:
            with open(ruta, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    default.update(data)
        except Exception:
            pass
    return default


def guardar_calibracion(cal):
    os.makedirs("predicciones", exist_ok=True)
    ruta = os.path.join("predicciones", "calibracion.json")
    try:
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump(cal, f, indent=4)
    except Exception:
        pass


def cargar_cuotas_apertura(fecha_hoy):
    ruta = os.path.join("predicciones", f"apertura_clv_{fecha_hoy}.json")
    if os.path.exists(ruta):
        try:
            with open(ruta, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception:
            pass
    return {}


def guardar_cuotas_apertura(fecha_hoy, registro):
    os.makedirs("predicciones", exist_ok=True)
    ruta = os.path.join("predicciones", f"apertura_clv_{fecha_hoy}.json")
    try:
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump(registro, f, indent=4)
    except Exception:
        pass


def descargar_clubelo():
    elos = {}
    try:
        tz_col = timezone(timedelta(hours=-5))
        fecha_str = datetime.now(tz_col).strftime("%Y-%m-%d")
        resp = requests.get(f"http://clubelo.com{fecha_str}", timeout=10)
        if resp.status_code == 200:
            reader = csv.DictReader(io.StringIO(resp.text))
            for row in reader:
                club = str(row.get("Club", "")).strip().lower()
                elo = row.get("Elo")
                if club and elo:
                    try:
                        elos[club] = float(elo)
                    except ValueError:
                        pass
    except Exception:
        pass
    return elos


def buscar_elo(nombre_equipo, mapa_elo):
    nombre = nombre_equipo.lower().strip()
    if nombre in mapa_elo:
        return mapa_elo[nombre]
    for k, v in mapa_elo.items():
        if nombre in k or k in nombre:
            return v
    return 1500.0


def obtener_estadisticas_tabla(id_liga, temporada):
    if not API_KEY:
        return {}
    url = f"https://api-sports.io{id_liga}&season={temporada}"
    headers = {"x-apisports-key": API_KEY}
    try:
        resp = requests.get(url, headers=headers, timeout=12)
        if resp.status_code != 200:
            return {}
        data = resp.json().get("response", [])
        primer_bloque = next(iter(data), None)
        if not isinstance(primer_bloque, dict):
            return {}
        stats_equipos = {}
        grupos = primer_bloque.get("league", {}).get("standings", [])
        for grupo in grupos:
            for fila in grupo:
                equipo_id = fila.get("team", {}).get("id")
                pj = fila.get("all", {}).get("played") or 1
                gf = fila.get("all", {}).get("goals", {}).get("for", 0)
                gc = fila.get("all", {}).get("goals", {}).get("against", 0)
                forma_raw = str(fila.get("form") or "DDDDD")
                forma = forma_raw[-5:]
                if equipo_id:
                    stats_equipos[equipo_id] = {
                        "ataque": float(gf) / float(pj),
                        "defensa": float(gc) / float(pj),
                        "forma": forma
                    }
        return stats_equipos
    except Exception:
        return {}


def factor_forma_real(forma_str):
    if not forma_str:
        return 1.0
    puntos = 0
    for ch in forma_str:
        if ch == "W":
            puntos += 3
        elif ch == "D":
            puntos += 1
    return 0.88 + (puntos / 15.0) * 0.24


def analizar_h2h(h2h_list, id_local):
    if not isinstance(h2h_list, list) or len(h2h_list) == 0:
        return 1.0, 1.0
    goles_l = 0
    goles_v = 0
    for m in h2h_list:
        h_id = m.get("teams", {}).get("home", {}).get("id")
        gh = m.get("goals", {}).get("home") or 0
        ga = m.get("goals", {}).get("away") or 0
        if h_id == id_local:
            goles_l += gh
            goles_v += ga
        else:
            goles_l += ga
            goles_v += gh
    n = len(h2h_list)
    prom_l = goles_l / n
    prom_v = goles_v / n
    f_l = max(0.85, min(1.15, 0.90 + (prom_l * 0.08)))
    f_v = max(0.85, min(1.15, 0.90 + (prom_v * 0.08)))
    return f_l, f_v


def extraer_cuotas_mercado(bookmakers):
    if not isinstance(bookmakers, list):
        return None, None
    asiaticas = ("pinnacle", "sbobet", "188bet")
    mundiales = ("bet365", "1xbet", "bwin", "william hill")
    c_asia = None
    c_mundo = None

    for bm in bookmakers:
        nombre = str(bm.get("name", "")).lower()
        for bet in bm.get("bets", []):
            if bet.get("id") == 1:
                vals = {}
                for v in bet.get("values", []):
                    try:
                        vals[str(v.get("value"))] = float(v.get("odd"))
                    except (ValueError, TypeError):
                        pass
                if "Home" in vals and "Draw" in vals and "Away" in vals:
                    terna = (vals["Home"], vals["Draw"], vals["Away"])
                    if any(a in nombre for a in asiaticas) and not c_asia:
                        c_asia = terna
                    elif any(m in nombre for m in mundiales) and not c_mundo:
                        c_mundo = terna
                    elif not c_mundo:
                        c_mundo = terna

    return (c_asia or c_mundo), (c_mundo or c_asia)


def devig_probabilidades(terna):
    o_l, o_e, o_v = terna
    if o_l <= 0 or o_e <= 0 or o_v <= 0:
        return 0.34, 0.33, 0.33
    inv_l = 1.0 / o_l
    inv_e = 1.0 / o_e
    inv_v = 1.0 / o_v
    suma = inv_l + inv_e + inv_v
    return (inv_l / suma), (inv_e / suma), (inv_v / suma)


def simulacion_markov_10k(lambda_l, lambda_v, semilla_id):
    rng = random.Random(semilla_id)
    pesos_bloques = (0.13, 0.15, 0.17, 0.16, 0.18, 0.21)

    wins_l = 0
    draws = 0
    wins_v = 0
    empate_goles_count = 0
    btts_count = 0
    under25_count = 0
    escenarios = 10000

    for _ in range(escenarios):
        gl = 0
        gv = 0
        for peso in pesos_bloques:
            mod_l = 1.08 if gl < gv else (0.94 if gl > gv else 1.0)
            mod_v = 1.08 if gv < gl else (0.94 if gv > gl else 1.0)
            if rng.random() < (lambda_l * peso * mod_l):
                gl += 1
            if rng.random() < (lambda_v * peso * mod_v):
                gv += 1

        if gl > gv:
            wins_l += 1
        elif gl < gv:
            wins_v += 1
        else:
            draws += 1
            if gl >= 1:
                empate_goles_count += 1

        if gl >= 1 and gv >= 1:
            btts_count += 1
        if (gl + gv) <= 2:
            under25_count += 1

    return (
        wins_l / escenarios,
        draws / escenarios,
        wins_v / escenarios,
        empate_goles_count / escenarios,
        btts_count / escenarios,
        under25_count / escenarios
    )


def calcular_entropia(p_l, p_e, p_v):
    entropia = 0.0
    for p in (p_l, p_e, p_v):
        if p > 0.0001:
            entropia -= p * math.log2(p)
    return entropia


def calcular_kelly(prob_algoritmo, cuota_mercado):
    if cuota_mercado <= 1.05:
        return 0.0
    b = cuota_mercado - 1.0
    q = 1.0 - prob_algoritmo
    f_kelly = ((b * prob_algoritmo) - q) / b
    return round(max(0.0, min(f_kelly * 0.25 * 100.0, 3.50)), 2)


def cargar_historial_ayer(fecha_ayer):
    fechas = {}
    ruta_ayer = os.path.join("predicciones", f"partidos_{fecha_ayer}.json")
    if os.path.exists(ruta_ayer):
        try:
            with open(ruta_ayer, "r", encoding="utf-8") as f:
                data_ayer = json.load(f)
            for item in data_ayer.get("response", []):
                f_iso = str(item.get("fixture", {}).get("date", ""))
                try:
                    dt_u = datetime.fromisoformat(f_iso.replace("Z", "+00:00"))
                    h_id = item.get("teams", {}).get("home", {}).get("id")
                    a_id = item.get("teams", {}).get("away", {}).get("id")
                    if h_id:
                        fechas[h_id] = dt_u
                    if a_id:
                        fechas[a_id] = dt_u
                except Exception:
                    pass
        except Exception:
            pass
    return fechas


def auditar_y_calibrar(resultados_ayer, cal):
