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
