"""
rutas_acceso.py  ·  PÁGINA DE INICIO, REGISTRO E INGRESO
Aquí está lo que ve TODO el mundo antes de entrar:
  /                 -> elegir si eres cliente, proveedor o administrador
  /acceso/<rol>     -> ingresar (si ya tienes cuenta) o ir a registrarte
  /registro/<rol>   -> formulario de registro; pide DATOS DISTINTOS según el rol
  /cuenta           -> ver mis datos y cambiar mi contraseña
"""
import hmac
import re
import sqlite3
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, abort, g
from werkzeug.security import generate_password_hash, check_password_hash

import config
import base_datos as bd
import validaciones as v
from seguridad import rol_requerido

acceso = Blueprint("acceso", __name__)

ROLES = {"cliente": "Cliente", "proveedor": "Proveedor", "administrador": "Administrador"}
PANEL = {"cliente": "cliente.inicio", "proveedor": "proveedor.inicio", "administrador": "admin.resumen"}
# Clave falsa: se usa para que tardar lo mismo aunque el usuario no exista (no revela quién tiene cuenta)
CLAVE_FALSA = generate_password_hash("clave-falsa-123")


@acceso.route("/")
def inicio():
    return render_template("inicio.html", roles=ROLES)


# ===================== INGRESAR =====================
@acceso.route("/acceso/<rol>", methods=["GET", "POST"])
def entrar(rol):
    if rol not in ROLES:
        abort(404)
    if request.method == "POST":
        usuario = v.texto(request.form.get("usuario"), 30).lower()
        clave = request.form.get("clave", "")
        # Bloqueo: 5 fallos seguidos en 15 minutos con el mismo usuario
        fallos = bd.uno("SELECT COUNT(*) n FROM bitacora WHERE accion='login_fallido' AND detalle=? AND fecha>?",
                        (usuario, bd.hace(15)))["n"]
        if fallos >= 5:
            flash("Demasiados intentos fallidos. Espera 15 minutos e inténtalo de nuevo.", "error")
            return render_template("acceso.html", rol=rol, nombre_rol=ROLES[rol])
        u = bd.uno("SELECT * FROM usuarios WHERE usuario=?", (usuario,))
        clave_buena = check_password_hash(u["clave_hash"] if u else CLAVE_FALSA, clave)
        if not (u and u["activo"] and clave_buena):
            bd.bitacora(usuario or "(vacío)", "login_fallido", usuario)
            flash("Usuario o contraseña incorrectos.", "error")
        elif u["rol"] != rol:
            # La clave es correcta, pero entró por el botón equivocado: se le indica el correcto.
            flash(f"Esa cuenta es de tipo «{ROLES[u['rol']]}». Entra por esa opción.", "aviso")
            return redirect(url_for("acceso.entrar", rol=u["rol"]))
        else:
            if rol == "proveedor" and bd.uno("SELECT estado FROM proveedores WHERE usuario_id=?", (u["id"],))["estado"] == "suspendido":
                flash("Tu cuenta está suspendida. Comunícate con Merakié.", "error")
                return render_template("acceso.html", rol=rol, nombre_rol=ROLES[rol])
            session.clear()                      # sesión nueva (más seguro)
            session["uid"] = u["id"]
            session.permanent = True             # recuerda la sesión: no pide la clave en cada visita
            bd.bitacora(u["usuario"], "login_ok", rol)
            flash(f"¡Hola, {u['nombre']}!", "ok")
            return redirect(url_for(PANEL[rol]))
    return render_template("acceso.html", rol=rol, nombre_rol=ROLES[rol])


@acceso.route("/salir", methods=["POST"])
def salir():
    session.clear()
    flash("Sesión cerrada.", "ok")
    return redirect(url_for("acceso.inicio"))


