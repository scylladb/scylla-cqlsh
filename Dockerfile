FROM python:3.13-slim-bullseye AS compile-image

WORKDIR /usr/src/app
RUN DEBIAN_FRONTEND=noninteractive apt-get update && apt-get -y install --no-install-recommends git gcc libc6-dev

COPY . .
# Configure pip to retry on network failures (helps with timeout issues)
ENV PIP_RETRIES=10
# Upgrade build tools to address CVEs in pip, setuptools, and wheel
RUN pip install --no-cache-dir --upgrade pip==26.1 setuptools==82.0.1 wheel==0.47.0
RUN pip install --user .


FROM python:3.13-slim-bullseye AS build-image

# Upgrade packages to the latest, pip as well.
RUN DEBIAN_FRONTEND=noninteractive apt-get update && apt-get -y upgrade && apt-get clean && rm -rf /var/lib/apt/lists/*
# Configure pip to retry on network failures (helps with timeout issues)
ENV PIP_RETRIES=10
RUN pip install --upgrade --no-cache-dir pip==26.1 setuptools==82.0.1 wheel==0.47.0 requests==2.33.1

COPY --from=compile-image /root/.local /root/.local

# Make sure scripts in .local are usable:
ENV PATH=/root/.local/bin:$PATH
ENTRYPOINT [ "cqlsh" ]
