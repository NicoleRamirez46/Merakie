"""
rutas_admin.py  ·  EL PANEL DEL ADMINISTRADOR
Resumen · Clientes · Proveedores (verificar) · Fraude · Pagos · Inconformidades · Compras · Agendamientos · Auditoría
El administrador ve los datos REALES que registran clientes y proveedores (se leen de la base de datos).
Cada consulta a datos personales delicados (documento completo, documentos del proveedor) queda en la bitácora.
"""
import csv
import io
from flask import Blueprint, render_template, request, redirect, url_for, flash, g, abort, Response, send_from_directory

import config
import base_datos as bd
import validaciones as v
import fraude
from seguridad import rol_requerido

admin = Blueprint("admin", __name__, url_prefix="/admin")


def _quien():
    return g.usuario["nombre"]


# ===================== RESUMEN =====================
@admin.route("/")
@rol_requerido("administrador")
def resumen():
    n = lambda sql, *a: bd.uno(sql, a)["n"]
    datos = {
        "clientes": n("SELECT COUNT(*) n FROM clientes"),
        "proveedores": n("SELECT COUNT(*) n FROM proveedores"),
        "prov_verificados": n("SELECT COUNT(*) n FROM proveedores WHERE estado='verificado'"),
        "prov_revision": n("SELECT COUNT(*) n FROM proveedores WHERE estado='en_revision'"),
        "citas": n("SELECT COUNT(*) n FROM citas"),
        "citas_activas": n("SELECT COUNT(*) n FROM citas WHERE estado IN ('pendiente','confirmada')"),
        "compras": n("SELECT COUNT(*) n FROM pedidos"),
        "pagos": n("SELECT COUNT(*) n FROM pagos"),
        "ingresos": bd.uno("SELECT COALESCE(SUM(valor),0) n FROM pagos WHERE estado='Aprobado'")["n"],
        "alertas": sum(1 for a in fraude.calcular_alertas() if a["estado"] != "sin_hallazgos"),
        "quejas": n("SELECT COUNT(*) n FROM quejas WHERE estado!='Resuelta'"),
    }
    reciente = bd.todos("SELECT * FROM bitacora ORDER BY id DESC LIMIT 8")
    return render_template("admin/resumen.html", d=datos, reciente=reciente)


# ===================== CLIENTES =====================
@admin.route("/clientes")
@rol_requerido("administrador")
def clientes():
    q = v.texto(request.args.get("q"), 60)
    lista = bd.todos("""SELECT u.id, u.nombre, u.usuario, u.correo, u.telefono, u.creado, c.documento, c.pass_activo,
                          (SELECT COUNT(*) FROM pedidos WHERE cliente_id=u.id) AS compras,
                          (SELECT COUNT(*) FROM citas WHERE cliente_id=u.id) AS citas
                        FROM usuarios u JOIN clientes c ON c.usuario_id=u.id
                        WHERE u.nombre LIKE ? OR u.usuario LIKE ? OR u.correo LIKE ? OR u.telefono LIKE ?
                        ORDER BY u.creado DESC""", (f"%{q}%",) * 4)
    return render_template("admin/clientes.html", lista=lista, q=q)


