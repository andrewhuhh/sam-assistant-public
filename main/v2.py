import datetime
import glob
import io
import os
import threading
import tkinter as tk
from tkinter import filedialog, scrolledtext, ttk

import openai
import speech_recognition as sr
from dotenv import load_dotenv
from google.cloud import texttospeech
from PIL import Image, ImageTk
from pydub import AudioSegment
from pydub.playback import play

# Google Cloud API key JSON file
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "google_credentials.json"

# Load dotenv tokens
load_dotenv()
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

# SR
recognizer = sr.Recognizer()
def recognize_speech():
    with sr.Microphone() as source:
        print("Listening...")
        audio = recognizer.listen(source)
        try:
            print("Recognizing...")
            text = recognizer.recognize_google(audio)
            return text
        except Exception as e:
            print("Error:", e)
            return None

# Generate response
def generate_response(conversation_history):
    openai.api_key = OPENAI_API_KEY
    
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "system", "content": "You are a helpful assistant named SAM."}] + conversation_history,
        max_tokens=400,
        n=1,
        stop=None,
        temperature=0.8,
    )
    
    message = response.choices[0].message['content'].strip()
    return message

# TTS and conversation globals
stop_flag = False
stream = None
audio_lock = threading.Lock()
conversation_history = []

# Initialize the Text-to-Speech API client
client = texttospeech.TextToSpeechClient()

# Google Cloud TTS engine
def text_to_speech(text, language_code="en-US", voice_name="en-US-News-L"):
    global stop_flag, stream, audio_lock, client

    # Configure the synthesis request
    synthesis_input = texttospeech.SynthesisInput(text=text)
    voice = texttospeech.VoiceSelectionParams(language_code=language_code, name=voice_name)
    audio_config = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.LINEAR16, speaking_rate=1.1)

    # Generate the speech audio
    response = client.synthesize_speech(input=synthesis_input, voice=voice, audio_config=audio_config)

    # Save the audio to an in-memory binary stream
    with io.BytesIO(response.audio_content) as fp:
        # Load the audio with pydub
        audio = AudioSegment.from_file(fp, format="wav")

        with audio_lock:
            # Check if the stop_flag is set before playing the audio
            if not stop_flag:
                stream = play(audio)
            else:
                stop_flag = True  # Keep the TTS muted

# List all conversation files in the "conversations" folder
def list_conversation_files():
    folder_path = "conversations"
    files = glob.glob(f"{folder_path}/*.txt")
    return files

# Load the selected conversation file and update conversation_history
def load_conversation(file_path, conversation_history):
    with open(file_path, "r", encoding="utf-8") as file:
        lines = file.readlines()

    conversation_history.clear()
    current_role = ""
    current_content = ""

    for i, line in enumerate(lines):
        if line.startswith("User:") or line.startswith("SAM:"):
            if current_role:
                conversation_history.append({"role": current_role, "content": current_content.rstrip()})
            
            current_role = "user" if line.startswith("User:") else "assistant"
            current_content = line[6:] if current_role == "user" else line[5:]
        else:
            current_content += line

    if current_role and current_content.strip():
        conversation_history.append({"role": current_role, "content": current_content.rstrip()})

# Conversation summary
def generate_summary(conversation_history):
    openai.api_key = OPENAI_API_KEY
    
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "system", "content": "You are a helpful assistant named SAM."}] + conversation_history + [{"role": "user", "content": "Please summarize this conversation in less than 6 words and replace all spaces with underscores. Do not include any special characters or punctuation in your response, only text and underscores."}],
        max_tokens=10,
        n=1,
        stop=None,
        temperature=0.8,
    )
    
    message = response.choices[0].message['content'].strip()
    return message

# Auto-scroll function
def scroll_to_end(chat_history):
    chat_history.see(tk.END)

# Load icons
def load_icons():
    icons = {}
    icons['talk'] = Image.open("icons\\mic.png").resize((16, 16), Image.LANCZOS)
    icons['stop'] = Image.open("icons\\exit.png").resize((16, 16), Image.LANCZOS)
    icons['save'] = Image.open("icons\\save.png").resize((16, 16), Image.LANCZOS)
    icons['mute'] = Image.open("icons\\mute.png").resize((16, 16), Image.LANCZOS)
    icons['load'] = Image.open("icons\\load.png").resize((16, 16), Image.LANCZOS)
    icons['clear'] = Image.open("icons\\clear.png").resize((16, 16), Image.LANCZOS)
    
    return icons

