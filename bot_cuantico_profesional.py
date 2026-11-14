import os
import sys
import json
import math
import csv
import io
import html
import random
import requests
from datetime import datetime, timedelta, timezone
from google import genai
from google.genai import types

API_KEY = os.getenv("API_FOOTBALL_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
URL_WEB_VIP = "https://github.io"

if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
    print("ERROR: Faltan credenciales de Telegram.")
    sys.exit(1)

LIGAS_VIP_IDS = {
    5: "UEFA NATIONS LEAGUE", 536: "CONCACAF NATIONS LEAGUE",
    6: "COPA AFRICANA DE NACIONES", 34: "ELIMINATORIAS CONMEBOL",
    10: "AMISTOSOS INTERNACIONALES", 2: "UEFA CHAMPIONS LEAGUE",
    3: "UEFA EUROPA LEAGUE", 39: "PREMIER LEAGUE (INGLATERRA)",
    40: "CHAMPIONSHIP (INGLATERRA)", 140: "LALIGA EA SPORTS (ESPAÑA)",
    141: "LALIGA 2 (ESPAÑA)", 135: "SERIE A (ITALIA)",
    78: "BUNDESLIGA (ALEMANIA)", 79: "2. BUNDESLIGA (ALEMANIA)",
    61: "LIGUE 1 (FRANCIA)", 144: "JUPILER PRO LEAGUE (BÉLGICA)",
    262: "LIGA MX (MÉXICO)", 71: "SERIE A (BRASIL)",
    72: "SERIE B (BRASIL)", 239: "LIGA BETPLAY (COLOMBIA)",
    241: "COPA COLOMBIA"
}


def cargar_json(ruta, default):
    if os.path.exists(ruta):
        try:
            with open(ruta, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, type(default)):
                    return data
        except Exception:
            pass
    return default


def guardar_json(ruta, data):
    carpeta = os.path.dirname(ruta)
    if carpeta:
        os.makedirs(carpeta, exist_ok=True)
    try:
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"Error guardando {ruta}: {e}")


def descargar_clubelo(fecha_str):
    elos = {}
    try:
        resp = requests.get(f"http://clubelo.com{fecha_str}", timeout=10)
        if resp.status_code == 200:
            for row in csv.DictReader(io.StringIO(resp.text)):
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


def obtener_tabla(id_liga, temporada):
    if not API_KEY:
        return {}
    url = f"https://api-sports.io{id_liga}&season={temporada}"
    try:
        resp = requests.get(url, headers={"x-apisports-key": API_KEY}, timeout=12)
        if resp.status_code != 200:
            return {}
        primer = next(iter(resp.json().get("response", [])), None)
        if not isinstance(primer, dict):
            return {}
        stats = {}
        for grupo in primer.get("league", {}).get("standings", []):
            for fila in grupo:
                eid = fila.get("team", {}).get("id")
                pj = fila.get("all", {}).get("played") or 1
                gf = fila.get("all", {}).get("goals", {}).get("for", 0)
                gc = fila.get("all", {}).get("goals", {}).get("against", 0)
                if eid:
                    stats[eid] = {
                        "ataque": float(gf) / float(pj),
                        "defensa": float(gc) / float(pj),
                        "forma": str(fila.get("form") or "DDDDD")[-5:]
                    }
        return stats
    except Exception:
        return {}


def factor_forma(forma_str):
    pts = sum(3 if c == "W" else (1 if c == "D" else 0) for c in (forma_str or ""))
    return 0.88 + (pts / 15.0) * 0.24


def analizar_h2h(h2h_list, id_local):
    if not isinstance(h2h_list, list) or not h2h_list:
        return 1.0, 1.0
    gl = gv = 0
    for m in h2h_list:
        gh = m.get("goals", {}).get("home") or 0
        ga = m.get("goals", {}).get("away") or 0
        if m.get("teams", {}).get("home", {}).get("id") == id_local:
            gl += gh
            gv += ga
        else:
            gl += ga
            gv += gh
    n = len(h2h_list)
    return max(0.85, min(1.15, 0.90 + (gl / n) * 0.08)), max(0.85, min(1.15, 0.90 + (gv / n) * 0.08))


def extraer_cuotas(bookmakers):
    if not isinstance(bookmakers, list):
        return None, None
    c_asia = c_mundo = None
    for bm in bookmakers:
        nom = str(bm.get("name", "")).lower()
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
                    if any(a in nom for a in ("pinnacle", "sbobet", "188bet")) and not c_asia:
                        c_asia = terna
                    elif any(m in nom for m in ("bet365", "1xbet", "bwin", "william hill")) and not c_mundo:
                        c_mundo = terna
                    elif not c_mundo:
                        c_mundo = terna
    return (c_asia or c_mundo), (c_mundo or c_asia)


def de_vigging(terna):
    if not terna or any(c <= 1.0 for c in terna):
        return None
    inv = [1.0 / c for c in terna]
    overround = sum(inv)
    if overround <= 0:
        return None
    return [round(p / overround, 4) for p in inv]


