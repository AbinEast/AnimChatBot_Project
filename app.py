# ==== Imports ====
from flask import Flask, render_template, request, jsonify
import sqlite3
from openai import OpenAI
import markdown2
import edge_tts
from io import BytesIO
from pydub import AudioSegment
import torch
from TTS.api import TTS
import os
import time
import re

# ==== Global Variables & Config ====
tts = None   # Will hold TTS model instance
type_tts = 'elevenlabs'  # Choose between 'elevenlabs', 'coqui', or 'edge'
elevenlabs_voice_id = 'Your voice ID'  # Replace with actual ElevenLabs voice ID
elevenlabs_api_key = 'Add your API key'  # Replace with actual ElevenLabs API key

# ==== Load TTS Model (based on type) ====
if type_tts == 'coqui':
    device = "cuda" if torch.cuda.is_available() else "cpu"
    tts = None  # Initialize
    try:
        # Try multilingual model for cloning
        tts = TTS("tts_models/multilingual/multi-dataset/your_tts", progress_bar=False).to(device)
        print("Successfully loaded multilingual model")
    except Exception as e:
        print(f"Failed to load multilingual model: {e}")
        try:
            # Try Bark model if the first fails
            tts = TTS("tts_models/multilingual/multi-dataset/bark", progress_bar=False).to(device)
            print("Successfully loaded Bark model")
        except Exception as e2:
            print(f"Failed to load Bark: {e2}")
            try:
                # Fallback single-language model
                tts = TTS("tts_models/en/ljspeech/tacotron2-DDC", progress_bar=False).to(device)
                print("Successfully loaded Tacotron2 model")
            except Exception as e3:
                print(f"All models failed: {e3}")
                type_tts = 'edge'
                tts = None
elif type_tts == 'elevenlabs':
    import requests
    print("Using ElevenLabs TTS")

# ==== Database Connection ====
conn = sqlite3.connect('chat_messages.db', check_same_thread=False)
c = conn.cursor()

# Create table if it doesn’t exist
c.execute('''CREATE TABLE IF NOT EXISTS messages
          (role TEXT, content TEXT)''')
conn.commit()

# ==== Utility: Clean text before TTS ====
def remove_emojis_and_pattern(text):
    text_no_tilde = text.replace('~', ' ')
    text_no_underscore = text_no_tilde.replace('_', ' ')
    text_no_star_words = re.sub(r'\*[^*]+?\*', '', text_no_underscore)  # remove *word*
    text_cleaned = text_no_star_words.replace('*', ' ').replace('=', ' ')
    text_cleaned = text_cleaned.replace('#', ' ')
    text_cleaned = re.sub(r'\<em\>([^<]+?)\<\/em\>', '', text_cleaned)  # remove <em> tags
    return text_cleaned

# ==== ElevenLabs TTS ====
def synth_audio_elevenlabs(text, temp_file):
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{elevenlabs_voice_id}"
    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": elevenlabs_api_key
    }
    data = {
        "text": text,
        "model_id": "eleven_monolingual_v1",
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.5
        }
    }
    try:
        response = requests.post(url, json=data, headers=headers)
        if response.status_code == 200:
            with open(temp_file, 'wb') as f:
                f.write(response.content)
            return temp_file
        else:
            print(f"ElevenLabs API error: {response.status_code}")
            return None
    except Exception as e:
        print(f"ElevenLabs error: {e}")
        return None

# ==== Edge TTS (Microsoft Speech) ====
async def synth_audio_edge(TEXT, temp_file):
    VOICE = 'en-US-EmilyNeutral'
    communicate = edge_tts.Communicate(TEXT, VOICE, rate='+10%')
    byte_array = bytearray()
    
    try:
        async for chunk in communicate.stream():
            if chunk['type'] == 'audio':
                byte_array.extend(chunk['data'])
        audio_data = BytesIO(byte_array)
        audio_segment = AudioSegment.from_file(audio_data)
        audio_segment.export(temp_file, format='wav')
    except Exception as e:
        print(e)
        return None
    
    return temp_file

