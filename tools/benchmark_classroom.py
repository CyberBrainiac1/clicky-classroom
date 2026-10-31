"""Benchmark saved audio/reference text, with no microphone or active app access.

Install jiwer in the development environment, then run:
python tools/benchmark_classroom.py --audio lecture.wav --reference reference.txt --output benchmark-output
"""
import argparse
import json
import os
from pathlib import Path
import sys
import time
import wave

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('OMP_NUM_THREADS','1')
os.environ.setdefault('MKL_NUM_THREADS','1')


def main():
    if os.name == 'nt':
        import ctypes
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.GetCurrentProcess.restype=ctypes.c_void_p
        kernel.SetPriorityClass.argtypes=[ctypes.c_void_p,ctypes.c_uint]
        if not kernel.SetPriorityClass(kernel.GetCurrentProcess(),0x4000):
            raise ctypes.WinError(ctypes.get_last_error())
    from classroom.models import default_parakeet_directory
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audio',required=True)
    parser.add_argument('--reference',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--model',default='base')
    parser.add_argument('--engine',choices=['whisper','parakeet'],default='parakeet')
    parser.add_argument('--parakeet-directory',default=default_parakeet_directory())
    args=parser.parse_args()
    out=Path(args.output).resolve()
    out.mkdir(parents=True,exist_ok=True)
    os.environ['CLICKY_CLASSROOM_DATA_DIR']=str(out/'data')
    from classroom.settings import Settings
    from classroom.recorder import import_audio,retry_session
    import jiwer
    reference=Path(args.reference).read_text('utf-8')
    settings=Settings(engine=args.engine,whisper_model=args.model,parakeet_directory=args.parakeet_directory,
                      automatic_notes=False,threads=1)
    session=import_audio(args.audio,'Transcription benchmark',settings)
    began=time.monotonic()
    retry_session(session,print)
    elapsed=time.monotonic()-began
    hypothesis=' '.join(row['text'] for row in session.rows() if row['status']=='done')
    normalize=jiwer.Compose([jiwer.ToLowerCase(),jiwer.RemovePunctuation(),jiwer.RemoveMultipleSpaces(),jiwer.Strip()])
    with wave.open(str(session.audio_path('import')),'rb') as audio:
        duration=audio.getnframes()/audio.getframerate()
    result={'referenceWords':len(reference.split()),'transcribedWords':len(hypothesis.split()),
            'audioSeconds':duration,'processingSeconds':elapsed,
            'wordErrorRate':jiwer.wer(normalize(reference),normalize(hypothesis)),
            'allChunksProcessed':not session.has_errors(),'chunks':len(session.rows()),
            'engine':args.engine,'model':Path(args.parakeet_directory).name if args.engine=='parakeet' else args.model,
            'threads':1,'liveDevicesUsed':False,'priority':'BelowNormal' if os.name=='nt' else 'normal'}
    (out/'hypothesis.txt').write_text(hypothesis,encoding='utf-8')
    (out/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
