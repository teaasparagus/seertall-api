from http import HTTPStatus

import structlog
from fastapi import FastAPI, UploadFile

app = FastAPI()

logger = structlog.get_logger(__name__)


@app.get("/")
def root():
    return {"message": "Hello World"}


@app.post("/ingest", status_code=HTTPStatus.ACCEPTED)
def ingest(file: UploadFile):
    logger.debug(f"Received {file.filename}")
    return {"message": "ingest scheduled"}
