# Dockerfile  ·  RECETA PARA CONSTRUIR EL BACKEND
FROM python:3.12-slim

# No crear archivos .pyc y mostrar los mensajes al instante
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

WORKDIR /app

# Primero las dependencias (Docker las guarda en cache si no cambian)
COPY requisitos.txt .
RUN pip install --no-cache-dir -r requisitos.txt gunicorn

# Luego el codigo. La carpeta datos/ NO se copia: la base vive en el volumen.
COPY . .

# Usuario sin privilegios: si alguien vulnera la app, no es "root"
RUN useradd --create-home merakie && mkdir -p /datos && chown merakie /datos
USER merakie

EXPOSE 5000
# SQLite escribe de a uno: 1 proceso con 4 hilos es suficiente y seguro
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "4", "app:app"]
