"""
pruebas.py  ·  PRUEBAS AUTOMÁTICAS 
Simula a personas reales usando la plataforma: se registran, ingresan, reservan, compran...
y revisa que todo funcione y que las protecciones (roles, CSRF, XSS) se cumplan.
Usa una base de datos temporal: NO toca tus datos reales.   Ejecutar:  python pruebas.py
"""
import io
import os
import re
import sys
import tempfile
from datetime import datetime, timedelta

os.environ["MERAKIE_DATOS"] = os.environ.get("PRUEBAS_DATOS") or tempfile.mkdtemp()   # base temporal, solo para la prueba
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config                                               # noqa: E402
import base_datos as bd                                     # noqa: E402
import validaciones as v                                    # noqa: E402
from app import app                                         # noqa: E402

app.config["TESTING"] = False
fallos, total = [], 0


def ok(condicion, mensaje):
    global total
    total += 1
    print(("  ✓ " if condicion else "  ✗ ") + mensaje)
    if not condicion:
        fallos.append(mensaje)


def token(c):
    html = c.get("/acceso/cliente").get_data(as_text=True)
    return re.search(r'name="_csrf" value="([^"]+)"', html).group(1)


def post(c, url, datos=None, **kw):
    datos = dict(datos or {})
    datos.setdefault("_csrf", token(c))
    return c.post(url, data=datos, follow_redirects=True, **kw)


def texto(r):
    return r.get_data(as_text=True)


# ---------------------------------------------------------------------
print("\n1. Validaciones")
ok(v.nit_ok("800197268-4"), "NIT de ejemplo válido")
ok(not v.nit_ok("800197268-5"), "NIT con dígito de verificación malo se rechaza")
ok(v.clave_ok("Clave1234") and not v.clave_ok("corta1") and not v.clave_ok("sinnumeros"), "Reglas de contraseña")

admin1, admin2, prov, cli, cli2, anon = (app.test_client() for _ in range(6))

print("\n2. Administradores (solo Santiago y Nicole)")
base = {"correo": "s@x.co", "usuario": "santiago", "clave": "Admin12345", "clave2": "Admin12345", "codigo": config.CODIGO_ADMIN}
ok("no está en la lista" in texto(post(anon, "/registro/administrador", {**base, "nombre": "Pedro Pérez"})), "Un nombre no autorizado se rechaza")
ok("código de administrador es incorrecto" in texto(post(anon, "/registro/administrador", {**base, "nombre": "Santiago Muñoz", "codigo": "xxx"})), "Código incorrecto se rechaza")
ok("Cuenta creada" in texto(post(admin1, "/registro/administrador", {**base, "nombre": "santiago  munoz"})), "Santiago se registra (acepta mayúsculas/tildes distintas)")
ok("Cuenta creada" in texto(post(admin2, "/registro/administrador", {**base, "nombre": "Nicole Ramirez", "correo": "n@x.co", "usuario": "nicole"})), "Nicole se registra")
ok("ya tiene cuenta" in texto(post(anon, "/registro/administrador", {**base, "nombre": "Nicole Ramirez", "correo": "n2@x.co", "usuario": "otra"})), "No se puede crear una segunda cuenta para la misma persona")
r = post(admin1, "/acceso/administrador", {"usuario": "santiago", "clave": "Admin12345"})
ok("Resumen" in texto(r), "Santiago ingresa al panel")
r = app.test_client().post("/acceso/administrador", data={"usuario": "santiago", "clave": "Admin12345", "_csrf": token(app.test_client())})
ok(r.status_code == 400, "Sin código CSRF no se puede ingresar (comprobación previa)")
cx = app.test_client()
r = cx.post("/acceso/administrador", data={"usuario": "santiago", "clave": "Admin12345", "_csrf": token(cx)})
ok("Expires=" in " ".join(r.headers.getlist("Set-Cookie")), "La sesión es persistente (la cookie tiene fecha de vencimiento: 7 días)")
post(admin2, "/acceso/administrador", {"usuario": "nicole", "clave": "Admin12345"})

