# Build only the native Classroom app, with offline speech dependencies.
from PyInstaller.utils.hooks import collect_all

datas, binaries, hidden = [], [], []
for package in ('PyQt6', 'faster_whisper', 'ctranslate2', 'tokenizers', 'sherpa_onnx',
                'pyaudiowpatch', 'sounddevice', 'soundfile', 'numpy', 'httpx', 'certifi'):
    d, b, h = collect_all(package)
    datas += d
    binaries += b
    hidden += h
datas += [('THIRD_PARTY_LICENSES/OpenWhispr-MIT.txt', 'licenses'), ('THIRD_PARTY_NOTICES.md', 'licenses')]
datas += [('assets/dashboard-icons','assets/dashboard-icons'),('THIRD_PARTY_LICENSES/Lucide-ISC.txt','licenses')]
a = Analysis(['classroom_app.py'], pathex=['.'], binaries=binaries, datas=datas,
             hiddenimports=hidden, excludes=['tkinter'])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='ClickyClassroom', console=False)
coll = COLLECT(exe, a.binaries, a.datas, name='ClickyClassroom')
