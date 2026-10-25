# Qiime2WebApp

Web interface to execute `qiime2_pipeline`.

## Run

```bash
pip install -r requirements.txt
```

Two services must be running:

- PostgreSQL (`localhost:5432`, user `postgres`, database `qiime2_web_app`)
- Redis (`localhost:6379`)

From the project directory `Qiime2WebApp`, in two separate terminals, start the Redis Queue worker and the app:

Terminal 1, start a Redix Queue worker named `qiime2`:
```bash
rq worker -w rq.worker.SpawnWorker qiime2
```

Terminal 2, start the app:
```bash
python main.py
```

Open http://localhost:8080.