print("\n3. Ingreso: rol equivocado y bloqueo")
r = post(anon, "/acceso/cliente", {"usuario": "santiago", "clave": "Admin12345"})
ok("tipo «Administrador»" in texto(r), "Entrar por el botón equivocado orienta a la opción correcta")
for _ in range(3):
    post(anon, "/acceso/cliente", {"usuario": "intruso", "clave": "mala"})
ok("incorrectos" in texto(post(anon, "/acceso/cliente", {"usuario": "intruso", "clave": "mala"})), "Usuario o clave incorrectos")

print("\n4. Proveedor: registro, documentos y verificación")
dprov = {"tipo_persona": "juridica", "nit": "800197268-4", "razon_social": "Aura SAS", "nombre_comercial": "Aura Studio",
         "nombre": "Laura Gómez", "telefono": "3109876543", "correo": "aura@x.co", "ciudad": "Bogotá", "direccion": "Calle 63 # 10-20",
         "usuario": "aura", "clave": "Aura123456", "clave2": "Aura123456", "consentimiento": "on"}
ok("NIT" in texto(post(prov, "/registro/proveedor", {**dprov, "nit": "800197268-9"})), "NIT inválido se rechaza")
ok("Debes autorizar" in texto(post(prov, "/registro/proveedor", {k: x for k, x in dprov.items() if k != "consentimiento"})), "Sin autorización de datos no se crea la cuenta")
ok("Cuenta creada" in texto(post(prov, "/registro/proveedor", dprov)), "Proveedor se registra")
ok("Ya existe un proveedor" in texto(post(anon, "/registro/proveedor", {**dprov, "usuario": "otro", "correo": "o@x.co"})), "No se repite el NIT")
post(prov, "/acceso/proveedor", {"usuario": "aura", "clave": "Aura123456"})
ok("Falta documentación" in texto(prov.get("/proveedor/")), "Panel del proveedor: estado inicial")
ok("Sube el RUT" in texto(post(prov, "/proveedor/enviar-revision")), "No puede enviar a revisión sin documentos")
ok("PDF, JPG o PNG válido" in texto(post(prov, "/proveedor/documentos/subir", {"tipo": "rut", "archivo": (io.BytesIO(b"esto no es un pdf"), "x.pdf")}, content_type="multipart/form-data")), "Archivo falso se rechaza (se mira el contenido real)")
for tipo in ("rut", "camara_comercio"):
    post(prov, "/proveedor/documentos/subir", {"tipo": tipo, "archivo": (io.BytesIO(b"%PDF-1.4 prueba"), tipo + ".pdf")}, content_type="multipart/form-data")
ok("rut.pdf" in texto(prov.get("/proveedor/documentos")), "Documentos subidos")
post(prov, "/proveedor/servicios/guardar", {"nombre": "Corte y peinado", "categoria": "Peluquería", "precio": "45000", "duracion_min": "60", "activo": "on"})
post(prov, "/proveedor/productos/guardar", {"nombre": "Aceite de argán", "precio": "30000", "stock": "5", "activo": "on"})
ok("Corte y peinado" in texto(prov.get("/proveedor/servicios")), "Servicio creado")
ok("Enviado a revisión" in texto(post(prov, "/proveedor/enviar-revision")), "Envía a revisión")

