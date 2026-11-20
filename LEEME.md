# Merakié · Plataforma unificada (Cliente + Proveedor + Administrador)

Hecha con **Python (Flask)** + **SQLite** (base de datos) + **un poquito de JavaScript** (40 líneas).
Una sola página de inicio: la persona elige si es **cliente, proveedor o administrador**, y según eso
se le piden **datos distintos**. Si ya tiene cuenta, entra con su usuario y su contraseña.

> Nota: dijeron "Java"; aquí usamos **JavaScript**, que es el lenguaje que corre dentro de las páginas web
> (Java y JavaScript son lenguajes distintos). Solo lo usamos para cargar las horas libres de una cita.

---

## 1. Cómo se ve el funcionamiento (idea general)

```
 Navegador (Chrome)  ──pide página──▶  Python + Flask  ──lee/guarda──▶  SQLite (datos/merakie.db)
        ▲                                   │
        └────────── recibe HTML ◀───────────┘
```

1. La persona abre una página (por ejemplo `/cliente/tienda`).
2. **Flask** (Python) recibe la petición, revisa quién es y qué permisos tiene.
3. Python consulta la **base de datos** y arma una página HTML con la **plantilla** (`templates/`).
4. Cuando la persona envía un formulario, Python **revisa** los datos y los **guarda**.

Todo lo importante (guardar, validar, calcular) pasa en Python, en el servidor. El navegador solo muestra.

---

## 2. Instalar y ejecutar (paso a paso, Windows)

1. Instala **Python 3.10 o superior** desde https://www.python.org/downloads/ ← al instalar, marca **"Add Python to PATH"**.
2. Descomprime la carpeta `merakie_plataforma`.
3. Abre la carpeta, haz clic en la barra de direcciones del Explorador, escribe `cmd` y pulsa Enter (se abre una consola ahí).
4. Instala Flask (solo la primera vez):
   ```
   pip install -r requisitos.txt
   ```
5. Inicia la plataforma:
   ```
   python app.py
   ```
6. Abre en el navegador: **http://127.0.0.1:5000** · Para detenerla: `Ctrl + C` en la consola.

En Mac/Linux usa `python3` y `pip3`. Si el puerto 5000 está ocupado: `set PORT=5001` (Windows) o `PORT=5001 python3 app.py` (Mac/Linux).

### Primer recorrido (para probar todo en 10 minutos)
1. **Administrador:** *Soy administrador → Crear cuenta*. Nombre exacto de la lista autorizada, código `MERAKIE-ADMIN-2026` (cámbialo en `config.py`).
2. **Proveedor:** abre otra ventana de incógnito → *Soy proveedor → Crear cuenta*. Usa el NIT de ejemplo `800197268-4`.
   Entra, sube el **RUT** y la **Cámara de Comercio** (cualquier PDF/JPG/PNG), crea un **servicio**, define el **horario** y pulsa **Enviar a revisión**.
3. **Administrador:** *Proveedores → Revisar → Verificar* (con el botón verde).
4. **Cliente:** otra ventana de incógnito → *Soy cliente → Crear cuenta*. Reserva una cita en el salón y compra en la tienda (prueba también "simular rechazo").
5. **Proveedor:** en *Citas* confirma la cita. **Administrador:** mira Resumen, Pagos, Fraude, Compras y Agendamientos.

---

## 3. Mapa de archivos (qué hace cada uno)

