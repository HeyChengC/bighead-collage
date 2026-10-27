# 用 demucs（htdemucs）把一条混音分成 人声 / 其他（配乐+音效）；只用 soundfile 读写，不依赖 torchaudio
import sys, numpy as np, soundfile as sf, torch
import os
if os.environ.get('DEMUCS_PATH'): sys.path.insert(0, os.environ['DEMUCS_PATH'])
from demucs.pretrained import get_model
from demucs.apply import apply_model
src, out = sys.argv[1], sys.argv[2]
m = get_model('htdemucs'); m.eval()
y, sr = sf.read(src, always_2d=True)
if sr != m.samplerate:
    import librosa; y = np.stack([librosa.resample(y[:, c], orig_sr=sr, target_sr=m.samplerate) for c in range(y.shape[1])], 1); sr = m.samplerate
if y.shape[1] == 1: y = np.repeat(y, 2, 1)
x = torch.tensor(y.T, dtype=torch.float32)[None]
ref = x.mean(); sd = x.std(); x = (x - ref) / sd
with torch.no_grad(): s = apply_model(m, x, device='cpu', split=True, overlap=.25)[0]
s = s * sd + ref
names = m.sources                       # drums bass other vocals
for n, w in zip(names, s): sf.write(f'{out}_{n}.wav', w.numpy().T, sr)
print('ok', names)
