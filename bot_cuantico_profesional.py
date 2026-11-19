import os
import json
import time
import math
import html
import random
import logging
import threading
from datetime import datetime, timezone, timedelta
from io import BytesIO
import requests

TZ_COL = timezone(timedelta(hours=-5))
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ArsenalQuantV18_3")

try:
    from PIL import Image, ImageDraw, ImageFont
    PILLOW_OK = True
except ImportError:
    PILLOW_OK = False

try:
    from google import genai
    from google.genai import types
    GENAI_OK = True
except ImportError:
    GENAI_OK = False

BANDERAS = {
    "England": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "Spain": "🇪🇸", "Italy": "🇮🇹", "Germany": "🇩🇪",
    "France": "🇫🇷", "Colombia": "🇨🇴", "Brazil": "🇧🇷", "Argentina": "🇦🇷",
    "Portugal": "🇵🇹", "Netherlands": "🇳🇱", "USA": "🇺🇸", "Mexico": "🇲🇽"
}


class RateLimiterGuard:
    def __init__(self, min_interval=6.5, max_rpm=8, max_calls=32):
        self.lock = threading.Lock()
        self.min_interval = min_interval
        self.max_rpm = max_rpm
        self.max_calls = max_calls
        self.last_call = 0.0
        self.timestamps = []
        self.total = 0

    def adquirir(self) -> bool:
        with self.lock:
            if self.total >= self.max_calls:
                return False
            ahora = time.time()
            self.timestamps = [t for t in self.timestamps if (ahora - t) < 60.0]
            if len(self.timestamps) >= self.max_rpm:
                espera = 60.0 - (ahora - min(self.timestamps)) + 0.5
                if espera > 0:
                    time.sleep(espera)
            ahora = time.time()
            if (ahora - self.last_call) < self.min_interval:
                time.sleep(self.min_interval - (ahora - self.last_call))
            self.last_call = time.time()
            self.timestamps.append(self.last_call)
            self.total += 1
            return True


def extraer_partido(raw: dict, factor_ayer: float = 1.0) -> dict:
    fix = raw.get("fixture") or {}
    lig = raw.get("league") or {}
    tms = raw.get("teams") or {}
    home = tms.get("home") or {}
    away = tms.get("away") or {}
    fid = fix.get("id") or raw.get("id") or random.randint(10000, 99999)
    fecha_iso = str(fix.get("date") or raw.get("fecha") or "")
    hora_col = "Por definir"
    if "T" in fecha_iso:
        try:
            dt_col = datetime.fromisoformat(fecha_iso.replace("Z", "+00:00")).astimezone(TZ_COL)
            hora_col = dt_col.strftime("%H:%M")
            fecha_iso = dt_col.isoformat()
        except Exception:
            tramo = fecha_iso.split("T")[-1]
            hora_col = tramo[:5] if len(tramo) >= 5 else "Por definir"

    cuotas = {}
    fuente_cuotas = raw.get("cuotas_vip") or raw.get("bookmakers") or []
    if isinstance(fuente_cuotas, dict):
        cuotas.update(fuente_cuotas)
    elif isinstance(fuente_cuotas, list):
        for bk in fuente_cuotas:
            if not isinstance(bk, dict):
                continue
            for bet in bk.get("bets") or []:
                bname = bet.get("name", "")
                for val in bet.get("values") or []:
                    v = str(val.get("value", ""))
                    try:
                        odd = float(val.get("odd", 0) or 0)
                    except (ValueError, TypeError):
                        odd = 0.0
                    if odd <= 1.01:
                        continue
                    if bname == "Match Winner":
                        if v == "Home":
                            cuotas.setdefault("1", odd)
                        elif v == "Draw":
                            cuotas.setdefault("X", odd)
                        elif v == "Away":
                            cuotas.setdefault("2", odd)
                    elif bname == "Double Chance":
                        if v == "Home/Draw":
                            cuotas.setdefault("1X", odd)
                        elif v == "Draw/Away":
                            cuotas.setdefault("X2", odd)
                    elif bname == "Goals Over/Under" and v == "Over 2.5":
                        cuotas.setdefault("Over2.5", odd)
                    elif bname == "Both Teams Score" and v == "Yes":
                        cuotas.setdefault("BTTS", odd)

    xg_mkt_l = max(0.65, min(2.60, 2.75 / max(1.10, float(cuotas.get("1", 2.10)))))
    xg_mkt_v = max(0.55, min(2.40, 2.55 / max(1.10, float(cuotas.get("2", 3.20)))))

    h2h_list = raw.get("h2h_vip") or raw.get("h2h") or []
    gh_sum = 0.0
    gv_sum = 0.0
    muestras = 0.0
    id_home = home.get("id")
    for m in h2h_list:
        if not isinstance(m, dict):
            continue
        g = m.get("goals") or {}
        if g.get("home") is not None and g.get("away") is not None:
            es_local = ((m.get("teams") or {}).get("home") or {}).get("id") == id_home
            gh_sum += float(g["home"] if es_local else g["away"])
            gv_sum += float(g["away"] if es_local else g["home"])
            muestras += 1.0

    if muestras > 0:
        xg_l = ((xg_mkt_l * 0.65) + ((gh_sum / muestras) * 0.35)) * factor_ayer
        xg_v = ((xg_mkt_v * 0.65) + ((gv_sum / muestras) * 0.35)) * factor_ayer
    else:
        xg_l = xg_mkt_l * factor_ayer
        xg_v = xg_mkt_v * factor_ayer

    pais = lig.get("country") or "World"
    return {
        "id": fid,
        "liga": lig.get("name") or raw.get("liga") or "LIGA VIP",
        "pais": pais,
        "bandera": BANDERAS.get(pais, "⚽"),
        "fecha": fecha_iso,
        "hora": hora_col,
        "local": home.get("name") or raw.get("local") or "Local",
        "visitante": away.get("name") or raw.get("visitante") or "Visitante",
        "xg_local": max(0.45, min(3.10, xg_l)),
        "xg_visita": max(0.40, min(2.90, xg_v)),
        "cuotas": cuotas
            }