@admin.route("/clientes/<int:cid>", methods=["GET", "POST"])
@rol_requerido("administrador")
def cliente(cid):
    """POST = el administrador pidió ver el documento completo (queda en la bitácora)."""
    u = bd.uno("SELECT u.*, c.documento, c.edad, c.pass_activo, c.consentimiento_fecha, c.consentimiento_version "
               "FROM usuarios u JOIN clientes c ON c.usuario_id=u.id WHERE u.id=?", (cid,))
    if not u:
        abort(404)
    mostrar = request.method == "POST"
    if mostrar:
        bd.bitacora(_quien(), "admin_ve_documento_cliente", u["usuario"])
    pedidos = bd.todos("""SELECT pe.*, GROUP_CONCAT(i.nombre || ' ×' || i.cantidad, ' | ') AS productos FROM pedidos pe
                          LEFT JOIN pedido_items i ON i.pedido_id=pe.id WHERE pe.cliente_id=? GROUP BY pe.id ORDER BY pe.creado DESC""", (cid,))
    return render_template("admin/cliente.html", u=u, mostrar=mostrar, pedidos=pedidos,
        pagos=bd.todos("SELECT * FROM pagos WHERE cliente_id=? ORDER BY creado DESC", (cid,)),
        citas=bd.todos("SELECT c.*, p.nombre_comercial FROM citas c JOIN proveedores p ON p.usuario_id=c.proveedor_id WHERE c.cliente_id=? ORDER BY c.fecha DESC", (cid,)),
        quejas=bd.todos("SELECT * FROM quejas WHERE cliente_id=? ORDER BY creado DESC", (cid,)))


# ===================== PROVEEDORES =====================
@admin.route("/proveedores")
@rol_requerido("administrador")
def proveedores():
    estado = request.args.get("estado", "")
    sql = """SELECT p.*, u.nombre AS contacto, u.correo, u.telefono,
               (SELECT COUNT(*) FROM servicios WHERE proveedor_id=p.usuario_id) AS n_servicios,
               (SELECT COUNT(*) FROM productos WHERE proveedor_id=p.usuario_id) AS n_productos
             FROM proveedores p JOIN usuarios u ON u.id=p.usuario_id"""
    lista = bd.todos(sql + (" WHERE p.estado=?" if estado else "") + " ORDER BY p.creado DESC", (estado,) if estado else ())
    return render_template("admin/proveedores.html", lista=lista, estado=estado)


@admin.route("/proveedores/<int:pid>")
@rol_requerido("administrador")
def proveedor(pid):
    p = bd.uno("SELECT p.*, u.nombre AS contacto, u.correo, u.telefono, u.usuario FROM proveedores p JOIN usuarios u ON u.id=p.usuario_id WHERE p.usuario_id=?", (pid,))
    if not p:
        abort(404)
    return render_template("admin/proveedor.html", p=p, tipos=config.TIPOS_DOCUMENTO,
        docs=bd.todos("SELECT * FROM documentos WHERE proveedor_id=?", (pid,)),
        servicios=bd.todos("SELECT * FROM servicios WHERE proveedor_id=?", (pid,)),
        productos=bd.todos("SELECT * FROM productos WHERE proveedor_id=?", (pid,)),
        stats=bd.uno("SELECT COUNT(*) total, COALESCE(SUM(estado='completada'),0) hechas FROM citas WHERE proveedor_id=?", (pid,)))


@admin.route("/proveedores/<int:pid>/estado", methods=["POST"])
@rol_requerido("administrador")
def estado_proveedor(pid):
    nuevo, motivo = request.form.get("estado"), v.texto(request.form.get("motivo"), 300)
    p = bd.uno("SELECT * FROM proveedores WHERE usuario_id=?", (pid,))
    if not p:
        abort(404)
    if nuevo not in ("verificado", "rechazado", "suspendido", "en_revision"):
        flash("Estado no válido.", "error")
    elif nuevo in ("rechazado", "suspendido") and len(motivo) < 5:
        flash("Escribe el motivo: el proveedor lo verá.", "error")
    else:
        bd.ejecutar("UPDATE proveedores SET estado=?, motivo=?, estado_fecha=? WHERE usuario_id=?", (nuevo, motivo, bd.ahora(), pid))
        bd.bitacora(_quien(), "proveedor_" + nuevo, f"{p['nombre_comercial']} (NIT {p['nit']}) {motivo}")
        flash(f"Estado actualizado a «{nuevo}».", "ok")
    return redirect(url_for("admin.proveedor", pid=pid))


