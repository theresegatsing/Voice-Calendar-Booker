# stt_live.py (IMPROVED audio handling)
import queue
import sys
import signal
import re
import shutil
import numpy as np
import sounddevice as sd
from google.cloud import speech
from google.auth.exceptions import DefaultCredentialsError
import time
import threading

LANGUAGE = "en-US"
SAMPLE_RATE = 16000
CHANNELS = 1
BLOCKS_PER_SECOND = 50  # Increased for better responsiveness
CHUNK_DURATION = 0.1  # 100ms chunks for better real-time processing

audio_q = queue.Queue()
committed_text = ""
last_len = 0
is_recording = False

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

def list_microphones():
    """List available audio devices"""
    print("Available audio devices:")
    devices = sd.query_devices()
    for i, device in enumerate(devices):
        if device['max_input_channels'] > 0:
            print(f"{i}: {device['name']} (in: {device['max_input_channels']} channels)")

def _audio_callback(indata, frames, time_info, status):
    if status: 
        print(f"\n[Audio warning] {status}", file=sys.stderr, flush=True)
    if is_recording:
        audio_q.put((indata.copy() * 32767).astype(np.int16).tobytes())

def _request_generator():
    from google.cloud import speech as _speech
    while True:
        chunk = audio_q.get()
        if chunk is None: 
            return
        yield _speech.StreamingRecognizeRequest(audio_content=chunk)

def print_recording_indicator():
    """Show a visual indicator that recording is in progress"""
    indicators = ["●", "◎", "○"]
    i = 0
    while is_recording:
        print(f"\r\033[2K🎤 Recording {indicators[i % 3]} (Press Ctrl+C to stop)", end="", flush=True)
        i += 1
        time.sleep(0.5)
    print("\r\033[2K", end="", flush=True)

def transcribe_once() -> str:
    global committed_text, is_recording
    committed_text = ""
    
    # List available microphones for debugging
    list_microphones()
    
    print("🎤 Speak now... (Press Ctrl+C when done)")
    print("Starting in: 3...", end="", flush=True)
    time.sleep(1)
    print("2...", end="", flush=True)
    time.sleep(1)
    print("1...", end="", flush=True)
    time.sleep(1)
    print("GO! 🎙️")
    print("Speak clearly into your microphone...")
    
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
        model="latest_short",  # Use latest model for better accuracy
        use_enhanced=True,     # Use enhanced model for better accuracy
    )
    
    streaming_config = speech.StreamingRecognitionConfig(
        config=config, 
        interim_results=True,
        single_utterance=False  # Allow longer utterances
    )
    
    blocksize = int(SAMPLE_RATE * CHUNK_DURATION)
    
    try:
        # Start recording indicator
        is_recording = True
        indicator_thread = threading.Thread(target=print_recording_indicator, daemon=True)
        indicator_thread.start()
        
        with sd.InputStream(
            samplerate=SAMPLE_RATE, 
            channels=CHANNELS, 
            dtype="float32",
            blocksize=blocksize, 
            callback=_audio_callback,
            device=None  # Let sounddevice choose the default device
        ) as stream:
            print(f"\n📡 Using audio device: {stream.device}")
            
            requests = _request_generator()
            responses = client.streaming_recognize(streaming_config, requests)
            
            try:
                silence_counter = 0
                max_silence = 10  # Stop after 5 seconds of silence
                
                for resp in responses:
                    if not is_recording:
                        break
                        
                    for result in resp.results:
                        if not result.alternatives:
                            continue
                            
                        alt = result.alternatives[0]
                        txt = clean_text(alt.transcript)
                        
                        if result.is_final:
                            committed_text = (committed_text + " " + txt).strip()
                            one_line_preview("💬 " + committed_text)
                            silence_counter = 0  # Reset silence counter when speech is detected
                        else:
                            # Show interim results
                            preview = f"💭 {committed_text} {txt}" if committed_text else f"💭 {txt}"
                            one_line_preview(preview)
                    
                    # Check for silence timeout
                    silence_counter += 1
                    if silence_counter > max_silence and committed_text:
                        print("\n⏹️  Auto-stop (silence detected)")
                        break
                        
            except KeyboardInterrupt:
                print("\n⏹️  Recording stopped by user")
            except Exception as e:
                print(f"\n❌ Recognition error: {e}")
            finally:
                is_recording = False
                audio_q.put(None)
                indicator_thread.join(timeout=1)
                
    except sd.PortAudioError as e:
        print(f"❌ Audio device error: {e}")
        print("Please check your microphone connection and permissions.")
        return input("🧑 Type your command instead: ")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return input("🧑 Type your command instead: ")
    finally:
        is_recording = False
    
    print("\n✅ Transcript complete")
    if not committed_text:
        print("❌ No speech detected. Please try again or type your command.")
        return input("🧑 Type your command: ")
    
    return committed_text

# Add a test function to check audio
def test_microphone():
    """Test microphone functionality"""
    print("Testing microphone...")
    try:
        duration = 3  # seconds
        print(f"Recording for {duration} seconds...")
        
        def callback(indata, frames, time, status):
            if status:
                print(f"Audio status: {status}")
            # Calculate volume level
            rms = np.sqrt(np.mean(indata**2))
            print(f"\rVolume: {rms:.4f} ", end="", flush=True)
        
        with sd.InputStream(callback=callback, channels=CHANNELS, samplerate=SAMPLE_RATE):
            sd.sleep(duration * 1000)
        print("\n✅ Microphone test completed")
        
    except Exception as e:
        print(f"❌ Microphone test failed: {e}")

if __name__ == "__main__":
    # Test the microphone
    test_microphone()
    # Then transcribe
    result = transcribe_once()
    print(f"Final result: {result}")