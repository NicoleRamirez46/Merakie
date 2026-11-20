"""
rutas_proveedor.py  ·  EL PANEL DEL PROVEEDOR (SALÓN)
Inicio · Mi salón · Servicios · Productos · Horarios · Citas · Documentos
Regla de oro: TODA consulta filtra por proveedor_id = id del proveedor con sesión.
Así un proveedor nunca puede ver ni tocar los datos de otro.
"""
import secrets
from flask import Blueprint, render_template, request, redirect, url_for, flash, g, jsonify, abort, send_from_directory

import config
import base_datos as bd
import validaciones as v
import agenda
from seguridad import rol_requerido

proveedor = Blueprint("proveedor", __name__, url_prefix="/proveedor")

ORDEN_SEMANA = [1, 2, 3, 4, 5, 6, 0]       # se muestra de lunes a domingo
NOMBRE_DIA = {0: "Domingo", 1: "Lunes", 2: "Martes", 3: "Miércoles", 4: "Jueves", 5: "Viernes", 6: "Sábado"}
FLUJO_CITAS = {"pendiente": ["confirmada", "rechazada"], "confirmada": ["completada", "no_asistio", "cancelada"]}


def _yo():
    return g.usuario["id"]


def _perfil():
    return bd.uno("SELECT * FROM proveedores WHERE usuario_id=?", (_yo(),))


def _documentos_requeridos(p):
    """Persona jurídica: RUT + Cámara de Comercio. Persona natural: RUT + cédula."""
    return "camara_comercio" if p["tipo_persona"] == "juridica" else "cedula"


# ===================== INICIO =====================
@proveedor.route("/")
@rol_requerido("proveedor")
def inicio():
    p, hoy = _perfil(), bd.hoy()
    mes = hoy[:7]
    uno = lambda sql, *a: bd.uno(sql, (_yo(), *a))
    tipos = [d["tipo"] for d in bd.todos("SELECT tipo FROM documentos WHERE proveedor_id=?", (_yo(),))]
    pide = _documentos_requeridos(p)
    lista = {"docs": "rut" in tipos and pide in tipos,
             "servicios": uno("SELECT COUNT(*) c FROM servicios WHERE proveedor_id=? AND activo=1")["c"] > 0,
             "horario": uno("SELECT COUNT(*) c FROM horarios WHERE proveedor_id=? AND cerrado=0")["c"] > 0}
    return render_template("proveedor/inicio.html", p=p, lista=lista, pide=pide,
        hoy_n=uno("SELECT COUNT(*) c FROM citas WHERE proveedor_id=? AND fecha=? AND estado IN ('pendiente','confirmada')", hoy)["c"],
        pendientes=uno("SELECT COUNT(*) c FROM citas WHERE proveedor_id=? AND estado='pendiente'")["c"],
        mes_n=uno("SELECT COUNT(*) c FROM citas WHERE proveedor_id=? AND estado='completada' AND fecha LIKE ?", mes + "%")["c"],
        mes_ingresos=uno("SELECT COALESCE(SUM(precio),0) s FROM citas WHERE proveedor_id=? AND estado='completada' AND fecha LIKE ?", mes + "%")["s"],
        tipos_doc=config.TIPOS_DOCUMENTO)


@proveedor.route("/enviar-revision", methods=["POST"])
@rol_requerido("proveedor")
def enviar_revision():
    p = _perfil()
    tipos = [d["tipo"] for d in bd.todos("SELECT tipo FROM documentos WHERE proveedor_id=?", (_yo(),))]
    pide = _documentos_requeridos(p)
    if p["estado"] not in ("pendiente_documentos", "rechazado"):
        flash("Tu cuenta ya está en revisión o verificada.", "aviso")
    elif "rut" not in tipos or pide not in tipos:
        flash(f"Sube el RUT y {config.TIPOS_DOCUMENTO[pide].lower()} para continuar.", "error")
    elif not bd.uno("SELECT 1 FROM servicios WHERE proveedor_id=? AND activo=1", (_yo(),)):
        flash("Agrega al menos un servicio activo.", "error")
    else:
        t = bd.ahora()
        bd.ejecutar("UPDATE proveedores SET estado='en_revision', motivo='', estado_fecha=? WHERE usuario_id=?", (t, _yo()))
        bd.bitacora(g.usuario["usuario"], "proveedor_envia_revision")
        flash("Enviado a revisión. El equipo de Merakié verificará tu información.", "ok")
    return redirect(url_for("proveedor.inicio"))