@admin.route("/documentos/<int:did>")
@rol_requerido("administrador")
def ver_documento(did):
    d = bd.uno("SELECT * FROM documentos WHERE id=?", (did,))
    if not d:
        abort(404)
    bd.bitacora(_quien(), "admin_ve_documento_proveedor", f"doc {did} proveedor {d['proveedor_id']}")   # queda constancia
    return send_from_directory(config.CARPETA_DOCS, d["nombre_guardado"], mimetype=d["mime"],
                               as_attachment=True, download_name=d["nombre_original"])


# ===================== FRAUDE =====================
@admin.route("/fraude")
@rol_requerido("administrador")
def fraude_vista():
    ver = request.args.get("ver", "abiertas")
    todas = fraude.calcular_alertas()
    lista = [a for a in todas if ver == "todas" or (ver == "abiertas") == (a["estado"] != "sin_hallazgos")]
    return render_template("admin/fraude.html", lista=lista, total=len(todas), ver=ver, umbral=config.UMBRAL_PAGO_ALTO)


@admin.route("/fraude/revisar", methods=["POST"])
@rol_requerido("administrador")
def revisar_alerta():
    clave, estado = v.texto(request.form.get("clave"), 200), request.form.get("estado")
    nota = v.texto(request.form.get("nota"), 300)
    if estado not in ("abierta", "en_revision", "sin_hallazgos") or not clave:
        abort(400)
    if estado == "sin_hallazgos" and len(nota) < 5:
        flash("Para cerrar una alerta escribe qué verificaste y con quién (mínimo 5 caracteres).", "error")
    else:
        bd.ejecutar("INSERT OR REPLACE INTO alertas_revision(clave,estado,nota,revisado_por,fecha) VALUES(?,?,?,?,?)",
                    (clave, estado, nota, _quien(), bd.ahora()))
        bd.bitacora(_quien(), "alerta_" + estado, f"{clave} {nota}")
        flash("Revisión guardada.", "ok")
    return redirect(url_for("admin.fraude_vista", ver=request.form.get("ver", "abiertas")))


# ===================== PAGOS, COMPRAS, CITAS =====================
SQL_PAGOS = """SELECT pg.*, u.nombre, u.usuario FROM pagos pg JOIN usuarios u ON u.id=pg.cliente_id"""
SQL_COMPRAS = """SELECT pe.*, u.nombre, u.usuario, GROUP_CONCAT(i.nombre || ' ×' || i.cantidad, ' | ') AS productos
                 FROM pedidos pe JOIN usuarios u ON u.id=pe.cliente_id LEFT JOIN pedido_items i ON i.pedido_id=pe.id
                 GROUP BY pe.id ORDER BY pe.creado DESC"""


@admin.route("/pagos")
@rol_requerido("administrador")
def pagos():
    estado = request.args.get("estado", "")
    lista = bd.todos(SQL_PAGOS + (" WHERE pg.estado=?" if estado else "") + " ORDER BY pg.creado DESC", (estado,) if estado else ())
    total = sum(p["valor"] for p in lista if p["estado"] == "Aprobado")
    return render_template("admin/pagos.html", lista=lista, estado=estado, total=total)


@admin.route("/compras")
@rol_requerido("administrador")
def compras():
    return render_template("admin/compras.html", lista=bd.todos(SQL_COMPRAS))


@admin.route("/agendamientos")
@rol_requerido("administrador")
def citas():
    f = {"salon": v.entero(request.args.get("salon")), "fecha": request.args.get("fecha", ""), "estado": request.args.get("estado", "")}
    sql, args = "SELECT c.*, p.nombre_comercial FROM citas c JOIN proveedores p ON p.usuario_id=c.proveedor_id WHERE 1=1", []
    if f["salon"]:
        sql += " AND c.proveedor_id=?"
        args.append(f["salon"])
    if v.fecha_ok(f["fecha"]):
        sql += " AND c.fecha=?"
        args.append(f["fecha"])
    if f["estado"]:
        sql += " AND c.estado=?"
        args.append(f["estado"])
    return render_template("admin/citas.html", lista=bd.todos(sql + " ORDER BY c.fecha DESC, c.hora DESC LIMIT 500", args), f=f,
                           salones=bd.todos("SELECT usuario_id, nombre_comercial FROM proveedores ORDER BY nombre_comercial"))


