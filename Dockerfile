FROM pypy:latest

WORKDIR /src/app
COPY bricklayers.py .
ENTRYPOINT ["python", "bricklayers.py"]
