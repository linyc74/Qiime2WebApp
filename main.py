import os
import uvicorn
from src.app import app, HOST, PORT


if __name__ == '__main__':
    uvicorn.run(app, host=HOST, port=PORT)