# ===================== MI SALÓN =====================
@proveedor.route("/salon", methods=["GET", "POST"])
@rol_requerido("proveedor")
def salon():
    if request.method == "POST":
        f = request.form
        d = dict(nombre=v.texto(f.get("nombre"), 80), comercial=v.texto(f.get("nombre_comercial"), 80),
                 telefono=v.texto(f.get("telefono"), 20), ciudad=v.texto(f.get("ciudad"), 60),
                 direccion=v.texto(f.get("direccion"), 150), descripcion=v.texto(f.get("descripcion"), 600),
                 cupos=v.entero(f.get("cupos")))
        if len(d["comercial"]) < 2 or len(d["nombre"]) < 3 or len(d["ciudad"]) < 2 or len(d["direccion"]) < 5:
            flash("Completa nombre comercial, contacto, ciudad y dirección.", "error")
        elif not v.telefono_ok(d["telefono"]):
            flash("El teléfono no es válido.", "error")
        elif not 1 <= d["cupos"] <= 50:
            flash("Los cupos deben estar entre 1 y 50.", "error")
        else:
            bd.db().execute("UPDATE usuarios SET nombre=?, telefono=? WHERE id=?", (d["nombre"], d["telefono"], _yo()))
            bd.db().execute("""UPDATE proveedores SET nombre_comercial=?, ciudad=?, direccion=?, descripcion=?, cupos=?,
                               auto_confirmar=? WHERE usuario_id=?""",
                            (d["comercial"], d["ciudad"], d["direccion"], d["descripcion"], d["cupos"],
                             1 if f.get("auto_confirmar") else 0, _yo()))
            bd.db().commit()
            flash("Datos del salón guardados.", "ok")
        return redirect(url_for("proveedor.salon"))
    return render_template("proveedor/salon.html", p=_perfil())


# ===================== SERVICIOS =====================
@proveedor.route("/servicios")
@rol_requerido("proveedor")
def servicios():
    editar = bd.uno("SELECT * FROM servicios WHERE id=? AND proveedor_id=?", (v.entero(request.args.get("editar")), _yo()))
    lista = bd.todos("SELECT * FROM servicios WHERE proveedor_id=? ORDER BY activo DESC, categoria, nombre", (_yo(),))
    return render_template("proveedor/servicios.html", lista=lista, e=editar, categorias=config.CATEGORIAS)


@proveedor.route("/servicios/guardar", methods=["POST"])
@rol_requerido("proveedor")
def guardar_servicio():
    f = request.form
    d = dict(nombre=v.texto(f.get("nombre"), 80), categoria=f.get("categoria"), descripcion=v.texto(f.get("descripcion"), 400),
             precio=v.entero(f.get("precio"), -1), duracion=v.entero(f.get("duracion_min")), activo=1 if f.get("activo") else 0)
    sid = v.entero(f.get("id"))
    if len(d["nombre"]) < 3:
        flash("Escribe el nombre del servicio.", "error")
    elif d["categoria"] not in config.CATEGORIAS:
        flash("Elige una categoría.", "error")
    elif not 0 <= d["precio"] <= 50_000_000:
        flash("Precio no válido (en pesos, sin puntos).", "error")
    elif not 10 <= d["duracion"] <= 600:
        flash("La duración debe estar entre 10 y 600 minutos.", "error")
    elif sid:
        r = bd.db().execute("""UPDATE servicios SET nombre=?, categoria=?, descripcion=?, precio=?, duracion_min=?, activo=?
                               WHERE id=? AND proveedor_id=?""",
                            (d["nombre"], d["categoria"], d["descripcion"], d["precio"], d["duracion"], d["activo"], sid, _yo()))
        bd.db().commit()
        flash("Servicio actualizado." if r.rowcount else "Servicio no encontrado.", "ok" if r.rowcount else "error")
    else:
        bd.ejecutar("""INSERT INTO servicios(proveedor_id,nombre,categoria,descripcion,precio,duracion_min,activo,creado)
                       VALUES(?,?,?,?,?,?,?,?)""",
                    (_yo(), d["nombre"], d["categoria"], d["descripcion"], d["precio"], d["duracion"], d["activo"], bd.ahora()))
        flash("Servicio agregado.", "ok")
    return redirect(url_for("proveedor.servicios"))


