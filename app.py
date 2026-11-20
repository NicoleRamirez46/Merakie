"""
app.py  ·  ARCHIVO PRINCIPAL. Para iniciar la plataforma:  python app.py
Aquí se arma la aplicación: se conectan las tres partes (cliente, proveedor, administrador),
se carga la persona que tiene sesión iniciada y se definen los "filtros" para mostrar datos.
"""
import os
from datetime import timedelta
from flask import Flask, g, session, render_template, flash, request

import config
import base_datos as bd
from seguridad import csrf_token, verificar_csrf
from rutas_acceso import acceso
from rutas_cliente import cliente
from rutas_proveedor import proveedor
from rutas_admin import admin

# Menú de arriba según el tipo de usuario: (texto, nombre_de_la_ruta)
MENUS = {
    "cliente": [("Inicio", "cliente.inicio"), ("Salones y citas", "cliente.salones"), ("Tienda", "cliente.tienda"),
                ("Beneficios", "cliente.beneficios"), ("Mi calendario", "cliente.calendario"),
                ("Mis compras", "cliente.compras"), ("Ayuda / PQR", "cliente.ayuda"), ("Mi cuenta", "acceso.cuenta")],
    "proveedor": [("Inicio", "proveedor.inicio"), ("Mi salón", "proveedor.salon"), ("Servicios", "proveedor.servicios"),
                  ("Productos", "proveedor.productos"), ("Horarios", "proveedor.horarios"), ("Citas", "proveedor.citas"),
                  ("Documentos", "proveedor.documentos"), ("Mi cuenta", "acceso.cuenta")],
    "administrador": [("Resumen", "admin.resumen"), ("Clientes", "admin.clientes"), ("Proveedores", "admin.proveedores"),
                      ("Fraude", "admin.fraude_vista"), ("Pagos", "admin.pagos"), ("Inconformidades", "admin.quejas"),
                      ("Compras", "admin.compras"), ("Agendamientos", "admin.citas"), ("Auditoría", "admin.auditoria"),
                      ("Mi cuenta", "acceso.cuenta")],
}

ESTADO_TEXTO = {"pendiente_documentos": "Falta documentación", "en_revision": "En revisión", "verificado": "Verificado",
                "rechazado": "Rechazado", "suspendido": "Suspendido", "pendiente": "Pendiente", "confirmada": "Confirmada",
                "rechazada": "Rechazada", "completada": "Completada", "no_asistio": "No asistió", "cancelada": "Cancelada",
                "abierta": "Abierta", "sin_hallazgos": "Sin hallazgos"}
ESTADO_CLASE = {"ok": ("verificado", "confirmada", "completada", "Aprobado", "Resuelta", "Pagado", "sin_hallazgos"),
                "mal": ("rechazado", "rechazada", "suspendido", "cancelada", "Rechazado", "no_asistio"),
                "aviso": ("pendiente", "pendiente_documentos", "Pendiente", "Por pagar en la entrega", "abierta")}


