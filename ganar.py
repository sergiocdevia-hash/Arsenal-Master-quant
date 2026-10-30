import math

def calcular_empate(equipo_l, equipo_v, xg_local, xg_vis, cuota_betplay):
    rho = -0.05
    prob_empate = 0.0
    for i in range(6):
        p_local = (math.exp(-xg_local) * (xg_local**i)) / math.factorial(i)
        p_vis = (math.exp(-xg_vis) * (xg_vis**i)) / math.factorial(i)
        if i == 0: factor = 1 - (xg_local * xg_vis * rho)
        elif i == 1: factor = 1 - rho
        else: factor = 1.0
        prob_empate += (p_local * p_vis) * factor
    
    cuota_justa = 1 / prob_empate
    print(f"\n⚽ {equipo_l} vs {equipo_v}")
    print(f"   [+] PROB. REAL: {prob_empate*100:.1f}% | CUOTA JUSTA: {cuota_justa:.2f} | BETPLAY: {cuota_betplay}")
    
    if cuota_betplay > cuota_justa:
        ventaja = (cuota_betplay / cuota_justa) - 1
        print(f"   --> ¡VENTAJA MATEMÁTICA DETECTADA! (+{ventaja*100:.1f}% EV)")
    else:
        print("   --> SIN VENTAJAS. La casa está protegida.")

def escanear_jornada():
    print("="*55)
    print("   ESCÁNER AUTOMÁTICO: LA LIGA & COPA LIBERTADORES")
    print("="*55)
    
    # Base de datos simulada en tiempo real (Equipos, xG Local, xG Vis, Cuota)
    partidos = [
        # LALIGA ESPAÑA
        ("Rayo Vallecano", "Espanyol", 1.34, 0.98, 3.45),
        ("Alavés", "Valencia", 1.20, 1.10, 3.15),
        ("Atlético de Madrid", "Osasuna", 1.75, 0.85, 3.80),
        ("Barcelona", "Racing de Santander", 2.30, 0.65, 4.50),
        
        # COPA LIBERTADORES (CUARTOS DE FINAL)
        ("Platense", "Fluminense", 1.05, 1.15, 2.95),
        ("LDU Quito", "Palmeiras", 1.40, 1.10, 3.35),
        ("Corinthians", "Estudiantes de La Plata", 1.25, 0.90, 3.10),
        ("Flamengo", "Independiente del Valle", 1.65, 0.95, 3.60)
    ]
    
    for p in partidos:
        calcular_empate(p[0], p[1], p[2], p[3], p[4])
    print("="*55 + "\n")

if __name__ == '__main__':
    escanear_jornada()
