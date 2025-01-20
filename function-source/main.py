import functions_framework
import requests
import json
import base64

# Triggered by a change in a storage bucket
@functions_framework.cloud_event
def translation_automation_job(cloud_event):

    print(f"Received Cloud Event: {cloud_event}")

    # ON means Realignmnet mode, OFF means Accuracy mode 
    mode="OFF"

    # The URL of the Cloud Run service
    target_cloud_run_url = (
        "https://translation-service-************.us-central1.run.app/translate"
        if mode == "OFF"
        else "https://translation-realignment-container-*************.us-central1.run.app/translate_realignment"
    )

    # Extract bucket and object name from the cloud event
    bucket_name = cloud_event.data['bucket']
    object_name = cloud_event.data['name']

    # Define output bucket
    output_bucket = 'vertex-translation-output'

    # Create the payload to send to Cloud Run service, base64 encode the data
    payload_data = {
        "bucket": bucket_name,
        "name": object_name,
        "output_bucket": output_bucket
    }

    # Convert the payload to JSON and base64 encode it
    encoded_data = base64.b64encode(json.dumps(payload_data).encode('utf-8')).decode('utf-8')

    # Create the event payload with attributes and the base64-encoded data
    event_payload = {
        "message": {
            "attributes": {
                "bucketId": bucket_name,
                "objectId": object_name,
                "eventType": "OBJECT_FINALIZE"
            },
            "data": encoded_data
        }
    }

    print(f"Event Payload: {event_payload}")
    
    try:
        # Send the event data to the Cloud Run service
        response = requests.post(
            target_cloud_run_url,
            json=event_payload,
            headers={"Content-Type": "application/json"}
        )
        
        # Check the response status
        if response.status_code == 200:
            print("Event successfully forwarded to Cloud Run service.")
        else:
            print(f"Failed to forward event. Status code: {response.status_code}, Response: {response.text}")
    except Exception as e:
        print(f"Error during forwarding event: {e}")
