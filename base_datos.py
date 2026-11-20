"""
base_datos.py  ·  LA BASE DE DATOS (SQLite)
SQLite guarda TODO en un solo archivo (datos/merakie.db). No hay que instalar nada.

Tablas principales (una "tabla" es como una hoja de Excel):
  usuarios      -> TODA persona que entra: cliente, proveedor o administrador (usuario + clave propios)
  clientes      -> datos extra de los clientes (documento, edad, Pass)
  proveedores   -> datos extra de los salones (NIT, estado de verificación...)
  servicios, horarios, cierres, documentos -> lo que administra cada proveedor
  productos     -> la tienda
  citas         -> reservas de los clientes en los salones
  pedidos, pedido_items, pagos -> compras y pagos
  quejas        -> inconformidades (PQR)
  alertas_revision, bitacora -> prevención de fraude y auditoría
"""
import sqlite3
from datetime import datetime, timedelta, timezone
from flask import g, request

import config

# Colombia está en UTC-5 todo el año (no tiene horario de verano).
BOGOTA = timezone(timedelta(hours=-5))


# ---------- Fechas y horas (siempre hora de Colombia) ----------
def ahora():
    return datetime.now(BOGOTA).strftime("%Y-%m-%d %H:%M:%S")


def hoy():
    return datetime.now(BOGOTA).strftime("%Y-%m-%d")


def minutos_ahora():
    n = datetime.now(BOGOTA)
    return n.hour * 60 + n.minute


def hace(minutos):
    """Texto de fecha de hace X minutos (sirve para filtrar 'las últimas 24 horas')."""
    return (datetime.now(BOGOTA) - timedelta(minutes=minutos)).strftime("%Y-%m-%d %H:%M:%S")


# ---------- Conexión ----------
def db():
    """Abre la conexión UNA vez por visita (petición) y la reutiliza."""
    if "db" not in g:
        con = sqlite3.connect(config.BASE_DATOS, timeout=10)
        con.row_factory = sqlite3.Row            # permite usar fila["nombre"] en vez de fila[0]
        con.execute("PRAGMA foreign_keys = ON")  # la base impide registros "huérfanos"
        g.db = con
    return g.db


def cerrar_db(error=None):
    con = g.pop("db", None)
    if con is not None:
        con.close()


def uno(sql, args=()):
    """Devuelve UNA fila (o None). Los ? se reemplazan por args: así nadie puede 'inyectar' SQL."""
    return db().execute(sql, args).fetchone()


def todos(sql, args=()):
    """Devuelve una lista de filas."""
    return db().execute(sql, args).fetchall()


def ejecutar(sql, args=()):
    """INSERT / UPDATE / DELETE: ejecuta, guarda (commit) y devuelve el id creado."""
    cur = db().execute(sql, args)
    db().commit()
    return cur.lastrowid


def bitacora(actor, accion, detalle=""):
    """Deja constancia de QUIÉN hizo QUÉ y CUÁNDO (auditoría)."""
    ip = request.remote_addr if request else ""
    ejecutar("INSERT INTO bitacora(actor,accion,detalle,ip,fecha) VALUES(?,?,?,?,?)",
             (str(actor), accion, str(detalle)[:500], ip, ahora()))


