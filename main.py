from nicegui import ui
from src.view import PipelinePage


@ui.page('/')
def root():
    PipelinePage()


ui.run(title='Qiime2 App')
