# Qiime2WebApp

Web interface to execute `qiime2_pipeline`.

## Run

```bash
pip install -r requirements.txt
```

Two services must be running:

- PostgreSQL (`localhost:5432`, user `postgres`, database `qiime2_web_app`)
- Redis (`localhost:6379`)

Set the Google OAuth environment variables in `~/.bashrc`:

```bash
export GOOGLE_CLIENT_ID="your-google-client-id"
export GOOGLE_CLIENT_SECRET="your-google-client-secret"
export BASE_URL="https://example.com"
```

From the project directory `Qiime2WebApp`, in two separate terminals, start the Redis Queue worker and the app:

Terminal 1, start a Redix Queue worker named `qiime2_web_app`:

```bash
rq worker -w rq.worker.SpawnWorker qiime2_web_app
```

Terminal 2, start the app:

```bash
python main.py
```