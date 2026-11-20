"""
fraude.py  ·  ALERTAS DE PREVENCIÓN DE FRAUDE
IMPORTANTE: una alerta es un INDICIO para que una persona lo revise, NUNCA una acusación.
Casi siempre hay una explicación normal (un regalo, una familia que comparte teléfono, un error).
Por eso el sistema solo avisa; no bloquea ni sanciona a nadie automáticamente.

Cada regla busca un patrón en la base de datos y crea una alerta con una "clave" única.
Con esa clave se guarda si el administrador ya la revisó (tabla alertas_revision).
"""
from datetime import datetime

import config
import base_datos as bd

SEVERIDAD = {"alta": 0, "media": 1, "baja": 2}


def _fecha(texto):
    return datetime.strptime(texto, "%Y-%m-%d %H:%M:%S")


def _ventana(lista, n, minutos):
    """Busca n eventos (ordenados por fecha) dentro de un lapso de X minutos.
    Devuelve el primero de ese grupo, o None."""
    for i in range(len(lista) - n + 1):
        if (_fecha(lista[i + n - 1]["creado"]) - _fecha(lista[i]["creado"])).total_seconds() <= minutos * 60:
            return lista[i]
    return None


def calcular_alertas():
    A = []

    def nuevo(clave, sev, titulo, detalle):
        A.append({"clave": clave, "sev": sev, "titulo": titulo, "detalle": detalle})

    def quien(uid):
        u = bd.uno("SELECT nombre, usuario FROM usuarios WHERE id=?", (uid,))
        return f"{u['nombre']} (@{u['usuario']})" if u else f"cuenta #{uid}"

    pesos = lambda n: "$" + f"{n:,.0f}".replace(",", ".")
    hace24h = bd.hace(24 * 60)

    # R1 · Varios intentos fallidos de ingreso en 24 horas
    for r in bd.todos("SELECT detalle AS usuario, COUNT(*) n FROM bitacora WHERE accion='login_fallido' AND fecha>? "
                      "GROUP BY detalle HAVING n>=3", (hace24h,)):
        nuevo(f"login:{r['usuario']}:{r['n']}", "media", "Intentos fallidos de ingreso",
              f"El usuario «{r['usuario']}» tuvo {r['n']} intentos fallidos en 24 h. Puede ser olvido de clave o un intento de acceso ajeno.")

    # R2 · Pagos rechazados repetidos
    for r in bd.todos("SELECT cliente_id, COUNT(*) n, SUM(valor) total FROM pagos WHERE estado='Rechazado' AND creado>? "
                      "GROUP BY cliente_id HAVING n>=2", (hace24h,)):
        nuevo(f"rechazados:{r['cliente_id']}:{r['n']}", "media", "Pagos rechazados repetidos",
              f"{quien(r['cliente_id'])} tiene {r['n']} pagos rechazados en 24 h por {pesos(r['total'])}. Puede ser falta de fondos o un medio de pago ajeno.")

    # R3 · Pago de valor alto
    for p in bd.todos("SELECT * FROM pagos WHERE estado!='Rechazado' AND valor>=?", (config.UMBRAL_PAGO_ALTO,)):
        nuevo(f"pago_alto:{p['id']}", "baja", "Pago de valor alto",
              f"Pago #{p['id']} de {quien(p['cliente_id'])} por {pesos(p['valor'])} (umbral {pesos(config.UMBRAL_PAGO_ALTO)}). Basta con confirmar que es coherente con su historial.")

    # R4 · Cuenta nueva con un pago relevante (menos de 24 h desde el registro)
    for p in bd.todos("SELECT p.*, u.creado AS cuenta_creada FROM pagos p JOIN usuarios u ON u.id=p.cliente_id "
                      "WHERE p.estado!='Rechazado' AND p.valor>=?", (config.UMBRAL_PAGO_ALTO / 2,)):
        if (_fecha(p["creado"]) - _fecha(p["cuenta_creada"])).total_seconds() < 86400:
            nuevo(f"cuenta_nueva:{p['id']}", "media", "Pago relevante en cuenta nueva",
                  f"{quien(p['cliente_id'])} pagó {pesos(p['valor'])} menos de 24 h después de crear su cuenta.")

    # R5 · Ráfaga de pagos (3 o más en 10 minutos)
    por_cliente = {}
    for p in bd.todos("SELECT id, cliente_id, creado FROM pagos ORDER BY creado"):
        por_cliente.setdefault(p["cliente_id"], []).append(p)
    for cid, lista in por_cliente.items():
        primero = _ventana(lista, 3, 10)
        if primero:
            nuevo(f"pagos_rafaga:{cid}:{primero['id']}", "media", "Varios pagos en poco tiempo",
                  f"{quien(cid)} registró 3 o más pagos en 10 minutos.")

    # R6 · Ráfaga de reservas (3 o más citas creadas en 10 minutos)
    por_cliente = {}
    for c in bd.todos("SELECT id, cliente_id, creado FROM citas WHERE origen='plataforma' AND cliente_id IS NOT NULL ORDER BY creado"):
        por_cliente.setdefault(c["cliente_id"], []).append(c)
    for cid, lista in por_cliente.items():
        primero = _ventana(lista, 3, 10)
        if primero:
            nuevo(f"citas_rafaga:{cid}:{primero['id']}", "baja", "Ráfaga de reservas",
                  f"{quien(cid)} creó 3 o más reservas en 10 minutos. Puede ser una reserva grupal legítima o un uso abusivo de los cupos.")

    # R7 · Citas a la misma hora en salones distintos
    for r in bd.todos("SELECT cliente_id, fecha, hora, COUNT(DISTINCT proveedor_id) n FROM citas "
                      "WHERE estado IN ('pendiente','confirmada') AND cliente_id IS NOT NULL "
                      "GROUP BY cliente_id, fecha, hora HAVING n>1"):
        nuevo(f"citas_simultaneas:{r['cliente_id']}:{r['fecha']}:{r['hora']}", "media", "Citas simultáneas en salones distintos",
              f"{quien(r['cliente_id'])} reservó {r['n']} salones diferentes para el {r['fecha']} a las {r['hora']}.")

    # R8 · Datos repetidos entre cuentas de clientes distintas
    for r in bd.todos("SELECT c.documento AS dato, COUNT(*) n, GROUP_CONCAT(u.usuario) quienes FROM clientes c "
                      "JOIN usuarios u ON u.id=c.usuario_id WHERE c.documento!='' GROUP BY c.documento HAVING n>1"):
        nuevo(f"doc_repetido:{r['dato']}:{r['n']}", "media", "Documento repetido en varias cuentas",
              f"{r['n']} cuentas comparten el mismo documento ({r['quienes']}). Puede ser un error de digitación o una cuenta duplicada.")
    for r in bd.todos("SELECT telefono AS dato, COUNT(*) n, GROUP_CONCAT(usuario) quienes FROM usuarios "
                      "WHERE rol='cliente' AND telefono!='' GROUP BY telefono HAVING n>1"):
        nuevo(f"tel_repetido:{r['dato']}:{r['n']}", "baja", "Teléfono repetido en varias cuentas",
              f"{r['n']} clientes comparten el teléfono terminado en {r['dato'][-4:]} ({r['quienes']}). Puede ser una familia.")

    # R9 · Proveedores esperando verificación
    for p in bd.todos("SELECT usuario_id, nombre_comercial, nit, estado_fecha FROM proveedores WHERE estado='en_revision'"):
        dias = (datetime.now(bd.BOGOTA).replace(tzinfo=None) - _fecha(p["estado_fecha"])).days if p["estado_fecha"] else 0
        nuevo(f"prov_pendiente:{p['usuario_id']}", "media" if dias > 3 else "baja", "Proveedor pendiente de verificar",
              f"«{p['nombre_comercial']}» (NIT {p['nit']}) lleva {dias} día(s) esperando revisión de documentos.")

    # Se le agrega a cada alerta su estado de revisión (si alguien ya la miró)
    revisadas = {r["clave"]: r for r in bd.todos("SELECT * FROM alertas_revision")}
    for a in A:
        r = revisadas.get(a["clave"])
        a.update(estado=r["estado"] if r else "abierta", nota=r["nota"] if r else "",
                 por=r["revisado_por"] if r else "", fecha=r["fecha"] if r else "")
    return sorted(A, key=lambda a: SEVERIDAD[a["sev"]])
