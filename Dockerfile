FROM python:3.11-slim AS build
WORKDIR /src
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN python -m pip install --no-cache-dir build && python -m build --wheel

FROM python:3.11-slim
RUN useradd --create-home --uid 10001 app
COPY --from=build /src/dist/*.whl /tmp/package.whl
RUN python -m pip install --no-cache-dir /tmp/package.whl && rm /tmp/package.whl
USER app
WORKDIR /home/app
ENTRYPOINT ["mcp-breakbench"]
CMD ["--help"]

