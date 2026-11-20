"""
config.py  ·  AJUSTES DE LA PLATAFORMA
Aquí van los valores que pueden cambiar sin tocar el resto del código.
"""
import os
import secrets
from pathlib import Path

# ---------- Carpetas ----------
CARPETA = Path(__file__).resolve().parent                       # carpeta donde está este archivo
CARPETA_DATOS = Path(os.environ.get("MERAKIE_DATOS", CARPETA / "datos"))
CARPETA_DOCS = CARPETA_DATOS / "documentos"                     # aquí se guardan RUT, cédulas, etc.
BASE_DATOS = CARPETA_DATOS / "merakie.db"                       # el archivo de la base de datos
CARPETA_DOCS.mkdir(parents=True, exist_ok=True)                 # se crean solas si no existen

# ---------- Administradores ----------
# SOLO estas dos personas pueden crear una cuenta de administrador.
ADMINS_AUTORIZADOS = ["Santiago Muñoz", "Nicole Ramirez"]
MERAKIE_CODIGO_ADMIN=mi-codigo-largo
CODIGO_ADMIN = os.environ.get("MERAKIE_CODIGO_ADMIN", "MERAKIE-ADMIN-2026")

# ---------- Reglas del negocio ----------
DIAS_SESION = 7                     # la sesión dura 7 días: no piden la clave a cada rato
VERSION_CONSENTIMIENTO = "2026-11"  # versión de la política de datos que aceptó la persona
UMBRAL_PAGO_ALTO = 500000           # pagos desde este valor generan una alerta de revisión (COP)
DESCUENTO_PASS = 0.05               # 5 % de descuento en productos para quien tiene Merakié Pass
PASO_CITAS = 30                     # las citas empiezan cada 30 minutos
MAX_DIAS_ANTICIPACION = 90          # no se agenda con más de 90 días de anticipación

CATEGORIAS = ["Peluquería", "Barbería", "Uñas", "Maquillaje", "Estética facial",
              "Estética corporal", "Depilación", "Spa y masajes", "Cejas y pestañas", "Otros"]
TIPOS_DOCUMENTO = {"rut": "RUT", "camara_comercio": "Certificado de Cámara de Comercio",
                   "cedula": "Cédula del titular", "concepto_sanitario": "Concepto sanitario",
                   "otro": "Otro documento"}


def clave_secreta():
    """Flask necesita una 'clave secreta' para firmar la sesión (la cookie).
    Se genera una sola vez, se guarda en datos/clave_secreta.txt y se reutiliza."""
    archivo = CARPETA_DATOS / "clave_secreta.txt"
    if not archivo.exists():
        archivo.write_text(secrets.token_hex(32))
    return archivo.read_text().strip()
