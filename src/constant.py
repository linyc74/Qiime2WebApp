import os


VERSION = 'v1.0.0-beta'

ASSETS_DIR = './assets'
BASE_URL = os.environ.get('BASE_URL', 'http://localhost:8080').rstrip('/')

SESSION_TTL = 1 * 60 * 60  # 1 hour
SESSION_COOKIE = 'app_session'

POSTGRES_HOST = 'localhost'
POSTGRES_PORT = 5432
POSTGRES_USER = 'postgres'
POSTGRES_DB = 'qiime2_web_app'
POSTGRES_URL = f'postgresql+psycopg2://{POSTGRES_USER}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}'

REDIS_HOST = 'localhost'
REDIS_PORT = 6379
REDIS_QUEUE = 'qiime2_web_app'  # start the redis queue worker in another terminal: `rq worker -w rq.worker.SpawnWorker qiime2_web_app`

QIIME2_PIPELINE = 'qiime2_pipeline-2.12.0'
QIIME2_CONDA_ENV = 'qiime2-amplicon-2024.2'
USERS_DIR = './data/users'
RESOURCE_DIR = './data/resource'