@proveedor.route("/servicios/<int:sid>/eliminar", methods=["POST"])
@rol_requerido("proveedor")
def eliminar_servicio(sid):
    if not bd.uno("SELECT 1 FROM servicios WHERE id=? AND proveedor_id=?", (sid, _yo())):
        abort(404)
    if bd.uno("SELECT 1 FROM citas WHERE servicio_id=?", (sid,)):     # ya tuvo citas: se desactiva, no se borra
        bd.ejecutar("UPDATE servicios SET activo=0 WHERE id=?", (sid,))
        flash("El servicio ya tuvo citas: se desactivó para conservar el historial.", "aviso")
    else:
        bd.ejecutar("DELETE FROM servicios WHERE id=?", (sid,))
        flash("Servicio eliminado.", "ok")
    return redirect(url_for("proveedor.servicios"))


# ===================== PRODUCTOS (para la tienda) =====================
@proveedor.route("/productos")
@rol_requerido("proveedor")
def productos():
    editar = bd.uno("SELECT * FROM productos WHERE id=? AND proveedor_id=?", (v.entero(request.args.get("editar")), _yo()))
    lista = bd.todos("SELECT * FROM productos WHERE proveedor_id=? ORDER BY activo DESC, nombre", (_yo(),))
    return render_template("proveedor/productos.html", lista=lista, e=editar, p=_perfil())


@proveedor.route("/productos/guardar", methods=["POST"])
@rol_requerido("proveedor")
def guardar_producto():
    f = request.form
    d = dict(nombre=v.texto(f.get("nombre"), 80), descripcion=v.texto(f.get("descripcion"), 300),
             precio=v.entero(f.get("precio"), -1), stock=v.entero(f.get("stock"), -1), activo=1 if f.get("activo") else 0)
    pid = v.entero(f.get("id"))
    if len(d["nombre"]) < 3:
        flash("Escribe el nombre del producto.", "error")
    elif not 0 <= d["precio"] <= 50_000_000 or not 0 <= d["stock"] <= 100_000:
        flash("Revisa el precio (en pesos) y las unidades disponibles.", "error")
    elif pid:
        bd.ejecutar("UPDATE productos SET nombre=?, descripcion=?, precio=?, stock=?, activo=? WHERE id=? AND proveedor_id=?",
                    (d["nombre"], d["descripcion"], d["precio"], d["stock"], d["activo"], pid, _yo()))
        flash("Producto actualizado.", "ok")
    else:
        bd.ejecutar("INSERT INTO productos(proveedor_id,nombre,descripcion,precio,stock,activo,creado) VALUES(?,?,?,?,?,?,?)",
                    (_yo(), d["nombre"], d["descripcion"], d["precio"], d["stock"], d["activo"], bd.ahora()))
        flash("Producto agregado. Se mostrará en la tienda cuando tu cuenta esté verificada.", "ok")
    return redirect(url_for("proveedor.productos"))


@proveedor.route("/productos/<int:pid>/eliminar", methods=["POST"])
@rol_requerido("proveedor")
def eliminar_producto(pid):
    if not bd.uno("SELECT 1 FROM productos WHERE id=? AND proveedor_id=?", (pid, _yo())):
        abort(404)
    if bd.uno("SELECT 1 FROM pedido_items WHERE producto_id=?", (pid,)):
        bd.ejecutar("UPDATE productos SET activo=0 WHERE id=?", (pid,))
        flash("El producto ya se vendió: se desactivó para conservar el historial.", "aviso")
    else:
        bd.ejecutar("DELETE FROM productos WHERE id=?", (pid,))
        flash("Producto eliminado.", "ok")
    return redirect(url_for("proveedor.productos"))


# ===================== HORARIOS =====================
@proveedor.route("/horarios")
@rol_requerido("proveedor")
def horarios():
    filas = {h["dia"]: h for h in bd.todos("SELECT * FROM horarios WHERE proveedor_id=?", (_yo(),))}
    cierres = bd.todos("SELECT * FROM cierres WHERE proveedor_id=? AND fecha>=? ORDER BY fecha", (_yo(), bd.hoy()))
    return render_template("proveedor/horarios.html", filas=filas, orden=ORDEN_SEMANA, nombres=NOMBRE_DIA, cierres=cierres)


