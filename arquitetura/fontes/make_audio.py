import sys, json, numpy as np, soundfile as sf
sys.path.insert(0, "/tmp/claude-0/-home-claude/4c9ae48c-10e9-5678-8681-628a8f13dac5/scratchpad/build")
from script import SCENES, tts_text
from tts import kokoro
out = sys.argv[1]
tts = kokoro(); meta = []
for sc in SCENES:
    a = tts.generate(tts_text(sc["text"]), sid=42, speed=1.0)
    x = np.asarray(a.samples, dtype="float32")
    pad = np.zeros(int(a.sample_rate*0.5), dtype="float32"); lead = np.zeros(int(a.sample_rate*0.35), dtype="float32")
    x = np.concatenate([lead, x, pad]); peak = np.abs(x).max() or 1; x = x/peak*0.89
    sf.write(f"{out}/{sc['id']}.wav", x, a.sample_rate)
    meta.append({"id":sc["id"], "dur": len(x)/a.sample_rate, "sr": a.sample_rate})
    print(sc["id"], round(len(x)/a.sample_rate,2), flush=True)
json.dump(meta, open(f"{out}/meta.json","w"))
print("total", round(sum(m["dur"] for m in meta),1))