# Main and GUI
def main():
    def on_talk():
        user_text = recognize_speech()
        if not user_text:
            return

        # Display the user's input on the GUI and update conversation history
        chat_history.insert(tk.END, "User: ", "user")
        chat_history.insert(tk.END, f"{user_text}\n\n")
        conversation_history.append({"role": "user", "content": user_text})

        # Display the assistant's response
        response = generate_response(conversation_history)
        chat_history.insert(tk.END, "SAM: ", "assistant")
        chat_history.insert(tk.END, f"{response}\n\n")

        # Update the conversation history with the assistant's response
        conversation_history.append({"role": "assistant", "content": response})
        scroll_to_end(chat_history)

        # Update the GUI immediately
        root.update_idletasks()

        # Run text_to_speech in a separate thread
        tts_thread = threading.Thread(target=text_to_speech, args=(response,))
        tts_thread.start()
    
    def on_mute():
        global stop_flag, audio_lock

        with audio_lock:
            # Set the stop_flag
            if stop_flag == True:
                stop_flag = False
                chat_history.insert(tk.END, "--- Unmuted ---\n\n", "system")
                scroll_to_end(chat_history)
                print(stop_flag)
            else:
                stop_flag = True
                chat_history.insert(tk.END, "--- Muted ---\n\n", "system")
                scroll_to_end(chat_history)
                print(stop_flag)

    def on_stop():
        root.destroy()

    def on_save():
        # Force an update of the chat_history widget
        root.update_idletasks()

        # Define the nested folder path
        folder_path = "conversations"
        
        # Check if the folder exists, and create it if not
        if not os.path.exists(folder_path):
            os.makedirs(folder_path)

        # Generate a summary of the conversation
        summary = generate_summary(conversation_history)

        # Create a unique file name based on the summary
        file_name = f"{summary[:50]}.txt"  # Limit the title to 50 characters to avoid overly long file names
        file_path = os.path.join(folder_path, file_name)

        # Save the conversation to the file
        with open(file_path, 'w', encoding='utf-8') as file:
            file.write(chat_history.get("1.0", tk.END))
        
        # Log the save event in the console
        print(f"Conversation saved to {file_path}")

        # Display the "conversation saved" message in the text box and scroll to the end
        chat_history.insert(tk.END, f"--- Conversation Saved as: {file_name} ---\n\n", "system")
        scroll_to_end(chat_history)
    
    def on_load():
        folder_path = "conversations"
        file_path = filedialog.askopenfilename(initialdir=folder_path, title="Select a Conversation File", filetypes=(("Text Files", "*.txt"), ("All Files", "*.*")))
        
        if file_path:
            # Clear the chat history
            chat_history.delete("1.0", tk.END)

            # Load the conversation from the file and update conversation_history
            load_conversation(file_path, conversation_history)

            # Display the loaded conversation in the text box
            for message in conversation_history:
                if message["role"] == "user":
                    chat_history.insert(tk.END, "User: ", "user")
                else:
                    chat_history.insert(tk.END, "SAM: ", "assistant")
                chat_history.insert(tk.END, f"{message['content']}\n\n")
                scroll_to_end(chat_history)

            # Log the load event in the console
            print(f"Conversation loaded from {file_path}")

            # Display the "conversation loaded" message in the text box
            file_name = os.path.basename(file_path)
            chat_history.insert(tk.END, f"--- Conversation Loaded from: {file_name} ---\n\n", "system")

    def on_clear():
        global conversation_history
        conversation_history = []  # Reset the conversation history
        chat_history.delete("1.0", tk.END)  # Clear the text in the chat_history text widget
        scroll_to_end(chat_history)

    # GUI box
    root = tk.Tk()
    root.title("SAM")

    # Chat box
    chat_history = scrolledtext.ScrolledText(root, wrap=tk.WORD)
    chat_history.grid(row=0, column=0, columnspan=6, padx=5, pady=5, sticky="nsew")

    # Custom font options
    chat_history.tag_configure("user", font=("Arial", 10, "bold"))
    chat_history.tag_configure("assistant", font=("Arial", 10, "bold"))
    chat_history.tag_configure("system", font=("Arial", 10, "bold"))

    # Load icons
    icons = load_icons()

    # Button and icon configs
    talk_img_tk = ImageTk.PhotoImage(icons['talk'])
    stop_img_tk = ImageTk.PhotoImage(icons['stop'])
    save_img_tk = ImageTk.PhotoImage(icons['save'])
    mute_img_tk = ImageTk.PhotoImage(icons['mute'])
    load_img_tk = ImageTk.PhotoImage(icons['load'])
    clear_img_tk = ImageTk.PhotoImage(icons['clear'])
    
    # Button styling
    style = ttk.Style()
    style.configure('TButton', font=('Helvetica', 10), padding=10)

    # Talk button
    talk_button = ttk.Button(root, text="Talk", command=on_talk, compound=tk.LEFT, style='TButton')
    talk_button.grid(row=1, column=0, columnspan=2, padx=(5,0), pady=(5,0), sticky="nsew")
    talk_button.config(image=talk_img_tk)
    # Mute button
    mute_button = ttk.Button(root, text="Mute", command=on_mute, compound=tk.LEFT, style='TButton')
    mute_button.grid(row=1, column=2, columnspan=2, padx=5, pady=(5,0), sticky="nsew")
    mute_button.config(image=mute_img_tk)
    # Clear button
    clear_button = ttk.Button(root, text="Clear", command=on_clear, compound=tk.LEFT, style='TButton')
    clear_button.grid(row=2, column=1, padx=(5,0), pady=(5,0), sticky="nsew")
    clear_button.config(image=clear_img_tk)

    # Save button
    save_button = ttk.Button(root, text="Save", command=on_save, compound=tk.LEFT, style='TButton')
    save_button.grid(row=2, column=2, padx=5, pady=(5,0), sticky="nsew")
    save_button.config(image=save_img_tk)
    # Load button
    load_button = ttk.Button(root, text="Load", command=on_load, compound=tk.LEFT, style='TButton')
    load_button.grid(row=2, column=0, padx=(5,0), pady=(5,0), sticky="nsew")
    load_button.config(image=load_img_tk)


    # Exit button
    stop_button = ttk.Button(root, text="Exit", command=on_stop, compound=tk.LEFT, style='TButton')
    stop_button.grid(row=3, column=0, columnspan=3, padx=5, pady=5, sticky="nsew")
    stop_button.config(image=stop_img_tk)

    # Configure row and column weights (responsive resizing)
    root.grid_rowconfigure(0, weight=1)
    root.grid_columnconfigure(0, weight=1)
    root.grid_columnconfigure(1, weight=1)
    root.grid_columnconfigure(2, weight=1)

    root.mainloop()

# Initiate
if __name__ == "__main__":
    main()