# ==== Dispatcher to generate audio with chosen TTS ====
async def call_generate(text, temp_file, tts=None):
    if type_tts == 'edge':
        await synth_audio_edge(text, temp_file)
    elif type_tts == 'elevenlabs':
        synth_audio_elevenlabs(text, temp_file)
    else:
        # For Coqui
        if tts is None:
            print("TTS model not initialized, cannot generate audio")
            return None
        try:
            voice_file = "voice/voice.wav"
            if os.path.exists(voice_file):
                # With voice cloning
                tts.tts_to_file(text=text, speaker_wav=voice_file, language="en", file_path=temp_file)
            else:
                # Without cloning
                tts.tts_to_file(text=text, language="en", file_path=temp_file)
        except Exception as e:
            print(f"Trying without language parameter: {e}")
            try:
                if os.path.exists("voice/voice.wav"):
                    tts.tts_to_file(text=text, speaker_wav="voice/voice.wav", file_path=temp_file)
                else:
                    tts.tts_to_file(text=text, file_path=temp_file)
            except Exception as e2:
                print(f"TTS generation failed: {e2}")
                return None
    return temp_file

# ==== Wrapper for audio synthesis ====
async def synthesize(text, filename):
    text = remove_emojis_and_pattern(text)  # Clean text
    if not os.path.exists('./static/audio'):
        os.makedirs('./static/audio')
    
    # Clear old audio files
    for file in os.listdir('./static/audio'):
        os.remove('./static/audio/' + file)
    
    # Create new filename with timestamp
    timestamp = time.strftime('%Y%m%d-%H%M%S')
    temp_file = f'./static/audio/{filename}-{timestamp}.wav'
    
    # Generate audio file
    path_out = await call_generate(text, temp_file, tts=tts)
    
    # Placeholder for RVC (voice conversion if needed)
    final_file = f'./static/audio/output.wav'
    
    return path_out

# ==== Chatbot System Prompt ====
system_prompt = "You are named Aki. you're a helpful assistant with a kind, sweet, wholesome and cute anime girl personality."

# ==== Chatbot Logic ====
def getAnswer(role, text):
    # Insert user message into DB
    c.execute('INSERT INTO messages VALUES (?, ?)', (role, text))
    conn.commit()
    
    # Get last 5 messages from DB
    c.execute('SELECT * FROM messages order by rowid DESC LIMIT 5')
    previous_messages = [{'role': row[0], 'content': row[1]} for row in c.fetchall()]
    
    # Reverse order (oldest → newest)
    previous_messages = list(reversed(previous_messages))
    
    # Add system prompt if missing
    if 'system' not in [x['role'] for x in previous_messages]:
        previous_messages = [{'role': 'system', 'content': system_prompt}] + previous_messages
    
    # Call local LLM (Ollama w/ Llama3)
    client = OpenAI(base_url='http://localhost:11434/v1', api_key='ollama')
    response = client.chat.completions.create(
        model='llama3',
        messages=previous_messages,
        temperature=0.7,
    )
    
    # Extract response
    bot_response = response.choices[0].message.content.strip()
    
    # Save bot response into DB
    c.execute('INSERT INTO messages VALUES (?, ?)', ('assistant', bot_response))
    conn.commit()
    
    return bot_response

# ==== Flask App Setup ====
app = Flask(__name__)

# Home route
@app.route('/')
def index():
    return render_template('index.html')

# Echo route (for testing)
@app.route('/echo', methods=['POST'])
def echo():
    data = request.json
    message = data['message']
    return jsonify({'FROM': 'Echobot', 'MESSAGE': message})

# Chat route
@app.route('/chat', methods=['POST'])
def chat():
    import asyncio
    data = request.json
    
    # Get chatbot response
    message = getAnswer('user', data['message'])
    
    # Generate TTS audio for response
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        name_wav = loop.run_until_complete(synthesize(message, 'chat'))
    finally:
        loop.close()
    
    return jsonify({'FROM': 'Aki', 'MESSAGE': markdown2.markdown(message), 'WAV': name_wav})

# History route (all messages)
@app.route('/history', methods=['GET'])
def history():
    c.execute('SELECT * FROM messages order by rowid')
    previous_messages = [{'role': row[0], 'content': markdown2.markdown(row[1])} for row in c.fetchall()]
    return jsonify(previous_messages)

# ==== Run Flask App ====
if __name__== '__main__':
    app.run(debug=True)
