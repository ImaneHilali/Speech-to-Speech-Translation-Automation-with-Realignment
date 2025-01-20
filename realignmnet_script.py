import base64
from flask import Flask, request, jsonify
from google.cloud import storage
from openai import OpenAI
from langdetect import detect
import json
import os
import re
app = Flask(__name__)

NVIDIA_API_KEY = "key"
nvidia_client = OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=NVIDIA_API_KEY)

storage_client = storage.Client()

def download_blob(bucket_name, blob_name, destination_file):
    """Download file from GCS bucket."""
    try:
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        blob.download_to_filename(destination_file)
    except Exception as e:
        raise RuntimeError(f"Failed to download blob: {e}")

def upload_blob(bucket_name, content, destination_blob_name):
    """
    Uploads a file to the bucket with a sanitized name.
    """
    sanitized_blob_name = re.sub(r"[^\w\-_/.]", "_", destination_blob_name)
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(sanitized_blob_name)

    blob.upload_from_string(content, content_type="application/json")
    print(f"File uploaded to {sanitized_blob_name}.")

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

def detect_language(segments):
    """Detect the language of the input segments."""
    if not segments:
        return 'en'
    sample_text = " ".join(segment["text"] for segment in segments[:5])
    return detect(sample_text)

def determine_target_languages(detected_lang):
    """Determine the target languages based on the detected language."""
    if detected_lang == 'fr':
        return ['eng_Latn', 'spa_Latn']
    elif detected_lang == 'es':
        return ['fra_Latn', 'eng_Latn']
    elif detected_lang == 'en':
        return ['fra_Latn', 'spa_Latn']
    else:
        return []

def realign_with_prompt(original_segments, target_lang):
    """Realign translated text using the updated prompt."""
    aligned_segments = []

    for segment in original_segments:
        source_text = segment['text']
        prompt = (
            f"As an expert translator specializing in {target_lang}, translate the following text from English to {target_lang} "
            f"with a focus on preserving both meaning and alignment with the original text's length and structure. "
            f"Prioritize sentence-by-sentence translation to closely match the word count and layout of the source text, "
            f"maintaining readability and natural flow in {target_lang}. "
            f"Ensure that cultural and idiomatic expressions are preserved, using equivalent expressions where necessary. "
            f"The text to translate is: \"{source_text}\". "
            f"Provide only the translated text, aligned with the original sentence structure and length, without any added commentary or formatting."
        )

        try:
            response = nvidia_client.chat.completions.create(
                model="nvidia/llama-3.1-nemotron-70b-instruct",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1024
            )

            if hasattr(response, 'choices') and len(response.choices) > 0:
                translated_text = response.choices[0].message.content.strip()
            else:
                translated_text = ""

            aligned_segments.append({
                "time": segment["time"],
                "speaker-id": segment["speaker-id"],
                "text": translated_text
            })

        except Exception as e:
            print(f"Error during realignment for segment: {source_text}. Error: {e}")
            aligned_segments.append({
                "time": segment["time"],
                "speaker-id": segment["speaker-id"],
                "text": ""
            })

    return aligned_segments

@app.route("/translate_realignment", methods=["POST"])
def realign_handler():
    try:
        data = request.get_json()
        if "message" in data and "data" in data["message"]:
            event_data = json.loads(base64.b64decode(data["message"]["data"]).decode("utf-8"))
            bucket = event_data["bucket"]
            blob_name = event_data["name"]
            output_bucket = event_data.get("output_bucket", "vertex-translation-output")
        else:
            return jsonify({"error": "Invalid event format"}), 400

        input_file = "/tmp/translation_input.txt"
        download_blob(bucket, blob_name, input_file)

        with open(input_file, "r", encoding="utf-8") as f:
            input_text = f.read()

        input_segments = parse_txt_to_json(input_text)
        detected_lang = detect_language(input_segments)
        print(f"Detected Language: {detected_lang}")

        target_langs = determine_target_languages(detected_lang)

        output_data = {}

        for target_lang in target_langs:
            aligned_segments = realign_with_prompt(input_segments, target_lang)

            result_data = []
            for segment in aligned_segments:
                result_data.append({
                    "time": segment["time"],
                    "speaker-id": segment["speaker-id"],
                    "text": segment["text"]
                })

            output_data[target_lang] = result_data

        for lang_key, output_translations in output_data.items():
            output_file = json.dumps(output_translations, ensure_ascii=False, indent=4)
            output_blob_name = f"translations_accuracy_mode/{os.path.basename(blob_name)}_{lang_key}.json"

            upload_blob(output_bucket, output_file, output_blob_name)

        return jsonify({"message": "Realignment completed for all languages", "output_files": list(output_data.keys())}), 200

    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)