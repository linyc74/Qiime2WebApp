from sqlalchemy import create_engine, text, Engine, Result


POSTGRES_HOST = 'localhost'
POSTGRES_PORT = 5432
POSTGRES_USER = 'postgres'
POSTGRES_DB = 'qiime2_web_app'
POSTGRES_URL = f'postgresql+psycopg2://{POSTGRES_USER}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}'


class Database:

    engine: Engine

    def __init__(self):
        self.engine = create_engine(POSTGRES_URL)

    def execute(self, query: str, params: dict) -> Result:
        with self.engine.connect() as conn:
            ret = conn.execute(text(query), params)
            conn.commit()
        return ret