# ---------- Esquema ----------
ESQUEMA = """
CREATE TABLE IF NOT EXISTS usuarios (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  rol TEXT NOT NULL CHECK (rol IN ('cliente','proveedor','administrador')),
  usuario TEXT NOT NULL UNIQUE COLLATE NOCASE,
  nombre TEXT NOT NULL,
  correo TEXT NOT NULL UNIQUE COLLATE NOCASE,
  telefono TEXT NOT NULL DEFAULT '',
  clave_hash TEXT NOT NULL,                 -- la clave NUNCA se guarda: solo su 'huella' (hash)
  activo INTEGER NOT NULL DEFAULT 1,
  creado TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS clientes (
  usuario_id INTEGER PRIMARY KEY REFERENCES usuarios(id) ON DELETE CASCADE,
  documento TEXT NOT NULL DEFAULT '',
  edad INTEGER NOT NULL,
  pass_activo INTEGER NOT NULL DEFAULT 0,
  consentimiento_fecha TEXT NOT NULL,
  consentimiento_version TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS proveedores (
  usuario_id INTEGER PRIMARY KEY REFERENCES usuarios(id) ON DELETE CASCADE,
  tipo_persona TEXT NOT NULL CHECK (tipo_persona IN ('juridica','natural')),
  razon_social TEXT NOT NULL,
  nombre_comercial TEXT NOT NULL,
  nit TEXT NOT NULL UNIQUE,
  ciudad TEXT NOT NULL,
  direccion TEXT NOT NULL,
  descripcion TEXT NOT NULL DEFAULT '',
  estado TEXT NOT NULL DEFAULT 'pendiente_documentos'
    CHECK (estado IN ('pendiente_documentos','en_revision','verificado','rechazado','suspendido')),
  motivo TEXT NOT NULL DEFAULT '',
  estado_fecha TEXT,
  auto_confirmar INTEGER NOT NULL DEFAULT 0,
  cupos INTEGER NOT NULL DEFAULT 1 CHECK (cupos BETWEEN 1 AND 50),
  consentimiento_fecha TEXT NOT NULL,
  consentimiento_version TEXT NOT NULL,
  creado TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS servicios (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  proveedor_id INTEGER NOT NULL REFERENCES proveedores(usuario_id) ON DELETE CASCADE,
  nombre TEXT NOT NULL, categoria TEXT NOT NULL, descripcion TEXT NOT NULL DEFAULT '',
  precio INTEGER NOT NULL CHECK (precio >= 0),
  duracion_min INTEGER NOT NULL CHECK (duracion_min BETWEEN 10 AND 600),
  activo INTEGER NOT NULL DEFAULT 1,
  creado TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS horarios (
  proveedor_id INTEGER NOT NULL REFERENCES proveedores(usuario_id) ON DELETE CASCADE,
  dia INTEGER NOT NULL CHECK (dia BETWEEN 0 AND 6),      -- 0 = domingo, 1 = lunes ... 6 = sábado
  cerrado INTEGER NOT NULL DEFAULT 0,
  abre TEXT NOT NULL, cierra TEXT NOT NULL,
  PRIMARY KEY (proveedor_id, dia)
);
CREATE TABLE IF NOT EXISTS cierres (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  proveedor_id INTEGER NOT NULL REFERENCES proveedores(usuario_id) ON DELETE CASCADE,
  fecha TEXT NOT NULL, motivo TEXT NOT NULL DEFAULT '',
  UNIQUE (proveedor_id, fecha)
);
CREATE TABLE IF NOT EXISTS documentos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  proveedor_id INTEGER NOT NULL REFERENCES proveedores(usuario_id) ON DELETE CASCADE,
  tipo TEXT NOT NULL, nombre_original TEXT NOT NULL, nombre_guardado TEXT NOT NULL,
  mime TEXT NOT NULL, tamano INTEGER NOT NULL, subido TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS productos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  proveedor_id INTEGER REFERENCES proveedores(usuario_id) ON DELETE CASCADE,  -- NULL = producto propio de Merakié
  nombre TEXT NOT NULL, descripcion TEXT NOT NULL DEFAULT '',
  precio INTEGER NOT NULL CHECK (precio >= 0),
  stock INTEGER NOT NULL DEFAULT 0 CHECK (stock >= 0),
  emoji TEXT NOT NULL DEFAULT '🛍️',
  activo INTEGER NOT NULL DEFAULT 1,
  creado TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS citas (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  proveedor_id INTEGER NOT NULL REFERENCES proveedores(usuario_id) ON DELETE CASCADE,
  servicio_id INTEGER REFERENCES servicios(id) ON DELETE SET NULL,
  cliente_id INTEGER REFERENCES usuarios(id) ON DELETE SET NULL,     -- NULL si la creó el salón (llamada)
  servicio_nombre TEXT NOT NULL, precio INTEGER NOT NULL, duracion_min INTEGER NOT NULL,
  fecha TEXT NOT NULL, hora TEXT NOT NULL, hora_fin TEXT NOT NULL,
  cliente_nombre TEXT NOT NULL, cliente_telefono TEXT NOT NULL DEFAULT '',
  modalidad TEXT NOT NULL DEFAULT 'En el salón', notas TEXT NOT NULL DEFAULT '',
  origen TEXT NOT NULL DEFAULT 'plataforma',
  estado TEXT NOT NULL DEFAULT 'pendiente'
    CHECK (estado IN ('pendiente','confirmada','rechazada','completada','no_asistio','cancelada')),
  creado TEXT NOT NULL, actualizado TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_citas_dia ON citas(proveedor_id, fecha);
CREATE TABLE IF NOT EXISTS pedidos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  cliente_id INTEGER NOT NULL REFERENCES usuarios(id),
  total INTEGER NOT NULL, estado TEXT NOT NULL, creado TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS pedido_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  pedido_id INTEGER NOT NULL REFERENCES pedidos(id) ON DELETE CASCADE,
  producto_id INTEGER REFERENCES productos(id) ON DELETE SET NULL,
  nombre TEXT NOT NULL, cantidad INTEGER NOT NULL, precio INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS pagos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  cliente_id INTEGER NOT NULL REFERENCES usuarios(id),
  pedido_id INTEGER REFERENCES pedidos(id) ON DELETE SET NULL,
  valor INTEGER NOT NULL, metodo TEXT NOT NULL,
  estado TEXT NOT NULL CHECK (estado IN ('Aprobado','Pendiente','Rechazado')),
  motivo TEXT NOT NULL DEFAULT '', creado TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS quejas (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  cliente_id INTEGER NOT NULL REFERENCES usuarios(id),
  tipo TEXT NOT NULL, pedido_id INTEGER REFERENCES pedidos(id) ON DELETE SET NULL,
  asunto TEXT NOT NULL, mensaje TEXT NOT NULL,
  estado TEXT NOT NULL DEFAULT 'Pendiente' CHECK (estado IN ('Pendiente','En revisión','Resuelta')),
  respuesta TEXT NOT NULL DEFAULT '', creado TEXT NOT NULL, actualizado TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS alertas_revision (
  clave TEXT PRIMARY KEY,
  estado TEXT NOT NULL CHECK (estado IN ('abierta','en_revision','sin_hallazgos')),
  nota TEXT NOT NULL DEFAULT '', revisado_por TEXT NOT NULL, fecha TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS bitacora (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  actor TEXT NOT NULL, accion TEXT NOT NULL, detalle TEXT NOT NULL DEFAULT '',
  ip TEXT, fecha TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_bitacora ON bitacora(accion, fecha);
"""

