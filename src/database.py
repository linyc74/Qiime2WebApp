from sqlalchemy import create_engine, text, Engine, Result
from .constant import POSTGRES_URL


class Database:

    engine: Engine

    def __init__(self):
        self.engine = create_engine(POSTGRES_URL)

    def execute(self, query: str, params: dict) -> Result:
        with self.engine.connect() as conn:
            ret = conn.execute(text(query), params)
            conn.commit()
        return ret
