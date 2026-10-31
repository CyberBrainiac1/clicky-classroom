"""Clicky-owned model cache. Never queries or writes a live OpenWhispr service."""
import os
from pathlib import Path, PurePosixPath
import shutil
import tarfile
import tempfile
import urllib.request
from .settings import data_root

PARAKEET_MODEL = 'parakeet-tdt-0.6b-v3'
PARAKEET_FILES = ('encoder.int8.onnx','decoder.int8.onnx','joiner.int8.onnx','tokens.txt')
PARAKEET_URL = 'https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8.tar.bz2'


def default_parakeet_directory():
    explicit=os.getenv('CLICKY_PARAKEET_MODEL')
    return str(Path(explicit) if explicit else data_root()/'models'/PARAKEET_MODEL)


def model_ready(directory=None):
    path=Path(directory or default_parakeet_directory())
    return all((path/name).is_file() and (path/name).stat().st_size > 0 for name in PARAKEET_FILES)


def prepare_parakeet_download():
    """Explicit user action only. Download official weights to Clicky's own cache."""
    destination=Path(default_parakeet_directory())
    if model_ready(destination):
        return str(destination)
    if destination.exists():
        raise ValueError('The Parakeet cache is incomplete. Select a complete model folder or a new empty destination.')
    destination.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='parakeet-download-',dir=destination.parent) as temporary:
        temporary=Path(temporary)
        archive=temporary/'model.tar.bz2'
        request=urllib.request.Request(PARAKEET_URL,headers={'User-Agent':'ClickyClassroom'})
        with urllib.request.urlopen(request,timeout=120) as response, archive.open('wb') as output:
            if not response.url.startswith('https://'):
                raise ValueError('Model download requires HTTPS')
            size=0
            while block:=response.read(1024*1024):
                size+=len(block)
                if size > 1_000_000_000:
                    raise ValueError('Parakeet archive exceeds the download size limit')
                output.write(block)
        stage=temporary/'model'
        stage.mkdir()
        with tarfile.open(archive,'r:bz2') as bundle:
            selected={}
            for entry in bundle:
                path=PurePosixPath(entry.name)
                if path.name not in PARAKEET_FILES:
                    continue
                if not entry.isfile() or path.is_absolute() or '..' in path.parts or path.name in selected:
                    raise ValueError('Unexpected model archive member')
                if entry.size > 900_000_000:
                    raise ValueError('Model file exceeds the size limit')
                selected[path.name]=entry
            if set(selected)!=set(PARAKEET_FILES):
                raise ValueError('Official archive is missing required Parakeet files')
            for name,entry in selected.items():
                with bundle.extractfile(entry) as source, (stage/name).open('wb') as output:
                    shutil.copyfileobj(source,output)
        if not model_ready(stage):
            raise ValueError('Downloaded Parakeet files are incomplete')
        if destination.exists():
            raise FileExistsError('A model appeared at the destination; it was not overwritten')
        stage.rename(destination)
    return str(destination)