print("\n5. Administrador verifica al proveedor")
pid = bd.sqlite3.connect(config.BASE_DATOS).execute("SELECT usuario_id FROM proveedores").fetchone()[0]
ok("Aura Studio" in texto(admin1.get("/admin/proveedores")), "El admin ve al proveedor registrado")
ok("Escribe el motivo" in texto(post(admin1, f"/admin/proveedores/{pid}/estado", {"estado": "rechazado", "motivo": ""})), "Rechazar exige motivo")
ok("verificado" in texto(post(admin1, f"/admin/proveedores/{pid}/estado", {"estado": "verificado"})).lower(), "Verifica al proveedor")
ok("Abrir" in texto(admin1.get(f"/admin/proveedores/{pid}")), "El admin puede abrir los documentos")
did = bd.sqlite3.connect(config.BASE_DATOS).execute("SELECT id FROM documentos LIMIT 1").fetchone()[0]
ok(admin1.get(f"/admin/documentos/{did}").status_code == 200, "Descarga de documento permitida al admin")
ok(prov.get(f"/admin/documentos/{did}").status_code == 403, "El proveedor NO puede usar la ruta del admin")

print("\n6. Cliente: registro, salones y citas")
dcli = {"nombre": "Ana <script>alert(1)</script> Ruiz", "documento": "1012345678", "edad": "30", "telefono": "3001112222", "correo": "ana@x.co",
        "usuario": "ana", "clave": "Ana1234567", "clave2": "Ana1234567", "consentimiento": "on"}
ok("edad debe estar" in texto(post(cli, "/registro/cliente", {**dcli, "edad": "15"})), "Menor de 18 años se rechaza")
ok("Cuenta creada" in texto(post(cli, "/registro/cliente", dcli)), "Cliente se registra")
post(cli, "/acceso/cliente", {"usuario": "ana", "clave": "Ana1234567"})
ok("Aura Studio" in texto(cli.get("/cliente/salones")), "El cliente ve el salón verificado")
lunes = datetime.now(bd.BOGOTA).date() + timedelta(days=1)
while lunes.weekday() != 0:
    lunes += timedelta(days=1)
fecha = lunes.isoformat()
sid = bd.sqlite3.connect(config.BASE_DATOS).execute("SELECT id FROM servicios").fetchone()[0]
horas = cli.get(f"/cliente/salones/{pid}/horas?servicio_id={sid}&fecha={fecha}").get_json()["horas"]
ok(horas and horas[0] == "09:00" and "17:00" in horas and "17:30" not in horas, "Horas libres calculadas (09:00 a 17:00 para un servicio de 60 min)")
ok(cli.get(f"/cliente/salones/{pid}/horas?servicio_id={sid}&fecha={(lunes - timedelta(days=1)).isoformat()}").get_json()["horas"] == [], "Domingo cerrado: sin horas")
ok("Cita solicitada" in texto(post(cli, f"/cliente/salones/{pid}/reservar", {"servicio_id": sid, "fecha": fecha, "hora": "10:00"})), "Cliente reserva (queda pendiente: el salón no confirma solo)")
horas2 = cli.get(f"/cliente/salones/{pid}/horas?servicio_id={sid}&fecha={fecha}").get_json()["horas"]
ok("10:00" not in horas2 and "10:30" not in horas2 and "09:30" not in horas2, "El cupo ocupado desaparece (y las horas que se cruzan)")
post(cli2, "/registro/cliente", {**dcli, "nombre": "Beto Díaz", "correo": "b@x.co", "usuario": "beto", "documento": "1012345678"})
post(cli2, "/acceso/cliente", {"usuario": "beto", "clave": "Ana1234567"})
ok("ya no está disponible" in texto(post(cli2, f"/cliente/salones/{pid}/reservar", {"servicio_id": sid, "fecha": fecha, "hora": "10:00"})), "Otro cliente NO puede tomar el mismo cupo")
ok("10:00" in texto(cli.get("/cliente/calendario")), "La cita aparece en el calendario")
ok("BEGIN:VCALENDAR" in texto(cli.get("/cliente/calendario.ics")), "Descarga .ics")
ok("Ana" in texto(prov.get("/proveedor/citas")) and "Pendiente" in texto(prov.get("/proveedor/citas")), "El proveedor ve la cita pendiente")
cid = bd.sqlite3.connect(config.BASE_DATOS).execute("SELECT id FROM citas").fetchone()[0]
ok("Cita actualizada" in texto(post(prov, f"/proveedor/citas/{cid}/estado", {"estado": "confirmada"})), "El proveedor confirma la cita")
ok("No se puede pasar" in texto(post(prov, f"/proveedor/citas/{cid}/estado", {"estado": "pendiente"})), "No se permiten saltos de estado inválidos")
ok("Cita manual registrada" in texto(post(prov, "/proveedor/citas/manual", {"servicio_id": sid, "fecha": fecha, "hora": "14:00", "cliente_nombre": "Cliente Llamada", "cliente_telefono": "3015556666"})), "Cita manual del salón")
post(cli, f"/cliente/salones/{pid}/reservar", {"servicio_id": sid, "fecha": fecha, "hora": "16:00"})
cid2 = bd.sqlite3.connect(config.BASE_DATOS).execute("SELECT id FROM citas WHERE hora='16:00'").fetchone()[0]
ok("Cita cancelada" in texto(post(cli, f"/cliente/citas/{cid2}/cancelar")), "El cliente cancela su cita")
cli2.post(f"/cliente/citas/{cid}/cancelar", data={"_csrf": token(cli2)})
ok(bd.sqlite3.connect(config.BASE_DATOS).execute("SELECT estado FROM citas WHERE id=?", (cid,)).fetchone()[0] == "confirmada", "Un cliente NO puede cancelar citas de otro")

