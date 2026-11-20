"""
validaciones.py  ·  FUNCIONES PARA REVISAR LO QUE ESCRIBE LA GENTE
Nunca se confía en lo que llega de un formulario: siempre se revisa en el servidor.
Cada función devuelve True/False (o el dato ya limpio).
"""
import re
import unicodedata
from datetime import datetime


def texto(valor, maximo):
    """Quita espacios sobrantes y corta el texto al largo máximo."""
    return str(valor or "").strip()[:maximo]


def normalizar_nombre(s):
    """'  Santiago   MUÑOZ ' -> 'santiago munoz'  (para comparar nombres sin tildes ni mayúsculas)."""
    sin_tildes = "".join(c for c in unicodedata.normalize("NFD", str(s)) if unicodedata.category(c) != "Mn")
    return " ".join(sin_tildes.lower().split())


def correo_ok(c):
    return bool(re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]{2,}", c)) and len(c) <= 120


def telefono_ok(t):
    limpio = re.sub(r"[\s-]", "", str(t))
    return bool(re.fullmatch(r"(\+?57)?3\d{9}", limpio) or re.fullmatch(r"\d{7,10}", limpio))


def usuario_ok(u):
    """3 a 30 caracteres: letras, números, punto, guion y guion bajo."""
    return bool(re.fullmatch(r"[A-Za-z0-9._-]{3,30}", u))


def clave_ok(c):
    """Mínimo 8 caracteres, con al menos una letra y un número."""
    return 8 <= len(c) <= 128 and bool(re.search(r"[A-Za-z]", c)) and bool(re.search(r"\d", c))


def fecha_ok(f):
    try:
        datetime.strptime(str(f), "%Y-%m-%d")
        return True
    except ValueError:
        return False


def hora_ok(h):
    return bool(re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", str(h)))


def a_minutos(hhmm):
    """'09:30' -> 570  (minutos desde la medianoche; facilita sumar y comparar horas)."""
    return int(hhmm[:2]) * 60 + int(hhmm[3:5])


def de_minutos(m):
    """570 -> '09:30'"""
    return f"{m // 60:02d}:{m % 60:02d}"


def normalizar_nit(crudo):
    """'800.197.268 4' -> '800197268-4'. Devuelve None si no tiene el formato correcto."""
    m = re.fullmatch(r"(\d{6,15})-?(\d)", re.sub(r"[.\s]", "", str(crudo)))
    return f"{m.group(1)}-{m.group(2)}" if m else None


def nit_ok(crudo):
    """Revisa el dígito de verificación del NIT con el algoritmo de la DIAN (módulo 11)."""
    nit = normalizar_nit(crudo)
    if not nit:
        return False
    cuerpo, dv = nit.split("-")
    pesos = [3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71]
    suma = sum(int(d) * pesos[i] for i, d in enumerate(reversed(cuerpo)))
    r = suma % 11
    return (11 - r if r > 1 else r) == int(dv)


def entero(valor, defecto=0):
    """Convierte a número entero sin romper el programa si viene vacío o con letras."""
    try:
        return int(float(str(valor).strip()))
    except (ValueError, TypeError):
        return defecto
