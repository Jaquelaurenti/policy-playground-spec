import sys, json, sherpa_onnx, soundfile as sf
T="/tmp/claude-0/-home-claude/4c9ae48c-10e9-5678-8681-628a8f13dac5/scratchpad/tts"
def kokoro():
    d=f"{T}/kokoro-multi-lang-v1_0"
    cfg=sherpa_onnx.OfflineTtsConfig(model=sherpa_onnx.OfflineTtsModelConfig(kokoro=sherpa_onnx.OfflineTtsKokoroModelConfig(
        model=f"{d}/model.onnx", voices=f"{d}/voices.bin", tokens=f"{d}/tokens.txt", data_dir=f"{d}/espeak-ng-data",
        lexicon=f"{d}/lexicon-us-en.txt,{d}/lexicon-zh.txt", dict_dir=f"{d}/dict", lang="pt-br"), num_threads=4))
    return sherpa_onnx.OfflineTts(cfg)
def faber():
    d=f"{T}/vits-piper-pt_BR-faber-medium"
    cfg=sherpa_onnx.OfflineTtsConfig(model=sherpa_onnx.OfflineTtsModelConfig(vits=sherpa_onnx.OfflineTtsVitsModelConfig(
        model=f"{d}/pt_BR-faber-medium.onnx", tokens=f"{d}/tokens.txt", data_dir=f"{d}/espeak-ng-data"), num_threads=4))
    return sherpa_onnx.OfflineTts(cfg)
if __name__=="__main__":
    which, text, out = sys.argv[1], sys.argv[2], sys.argv[3]
    tts = kokoro() if which=="kokoro" else faber()
    sid = int(sys.argv[4]) if len(sys.argv)>4 else 0
    a = tts.generate(text, sid=sid, speed=1.0)
    sf.write(out, a.samples, a.sample_rate); print(out, len(a.samples)/a.sample_rate)
