"""Python adaptations of OpenWhispr's MIT-licensed audio policies.

Sources at b9e9ebefac4b961456c269164a93ddfdd53438b9:
src/helpers/parakeetSegmentation.js and src/helpers/localSpeechGate.js.
Copyright(c)2024 OpenWhispr Team. See THIRD_PARTY_NOTICES.md.
"""
import math
import numpy as np


def split_at_pauses(samples, sample_rate=16000, max_seconds=30):
    """Port the source's100ms pause search and0.5second tail allowance."""
    samples = np.asarray(samples, dtype=np.float32)
    limit_frames = int(max_seconds * sample_rate)
    frame = max(1, round(.01 * sample_rate))
    search = 4 * sample_rate
    allowance = round(.5 * sample_rate)
    segments = max(1, math.ceil((len(samples)-allowance) / limit_frames))
    result, start = [], 0
    while len(samples)-start > limit_frames+allowance:
        limit = start+limit_frames
        earliest = max(limit-search, len(samples)-(segments-len(result)-1)*limit_frames-allowance)
        count = (limit-earliest)//frame
        cut = limit
        if count >= 10:
            values = samples[earliest:earliest+count*frame].reshape(count, frame).astype(np.float64)
            energies = (values*values).sum(axis=1)
            windows = [float(energies[i:i+10].sum()) for i in range(count-9)]
            quietest = min(windows)
            run_start = windows.index(quietest)
            run_end = run_start
            while run_end+1 < len(windows) and windows[run_end+1] == quietest:
                run_end += 1
            if quietest < windows[-1]*.5:
                cut = earliest+((run_start+run_end+10)//2)*frame
        result.append(samples[start:cut])
        start = cut
    result.append(samples[start:])
    return result


def speech_decision(samples, sample_rate=16000):
    """Port the PCM16 gate without treating missing measurements as silence."""
    audio = np.asarray(samples, dtype=np.float32)
    peak_rms, speech_windows, count = 0., 0, 0
    for start in range(0, len(audio), max(1, round(sample_rate*.1))):
        window = audio[start:start+max(1, round(sample_rate*.1))]
        if not len(window):
            continue
        # Match recordPcm16SpeechWindow's8bit analyser quantization.
        pcm16 = np.clip(window*32768, -32768, 32767).astype(np.int16)
        quantized = (np.floor(128*(1+pcm16.astype(np.float64)/32768))-128)/128
        rms = float(np.sqrt(np.mean(quantized*quantized)))
        peak = float(np.max(np.abs(quantized)))
        count += 1
        peak_rms = max(peak_rms, rms)
        speech_windows += int(rms >= .003 and peak >= .02)
    if not count:
        return False, 'unavailable'
    if peak_rms < .002:
        return True, 'silence'
    if not speech_windows and peak_rms < .006:
        return True, 'insufficient_speech'
    return False, 'speech_detected'