def simulacion_markov_10k(lambda_l, lambda_v, semilla_id):
    rng = random.Random(semilla_id)
    pesos = (0.13, 0.15, 0.17, 0.16, 0.18, 0.21)
    wl = dr = wv = og = btts = u25 = 0
    for _ in range(10000):
        gl = gv = 0
        for p in pesos:
            ml = 1.08 if gl > gv else (0.94 if gl < gv else 1.0)
            mv = 1.08 if gv > gl else (0.94 if gv < gl else 1.0)
            if rng.random() < lambda_l * p * ml:
                gl += 1
            if rng.random() < lambda_v * p * mv:
                gv += 1
        if gl > gv:
            wl += 1
        elif gl < gv:
            wv += 1
        else:
            dr += 1
        if gl >= 1:
            og += 1
        if gl >= 1 and gv >= 1:
            btts += 1
        if gl + gv <= 2:
            u25 += 1
    return wl / 10000.0, dr / 10000.0, wv / 10000.0, og / 10000.0, btts / 10000.0, u25 / 10000.0


def calcular_entropia_shannon(probs):
    h = 0.0
    for p in probs:
        if p > 0:
            h -= p * math.log2(p)
    return round(h / math.log2(len(probs)), 3)


def criterio_kelly(prob_real, cuota, fraccion=0.25, tope=3.5):
    if not cuota or cuota <= 1.01 or prob_real <= 0:
        return 0.0
    b = cuota - 1.0
    q = 1.0 - prob_real
    f_star = ((b * prob_real) - q) / b
    if f_star <= 0:
        return 0.0
    stake = f_star * fraccion * 100.0
    return round(min(tope, max(0.5, stake)), 2)


def auditar_y_calibrar(resultados_ayer, cal):
    if not resultados_ayer or not os.path.exists("www/data/partidos_del_dia.json"):
        return ""
    previa = cargar_json("www/data/partidos_del_dia.json", {})
    tarjetas = previa.get("partidos", {}) if isinstance(previa.get("partidos"), dict) else previa
    ok_cnt = eval_cnt = 0
    for t in tarjetas.values():
        if not isinstance(t, dict):
            continue
        fid = str(t.get("fixture_id", ""))
        if fid in resultados_ayer:
            eval_cnt += 1
            gl, gv = resultados_ayer[fid]["gl"], resultados_ayer[fid]["gv"]
            pred = t.get("prediccion", "")
            if (("EMPATE CON GOLES" in pred and gl == gv and gl >= 1) or
                ("LOCAL" in pred and "1X" not in pred and "EMPATE" not in pred and gl > gv) or
                ("VISITANTE" in pred and "X2" not in pred and "EMPATE" not in pred and gv > gl) or
                (("1X" in pred or "LOCAL O EMPATE" in pred) and gl >= gv) or
                (("X2" in pred or "EMPATE O VISITANTE" in pred) and gv >= gl) or
                ("BTTS" in pred and gl >= 1 and gv >= 1) or
                ("UNDER" in pred and gl + gv <= 2)):
                ok_cnt += 1

    if eval_cnt > 0:
        pct = (ok_cnt / eval_cnt) * 100.0
        if pct < 55.0:
            cal["peso_asia"] = min(0.55, round(cal.get("peso_asia", 0.40) + 0.03, 2))
            cal["peso_modelo"] = round(1.0 - cal["peso_asia"], 2)
        elif pct > 70.0:
            cal["peso_modelo"] = min(0.70, round(cal.get("peso_modelo", 0.60) + 0.02, 2))
            cal["peso_asia"] = round(1.0 - cal["peso_modelo"], 2)
        guardar_json("predicciones/calibracion.json", cal)

        historial = cargar_json("www/data/historial_aciertos.json", {"registros": []})
        historial["registros"].append({
            "fecha": datetime.now(timezone(timedelta(hours=-5))).strftime("%Y-%m-%d"),
            "evaluados": eval_cnt,
            "aciertos": ok_cnt,
            "efectividad": round(pct, 1)
        })
        guardar_json("www/data/historial_aciertos.json", historial)
        return f"📊 Auditoría Ayer: {ok_cnt}/{eval_cnt} aciertos ({pct:.1f}%)\n"
    return ""


def auditar_comite_ia(loc, vis, liga, fecha_str, prediccion, steam_alerta):
    if not GEMINI_API_KEY:
        return True, "⚠️ Sin GEMINI_API_KEY (Auditoría IA omitida)"
    client = genai.Client(api_key=GEMINI_API_KEY)
    perfiles = [
        ("Analista de Bajas y Lesiones", f"Busca lesiones recientes, sancionados o bajas clave de última hora para {loc} vs {vis} ({liga}) hoy {fecha_str}. Responde en máximo 2 líneas y termina con VOTO: LUZ VERDE o VOTO: TRAMPA."),
