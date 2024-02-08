# python:3.12-slim-bookworm
FROM python@sha256:eb53cb99a609b86da6e239b16e1f2aed5e10cfbc538671fc4631093a00f133f2

WORKDIR /opt/app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

EXPOSE 8000
CMD exec uvicorn seertall_api.main:app --host 0.0.0.0 --port 8000