@proveedor.route("/horarios/guardar", methods=["POST"])
@rol_requerido("proveedor")
def guardar_horarios():
    f, nuevos = request.form, []
    for dia in range(7):
        cerrado = bool(f.get(f"cerrado_{dia}"))
        abre, cierra = f.get(f"abre_{dia}", "09:00"), f.get(f"cierra_{dia}", "18:00")
        if not cerrado and (not v.hora_ok(abre) or not v.hora_ok(cierra) or v.a_minutos(abre) >= v.a_minutos(cierra)):
            flash(f"{NOMBRE_DIA[dia]}: la hora de apertura debe ser anterior a la de cierre.", "error")
            return redirect(url_for("proveedor.horarios"))
        nuevos.append((1 if cerrado else 0, "09:00" if cerrado else abre, "18:00" if cerrado else cierra, _yo(), dia))
    bd.db().executemany("UPDATE horarios SET cerrado=?, abre=?, cierra=? WHERE proveedor_id=? AND dia=?", nuevos)
    bd.db().commit()
    flash("Horario guardado.", "ok")
    return redirect(url_for("proveedor.horarios"))


@proveedor.route("/cierres/agregar", methods=["POST"])
@rol_requerido("proveedor")
def agregar_cierre():
    fecha = request.form.get("fecha", "")
    if not v.fecha_ok(fecha) or fecha < bd.hoy():
        flash("Elige una fecha válida.", "error")
    else:
        bd.ejecutar("INSERT OR REPLACE INTO cierres(proveedor_id,fecha,motivo) VALUES(?,?,?)",
                    (_yo(), fecha, v.texto(request.form.get("motivo"), 80)))
        flash("Día cerrado agregado: no se podrán reservar citas ese día.", "ok")
    return redirect(url_for("proveedor.horarios"))


@proveedor.route("/cierres/<int:cid>/eliminar", methods=["POST"])
@rol_requerido("proveedor")
def eliminar_cierre(cid):
    bd.ejecutar("DELETE FROM cierres WHERE id=? AND proveedor_id=?", (cid, _yo()))
    return redirect(url_for("proveedor.horarios"))


# ===================== CITAS =====================
@proveedor.route("/citas")
@rol_requerido("proveedor")
def citas():
    estado, desde = request.args.get("estado", ""), request.args.get("desde", "")
    sql, args = "SELECT * FROM citas WHERE proveedor_id=?", [_yo()]
    if estado in FLUJO_CITAS or estado in ("completada", "rechazada", "no_asistio", "cancelada"):
        sql += " AND estado=?"
        args.append(estado)
    if v.fecha_ok(desde):
        sql += " AND fecha>=?"
        args.append(desde)
    lista = bd.todos(sql + " ORDER BY fecha DESC, hora DESC LIMIT 300", args)
    servicios = bd.todos("SELECT * FROM servicios WHERE proveedor_id=? AND activo=1 ORDER BY nombre", (_yo(),))
    return render_template("proveedor/citas.html", lista=lista, estado=estado, desde=desde, servicios=servicios, flujo=FLUJO_CITAS)


@proveedor.route("/citas/<int:cid>/estado", methods=["POST"])
@rol_requerido("proveedor")
def cambiar_estado_cita(cid):
    c = bd.uno("SELECT * FROM citas WHERE id=? AND proveedor_id=?", (cid, _yo()))
    nuevo = request.form.get("estado", "")
    if not c:
        abort(404)
    if nuevo not in FLUJO_CITAS.get(c["estado"], []):
        flash(f"No se puede pasar de «{c['estado']}» a «{nuevo}».", "error")
    else:
        bd.ejecutar("UPDATE citas SET estado=?, actualizado=? WHERE id=?", (nuevo, bd.ahora(), cid))
        bd.bitacora(g.usuario["usuario"], "cita_" + nuevo, f"cita {cid}")
        flash("Cita actualizada.", "ok")
    return redirect(url_for("proveedor.citas"))


@proveedor.route("/citas/horas")
@rol_requerido("proveedor")
def api_horas():
    svc = bd.uno("SELECT * FROM servicios WHERE id=? AND proveedor_id=? AND activo=1", (v.entero(request.args.get("servicio_id")), _yo()))
    fecha = request.args.get("fecha", "")
    if not svc or not v.fecha_ok(fecha):
        return jsonify(horas=[])
    return jsonify(horas=agenda.horas_libres(_yo(), svc, fecha))