# ===================== INCONFORMIDADES (PQR) =====================
@admin.route("/inconformidades")
@rol_requerido("administrador")
def quejas():
    estado = request.args.get("estado", "")
    lista = bd.todos("SELECT q.*, u.nombre, u.usuario FROM quejas q JOIN usuarios u ON u.id=q.cliente_id"
                     + (" WHERE q.estado=?" if estado else "") + " ORDER BY q.creado DESC", (estado,) if estado else ())
    return render_template("admin/quejas.html", lista=lista, estado=estado)


@admin.route("/inconformidades/<int:qid>", methods=["POST"])
@rol_requerido("administrador")
def actualizar_queja(qid):
    estado, respuesta = request.form.get("estado"), v.texto(request.form.get("respuesta"), 1000)
    if estado not in ("Pendiente", "En revisión", "Resuelta") or not bd.uno("SELECT 1 FROM quejas WHERE id=?", (qid,)):
        abort(400)
    bd.ejecutar("UPDATE quejas SET estado=?, respuesta=?, actualizado=? WHERE id=?", (estado, respuesta, bd.ahora(), qid))
    bd.bitacora(_quien(), "queja_" + estado, f"PQR {qid}")
    flash("Solicitud actualizada.", "ok")
    return redirect(url_for("admin.quejas"))


# ===================== AUDITORÍA Y EXPORTAR =====================
@admin.route("/auditoria")
@rol_requerido("administrador")
def auditoria():
    return render_template("admin/auditoria.html", lista=bd.todos("SELECT * FROM bitacora ORDER BY id DESC LIMIT 300"))


@admin.route("/exportar/<tipo>")
@rol_requerido("administrador")
def exportar(tipo):
    """Descarga un CSV (se abre en Excel). Las celdas que empiezan por = + - @ se neutralizan
    para que nadie pueda esconder una fórmula maliciosa en un nombre."""
    if tipo == "pagos":
        cab = ["ID", "Cliente", "Usuario", "Valor", "Fecha", "Método", "Estado"]
        filas = [[p["id"], p["nombre"], p["usuario"], p["valor"], p["creado"], p["metodo"], p["estado"]]
                 for p in bd.todos(SQL_PAGOS + " ORDER BY pg.creado DESC")]
    elif tipo == "compras":
        cab = ["Pedido", "Cliente", "Usuario", "Fecha", "Productos", "Total", "Estado"]
        filas = [[c["id"], c["nombre"], c["usuario"], c["creado"], c["productos"], c["total"], c["estado"]] for c in bd.todos(SQL_COMPRAS)]
    elif tipo == "citas":
        cab = ["ID", "Fecha", "Hora", "Salón", "Servicio", "Cliente", "Estado", "Valor"]
        filas = [[c["id"], c["fecha"], c["hora"], c["nombre_comercial"], c["servicio_nombre"], c["cliente_nombre"], c["estado"], c["precio"]]
                 for c in bd.todos("SELECT c.*, p.nombre_comercial FROM citas c JOIN proveedores p ON p.usuario_id=c.proveedor_id ORDER BY c.fecha DESC")]
    else:
        abort(404)
    seguro = lambda x: ("'" + str(x)) if str(x)[:1] in "=+-@" else str(x if x is not None else "")
    salida = io.StringIO()
    w = csv.writer(salida, delimiter=";", quoting=csv.QUOTE_ALL)
    w.writerow(cab)
    w.writerows([[seguro(c) for c in fila] for fila in filas])
    bd.bitacora(_quien(), "exportar_csv", tipo)
    return Response("﻿" + salida.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={tipo}-merakie.csv"})