| Archivo | Para qué sirve |
|---|---|
| `app.py` | **Arranca todo.** Une las partes, carga al usuario con sesión y define los "filtros" para mostrar pesos y fechas. |
| `config.py` | **Ajustes**: administradores autorizados, código secreto, umbral de fraude, categorías... |
| `base_datos.py` | **La base de datos**: crea las tablas y trae funciones para consultar/guardar. |
| `validaciones.py` | Revisa lo que escribe la gente (NIT, correo, teléfono, contraseña, fechas...). |
| `seguridad.py` | Protección CSRF y el "guardia" que deja entrar a cada parte solo a quien corresponde. |
| `agenda.py` | Calcula las **horas libres** y crea citas sin que dos clientes tomen el mismo cupo. |
| `fraude.py` | Las **reglas de alertas** de prevención de fraude. |
| `rutas_acceso.py` | Inicio, **registro** (distinto por rol), **ingreso**, cerrar sesión y mi cuenta. |
| `rutas_cliente.py` | Todo lo del **cliente**: salones, citas, tienda, carrito, pagos, Pass, PQR. |
| `rutas_proveedor.py` | Todo lo del **proveedor**: salón, servicios, productos, horarios, citas, documentos. |
| `rutas_admin.py` | Todo lo del **administrador**: resumen, clientes, verificar proveedores, fraude, pagos... |
| `templates/` | Las páginas HTML (con "huecos" que Python llena). Una carpeta por rol. |
| `static/estilos.css` | Colores y diseño. |
| `static/app.js` | El **único JavaScript** (confirmaciones y horas libres). |
| `pruebas.py` | 84 pruebas automáticas (opcional). |
| `datos/` | Se crea sola: la base de datos, los documentos subidos y la clave secreta. **No la compartas.** |

---

## 4. Explicación de cada parte del código

### 4.1 Flask y las "rutas"
Una **ruta** es una dirección web asociada a una función de Python:
```python
@cliente.route("/tienda")            # cuando alguien abra /cliente/tienda...
@rol_requerido("cliente")            # ...y sea un cliente con sesión...
def tienda():                        # ...se ejecuta esta función
    return render_template("cliente/tienda.html", productos=bd.todos("SELECT ..."))
```
`render_template` toma la plantilla HTML y le pasa los datos. Cada rol tiene su archivo de rutas (un **Blueprint**,
que es solo "un grupo de rutas con el mismo comienzo": `/cliente/...`, `/proveedor/...`, `/admin/...`).

### 4.2 La base de datos (SQLite)
Una tabla es como una hoja de Excel; cada fila es un registro. Las principales:
`usuarios` (todos), `clientes`, `proveedores`, `servicios`, `horarios`, `citas`, `productos`, `pedidos`, `pagos`, `quejas`, `bitacora`...
- **Un solo `usuarios`**: así *cada persona tiene su propio usuario y contraseña*, y la columna `rol` dice si es cliente, proveedor o administrador.
- `clientes` y `proveedores` guardan los **datos extra** de cada rol (por eso el registro pide datos distintos).
- Para consultar se usa SQL con `?`:
  ```python
  bd.uno("SELECT * FROM usuarios WHERE usuario = ?", (usuario,))
  ```
  Los `?` **evitan la "inyección SQL"** (que alguien escriba código dentro de un campo). Nunca se pegan textos directamente en el SQL.
- Para ver la base con ventanitas, instala **DB Browser for SQLite** y abre `datos/merakie.db` (solo lectura, mejor no editar a mano).

### 4.3 Usuario y contraseña propios (y por qué no guardamos la contraseña)
```python
generate_password_hash(clave)           # al registrarse: convierte "Hola1234" en una huella ilegible
check_password_hash(huella, clave)      # al ingresar: compara sin poder "des-hacer" la huella
```
En la base solo queda la **huella (hash)**. Si alguien robara el archivo, no vería las contraseñas.

### 4.4 Registro distinto según el rol (`registro.html` + `rutas_acceso.py`)
- **Cliente:** nombre, documento (opcional), edad (18-100), teléfono, correo, usuario, contraseña y **autorización de datos**.
- **Proveedor:** tipo de persona, **NIT** (se valida el dígito de verificación), razón social, nombre comercial, contacto, teléfono, correo, ciudad, dirección, usuario, contraseña y autorización.
- **Administrador:** solo las personas de `ADMINS_AUTORIZADOS` (Santiago Muñoz y Nicole Ramirez) **y** con el **código** de administrador.
Cada rol tiene su función (`_registrar_cliente`, `_registrar_proveedor`, `_registrar_administrador`).