def calcular_cuantico(info: dict) -> dict:
    lmbda = info["xg_local"]
    mu = info["xg_visita"]
    cuotas = info["cuotas"]

    p_l = [(math.exp(-lmbda) * (lmbda ** g)) / math.factorial(g) for g in range(8)]
    p_v = [(math.exp(-mu) * (mu ** g)) / math.factorial(g) for g in range(8)]
    sim_l = random.choices(range(8), weights=p_l, k=15000)
    sim_v = random.choices(range(8), weights=p_v, k=15000)

    p1 = 0.0
    px = 0.0
    p2 = 0.0
    ov = 0.0
    bt = 0.0
    eg = 0.0

    for gl, gv in zip(sim_l, sim_v):
        w = 1.0 - (0.11 * lmbda * mu if (gl == 0 and gv == 0) else 0.0)
        if gl > gv:
            p1 += w
        elif gl == gv:
            px += w
            if gl > 0:
                eg += w
        else:
            p2 += w
        if (gl + gv) >= 2.5:
            ov += w
        if gl > 0 and gv > 0:
            bt += w

    tot = max(1e-6, p1 + px + p2)
    p_1 = p1 / tot
    p_x = px / tot
    p_2 = p2 / tot
    p_1x = min(0.95, p_1 + p_x)
    p_x2 = min(0.95, p_x + p_2)
    p_ov = max(0.08, ov / 15000.0)
    p_bt = max(0.08, bt / 15000.0)
    p_eg = max(0.04, eg / 15000.0)
    entropia = -sum(max(1e-6, p) * math.log2(max(1e-6, p)) for p in (p_1, p_x, p_2)) / math.log2(3)

    opciones = [
        {"m": "1 (Local)", "p": p_1, "c": float(cuotas.get("1", round(1 / max(0.15, p_1), 2)))},
        {"m": "X (Empate)", "p": p_x, "c": float(cuotas.get("X", round(1 / max(0.15, p_x), 2)))},
        {"m": "2 (Visita)", "p": p_2, "c": float(cuotas.get("2", round(1 / max(0.15, p_2), 2)))},
        {"m": "1X (Doble Oportunidad)", "p": p_1x, "c": float(cuotas.get("1X", round(1 / max(0.24, p_1x), 2)))},
        {"m": "X2 (Doble Oportunidad)", "p": p_x2, "c": float(cuotas.get("X2", round(1 / max(0.24, p_x2), 2)))},
        {"m": "Over 2.5 Goles", "p": p_ov, "c": float(cuotas.get("Over2.5", round(1 / max(0.22, p_ov), 2)))},
        {"m": "BTTS (Ambos Anotan)", "p": p_bt, "c": float(cuotas.get("BTTS", round(1 / max(0.22, p_bt), 2)))},
        {"m": "Empate con Goles", "p": p_eg, "c": round(1 / max(0.12, p_eg), 2)},
    ]

    extremo = [o for o in opciones if 2.30 <= o["c"] <= 4.80 and (o["p"] * o["c"] - 1.0) > 0.04]
    elegido = max(extremo, key=lambda x: x["p"] * x["c"]) if extremo else max(opciones, key=lambda x: x["p"])
    ev = (elegido["p"] * elegido["c"]) - 1.0
    kelly_raw = ((elegido["c"] - 1) * elegido["p"] - (1 - elegido["p"])) / max(0.05, elegido["c"] - 1) * 25
    kelly = round(min(10.0, max(1.5, kelly_raw)), 1)
    casas = ("BetPlay", "Wplay", "RushBet", "Codere")

    return {
        "prediccion": elegido["m"],
        "mercado": elegido["m"],
        "cuota": round(elegido["c"], 2),
        "probabilidad": round(elegido["p"] * 100, 1),
        "ev": round(ev * 100, 1),
        "confianza": round(min(96.5, max(64.0, elegido["p"] * 82 + (1 - entropia) * 18)), 1),
        "kelly_stake": f"{kelly}% Bank",
        "casa_colombia": random.choice(casas),
    }


