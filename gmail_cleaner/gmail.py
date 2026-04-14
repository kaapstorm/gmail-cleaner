from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


def build_service(creds: Credentials):
    return build('gmail', 'v1', credentials=creds)


def get_user_email(creds: Credentials) -> str:
    service = build_service(creds)
    profile = service.users().getProfile(userId='me').execute()
    return profile['emailAddress']


def list_user_labels(creds: Credentials) -> list[dict]:
    service = build_service(creds)
    response = service.users().labels().list(userId='me').execute()
    user_labels = [
        label
        for label in response.get('labels', [])
        if label.get('type') == 'user'
    ]
    return sorted(user_labels, key=lambda label: label['name'])
