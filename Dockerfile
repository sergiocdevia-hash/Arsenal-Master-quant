# 1. Usamos una imagen oficial de Python ligera como base
FROM python:3.10-slim

# 2. Creamos y nos movemos a la carpeta de trabajo dentro del contenedor
WORKDIR /app

# 3. Instalamos las librerías necesarias de forma directa
RUN pip install --no-cache-dir fastapi uvicorn requests python-jose[cryptography] passlib[bcrypt] beautifulsoup4

# 4. Copiamos todos tus scripts de ciberseguridad dentro del contenedor
COPY automatizacion.py mi_api.py alertas_telegram.py extractor.py seguridad_auth.py ./

# 5. Comando por defecto para arrancar tu API de seguridad cuando el contenedor se encienda
CMD ["uvicorn", "mi_api:app", "--host", "0.0.0.0", "--port", "8000"]