def crear_app():
    app = Flask(__name__)
    app.secret_key = config.clave_secreta()
    app.config.update(
        MAX_CONTENT_LENGTH=6 * 1024 * 1024,          # nadie puede subir archivos de más de 6 MB
        SESSION_COOKIE_HTTPONLY=True,                # JavaScript no puede leer la cookie de sesión
        SESSION_COOKIE_SAMESITE="Lax",
        PERMANENT_SESSION_LIFETIME=timedelta(days=config.DIAS_SESION),
    )
    bd.crear_tablas()
    app.teardown_appcontext(bd.cerrar_db)            # cierra la base al terminar cada visita

    for parte in (acceso, cliente, proveedor, admin):  # conecta las cuatro partes
        app.register_blueprint(parte)

    @app.before_request
    def antes_de_cada_visita():
        """Se ejecuta ANTES de cada página: revisa el formulario (CSRF) y carga al usuario."""
        verificar_csrf()
        g.usuario = None
        uid = session.get("uid")
        if uid:
            u = bd.uno("SELECT * FROM usuarios WHERE id=? AND activo=1", (uid,))
            if u and u["rol"] == "proveedor":
                p = bd.uno("SELECT estado FROM proveedores WHERE usuario_id=?", (uid,))
                if p and p["estado"] == "suspendido":
                    u = None
                    session.clear()
                    flash("Tu cuenta está suspendida. Comunícate con Merakié.", "error")
            if u:
                g.usuario = u
            else:
                session.pop("uid", None)

    @app.context_processor
    def datos_para_todas_las_plantillas():
        """Variables que TODAS las páginas HTML pueden usar (menú, contadores, código CSRF)."""
        info = {"csrf_token": csrf_token, "hoy": bd.hoy(), "menu": [], "contador": {}}
        u = g.get("usuario")
        if u:
            info["menu"] = MENUS[u["rol"]]
            if u["rol"] == "cliente":
                info["contador"]["cliente.tienda"] = 0
                info["carrito_n"] = sum(session.get("carrito", {}).values())
            elif u["rol"] == "proveedor":
                n = bd.uno("SELECT COUNT(*) n FROM citas WHERE proveedor_id=? AND estado='pendiente'", (u["id"],))["n"]
                info["contador"]["proveedor.citas"] = n
            elif u["rol"] == "administrador":
                info["contador"]["admin.proveedores"] = bd.uno("SELECT COUNT(*) n FROM proveedores WHERE estado='en_revision'")["n"]
                info["contador"]["admin.quejas"] = bd.uno("SELECT COUNT(*) n FROM quejas WHERE estado='Pendiente'")["n"]
        return info

    # ---------- Filtros: transforman un dato antes de mostrarlo en la página ----------
    @app.template_filter("pesos")
    def pesos(n):
        return "$" + f"{int(n or 0):,}".replace(",", ".")            # 45000 -> $45.000

    @app.template_filter("fecha")
    def fecha(s):
        s = str(s or "")
        return f"{s[8:10]}/{s[5:7]}/{s[:4]}" if len(s) >= 10 else "—"   # 2026-11-17 -> 17/11/2026

    @app.template_filter("fecha_hora")
    def fecha_hora(s):
        s = str(s or "")
        return f"{s[8:10]}/{s[5:7]}/{s[:4]} {s[11:16]}" if len(s) >= 16 else "—"

    @app.template_filter("estado_texto")
    def estado_texto(e):
        return ESTADO_TEXTO.get(e, e)

    @app.template_filter("estado_clase")
    def estado_clase(e):
        for clase, estados in ESTADO_CLASE.items():
            if e in estados:
                return clase
        return "info"

    @app.template_filter("oculto")
    def oculto(doc):
        return "•••" + doc[-3:] if doc else "—"                      # 1234567 -> •••567

    # ---------- Páginas de error ----------
    @app.errorhandler(400)
    @app.errorhandler(403)
    @app.errorhandler(404)
    @app.errorhandler(413)
    def error(e):
        textos = {400: "Solicitud no válida", 403: "No tienes permiso para ver esta página",
                  404: "Página no encontrada", 413: "El archivo es demasiado grande (máximo 5 MB)"}
        detalle = e.description if e.code == 400 else ""
        return render_template("error.html", codigo=e.code, titulo=textos.get(e.code, "Error"), detalle=detalle), e.code

    return app


app = crear_app()

if __name__ == "__main__":
    if config.CODIGO_ADMIN == "MERAKIE-ADMIN-2026":
        print("\nATENCION: estas usando el codigo de administrador de ejemplo. Cambialo en config.py antes de publicar.\n")
    puerto = int(os.environ.get("PORT", 5000))      # si el puerto 5000 esta ocupado: set PORT=5001
    print(f"Merakie listo. Abre en tu navegador:  http://127.0.0.1:{puerto}   (para detener: Ctrl + C)")
    app.run(host="127.0.0.1", port=puerto, debug=False)