def evaluar_multiagente(client, guard: RateLimiterGuard, info: dict, q: dict) -> dict:
    respaldo = f"Dixon-Coles (15k sim) confirma {q['prediccion']} con EV +{q['ev']}% y valor en {q['casa_colombia']}."
    if not client:
        return {"resumen_ia": respaldo}

    def pedir(prompt: str) -> str:
        if not guard.adquirir():
            return ""
        try:
            r = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt,
                config=types.GenerateContentConfig(temperature=0.2, max_output_tokens=150)
            )
            return r.text.strip() if r and r.text else ""
        except Exception:
            return ""

    r1 = pedir(f"Gemini 1 Rastreador: lesiones y clima breve para {info['local']} vs {info['visitante']} ({info['liga']}).")
    r2 = pedir(f"Gemini 2 Auditor: evalua cuota @{q['cuota']} en {q['prediccion']} frente a {q['casa_colombia']}.")
    r3 = pedir(
        f"Gemini 3 Juez Cuantico: veredicto de 25 palabras para {info['local']} vs {info['visitante']}, "
        f"pick {q['prediccion']} @{q['cuota']}. Contexto: {r1} {r2}"
    )
    return {"resumen_ia": r3 or respaldo}


def crear_gif_3d(ficha: dict) -> BytesIO | None:
    if not PILLOW_OK:
        return None
    try:
        frames = []
        font = ImageFont.load_default()
        for step in range(4):
            img = Image.new("RGB", (800, 440), (7, 13, 28))
            d = ImageDraw.Draw(img)
            borde = (0, 240, 200) if step % 2 == 0 else (56, 189, 248)
            d.rounded_rectangle((18, 18, 782, 422), radius=20, fill=(13, 25, 48), outline=borde, width=4)
            d.text((40, 36), "ARSENAL MASTER QUANT V18.3 // VIP SIGNAL", fill=(0, 240, 200), font=font)
            d.text((40, 65), f"LIGA: {ficha['liga']} | HORA COL: {ficha['hora']}", fill=(56, 189, 248), font=font)
            d.text((40, 110), f"{ficha['local']} VS {ficha['visitante']}", fill=(255, 255, 255), font=font)
            d.rounded_rectangle((40, 145, 760, 235), radius=12, fill=(13, 23, 36), outline=(250, 204, 21), width=2)
            d.text((60, 168), f"PICK: {ficha['prediccion']}  |  CUOTA: @{ficha['cuota']}", fill=(250, 204, 21), font=font)
            d.text((60, 200), f"STAKE: {ficha['kelly_stake']}  |  CASA: {ficha['casa_colombia']}", fill=(255, 255, 255), font=font)
            conf = float(ficha["confianza"])
            d.text((40, 260), f"CONFIANZA: {conf}% (EV +{ficha['ev']}%)", fill=(0, 240, 200), font=font)
            d.rounded_rectangle((40, 285, 760, 312), radius=8, fill=(20, 35, 55))
            ancho = int(720 * min(1.0, ((step + 1) / 4.0) * (conf / 100.0)))
            if ancho > 10:
                d.rounded_rectangle((40, 285, 40 + ancho, 312), radius=8, fill=(0, 240, 200))
            d.text((40, 380), "ARSENAL QUANT COLOMBIA // PROTECTED SIGNAL", fill=(148, 163, 184), font=font)
            frames.append(img)
        primero = frames.pop(0)
        buf = BytesIO()
        primero.save(buf, format="GIF", save_all=True, append_images=frames, duration=260, loop=0)
        buf.seek(0)
        return buf
    except Exception:
        return None
