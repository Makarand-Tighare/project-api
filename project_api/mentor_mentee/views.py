import requests
import json
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from .models import Participant
from .serializers import ParticipantSerializer
from collections import defaultdict
from itertools import cycle

@api_view(['POST'])
def create_participant(request):
    if request.method == 'POST':
        serializer = ParticipantSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response({'msg': 'Details saved successfully'}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET'])
def list_participants(request):
    if request.method == 'GET':
        participants = Participant.objects.all()
        serializer = ParticipantSerializer(participants, many=True)
        return Response(serializer.data)

# Function to get LinkedIn user profile
def get_linkedin_user_id(access_token):
    try:
        # LinkedIn API URL for fetching user profile
        url = 'https://api.linkedin.com/v2/me'

        # Set up headers
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }

        # Send request to LinkedIn API
        response = requests.get(url, headers=headers, timeout=5)  # 5 seconds timeout

        # Handle LinkedIn API response
        if response.status_code == 200:
            data = response.json()
            # Return LinkedIn user ID or any other required information
            return data.get('id'), None
        else:
            error_data = response.json()
            return None, error_data.get('message', 'Unknown error')

    except requests.exceptions.Timeout:
        return None, 'Request timed out'
    except Exception as e:
        return None, str(e)

# Function to create a post on LinkedIn
@api_view(['POST'])
def linkedin_post(request):
    try:
        # Extract access token and post content from request body
        data = request.data
        access_token = data.get('accessToken')
        content = data.get('content')

        # Fetch user ID dynamically
        user_id, error = get_linkedin_user_id(access_token)
        if error:
            return Response({
                'error': 'Failed to fetch LinkedIn user ID',
                'details': error
            }, status=status.HTTP_400_BAD_REQUEST)

        # LinkedIn API endpoint for UGC posts
        url = 'https://api.linkedin.com/v2/ugcPosts'

        # Post body data
        body = {
            "author": f"urn:li:person:{user_id}",  # Dynamically fetched user ID
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {
                        "text": content,  # Text for your LinkedIn post
                    },
                    "shareMediaCategory": "NONE"
                }
            },
            "visibility": {
                "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
            }
        }

        # Send POST request to LinkedIn API
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }

        response = requests.post(url, headers=headers, data=json.dumps(body))

        # Check for successful response
        if response.status_code in [200, 201]:
            return Response({
                'message': 'Post created successfully!',
                'data': response.json()
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                'error': 'Failed to create post',
                'details': response.json()
            }, status=response.status_code)

    except Exception as e:
        return Response({
            'error': 'An error occurred',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

def evaluate_student(student):
    """Score students dynamically based on their achievements."""
    score = 0
    
    # Higher semester students get preference for being mentors
    if int(student['semester']) >= 5:
        score += (int(student['semester']) - 4) * 10
    
    # Previous mentoring experience
    if student['previous_mentoring_experience']:
        score += 10

    # Score based on hackathon participation
    if student['hackathon_participation'] == 'National':
        score += 15 + int(student['number_of_wins']) * 5  # Wins add more points
    elif student['hackathon_participation'] == 'International':
        score += 20 + int(student['number_of_wins']) * 10

    # Score for coding competitions
    if student['coding_competitions_participate'] == 'yes':
        score += 15 + int(student['number_of_coding_competitions']) * 5  # Add points for each competition

    # Add CGPA/SGPA to the score (scaled to 10 points)
    score += float(student['cgpa']) * 2  # Scale CGPA to a maximum of 20
    score += float(student['sgpa']) * 1.5  # Scale SGPA to a maximum of 15
    
    # Extra points for internship experience
    if student['internship_experience'] == 'yes':
        score += 20
    
    # Score for seminars and workshops
    if student['seminars_or_workshops_attended'] == 'yes':
        score += 10
    
    # Extra points for extracurricular activities
    if student['extracurricular_activities'] == 'yes':
        score += 10

    return score

def has_common_interests(mentor, mentee):
    """Check if mentor and mentee share common tech stack or areas of interest."""
    mentor_tech_stack = set(mentor['tech_stack'].split(', '))
    mentee_tech_stack = set(mentee['tech_stack'].split(', '))
    mentor_interests = set(mentor['areas_of_interest'].split(', '))
    mentee_interests = set(mentee['areas_of_interest'].split(', '))
    
    return bool(mentor_tech_stack & mentee_tech_stack or mentor_interests & mentee_interests)

def match_mentors_mentees(students):
    """Match mentors with mentees dynamically with fallback matching."""
    mentors = []
    mentees = []
    matches = []

    # Separate students into mentor and mentee lists based on semester
    for student in students:
        if int(student['semester']) >= 5:
            mentors.append(student)
        else:
            mentees.append(student)  # Only students with semester < 5 should be mentees

    # Sort mentors by their evaluated score
    mentors = sorted(mentors, key=evaluate_student, reverse=True)

    # Dictionary to count mentees per mentor (max 3 mentees per mentor)
    mentor_mentee_count = defaultdict(int)

    # First match based on common tech stack or areas of interest
    unmatched_mentees = []
    for mentee in mentees:
        matched = False
        for mentor in mentors:
            # Ensure that the mentor and mentee are not the same person
            if mentor_mentee_count[mentor['name']] < 3 and mentor['name'] != mentee['name'] and has_common_interests(mentor, mentee):
                matches.append({
                    "mentor": {
                        "name": mentor['name'],
                        "registration_no": mentor['registration_no'],
                        "semester": mentor['semester']
                    },
                    "mentee": {
                        "name": mentee['name'],
                        "registration_no": mentee['registration_no'],
                        "semester": mentee['semester']
                    }
                })
                mentor_mentee_count[mentor['name']] += 1
                matched = True
                break

        if not matched:
            unmatched_mentees.append(mentee)

    # Fallback: Assign remaining unmatched mentees to mentors
    if unmatched_mentees:
        mentor_cycle = cycle(mentors)  # Cycle through mentors to ensure even distribution
        for mentee in unmatched_mentees:
            mentor = next(mentor_cycle)
            while mentor_mentee_count[mentor['name']] >= 3:
                mentor = next(mentor_cycle)
            matches.append({
                "mentor": {
                    "name": mentor['name'],
                    "registration_no": mentor['registration_no'],
                    "semester": mentor['semester']
                },
                "mentee": {
                    "name": mentee['name'],
                    "registration_no": mentee['registration_no'],
                    "semester": mentee['semester']
                }
            })
            mentor_mentee_count[mentor['name']] += 1

    return matches

@api_view(['GET'])
def match_participants(request):
    """Endpoint to trigger mentor-mentee matching."""
    participants = Participant.objects.all()
    serializer = ParticipantSerializer(participants, many=True)
    students = serializer.data
    
    if not students:
        return Response({"error": "No participants found"}, status=status.HTTP_404_NOT_FOUND)

    matches = match_mentors_mentees(students)
    return Response({"matches": matches})