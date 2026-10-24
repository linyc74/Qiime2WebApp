import os
import csv
import subprocess
from nicegui import ui
from os.path import join
from datetime import datetime
from .worker import Worker
from .io import read_parameters, write_parameters


ILLUMINA_KEY_TO_OPTIONS = {
    'fq1-suffix': ['_R1.fastq.gz'],
    'fq2-suffix': ['_R2.fastq.gz'],
    'output': ['output'],
    'feature-classifier': ['nb', 'vsearch'],
    'nb-classifier-qza': ['silva-138-99-nb-classifier.qza'],
    'reference-sequence-qza': ['silva-138-99-seqs.qza'],
    'reference-taxonomy-qza': ['silva-138-99-tax.qza'],
    'vsearch-classifier-max-hits': ['10'],
    'threads': ['1', '4', '8'],
    'paired-end-mode': ['merge', 'pool'],
    'skip-otu': False,
    'otu-identity': ['0.97'],
    'dna-concentration-column': ['None'],
    'decontam-threshold': ['0.1'],
    'clip-r1-5-prime': ['17'],
    'clip-r2-5-prime': ['20'],
    'classifier-reads-per-batch': ['1000'],
    'max-expected-error-bases': ['8.0'],
    'alpha-metrics': ['all'],
    'beta-diversity-feature-level': [
        'feature',
        'species',
        'genus',
        'family',
        'order',
        'class',
        'phylum',
    ],
    'heatmap-read-fraction': ['0.95'],
    'n-taxa-barplot': ['20'],
    'colormap': [
        'Set1',
        'Set2',
        'Set3',
        'tab10',
        'tab20',
        'tab20b',
        'tab20c',
        'Pastel1',
        'Pastel2',
        'Paired',
        'Accent',
        'Dark2',
    ],
    'invert-colors': False,
    'publication-figure': False,
    'skip-differential-abundance': False,
    'differential-abundance-p-value': ['0.05'],
    'min-abundance-per-group': ['0.0']
}
PACBIO_KEY_TO_OPTIONS = {
    'fq1-suffix': ['.fastq.gz'],
    'output': ['output'],
    'feature-classifier': ['nb', 'vsearch'],
    'nb-classifier-qza': ['silva-138-99-nb-classifier.qza'],
    'reference-sequence-qza': ['silva-138-99-seqs.qza'],
    'reference-taxonomy-qza': ['silva-138-99-tax.qza'],
    'vsearch-classifier-max-hits': ['10'],
    'threads': ['1', '4', '8'],
    'skip-otu': False,
    'otu-identity': ['0.97'],
    'dna-concentration-column': ['None'],
    'decontam-threshold': ['0.1'],
    'classifier-reads-per-batch': ['1000'],
    'max-expected-error-bases': ['8.0'],
    'alpha-metrics': ['all'],
    'beta-diversity-feature-level': [
        'feature',
        'species',
        'genus',
        'family',
        'order',
        'class',
        'phylum',
    ],
    'heatmap-read-fraction': ['0.95'],
    'n-taxa-barplot': ['20'],
    'colormap': [
        'Set1',
        'Set2',
        'Set3',
        'tab10',
        'tab20',
        'tab20b',
        'tab20c',
        'Pastel1',
        'Pastel2',
        'Paired',
        'Accent',
        'Dark2',
    ],
    'invert-colors': False,
    'publication-figure': False,
    'skip-differential-abundance': False,
    'differential-abundance-p-value': ['0.05'],
    'min-abundance-per-group': ['0.0']
}
MODES = {
    'illumina': ILLUMINA_KEY_TO_OPTIONS,
    'pacbio': PACBIO_KEY_TO_OPTIONS
}
USERNAME = 'username'
USER_ID = 1
QIIME2_PIPELINE = 'qiime2_pipeline-2.12.0'
FASTQ_DIR = './data/fastq'
RESOURCE_DIR = './data/resources'
JOB_DIR = './data/jobs'