### 4.5 "Si ya tienes cuenta, ingresa" y que no pida la clave todo el tiempo
En `/acceso/<rol>` hay un formulario de ingreso y un botón para crear cuenta. Al ingresar bien:
```python
session["uid"] = u["id"]      # Flask guarda en una cookie firmada quién eres
session.permanent = True      # la cookie dura 7 días (config.DIAS_SESION)
```
Así **no vuelve a pedir la contraseña** hasta que pulses *Salir* o pasen 7 días.
Si alguien con cuenta de cliente entra por el botón de administrador, se le avisa cuál es el correcto.
Tras **5 intentos fallidos** en 15 minutos, se bloquea ese usuario un rato.

### 4.6 Quién puede ver qué (roles)
`@rol_requerido("cliente")` revisa `g.usuario["rol"]`. Si un cliente intenta abrir `/admin/`, recibe "403: no tienes permiso".
Además **cada consulta filtra por el dueño**: el cliente solo ve sus citas (`WHERE cliente_id = ?`) y el proveedor solo lo suyo (`WHERE proveedor_id = ?`).

### 4.7 El portal de proveedores (adaptado del ejemplo en Node)
Hace lo mismo que el ejemplo del ZIP, ahora en Python:
registro con NIT validado → subir **RUT y Cámara de Comercio** (o cédula si es persona natural) → crear **servicios**, **productos** y **horarios** →
**Enviar a revisión** → el administrador **verifica o rechaza con motivo** → solo los salones **verificados** aparecen a los clientes y reciben citas.
El proveedor también gestiona sus **citas** (pendiente → confirmada → completada / no asistió / cancelada), y puede registrar una **cita manual** (llamada o mostrador).
Los documentos se guardan **fuera de las páginas públicas**, con nombre aleatorio, y se revisa su contenido real (no solo la extensión).

### 4.8 Las horas libres (`agenda.py`)
Se parte del horario del día (ej. 09:00-18:00) y se prueban horas cada 30 minutos. Una hora se ofrece si el servicio termina antes de cerrar
y si las citas que se cruzan son **menos que los cupos** del salón. Al guardar se usa `BEGIN IMMEDIATE`: bloquea la base un instante para que
**dos clientes no tomen el último cupo a la vez**.

### 4.9 Tienda, carrito y pagos
- El **carrito** vive en la sesión (`{"101": 2}` = 2 unidades del producto 101).
- Al pagar (simulado): se revisa el **stock**, se guarda el **pago** siempre y el **pedido** solo si no fue rechazado, y se descuenta el stock.
- Métodos: tarjeta, PSE, Nequi, contra entrega (queda *Pendiente*) y "simular rechazo".
- **Merakié Pass** da 5 % de descuento real en la tienda.

### 4.10 Prevención de fraude (`fraude.py`)
Reglas: intentos fallidos de ingreso, pagos rechazados repetidos, pago de valor alto, pago relevante en cuenta nueva, ráfaga de pagos,
ráfaga de reservas, citas a la misma hora en salones distintos, documento o teléfono repetido, y proveedores esperando verificación.
**Nunca bloquea ni acusa**: solo crea una alerta. El administrador la marca *en revisión* o *cerrada sin hallazgos* y debe escribir **qué verificó** (queda en auditoría).

### 4.11 Seguridad (lo que protege la plataforma)
| Riesgo | Cómo se evita |
|---|---|
| Ver contraseñas robando la base | Solo se guarda el hash |
| Inyección SQL | Consultas con `?` |
| XSS (código escondido en un nombre) | Jinja escapa todo automáticamente (`<script>` se ve como texto) |
| CSRF (otra página envía formularios por ti) | Código secreto en cada formulario (`seguridad.py`) |
| Subir archivos peligrosos | Solo PDF/JPG/PNG reales, máx. 5 MB, nombre aleatorio |
| Adivinar contraseñas o el código admin | Bloqueo tras 5 intentos |
| Un usuario viendo datos de otro | `@rol_requerido` + filtros por dueño |
| Excel con fórmulas maliciosas | Al exportar CSV se neutralizan `=`, `+`, `-`, `@` |
| "¿Quién vio mis datos?" | `bitacora` (ver pantalla *Auditoría*) |

