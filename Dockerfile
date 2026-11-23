# Acomoda en un servidor (Railway u otro que acepte Docker)
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    ACOMODA_DATOS=/data \
    MPLBACKEND=Agg

# libgomp1: lo necesita el solver CBC que trae PuLP; libgl/libglib: lectura de imágenes y PDF
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 libglib2.0-0 libgl1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
RUN mkdir -p /data && chmod +x "$(python -c 'import pulp,os;print(os.path.join(os.path.dirname(pulp.__file__),"solverdir","cbc","linux","i64","cbc"))')" || true

# Railway asigna el puerto en la variable PORT
CMD streamlit run app.py --server.port=${PORT:-8501} --server.address=0.0.0.0 --server.headless=true