# ===================== REGISTRARSE =====================
def _cuenta_comun(f, telefono_obligatorio):
    """Revisa los datos que TODAS las cuentas tienen. Devuelve (error, datos_limpios)."""
    d = {"nombre": v.texto(f.get("nombre"), 80), "correo": v.texto(f.get("correo"), 120).lower(),
         "telefono": v.texto(f.get("telefono"), 20), "usuario": v.texto(f.get("usuario"), 30)}
    clave, repetir = f.get("clave", ""), f.get("clave2", "")
    if len(d["nombre"]) < 3:
        return "Escribe el nombre completo.", d
    if not v.correo_ok(d["correo"]):
        return "El correo no es válido.", d
    if (telefono_obligatorio or d["telefono"]) and not v.telefono_ok(d["telefono"]):
        return "El teléfono no es válido (ej. 3109876543).", d
    if not v.usuario_ok(d["usuario"]):
        return "El usuario debe tener de 3 a 30 caracteres: letras, números, punto, guion o guion bajo.", d
    if not v.clave_ok(clave):
        return "La contraseña debe tener mínimo 8 caracteres, con letras y números.", d
    if clave != repetir:
        return "Las dos contraseñas no coinciden.", d
    if bd.uno("SELECT 1 FROM usuarios WHERE usuario=?", (d["usuario"],)):
        return "Ese nombre de usuario ya existe. Elige otro (o usa «Ya tengo cuenta»).", d
    if bd.uno("SELECT 1 FROM usuarios WHERE correo=?", (d["correo"],)):
        return "Ya existe una cuenta con ese correo. Usa «Ya tengo cuenta».", d
    d["clave_hash"] = generate_password_hash(clave)   # se guarda la 'huella', nunca la clave
    return None, d


def _insertar_usuario(con, rol, d):
    cur = con.execute("INSERT INTO usuarios(rol,usuario,nombre,correo,telefono,clave_hash,creado) VALUES(?,?,?,?,?,?,?)",
                      (rol, d["usuario"], d["nombre"], d["correo"], d["telefono"], d["clave_hash"], bd.ahora()))
    return cur.lastrowid


def _registrar_cliente(f):
    error, d = _cuenta_comun(f, telefono_obligatorio=True)
    if error:
        return error
    edad = v.entero(f.get("edad"))
    documento = v.texto(f.get("documento"), 20)
    if not 18 <= edad <= 100:
        return "La edad debe estar entre 18 y 100 años."
    if documento and not re.fullmatch(r"[0-9A-Za-z.-]{5,20}", documento):
        return "El documento no es válido."
    if not f.get("consentimiento"):
        return "Debes autorizar el tratamiento de tus datos personales para crear la cuenta."
    con = bd.db()
    try:
        uid = _insertar_usuario(con, "cliente", d)
        con.execute("INSERT INTO clientes(usuario_id,documento,edad,consentimiento_fecha,consentimiento_version) VALUES(?,?,?,?,?)",
                    (uid, documento, edad, bd.ahora(), config.VERSION_CONSENTIMIENTO))
        con.commit()
    except sqlite3.IntegrityError:
        con.rollback()
        return "Ese usuario o correo ya está registrado."
    bd.bitacora(d["usuario"], "registro_cliente")


