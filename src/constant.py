import os
from .version import get_app_version


VERSION = get_app_version()

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

QIIME2_PIPELINE_VERSION = '2.12.1'
QIIME2_PIPELINE = f'qiime2_pipeline-{QIIME2_PIPELINE_VERSION}'
QIIME2_VERSION = '2024.2'
QIIME2_CONDA_ENV = f'qiime2-amplicon-{QIIME2_VERSION}'
PIPELINE_LABEL = f'{QIIME2_PIPELINE} · {QIIME2_CONDA_ENV}'
USERS_DIR = './data/users'
RESOURCE_DIR = './data/resource'
