from .job import JobInput
from .database import Database
from .constant import USERS_DIR
from .utils import to_valid_filename, get_dirs, read_parameters


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


class UserInput:
    """
    Current state (data model) for the user input, dynamically updated by the UI.
    """

    def __init__(self, user_id: int):
        self.user_id = user_id
        self.mode = 'illumina'
        self.db = Database()
        self.set_email()
        self.user_dirname = f'{self.user_id}_{to_valid_filename(self.email)}'  # user-specific directory name to store data
        self.sample_sheet_name = ''
        self.sample_sheet_content = ''
        self.reset_values()

    def set_email(self):
        ret = self.db.execute(
            '''
                SELECT email FROM users WHERE id = :user_id
            ''',
            {'user_id': self.user_id}
        )
        self.email = ret.scalar_one()

    def reset_values(self):
        self.values = {}
        for key, options in MODES[self.mode].items():
            if isinstance(options, list):
                self.values[key] = options[0]
            else:
                self.values[key] = options

    def get_output_dirname(self, job_timestamp: str) -> str:
        dirs = get_dirs(
            source=f'{USERS_DIR}/{self.user_dirname}/jobs/{job_timestamp}',
            isfullpath=False)

        if len(dirs) == 0:
            return '(not found)'

        return dirs[0]

    def load_parameters(self, name: str, text: str):
        parameters = read_parameters(name, text)
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

    def create_job(self) -> JobInput:
        return JobInput(
            user_id=self.user_id,
            user_dirname=self.user_dirname,
            sample_sheet_name=self.sample_sheet_name,
            sample_sheet_content=self.sample_sheet_content,
            sequencing_platform=self.mode,
            parameters=self.values)