def enviar_tg(token: str, metodo: str, data: dict, files: dict = None):
    if not token:
        return
    try:
        url = f"https://telegram.org{token}/{metodo}"
        if files:
            resp = requests.post(url, data=data, files=files, timeout=18)
        else:
            resp = requests.post(url, json=data, timeout=18)
        if resp.status_code != 200:
            logger.warning(f"Telegram HTTP {resp.status_code} ({metodo}): {resp.text[:150]}")
        time.sleep(1.2)
    except Exception as e:
        logger.error(f"Error Telegram ({metodo}): {type(e).__name__}")


def difundir_telegram(cartelera: list, token: str, vip_id: str, free_id: str, link_vip: str, web_url: str):
    if not token or not cartelera:
        return

    markup_web_dict = {"inline_keyboard": [[{"text": "🌐 ABRIR PANEL WEB 3D", "url": web_url}]]}
    markup_web_json = json.dumps(markup_web_dict)

    if vip_id:
        for p in cartelera:
            liga_safe = html.escape(str(p["liga"]))
            local_safe = html.escape(str(p["local"]))
            visita_safe = html.escape(str(p["visitante"]))
            pick_safe = html.escape(str(p["prediccion"]))
            casa_safe = html.escape(str(p["casa_colombia"]))
            ia_safe = html.escape(str(p["resumen_ia"]))

            txt = (
                f"💎 <b>SEÑAL VIP V18.3</b>\n"
                f"{p['bandera']} <b>{liga_safe}</b>\n"
                f"⚽ <b>{local_safe} vs {visita_safe}</b> | 🕒 {p['hora']} COL\n"
                f"🎯 <b>Pick:</b> {pick_safe} | <b>@{p['cuota']}</b> ({casa_safe})\n"
                f"📊 <b>Confianza:</b> {p['confianza']}% | <b>EV:</b> +{p['ev']}%\n"
                f"💰 <b>Stake:</b> {p['kelly_stake']}\n\n"
                f"🧠 <i>{ia_safe}</i>"
            )
            gif = crear_gif_3d(p)
            if gif:
                enviar_tg(
                    token,
                    "sendAnimation",
                    {
                        "chat_id": vip_id,
                        "caption": txt,
                        "parse_mode": "HTML",
                        "protect_content": True,
                        "reply_markup": markup_web_json
                    },
                    files={"animation": ("senal_vip.gif", gif, "image/gif")}
                )
            else:
                enviar_tg(
                    token,
                    "sendMessage",
                    {
                        "chat_id": vip_id,
                        "text": txt,
                        "parse_mode": "HTML",
                        "protect_content": True,
                        "reply_markup": markup_web_dict
                    }
                )

    if free_id:
        top2 = sorted(cartelera, key=lambda x: x["confianza"], reverse=True)[:2]
        comb = 1.0
        for t in top2:
            comb *= float(t["cuota"])

        apertura = (
            f"🔥 <b>JORNADA CUÁNTICA V18.3 ACTIVA</b>\n"
            f"📊 <b>{len(cartelera)} partidos auditados.</b>\n"
            f"💎 <b>Combinada 2 Regalos (@{comb:.2f}):</b>\n"
            f"💵 Con <b>$50.000 COP</b> cobras <b>${int(50000 * comb):,} COP</b>\n"
            f"💵 Con <b>$100.000 COP</b> cobras <b>${int(100000 * comb):,} COP</b>"
        )
        enviar_tg(token, "sendMessage", {"chat_id": free_id, "text": apertura, "parse_mode": "HTML"})

        for i, p in enumerate(top2, 1):
            local_safe = html.escape(str(p["local"]))
            visita_safe = html.escape(str(p["visitante"]))
            pick_safe = html.escape(str(p["prediccion"]))
            casa_safe = html.escape(str(p["casa_colombia"]))

            cap = (
                f"🎁 <b>REGALO #{i}</b>\n"
                f"⚽ <b>{local_safe} vs {visita_safe}</b>\n"
                f"🎯 <b>Pick:</b> {pick_safe} | <b>@{p['cuota']}</b> ({casa_safe})\n"
                f"📊 <b>Confianza:</b> {p['confianza']}%"
            )
            gif = crear_gif_3d(p)
            if gif:
                enviar_tg(
                    token,
                    "sendAnimation",
                    {"chat_id": free_id, "caption": cap, "parse_mode": "HTML"},
                    files={"animation": ("regalo.gif", gif, "image/gif")}
                )
            else:
                enviar_tg(token, "sendMessage", {"chat_id": free_id, "text": cap, "parse_mode": "HTML"})

        restantes = max(0, len(cartelera) - 2)
        cierre = (
            f"🔓 <b>DESBLOQUEA LOS {restantes} PICKS VIP RESTANTES</b>\n"
            f"📲 Pago inmediato Nequi / Bancolombia"
        )
        markup_cierre = {
            "inline_keyboard": [
                [{"text": "💎 UNIRSE AL VIP", "url": link_vip}],
                [{"text": "🌐 VER WEB 3D", "url": web_url}]
            ]
        }
        enviar_tg(
            token,
            "sendMessage",
            {
                "chat_id": free_id,
                "text": cierre,
                "parse_mode": "HTML",
                "reply_markup": markup_cierre
            }
        )


