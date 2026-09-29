FROM kestra/kestra:v1.0.0
USER root
# Kestra 1.0.0 includes uv 0.6.17. Managed Python is compatible with its Ubuntu base.
ENV UV_PYTHON_INSTALL_DIR=/opt/python
RUN uv python install 3.12.9 && uv venv --python 3.12.9 /opt/taxi-venv
COPY requirements.lock.txt /tmp/taxi-requirements.txt
RUN uv pip install --python /opt/taxi-venv/bin/python --no-cache -r /tmp/taxi-requirements.txt
ENV PATH="/opt/taxi-venv/bin:${PATH}" \
    PYTHONPATH="/opt/nyc-taxi" \
    PYTHONUNBUFFERED=1 \
    DBT_SEND_ANONYMOUS_USAGE_STATS=false
COPY ingestion /opt/nyc-taxi/ingestion
COPY dbt_project /opt/nyc-taxi/dbt_project
COPY infrastructure/bootstrap.sql /opt/nyc-taxi/infrastructure/bootstrap.sql
COPY kestra /opt/nyc-taxi/kestra
# Process runner runs in this container; no host Docker socket is mounted.
RUN mkdir -p /opt/nyc-taxi/data /opt/nyc-taxi/reports /opt/nyc-taxi/secrets
