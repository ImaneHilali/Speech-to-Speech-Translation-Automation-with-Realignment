import json
import base64
from langdetect import detect
from google.cloud import storage
from flask import Flask, request, jsonify
from openai import OpenAI
import re
import os

NVIDIA_API_KEY = "key"

nvidia_client = OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=NVIDIA_API_KEY)

app = Flask(__name__)

lang_code_map = {
    "fr": "fra_Latn",
    "en": "eng_Latn",
    "es": "spa_Latn",
}

client = storage.Client(project="core-dev-435517")

def download_blob(bucket_name, source_blob_name, destination_file_name):
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(source_blob_name)
    blob.download_to_filename(destination_file_name)
    print(f"Blob {source_blob_name} downloaded to {destination_file_name}.")

def upload_blob(bucket_name, source_file_name, destination_blob_name):
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(destination_blob_name)
    blob.upload_from_filename(source_file_name)
    print(f"File {source_file_name} uploaded to {destination_blob_name}.")

def parse_txt_to_json(input_text):
    """Parse text to JSON format with time, speaker-id, and text."""
    json_data = []
    lines = input_text.splitlines()
    for line in lines:
        match = re.match(r'\[(.*?)\] (\w+):\s*(.*)', line)
        if match:
            time = match.group(1).strip()
            speaker_id = match.group(2).strip()
            text = match.group(3).strip()
            json_data.append({"time": time, "speaker-id": speaker_id, "text": text})
    return json_data

def clean_translation(response_text):
    """Remove unwanted introductory text from the translation response."""
    clean_text = re.sub(r"^(Here is the translation.*?:|Translate.*?:|Translation.*?:)", "", response_text, flags=re.IGNORECASE).strip()
    return clean_text
    
def translate_llama(input_data):
    """Perform translation using the LLaMA API."""
    detected_lang = detect(input_data[0]['text'])
    source_lang = lang_code_map.get(detected_lang)

    target_langs = []
    if detected_lang == 'fr':
        target_langs = ['eng_Latn', 'spa_Latn']
    elif detected_lang == 'es':
        target_langs = ['fra_Latn', 'eng_Latn']
    elif detected_lang == 'en':
        target_langs = ['fra_Latn', 'spa_Latn']

    translations = {}

    for target_lang in target_langs:
        translated_entries = []
        try:
            for entry in input_data:
                response = nvidia_client.chat.completions.create(
                    model="nvidia/llama-3.1-nemotron-70b-instruct",
                    messages=[{"role": "user", "content": f"Translate to {target_lang} only the following text without any additional explanation or introduction: {entry['text']}"}],
                    max_tokens=1024
                )

                if hasattr(response, 'choices') and len(response.choices) > 0:
                    raw_translation = response.choices[0].message.content.strip()
                    clean_text = clean_translation(raw_translation)
                    translated_entries.append({"time": entry["time"], "speaker-id": entry["speaker-id"], "text": clean_text})
                else:
                    translated_entries.append({"time": entry["time"], "speaker-id": entry["speaker-id"], "text": ""})

            translations[target_lang] = translated_entries

        except Exception as e:
            print(f"Error while translating to {target_lang}: {e}")
            translations[target_lang] = [{"time": entry["time"], "speaker-id": entry["speaker-id"], "text": ""} for entry in input_data]

    return translations

@app.route("/translate", methods=["POST"])
def translate_handler():
    try:
        data = request.get_json()

        if "message" in data and "data" in data["message"]:
            event_data = json.loads(base64.b64decode(data['message']['data']).decode('utf-8'))
            input_bucket = event_data['bucket']
            input_blob_name = event_data['name']
            output_bucket = event_data.get('output_bucket', 'vertex-translation-output')
        else:
            return jsonify({"error": "Invalid event format"}), 400

        input_file = '/tmp/translation_input.txt'
        download_blob(input_bucket, input_blob_name, input_file)

        with open(input_file, 'r', encoding='utf-8') as f:
            input_text = f.read()

        input_data = parse_txt_to_json(input_text)
        translated_data = translate_llama(input_data)

        for lang_key, output_data in translated_data.items():
            output_file = f'/tmp/{lang_key}.json'
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(output_data, f, ensure_ascii=False, indent=4)
            upload_blob(output_bucket, output_file, f"translations_accuracy_mode/{os.path.basename(input_blob_name)}_{lang_key}.json")

        return jsonify({"status": "success", "message": f"Translations completed and uploaded for {input_blob_name}"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)