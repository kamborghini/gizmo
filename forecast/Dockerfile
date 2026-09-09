# The nightly forecasting service. Build it from the repository root with the
# Dockerfile path set to forecast/Dockerfile (Railway: service settings, or
# RAILWAY_DOCKERFILE_PATH=forecast/Dockerfile) and a cron schedule such as
# "0 3 * * *". It is separate from the app's own Dockerfile on purpose: the
# app never carries these libraries.
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
# The per-variant model's libraries (scikit-learn, LightGBM, CatBoost) are NOT
# installed: they were two thirds of this image and serve a model that is off
# by default. To turn it back on, copy requirements-m5.txt too and add it to
# the pip install below.
COPY forecast/requirements-service.txt /app/forecast/requirements-service.txt
RUN pip install --no-cache-dir -r /app/forecast/requirements-service.txt
COPY forecast /app/forecast
CMD ["python", "-m", "forecast", "nightly"]
