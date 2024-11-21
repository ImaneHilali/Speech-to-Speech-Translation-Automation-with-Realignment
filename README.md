# Speech-to-Speech-Translation-Automation-with-Realignment
This repository implements an end-to-end automated translation pipeline for transcriptions stored in Google Cloud Storage. The system leverages Google Cloud Functions to trigger translation jobs when a new transcription file is uploaded to a specified input bucket. The translation process involves:

  1. Download and Parse: The transcription file is downloaded, and the text is parsed into a structured format with timestamps, speaker IDs, and text.
  2. Language Detection: The language of the input text is detected, and the appropriate target languages for translation are determined.
  3. Realignment: The system uses AI models to realign the translated text to preserve the structure and timing of the original transcription.
  4. Cloud Run Service: A Cloud Run service is called to handle the translation and realignment tasks. The results are returned in the specified format and uploaded to the designated output bucket in Google Cloud Storage.
  5. Error Handling and Logging: Comprehensive error handling ensures robustness, logging every step of the process for monitoring and troubleshooting.
     
The automation is triggered by a Google Cloud Storage event when a new transcription file is uploaded. The event data is forwarded to a Cloud Run service, where the translation and realignment process occurs. Once the process is complete, the translated files are uploaded to a designated output bucket for further use or review.

This setup facilitates a scalable, serverless architecture for automatic, real-time language translation and alignment of audio transcriptions.