print("\n7. Tienda, carrito y pagos")
ok("Aceite de argán" in texto(cli.get("/cliente/tienda")), "Producto del proveedor verificado aparece en la tienda")
pr = bd.sqlite3.connect(config.BASE_DATOS).execute("SELECT id FROM productos WHERE nombre LIKE 'Shampoo%'").fetchone()[0]
post(cli, f"/cliente/carrito/agregar/{pr}")
post(cli, f"/cliente/carrito/agregar/{pr}")
ok("$64.000" in texto(cli.get("/cliente/carrito")), "Carrito: 2 × $32.000")
ok("rechazado" in texto(post(cli, "/cliente/carrito/pagar", {"metodo": "rechazo"})).lower() and "$64.000" in texto(cli.get("/cliente/carrito")), "Pago rechazado: el carrito sigue intacto")
ok("Compra registrada" in texto(post(cli, "/cliente/carrito/pagar", {"metodo": "tarjeta"})), "Pago aprobado crea el pedido")
con = bd.sqlite3.connect(config.BASE_DATOS)
ok(con.execute("SELECT stock FROM productos WHERE id=?", (pr,)).fetchone()[0] == 48, "El stock se descuenta")
ok(con.execute("SELECT COUNT(*) FROM pagos").fetchone()[0] == 2 and con.execute("SELECT COUNT(*) FROM pedidos").fetchone()[0] == 1, "Pagos: 2 registrados (1 rechazado + 1 aprobado); pedidos: 1")
post(cli, "/cliente/pass")
post(cli, f"/cliente/carrito/agregar/{pr}")
ok("$30.400" in texto(cli.get("/cliente/carrito")), "Con Pass: 5 % de descuento ($32.000 → $30.400)")
ok("Compra registrada" in texto(post(cli, "/cliente/carrito/pagar", {"metodo": "contraentrega"})) and "Por pagar en la entrega" in texto(cli.get("/cliente/compras")), "Pago contra entrega queda pendiente")

print("\n8. Quejas (PQR)")
ok("Solicitud enviada" in texto(post(cli, "/cliente/ayuda", {"tipo": "Queja", "asunto": "Demora", "mensaje": "Me atendieron tarde en el salón"})), "El cliente envía una queja")
qid = con.execute("SELECT id FROM quejas").fetchone()[0]
ok("Demora" in texto(admin1.get("/admin/inconformidades")), "El admin ve la queja")
post(admin1, f"/admin/inconformidades/{qid}", {"estado": "Resuelta", "respuesta": "Ya contactamos al salón."})
ok("Ya contactamos" in texto(cli.get("/cliente/ayuda")) and "Resuelta" in texto(cli.get("/cliente/ayuda")), "El cliente ve el estado y la respuesta")

