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

API_KEY = (os.getenv("API_FOOTBALL_KEY") or "").strip()
GEMINI_KEY = (os.getenv("GEMINI_API_KEY") or "").strip()
TELEGRAM_TOKEN = (os.getenv("TELEGRAM_TOKEN") or "").strip()
TELEGRAM_CHAT_ID = (os.getenv("TELEGRAM_CHAT_ID") or "").strip()
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
                    terna = {"Home": vals["Home"], "Draw": vals["Draw"], "Away": vals["Away"]}
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
    if not GEMINI_KEY:
        return True, "⚠️ Sin GEMINI_API_KEY (Auditoría IA omitida)"
    client = genai.Client(api_key=GEMINI_KEY)
    perfiles = [
        ("Analista de Bajas y Lesiones", "Busca lesiones recientes, sancionados o bajas clave de última hora para el partido."),
        ("Analista Táctico y Contexto", "Evalúa fatiga de calendario, rotación de plantilla y motivación competitiva en la tabla."),
        ("Auditor de Riesgo y Cuotas", "Detecta trampas de mercado, sobrevaloración pública o alertas de movimiento brusco de cuotas.")
    ]
    votos_ok = 0
    notas = []
    for rol, tarea in perfiles:
        etiqueta = rol.split().pop(0)
        prompt = (
            f"Eres {rol}. Partido: {loc} vs {vis} ({liga}) el {fecha_str}. "
            f"Pronóstico del modelo: {prediccion}. Alerta de mercado: {steam_alerta}. "
            f"{tarea} Responde estrictamente en una línea comenzando con APROBAR: o RECHAZAR: seguido de tu razón breve."
        )
        try:
            resp = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(temperature=0.2)
            )
            txt = (resp.text or "").strip()
            if txt.upper().startswith("APROBAR"):
                votos_ok += 1
            notas.append(f"{etiqueta}: {txt[:90]}")
        except Exception as e:
            votos_ok += 1
            notas.append(f"{etiqueta}: Sin novedad ({str(e)[:30]})")
    aprobado = votos_ok >= 2
    return aprobado, " | ".join(notas)
    def analizar_partido(p, elos, tablas, cal):
    fix = p.get("fixture", {})
    fid = str(fix.get("id", ""))
    fecha_iso = fix.get("date", "")
    liga_info = p.get("league", {})
    lid = liga_info.get("id")
    liga_nom = LIGAS_VIP_IDS.get(lid, liga_info.get("name", "Liga VIP"))

    teams = p.get("teams", {})
    loc_info = teams.get("home", {})
    vis_info = teams.get("away", {})
    loc_id = loc_info.get("id")
    vis_id = vis_info.get("id")
    loc = loc_info.get("name", "Local")
    vis = vis_info.get("name", "Visitante")

    elo_l = buscar_elo(loc, elos)
    elo_v = buscar_elo(vis, elos)
    diff_elo = (elo_l + 65.0) - elo_v

    tabla_liga = tablas.get(lid, {})
    st_l = tabla_liga.get(loc_id, {"ataque": 1.35, "defensa": 1.25, "forma": "DDDDD"})
    st_v = tabla_liga.get(vis_id, {"ataque": 1.15, "defensa": 1.35, "forma": "DDDDD"})

    h2h_l, h2h_v = analizar_h2h(p.get("h2h", []), loc_id)
    f_l = factor_forma(st_l["forma"])
    f_v = factor_forma(st_v["forma"])

    aj_elo_l = max(0.75, min(1.30, 1.0 + diff_elo / 900.0))
    aj_elo_v = max(0.75, min(1.30, 1.0 - diff_elo / 900.0))

    lambda_l = max(0.35, min(3.4, ((st_l["ataque"] + st_v["defensa"]) / 2.0) * 1.10 * aj_elo_l * f_l * h2h_l))
    lambda_v = max(0.30, min(3.1, ((st_v["ataque"] + st_l["defensa"]) / 2.0) * 0.92 * aj_elo_v * f_v * h2h_v))

    semilla = int(fid) if fid.isdigit() else 42
    p_l, p_e, p_v, p_ov, p_bt, p_u25 = simulacion_markov_10k(lambda_l, lambda_v, semilla)

    bms = p.get("bookmakers", [])
    c_asia, c_mundo = extraer_cuotas(bms)
    if not c_asia:
        return None

    probs_asia = de_vigging([c_asia["Home"], c_asia["Draw"], c_asia["Away"]])
    if not probs_asia:
        return None

    p_asia_l, p_asia_e, p_asia_v = probs_asia
    w_a = cal.get("peso_asia", 0.45)
    w_m = cal.get("peso_modelo", 0.55)
    prob_l = round(w_a * p_asia_l + w_m * p_l, 4)
    prob_e = round(w_a * p_asia_e + w_m * p_e, 4)
    prob_v = round(w_a * p_asia_v + w_m * p_v, 4)

    entropia = calcular_entropia_shannon([prob_l, prob_e, prob_v])
    if entropia > 0.96:
        return None

    steam_alerta = "Normal"
    if c_mundo and c_asia["Home"] < c_mundo["Home"] * 0.92:
        steam_alerta = "Caída fuerte cuota Local en Asia"
    elif c_mundo and c_asia["Away"] < c_mundo["Away"] * 0.92:
        steam_alerta = "Caída fuerte cuota Visitante en Asia"

    opciones = [
        ("LOCAL", prob_l, c_asia["Home"]),
        ("EMPATE CON GOLES", prob_e, c_asia["Draw"]),
        ("VISITANTE", prob_v, c_asia["Away"]),
    ]
    mejor = None
    for nombre_m, pr, ct in opciones:
        ev = (pr * ct) - 1.0
        if ev >= 0.04 and pr >= 0.42:
            if not mejor or ev > mejor:
                mejor = (nombre_m, pr, ct, ev)

    if not mejor:
        return None

    pred_txt, prob_final, cuota_final, ev_final = mejor
    stake = criterio_kelly(prob_final, cuota_final)
    if stake <= 0:
        return None

    aprobado, resumen_ia = auditar_comite_ia(loc, vis, liga_nom, fecha_iso[:10], pred_txt, steam_alerta)
    if not aprobado:
        return None

    return {
        "fixture_id": fid,
        "fecha": fecha_iso,
        "liga": liga_nom,
        "local": loc,
        "visitante": vis,
        "prediccion": pred_txt,
        "probabilidad": round(prob_final * 100, 1),
        "cuota": cuota_final,
        "ev": round(ev_final * 100, 1),
        "stake": stake,
        "entropia": entropia,
        "resumen_ia": resumen_ia
    }


