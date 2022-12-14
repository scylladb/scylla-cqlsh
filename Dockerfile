FROM python:3.11-slim-bullseye AS compile-image

WORKDIR /usr/src/app
RUN apt-get update && apt-get -y install git gcc

COPY . .
RUN pip install --user .


FROM python:3.11-slim-bullseye AS build-image
COPY --from=compile-image /root/.local /root/.local

# Make sure scripts in .local are usable:
ENV PATH=/root/.local/bin:$PATH
ENTRYPOINT [ "cqlsh" ]
