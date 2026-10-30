import numpy as np

def motor_analisis_avanzado(cuota_local, cuota_empate, cuota_visita, cuota_mas_goles, cuota_menos_goles, nombre_l, nombre_v, goles_proyectados_total):
    # 1. Extracción y Limpieza del Margen de la Casa (Overround)
    prob_implicita_l = 1 / cuota_local
    prob_implicita_e = 1 / cuota_empate
    prob_implicita_v = 1 / cuota_visita
    total_mercado = prob_implicita_l + prob_implicita_e + prob_implicita_v
    
    # Probabilidades puras del partido sin la trampa de la casa
    prob_real_l = (prob_implicita_l / total_mercado) * 100
    prob_real_e = (prob_implicita_e / total_mercado) * 100
    prob_real_v = (prob_implicita_v / total_mercado) * 100
    
    # 2. Análisis del Mercado de Goles (Over/Under 2.5)
    total_goles_mercado = (1 / cuota_mas_goles) + (1 / cuota_menos_goles)
    prob_mas_goles = ((1 / cuota_mas_goles) / total_goles_mercado) * 100
    
    # 3. Determinación del Escenario Más Probable (Predicción Pura)
    probabilidades = [prob_real_l, prob_real_e, prob_real_v]
    opciones = [f"GANADOR {nombre_l}", "EMPATE", f"GANADOR {nombre_v}"]
    indice_favorito = np.argmax(probabilidades)
    evento_principal = opciones[indice_favorito]
    probabilidad_principal = probabilidades[indice_favorito]
    
    # Pronóstico de la línea de anotación
    pronostico_goles = "MÁS DE 2.5 GOLES" if prob_mas_goles > 50 or goles_proyectados_total >= 2.5 else "MENOS DE 2.5 GOLES"
    prob_goles_final = prob_mas_goles if pronostico_goles == "MÁS DE 2.5 GOLES" else (100 - prob_mas_goles)

    print("=" * 65)
    print(f"🕵️‍♂️ DETECTOR DE FALLAS ACTIVADO: {nombre_l} vs {nombre_v}")
    print("=" * 65)
    print(f"📊 PROYECCIÓN ESTADÍSTICA DEL ENCUENTRO:")
    print(f"   • Tendencia Principal: {evento_principal} ({probabilidad_principal:.1f}%)")
    print(f"   • Tendencia de Goles: {pronostico_goles} ({prob_goles_final:.1f}%)")
    print("-" * 65)
    print("🎯 DICTAMEN DE OPERACIÓN CONTRA LA CASA:")

    # 4. Buscador de Asimetría (Fallas de cuota en base al flujo del mercado)
    falla_detectada = False
    
    # Si la probabilidad real es alta y la casa ofrece una cuota competitiva por el favorito
    if probabilidad_principal > 65.0 and (100 / probabilidad_principal) <= cuota_local if indice_favorito==0 else cuota_visita:
        print(f"🟢 [APUESTA RECOMENDADA]: CONFIRMAR FAVORITO -> {evento_principal} + {pronostico_goles}")
        print(f"   Motivo: La casa sabe que este resultado es altamente probable, el margen es óptimo.")
        falla_detectada = True
        
    # Identificación de la cuota inflada por saturación del público (Value Betting)
    if cuota_empate > 5.5 and prob_real_e > 15.0:
        print(f"🔥 [ALERTA DE FALLA EN CUOTA]: EL EMPATE TIENE VALOR INVERSO")
        print(f"   Motivo: El público saturó al favorito. La casa infló la cuota del Empate a {cuota_empate} por protección.")
        falla_detectada = True

    if not falla_detectada:
        print("❌ [OMITIR MERCADO]: Las líneas están equilibradas. No arriesgar capital aquí.")
    print("=" * 65 + "\n")

# PROCESAMIENTO JORNADA DE MAÑANA (Datos cruzados: Cuotas 1X2, Cuotas Goles, Nombres, Proyección de Goles)
motor_analisis_avanzado(12.50, 7.30, 1.21, 1.45, 2.70, "Elche", "Real Madrid", 3.1)
motor_analisis_avanzado(1.88, 3.40, 4.70, 2.10, 1.70, "Alavés", "Valencia", 2.1)
motor_analisis_avanzado(2.30, 3.55, 3.10, 1.95, 1.85, "Rayo Vallecano", "Espanyol", 2.3)