class PipelinePage:

    def __init__(self):
        self.mode = 'illumina'
        self.values = {}  # ground truth values
        self.controls = {}  # UI controls
        self.sample_sheet_name = ''
        self.sample_sheet_content = ''
        self.worker = Worker(user_id=USER_ID)

        self.initialize_values()
        
        ui.colors(primary='#12329A', secondary='#25636b')
        
        with ui.column().classes('w-full max-w-4xl mx-auto p-4 sm:p-8 gap-6'):

            with ui.row().classes('w-full items-center justify-between'):
                ui.label('Qiime2 App').classes('text-3xl font-semibold')
                ui.button('Dashboard', icon='table_chart', on_click=self.show_dashboard).props('outline')
            
            ui.toggle(
                {'illumina': 'Illumina Mode', 'pacbio': 'PacBio Mode'},
                value=self.mode,
                on_change=self.change_mode
            )
            
            self.form = ui.column().classes('w-full gap-4')
            self.render_form()

            with ui.row().classes('w-full gap-3 justify-end'):
                ui.button('Load Parameters', icon='upload_file', on_click=self.load_dialog)
                ui.button('Save Parameters', icon='download', on_click=self.save_dialog)
                ui.button('Submit', icon='send', on_click=self.submit)

    def initialize_values(self):
        self.values = {}
        for key, options in MODES[self.mode].items():
            if isinstance(options, list):
                self.values[key] = options[0]
            else:
                self.values[key] = options

    def change_mode(self, event):
        self.mode = event.value
        self.render_form()

    def render_form(self):
        self.form.clear()
        self.controls = {}  # refresh UI controls

        with self.form:

            ui.button('Upload Sample Sheet', icon='upload_file', on_click=self.sample_sheet_dialog)
            if self.sample_sheet_name:  # show sample sheet name if uploaded
                ui.label(self.sample_sheet_name).classes('text-sm text-slate-500')
            
            for key, options in MODES[self.mode].items():  # follow items and data types in the presets
                if isinstance(options, bool):
                    control = ui.checkbox(key).bind_value(self.values, key)  # use self.values to fill in
                else:
                    choices = list(options)  # create a new list
                    if self.values[key] not in choices:
                        choices.append(self.values[key])  # append to the new list if not present
                    control = ui.select(choices, label=key, new_value_mode='add-unique')
                    control.bind_value(self.values, key).props('outlined').classes('w-full')
                
                self.controls[key] = control

    def sample_sheet_dialog(self):
        with self.form.client, ui.dialog() as dialog, ui.card().classes('w-full max-w-lg'):
            ui.label('Upload Sample Sheet').classes('text-xl font-semibold')

            async def upload(event):
                if event.file.size() > 10_000_000:
                    ui.notify('Choose a sample sheet smaller than 10 MB.', type='negative')
                    return

                content = await event.file.text()
                if not content:
                    ui.notify('Choose a non-empty sample sheet.', type='negative')
                    return

                self.sample_sheet_name = event.file.name
                self.sample_sheet_content = content

                self.render_form()  # refresh UI controls

                dialog.close()
                ui.notify('Sample sheet uploaded.', type='positive')

            ui.upload(
                label='Choose sample sheet',
                auto_upload=True,
                on_upload=upload,  # async function defined above
                max_file_size=10_000_000,
                on_rejected=lambda: ui.notify('Choose a sample sheet smaller than 10 MB.', type='negative')
            ).classes('w-full')
            
            ui.button('Close', on_click=dialog.close).props('flat')
        
        dialog.open()

    def load_dialog(self):
        with self.form.client, ui.dialog() as dialog, ui.card().classes('w-full max-w-lg'):
            ui.label('Load Parameters').classes('text-xl font-semibold')

            async def load(event):
                try:
                    if event.file.size() > 1_000_000:
                        raise ValueError('Choose a parameter file smaller than 1 MB.')
                    parameters = read_parameters(event.file.name, await event.file.text())
                    updates = {}
                    for key, default in MODES[self.mode].items():
                        if isinstance(default, bool):
                            value = parameters.get(key, False)
                            if isinstance(value, str):
                                if value.lower() not in ('true', 'false'):
                                    raise ValueError(f'{key} must be a flag, true, or false.')
                                value = value.lower() == 'true'
                            updates[key] = value
                        elif key in parameters:
                            if not isinstance(parameters[key], str):
                                raise ValueError(f'{key} requires a value.')
                            updates[key] = parameters[key]
                    self.values.update(updates)

                    self.render_form()  # refresh UI controls
                    
                    dialog.close()
                    ui.notify('Parameters loaded.', type='positive')
                
                except (ValueError, UnicodeError, csv.Error) as error:
                    ui.notify(str(error), type='negative')

            ui.upload(
                label='Choose parameter file',
                auto_upload=True,
                on_upload=load,  # async function defined above
                max_file_size=1_000_000,
                on_rejected=lambda: ui.notify('Choose a parameter file smaller than 1 MB.', type='negative')
            ).props(
                'accept=".csv,.tsv,.tab,.txt"'
            ).classes(
                'w-full'
            )
            
            ui.button('Close', on_click=dialog.close).props('flat')
        
        dialog.open()

    def save_dialog(self):
        with self.form.client, ui.dialog() as dialog, ui.card().classes('w-full max-w-lg'):
            ui.label('Save Parameters').classes('text-xl font-semibold')
            file_format = ui.select(['.csv', '.tsv', '.tab', '.txt'], value='.csv', label='Format')

            def download():
                suffix = file_format.value
                ui.download(write_parameters(self.values, suffix), f'{self.mode}-parameters{suffix}')
                dialog.close()

            with ui.row():
                ui.button('Download', on_click=download)
                ui.button('Cancel', on_click=dialog.close).props('flat')

        dialog.open()

    def show_dashboard(self):
        with self.form.client, ui.dialog() as dialog, ui.card().classes('w-full max-w-3xl'):
            ui.label('Dashboard').classes('text-xl font-semibold')

            ui.table(columns=[
                {'name': 'id',      'label': 'Job ID',       'field': 'id',      'align': 'left'},
                {'name': 'start',   'label': 'Start Time',   'field': 'start',   'align': 'left'},
                {'name': 'elapsed', 'label': 'Elapsed Time', 'field': 'elapsed', 'align': 'left'},
            ], rows=[], row_key='id', selection='multiple').classes('w-full')

            with ui.row().classes('w-full justify-end'):
                ui.button('Update', icon='refresh').disable()
                ui.button('Kill Jobs', icon='stop', color='negative').disable()
                ui.button('Download', icon='download').disable()
                ui.button('Close', on_click=dialog.close).props('flat')

        dialog.open()

    def submit(self):
        if self.sample_sheet_name == '':
            ui.notify('Please upload a sample sheet.', type='negative')
            return
        
        job_timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S.%f')[:-3]  # down to milliseconds

        outdir = join(JOB_DIR, USERNAME, job_timestamp, self.values['output'])
        os.makedirs(outdir, exist_ok=True)

        with open(join(outdir, self.sample_sheet_name), 'w') as f:
            f.write(self.sample_sheet_content)

        cmd = self.build_cmd(outdir=outdir)

        self.worker.submit_job(job_timestamp=job_timestamp, cmd=cmd)

        ui.notify(f'Submitted job [{job_timestamp}].', type='positive')

    def build_cmd(self, outdir: str) -> str:
        lines = [
            f'python {QIIME2_PIPELINE}',
            f'--fq-dir="{join(FASTQ_DIR, USERNAME)}"',
            f'--sample-sheet="{join(outdir, self.sample_sheet_name)}"',
        ]

        for key, value in self.values.items():

            if isinstance(value, bool):
                lines.append(f'--{key}')

            elif key in ['output']:
                lines.append(f'--{key}="{outdir}"')                
            
            elif key in ['nb-classifier-qza', 'reference-sequence-qza', 'reference-taxonomy-qza']:
                lines.append(f'--{key}="{join(RESOURCE_DIR, value)}"')

            else:
                lines.append(f'--{key}="{value}"')
                
        lines.append(f'> "{join(outdir, "progress.txt")}" 2>&1')

        cmd = ' \\\n  '.join(lines)
        return cmd
