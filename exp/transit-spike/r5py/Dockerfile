# Throwaway image for the T1 spike: r5py (pinned) on a JDK 21 runtime. Not part of the project.
FROM eclipse-temurin:21-jre-noble
COPY --from=ghcr.io/astral-sh/uv:0.13.0 /uv /usr/local/bin/uv
ENV UV_PYTHON_INSTALL_DIR=/opt/python UV_LINK_MODE=copy
RUN uv venv --python 3.12 /opt/venv \
 && VIRTUAL_ENV=/opt/venv uv pip install "r5py==1.1.7" "pyarrow>=17"
ENV PATH=/opt/venv/bin:$PATH
# Fetch the R5 jar at build time so runs need no network.
RUN python -c "import r5py; print(r5py.__version__)"
WORKDIR /work
