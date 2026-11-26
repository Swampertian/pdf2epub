# CPU-only image: torch comes from the PyTorch CPU index, so none of the
# ~3 GB of NVIDIA CUDA libraries are installed. For GPU acceleration run
# natively with `uv sync --extra cu132`. Build from the repository root:
#   docker build -f docker/Dockerfile -t pdf2epub .
FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.13 /uv /usr/local/bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv

# Dependencies first so this layer is cached across source changes.
COPY pyproject.toml uv.lock .python-version ./
# The uv cache lives in a BuildKit cache mount, not in the image layers.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-default-groups --extra cpu --no-install-project

COPY README.md ./
COPY src/ src/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-default-groups --extra cpu

ENV PATH=/opt/venv/bin:$PATH

# marker-pdf (surya) downloads its models on first run into MODEL_CACHE_DIR;
# mount a volume at this path to cache them across container runs.
ENV MODEL_CACHE_DIR=/models
VOLUME /models

# PDFs are read from /data/input and results written next to them by default.
WORKDIR /data

ENTRYPOINT ["pdf2epub"]
