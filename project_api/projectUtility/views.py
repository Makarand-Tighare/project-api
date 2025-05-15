import os
import requests
import json
from rest_framework.response import Response
from rest_framework import status
from rest_framework.views import APIView
from account.models import Student
from django.http import HttpResponse, JsonResponse, HttpResponseRedirect
from django.urls import reverse
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from rest_framework.permissions import AllowAny
from google.auth.transport.requests import Request
from django.views.decorators.http import require_http_methods

# Configure the OAuth2 client
CLIENT_SECRETS_FILE = os.path.join(settings.BASE_DIR, "client_secret.json")
SCOPES = ['https://www.googleapis.com/auth/calendar.events']
REDIRECT_URI = "https://vidyasangam.duckdns.org/api/utility/callback"

os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

# OAuth 2.0 flow setup
flow = Flow.from_client_secrets_file(CLIENT_SECRETS_FILE, scopes=SCOPES)
flow.redirect_uri = REDIRECT_URI

def credentials_to_dict(credentials):
    return {
        'token': credentials.token,
        'refresh_token': credentials.refresh_token,
        'token_uri': credentials.token_uri,
        'client_id': credentials.client_id,
        'client_secret': credentials.client_secret,
        'scopes': credentials.scopes
    }

class LinkedInAuthView(APIView):
    """
    View to handle LinkedIn authentication. It exchanges the authorization code
    for an access token and saves the access token for the authenticated user.
    """

    def post(self, request):
        # Retrieve LinkedIn OAuth configurations from environment variables
        client_id = os.environ.get('LINKEDIN_CLIENT_ID')
        client_secret = os.environ.get('LINKEDIN_CLIENT_SECRET')
        redirect_uri = os.environ.get('LINKEDIN_REDIRECT_URI')
        token_url = 'https://www.linkedin.com/oauth/v2/accessToken'

        # Validate the incoming data
        authorization_code = request.data.get('authorization_code')
        state_code = request.data.get('state')
        user_email = request.data.get('email')

        if not authorization_code:
            return Response({'error': 'Authorization code is required'}, status=status.HTTP_400_BAD_REQUEST)

        # Exchange authorization code for access token
        token_params = {
            'grant_type': 'authorization_code',
            'code': authorization_code,
            'redirect_uri': redirect_uri,
            'client_id': client_id,
            'client_secret': client_secret,
        }

        # Make the request to LinkedIn to get the access token
        response = requests.post(token_url, data=token_params)

        if response.status_code == 200:
            token_data = response.json()
            access_token = token_data['access_token']
            
            # Try to get the user based on the provided email
            try:
                user = Student.objects.get(email=user_email)
                user.linkedin_access_token = access_token
                user.save()
                
                # Successful response after saving the access token
                return Response({'msg': 'LinkedIn authentication successful'}, status=status.HTTP_200_OK)
            except Student.DoesNotExist:
                # Error if the user is not found in the system
                return Response({'error': 'Please log in before connecting to LinkedIn'},
                                status=status.HTTP_400_BAD_REQUEST)
        else:
            # Error response if unable to obtain the access token from LinkedIn
            return Response({'error': 'Error obtaining access token', 'details': response.json()},
                            status=status.HTTP_400_BAD_REQUEST)


class IndexView(APIView):
    """
    View to display a welcome message for Google Meet Integration.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        return JsonResponse({"message": "Google Meet Integration!"})


class AuthorizeView(APIView):
    """
    View to handle the authorization flow with Google OAuth2.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        authorization_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true'
        )
        request.session['state'] = state
        
        # Instead of redirecting, return the URL for the frontend to use
        return JsonResponse({
            'authorization_url': authorization_url,
            'state': state
        })