def _registrar_proveedor(f):
    error, d = _cuenta_comun(f, telefono_obligatorio=True)
    if error:
        return error
    p = {"tipo": f.get("tipo_persona"), "razon": v.texto(f.get("razon_social"), 120),
         "comercial": v.texto(f.get("nombre_comercial"), 80), "ciudad": v.texto(f.get("ciudad"), 60),
         "direccion": v.texto(f.get("direccion"), 150)}
    if p["tipo"] not in ("juridica", "natural"):
        return "Indica si eres persona jurídica o natural."
    if len(p["razon"]) < 3 or len(p["comercial"]) < 2:
        return "Escribe la razón social (o tu nombre completo) y el nombre comercial del salón."
    if not v.nit_ok(f.get("nit", "")):
        return "El NIT o su dígito de verificación no es válido (ejemplo: 800197268-4)."
    nit = v.normalizar_nit(f.get("nit"))
    if len(p["ciudad"]) < 2 or len(p["direccion"]) < 5:
        return "Indica la ciudad y la dirección del salón."
    if not f.get("consentimiento"):
        return "Debes autorizar el tratamiento de datos personales para registrarte."
    if bd.uno("SELECT 1 FROM proveedores WHERE nit=?", (nit,)):
        return "Ya existe un proveedor registrado con ese NIT. Si es tuyo, usa «Ya tengo cuenta» o escríbenos."
    con = bd.db()
    try:
        uid = _insertar_usuario(con, "proveedor", d)
        t = bd.ahora()
        con.execute("""INSERT INTO proveedores(usuario_id,tipo_persona,razon_social,nombre_comercial,nit,ciudad,direccion,
                       consentimiento_fecha,consentimiento_version,creado) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (uid, p["tipo"], p["razon"], p["comercial"], nit, p["ciudad"], p["direccion"], t, config.VERSION_CONSENTIMIENTO, t))
        for dia in range(7):                             # horario inicial: lunes a sábado 9:00-18:00
            con.execute("INSERT INTO horarios(proveedor_id,dia,cerrado,abre,cierra) VALUES(?,?,?,?,?)",
                        (uid, dia, 1 if dia == 0 else 0, "09:00", "18:00"))
        con.commit()
    except sqlite3.IntegrityError:
        con.rollback()
        return "Ese usuario, correo o NIT ya está registrado."
    bd.bitacora(d["usuario"], "registro_proveedor", f"NIT {nit}")


def _registrar_administrador(f):
    # Frena la adivinación del código: 5 intentos fallidos por IP en 15 minutos
    if bd.uno("SELECT COUNT(*) n FROM bitacora WHERE accion='admin_codigo_incorrecto' AND ip=? AND fecha>?",
              (request.remote_addr, bd.hace(15)))["n"] >= 5:
        return "Demasiados intentos con el código. Espera 15 minutos."
    autorizados = {v.normalizar_nombre(n): n for n in config.ADMINS_AUTORIZADOS}
    nombre_ok = autorizados.get(v.normalizar_nombre(f.get("nombre", "")))
    if not nombre_ok:
        bd.bitacora("(desconocido)", "admin_nombre_no_autorizado", v.texto(f.get("nombre"), 80))
        return "Ese nombre no está en la lista de administradores autorizados."
    if not hmac.compare_digest(str(f.get("codigo", "")), config.CODIGO_ADMIN):
        bd.bitacora(nombre_ok, "admin_codigo_incorrecto")
        return "El código de administrador es incorrecto."
    if bd.uno("SELECT 1 FROM usuarios WHERE rol='administrador' AND nombre=?", (nombre_ok,)):
        return "Esa persona ya tiene cuenta de administrador. Usa «Ya tengo cuenta»."
    f = {**f.to_dict(), "nombre": nombre_ok}             # se guarda el nombre oficial (con tildes)
    error, d = _cuenta_comun(f, telefono_obligatorio=False)
    if error:
        return error
    con = bd.db()
    try:
        _insertar_usuario(con, "administrador", d)
        con.commit()
    except sqlite3.IntegrityError:
        con.rollback()
        return "Ese usuario o correo ya está registrado."
    bd.bitacora(d["usuario"], "registro_administrador", nombre_ok)


@acceso.route("/registro/<rol>", methods=["GET", "POST"])
def registro(rol):
    if rol not in ROLES:
        abort(404)
    if request.method == "POST":
        registrar = {"cliente": _registrar_cliente, "proveedor": _registrar_proveedor,
                     "administrador": _registrar_administrador}[rol]
        error = registrar(request.form)
        if error is None:
            flash("¡Cuenta creada! Ahora ingresa con tu usuario y contraseña.", "ok")
            return redirect(url_for("acceso.entrar", rol=rol))
        flash(error, "error")
    return render_template("registro.html", rol=rol, nombre_rol=ROLES[rol], d=request.form, admins=config.ADMINS_AUTORIZADOS)


# ===================== MI CUENTA (todos los roles) =====================
@acceso.route("/cuenta")
def cuenta():
    if g.usuario is None:
        return redirect(url_for("acceso.inicio"))
    u = g.usuario
    extra = None
    if u["rol"] == "cliente":
        extra = bd.uno("SELECT * FROM clientes WHERE usuario_id=?", (u["id"],))
    elif u["rol"] == "proveedor":
        extra = bd.uno("SELECT * FROM proveedores WHERE usuario_id=?", (u["id"],))
    return render_template("cuenta.html", extra=extra)


@acceso.route("/cuenta/clave", methods=["POST"])
def cambiar_clave():
    if g.usuario is None:
        return redirect(url_for("acceso.inicio"))
    actual, nueva, repetir = request.form.get("actual", ""), request.form.get("nueva", ""), request.form.get("repetir", "")
    if not check_password_hash(g.usuario["clave_hash"], actual):
        flash("La contraseña actual no es correcta.", "error")
    elif not v.clave_ok(nueva):
        flash("La nueva contraseña debe tener mínimo 8 caracteres, con letras y números.", "error")
    elif nueva != repetir:
        flash("Las contraseñas nuevas no coinciden.", "error")
    else:
        bd.ejecutar("UPDATE usuarios SET clave_hash=? WHERE id=?", (generate_password_hash(nueva), g.usuario["id"]))
        bd.bitacora(g.usuario["usuario"], "cambio_clave")
        flash("Contraseña actualizada.", "ok")
    return redirect(url_for("acceso.cuenta"))
