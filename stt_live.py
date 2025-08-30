# stt_live.py
import queue, sys, signal, re, shutil
import numpy as np
import sounddevice as sd
from google.cloud import speech
from google.auth.exceptions import DefaultCredentialsError

LANGUAGE = "en-US"
SAMPLE_RATE = 16000
CHANNELS = 1
BLOCKS_PER_SECOND = 10

audio_q = queue.Queue()
committed_text = ""
last_len = 0

def clean_text(t: str) -> str:
    return re.sub(r"\s+", " ", t.strip())

def one_line_preview(paragraph: str):
    global last_len
    try:
        width = shutil.get_terminal_size((100, 20)).columns
    except Exception:
        width = 100
    view = paragraph[-(width-2):] if len(paragraph) > width else paragraph
    print("\r\033[2K" + view, end="", flush=True)
    last_len = len(view)

def _audio_callback(indata, frames, time_info, status):
    if status: print("\n[Audio warning]", status, file=sys.stderr, flush=True)
    audio_q.put((indata.copy() * 32767).astype(np.int16).tobytes())

def _request_generator():
    from google.cloud import speech as _speech
    while True:
        chunk = audio_q.get()
        if chunk is None: return
        yield _speech.StreamingRecognizeRequest(audio_content=chunk)

def transcribe_once() -> str:
    global committed_text
    committed_text = ""
    try:
        client = speech.SpeechClient()
    except DefaultCredentialsError:
        print("[!] No Google Speech credentials. Falling back to typed input.")
        return input("🧑 Type your command: ")
    config = speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
        sample_rate_hertz=SAMPLE_RATE,
        language_code=LANGUAGE,
        enable_automatic_punctuation=True,
    )
    streaming_config = speech.StreamingRecognitionConfig(config=config, interim_results=True)
    blocksize = int(SAMPLE_RATE / BLOCKS_PER_SECOND)
    with sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS, dtype="float32",
                        blocksize=blocksize, callback=_audio_callback):
        requests = _request_generator()
        responses = client.streaming_recognize(streaming_config, requests)
        try:
            for resp in responses:
                for result in resp.results:
                    alt = result.alternatives[0]
                    txt = clean_text(alt.transcript)
                    if result.is_final:
                        committed_text = (committed_text + " " + txt).strip()
                        one_line_preview(committed_text)
        except KeyboardInterrupt:
            pass
        finally:
            audio_q.put(None)
    print("\n📝 Transcript:\n", committed_text)
    return committed_text
