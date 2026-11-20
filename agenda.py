"""
agenda.py  ·  HORAS LIBRES Y CREACIÓN DE CITAS
Regla clave: en una misma franja NO puede haber más citas al tiempo que los "cupos"
(puestos de trabajo) del salón. Ej.: un salón con 2 cupos atiende 2 clientes a las 10:00.
"""
from datetime import datetime, timedelta

import config
import base_datos as bd
import validaciones as v

ACTIVAS = "('pendiente','confirmada')"   # estados que ocupan cupo


def dia_semana(fecha):
    """Devuelve 0 = domingo, 1 = lunes ... 6 = sábado (igual que la tabla horarios)."""
    d = datetime.strptime(fecha, "%Y-%m-%d").date()
    return (d.weekday() + 1) % 7         # Python cuenta lunes=0 ... domingo=6; lo convertimos


def horas_libres(proveedor_id, servicio, fecha):
    """Lista de horas ('09:00', '09:30', ...) en las que se puede empezar este servicio ese día."""
    limite = (datetime.now(bd.BOGOTA).date() + timedelta(days=config.MAX_DIAS_ANTICIPACION)).isoformat()
    if fecha < bd.hoy() or fecha > limite:
        return []
    if bd.uno("SELECT 1 FROM cierres WHERE proveedor_id=? AND fecha=?", (proveedor_id, fecha)):
        return []                                        # el salón cerró ese día (festivo, etc.)
    dia = bd.uno("SELECT * FROM horarios WHERE proveedor_id=? AND dia=?", (proveedor_id, dia_semana(fecha)))
    if not dia or dia["cerrado"]:
        return []
    cupos = bd.uno("SELECT cupos FROM proveedores WHERE usuario_id=?", (proveedor_id,))["cupos"]
    ocupadas = [(v.a_minutos(c["hora"]), v.a_minutos(c["hora_fin"])) for c in bd.todos(
        f"SELECT hora, hora_fin FROM citas WHERE proveedor_id=? AND fecha=? AND estado IN {ACTIVAS}",
        (proveedor_id, fecha))]
    abre, cierra, duracion = v.a_minutos(dia["abre"]), v.a_minutos(dia["cierra"]), servicio["duracion_min"]
    libres, inicio = [], abre
    while inicio + duracion <= cierra:                   # el servicio debe terminar antes de cerrar
        ya_paso = fecha == bd.hoy() and inicio <= bd.minutos_ahora()
        if not ya_paso:
            fin = inicio + duracion
            cruzadas = sum(1 for s, e in ocupadas if s < fin and e > inicio)   # citas que se cruzan
            if cruzadas < cupos:
                libres.append(v.de_minutos(inicio))
        inicio += config.PASO_CITAS
    return libres


def crear_cita(proveedor_id, servicio_id, fecha, hora, cliente_id, nombre, telefono,
               modalidad="En el salón", notas="", origen="plataforma"):
    """Crea la cita. Devuelve (id_cita, None) si salió bien o (None, 'mensaje de error').

    BEGIN IMMEDIATE bloquea la base mientras se revisa y se guarda: así dos clientes
    NO pueden quedarse con el último cupo al mismo tiempo."""
    con = bd.db()
    con.execute("BEGIN IMMEDIATE")
    try:
        prov = bd.uno("SELECT * FROM proveedores WHERE usuario_id=?", (proveedor_id,))
        if not prov:
            con.rollback()
            return None, "Salón no encontrado"
        if origen == "plataforma" and prov["estado"] != "verificado":
            con.rollback()
            return None, "Este salón aún no está habilitado"
        svc = bd.uno("SELECT * FROM servicios WHERE id=? AND proveedor_id=? AND activo=1", (servicio_id, proveedor_id))
        if not svc:
            con.rollback()
            return None, "Ese servicio no está disponible"
        if hora not in horas_libres(proveedor_id, svc, fecha):
            con.rollback()
            return None, "Esa hora ya no está disponible. Elige otra."
        estado = "confirmada" if (origen == "manual" or prov["auto_confirmar"]) else "pendiente"
        fin = v.de_minutos(v.a_minutos(hora) + svc["duracion_min"])
        t = bd.ahora()
        cur = con.execute(
            """INSERT INTO citas(proveedor_id,servicio_id,cliente_id,servicio_nombre,precio,duracion_min,fecha,hora,hora_fin,
               cliente_nombre,cliente_telefono,modalidad,notas,origen,estado,creado,actualizado)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (proveedor_id, svc["id"], cliente_id, svc["nombre"], svc["precio"], svc["duracion_min"], fecha, hora, fin,
             nombre, telefono, modalidad, notas, origen, estado, t, t))
        con.commit()
        return cur.lastrowid, None
    except Exception:
        con.rollback()
        raise
