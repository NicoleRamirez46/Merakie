"""
rutas_cliente.py  ·  TODO LO QUE PUEDE HACER UN CLIENTE
Salones y citas, tienda y carrito, pagos, calendario, beneficios (Pass) y ayuda (PQR).
Todas las rutas llevan @rol_requerido("cliente"): un proveedor o administrador no puede entrar aquí.
Y cada consulta filtra por cliente_id = g.usuario["id"]: un cliente SOLO ve lo suyo.
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, g, jsonify, abort, Response

import config
import base_datos as bd
import validaciones as v
import agenda
from seguridad import rol_requerido

cliente = Blueprint("cliente", __name__, url_prefix="/cliente")

TIPOS_PQR = ["Queja", "Reclamo", "Petición", "Solicitud", "Sugerencia"]
METODOS = {"tarjeta": "Tarjeta de prueba", "pse": "PSE (simulado)", "nequi": "Nequi (simulado)",
           "contraentrega": "Pago contra entrega (simulado)", "rechazo": "Tarjeta de prueba"}
DESCUENTOS = [("Manicure con 15% de descuento", "En salones aliados · promoción de ejemplo"),
              ("10% en cuidado capilar", "En productos seleccionados · promoción de ejemplo"),
              ("Beneficio Merakié Pass", "5% de descuento en todos los productos de la tienda (real en esta demo)")]


def _yo():
    return g.usuario["id"]


def _perfil():
    return bd.uno("SELECT * FROM clientes WHERE usuario_id=?", (_yo(),))


# ===================== INICIO =====================
@cliente.route("/")
@rol_requerido("cliente")
def inicio():
    proximas = bd.todos("""SELECT c.*, p.nombre_comercial FROM citas c JOIN proveedores p ON p.usuario_id=c.proveedor_id
                           WHERE c.cliente_id=? AND c.estado IN ('pendiente','confirmada') AND c.fecha>=?
                           ORDER BY c.fecha, c.hora LIMIT 5""", (_yo(), bd.hoy()))
    return render_template("cliente/inicio.html", proximas=proximas, perfil=_perfil())


# ===================== SALONES Y CITAS =====================
@cliente.route("/salones")
@rol_requerido("cliente")
def salones():
    ciudad, categoria = v.texto(request.args.get("ciudad"), 60), v.texto(request.args.get("categoria"), 40)
    sql = """SELECT p.*, u.telefono FROM proveedores p JOIN usuarios u ON u.id=p.usuario_id
             WHERE p.estado='verificado'
               AND EXISTS (SELECT 1 FROM servicios s WHERE s.proveedor_id=p.usuario_id AND s.activo=1)"""
    args = []
    if ciudad:
        sql += " AND p.ciudad LIKE ?"
        args.append(f"%{ciudad}%")
    if categoria:
        sql += " AND EXISTS (SELECT 1 FROM servicios s WHERE s.proveedor_id=p.usuario_id AND s.activo=1 AND s.categoria=?)"
        args.append(categoria)
    lista = []
    for s in bd.todos(sql + " ORDER BY p.nombre_comercial", args):
        servicios = bd.todos("SELECT nombre FROM servicios WHERE proveedor_id=? AND activo=1 ORDER BY nombre", (s["usuario_id"],))
        lista.append({"salon": s, "servicios": [x["nombre"] for x in servicios]})
    return render_template("cliente/salones.html", lista=lista, ciudad=ciudad, categoria=categoria, categorias=config.CATEGORIAS)


def _salon_verificado(pid):
    s = bd.uno("SELECT p.*, u.telefono FROM proveedores p JOIN usuarios u ON u.id=p.usuario_id "
               "WHERE p.usuario_id=? AND p.estado='verificado'", (pid,))
    if not s:
        abort(404)
    return s


@cliente.route("/salones/<int:pid>")
@rol_requerido("cliente")
def salon(pid):
    s = _salon_verificado(pid)
    servicios = bd.todos("SELECT * FROM servicios WHERE proveedor_id=? AND activo=1 ORDER BY categoria, nombre", (pid,))
    return render_template("cliente/salon.html", s=s, servicios=servicios)


@cliente.route("/salones/<int:pid>/horas")
@rol_requerido("cliente")
def api_horas(pid):
    """Responde en JSON las horas libres. Lo usa el pequeño JavaScript de la página."""
    _salon_verificado(pid)
    svc = bd.uno("SELECT * FROM servicios WHERE id=? AND proveedor_id=? AND activo=1", (v.entero(request.args.get("servicio_id")), pid))
    fecha = request.args.get("fecha", "")
    if not svc or not v.fecha_ok(fecha):
        return jsonify(horas=[])
    return jsonify(horas=agenda.horas_libres(pid, svc, fecha))


@cliente.route("/salones/<int:pid>/reservar", methods=["POST"])
@rol_requerido("cliente")
def reservar(pid):
    _salon_verificado(pid)
    f = request.form
    modalidad = f.get("modalidad") if f.get("modalidad") in ("En el salón", "A domicilio (simulación)") else "En el salón"
    if not v.fecha_ok(f.get("fecha", "")) or not v.hora_ok(f.get("hora", "")):
        flash("Elige una fecha y una hora disponibles.", "error")
        return redirect(url_for("cliente.salon", pid=pid))
    cita_id, error = agenda.crear_cita(pid, v.entero(f.get("servicio_id")), f["fecha"], f["hora"], _yo(),
                                       g.usuario["nombre"], g.usuario["telefono"], modalidad, v.texto(f.get("notas"), 300))
    if error:
        flash(error, "error")
        return redirect(url_for("cliente.salon", pid=pid))
    estado = bd.uno("SELECT estado FROM citas WHERE id=?", (cita_id,))["estado"]
    bd.bitacora(g.usuario["usuario"], "cita_creada", f"cita {cita_id} salón {pid} {f['fecha']} {f['hora']}")
    flash("¡Cita confirmada!" if estado == "confirmada" else "¡Cita solicitada! El salón la confirmará pronto.", "ok")
    return redirect(url_for("cliente.calendario"))


# ===================== CALENDARIO =====================
@cliente.route("/calendario")
@rol_requerido("cliente")
def calendario():
    citas = bd.todos("""SELECT c.*, p.nombre_comercial, p.direccion FROM citas c JOIN proveedores p ON p.usuario_id=c.proveedor_id
                        WHERE c.cliente_id=? ORDER BY c.fecha DESC, c.hora DESC""", (_yo(),))
    return render_template("cliente/calendario.html", citas=citas)


@cliente.route("/citas/<int:cid>/cancelar", methods=["POST"])
@rol_requerido("cliente")
def cancelar_cita(cid):
    c = bd.uno("SELECT * FROM citas WHERE id=? AND cliente_id=?", (cid, _yo()))   # solo SUS citas
    if not c or c["estado"] not in ("pendiente", "confirmada"):
        flash("Esa cita no se puede cancelar.", "error")
    else:
        bd.ejecutar("UPDATE citas SET estado='cancelada', actualizado=? WHERE id=?", (bd.ahora(), cid))
        bd.bitacora(g.usuario["usuario"], "cita_cancelada", f"cita {cid}")
        flash("Cita cancelada. El horario quedó libre.", "ok")
    return redirect(url_for("cliente.calendario"))


@cliente.route("/calendario.ics")
@rol_requerido("cliente")
def calendario_ics():
    """Archivo .ics: se puede importar a Google Calendar, Outlook o el calendario del celular."""
    citas = bd.todos("""SELECT c.*, p.nombre_comercial FROM citas c JOIN proveedores p ON p.usuario_id=c.proveedor_id
                        WHERE c.cliente_id=? AND c.estado IN ('pendiente','confirmada')""", (_yo(),))
    if not citas:
        flash("No tienes citas activas para exportar.", "aviso")
        return redirect(url_for("cliente.calendario"))
    esc = lambda s: str(s).replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;").replace("\n", " ")
    marca = bd.ahora().replace("-", "").replace(":", "").replace(" ", "T")
    lineas = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Merakie//Plataforma//ES"]
    for c in citas:
        d = c["fecha"].replace("-", "")
        lineas += ["BEGIN:VEVENT", f"UID:cita-{c['id']}@merakie", f"DTSTAMP:{marca}",
                   f"DTSTART:{d}T{c['hora'].replace(':', '')}00", f"DTEND:{d}T{c['hora_fin'].replace(':', '')}00",
                   f"SUMMARY:{esc(c['servicio_nombre'] + ' - ' + c['nombre_comercial'])}", "END:VEVENT"]
    lineas.append("END:VCALENDAR")
    return Response("\r\n".join(lineas) + "\r\n", mimetype="text/calendar",
                    headers={"Content-Disposition": "attachment; filename=mis-citas-merakie.ics"})


# ===================== TIENDA Y CARRITO =====================
# Se venden los productos de Merakié y los de proveedores YA verificados.
SQL_DISPONIBLES = """SELECT pr.*, COALESCE(p.nombre_comercial,'Merakié') AS vendedor FROM productos pr
                     LEFT JOIN proveedores p ON p.usuario_id=pr.proveedor_id
                     WHERE pr.activo=1 AND (pr.proveedor_id IS NULL OR p.estado='verificado')"""


@cliente.route("/tienda")
@rol_requerido("cliente")
def tienda():
    return render_template("cliente/tienda.html", productos=bd.todos(SQL_DISPONIBLES + " ORDER BY pr.nombre"))


def _leer_carrito():
    """El carrito vive en la sesión: {'101': 2, '103': 1} = producto 101 (x2) y 103 (x1)."""
    items, subtotal = [], 0
    for pid, cant in session.get("carrito", {}).items():
        p = bd.uno(SQL_DISPONIBLES + " AND pr.id=?", (int(pid),))
        if p:
            items.append({"p": p, "cantidad": cant, "total": p["precio"] * cant})
            subtotal += p["precio"] * cant
    descuento = round(subtotal * config.DESCUENTO_PASS) if _perfil()["pass_activo"] else 0
    return items, subtotal, descuento


@cliente.route("/carrito")
@rol_requerido("cliente")
def carrito():
    items, subtotal, descuento = _leer_carrito()
    return render_template("cliente/carrito.html", items=items, subtotal=subtotal, descuento=descuento,
                           total=subtotal - descuento, metodos=METODOS)


@cliente.route("/carrito/agregar/<int:pid>", methods=["POST"])
@rol_requerido("cliente")
def agregar(pid):
    p = bd.uno(SQL_DISPONIBLES + " AND pr.id=?", (pid,))
    if not p:
        abort(404)
    carrito = session.get("carrito", {})
    nueva = carrito.get(str(pid), 0) + 1
    if nueva > p["stock"]:
        flash(f"Solo quedan {p['stock']} unidades de {p['nombre']}.", "aviso")
    else:
        carrito[str(pid)] = nueva
        session["carrito"] = carrito
        flash(f"{p['nombre']} se añadió al carrito.", "ok")
    return redirect(url_for("cliente.tienda"))


@cliente.route("/carrito/cambiar/<int:pid>/<int:delta>", methods=["POST"])
@rol_requerido("cliente")
def cambiar(pid, delta):
    carrito = session.get("carrito", {})
    if str(pid) in carrito:
        nueva = carrito[str(pid)] + (1 if delta == 1 else -1)
        p = bd.uno("SELECT stock FROM productos WHERE id=?", (pid,))
        if nueva <= 0:
            del carrito[str(pid)]
        elif p and nueva <= p["stock"]:
            carrito[str(pid)] = nueva
        else:
            flash("No hay más unidades disponibles.", "aviso")
        session["carrito"] = carrito
    return redirect(url_for("cliente.carrito"))


@cliente.route("/carrito/vaciar", methods=["POST"])
@rol_requerido("cliente")
def vaciar():
    session["carrito"] = {}
    return redirect(url_for("cliente.carrito"))


@cliente.route("/carrito/pagar", methods=["POST"])
@rol_requerido("cliente")
def pagar():
    """Pago SIMULADO. Siempre se registra el pago; el pedido solo si el pago NO fue rechazado."""
    metodo = request.form.get("metodo")
    if metodo not in METODOS:
        flash("Elige un método de pago.", "error")
        return redirect(url_for("cliente.carrito"))
    con = bd.db()
    con.execute("BEGIN IMMEDIATE")          # bloquea la base: nadie más compra el mismo stock a la vez
    try:
        items, subtotal, descuento = _leer_carrito()
        if not items:
            con.rollback()
            flash("Tu carrito está vacío.", "aviso")
            return redirect(url_for("cliente.carrito"))
        for it in items:
            if it["cantidad"] > it["p"]["stock"]:
                con.rollback()
                flash(f"No hay suficiente stock de {it['p']['nombre']} (quedan {it['p']['stock']}).", "error")
                return redirect(url_for("cliente.carrito"))
        total, t = subtotal - descuento, bd.ahora()
        if metodo == "rechazo":
            estado_pago, motivo, pedido_id = "Rechazado", "Fondos insuficientes (simulado)", None
        else:
            estado_pago, motivo = ("Pendiente" if metodo == "contraentrega" else "Aprobado"), ""
            cur = con.execute("INSERT INTO pedidos(cliente_id,total,estado,creado) VALUES(?,?,?,?)",
                              (_yo(), total, "Por pagar en la entrega" if estado_pago == "Pendiente" else "Pagado", t))
            pedido_id = cur.lastrowid
            for it in items:
                con.execute("INSERT INTO pedido_items(pedido_id,producto_id,nombre,cantidad,precio) VALUES(?,?,?,?,?)",
                            (pedido_id, it["p"]["id"], it["p"]["nombre"], it["cantidad"], it["p"]["precio"]))
                con.execute("UPDATE productos SET stock=stock-? WHERE id=?", (it["cantidad"], it["p"]["id"]))
        cur = con.execute("INSERT INTO pagos(cliente_id,pedido_id,valor,metodo,estado,motivo,creado) VALUES(?,?,?,?,?,?,?)",
                          (_yo(), pedido_id, total, METODOS[metodo], estado_pago, motivo, t))
        con.commit()
    except Exception:
        con.rollback()
        raise
    bd.bitacora(g.usuario["usuario"], "pago_" + estado_pago.lower(), f"pago {cur.lastrowid} {METODOS[metodo]} {total}")
    if estado_pago == "Rechazado":
        flash("El pago fue rechazado (simulación). Tu carrito sigue intacto; prueba con otro método.", "error")
        return redirect(url_for("cliente.carrito"))
    session["carrito"] = {}
    flash(f"¡Compra registrada! Pedido #{pedido_id} por {total:,}".replace(",", ".") + " COP. No se procesó dinero real.", "ok")
    return redirect(url_for("cliente.compras"))


@cliente.route("/compras")
@rol_requerido("cliente")
def compras():
    pedidos = bd.todos("""SELECT pe.*, GROUP_CONCAT(i.nombre || ' ×' || i.cantidad, ' | ') AS productos
                          FROM pedidos pe LEFT JOIN pedido_items i ON i.pedido_id=pe.id
                          WHERE pe.cliente_id=? GROUP BY pe.id ORDER BY pe.creado DESC""", (_yo(),))
    pagos = bd.todos("SELECT * FROM pagos WHERE cliente_id=? ORDER BY creado DESC", (_yo(),))
    return render_template("cliente/compras.html", pedidos=pedidos, pagos=pagos)


# ===================== BENEFICIOS (descuentos + Pass) =====================
@cliente.route("/beneficios")
@rol_requerido("cliente")
def beneficios():
    return render_template("cliente/beneficios.html", descuentos=DESCUENTOS, perfil=_perfil())


@cliente.route("/pass", methods=["POST"])
@rol_requerido("cliente")
def activar_pass():
    bd.ejecutar("UPDATE clientes SET pass_activo=1 WHERE usuario_id=?", (_yo(),))
    bd.bitacora(g.usuario["usuario"], "pass_activado")
    flash("Merakié Pass activado (demostración, sin cobro). Ya tienes 5 % de descuento en la tienda.", "ok")
    return redirect(url_for("cliente.beneficios"))


# ===================== AYUDA / PQR =====================
@cliente.route("/ayuda", methods=["GET", "POST"])
@rol_requerido("cliente")
def ayuda():
    if request.method == "POST":
        f = request.form
        tipo, asunto, mensaje = f.get("tipo"), v.texto(f.get("asunto"), 100), v.texto(f.get("mensaje"), 1000)
        pedido = v.entero(f.get("pedido_id"), None) if f.get("pedido_id") else None
        if pedido and not bd.uno("SELECT 1 FROM pedidos WHERE id=? AND cliente_id=?", (pedido, _yo())):
            pedido = None                                   # solo se puede enlazar una compra propia
        if tipo not in TIPOS_PQR or len(asunto) < 3 or len(mensaje) < 5:
            flash("Completa el tipo, el asunto y el detalle de tu solicitud.", "error")
        else:
            t = bd.ahora()
            qid = bd.ejecutar("INSERT INTO quejas(cliente_id,tipo,pedido_id,asunto,mensaje,creado,actualizado) VALUES(?,?,?,?,?,?,?)",
                              (_yo(), tipo, pedido, asunto, mensaje, t, t))
            bd.bitacora(g.usuario["usuario"], "queja_creada", f"PQR {qid}")
            flash("Solicitud enviada. Queda en estado Pendiente.", "ok")
        return redirect(url_for("cliente.ayuda"))
    return render_template("cliente/ayuda.html", tipos=TIPOS_PQR,
                           mis_pedidos=bd.todos("SELECT id, total FROM pedidos WHERE cliente_id=? ORDER BY id DESC", (_yo(),)),
                           quejas=bd.todos("SELECT * FROM quejas WHERE cliente_id=? ORDER BY creado DESC", (_yo(),)))
