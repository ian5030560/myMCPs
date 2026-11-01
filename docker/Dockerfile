# Verifies that `pip install -c requirements.txt ".[all]"` works on Linux and that the
# test suite passes against the *installed* package (not the source tree).
ARG PYTHON_VERSION=3.12
FROM python:${PYTHON_VERSION}-slim

WORKDIR /app
COPY requirements.txt pyproject.toml README.md ./
COPY src ./src
# The pip cache lives in a BuildKit cache mount: rebuilds reuse downloads (~120 MB),
# and the cache never ends up in the image.
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -c requirements.txt ".[all]" pytest pytest-asyncio respx \
    && pip check

COPY tests ./tests
# The tests check that the shipped example config and the manual-testing docs stay valid.
COPY config.example.toml ./
COPY docs ./docs
CMD ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider"]
