# seertall-api

## Utvikle lokalt

### Oppsett

```sh
poetry install
```

### Start server

```sh
uvicorn seertall_api.main:app
```

### Populere database

I en annen shell-tab:

```sh
curl --include http://localhost:8000/ingest --form file=@./datasets/Datasett_seertall_NRK_2018.csv
```
