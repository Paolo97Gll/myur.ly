# syntax=docker/dockerfile:1

FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# install the package and its dependencies
COPY pyproject.toml ./
COPY myurly ./myurly
RUN pip install --no-cache-dir .

# run as unprivileged user
RUN useradd --system --no-create-home myurly
USER myurly

# define the entrypoint for the container
ENTRYPOINT ["myurly"]
