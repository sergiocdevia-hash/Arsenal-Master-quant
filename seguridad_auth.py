from datetime import datetime, timedelta
from jose import jwt
from passlib.context import CryptContext
from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm

# 1. Configuración de seguridad (Llave secreta para cifrar los tokens)
SECRET_KEY = "MI_LLAVE_SECRETA_SUPER_EXTREMA_Y_CONFIDENCIAL_1992"
ALGORITHM = "HS256"
TOKEN_EXPIRATION_MINUTES = 30

# Motor para encriptar contraseñas
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

app = FastAPI(title="Sistema de Autenticación Blindado")

# Base de datos simulada (Contraseña encriptada para el usuario 'Andres')
Contrasena_Cifrada_Andres = pwd_context.hash("Hackme123*")
USUARIOS_DB = {
    "Andres": {
        "username": "Andres",
        "email": "andres@correo.com",
        "hash_password": Contrasena_Cifrada_Andres
    }
}

# 2. Función para crear el Token JWT (Pase digital)
def crear_token_acceso(data: dict):
    datos_a_cifrar = data.copy()
    tiempo_expiracion = datetime.utcnow() + timedelta(minutes=TOKEN_EXPIRATION_MINUTES)
    datos_a_cifrar.update({"exp": tiempo_expiracion})
    token_cifrado = jwt.encode(datos_a_cifrar, SECRET_KEY, algorithm=ALGORITHM)
    return token_cifrado

# 3. Ruta de Login (Verifica credenciales y entrega el Token)
@app.post("/login")
def iniciar_sesion(form_data: OAuth2PasswordRequestForm = Depends()):
    usuario_encontrado = USUARIOS_DB.get(form_data.username)
    if not usuario_encontrado:
        raise HTTPException(status_code=400, detail="Usuario o contraseña incorrectos")
    
    # Comparamos matemáticamente la contraseña escrita con la encriptada
    if not pwd_context.verify(form_data.password, usuario_encontrado["hash_password"]):
        raise HTTPException(status_code=400, detail="Usuario o contraseña incorrectos")
    
    # Si todo está bien, generamos su pase digital de acceso
    token_digital = crear_token_acceso(data={"sub": form_data.username})
    return {"access_token": token_digital, "token_type": "bearer", "mensaje": "¡Sesión iniciada de forma segura!"}

# 4. Ruta Protegida (Solo entra quien tenga un Token válido)
@app.get("/datos-privados")
def ver_zona_secreta(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        usuario: str = payload.get("sub")
        if usuario is None:
            raise HTTPException(status_code=401, detail="Token inválido")
    except:
        raise HTTPException(status_code=401, detail="Token expirado o corrupto")
        
    return {
        "estatus": "Acceso Autorizado",
        "contenido": "Esta es información confidencial del servidor protegida por criptografía.",
        "usuario_activo": usuario
    }
