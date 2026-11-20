"""
seguridad.py  ·  PROTECCIONES COMUNES A TODA LA PLATAFORMA
  - csrf: evita que otra página engañe al navegador para enviar formularios en nombre del usuario
  - rol_requerido: cada parte (cliente / proveedor / administrador) solo la ve quien corresponde
"""
import secrets
from functools import wraps
from flask import session, request, g, redirect, url_for, flash, abort


# ---------- CSRF ----------
def csrf_token():
    """Cada sesión tiene un código secreto. Se pone escondido en CADA formulario."""
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_hex(16)
    return session["_csrf"]


def verificar_csrf():
    """Antes de aceptar cualquier formulario (POST) se revisa que traiga el código correcto."""
    if request.method == "POST":
        enviado = request.form.get("_csrf", "")
        if not enviado or not secrets.compare_digest(enviado, session.get("_csrf", "")):
            abort(400, "El formulario expiró o no es válido. Recarga la página e inténtalo de nuevo.")


# ---------- Roles ----------
def rol_requerido(rol):
    """Decorador: se pone encima de una ruta para exigir un tipo de usuario.
    Ejemplo:  @rol_requerido("cliente")  -> solo entran clientes con sesión iniciada."""
    def decorador(funcion):
        @wraps(funcion)
        def interna(*args, **kwargs):
            if g.usuario is None:
                flash("Inicia sesión para continuar.", "aviso")
                return redirect(url_for("acceso.entrar", rol=rol))
            if g.usuario["rol"] != rol:
                abort(403)
            return funcion(*args, **kwargs)
        return interna
    return decorador