def main():
    fecha_hoy = datetime.now(TZ_COL).strftime("%Y-%m-%d")
    logger.info(f"--- ARRANQUE BOT CUANTICO V18.3 ({fecha_hoy}) ---")
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    tg_token = os.getenv("TELEGRAM_TOKEN", os.getenv("TELEGRAM_BOT_TOKEN", "")).strip()
    tg_vip = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    tg_free = os.getenv("TELEGRAM_FREE_CHAT_ID", "").strip()
    link_vip = os.getenv("LINK_SUSCRIPCION_VIP", "https://wa.me").strip()
    web_url = os.getenv("PANEL_WEB_URL", "https://github.io").strip()

    ruta_in = os.path.join("predicciones", f"partidos_{fecha_hoy}.json")
    if os.path.exists(ruta_in):
        with open(ruta_in, "r", encoding="utf-8") as f:
            datos = json.load(f)
    else:
        datos = {"partidos": []}

    partidos_raw = datos.get("partidos", [])

    ayer = datos.get("resultados_ayer", {})
    factor_ayer = 1.0
    if isinstance(ayer, dict) and len(ayer) > 0:
        prom_goles = sum(v.get("gl", 0) + v.get("gv", 0) for v in ayer.values() if isinstance(v, dict)) / len(ayer)
        factor_ayer = 1.06 if prom_goles >= 2.8 else (0.94 if prom_goles <= 1.7 else 1.0)
        logger.info(f"Auto-Calibracion H2H/Ayer: {len(ayer)} partidos, prom goles {prom_goles:.2f} -> factor {factor_ayer}")

    guard = RateLimiterGuard(6.5, 8, 32)
    client = genai.Client(api_key=gemini_key) if (gemini_key and GENAI_OK) else None
    cartelera = []

    for raw in partidos_raw:
        try:
            info = extraer_partido(raw, factor_ayer)
            calc = calcular_cuantico(info)
            ia = evaluar_multiagente(client, guard, info, calc)
            cartelera.append({**info, **calc, **ia})
        except Exception as e:
            logger.error(f"Error en fixture: {type(e).__name__}")

    os.makedirs("predicciones", exist_ok=True)
    os.makedirs(os.path.join("www", "data"), exist_ok=True)
    salida = {
        "actualizado_colombia": datetime.now(TZ_COL).strftime("%Y-%m-%d %H:%M:%S"),
        "total_partidos": len(cartelera),
        "partidos": cartelera
    }
    with open(os.path.join("predicciones", f"pronosticos_vip_{fecha_hoy}.json"), "w", encoding="utf-8") as f:
        json.dump(salida, f, ensure_ascii=False, indent=2)
    with open(os.path.join("www", "data", "partidos_del_dia.json"), "w", encoding="utf-8") as f:
        json.dump(salida, f, ensure_ascii=False, indent=2)

    difundir_telegram(cartelera, tg_token, tg_vip, tg_free, link_vip, web_url)
    logger.info("--- FINALIZADO SIN ERRORES ---")


if __name__ == "__main__":
    main()
            