@proveedor.route("/citas/manual", methods=["POST"])
@rol_requerido("proveedor")
def cita_manual():
    """El salón registra una cita tomada por teléfono o en mostrador."""
    f = request.form
    nombre, tel = v.texto(f.get("cliente_nombre"), 80), v.texto(f.get("cliente_telefono"), 20)
    if len(nombre) < 2 or not v.telefono_ok(tel) or not v.fecha_ok(f.get("fecha", "")) or not v.hora_ok(f.get("hora", "")):
        flash("Completa nombre, teléfono, fecha y hora válidos.", "error")
    else:
        _, error = agenda.crear_cita(_yo(), v.entero(f.get("servicio_id")), f["fecha"], f["hora"], None, nombre, tel,
                                     notas=v.texto(f.get("notas"), 300), origen="manual")
        flash(error or "Cita manual registrada y confirmada.", "error" if error else "ok")
    return redirect(url_for("proveedor.citas"))


# ===================== DOCUMENTOS DE VERIFICACIÓN =====================
def _mime_real(cabecera):
    """Revisa los primeros bytes del archivo: el tipo REAL, no el que dice la extensión."""
    if cabecera[:4] == b"%PDF":
        return "application/pdf"
    if cabecera[:2] == b"\xff\xd8":
        return "image/jpeg"
    if cabecera[1:4] == b"PNG":
        return "image/png"
    return None


@proveedor.route("/documentos")
@rol_requerido("proveedor")
def documentos():
    docs = bd.todos("SELECT * FROM documentos WHERE proveedor_id=? ORDER BY subido DESC", (_yo(),))
    return render_template("proveedor/documentos.html", docs=docs, tipos=config.TIPOS_DOCUMENTO, p=_perfil())


@proveedor.route("/documentos/subir", methods=["POST"])
@rol_requerido("proveedor")
def subir_documento():
    tipo, archivo = request.form.get("tipo"), request.files.get("archivo")
    if tipo not in config.TIPOS_DOCUMENTO or not archivo or not archivo.filename:
        flash("Elige el tipo de documento y el archivo.", "error")
        return redirect(url_for("proveedor.documentos"))
    contenido = archivo.read()
    mime = _mime_real(contenido[:8])
    if len(contenido) > 5 * 1024 * 1024:
        flash("El archivo supera los 5 MB.", "error")
    elif not mime:
        flash("El archivo debe ser un PDF, JPG o PNG válido.", "error")
    elif bd.uno("SELECT COUNT(*) n FROM documentos WHERE proveedor_id=?", (_yo(),))["n"] >= 15:
        flash("Máximo 15 documentos.", "error")
    else:
        guardado = secrets.token_hex(16)                       # nombre aleatorio: nadie lo puede adivinar
        (config.CARPETA_DOCS / guardado).write_bytes(contenido)
        bd.ejecutar("INSERT INTO documentos(proveedor_id,tipo,nombre_original,nombre_guardado,mime,tamano,subido) VALUES(?,?,?,?,?,?,?)",
                    (_yo(), tipo, v.texto(archivo.filename, 120), guardado, mime, len(contenido), bd.ahora()))
        bd.bitacora(g.usuario["usuario"], "documento_subido", tipo)
        flash("Documento subido.", "ok")
    return redirect(url_for("proveedor.documentos"))


@proveedor.route("/documentos/<int:did>/archivo")
@rol_requerido("proveedor")
def descargar_documento(did):
    d = bd.uno("SELECT * FROM documentos WHERE id=? AND proveedor_id=?", (did, _yo()))   # solo SUS documentos
    if not d:
        abort(404)
    return send_from_directory(config.CARPETA_DOCS, d["nombre_guardado"], mimetype=d["mime"],
                               as_attachment=True, download_name=d["nombre_original"])


@proveedor.route("/documentos/<int:did>/eliminar", methods=["POST"])
@rol_requerido("proveedor")
def eliminar_documento(did):
    d = bd.uno("SELECT * FROM documentos WHERE id=? AND proveedor_id=?", (did, _yo()))
    if not d:
        abort(404)
    if _perfil()["estado"] == "verificado":
        flash("Con la cuenta verificada los documentos no se pueden borrar. Escríbenos si debes actualizarlos.", "error")
    else:
        bd.ejecutar("DELETE FROM documentos WHERE id=?", (did,))
        (config.CARPETA_DOCS / d["nombre_guardado"]).unlink(missing_ok=True)
        flash("Documento eliminado.", "ok")
    return redirect(url_for("proveedor.documentos"))
