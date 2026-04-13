from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


def build_service(creds: Credentials):
    return build('gmail', 'v1', credentials=creds)


def get_user_email(creds: Credentials) -> str:
    service = build_service(creds)
    profile = service.users().getProfile(userId='me').execute()
    return profile['emailAddress']