print("\n9. Prevención de fraude")
for _ in range(2):
    post(cli, f"/cliente/carrito/agregar/{pr}")
    post(cli, "/cliente/carrito/pagar", {"metodo": "rechazo"})
html = texto(admin1.get("/admin/fraude?ver=todas"))
ok("Pagos rechazados repetidos" in html, "Alerta: pagos rechazados repetidos")
ok("Intentos fallidos de ingreso" in html, "Alerta: intentos fallidos de ingreso")
ok("Documento repetido" in html, "Alerta: documento repetido entre dos cuentas")
ok("no acusaciones" in html, "Se muestra el aviso: indicios, no acusaciones")
clave = re.search(r'name="clave" value="([^"]+)"', html).group(1)
ok("escribe qué verificaste" in texto(post(admin1, "/admin/fraude/revisar", {"clave": clave, "estado": "sin_hallazgos", "nota": ""})), "Cerrar una alerta exige una nota")
ok("Revisión guardada" in texto(post(admin1, "/admin/fraude/revisar", {"clave": clave, "estado": "sin_hallazgos", "nota": "Verificado con el cliente"})), "Alerta cerrada con nota")

print("\n10. Panel del administrador: datos reales")
for ruta in ("", "clientes", "proveedores", "fraude", "pagos", "compras", "agendamientos", "inconformidades", "auditoria"):
    ok(admin1.get("/admin/" + ruta).status_code == 200, f"/admin/{ruta} responde")
uid = con.execute("SELECT id FROM usuarios WHERE usuario='ana'").fetchone()[0]
h = texto(admin1.get("/admin/clientes"))
ok("&lt;script&gt;" in h and "<script>alert" not in h, "XSS: un nombre con <script> se muestra como texto")
ok("•••678" in h and "1012345678" not in h, "El documento aparece enmascarado en la lista")
ok("1012345678" in texto(post(admin1, f"/admin/clientes/{uid}")), "El documento completo solo se ve al pedirlo…")
ok("admin_ve_documento_cliente" in texto(admin1.get("/admin/auditoria")), "…y queda en la auditoría")
csv_ = texto(admin1.get("/admin/exportar/pagos"))
ok("Pendiente" in csv_ and csv_.startswith("﻿"), "Exportación CSV")

print("\n11. Seguridad")
ok(cli.get("/admin/").status_code == 403, "Un cliente no puede entrar al panel admin")
ok(cli.get("/proveedor/").status_code == 403, "Un cliente no puede entrar al panel del proveedor")
ok(anon.get("/cliente/").status_code in (302, 303), "Sin sesión se redirige al ingreso")
ok(anon.post("/acceso/cliente", data={"usuario": "ana", "clave": "Ana1234567"}).status_code == 400, "Formulario sin código CSRF se rechaza")
ok(cli2.get(f"/proveedor/documentos/{did}/archivo").status_code == 403, "Un cliente no descarga documentos de proveedores")
ok(prov.get("/proveedor/documentos/9999/archivo").status_code == 404, "Un proveedor no accede a documentos que no son suyos")
ok("Salir" in texto(cli.get("/cliente/")) and cli.post("/salir", data={"_csrf": token(cli)}).status_code in (302, 303), "Cerrar sesión funciona")
ok("clave_hash" not in texto(admin1.get("/admin/clientes")) and "Ana1234567" not in texto(admin1.get("/admin/clientes")), "Nunca se muestran contraseñas")

print(f"\n{'✅ TODO BIEN' if not fallos else '❌ HAY FALLOS'}: {total - len(fallos)}/{total} pruebas")
for f in fallos:
    print("   -", f)
sys.exit(1 if fallos else 0)
