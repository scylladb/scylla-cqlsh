FROM python:3.11-slim-bullseye AS compile-image

WORKDIR /usr/src/app
RUN DEBIAN_FRONTEND=noninteractive apt-get update && apt-get -y install --no-install-recommends git gcc libc6-dev

COPY . .
RUN pip install --user .


FROM python:3.11-slim-bullseye AS build-image

# Upgrade packages to the latest, pip as well.
RUN DEBIAN_FRONTEND=noninteractive apt-get update && apt-get -y upgrade && apt-get clean && rm -rf /var/lib/apt/lists/*
RUN pip install --upgrade --no-cache-dir pip

COPY --from=compile-image /root/.local /root/.local

# Make sure scripts in .local are usable:
ENV PATH=/root/.local/bin:$PATH
ENTRYPOINT [ "cqlsh" ]