def enviar_telegram(mensaje_html):
    url = f"https://telegram.org{TELEGRAM_TOKEN}/sendMessage"
    max_len = 3800
    partes = []
    texto_restante = mensaje_html

    while len(texto_restante) > max_len:
        corte = texto_restante.rfind("\n\n", 0, max_len)
        if corte == -1:
            corte = texto_restante.rfind("\n", 0, max_len)
        if corte == -1:
            corte = max_len
        partes.append(texto_restante[:corte].strip())
        texto_restante = texto_restante[corte:].strip()

    if texto_restante:
        partes.append(texto_restante)

    for idx, parte in enumerate(partes, 1):
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": parte,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }
        try:
            resp = requests.post(url, json=payload, timeout=15)
            if resp.status_code != 200:
                print(f"Error respuesta Telegram parte {idx} ({resp.status_code}): {resp.text}")
            else:
                print(f"Parte {idx}/{len(partes)} enviada a Telegram correctamente.")
        except Exception as e:
            print(f"Error Telegram parte {idx}: {e}")


def main():
    tz_col = timezone(timedelta(hours=-5))
    ahora = datetime.now(tz_col)
    fecha_hoy = ahora.strftime("%Y-%m-%d")
    fecha_ayer = (ahora - timedelta(days=1)).strftime("%Y-%m-%d")

    cal = cargar_json("predicciones/calibracion.json", {"peso_asia": 0.45, "peso_modelo": 0.55})
    data_hoy = cargar_json(f"predicciones/partidos_{fecha_hoy}.json", {})
    data_ayer = cargar_json(f"predicciones/partidos_{fecha_ayer}.json", {})

    resultados_ayer = data_ayer.get("resultados", {}) if isinstance(data_ayer, dict) else {}
    resumen_auditoria = auditar_y_calibrar(resultados_ayer, cal)

    partidos_raw = data_hoy.get("partidos", []) if isinstance(data_hoy, dict) else []
    elos = descargar_clubelo(fecha_hoy)

    ligas_presentes = set()
    temporadas = {}
    for p in partidos_raw:
        lg = p.get("league", {})
        if lg.get("id"):
            ligas_presentes.add(lg["id"])
            temporadas[lg["id"]] = lg.get("season", ahora.year)

    tablas = {lid: obtener_tabla(lid, temporadas[lid]) for lid in ligas_presentes}

    seleccionados = {}
    for p in partidos_raw:
        tarjeta = analizar_partido(p, elos, tablas, cal)
        if tarjeta:
            seleccionados[tarjeta["fixture_id"]] = tarjeta

    salida_web = {
        "actualizado": ahora.strftime("%Y-%m-%d %H:%M COL"),
        "calibracion": cal,
        "total": len(seleccionados),
        "partidos": seleccionados
    }
    guardar_json("www/data/partidos_del_dia.json", salida_web)

    lineas = [f"<b>⚡ ARSENAL MASTER QUANT V18.1</b> ({fecha_hoy})\n"]
    if resumen_auditoria:
        lineas.append(html.escape(resumen_auditoria))

    if not seleccionados:
        lineas.append("Sin señales con valor matemático positivo (+EV) tras filtrar entropía y comité IA.")
    else:
        for t in seleccionados.values():
            bloque = (
                f"🏆 <b>{html.escape(t['liga'])}</b>\n"
                f"⚽ {html.escape(t['local'])} vs {html.escape(t['visitante'])}\n"
                f"🎯 Pick: <b>{html.escape(t['prediccion'])}</b> @ {t['cuota']}\n"
                f"📊 Prob: {t['probabilidad']}% | EV: +{t['ev']}% | Stake: {t['stake']}%\n"
                f"🤖 {html.escape(t['resumen_ia'])}\n"
            )
            lineas.append(bloque)

    lineas.append(f"🌐 Panel en vivo: {URL_WEB_VIP}")
    enviar_telegram("\n".join(lineas))
    print(f"Proceso completado. Picks enviados: {len(seleccionados)}")


if __name__ == "__main__":
    main()
    
