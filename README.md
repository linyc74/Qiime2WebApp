# Qiime2WebApp

Web interface to execute `qiime2_pipeline`.

## Setup

```bash
pip install -r requirements.txt
```

Set the Google OAuth environment variables in `~/.bashrc`:

```bash
export GOOGLE_CLIENT_ID="your-google-client-id"
export GOOGLE_CLIENT_SECRET="your-google-client-secret"
export BASE_URL="https://example.com"  # optional, defaults to "http://localhost:8080"
```

From the project directory `Qiime2WebApp`, make data directories and set up `qiime2_pipeline` version `2.12.1`:

```bash
cd Qiime2WebApp
mkdir -p ./data/users ./data/resource
wget https://github.com/linyc74/qiime2_pipeline/archive/refs/tags/2.12.1.tar.gz
tar xzf 2.12.1.tar.gz
rm 2.12.1.tar.gz
```

Configure Caddyfile:

```bash
sudo vim /etc/caddy/Caddyfile
```

```text
example.com {
	reverse_proxy 127.0.0.1:8080
}
```

## Run

Two services must be running:

- PostgreSQL (`localhost:5432`, user `postgres`, database `qiime2_web_app`). See [`schema.md`](schema.md) for more details.
- Redis (`localhost:6379`)

From the project directory `Qiime2WebApp`, in two separate terminals, start the Redis Queue worker and the app:

Terminal 1, start a Redix Queue worker named `qiime2_web_app`:

```bash
rq worker -w rq.worker.SpawnWorker qiime2_web_app
```

Terminal 2, start the app:

```bash
python main.py
```