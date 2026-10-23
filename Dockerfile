FROM python:3.12-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --default-toolchain 1.85.0 \
    && rm -rf /var/lib/apt/lists/*
ENV PATH="/root/.cargo/bin:${PATH}"

WORKDIR /build
COPY pyproject.toml Cargo.toml Cargo.lock README.md LICENSE ./
COPY src ./src
COPY phone_standardizer ./phone_standardizer
COPY address_standardizer ./address_standardizer
COPY entity_standardizer ./entity_standardizer

RUN pip install --no-cache-dir maturin wheel setuptools && \
    maturin build --release --locked --out /dist/native && \
    pip wheel --no-cache-dir --no-deps --wheel-dir /dist/py .

FROM python:3.12-slim

WORKDIR /app
COPY --from=builder /dist/native/*.whl /tmp/native/
COPY --from=builder /dist/py/*.whl /tmp/py/

RUN pip install --no-cache-dir "$(ls /tmp/py/entity_standardizer-*.whl | head -n 1)[server,mcp]" && \
    python -m zipfile -e "$(ls /tmp/native/*.whl | head -n 1)" /tmp/native_x && \
    cp -r /tmp/native_x/_phone_standardizer_rs "$(python -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')/" && \
    rm -rf /tmp/native /tmp/native_x /tmp/py && \
    useradd -m appuser && \
    chown -R appuser:appuser /app

USER appuser
EXPOSE 8000

CMD ["uvicorn", "phone_standardizer.server:app", "--host", "0.0.0.0", "--port", "8000"]