### 4.12 El JavaScript mínimo (`static/app.js`)
Solo hace dos cosas: **(1)** pedir confirmación ("¿Cancelar esta cita?") y **(2)** cuando eliges servicio y fecha, preguntarle a Python
qué horas están libres (`fetch`) y llenar la lista. Todo lo demás es Python.

---

## 5. Cosas que seguro van a querer cambiar
| Quiero... | Dónde |
|---|---|
| Cambiar el **código de administrador** | `config.py` → `CODIGO_ADMIN` (o la variable de entorno `MERAKIE_CODIGO_ADMIN`) |
| Cambiar los **nombres autorizados** como administradores | `config.py` → `ADMINS_AUTORIZADOS` |
| Cambiar el valor desde el cual un pago genera alerta | `config.py` → `UMBRAL_PAGO_ALTO` |
| Cambiar los días que dura la sesión | `config.py` → `DIAS_SESION` |
| Cambiar colores | `static/estilos.css` (arriba, `:root`) |
| Empezar de cero | Detén la app y borra la carpeta `datos/` |

---

## 6. Pruebas automáticas
```
python pruebas.py
```
Usa una base temporal (no toca tus datos). Simula registros, ingresos, citas, compras y alertas, y revisa las protecciones.

---

## 7. Normatividad colombiana relacionada (con ejemplos en la plataforma)
> Es una guía académica, no asesoría jurídica. Verifica la vigencia en la SIC (sic.gov.co), la DIAN y el Diario Oficial.

| Norma | Qué exige | Ejemplo en Merakié |
|---|---|---|
| **Ley 1581 de 2012** y **Decreto 1074 de 2015** (compila el Decreto 1377 de 2013) | Autorización previa, finalidad, acceso restringido, seguridad | Casilla de autorización con fecha y versión; documento enmascarado (`•••678`); ver el completo deja huella en *Auditoría* |
| **Decreto 090 de 2018** (RNBD) | Inscribir bases de datos en el Registro Nacional si los activos superan 100.000 UVT | Si Merakié crece, hay que inscribir la base de clientes |
| **Ley 1480 de 2011** (Estatuto del Consumidor) modificada por la **Ley 2439 de 2024** | Información clara, retracto, reversión del pago, devolución del dinero en comercio electrónico máx. 15 días calendario | Módulo PQR con estados y respuesta; en producción mostrar plazo de entrega y gestionar retractos |
| **Ley 1755 de 2015** | Derecho de petición | Las "Peticiones" del módulo de Ayuda deben responderse dentro de los términos legales |
| **Ley 527 de 1999** | Validez de los mensajes de datos y el comercio electrónico | Las reservas y compras quedan registradas con fecha y hora |
| **Ley 1273 de 2009** | Delitos informáticos (ej. acceso abusivo a un sistema) | Control de acceso por roles, bloqueo por intentos y bitácora |
| **Estatuto Tributario art. 615** y **Resolución DIAN 000165 de 2023** | Facturación (electrónica) de las ventas | Los pagos aquí son simulados; en producción cada venta debe facturarse electrónicamente |
| **Constitución art. 29** | Presunción de inocencia | Las alertas de fraude son *indicios*, nunca acusaciones automáticas |

**Proyecto de reforma a la Ley 1581:** en agosto de 2026 se radicó de nuevo en la Cámara de Representantes un proyecto de ley estatutaria que la modifica. **Todavía es un proyecto, no es ley**; hoy rige la Ley 1581 de 2012.

---

## 8. Límites actuales y siguientes pasos
- Es un **prototipo**: corre en un computador. Para publicarla se necesita un servidor con **HTTPS**, `debug=False` (ya está así) y servidor de producción (ej. `gunicorn`/`waitress`).
- **No envía correos** (confirmar correo, recuperar contraseña). Es el siguiente paso natural.
- **Los pagos son simulados**: no hay pasarela real ni factura electrónica.
- SQLite sirve para empezar; si crece mucho, se migra a PostgreSQL.
- Haz **copia de seguridad** de la carpeta `datos/` periódicamente.
- Los 6 productos iniciales son de Merakié (se crean una vez); los de cada proveedor los administra él mismo.