# Productos propios de Merakié (los mismos de la tienda original). Se crean una sola vez.
PRODUCTOS_INICIALES = [
    ("Shampoo Brisa Hidratante", "Shampoo suave para uso diario · 300 ml", 32000, "🧴"),
    ("Sérum Glow de Rosas", "Sérum facial · 30 ml", 48000, "🌹"),
    ("Crema Manos Nube", "Crema humectante · 75 ml", 18000, "🫧"),
    ("Kit Esmaltes Merakié", "Set de 3 tonos de temporada", 39000, "💅"),
    ("Mascarilla Capilar Seda", "Mascarilla nutritiva · 250 g", 42000, "🪷"),
    ("Protector Solar Día", "Protector solar · 50 ml", 52000, "☀️"),
]


def crear_tablas():
    """Se ejecuta al iniciar: crea las tablas si todavía no existen."""
    con = sqlite3.connect(config.BASE_DATOS)
    con.execute("PRAGMA journal_mode = WAL")   # permite leer mientras otra persona escribe
    con.executescript(ESQUEMA)
    if con.execute("SELECT COUNT(*) FROM productos").fetchone()[0] == 0:
        con.executemany("INSERT INTO productos(nombre,descripcion,precio,stock,emoji,creado) VALUES(?,?,?,50,?,?)",
                        [(n, d, p, e, ahora()) for n, d, p, e in PRODUCTOS_INICIALES])
    con.commit()
    con.close()