class CheckAuthView(APIView):
    """
    View to check if the user is already authorized.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        # Check for credentials in the database if user is authenticated
        if request.user.is_authenticated:
            user = request.user
            if user.google_token:
                return JsonResponse({'is_authorized': True, 'storage': 'database'})
        
        # Fall back to checking session
        if 'credentials' in request.session:
            return JsonResponse({'is_authorized': True, 'storage': 'session'})
            
        return JsonResponse({'is_authorized': False})


class CallbackView(APIView):
    """
    View to handle the callback from Google's OAuth2.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        if 'state' not in request.session:
            return JsonResponse({"error": "Session state not found"}, status=400)
        if request.session['state'] != request.GET.get('state'):
            return JsonResponse({"error": "State mismatch error"}, status=400)

        flow.fetch_token(authorization_response=request.build_absolute_uri())
        credentials = flow.credentials
        
        # Store the credentials in the database if user is authenticated
        if request.user.is_authenticated:
            user = request.user
            user.google_token = credentials.token
            user.google_refresh_token = credentials.refresh_token
            user.google_token_uri = credentials.token_uri
            
            # Store expiry time if available
            if hasattr(credentials, 'expiry'):
                user.google_token_expiry = credentials.expiry
            
            # Store scopes as a comma-separated string
            if credentials.scopes:
                user.google_scopes = ','.join(credentials.scopes)
            
            user.save()
        else:
            # For non-authenticated users, fall back to session storage
            request.session['credentials'] = credentials_to_dict(credentials)
            request.session['credentials_temporary'] = True  # Flag to indicate temporary storage

        return HttpResponse("""
            <html>
            <head>
                <style>
                    body {
                        font-family: 'Arial', sans-serif;
                        background-color: #f0f8ff;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        height: 100vh;
                        margin: 0;
                    }
                    .container {
                        background-color: #ffffff;
                        border-radius: 8px;
                        box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
                        padding: 20px;
                        max-width: 400px;
                        text-align: center;
                    }
                    h2 {
                        color: #4CAF50;
                    }
                    p {
                        color: #333333;
                    }
                    button {
                        background-color: #4CAF50;
                        color: white;
                        border: none;
                        padding: 10px 20px;
                        font-size: 16px;
                        border-radius: 4px;
                        cursor: pointer;
                    }
                    button:hover {
                        background-color: #45a049;
                    }
                </style>
            </head>
            <body>
                <div class="container">
                    <h2>Authentication Successful</h2>
                    <p>You can now safely close this page.</p>
                    <button onclick="window.close()">Close Page</button>
                </div>
            </body>
            </html>
        """)


class CreateMeetView(APIView):
    permission_classes = [AllowAny]

    @csrf_exempt
    def post(self, request):
        credentials = None
        
        # First check if user is authenticated to get credentials from database
        if request.user.is_authenticated:
            user = request.user
            # Check if user has Google credentials
            if user.google_token:
                # Create credentials object from database values
                credentials = Credentials(
                    token=user.google_token,
                    refresh_token=user.google_refresh_token,
                    token_uri=user.google_token_uri,
                    client_id=flow.client_config['client_id'],
                    client_secret=flow.client_config['client_secret'],
                    scopes=user.google_scopes.split(',') if user.google_scopes else []
                )
        
        # Fall back to session if not authenticated or no credentials in database
        if not credentials and 'credentials' in request.session:
            credentials_data = request.session.get('credentials')
            credentials = Credentials(**credentials_data)
            
        # If no credentials found anywhere, return auth URL instead of redirecting
        if not credentials:
            authorization_url, state = flow.authorization_url(
                access_type='offline',
                include_granted_scopes='true'
            )
            request.session['state'] = state
            return JsonResponse({
                'authenticated': False,
                'authorization_url': authorization_url,
                'state': state
            })

        # Check if credentials are expired and refresh if needed
        if credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
            
            # Update the refreshed credentials
            if request.user.is_authenticated and hasattr(request.user, 'google_token'):
                request.user.google_token = credentials.token
                if hasattr(credentials, 'expiry'):
                    request.user.google_token_expiry = credentials.expiry
                request.user.save()
            else:
                # Update session if using session-based auth
                request.session['credentials'] = credentials_to_dict(credentials)

        service = build('calendar', 'v3', credentials=credentials)

        # Create a new Google Meet event
        event = {
            'summary': request.data.get('summary', 'Meeting'),
            'description': request.data.get('description', 'Meeting created via API'),
            'start': {
                'dateTime': request.data.get('start_time', '2024-10-15T10:00:00Z'),
                'timeZone': request.data.get('timezone', 'UTC'),
            },
            'end': {
                'dateTime': request.data.get('end_time', '2024-10-15T11:00:00Z'),
                'timeZone': request.data.get('timezone', 'UTC'),
            },
            'conferenceData': {
                'createRequest': {
                    'conferenceSolutionKey': {'type': 'hangoutsMeet'},
                    'requestId': request.data.get('request_id', 'meeting_request'),
                },
            },
            'attendees': request.data.get('attendees', [{'email': 'vidyasangam.edu@gmail.com'}]),
        }

        try:
            event = service.events().insert(calendarId='primary', body=event, conferenceDataVersion=1).execute()
            meet_link = event.get('hangoutLink')
            meeting_id = meet_link.split('/')[-1] if meet_link else None
            
            return JsonResponse({
                'authenticated': True,
                'meet_link': meet_link,
                'meeting_id': meeting_id,
                'event_id': event.get('id')
            })
        except Exception as e:
            return JsonResponse({
                'error': 'Failed to create meeting',
                'details': str(e)
            }, status=500)