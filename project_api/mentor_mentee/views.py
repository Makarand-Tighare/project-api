import requests
import json
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from .models import Participant, MentorMenteeRelationship, Session, QuizResult, Badge, ParticipantBadge, Department, FeedbackSettings, MentorFeedback, ApplicationFeedback, ParticipantHistory
from .serializers import ParticipantSerializer, SessionSerializer, MentorInfoSerializer, MenteeInfoSerializer, QuizResultSerializer, BadgeSerializer, ParticipantBadgeSerializer, FeedbackSettingsSerializer, MentorFeedbackSerializer, ApplicationFeedbackSerializer, ProfileSerializer, ParticipantListSerializer
from collections import defaultdict
from itertools import cycle
from django.db import transaction
from rest_framework.permissions import IsAuthenticated  # or AllowAny if public
import os
from dotenv import load_dotenv
import datetime
from django.db import models
from account.models import Student  # Import Student model for email lookup
from django.utils import timezone
from django.http import HttpResponse, Http404
import base64
from datetime import timedelta
from django.db.models.functions import TruncDate
from django.db.models import Count, Q, Avg

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY")  # Use .env or fallback

# Helper function to get email from registration number
def get_email_by_registration_no(registration_no):
    """Get a student's email by their registration number"""
    try:
        # Try multiple approaches to find the student
        # First try getting Student by reg_no
        student = Student.objects.filter(reg_no=registration_no).first()
        if student:
            return student.email
            
        # If not found, try searching by email directly (in case registration_no is actually an email)
        if '@' in registration_no:
            student = Student.objects.filter(email=registration_no).first()
            if student:
                return student.email
                
        # If no matching student found, return the registration_no as fallback
        print(f"No student found with registration number or email {registration_no}")
        return registration_no
    except Exception as e:
        # Log the error and return registration_no as fallback
        print(f"Error finding email for registration number {registration_no}: {str(e)}")
        return registration_no

@api_view(['POST'])
def create_participant(request):
    if request.method == 'POST':
        # Extract file objects before copying request.data
        files = {}
        for field_name, field_value in request.data.items():
            if hasattr(field_value, 'read') and callable(field_value.read):
                files[field_name] = field_value
                
        # Create a mutable copy of request data without file objects
        data = {}
        for key, value in request.data.items():
            if key not in files:
                data[key] = value
                
        # Ensure the approval status is set to pending for new participants
        data['approval_status'] = 'pending'  # Force pending status for all new registrations
        
        # Check if participant already exists
        try:
            existing_participant = Participant.objects.get(registration_no=data['registration_no'])
            
            # Check if this is a re-registration after archival
            is_archived = (
                not existing_participant.tech_stack and 
                not existing_participant.areas_of_interest and 
                existing_participant.approval_status == 'pending'
            )
            
            if is_archived:
                # This is a re-registration after archival, update the existing record
                serializer = ParticipantSerializer(existing_participant, data=data)
            else:
                # This is a duplicate registration
                return Response({
                    'error': 'Registration number already exists',
                    'message': 'A participant with this registration number is already registered'
                }, status=status.HTTP_400_BAD_REQUEST)
        except Participant.DoesNotExist:
            # This is a new registration
            serializer = ParticipantSerializer(data=data)
            
        if serializer.is_valid():
            participant = serializer.save()
            
            # Handle file uploads
            for field_name, file_obj in files.items():
                if field_name == 'proof_of_research_publications':
                    participant.proof_of_research_publications = file_obj.read()
                elif field_name == 'proof_of_hackathon_participation':
                    participant.proof_of_hackathon_participation = file_obj.read()
                elif field_name == 'proof_of_coding_competitions':
                    participant.proof_of_coding_competitions = file_obj.read()
                elif field_name == 'proof_of_academic_performance':
                    participant.proof_of_academic_performance = file_obj.read()
                elif field_name == 'proof_of_internships':
                    participant.proof_of_internships = file_obj.read()
                elif field_name == 'proof_of_extracurricular_activities':
                    participant.proof_of_extracurricular_activities = file_obj.read()
            
            participant.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET'])
def list_participants(request):
    """List all participants with optional filtering"""
    try:
        # Get query parameters
        status_filter = request.query_params.get('status', 'active')
        approval_filter = request.query_params.get('approval_status')
        department_id = request.query_params.get('department_id')
        
        # Base query - only show active participants who haven't been archived
        participants = Participant.objects.filter(
            status='active',  # Only active participants
            mentoring_preferences__isnull=False,  # Must have mentoring preferences set
        ).exclude(
            mentoring_preferences=''  # Exclude empty string preferences
        )
        
        # Apply filters if provided
        if approval_filter:
            participants = participants.filter(approval_status=approval_filter)
            
        # Check if user is a department admin
        if hasattr(request.user, 'is_department_admin') and request.user.is_department_admin:
            # If user is department admin, only show participants from their department
            if request.user.department:
                participants = participants.filter(department=request.user.department)
        elif department_id:
            # If not department admin but department_id provided, filter by that
            participants = participants.filter(department_id=department_id)
            
        # Serialize the data
        serializer = ParticipantListSerializer(participants, many=True)
        
        return Response({
            'count': participants.count(),
            'participants': serializer.data
        })
        
    except Exception as e:
        return Response({
            'error': 'Failed to fetch participants',
            'details': str(e)
        }, status=500)

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

def generate_linkedin_post_content(badge_name, achievement_details):
    """
    Generate LinkedIn post content using Gemini API for badge achievements
    """
    try:
        # Gemini API endpoint
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
        
        # Create prompt for Gemini
        prompt = f"""Create a professional LinkedIn post announcing the achievement of the {badge_name} badge. 
        The post should be engaging, highlight the achievement, and be suitable for professional networking.
        Here are the details of the achievement: {achievement_details}
        
        The post should:
        1. Be professional and engaging
        2. Include relevant hashtags
        3. Be between 100-200 words
        4. Highlight the significance of the achievement
        5. Be suitable for a professional networking platform
        
        Format the response as a single paragraph with hashtags at the end."""
        
        # Request body
        data = {
            "contents": [{
                "parts": [{"text": prompt}]
            }],
            "generationConfig": {
                "temperature": 0.7,
                "topP": 0.8,
                "topK": 40
            }
        }
        
        # Send request to Gemini API
        headers = {'Content-Type': 'application/json'}
        response = requests.post(url, headers=headers, json=data, timeout=30)
        
        # Check response status
        if response.status_code == 200:
            # Parse response and extract generated text
            response_data = response.json()
            generated_text = response_data['candidates'][0]['content']['parts'][0]['text']
            return generated_text, None
        else:
            return None, f"Gemini API error: {response.status_code}, {response.text}"
        
    except Exception as e:
        return None, str(e)

@api_view(['POST'])
def linkedin_post(request):
    try:
        # Extract data from request
        data = request.data
        access_token = data.get('accessToken')
        custom_content = data.get('content')  # User-provided content (optional)
        participant_id = data.get('participant_id')  # ID of the participant who owns the badge
        badge_id = data.get('badge_id')  # ID of the badge being shared (optional)
        
        # Check if user is providing custom content or wants us to generate it
        if custom_content:
            content = custom_content
        else:
            badge_name = data.get('badgeName')
            achievement_details = data.get('achievementDetails')
            
            if not badge_name or not achievement_details:
                return Response({
                    'error': 'Either provide content directly or badge name and achievement details'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Generate content using Gemini
            content, error = generate_linkedin_post_content(badge_name, achievement_details)
            if error:
                return Response({
                    'error': 'Failed to generate post content',
                    'details': error
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
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
            "author": f"urn:li:person:{user_id}",
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {
                        "text": content,
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
            # If badge_id and participant_id are provided, mark the badge as shared on LinkedIn
            badge_shared = False
            if badge_id and participant_id:
                try:
                    participant = Participant.objects.get(registration_no=participant_id)
                    participant_badge = ParticipantBadge.objects.get(participant=participant, badge__id=badge_id)
                    participant_badge.linkedin_shared = True
                    participant_badge.save()
                    badge_shared = True
                except (Participant.DoesNotExist, ParticipantBadge.DoesNotExist):
                    # If no badge found, continue without error since the post was still successful
                    pass
            
            response_data = {
                'message': 'Post created successfully!',
                'data': response.json(),
                'posted_content': content
            }
            
            if badge_shared:
                response_data['badge_shared'] = True
                
            return Response(response_data, status=status.HTTP_200_OK)
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
    # First check approval status - only approved participants can be mentors
    if 'approval_status' in student and student['approval_status'] != 'approved':
        return -1000  # Non-approved participants cannot be mentors
    
    # Also check if deactivated - deactivated participants cannot be mentors either
    if 'status' in student and student['status'] == 'deactivated':
        return -1000  # Deactivated participants cannot be mentors
    
    score = 0
    
    # Higher semester students get preference for being mentors
    # Give equal preference to students in semesters 6-8
    semester = int(student['semester'])
    if semester >= 6 and semester <= 8:
        score += 30  # Fixed score for semesters 6-8
    
    # Previous mentoring experience is valuable
    if student['previous_mentoring_experience'] and student['previous_mentoring_experience'] != 'nan':
        score += 15
    
    # Research publications (significant boost)
    if student['published_research_papers'] and student['published_research_papers'] != 'nan':
        score += 25

    # Hackathon participation (major factor)
    if student['hackathon_participation'] and student['hackathon_participation'] != 'nan':
        if student['hackathon_participation'] == 'International':
            score += 25
        elif student['hackathon_participation'] == 'National':
            score += 20
        elif student['hackathon_participation'] == 'College':
            score += 15
            
        # Add points for wins
        if student['number_of_wins'] and student['number_of_wins'] != 'nan':
            score += int(student['number_of_wins']) * 5
            
        # Add points for hackathon role
        if student['hackathon_role'] == 'Team Leader':
            score += 10
        elif student['hackathon_role'] == 'Participant':
            score += 5

    # Coding competitions are important for technical skill assessment
    if student['coding_competitions_participate'] == 'Yes':
        score += 20
        if student['number_of_coding_competitions'] and student['number_of_coding_competitions'] != 'nan':
            score += int(student['number_of_coding_competitions']) * 3

    # CGPA/SGPA still matters but less weight
    if student['cgpa'] and student['cgpa'] != 'nan':
        score += float(student['cgpa'])
    if student['sgpa'] and student['sgpa'] != 'nan':
        score += float(student['sgpa'])
    
    # Internship experience demonstrates real-world application
    if student['internship_experience'] == 'Yes':
        score += 15
        if student['number_of_internships'] and student['number_of_internships'] != 'nan':
            score += int(student['number_of_internships']) * 5
    
    # Seminars and workshops show continuous learning
    if student['seminars_or_workshops_attended'] == 'Yes':
        score += 5
    
    # Extracurricular activities show well-rounded individuals
    if student['extracurricular_activities'] == 'Yes':
        score += 5
        
    # Badge and Super Mentor factors (NEW)
    
    # More badges means higher mentor preference - progressive scale
    if 'badges_earned' in student and student['badges_earned']:
        badge_count = int(student['badges_earned'])
        # Progressive scoring: each badge adds more points than the previous one
        # 1 badge: 10pts, 2 badges: 25pts, 3 badges: 45pts, 4 badges: 70pts, 5+ badges: 100pts
        badge_scores = {
            1: 10,
            2: 25,
            3: 45,
            4: 70,
            5: 100,
        }
        
        if badge_count <= 5:
            score += badge_scores.get(badge_count, 0)
        else:
            # For more than 5 badges, add 100 + 15 points per additional badge
            score += 100 + (badge_count - 5) * 15
        
    # Super mentors get a significant boost
    if 'is_super_mentor' in student and student['is_super_mentor']:
        score += 50  # Significant boost for super mentors
    
    # Leaderboard points add directly to score with a multiplier
    if 'leaderboard_points' in student and student['leaderboard_points']:
        score += int(student['leaderboard_points']) * 0.5  # Half weight of actual points
    
    return score

def has_common_interests(mentor, mentee):
    """
    Check if mentor and mentee share common tech stack or areas of interest.
    Takes into account interest priorities of both mentor and mentee.
    Returns tuple of (common_tech, common_interests, preference_score)
    """
    # Handle possible nan or empty values
    mentor_tech = mentor.get('tech_stack', '').split(',') if mentor.get('tech_stack') else []
    mentee_tech = mentee.get('tech_stack', '').split(',') if mentee.get('tech_stack') else []
    mentor_interest = mentor.get('areas_of_interest', '').split(',') if mentor.get('areas_of_interest') else []
    mentee_interest = mentee.get('areas_of_interest', '').split(',') if mentee.get('areas_of_interest') else []
    
    # Clean up the lists - strip whitespace and remove empty strings
    mentor_tech = [tech.strip() for tech in mentor_tech if tech.strip()]
    mentee_tech = [tech.strip() for tech in mentee_tech if tech.strip()]
    mentor_interests = [interest.strip() for interest in mentor_interest if interest.strip()]
    mentee_interests = [interest.strip() for interest in mentee_interest if interest.strip()]
    
    # Get prioritized interests
    mentor_pref1 = mentor.get('interest_preference1', '').strip()
    mentor_pref2 = mentor.get('interest_preference2', '').strip()
    mentor_pref3 = mentor.get('interest_preference3', '').strip()
    mentee_pref1 = mentee.get('interest_preference1', '').strip()
    mentee_pref2 = mentee.get('interest_preference2', '').strip()
    mentee_pref3 = mentee.get('interest_preference3', '').strip()
    
    # Find common tech stack and interests
    common_tech = []
    for m_tech in mentor_tech:
        for s_tech in mentee_tech:
            if m_tech.lower() in s_tech.lower() or s_tech.lower() in m_tech.lower():
                common_tech.append((m_tech, s_tech))
    
    common_interests = []
    for m_int in mentor_interests:
        for s_int in mentee_interests:
            if m_int.lower() in s_int.lower() or s_int.lower() in m_int.lower():
                common_interests.append((m_int, s_int))
    
    # Calculate preference match score (higher is better)
    preference_score = 0
    
    # Check if mentor's preferences match mentee's interests/tech
    if mentor_pref1:
        if any(mentor_pref1.lower() in interest.lower() for interest in mentee_interests) or \
           any(mentor_pref1.lower() in tech.lower() for tech in mentee_tech):
            preference_score += 10  # Highest priority match
    if mentor_pref2:
        if any(mentor_pref2.lower() in interest.lower() for interest in mentee_interests) or \
           any(mentor_pref2.lower() in tech.lower() for tech in mentee_tech):
            preference_score += 6   # Medium priority match
    if mentor_pref3:
        if any(mentor_pref3.lower() in interest.lower() for interest in mentee_interests) or \
           any(mentor_pref3.lower() in tech.lower() for tech in mentee_tech):
            preference_score += 3   # Lower priority match
    
    # Check if mentee's preferences match mentor's interests/tech
    if mentee_pref1:
        if any(mentee_pref1.lower() in interest.lower() for interest in mentor_interests) or \
           any(mentee_pref1.lower() in tech.lower() for tech in mentor_tech):
            preference_score += 10  # Highest priority match
    if mentee_pref2:
        if any(mentee_pref2.lower() in interest.lower() for interest in mentor_interests) or \
           any(mentee_pref2.lower() in tech.lower() for tech in mentor_tech):
            preference_score += 6   # Medium priority match
    if mentee_pref3:
        if any(mentee_pref3.lower() in interest.lower() for interest in mentor_interests) or \
           any(mentee_pref3.lower() in tech.lower() for tech in mentor_tech):
            preference_score += 3   # Lower priority match
    
    return common_tech, common_interests, preference_score

def calculate_match_quality(mentor, mentee):
    """Calculate the match quality score between a mentor and mentee"""
    quality_score = 0
    
    # Consider mentor's historical performance
    if mentor.get('historical_data'):
        mentor_history = mentor['historical_data']
        if mentor_history['was_mentor'] and mentor_history['mentor_rating']:
            quality_score += min(mentor_history['mentor_rating'] / 2, 2)  # Max 2 points for good rating
        if mentor_history['sessions_conducted'] > 0:
            quality_score += min(mentor_history['sessions_conducted'] / 5, 1)  # Max 1 point for session experience
    
    # Consider mentee's historical performance
    if mentee.get('historical_data'):
        mentee_history = mentee['historical_data']
        if mentee_history['was_mentee'] and mentee_history['mentee_rating']:
            quality_score += min(mentee_history['mentee_rating'] / 2, 2)  # Max 2 points for good rating
        if mentee_history['sessions_attended'] > 0:
            quality_score += min(mentee_history['sessions_attended'] / 5, 1)  # Max 1 point for session attendance
    
    # Consider badges and super mentor status
    if mentor.get('badges_earned'):
        badge_count = int(mentor['badges_earned'])
        quality_score += min(badge_count * 0.5, 2)  # Max 2 points for badges
    
    if mentor.get('is_super_mentor'):
        quality_score += 2  # Bonus points for super mentors
    
    return quality_score

def match_mentors_mentees(students):
    """Match mentors and mentees based on various criteria"""
    # Separate mentors and mentees
    mentors = [s for s in students if s['mentoring_preferences'] == 'mentor']
    mentees = [s for s in students if s['mentoring_preferences'] == 'mentee']
    
    # If no mentors or mentees, return empty matches
    if not mentors or not mentees:
        return {
            "matches": [],
            "unmatched_mentees": mentees,
            "unmatched_mentors": mentors,
            "statistics": {
                "total_participants": len(students),
                "total_mentors": len(mentors),
                "total_mentees": len(mentees),
                "matches_made": 0
            }
        }
    
    # Get historical data for all participants
    registration_nos = [s['registration_no'] for s in students]
    historical_data = {
        h.registration_no: h for h in ParticipantHistory.objects.filter(
            registration_no__in=registration_nos
        )
    }
    
    # Add historical data to student profiles
    for student in students:
        reg_no = student['registration_no']
        if reg_no in historical_data:
            history = historical_data[reg_no]
            student['historical_data'] = {
                'total_badges': history.total_badges_earned,
                'total_points': history.total_leaderboard_points,
                'quizzes_completed': history.total_quizzes_completed,
                'average_quiz_score': history.average_quiz_score,
                'was_mentor': history.was_mentor,
                'was_mentee': history.was_mentee,
                'mentor_rating': history.mentor_rating,
                'mentee_rating': history.mentee_rating,
                'sessions_attended': history.sessions_attended,
                'sessions_conducted': history.sessions_conducted
            }
        else:
            student['historical_data'] = None
    
    # Dictionary to track how many mentees each mentor has
    mentor_mentee_count = {mentor['registration_no']: 0 for mentor in mentors}
    MAX_MENTEES_PER_MENTOR = 4
    
    # List to store all matches
    matches = []
    unmatched_mentees = []
    
    # For each mentee, find the best matching mentor
    for mentee in mentees:
        best_match = None
        best_score = -1
        best_common_tech = []
        best_common_interests = []
        best_preference_score = 0
        
        for mentor in mentors:
            # Skip if mentor already has max mentees
            if mentor_mentee_count[mentor['registration_no']] >= MAX_MENTEES_PER_MENTOR:
                continue
                
            # Skip if mentor and mentee are the same person
            if mentor['registration_no'] == mentee['registration_no']:
                continue
                
            # Check if they have common interests and calculate match quality
            common_tech, common_interests, preference_score = has_common_interests(mentor, mentee)
            
            # Calculate overall match quality
            match_quality = calculate_match_quality(mentor, mentee)
            
            # Add bonus for common interests
            if common_tech or common_interests:
                match_quality += len(common_tech) + len(common_interests)
            
            # Add preference score
            match_quality += preference_score
            
            # If this is the best match so far, store it
            if match_quality > best_score:
                best_score = match_quality
                best_match = mentor
                best_common_tech = common_tech
                best_common_interests = common_interests
                best_preference_score = preference_score
        
        # If we found a match, add it to our matches list
        if best_match and best_score > 0:
            matches.append({
                "mentor": {
                    "name": best_match['name'],
                    "registration_no": best_match['registration_no'],
                    "semester": best_match['semester'],
                    "branch": best_match['branch'],
                    "tech_stack": best_match['tech_stack'],
                    "department_id": best_match.get('department_id')
                },
                "mentee": {
                    "name": mentee['name'],
                    "registration_no": mentee['registration_no'],
                    "semester": mentee['semester'],
                    "branch": mentee['branch'],
                    "tech_stack": mentee['tech_stack'],
                    "department_id": mentee.get('department_id')
                },
                "match_quality": best_score,
                "common_tech": best_common_tech,
                "common_interests": best_common_interests,
                "preference_score": best_preference_score
            })
            mentor_mentee_count[best_match['registration_no']] += 1
        else:
            unmatched_mentees.append(mentee)
    
    # Get list of mentors who still have capacity
    available_mentors = [
        mentor for mentor in mentors 
        if mentor_mentee_count[mentor['registration_no']] < MAX_MENTEES_PER_MENTOR
    ]
    
    return {
        "matches": matches,
        "unmatched_mentees": unmatched_mentees,
        "unmatched_mentors": available_mentors,
        "statistics": {
            "total_participants": len(students),
            "total_mentors": len(mentors),
            "total_mentees": len(mentees),
            "matches_made": len(matches),
            "mentees_unmatched": len(unmatched_mentees),
            "mentors_with_capacity": len(available_mentors)
        }
    }

@api_view(['GET'])
def match_participants(request):
    """Endpoint to trigger mentor-mentee matching for new/unmatched participants only."""
    # Get the requesting user for department filtering
    user = request.user
    department_filter = None
    
    # If this is a department admin, they should only match participants from their department
    if hasattr(user, 'is_department_admin') and user.is_department_admin and user.department:
        department_filter = user.department
        print(f"Department admin matching for department: {department_filter.name}")
        
        # Check if there are pending approvals for this department
        pending_approvals_count = Participant.objects.filter(
            approval_status='pending',
            department=department_filter,
            # Only count participants who have re-registered (have tech stack and interests)
            tech_stack__isnull=False,
            tech_stack__gt='',
            areas_of_interest__isnull=False,
            areas_of_interest__gt=''
        ).count()
        
        if pending_approvals_count > 0:
            return Response({
                "error": "Approval required before matching",
                "message": f"There are {pending_approvals_count} participants pending approval in your department",
                "action_required": "Please approve or reject pending participants before matching",
                "pending_count": pending_approvals_count
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get APPROVED participants only from this department
        participants = Participant.objects.filter(
            approval_status='approved',
            status='active',
            department=department_filter
        )
    else:
        # Check if there are pending approvals overall
        pending_approvals_count = Participant.objects.filter(
            approval_status='pending',
            # Only count participants who have re-registered (have tech stack and interests)
            tech_stack__isnull=False,
            tech_stack__gt='',
            areas_of_interest__isnull=False,
            areas_of_interest__gt=''
        ).count()
        
        if pending_approvals_count > 0:
            return Response({
                "error": "Approval required before matching",
                "message": f"There are {pending_approvals_count} participants pending approval",
                "action_required": "Please approve or reject pending participants before matching",
                "pending_count": pending_approvals_count
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get all APPROVED participants
        participants = Participant.objects.filter(approval_status='approved', status='active')
    
    serializer = ParticipantSerializer(participants, many=True)
    students = serializer.data
    
    if not students:
        return Response({
            "error": "No approved participants found",
            "message": "All participants need to be approved by an admin before matching"
        }, status=status.HTTP_400_BAD_REQUEST)  # Changed from 404 to 400
        
    # Get participants who are already in relationships
    if department_filter:
        # For department admin, only consider relationships in their department
        department_participants = Participant.objects.filter(department=department_filter)
        participant_ids = [p.registration_no for p in department_participants]
        
        mentors_in_relationships = MentorMenteeRelationship.objects.filter(
            mentor__registration_no__in=participant_ids
        ).values_list('mentor__registration_no', flat=True).distinct()
        
        mentees_in_relationships = MentorMenteeRelationship.objects.filter(
            mentee__registration_no__in=participant_ids
        ).values_list('mentee__registration_no', flat=True).distinct()
    else:
        # For regular admin, consider all relationships
        mentors_in_relationships = MentorMenteeRelationship.objects.values_list('mentor__registration_no', flat=True).distinct()
        mentees_in_relationships = MentorMenteeRelationship.objects.values_list('mentee__registration_no', flat=True).distinct()
    
    # Identify participants who already have relationships
    matched_reg_nos = set(mentors_in_relationships) | set(mentees_in_relationships)
    
    # Find unmatched participants
    unmatched_students = [s for s in students if s['registration_no'] not in matched_reg_nos]
    
    # Check if we have any unmatched participants
    if not unmatched_students:
        return Response({
            "message": "All approved participants are already matched",
            "matched_count": len(matched_reg_nos),
            "total_count": len(students)
        }, status=status.HTTP_200_OK)
    
    # Now call the matching algorithm but ONLY for unmatched participants
    # If department_filter is active, only match within same department
    if department_filter:
        # Additional check to ensure we're only matching within the same department
        for student in unmatched_students:
            student['department_id'] = department_filter.id
    
    matches = match_mentors_mentees(unmatched_students)
    
    # Check if there was an error in matching
    if isinstance(matches, dict) and 'error' in matches:
        return Response(matches, status=status.HTTP_400_BAD_REQUEST)
    
    # Save relationships to database
    try:
        with transaction.atomic():
            # Special case: If we have unmatched mentees but no new mentors,
            # try to match them with existing mentors in the database
            if 'unmatched_mentees' in matches and matches['unmatched_mentees']:
                unmatched_mentees = matches['unmatched_mentees']
                
                # Get existing mentors who might be able to take on more mentees
                if department_filter:
                    # Only get mentors from this department
                    existing_mentors_qs = Participant.objects.filter(
                        registration_no__in=mentors_in_relationships,
                        department=department_filter
                    )
                else:
                    # Get all existing mentors
                    existing_mentors_qs = Participant.objects.filter(
                        registration_no__in=mentors_in_relationships
                    )
                
                existing_mentors = []
                for mentor in existing_mentors_qs:
                    # Count how many mentees this mentor already has
                    mentee_count = MentorMenteeRelationship.objects.filter(
                        mentor__registration_no=mentor.registration_no
                    ).count()
                    
                    # If they have capacity for more mentees, add them to our list
                    if mentee_count < 4:  # MAX_MENTEES_PER_MENTOR
                        existing_mentors.append({
                            'registration_no': mentor.registration_no,
                            'name': mentor.name,
                            'branch': mentor.branch,
                            'semester': mentor.semester,
                            'tech_stack': mentor.tech_stack,
                            'current_mentee_count': mentee_count,
                            'department_id': mentor.department.id if mentor.department else None
                        })
                
                # If we have existing mentors with capacity, assign the unmatched mentees
                if existing_mentors:
                    # Sort mentors by current mentee count (ascending)
                    existing_mentors.sort(key=lambda m: m['current_mentee_count'])
                    
                    # Create matches for unmatched mentees
                    for mentee_data in unmatched_mentees:
                        # Filter mentors by department if department_filter is active
                        if department_filter:
                            available_mentors = [
                                m for m in existing_mentors 
                                if m['department_id'] == department_filter.id
                            ]
                        else:
                            available_mentors = existing_mentors
                            
                        if not available_mentors:
                            continue
                            
                        # Get the mentor with the fewest mentees
                        mentor_data = available_mentors[0]
                        
                        # Create the relationship
                        mentor = Participant.objects.get(registration_no=mentor_data['registration_no'])
                        mentee = Participant.objects.get(registration_no=mentee_data['registration_no'])
                        
                        # Skip if they're from different departments and department_filter is active
                        if (department_filter and 
                            ((mentor.department and mentor.department.id != department_filter.id) or
                             (mentee.department and mentee.department.id != department_filter.id))):
                            continue
                        
                        MentorMenteeRelationship.objects.create(
                            mentor=mentor,
                            mentee=mentee,
                            manually_created=False
                        )
                        
                        # Update the mentor's mentee count
                        mentor_data['current_mentee_count'] += 1
                        
                        # Re-sort the mentors list
                        existing_mentors.sort(key=lambda m: m['current_mentee_count'])
                        
                        # Add to matches for response
                        matches['matches'].append({
                            "mentor": {
                                "name": mentor_data['name'],
                                "registration_no": mentor_data['registration_no'],
                                "semester": mentor_data['semester'],
                                "branch": mentor_data['branch'],
                                "tech_stack": mentor_data['tech_stack'],
                                "department_id": mentor_data['department_id']
                            },
                            "mentee": {
                                "name": mentee_data['name'],
                                "registration_no": mentee_data['registration_no'],
                                "semester": mentee_data['semester'],
                                "branch": mentee_data['branch'],
                                "tech_stack": mentee_data['tech_stack'],
                                "department_id": mentee_data.get('department_id')
                            },
                            "match_quality": "assigned-to-existing",
                            "common_tech": [],
                            "common_interests": [],
                            "preference_score": 0
                        })
            
            # Create new relationships from the algorithm
            for match in matches['matches']:
                mentor_reg_no = match['mentor']['registration_no']
                mentee_reg_no = match['mentee']['registration_no']
                
                # Skip if a relationship already exists
                if MentorMenteeRelationship.objects.filter(
                    mentor__registration_no=mentor_reg_no, 
                    mentee__registration_no=mentee_reg_no
                ).exists():
                    continue
                
                # Skip if mentee already has a relationship
                if MentorMenteeRelationship.objects.filter(
                    mentee__registration_no=mentee_reg_no
                ).exists():
                    continue
                
                try:
                    mentor = Participant.objects.get(registration_no=mentor_reg_no)
                    mentee = Participant.objects.get(registration_no=mentee_reg_no)
                    
                    # Skip if they're from different departments and department_filter is active
                    if (department_filter and 
                        ((mentor.department and mentor.department.id != department_filter.id) or
                         (mentee.department and mentee.department.id != department_filter.id))):
                        continue
                    
                    # Create the relationship (flag as auto-generated)
                    MentorMenteeRelationship.objects.create(
                        mentor=mentor,
                        mentee=mentee,
                        manually_created=False
                    )
                except Participant.DoesNotExist:
                    # Skip if either mentor or mentee doesn't exist
                    continue
    except Exception as e:
        return Response({
            "error": "Failed to save mentor-mentee relationships",
            "details": str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    # Get all relationships for a complete response
    if department_filter:
        # For department admin, only get relationships in their department
        department_participants = Participant.objects.filter(department=department_filter)
        participant_ids = [p.registration_no for p in department_participants]
        
        all_relationships = MentorMenteeRelationship.objects.filter(
            mentor__registration_no__in=participant_ids
        )
    else:
        # For regular admin, get all relationships
        all_relationships = MentorMenteeRelationship.objects.all()
        
    total_relationships = all_relationships.count()
    manual_relationships = all_relationships.filter(manually_created=True).count()
    auto_relationships = all_relationships.filter(manually_created=False).count()
    newly_created = len(matches['matches'])
        
    response_data = {
        "message": f"Successfully matched {newly_created} new participants",
        "newly_matched": newly_created,
        "total_relationships": total_relationships,
        "relationship_types": {
            "manual": manual_relationships,
            "automatic": auto_relationships
        },
        "new_matches": matches['matches'],
        "statistics": matches.get('statistics', {})
    }
    
    # Add department info if filtering was applied
    if department_filter:
        response_data["department_filter"] = {
            "id": department_filter.id,
            "name": department_filter.name,
            "code": department_filter.code
        }
        
    return Response(response_data)

@api_view(['DELETE'])
def delete_all_participants(request):
    """Endpoint to delete all participants from the database."""
    try:
        count = Participant.objects.count()
        Participant.objects.all().delete()
        return Response({
            "message": f"Successfully deleted all {count} participants",
            "count": count
        }, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({
            "error": "Failed to delete participants",
            "details": str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
@api_view(['GET'])
def get_participant_profile(request, registration_no):
    """Get a participant's profile with mentor/mentee relationships."""
    try:
        participant = Participant.objects.get(registration_no=registration_no)
        serializer = ProfileSerializer(participant)
        data = serializer.data
        
        # Try to fetch mobile_number from Student model using registration_no
        try:
            from account.models import Student
            student = Student.objects.filter(reg_no=registration_no).first()
            if student:
                data['mobile_number'] = student.mobile_number
            else:
                data['mobile_number'] = participant.mobile_number  # Fallback to participant model if student not found
        except Exception as e:
            print(f"Error fetching mobile number: {e}")
            data['mobile_number'] = participant.mobile_number  # Use participant model as fallback
            
        return Response(data)
    except Participant.DoesNotExist:
        return Response({"error": "Participant not found"}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ---- Session Management Endpoints ----

@api_view(['POST'])
def create_session(request):
    """Create a new mentoring session."""
    try:
        # Add the mentor from request data
        mentor_reg_no = request.data.get('mentor')
        
        # Verify that the mentor exists
        try:
            mentor = Participant.objects.get(registration_no=mentor_reg_no)
        except Participant.DoesNotExist:
            return Response({
                "error": "Invalid mentor registration number"
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Create serializer with request data
        serializer = SessionSerializer(data=request.data)
        
        if serializer.is_valid():
            # Save session with mentor
            session = serializer.save(mentor=mentor)
            
            # Send email notifications
            from account.utils import Util
            
            # Get session details for the email
            session_type = session.session_type
            date_time = session.date_time.strftime("%Y-%m-%d %H:%M")
            location_info = session.meeting_link if session_type == 'virtual' else session.location
            summary = session.summary
            
            # Get the mentor's email
            mentor_email = get_email_by_registration_no(mentor.registration_no)
            
            # Send email to the mentor
            mentor_body = f"Dear {mentor.name},\n\nYou have successfully scheduled a new {session_type} session on {date_time}.\n\nSession details:\n{summary}\n\nLocation/Link: {location_info}\n\nRegards,\nThe Team VidyaSangam"
            mentor_data = {
                'subject': 'New Session Scheduled',
                'body': mentor_body,
                'to_email': mentor_email
            }
            Util.send_email(mentor_data)
            
            # Send emails to all participants
            for participant in session.participants.all():
                # Get the participant's email
                participant_email = get_email_by_registration_no(participant.registration_no)
                
                participant_body = f"Dear {participant.name},\n\nYou have been invited to a {session_type} session scheduled by {mentor.name} on {date_time}.\n\nSession details:\n{summary}\n\nLocation/Link: {location_info}\n\nRegards,\nThe Team VidyaSangam"
                participant_data = {
                    'subject': 'Session Invitation',
                    'body': participant_body,
                    'to_email': participant_email
                }
                Util.send_email(participant_data)
            
            return Response({
                "message": "Session created successfully",
                "session": SessionSerializer(session).data
            }, status=status.HTTP_201_CREATED)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            
    except Exception as e:
        return Response({
            "error": "Failed to create session",
            "details": str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def get_user_sessions(request, registration_no):
    """Get all sessions for a specific user (as mentor or participant)."""
    try:
        # Verify the participant exists
        try:
            participant = Participant.objects.get(registration_no=registration_no)
        except Participant.DoesNotExist:
            return Response({
                "error": "Participant not found"
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Get sessions where user is a mentor
        mentor_sessions = Session.objects.filter(mentor=participant)
        
        # Get sessions where user is a participant
        participant_sessions = Session.objects.filter(participants=participant)
        
        # Combine the two querysets without duplicates
        all_sessions = mentor_sessions.union(participant_sessions)
        
        # Sort by date_time (most recent first)
        all_sessions = all_sessions.order_by('-date_time')
        
        # Serialize and return
        serializer = SessionSerializer(all_sessions, many=True)
        return Response(serializer.data)
        
    except Exception as e:
        return Response({
            "error": "Failed to retrieve sessions",
            "details": str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def get_session_details(request, session_id):
    """Get details for a specific session."""
    try:
        session = Session.objects.get(session_id=session_id)
        serializer = SessionSerializer(session)
        return Response(serializer.data)
    except Session.DoesNotExist:
        return Response({
            "error": "Session not found"
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            "error": "Failed to retrieve session details",
            "details": str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['DELETE'])
def delete_session(request, session_id):
    """Delete a specific session."""
    try:
        try:
            session = Session.objects.get(session_id=session_id)
        except Session.DoesNotExist:
            return Response({
                "error": "Session not found"
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Check if the requester is the mentor who created the session
        mentor_reg_no = request.data.get('mentor_reg_no')
        if mentor_reg_no and session.mentor.registration_no != mentor_reg_no:
            return Response({
                "error": "Only the session creator can delete this session"
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Delete the session
        session.delete()
        
        return Response({
            "message": "Session deleted successfully"
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            "error": "Failed to delete session",
            "details": str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# ----- Admin Endpoints for Managing Mentor-Mentee Relationships -----

@api_view(['GET'])
def list_all_relationships(request):
    """Get all mentor-mentee relationships"""
    try:
        # Check if the user is a department admin
        user = request.user
        department_filter = None
        
        # If this is a department admin, they should only see relationships from their department
        if hasattr(user, 'is_department_admin') and user.is_department_admin and user.department:
            department_filter = user.department
            print(f"Department admin filtering for department: {department_filter.name}")
            
            # Get relationships where either mentor or mentee is in this department
            department_participants = Participant.objects.filter(
                department=department_filter,
                approval_status='approved'
            )
            participant_ids = [p.registration_no for p in department_participants]
            
            relationships = MentorMenteeRelationship.objects.filter(
                mentor__registration_no__in=participant_ids
            )
        else:
            # Regular admin or non-logged in user gets all relationships
            relationships = MentorMenteeRelationship.objects.all()
            
        # Create detailed response with mentor and mentee info
        result = []
        for rel in relationships:
            mentor_data = {
                'registration_no': rel.mentor.registration_no,
                'name': rel.mentor.name,
                'branch': rel.mentor.branch,
                'semester': rel.mentor.semester,
                'department_id': rel.mentor.department.id if rel.mentor.department else None,
                'department_name': rel.mentor.department.name if rel.mentor.department else None
            }
            
            mentee_data = {
                'registration_no': rel.mentee.registration_no,
                'name': rel.mentee.name,
                'branch': rel.mentee.branch,
                'semester': rel.mentee.semester,
                'department_id': rel.mentee.department.id if rel.mentee.department else None,
                'department_name': rel.mentee.department.name if rel.mentee.department else None
            }
            
            result.append({
                'id': rel.id,
                'mentor': mentor_data,
                'mentee': mentee_data,
                'created_at': rel.created_at,
                'manually_created': rel.manually_created
            })
        
        # Add department info to response
        response_data = {
            'relationships': result,
            'count': len(result)
        }
        
        if department_filter:
            response_data['department_filter'] = {
                'id': department_filter.id,
                'name': department_filter.name,
                'code': department_filter.code
            }
            
        return Response(response_data)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
def create_relationship(request):
    """Create a new mentor-mentee relationship"""
    try:
        mentor_reg_no = request.data.get('mentor_registration_no')
        mentee_reg_no = request.data.get('mentee_registration_no')
        
        if not mentor_reg_no or not mentee_reg_no:
            return Response({
                "error": "Both mentor_registration_no and mentee_registration_no are required"
            }, status=status.HTTP_400_BAD_REQUEST)
            
        # Check if the user is a department admin with department restrictions
        user = request.user
        department_filter = None
        
        if hasattr(user, 'is_department_admin') and user.is_department_admin and user.department:
            department_filter = user.department
            # Check if there are pending approvals for this department
            pending_approvals_count = Participant.objects.filter(
                approval_status='pending',
                department=department_filter,
                # Only count participants who have re-registered (have tech stack and interests)
                tech_stack__isnull=False,
                tech_stack__gt='',
                areas_of_interest__isnull=False,
                areas_of_interest__gt=''
            ).count()
            if pending_approvals_count > 0:
                return Response({
                    "error": "Approval required before creating relationships",
                    "message": f"There are {pending_approvals_count} participants pending approval in your department",
                    "action_required": "Please approve or reject pending participants first",
                    "pending_count": pending_approvals_count
                }, status=status.HTTP_400_BAD_REQUEST)
        else:
            # Check if there are pending approvals in the departments of the mentor or mentee
            mentor = Participant.objects.filter(registration_no=mentor_reg_no).first()
            mentee = Participant.objects.filter(registration_no=mentee_reg_no).first()
            mentor_dept = mentor.department if mentor else None
            mentee_dept = mentee.department if mentee else None

            pending_approvals_count = 0
            pending_departments = []

            if mentor_dept:
                count = Participant.objects.filter(
                    approval_status='pending',
                    department=mentor_dept,
                    # Only count participants who have re-registered
                    tech_stack__isnull=False,
                    tech_stack__gt='',
                    areas_of_interest__isnull=False,
                    areas_of_interest__gt=''
                ).count()
                if count > 0:
                    pending_approvals_count += count
                    pending_departments.append(mentor_dept.name)
            if mentee_dept and mentee_dept != mentor_dept:
                count = Participant.objects.filter(
                    approval_status='pending',
                    department=mentee_dept,
                    # Only count participants who have re-registered
                    tech_stack__isnull=False,
                    tech_stack__gt='',
                    areas_of_interest__isnull=False,
                    areas_of_interest__gt=''
                ).count()
                if count > 0:
                    pending_approvals_count += count
                    pending_departments.append(mentee_dept.name)

            if pending_approvals_count > 0:
                return Response({
                    "error": "Approval required before creating relationships",
                    "message": f"There are {pending_approvals_count} participants pending approval in the following department(s): {', '.join(pending_departments)}",
                    "action_required": "Please approve or reject pending participants first",
                    "pending_count": pending_approvals_count
                }, status=status.HTTP_400_BAD_REQUEST)
        
        # Verify both participants exist
        try:
            mentor = Participant.objects.get(registration_no=mentor_reg_no)
            mentee = Participant.objects.get(registration_no=mentee_reg_no)
        except Participant.DoesNotExist:
            return Response({
                "error": "One or both participants not found"
            }, status=status.HTTP_404_NOT_FOUND)
            
        # Check if participants are approved
        if mentor.approval_status != 'approved':
            return Response({
                "error": f"Mentor (registration no: {mentor_reg_no}) is not approved",
                "current_status": mentor.approval_status,
                "action_required": "Please approve the mentor before creating the relationship"
            }, status=status.HTTP_400_BAD_REQUEST)
            
        if mentee.approval_status != 'approved':
            return Response({
                "error": f"Mentee (registration no: {mentee_reg_no}) is not approved",
                "current_status": mentee.approval_status,
                "action_required": "Please approve the mentee before creating the relationship"
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if mentor.status != 'active':
            return Response({
                "error": f"Mentor (registration no: {mentor_reg_no}) is not active",
                "current_status": mentor.status,
                "action_required": "Please ensure the mentor is active before creating the relationship"
            }, status=status.HTTP_400_BAD_REQUEST)

        if mentee.status != 'active':
            return Response({
                "error": f"Mentee (registration no: {mentee_reg_no}) is not active",
                "current_status": mentee.status,
                "action_required": "Please ensure the mentee is active before creating the relationship"
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Department restriction check for department admins
        if department_filter:
            # Verify both participants are from the department admin's department
            if (mentor.department and mentor.department.id != department_filter.id) or \
               (mentee.department and mentee.department.id != department_filter.id):
                return Response({
                    "error": "Department admin can only create relationships within their department",
                    "department": department_filter.name
                }, status=status.HTTP_403_FORBIDDEN)
        
        # Verify they're not the same person
        if mentor_reg_no == mentee_reg_no:
            return Response({
                "error": "Cannot create a relationship where mentor and mentee are the same person"
            }, status=status.HTTP_400_BAD_REQUEST)
            
        # Check for existing relationship
        if MentorMenteeRelationship.objects.filter(
            mentor=mentor, mentee=mentee
        ).exists():
            return Response({
                "error": "This mentor-mentee relationship already exists"
            }, status=status.HTTP_400_BAD_REQUEST)
            
        # Check if the mentee already has a mentor
        if MentorMenteeRelationship.objects.filter(mentee=mentee).exists():
            existing_mentor = MentorMenteeRelationship.objects.get(mentee=mentee).mentor
            return Response({
                "error": f"Mentee already has a mentor: {existing_mentor.name} ({existing_mentor.registration_no})",
                "suggestion": "You can delete the existing relationship first if you want to reassign the mentee"
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Check if mentor has reached maximum mentees (e.g., 5)
        mentee_count = MentorMenteeRelationship.objects.filter(mentor=mentor).count()
        if mentee_count >= 5:  # Maximum mentees per mentor
            return Response({
                "error": f"Mentor already has {mentee_count} mentees (maximum allowed)",
                "suggestion": "Please assign this mentee to another mentor with capacity"
            }, status=status.HTTP_400_BAD_REQUEST)
            
        # Create the relationship
        relationship = MentorMenteeRelationship.objects.create(
            mentor=mentor,
            mentee=mentee,
            manually_created=True  # Flag as manually created
        )
        
        # Return success response with relationship details
        return Response({
            "message": "Mentor-mentee relationship created successfully",
            "relationship": {
                "id": relationship.id,
                "mentor": {
                    "name": mentor.name,
                    "registration_no": mentor.registration_no,
                    "department_name": mentor.department.name if mentor.department else None
                },
                "mentee": {
                    "name": mentee.name,
                    "registration_no": mentee.registration_no,
                    "department_name": mentee.department.name if mentee.department else None
                },
                "created_at": relationship.created_at
            }
        }, status=status.HTTP_201_CREATED)
    except Exception as e:
        return Response({
            "error": "Failed to create mentor-mentee relationship",
            "details": str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['PUT'])
def update_relationship(request, relationship_id):
    """Update a mentor-mentee relationship (change mentor or mentee)."""
    try:
        try:
            relationship = MentorMenteeRelationship.objects.get(id=relationship_id)
        except MentorMenteeRelationship.DoesNotExist:
            return Response({
                "error": "Relationship not found"
            }, status=status.HTTP_404_NOT_FOUND)
            
        mentor_reg_no = request.data.get('mentor_registration_no')
        mentee_reg_no = request.data.get('mentee_registration_no')
        
        new_mentor = None
        new_mentee = None
        
        if mentor_reg_no:
            try:
                new_mentor = Participant.objects.get(registration_no=mentor_reg_no)
                # Check approval status
                if new_mentor.approval_status != 'approved':
                    return Response({
                        "error": f"Mentor {new_mentor.name} has not been approved by admin",
                        "current_status": new_mentor.approval_status
                    }, status=status.HTTP_400_BAD_REQUEST)
                relationship.mentor = new_mentor
            except Participant.DoesNotExist:
                return Response({
                    "error": "Mentor not found"
                }, status=status.HTTP_404_NOT_FOUND)
                
        if mentee_reg_no:
            try:
                new_mentee = Participant.objects.get(registration_no=mentee_reg_no)
                # Check approval status
                if new_mentee.approval_status != 'approved':
                    return Response({
                        "error": f"Mentee {new_mentee.name} has not been approved by admin",
                        "current_status": new_mentee.approval_status
                    }, status=status.HTTP_400_BAD_REQUEST)
                relationship.mentee = new_mentee
            except Participant.DoesNotExist:
                return Response({
                    "error": "Mentee not found"
                }, status=status.HTTP_404_NOT_FOUND)
        
        # Check if updated relationship would be a duplicate
        if MentorMenteeRelationship.objects.filter(
            mentor=relationship.mentor, 
            mentee=relationship.mentee
        ).exclude(id=relationship_id).exists():
            return Response({
                "error": "This mentor-mentee relationship already exists"
            }, status=status.HTTP_400_BAD_REQUEST)
                
        relationship.save()
        
        return Response({
            "message": "Relationship updated successfully",
            "relationship": {
                "id": relationship.id,
                "mentor": {
                    "name": relationship.mentor.name,
                    "registration_no": relationship.mentor.registration_no
                },
                "mentee": {
                    "name": relationship.mentee.name,
                    "registration_no": relationship.mentee.registration_no
                }
            }
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            "error": "Failed to update relationship",
            "details": str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['DELETE'])
def delete_relationship(request, relationship_id):
    """Delete a mentor-mentee relationship."""
    try:
        try:
            relationship = MentorMenteeRelationship.objects.get(id=relationship_id)
        except MentorMenteeRelationship.DoesNotExist:
            return Response({
                "error": "Relationship not found"
            }, status=status.HTTP_404_NOT_FOUND)
            
        # Save details for response
        mentor_name = relationship.mentor.name
        mentee_name = relationship.mentee.name
        
        # Delete the relationship
        relationship.delete()
        
        return Response({
            "message": f"Relationship between mentor '{mentor_name}' and mentee '{mentee_name}' deleted successfully"
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            "error": "Failed to delete relationship",
            "details": str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
def list_unmatched_participants(request):
    """List all participants who don't have any mentor-mentee relationships."""
    try:
        # Check if the user is a department admin
        user = request.user
        department_filter = None
        
        # If this is a department admin, they should only see participants from their department
        if hasattr(user, 'is_department_admin') and user.is_department_admin and user.department:
            department_filter = user.department
            print(f"Department admin filtering unmatched participants for department: {department_filter.name}")
            
            # Get all approved participants from this department
            all_participants = Participant.objects.filter(
                department=department_filter,
                approval_status='approved'
            )
        else:
            # Regular admin or non-logged in user gets all approved participants
            all_participants = Participant.objects.filter(approval_status='approved')
        
        # Get all participants who are mentors or mentees in a relationship
        if department_filter:
            # For department admin, only consider relationships in their department
            department_participants = all_participants.values_list('registration_no', flat=True)
            
            mentors_in_relationships = MentorMenteeRelationship.objects.filter(
                mentor__registration_no__in=department_participants
            ).values_list('mentor', flat=True).distinct()
            
            mentees_in_relationships = MentorMenteeRelationship.objects.filter(
                mentee__registration_no__in=department_participants
            ).values_list('mentee', flat=True).distinct()
        else:
            # For regular admin, consider all relationships
            mentors_in_relationships = MentorMenteeRelationship.objects.values_list('mentor', flat=True).distinct()
            mentees_in_relationships = MentorMenteeRelationship.objects.values_list('mentee', flat=True).distinct()
        
        # Combine the two lists to get all participants in relationships
        matched_reg_nos = set(mentors_in_relationships) | set(mentees_in_relationships)
        
        # Filter for participants who are not in any relationship
        unmatched_participants = all_participants.exclude(registration_no__in=matched_reg_nos)
        
        # Serialize the unmatched participants
        serializer = ParticipantSerializer(unmatched_participants, many=True)
        
        # Add department info to response
        response_data = {
            "count": unmatched_participants.count(),
            "total_participants": all_participants.count(),
            "unmatched_participants": serializer.data
        }
        
        if department_filter:
            response_data["department_filter"] = {
                "id": department_filter.id,
                "name": department_filter.name,
                "code": department_filter.code
            }
            
        return Response(response_data)
        
    except Exception as e:
        return Response({
            "error": "Failed to retrieve unmatched participants",
            "details": str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

def parse_quiz_response(text):
    """
    Parse the quiz response from Gemini, handling markdown code blocks and JSON formatting.
    
    Args:
        text (str): The text response from Gemini API
        
    Returns:
        list: List of quiz questions with options, answers, and explanations
    """
    # Check if the response is wrapped in markdown code blocks
    if "```json" in text:
        # Extract content between markdown code blocks
        start_idx = text.find("```json") + 7  # Skip past ```json
        end_idx = text.rfind("```")
        if end_idx > start_idx:
            json_text = text[start_idx:end_idx].strip()
        else:
            json_text = text
    else:
        json_text = text
    
    # Clean up any remaining issues
    json_text = json_text.strip()
    
    try:
        # Parse the JSON
        return json.loads(json_text)
    except json.JSONDecodeError as e:
        # If parsing fails, return an error message
        return [{"error": f"Failed to parse JSON: {str(e)}", "raw_text": json_text}]

@api_view(['POST'])
def generate_quiz(request):
    """
    Generate a quiz using Gemini API and optionally assign it to a mentee.
    
    Expects: 
        - prompt (topic)
        - num_questions
        - mentee_id (registration number of the mentee)
        - mentor_id (registration number of the mentor generating the quiz)
        - description (optional)
    
    Returns: quiz as a list of dicts with question, options, answer, explanation
    """
    prompt = request.data.get('prompt')
    description = request.data.get('description', '')
    mentee_id = request.data.get('mentee_id')
    mentor_id = request.data.get('mentor_id')
    num_questions = int(request.data.get('num_questions', 5))

    if not prompt or not num_questions:
        return Response({'error': 'Prompt and num_questions are required.'}, status=400)
    
    # Validate mentee and mentor if provided
    mentee = None
    mentor = None
    relationship_validated = False
    
    if mentee_id:
        try:
            mentee = Participant.objects.get(registration_no=mentee_id)
        except Participant.DoesNotExist:
            return Response({'error': f'Mentee with ID {mentee_id} not found'}, status=404)
    
    if mentor_id:
        try:
            mentor = Participant.objects.get(registration_no=mentor_id)
            
            # If both mentor and mentee are provided, verify their relationship
            if mentee:
                relationship = MentorMenteeRelationship.objects.filter(
                    mentor=mentor, 
                    mentee=mentee
                ).exists()
                
                if not relationship:
                    return Response({
                        'error': f'No mentor-mentee relationship found between {mentor_id} and {mentee_id}'
                    }, status=400)
                
                relationship_validated = True
                
        except Participant.DoesNotExist:
            return Response({'error': f'Mentor with ID {mentor_id} not found'}, status=404)

    # Compose the Gemini prompt
    gemini_prompt = (
        f"Generate a quiz with {num_questions} multiple-choice questions on the topic: '{prompt}' and description: '{description}'. "
        "For each question, provide 4 options (A, B, C, D), indicate the correct answer, and provide a short explanation. "
        "Return the JSON array directly WITHOUT ANY TEXT INTRODUCTION OR CODE BLOCK FORMATTING. "
        "Required JSON format: ["
        "{\"question\": \"What is AI?\", \"options\": {\"A\": \"Artificial Intelligence\", \"B\": \"Automated Input\", \"C\": \"Analog Interface\", \"D\": \"Advanced Integration\"}, \"answer\": \"A\", \"explanation\": \"AI stands for Artificial Intelligence.\"}"
        "]"
    )

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
    headers = {'Content-Type': 'application/json'}
    data = {
        "contents": [{
            "parts": [{"text": gemini_prompt}]
        }],
        "generationConfig": {
            "temperature": 0.2,
            "topP": 0.8,
            "topK": 40
        }
    }

    try:
        gemini_response = requests.post(url, headers=headers, json=data, timeout=30)
        gemini_response.raise_for_status()
        gemini_data = gemini_response.json()
        # Extract the quiz from the Gemini response
        quiz_text = gemini_data['candidates'][0]['content']['parts'][0]['text']
        
        # Parse the quiz using our helper function
        quiz = parse_quiz_response(quiz_text)
        
        # If mentee_id is provided, create a pending quiz for them
        if mentee and mentor and relationship_validated:
            # Create a pending quiz result with score of 0
            pending_quiz = QuizResult(
                participant=mentee,
                mentor=mentor,  # Store the mentor who created the quiz
                quiz_topic=prompt,
                score=0,
                total_questions=len(quiz),
                percentage=0,
                quiz_data=quiz,
                quiz_answers={},  # Empty until the mentee submits answers
                result_details=[]  # Empty until the mentee submits answers
            )
            pending_quiz.save()
            
            # Send email notification to the mentee
            from account.utils import Util
            
            # Get the mentee's email
            email = get_email_by_registration_no(mentee.registration_no)
            
            # Send quiz assignment email
            body = f"Dear {mentee.name},\n\nA new quiz on '{prompt}' has been assigned to you by your mentor {mentor.name}. Please login to the platform to attempt the quiz.\n\nRegards,\nThe Team VidyaSangam"
            data = {
                'subject': 'New Quiz Assigned',
                'body': body,
                'to_email': email
            }
            Util.send_email(data)
            
            # Include the quiz_id in the response
            return Response({
                'quiz': quiz,
                'quiz_id': pending_quiz.id,
                'mentee': {
                    'name': mentee.name,
                    'registration_no': mentee.registration_no
                },
                'mentor': {
                    'name': mentor.name,
                    'registration_no': mentor.registration_no
                },
                'status': 'pending',
                'message': f'Quiz assigned to {mentee.name} successfully'
            }, status=200)
        
        # If mentor is provided but no mentee, also track that the mentor generated a quiz
        # but mark it as not assigned to anyone specific
        elif mentor and not mentee:
            # Create a placeholder "mentor quiz" that isn't assigned to a mentee
            mentor_quiz = QuizResult(
                participant=mentor,  # The mentor is the participant
                mentor=mentor,       # The mentor is also the creator
                quiz_topic=prompt,
                score=0,
                total_questions=len(quiz),
                percentage=0,
                quiz_data=quiz,
                quiz_answers={},
                result_details=[],
                status='unassigned'  # Special status for tracking mentor-generated quizzes
            )
            mentor_quiz.save()
            
            return Response({
                'quiz': quiz,
                'quiz_id': mentor_quiz.id,
                'mentor': {
                    'name': mentor.name,
                    'registration_no': mentor.registration_no
                },
                'status': 'unassigned',
                'message': 'Quiz generated but not assigned to any mentee'
            }, status=200)
        
        # If no mentee_id, just return the quiz
        return Response({'quiz': quiz}, status=200)
    except requests.exceptions.RequestException as e:
        return Response({'error': f'Gemini API error: {str(e)}'}, status=502)
    except Exception as e:
        return Response({'error': f'Internal error: {str(e)}'}, status=500)

@api_view(['POST'])
def submit_quiz_answers(request):
    """
    Submit answers for a quiz and calculate the score.
    
    Request format:
    {
        "participant_id": "registration_no",
        "quiz_id": 123,  # Optional - if provided, updates the existing quiz result
        "quiz_topic": "AI Basics",  # Required if quiz_id not provided
        "quiz_data": [...],  # Required if quiz_id not provided
        "quiz_answers": {...}  # Dictionary of question indexes to answers (e.g., {"0": "A", "1": "C"})
    }
    """
    participant_id = request.data.get('participant_id')
    quiz_id = request.data.get('quiz_id')
    quiz_answers = request.data.get('quiz_answers')
    
    if not participant_id or not quiz_answers:
        return Response({
            'error': 'participant_id and quiz_answers are required'
        }, status=400)
        
    try:
        participant = Participant.objects.get(registration_no=participant_id)
    except Participant.DoesNotExist:
        return Response({'error': f'Participant with ID {participant_id} not found'}, status=404)
    
    # Two paths: update existing quiz or create new one
    if quiz_id:
        # Update existing quiz result
        try:
            quiz_result = QuizResult.objects.get(id=quiz_id, participant=participant)
            
            # Prevent resubmission if already completed
            if quiz_result.status == 'completed':
                return Response({
                    'error': 'This quiz has already been completed and cannot be resubmitted',
                    'quiz_result': QuizResultSerializer(quiz_result).data
                }, status=400)
                
            quiz_topic = quiz_result.quiz_topic
            quiz_data = quiz_result.quiz_data
            
        except QuizResult.DoesNotExist:
            return Response({'error': f'Quiz with ID {quiz_id} not found for this participant'}, status=404)
    else:
        # Create new quiz result
        quiz_topic = request.data.get('quiz_topic')
        quiz_data = request.data.get('quiz_data')
        
        if not quiz_topic or not quiz_data:
            return Response({
                'error': 'quiz_topic and quiz_data are required when not providing quiz_id'
            }, status=400)
            
        # New quiz will be created below after score calculation
    
    # Calculate score
    score = 0
    results = []
    
    for idx, question in enumerate(quiz_data):
        user_answer = quiz_answers.get(str(idx))
        correct_answer = question.get('answer')
        is_correct = user_answer == correct_answer
        
        if is_correct:
            score += 1
            
        # Store detailed result for this question
        results.append({
            'question': question.get('question'),
            'user_answer': user_answer,
            'correct_answer': correct_answer,
            'is_correct': is_correct,
            'explanation': question.get('explanation')
        })
    
    total_questions = len(quiz_data)
    percentage = round((score / total_questions) * 100, 2) if total_questions > 0 else 0
    
    # Update existing or create new quiz result
    if quiz_id:
        # Update existing quiz
        quiz_result.score = score
        quiz_result.percentage = percentage
        quiz_result.quiz_answers = quiz_answers
        quiz_result.result_details = results
        quiz_result.status = 'completed'
        quiz_result.completed_date = datetime.datetime.now()
        quiz_result.save()
    else:
        # Create new quiz result
        quiz_result = QuizResult(
            participant=participant,
            quiz_topic=quiz_topic,
            score=score,
            total_questions=total_questions,
            percentage=percentage,
            quiz_data=quiz_data,
            quiz_answers=quiz_answers,
            result_details=results,
            status='completed',
            completed_date=datetime.datetime.now()
        )
        quiz_result.save()
    
    serializer = QuizResultSerializer(quiz_result)
    response_data = serializer.data
    response_data['marks_display'] = f"{score}/{total_questions}"
    return Response(response_data, status=201)

@api_view(['GET'])
def get_participant_quiz_results(request, registration_no):
    """Get all quiz results for a specific participant."""
    try:
        participant = Participant.objects.get(registration_no=registration_no)
        quiz_results = QuizResult.objects.filter(participant=participant)
        serializer = QuizResultSerializer(quiz_results, many=True)
        response_data = serializer.data
        for result in response_data:
            result['marks_display'] = f"{result['score']}/{result['total_questions']}"
        return Response(response_data)
    except Participant.DoesNotExist:
        return Response({'error': f'Participant with ID {registration_no} not found'}, status=404)
    except Exception as e:
        return Response({'error': str(e)}, status=500)

@api_view(['GET'])
def get_quiz_result_details(request, result_id):
    """Get detailed information about a specific quiz result."""
    try:
        quiz_result = QuizResult.objects.get(id=result_id)
        serializer = QuizResultSerializer(quiz_result)
        response_data = serializer.data
        response_data['marks_display'] = f"{quiz_result.score}/{quiz_result.total_questions}"
        return Response(response_data)
    except QuizResult.DoesNotExist:
        return Response({'error': f'Quiz result with ID {result_id} not found'}, status=404)
    except Exception as e:
        return Response({'error': str(e)}, status=500)

@api_view(['GET'])
def get_pending_quizzes(request, registration_no):
    """Get all pending quizzes for a specific participant."""
    try:
        participant = Participant.objects.get(registration_no=registration_no)
        pending_quizzes = QuizResult.objects.filter(participant=participant, status='pending')
        serializer = QuizResultSerializer(pending_quizzes, many=True)
        return Response(serializer.data)
    except Participant.DoesNotExist:
        return Response({'error': f'Participant with ID {registration_no} not found'}, status=404)
    except Exception as e:
        return Response({'error': str(e)}, status=500)

@api_view(['DELETE'])
def delete_quiz(request, quiz_id):
    """
    Delete a quiz by ID.
    Only the mentor who created the quiz or the mentee assigned to it can delete it.
    
    Request should include either mentor_id or mentee_id to verify permissions.
    """
    user_id = request.data.get('user_id')  # Registration number of user trying to delete
    user_role = request.data.get('user_role')  # Either 'mentor' or 'mentee'
    
    if not user_id or not user_role or user_role not in ['mentor', 'mentee']:
        return Response({
            'error': 'user_id and user_role (mentor/mentee) are required'
        }, status=400)
    
    try:
        quiz_result = QuizResult.objects.get(id=quiz_id)
    except QuizResult.DoesNotExist:
        return Response({'error': f'Quiz with ID {quiz_id} not found'}, status=404)
    
    # Check permissions
    has_permission = False
    
    if user_role == 'mentor' and quiz_result.mentor and quiz_result.mentor.registration_no == user_id:
        # Mentor who created the quiz
        has_permission = True
    elif user_role == 'mentee' and quiz_result.participant.registration_no == user_id:
        # Mentee assigned to the quiz
        has_permission = True
        
    if not has_permission:
        return Response({
            'error': 'You do not have permission to delete this quiz'
        }, status=403)
    
    # Store quiz details for the response
    quiz_details = {
        'id': quiz_result.id,
        'topic': quiz_result.quiz_topic,
        'status': quiz_result.status,
    }
    
    # Delete the quiz
    quiz_result.delete()
    
    return Response({
        'message': 'Quiz deleted successfully',
        'quiz': quiz_details
    }, status=200)

# Admin approval functions

@api_view(['POST'])
def update_participant_approval(request):
    """Update the approval status of a participant (admin only)"""
    registration_no = request.data.get('registration_no')
    new_status = request.data.get('approval_status')
    
    if not registration_no or not new_status:
        return Response({
            'error': 'Registration number and approval status are required'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    if new_status not in ['pending', 'approved', 'rejected']:
        return Response({
            'error': 'Invalid approval status. Must be pending, approved, or rejected'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        participant = Participant.objects.get(registration_no=registration_no)
        participant.approval_status = new_status
        
        # If rejected, store the reason
        if new_status == 'rejected':
            reason = request.data.get('reason', '')
            if not reason:
                return Response({
                    'error': 'Reason is required when rejecting a participant'
                }, status=status.HTTP_400_BAD_REQUEST)
            participant.deactivation_reason = reason
        
        participant.save()
        
        # Send email notification based on the approval status
        if new_status == 'approved':
            # Import the email utility
            from account.utils import Util
            
            # Get the student's email
            email = get_email_by_registration_no(participant.registration_no)
            
            # Send approval email
            body = f"Dear {participant.name},\n\nCongratulations! Your profile has been approved. You can now access all the features of our platform.\n\nRegards,\nThe Team VidyaSangam"
            data = {
                'subject': 'Profile Approved',
                'body': body,
                'to_email': email
            }
            Util.send_email(data)
        elif new_status == 'rejected':
            # Import the email utility
            from account.utils import Util
            
            # Get the student's email
            email = get_email_by_registration_no(participant.registration_no)
            
            # Send rejection email with reason
            body = f"Dear {participant.name},\n\nWe regret to inform you that your profile has been rejected for the following reason:\n\n{participant.deactivation_reason}\n\nPlease contact the administrator for more information.\n\nRegards,\nThe Team VidyaSangam"
            data = {
                'subject': 'Profile Rejection',
                'body': body,
                'to_email': email
            }
            Util.send_email(data)
        
        return Response({
            'message': f'Participant approval status updated to {new_status}',
            'participant': ParticipantSerializer(participant).data
        }, status=status.HTTP_200_OK)
        
    except Participant.DoesNotExist:
        return Response({
            'error': f'Participant with registration number {registration_no} not found'
        }, status=status.HTTP_404_NOT_FOUND)

@api_view(['GET'])
def list_pending_approvals(request):
    """List all participants with pending approval status (admin only)"""
    pending_participants = Participant.objects.filter(approval_status='pending')
    serializer = ParticipantSerializer(pending_participants, many=True)
    
    return Response({
        'count': pending_participants.count(),
        'participants': serializer.data
    }, status=status.HTTP_200_OK)

@api_view(['GET'])
def get_approval_status(request, registration_no):
    """Get the approval status of a specific participant"""
    try:
        participant = Participant.objects.get(registration_no=registration_no)
        return Response({
            'registration_no': registration_no,
            'approval_status': participant.approval_status,
            'reason': participant.deactivation_reason if participant.approval_status == 'rejected' else None
        }, status=status.HTTP_200_OK)
    except Participant.DoesNotExist:
        return Response({
            'error': f'Participant with registration number {registration_no} not found'
        }, status=status.HTTP_404_NOT_FOUND)

# Profile status management functions

@api_view(['POST'])
def update_participant_status(request):
    """Update the status of a participant (active, graduated, deactivated)"""
    registration_no = request.data.get('registration_no')
    new_status = request.data.get('status')
    
    if not registration_no or not new_status:
        return Response({
            'error': 'Registration number and status are required'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    if new_status not in ['active', 'graduated', 'deactivated']:
        return Response({
            'error': 'Invalid status. Must be active, graduated, or deactivated'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        participant = Participant.objects.get(registration_no=registration_no)
        old_status = participant.status
        participant.status = new_status
        
        # If deactivated, store the reason
        if new_status == 'deactivated':
            reason = request.data.get('reason', '')
            if not reason:
                return Response({
                    'error': 'Reason is required when deactivating a participant'
                }, status=status.HTTP_400_BAD_REQUEST)
            participant.deactivation_reason = reason
        
        participant.save()
        
        # Handle relationships when deactivating a mentor
        if new_status == 'deactivated' and MentorMenteeRelationship.objects.filter(mentor=participant).exists():
            # Get all mentees for this mentor
            mentees = [rel.mentee for rel in MentorMenteeRelationship.objects.filter(mentor=participant)]
            
            # Delete the relationships
            MentorMenteeRelationship.objects.filter(mentor=participant).delete()
            
            return Response({
                'message': f'Participant status updated from {old_status} to {new_status}',
                'participant': ParticipantSerializer(participant).data,
                'note': f'{len(mentees)} mentee relationships have been removed'
            }, status=status.HTTP_200_OK)
        
        return Response({
            'message': f'Participant status updated from {old_status} to {new_status}',
            'participant': ParticipantSerializer(participant).data
        }, status=status.HTTP_200_OK)
        
    except Participant.DoesNotExist:
        return Response({
            'error': f'Participant with registration number {registration_no} not found'
        }, status=status.HTTP_404_NOT_FOUND)

@api_view(['GET'])
def list_participants_by_status(request, status_filter):
    """List all participants with a specific status"""
    if status_filter not in ['active', 'graduated', 'deactivated', 'all']:
        return Response({
            'error': 'Invalid status filter. Must be active, graduated, deactivated, or all'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    if status_filter == 'all':
        participants = Participant.objects.all()
    else:
        participants = Participant.objects.filter(status=status_filter)
    
    serializer = ParticipantSerializer(participants, many=True)
    
    return Response({
        'count': participants.count(),
        'status': status_filter,
        'participants': serializer.data
    }, status=status.HTTP_200_OK)

# Badge and super mentor functions

@api_view(['POST'])
def create_badge(request):
    """Create a new badge (admin only)"""
    serializer = BadgeSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET'])
def list_badges(request):
    """List all available badges"""
    badges = Badge.objects.all()
    serializer = BadgeSerializer(badges, many=True)
    return Response(serializer.data)

@api_view(['POST'])
def award_badge(request):
    """Award a badge to a participant (admin only)"""
    participant_id = request.data.get('participant_id')
    badge_id = request.data.get('badge_id')
    
    if not participant_id or not badge_id:
        return Response({
            'error': 'Participant ID and badge ID are required'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        participant = Participant.objects.get(registration_no=participant_id)
        badge = Badge.objects.get(id=badge_id)
        
        # Check if participant already has this badge
        if ParticipantBadge.objects.filter(participant=participant, badge=badge).exists():
            return Response({
                'error': f'Participant already has the badge "{badge.name}"'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Award the badge
        participant_badge = ParticipantBadge.objects.create(
            participant=participant,
            badge=badge,
            is_claimed=False
        )
        
        return Response({
            'message': f'Badge "{badge.name}" awarded to {participant.name}',
            'participant_badge': ParticipantBadgeSerializer(participant_badge).data
        }, status=status.HTTP_201_CREATED)
        
    except Participant.DoesNotExist:
        return Response({
            'error': f'Participant with ID {participant_id} not found'
        }, status=status.HTTP_404_NOT_FOUND)
    except Badge.DoesNotExist:
        return Response({
            'error': f'Badge with ID {badge_id} not found'
        }, status=status.HTTP_404_NOT_FOUND)

@api_view(['POST'])
def claim_badge(request):
    """Claim a badge that has been awarded (participant action)"""
    participant_id = request.data.get('participant_id')
    badge_id = request.data.get('badge_id')
    
    if not participant_id or not badge_id:
        return Response({
            'error': 'Participant ID and badge ID are required'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        participant = Participant.objects.get(registration_no=participant_id)
        badge = Badge.objects.get(id=badge_id)
        
        try:
            participant_badge = ParticipantBadge.objects.get(
                participant=participant,
                badge=badge,
                is_claimed=False  # Only unclaimed badges can be claimed
            )
        except ParticipantBadge.DoesNotExist:
            return Response({
                'error': 'This badge is either not awarded to you or already claimed'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Mark the badge as claimed
        participant_badge.is_claimed = True
        participant_badge.claimed_date = datetime.datetime.now()
        participant_badge.save()
        
        # Update participant's badges count
        participant.badges_earned += 1
        
        # Check if participant should be promoted to super mentor
        if participant.badges_earned >= 5:
            participant.is_super_mentor = True
        
        participant.save()
        
        return Response({
            'message': f'Badge "{badge.name}" claimed successfully',
            'participant_badge': ParticipantBadgeSerializer(participant_badge).data,
            'badges_earned': participant.badges_earned,
            'is_super_mentor': participant.is_super_mentor
        }, status=status.HTTP_200_OK)
        
    except Participant.DoesNotExist:
        return Response({
            'error': f'Participant with ID {participant_id} not found'
        }, status=status.HTTP_404_NOT_FOUND)
    except Badge.DoesNotExist:
        return Response({
            'error': f'Badge with ID {badge_id} not found'
        }, status=status.HTTP_404_NOT_FOUND)

@api_view(['GET'])
def get_participant_badges(request, registration_no):
    """Get all badges for a specific participant"""
    try:
        participant = Participant.objects.get(registration_no=registration_no)
        participant_badges = ParticipantBadge.objects.filter(participant=participant)
        serializer = ParticipantBadgeSerializer(participant_badges, many=True)
        
        return Response({
            'participant': {
                'name': participant.name,
                'registration_no': participant.registration_no,
                'badges_earned': participant.badges_earned,
                'is_super_mentor': participant.is_super_mentor
            },
            'badges': serializer.data
        }, status=status.HTTP_200_OK)
        
    except Participant.DoesNotExist:
        return Response({
            'error': f'Participant with registration number {registration_no} not found'
        }, status=status.HTTP_404_NOT_FOUND)

@api_view(['POST'])
def update_leaderboard_points(request):
    """Update a participant's leaderboard points"""
    registration_no = request.data.get('registration_no')
    points = request.data.get('points')
    
    if not registration_no or points is None:
        return Response({
            'error': 'Registration number and points are required'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        participant = Participant.objects.get(registration_no=registration_no)
        old_points = participant.leaderboard_points
        participant.leaderboard_points = int(points)
        participant.save()
        
        # Check if participant qualifies for any badges based on points
        eligible_badges = Badge.objects.filter(points_required__lte=participant.leaderboard_points)
        
        # Get badges participant already has
        existing_badge_ids = ParticipantBadge.objects.filter(participant=participant).values_list('badge_id', flat=True)
        
        # Award new eligible badges
        newly_awarded = []
        for badge in eligible_badges:
            if badge.id not in existing_badge_ids:
                ParticipantBadge.objects.create(
                    participant=participant,
                    badge=badge,
                    is_claimed=False
                )
                newly_awarded.append(badge.name)
        
        response_data = {
            'message': f'Leaderboard points updated from {old_points} to {points}',
            'participant': {
                'name': participant.name,
                'registration_no': participant.registration_no,
                'leaderboard_points': participant.leaderboard_points
            }
        }
        
        if newly_awarded:
            response_data['newly_eligible_badges'] = newly_awarded
        
        return Response(response_data, status=status.HTTP_200_OK)
        
    except Participant.DoesNotExist:
        return Response({
            'error': f'Participant with registration number {registration_no} not found'
        }, status=status.HTTP_404_NOT_FOUND)

# Leaderboard management functions

@api_view(['POST'])
def sync_leaderboard_points(request):
    """Sync the leaderboard points from the frontend to store in the database"""
    try:
        leaderboard_data = request.data.get('leaderboard_data', [])
        
        if not leaderboard_data:
            return Response({
                'error': 'No leaderboard data provided'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        updated_participants = []
        
        for entry in leaderboard_data:
            participant_id = entry.get('id')
            score = entry.get('score', 0)
            
            if not participant_id:
                continue
                
            try:
                participant = Participant.objects.get(registration_no=participant_id)
                participant.leaderboard_points = score
                participant.save()
                
                # Check if participant qualifies for any badges based on points
                eligible_badges = Badge.objects.filter(points_required__lte=score)
                
                # Get badges participant already has
                existing_badge_ids = ParticipantBadge.objects.filter(participant=participant).values_list('badge_id', flat=True)
                
                # Award new eligible badges
                newly_awarded = []
                for badge in eligible_badges:
                    if badge.id not in existing_badge_ids:
                        ParticipantBadge.objects.create(
                            participant=participant,
                            badge=badge,
                            is_claimed=False
                        )
                        newly_awarded.append(badge.name)
                
                participant_data = {
                    'registration_no': participant.registration_no,
                    'name': participant.name,
                    'leaderboard_points': participant.leaderboard_points,
                    'badges_earned': participant.badges_earned,
                    'is_super_mentor': participant.is_super_mentor
                }
                
                if newly_awarded:
                    participant_data['newly_awarded_badges'] = newly_awarded
                    
                updated_participants.append(participant_data)
                
            except Participant.DoesNotExist:
                # Skip participants that don't exist in the database
                continue
        
        return Response({
            'message': f'Successfully updated leaderboard points for {len(updated_participants)} participants',
            'updated_participants': updated_participants
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'error': 'Failed to sync leaderboard points',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
def calculate_leaderboard_points(request):
    """
    Calculate leaderboard points for all participants based on activities and store in the database.
    This is a server-side calculation that can be used as an alternative to frontend calculation.
    """
    try:
        # Get all approved and active participants
        participants = Participant.objects.filter(
            approval_status='approved',
            status='active'
        )
        
        updated_participants = []
        
        for participant in participants:
            # Initialize score components
            sessions_score = 0
            quiz_score = 0
            mentee_score = 0
            quiz_assignment_score = 0
            
            # Calculate score based on sessions 
            # Each session is worth 20 points (further reduced)
            sessions = Session.objects.filter(mentor=participant).count()
            sessions_as_participant = Session.objects.filter(participants=participant).count()
            sessions_score = (sessions * 20) + (sessions_as_participant * 10)  # Further reduced
            
            # Check if participant is a mentor (has mentees)
            mentor_relationships = MentorMenteeRelationship.objects.filter(mentor=participant)
            is_mentor = mentor_relationships.exists()
            
            # Points for quizzes assigned by mentor
            # Each quiz assigned is worth 5 points (further reduced)
            assigned_quizzes = QuizResult.objects.filter(mentor=participant)
            assigned_quiz_count = assigned_quizzes.count()
            quiz_assignment_score = assigned_quiz_count * 5  # Further reduced
            
            # Add points for completed quizzes with direct score
            completed_assigned_quizzes = assigned_quizzes.filter(status='completed')
            if completed_assigned_quizzes.exists():
                # Add points based on direct score (e.g., 4/5 = 4 points)
                for quiz in completed_assigned_quizzes:
                    quiz_assignment_score += quiz.score
            
            if is_mentor:
                # For mentors: Add points for each mentee and their quiz performance
                mentees = [rel.mentee for rel in mentor_relationships]
                mentee_count = len(mentees)
                mentee_score = mentee_count * 40  # Further reduced
                
                # Add score for mentee quiz performance
                for mentee in mentees:
                    # Get completed quizzes for this mentee
                    quizzes = QuizResult.objects.filter(
                        participant=mentee,
                        status='completed'
                    )
                    
                    if quizzes.exists():
                        # Add direct score from each quiz (e.g., 4/5 = 4 points)
                        for quiz in quizzes:
                            quiz_score += quiz.score
            else:
                # For mentees: Calculate scores based on their own quizzes
                quizzes = QuizResult.objects.filter(
                    participant=participant,
                    status='completed'
                )
                
                if quizzes.exists():
                    # Add direct score from each quiz (e.g., 4/5 = 4 points)
                    for quiz in quizzes:
                        quiz_score += quiz.score
            
            # Calculate total score - include quiz assignment points
            total_score = sessions_score + quiz_score + mentee_score + quiz_assignment_score
            
            # Add bonus for badges and super mentor status (further reduced)
            if participant.badges_earned > 0:
                total_score += participant.badges_earned * 20  # Further reduced
                
            if participant.is_super_mentor:
                total_score += 100  # Further reduced
            
            # Update participant's leaderboard points
            participant.leaderboard_points = total_score
            participant.save()
            
            # Check for badge eligibility based on new score
            eligible_badges = Badge.objects.filter(points_required__lte=total_score)
            existing_badge_ids = ParticipantBadge.objects.filter(participant=participant).values_list('badge_id', flat=True)
            
            # Award new eligible badges
            newly_awarded = []
            for badge in eligible_badges:
                if badge.id not in existing_badge_ids:
                    ParticipantBadge.objects.create(
                        participant=participant,
                        badge=badge,
                        is_claimed=False
                    )
                    newly_awarded.append(badge.name)
            
            # Add to results
            participant_data = {
                'registration_no': participant.registration_no,
                'name': participant.name,
                'role': 'mentor' if is_mentor else 'mentee',
                'sessions_score': sessions_score,
                'quiz_score': quiz_score,
                'mentee_score': mentee_score,
                'quiz_assignment_score': quiz_assignment_score,
                'total_score': total_score,
                'badges_earned': participant.badges_earned,
                'is_super_mentor': participant.is_super_mentor,
                'assigned_quizzes': assigned_quiz_count
            }
            
            if newly_awarded:
                participant_data['newly_awarded_badges'] = newly_awarded
                
            updated_participants.append(participant_data)
        
        # Sort by total score (highest first)
        updated_participants.sort(key=lambda p: p['total_score'], reverse=True)
        
        return Response({
            'message': f'Successfully calculated leaderboard points for {len(updated_participants)} participants',
            'updated_participants': updated_participants
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'error': 'Failed to calculate leaderboard points',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
def get_leaderboard(request):
    """Get the current leaderboard with participants sorted by leaderboard points"""
    try:
        # Get filter parameters
        role = request.query_params.get('role', 'all')  # 'mentor', 'mentee', or 'all'
        search = request.query_params.get('search', '')
        
        # Get approved and active participants
        participants = Participant.objects.filter(
            approval_status='approved',
            status='active'
        ).order_by('-leaderboard_points')
        
        # Apply role filter if specified
        if role == 'mentor':
            # Get registration numbers of all mentors
            mentor_reg_nos = MentorMenteeRelationship.objects.values_list('mentor__registration_no', flat=True).distinct()
            participants = participants.filter(registration_no__in=mentor_reg_nos)
        elif role == 'mentee':
            # Get registration numbers of all mentees
            mentee_reg_nos = MentorMenteeRelationship.objects.values_list('mentee__registration_no', flat=True).distinct()
            participants = participants.filter(registration_no__in=mentee_reg_nos)
        
        # Apply search filter if provided
        if search:
            participants = participants.filter(name__icontains=search)
        
        # Serialize the data
        leaderboard_data = []
        
        for participant in participants:
            # Determine role
            is_mentor = MentorMenteeRelationship.objects.filter(mentor=participant).exists()
            is_mentee = MentorMenteeRelationship.objects.filter(mentee=participant).exists()
            
            role = 'mentor' if is_mentor else 'mentee' if is_mentee else 'unknown'
            
            # Get mentor info for mentees
            mentor_name = 'Not assigned'
            mentor_id = None
            if is_mentee:
                relationship = MentorMenteeRelationship.objects.filter(mentee=participant).first()
                if relationship:
                    mentor_name = relationship.mentor.name
                    mentor_id = relationship.mentor.registration_no
            
            # Get mentee count for mentors
            mentees_count = 0
            if is_mentor:
                mentees_count = MentorMenteeRelationship.objects.filter(mentor=participant).count()
            
            # Get sessions
            sessions_attended = Session.objects.filter(
                models.Q(mentor=participant) | models.Q(participants=participant)
            ).distinct().count()
            
            # Get quizzes completed by the participant
            completed_quizzes = QuizResult.objects.filter(
                participant=participant, 
                status='completed'
            )
            quiz_count = completed_quizzes.count()
            avg_score = completed_quizzes.aggregate(models.Avg('percentage'))['percentage__avg'] or 0
            
            # Get quizzes assigned by the participant (if they're a mentor)
            assigned_quizzes = QuizResult.objects.filter(mentor=participant)
            assigned_quiz_count = assigned_quizzes.count()
            completed_assigned_count = assigned_quizzes.filter(status='completed').count()
            
            # Calculate average performance of assigned quizzes
            avg_assigned_score = 0
            if completed_assigned_count > 0:
                avg_assigned_score = assigned_quizzes.filter(status='completed').aggregate(
                    models.Avg('percentage')
                )['percentage__avg'] or 0
            
            # Add to leaderboard
            leaderboard_data.append({
                'id': participant.registration_no,
                'name': participant.name,
                'role': role,
                'mentorName': mentor_name,
                'mentorId': mentor_id,
                'menteesCount': mentees_count,
                'branch': participant.branch,
                'semester': participant.semester,
                'techStack': participant.tech_stack,
                'score': participant.leaderboard_points,
                'sessionsAttended': sessions_attended,
                'tasksCompleted': quiz_count,
                'averageScore': round(avg_score, 2),
                'feedbackGiven': calculate_feedback_level(avg_score),
                'badges_earned': participant.badges_earned,
                'is_super_mentor': participant.is_super_mentor,
                # New fields for assigned quizzes
                'assignedQuizzes': assigned_quiz_count,
                'completedAssignedQuizzes': completed_assigned_count,
                'averageAssignedScore': round(avg_assigned_score, 2)
            })
        
        return Response(leaderboard_data, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'error': 'Failed to fetch leaderboard data',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

def calculate_feedback_level(average_score):
    """Calculate feedback level based on average score"""
    if average_score >= 90:
        return "Excellent"
    if average_score >= 80:
        return "Very Good"
    if average_score >= 70:
        return "Good"
    if average_score >= 60:
        return "Satisfactory"
    return "Needs Improvement"

@api_view(['POST'])
def unclaim_badge(request):
    """Unclaim/delete a claimed badge from a participant"""
    try:
        participant_id = request.data.get('participant_id')
        badge_id = request.data.get('badge_id')
        
        if not participant_id or not badge_id:
            return Response({
                'error': 'Participant ID and badge ID are required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            participant = Participant.objects.get(registration_no=participant_id)
            badge = Badge.objects.get(id=badge_id)
        except Participant.DoesNotExist:
            return Response({
                'error': f'Participant with ID {participant_id} not found'
            }, status=status.HTTP_404_NOT_FOUND)
        except Badge.DoesNotExist:
            return Response({
                'error': f'Badge with ID {badge_id} not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Check if the participant has this badge
        try:
            participant_badge = ParticipantBadge.objects.get(
                participant=participant,
                badge=badge
            )
        except ParticipantBadge.DoesNotExist:
            return Response({
                'error': f'Participant does not have this badge'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Check if the badge was claimed
        was_claimed = participant_badge.is_claimed
        
        # Delete the participant badge
        participant_badge.delete()
        
        # If the badge was claimed, decrease the participant's claimed badge count
        if was_claimed:
            participant.badges_earned = max(0, participant.badges_earned - 1)
            
            # If the participant falls below 5 badges, they lose super mentor status
            if participant.badges_earned < 5 and participant.is_super_mentor:
                participant.is_super_mentor = False
                
            participant.save()
        
        return Response({
            'message': f'Badge "{badge.name}" has been removed from {participant.name}',
            'participant': {
                'name': participant.name,
                'registration_no': participant.registration_no,
                'badges_earned': participant.badges_earned,
                'is_super_mentor': participant.is_super_mentor
            }
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'error': 'Failed to unclaim badge',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['DELETE'])
def delete_participant_badge(request):
    """Completely delete a badge from a participant (admin only)"""
    try:
        participant_id = request.data.get('participant_id')
        badge_id = request.data.get('badge_id')
        force = request.data.get('force', False)  # Force delete even if claimed
        
        if not participant_id or not badge_id:
            return Response({
                'error': 'Participant ID and badge ID are required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            participant = Participant.objects.get(registration_no=participant_id)
            badge = Badge.objects.get(id=badge_id)
        except Participant.DoesNotExist:
            return Response({
                'error': f'Participant with ID {participant_id} not found'
            }, status=status.HTTP_404_NOT_FOUND)
        except Badge.DoesNotExist:
            return Response({
                'error': f'Badge with ID {badge_id} not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Check if the participant has this badge
        try:
            participant_badge = ParticipantBadge.objects.get(
                participant=participant,
                badge=badge
            )
        except ParticipantBadge.DoesNotExist:
            return Response({
                'error': f'Participant does not have this badge'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # If the badge is claimed and force is not True, prevent deletion
        if participant_badge.is_claimed and not force:
            return Response({
                'error': 'Cannot delete a claimed badge. Unclaim it first or use force=true.',
                'claimed': True
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Check if the badge was claimed
        was_claimed = participant_badge.is_claimed
        
        # Delete the participant badge
        participant_badge.delete()
        
        # If the badge was claimed, decrease the participant's claimed badge count
        if was_claimed:
            participant.badges_earned = max(0, participant.badges_earned - 1)
            
            # If the participant falls below 5 badges, they lose super mentor status
            if participant.badges_earned < 5 and participant.is_super_mentor:
                participant.is_super_mentor = False
                
            participant.save()
        
        return Response({
            'message': f'Badge "{badge.name}" has been deleted from {participant.name}',
            'was_claimed': was_claimed,
            'participant': {
                'name': participant.name,
                'registration_no': participant.registration_no,
                'badges_earned': participant.badges_earned,
                'is_super_mentor': participant.is_super_mentor
            }
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'error': 'Failed to delete badge',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['DELETE'])
def delete_badge_type(request, badge_id):
    """Delete a badge type completely from the system (admin only)"""
    try:
        try:
            badge = Badge.objects.get(id=badge_id)
        except Badge.DoesNotExist:
            return Response({
                'error': f'Badge with ID {badge_id} not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Check if there are any claimed instances of this badge
        claimed_instances = ParticipantBadge.objects.filter(
            badge=badge,
            is_claimed=True
        ).count()
        
        # Get total number of badge instances
        total_instances = ParticipantBadge.objects.filter(badge=badge).count()
        
        # Check if force delete is requested
        force_delete = request.data.get('force', False)
        
        # If there are claimed instances and force is not True, prevent deletion
        if claimed_instances > 0 and not force_delete:
            return Response({
                'error': 'Cannot delete badge type. There are participants who have claimed this badge.',
                'claimed_instances': claimed_instances,
                'total_instances': total_instances,
                'badge': {
                    'id': badge.id,
                    'name': badge.name
                },
                'force_required': True
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Store badge info for response
        badge_info = {
            'id': badge.id,
            'name': badge.name,
            'description': badge.description,
            'points_required': badge.points_required
        }
        
        # If we're force deleting, we need to update participant badges_earned counts
        if claimed_instances > 0:
            # Get all participants who claimed this badge
            affected_participants = []
            claimed_badges = ParticipantBadge.objects.filter(
                badge=badge,
                is_claimed=True
            )
            
            for claimed_badge in claimed_badges:
                participant = claimed_badge.participant
                
                # Decrement badge count
                participant.badges_earned = max(0, participant.badges_earned - 1)
                
                # Update super mentor status if needed
                if participant.badges_earned < 5 and participant.is_super_mentor:
                    participant.is_super_mentor = False
                
                participant.save()
                
                affected_participants.append({
                    'registration_no': participant.registration_no,
                    'name': participant.name,
                    'new_badge_count': participant.badges_earned,
                    'is_super_mentor': participant.is_super_mentor
                })
        
        # First, delete all ParticipantBadge instances
        deleted_instances = ParticipantBadge.objects.filter(badge=badge).delete()[0]
        
        # Then, delete the badge type itself
        badge.delete()
        
        response_data = {
            'message': f'Badge type "{badge_info["name"]}" has been deleted',
            'badge': badge_info,
            'instances_deleted': deleted_instances
        }
        
        if claimed_instances > 0:
            response_data['affected_participants'] = affected_participants
            response_data['claimed_instances_removed'] = claimed_instances
        
        return Response(response_data, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'error': 'Failed to delete badge type',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ----- Feedback Management Endpoints -----

@api_view(['POST'])
def update_feedback_settings(request):
    """Update feedback settings (global or department-specific)"""
    department_id = request.data.get('department_id', None)
    
    try:
        # Find the department if provided
        department = None
        if department_id:
            try:
                department = Department.objects.get(id=department_id)
            except Department.DoesNotExist:
                return Response({
                    'error': f'Department with ID {department_id} not found'
                }, status=status.HTTP_404_NOT_FOUND)
        
        # Try to get existing settings
        try:
            settings = FeedbackSettings.objects.get(department=department)
            old_mentor_feedback_enabled = settings.mentor_feedback_enabled
            old_app_feedback_enabled = settings.app_feedback_enabled
        except FeedbackSettings.DoesNotExist:
            # Create new settings if they don't exist
            settings = FeedbackSettings(department=department)
            old_mentor_feedback_enabled = False
            old_app_feedback_enabled = False
        
        # Track if feedback has been newly enabled
        mentor_feedback_newly_enabled = False
        app_feedback_newly_enabled = False
        
        # Update settings fields
        if 'mentor_feedback_enabled' in request.data:
            new_mentor_feedback_enabled = request.data.get('mentor_feedback_enabled')
            if not old_mentor_feedback_enabled and new_mentor_feedback_enabled:
                mentor_feedback_newly_enabled = True
            settings.mentor_feedback_enabled = new_mentor_feedback_enabled
        
        if 'app_feedback_enabled' in request.data:
            new_app_feedback_enabled = request.data.get('app_feedback_enabled')
            if not old_app_feedback_enabled and new_app_feedback_enabled:
                app_feedback_newly_enabled = True
            settings.app_feedback_enabled = new_app_feedback_enabled
        
        if 'allow_anonymous_feedback' in request.data:
            settings.allow_anonymous_feedback = request.data.get('allow_anonymous_feedback')
            
        # Handle dates (convert to datetime if provided)
        if 'feedback_start_date' in request.data and request.data.get('feedback_start_date'):
            settings.feedback_start_date = request.data.get('feedback_start_date')
            
        if 'feedback_end_date' in request.data and request.data.get('feedback_end_date'):
            settings.feedback_end_date = request.data.get('feedback_end_date')
            
        settings.save()
        
        # Send emails if feedback has been newly enabled and we're within the feedback window
        if mentor_feedback_newly_enabled or app_feedback_newly_enabled:
            # Check if we're within the feedback window
            now = timezone.now()
            within_window = True
            
            if settings.feedback_start_date and settings.feedback_end_date:
                within_window = (settings.feedback_start_date <= now <= settings.feedback_end_date)
            elif settings.feedback_start_date:
                within_window = (settings.feedback_start_date <= now)
            elif settings.feedback_end_date:
                within_window = (now <= settings.feedback_end_date)
                
            if within_window:
                # Import email utility
                from account.utils import Util
                
                # Get relevant participants
                if department:
                    # Department-specific
                    participants = Participant.objects.filter(
                        department=department,
                        approval_status='approved',
                        status='active'
                    )
                else:
                    # Global
                    participants = Participant.objects.filter(
                        approval_status='approved',
                        status='active'
                    )
                
                # Identify which participants should get mentor feedback notifications
                if mentor_feedback_newly_enabled:
                    # Find mentees
                    mentee_ids = MentorMenteeRelationship.objects.values_list('mentee__registration_no', flat=True)
                    mentees = participants.filter(registration_no__in=mentee_ids)
                    
                    # Don't notify mentees who have already submitted feedback
                    for mentee in mentees:
                        try:
                            # Check if this mentee has already given feedback
                            relationship = MentorMenteeRelationship.objects.get(mentee=mentee)
                            already_submitted = MentorFeedback.objects.filter(relationship=relationship).exists()
                            
                            if not already_submitted:
                                # Get the mentee's email
                                email = get_email_by_registration_no(mentee.registration_no)
                                mentor = relationship.mentor
                                
                                # Send mentor feedback email notification
                                mentor_feedback_body = f"Dear {mentee.name},\n\nThe mentor feedback window is now open! Please take a moment to provide feedback for your mentor, {mentor.name}.\n\nFeedback helps mentors improve and is valuable for the program's success.\n\nThank you,\nThe Team VidyaSangam"
                                mentor_feedback_data = {
                                    'subject': 'Mentor Feedback Window Now Open',
                                    'body': mentor_feedback_body,
                                    'to_email': email
                                }
                                Util.send_email(mentor_feedback_data)
                        except Exception as e:
                            print(f"Error sending mentor feedback email to {mentee.registration_no}: {str(e)}")
                
                # Send application feedback notifications to all participants
                if app_feedback_newly_enabled:
                    # Don't notify users who have already submitted app feedback
                    for participant in participants:
                        try:
                            already_submitted = ApplicationFeedback.objects.filter(participant=participant).exists()
                            
                            if not already_submitted:
                                # Get participant's email
                                email = get_email_by_registration_no(participant.registration_no)
                                
                                # Send app feedback email notification
                                app_feedback_body = f"Dear {participant.name},\n\nWe value your opinion! The application feedback window is now open. Please take a moment to share your thoughts on the VidyaSangam platform.\n\nYour feedback helps us improve the experience for everyone.\n\nThank you,\nThe Team VidyaSangam"
                                app_feedback_data = {
                                    'subject': 'Application Feedback Window Now Open',
                                    'body': app_feedback_body,
                                    'to_email': email
                                }
                                Util.send_email(app_feedback_data)
                        except Exception as e:
                            print(f"Error sending app feedback email to {participant.registration_no}: {str(e)}")
        
        serializer = FeedbackSettingsSerializer(settings)
        return Response({
            'message': 'Feedback settings updated successfully',
            'settings': serializer.data,
            'email_notifications': 'Sent' if (mentor_feedback_newly_enabled or app_feedback_newly_enabled) else 'Not sent'
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'error': 'Failed to update feedback settings',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
def get_feedback_settings(request):
    """Get feedback settings (global or department-specific)"""
    department_id = request.query_params.get('department_id', None)
    
    try:
        # Find the department if provided
        department = None
        if department_id:
            try:
                department = Department.objects.get(id=department_id)
            except Department.DoesNotExist:
                return Response({
                    'error': f'Department with ID {department_id} not found'
                }, status=status.HTTP_404_NOT_FOUND)
        
        # Try to get department-specific settings first
        if department:
            settings = FeedbackSettings.objects.filter(department=department).first()
            if settings:
                serializer = FeedbackSettingsSerializer(settings)
                return Response(serializer.data)
        
        # Fall back to global settings
        global_settings = FeedbackSettings.objects.filter(department=None).first()
        
        # If no settings exist at all, return default values
        if not global_settings:
            return Response({
                'mentor_feedback_enabled': False,
                'app_feedback_enabled': False,
                'allow_anonymous_feedback': True,
                'feedback_start_date': None,
                'feedback_end_date': None,
                'is_global': True,
                'department': None,
                'department_name': None
            })
            
        serializer = FeedbackSettingsSerializer(global_settings)
        return Response(serializer.data)
        
    except Exception as e:
        return Response({
            'error': 'Failed to retrieve feedback settings',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
def check_feedback_eligibility(request, registration_no):
    """Check if a participant is eligible to submit feedback"""
    try:
        participant = Participant.objects.get(registration_no=registration_no)
        
        # Get participant's department
        department = participant.department
        
        # Check if feedback is enabled (department-specific or global)
        department_settings = None
        if department:
            department_settings = FeedbackSettings.objects.filter(department=department).first()
            
        global_settings = FeedbackSettings.objects.filter(department=None).first()
        
        # Use department settings if available, otherwise global settings
        settings = department_settings or global_settings
        
        if not settings:
            return Response({
                'mentor_feedback_eligible': False,
                'app_feedback_eligible': False,
                'message': 'Feedback is not currently enabled'
            })
        
        # Check if within feedback window (if dates are set)
        # Use timezone-aware datetime for comparison
        now = timezone.now()
        within_window = True
        
        if settings.feedback_start_date and settings.feedback_end_date:
            within_window = (settings.feedback_start_date <= now <= settings.feedback_end_date)
        elif settings.feedback_start_date:
            within_window = (settings.feedback_start_date <= now)
        elif settings.feedback_end_date:
            within_window = (now <= settings.feedback_end_date)
            
        if not within_window:
            return Response({
                'mentor_feedback_eligible': False,
                'app_feedback_eligible': False,
                'message': 'Outside of feedback submission window',
                'window': {
                    'start_date': settings.feedback_start_date,
                    'end_date': settings.feedback_end_date
                }
            })
            
        # For mentor feedback, check if participant is a mentee
        is_mentee = MentorMenteeRelationship.objects.filter(mentee=participant).exists()
        
        # Check if mentee has already submitted feedback for their mentor
        already_submitted_mentor_feedback = False
        if is_mentee:
            relationship = MentorMenteeRelationship.objects.get(mentee=participant)
            already_submitted_mentor_feedback = MentorFeedback.objects.filter(
                relationship=relationship
            ).exists()
            
        # Check if participant has already submitted app feedback
        already_submitted_app_feedback = ApplicationFeedback.objects.filter(
            participant=participant
        ).exists()
        
        return Response({
            'mentor_feedback_eligible': settings.mentor_feedback_enabled and is_mentee and not already_submitted_mentor_feedback,
            'app_feedback_eligible': settings.app_feedback_enabled and not already_submitted_app_feedback,
            'allow_anonymous_feedback': settings.allow_anonymous_feedback,
            'is_mentee': is_mentee,
            'already_submitted_mentor_feedback': already_submitted_mentor_feedback,
            'already_submitted_app_feedback': already_submitted_app_feedback,
            'window': {
                'start_date': settings.feedback_start_date,
                'end_date': settings.feedback_end_date
            }
        })
        
    except Participant.DoesNotExist:
        return Response({
            'error': f'Participant with registration number {registration_no} not found'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            'error': 'Failed to check feedback eligibility',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
def submit_mentor_feedback(request):
    """Submit feedback for a mentor"""
    mentee_id = request.data.get('mentee_id')
    
    if not mentee_id:
        return Response({
            'error': 'Mentee ID is required'
        }, status=status.HTTP_400_BAD_REQUEST)
        
    try:
        # Get the mentee
        mentee = Participant.objects.get(registration_no=mentee_id)
        
        # Check if mentee has a mentor
        try:
            relationship = MentorMenteeRelationship.objects.get(mentee=mentee)
        except MentorMenteeRelationship.DoesNotExist:
            return Response({
                'error': 'Mentee does not have an assigned mentor'
            }, status=status.HTTP_400_BAD_REQUEST)
            
        mentor = relationship.mentor
        
        # Check if feedback already exists
        if MentorFeedback.objects.filter(relationship=relationship).exists():
            return Response({
                'error': 'Feedback has already been submitted for this mentor-mentee relationship',
                'message': 'You can only submit feedback once'
            }, status=status.HTTP_400_BAD_REQUEST)
            
        # Check eligibility based on settings
        department = mentee.department
        
        # Check if feedback is enabled (department-specific or global)
        department_settings = None
        if department:
            department_settings = FeedbackSettings.objects.filter(department=department).first()
            
        global_settings = FeedbackSettings.objects.filter(department=None).first()
        
        # Use department settings if available, otherwise global settings
        settings = department_settings or global_settings
        
        if not settings or not settings.mentor_feedback_enabled:
            return Response({
                'error': 'Mentor feedback is not currently enabled'
            }, status=status.HTTP_403_FORBIDDEN)
            
        # Check if within feedback window (if dates are set)
        now = timezone.now()
        within_window = True
        
        if settings.feedback_start_date and settings.feedback_end_date:
            within_window = (settings.feedback_start_date <= now <= settings.feedback_end_date)
        elif settings.feedback_start_date:
            within_window = (settings.feedback_start_date <= now)
        elif settings.feedback_end_date:
            within_window = (now <= settings.feedback_end_date)
            
        if not within_window:
            return Response({
                'error': 'Outside of feedback submission window',
                'window': {
                    'start_date': settings.feedback_start_date,
                    'end_date': settings.feedback_end_date
                }
            }, status=status.HTTP_403_FORBIDDEN)
            
        # Validate required fields
        required_fields = [
            'communication_rating', 
            'knowledge_rating', 
            'availability_rating', 
            'helpfulness_rating', 
            'overall_rating'
        ]
        
        for field in required_fields:
            if field not in request.data or not request.data.get(field):
                return Response({
                    'error': f'Field {field} is required'
                }, status=status.HTTP_400_BAD_REQUEST)
                
        # Get optional fields
        strengths = request.data.get('strengths', '')
        areas_for_improvement = request.data.get('areas_for_improvement', '')
        additional_comments = request.data.get('additional_comments', '')
        anonymous = request.data.get('anonymous', False)
        
        # Ensure anonymous feedback is allowed if requested
        if anonymous and not settings.allow_anonymous_feedback:
            return Response({
                'error': 'Anonymous feedback is not allowed',
                'message': 'Please submit feedback with your identity'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Create the feedback
        feedback = MentorFeedback.objects.create(
            relationship=relationship,
            mentor=mentor,
            mentee=mentee,
            communication_rating=request.data.get('communication_rating'),
            knowledge_rating=request.data.get('knowledge_rating'),
            availability_rating=request.data.get('availability_rating'),
            helpfulness_rating=request.data.get('helpfulness_rating'),
            overall_rating=request.data.get('overall_rating'),
            strengths=strengths,
            areas_for_improvement=areas_for_improvement,
            additional_comments=additional_comments,
            anonymous=anonymous
        )
        
        # Return the created feedback
        serializer = MentorFeedbackSerializer(feedback)
        return Response({
            'message': 'Mentor feedback submitted successfully',
            'feedback': serializer.data
        }, status=status.HTTP_201_CREATED)
        
    except Participant.DoesNotExist:
        return Response({
            'error': f'Participant with registration number {mentee_id} not found'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            'error': 'Failed to submit mentor feedback',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
def submit_app_feedback(request):
    """Submit feedback about the application"""
    participant_id = request.data.get('participant_id')
    
    if not participant_id:
        return Response({
            'error': 'Participant ID is required'
        }, status=status.HTTP_400_BAD_REQUEST)
        
    try:
        # Get the participant
        participant = Participant.objects.get(registration_no=participant_id)
        
        # Check if feedback already exists
        if ApplicationFeedback.objects.filter(participant=participant).exists():
            return Response({
                'error': 'App feedback has already been submitted by this participant',
                'message': 'You can only submit feedback once'
            }, status=status.HTTP_400_BAD_REQUEST)
            
        # Check eligibility based on settings
        department = participant.department
        
        # Check if feedback is enabled (department-specific or global)
        department_settings = None
        if department:
            department_settings = FeedbackSettings.objects.filter(department=department).first()
            
        global_settings = FeedbackSettings.objects.filter(department=None).first()
        
        # Use department settings if available, otherwise global settings
        settings = department_settings or global_settings
        
        if not settings or not settings.app_feedback_enabled:
            return Response({
                'error': 'Application feedback is not currently enabled'
            }, status=status.HTTP_403_FORBIDDEN)
            
        # Check if within feedback window (if dates are set)
        now = timezone.now()
        within_window = True
        
        if settings.feedback_start_date and settings.feedback_end_date:
            within_window = (settings.feedback_start_date <= now <= settings.feedback_end_date)
        elif settings.feedback_start_date:
            within_window = (settings.feedback_start_date <= now)
        elif settings.feedback_end_date:
            within_window = (now <= settings.feedback_end_date)
            
        if not within_window:
            return Response({
                'error': 'Outside of feedback submission window',
                'window': {
                    'start_date': settings.feedback_start_date,
                    'end_date': settings.feedback_end_date
                }
            }, status=status.HTTP_403_FORBIDDEN)
            
        # Validate required fields
        required_fields = [
            'usability_rating', 
            'features_rating', 
            'performance_rating', 
            'overall_rating',
            'nps_score'
        ]
        
        for field in required_fields:
            if field not in request.data or request.data.get(field) is None:
                return Response({
                    'error': f'Field {field} is required'
                }, status=status.HTTP_400_BAD_REQUEST)
                
        # Get optional fields
        what_you_like = request.data.get('what_you_like', '')
        what_to_improve = request.data.get('what_to_improve', '')
        feature_requests = request.data.get('feature_requests', '')
        additional_comments = request.data.get('additional_comments', '')
        anonymous = request.data.get('anonymous', False)
        
        # Ensure anonymous feedback is allowed if requested
        if anonymous and not settings.allow_anonymous_feedback:
            return Response({
                'error': 'Anonymous feedback is not allowed',
                'message': 'Please submit feedback with your identity'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Create the feedback
        feedback = ApplicationFeedback.objects.create(
            participant=participant,
            usability_rating=request.data.get('usability_rating'),
            features_rating=request.data.get('features_rating'),
            performance_rating=request.data.get('performance_rating'),
            overall_rating=request.data.get('overall_rating'),
            nps_score=request.data.get('nps_score'),
            what_you_like=what_you_like,
            what_to_improve=what_to_improve,
            feature_requests=feature_requests,
            additional_comments=additional_comments,
            anonymous=anonymous
        )
        
        # Return the created feedback
        serializer = ApplicationFeedbackSerializer(feedback)
        return Response({
            'message': 'Application feedback submitted successfully',
            'feedback': serializer.data
        }, status=status.HTTP_201_CREATED)
        
    except Participant.DoesNotExist:
        return Response({
            'error': f'Participant with registration number {participant_id} not found'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            'error': 'Failed to submit application feedback',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
def get_mentor_feedback(request, mentor_id):
    """Get all feedback for a specific mentor"""
    try:
        mentor = Participant.objects.get(registration_no=mentor_id)
        
        # Get all feedback for this mentor
        feedback = MentorFeedback.objects.filter(mentor=mentor)
        
        # Calculate average ratings
        avg_ratings = {
            'communication': feedback.aggregate(models.Avg('communication_rating'))['communication_rating__avg'] or 0,
            'knowledge': feedback.aggregate(models.Avg('knowledge_rating'))['knowledge_rating__avg'] or 0,
            'availability': feedback.aggregate(models.Avg('availability_rating'))['availability_rating__avg'] or 0,
            'helpfulness': feedback.aggregate(models.Avg('helpfulness_rating'))['helpfulness_rating__avg'] or 0,
            'overall': feedback.aggregate(models.Avg('overall_rating'))['overall_rating__avg'] or 0
        }
        
        # Round the averages to 2 decimal places
        for key in avg_ratings:
            avg_ratings[key] = round(avg_ratings[key], 2)
            
        # Serialize the feedback
        serializer = MentorFeedbackSerializer(feedback, many=True)
        
        return Response({
            'mentor': {
                'name': mentor.name,
                'registration_no': mentor.registration_no
            },
            'feedback_count': feedback.count(),
            'average_ratings': avg_ratings,
            'feedback': serializer.data
        })
        
    except Participant.DoesNotExist:
        return Response({
            'error': f'Mentor with registration number {mentor_id} not found'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            'error': 'Failed to retrieve mentor feedback',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
def get_app_feedback_summary(request):
    """Get a summary of all application feedback (admin only)"""
    try:
        # Get all application feedback
        feedback = ApplicationFeedback.objects.all()
        
        # Calculate average ratings
        avg_ratings = {
            'usability': feedback.aggregate(models.Avg('usability_rating'))['usability_rating__avg'] or 0,
            'features': feedback.aggregate(models.Avg('features_rating'))['features_rating__avg'] or 0,
            'performance': feedback.aggregate(models.Avg('performance_rating'))['performance_rating__avg'] or 0,
            'overall': feedback.aggregate(models.Avg('overall_rating'))['overall_rating__avg'] or 0,
            'nps': feedback.aggregate(models.Avg('nps_score'))['nps_score__avg'] or 0
        }
        
        # Round the averages to 2 decimal places
        for key in avg_ratings:
            avg_ratings[key] = round(avg_ratings[key], 2)
            
        # Calculate NPS categories
        nps_promoters = feedback.filter(nps_score__gte=9).count()
        nps_passives = feedback.filter(nps_score__gte=7, nps_score__lte=8).count()
        nps_detractors = feedback.filter(nps_score__lte=6).count()
        
        # Calculate NPS score
        total_responses = feedback.count()
        nps_score = 0
        
        if total_responses > 0:
            nps_score = round(((nps_promoters / total_responses) - (nps_detractors / total_responses)) * 100)
            
        # Serialize the feedback
        serializer = ApplicationFeedbackSerializer(feedback, many=True)
        
        return Response({
            'feedback_count': total_responses,
            'average_ratings': avg_ratings,
            'nps': {
                'score': nps_score,
                'promoters': nps_promoters,
                'passives': nps_passives,
                'detractors': nps_detractors
            },
            'feedback': serializer.data
        })
        
    except Exception as e:
        return Response({
            'error': 'Failed to retrieve application feedback summary',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['DELETE'])
def delete_feedback(request):
    """Delete a specific feedback instance (admin only)"""
    feedback_type = request.data.get('feedback_type')  # 'mentor' or 'app'
    feedback_id = request.data.get('feedback_id')
    
    if not feedback_type or not feedback_id:
        return Response({
            'error': 'Feedback type and ID are required'
        }, status=status.HTTP_400_BAD_REQUEST)
        
    if feedback_type not in ['mentor', 'app']:
        return Response({
            'error': 'Invalid feedback type. Must be "mentor" or "app"'
        }, status=status.HTTP_400_BAD_REQUEST)
        
    try:
        if feedback_type == 'mentor':
            try:
                feedback = MentorFeedback.objects.get(id=feedback_id)
            except MentorFeedback.DoesNotExist:
                return Response({
                    'error': f'Mentor feedback with ID {feedback_id} not found'
                }, status=status.HTTP_404_NOT_FOUND)
                
            # Store details for response
            mentor_name = feedback.mentor.name
            mentee_name = "Anonymous" if feedback.anonymous else feedback.mentee.name
            
            # Delete the feedback
            feedback.delete()
            
            return Response({
                'message': f'Mentor feedback from {mentee_name} for {mentor_name} deleted successfully'
            }, status=status.HTTP_200_OK)
        else:  # app feedback
            try:
                feedback = ApplicationFeedback.objects.get(id=feedback_id)
            except ApplicationFeedback.DoesNotExist:
                return Response({
                    'error': f'Application feedback with ID {feedback_id} not found'
                }, status=status.HTTP_404_NOT_FOUND)
                
            # Store details for response
            participant_name = "Anonymous" if feedback.anonymous else feedback.participant.name
            
            # Delete the feedback
            feedback.delete()
            
            return Response({
                'message': f'Application feedback from {participant_name} deleted successfully'
            }, status=status.HTTP_200_OK)
            
    except Exception as e:
        return Response({
            'error': 'Failed to delete feedback',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
def send_feedback_reminders(request):
    """Send email reminders about open feedback to eligible participants"""
    department_id = request.data.get('department_id', None)
    feedback_type = request.data.get('feedback_type', 'all')  # 'mentor', 'app', or 'all'
    
    if feedback_type not in ['mentor', 'app', 'all']:
        return Response({
            'error': 'Invalid feedback type. Must be "mentor", "app", or "all"'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        # Find the department if provided
        department = None
        if department_id:
            try:
                department = Department.objects.get(id=department_id)
            except Department.DoesNotExist:
                return Response({
                    'error': f'Department with ID {department_id} not found'
                }, status=status.HTTP_404_NOT_FOUND)
        
        # Get feedback settings (department-specific or global)
        department_settings = None
        if department:
            department_settings = FeedbackSettings.objects.filter(department=department).first()
            
        global_settings = FeedbackSettings.objects.filter(department=None).first()
        
        # Use department settings if available, otherwise global settings
        settings = department_settings or global_settings
        
        if not settings:
            return Response({
                'error': 'No feedback settings found',
                'message': 'Please configure feedback settings first'
            }, status=status.HTTP_400_BAD_REQUEST)
            
        # Check if feedback is enabled
        mentor_feedback_enabled = settings.mentor_feedback_enabled
        app_feedback_enabled = settings.app_feedback_enabled
        
        if feedback_type == 'mentor' and not mentor_feedback_enabled:
            return Response({
                'error': 'Mentor feedback is not currently enabled',
                'message': 'Enable mentor feedback before sending reminders'
            }, status=status.HTTP_400_BAD_REQUEST)
            
        if feedback_type == 'app' and not app_feedback_enabled:
            return Response({
                'error': 'Application feedback is not currently enabled',
                'message': 'Enable application feedback before sending reminders'
            }, status=status.HTTP_400_BAD_REQUEST)
            
        if feedback_type == 'all' and not (mentor_feedback_enabled or app_feedback_enabled):
            return Response({
                'error': 'No feedback is currently enabled',
                'message': 'Enable at least one type of feedback before sending reminders'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Check if we're within the feedback window
        now = timezone.now()
        within_window = True
        
        if settings.feedback_start_date and settings.feedback_end_date:
            within_window = (settings.feedback_start_date <= now <= settings.feedback_end_date)
        elif settings.feedback_start_date:
            within_window = (settings.feedback_start_date <= now)
        elif settings.feedback_end_date:
            within_window = (now <= settings.feedback_end_date)
            
        if not within_window:
            return Response({
                'error': 'Outside of feedback submission window',
                'window': {
                    'start_date': settings.feedback_start_date,
                    'end_date': settings.feedback_end_date
                },
                'message': 'Cannot send reminders outside of feedback window'
            }, status=status.HTTP_400_BAD_REQUEST)
            
        # Import email utility
        from account.utils import Util
        
        # Get relevant participants
        if department:
            # Department-specific
            participants = Participant.objects.filter(
                department=department,
                approval_status='approved',
                status='active'
            )
        else:
            # Global
            participants = Participant.objects.filter(
                approval_status='approved',
                status='active'
            )
            
        emails_sent = 0
        errors = 0
        
        # Send mentor feedback reminders
        if feedback_type in ['mentor', 'all'] and mentor_feedback_enabled:
            # Find mentees
            mentee_ids = MentorMenteeRelationship.objects.values_list('mentee__registration_no', flat=True)
            mentees = participants.filter(registration_no__in=mentee_ids)
            
            # Don't send to mentees who have already submitted feedback
            for mentee in mentees:
                try:
                    # Check if this mentee has already given feedback
                    relationship = MentorMenteeRelationship.objects.get(mentee=mentee)
                    already_submitted = MentorFeedback.objects.filter(relationship=relationship).exists()
                    
                    if not already_submitted:
                        # Get the mentee's email
                        email = get_email_by_registration_no(mentee.registration_no)
                        mentor = relationship.mentor
                        
                        # Get deadline info for the email
                        deadline_text = ""
                        if settings.feedback_end_date:
                            deadline = settings.feedback_end_date.strftime("%Y-%m-%d")
                            deadline_text = f"\n\nPlease submit your feedback by {deadline}."
                        
                        # Send mentor feedback email notification
                        mentor_feedback_body = f"Dear {mentee.name},\n\nThis is a reminder that the mentor feedback window is open! Please take a moment to provide feedback for your mentor, {mentor.name}.{deadline_text}\n\nFeedback helps mentors improve and is valuable for the program's success.\n\nThank you,\nThe Team VidyaSangam"
                        mentor_feedback_data = {
                            'subject': 'Reminder: Mentor Feedback',
                            'body': mentor_feedback_body,
                            'to_email': email
                        }
                        Util.send_email(mentor_feedback_data)
                        emails_sent += 1
                except Exception as e:
                    print(f"Error sending mentor feedback reminder to {mentee.registration_no}: {str(e)}")
                    errors += 1
        
        # Send app feedback reminders
        if feedback_type in ['app', 'all'] and app_feedback_enabled:
            # Don't send to users who have already submitted app feedback
            for participant in participants:
                try:
                    already_submitted = ApplicationFeedback.objects.filter(participant=participant).exists()
                    
                    if not already_submitted:
                        # Get participant's email
                        email = get_email_by_registration_no(participant.registration_no)
                        
                        # Get deadline info for the email
                        deadline_text = ""
                        if settings.feedback_end_date:
                            deadline = settings.feedback_end_date.strftime("%Y-%m-%d")
                            deadline_text = f"\n\nPlease submit your feedback by {deadline}."
                        
                        # Send app feedback email notification
                        app_feedback_body = f"Dear {participant.name},\n\nThis is a reminder that we value your opinion! The application feedback window is currently open. Please take a moment to share your thoughts on the VidyaSangam platform.{deadline_text}\n\nYour feedback helps us improve the experience for everyone.\n\nThank you,\nThe Team VidyaSangam"
                        app_feedback_data = {
                            'subject': 'Reminder: Application Feedback',
                            'body': app_feedback_body,
                            'to_email': email
                        }
                        Util.send_email(app_feedback_data)
                        emails_sent += 1
                except Exception as e:
                    print(f"Error sending app feedback reminder to {participant.registration_no}: {str(e)}")
                    errors += 1
        
        return Response({
            'message': 'Feedback reminders sent successfully',
            'emails_sent': emails_sent,
            'errors': errors,
            'feedback_types': feedback_type
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'error': 'Failed to send feedback reminders',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

def view_proof(request, registration_no, proof_type):
    """
    Django view to serve proof files (stored as BLOB) for a participant.
    Supports dynamic content type based on optional 'filetype' GET parameter.
    Usage: /participant/<registration_no>/proof/<proof_type>/?filetype=pdf|png|jpeg
    """
    from .models import Participant
    # Get the participant or return 404
    try:
        participant = Participant.objects.get(registration_no=registration_no)
    except Participant.DoesNotExist:
        raise Http404("Participant not found.")

    # Map proof_type to the correct field
    proof_field = {
        'research': participant.proof_of_research_publications,
        'hackathon': participant.proof_of_hackathon_participation,
        'coding': participant.proof_of_coding_competitions,
        'academic': participant.proof_of_academic_performance,
        'internship': participant.proof_of_internships,
        'extracurricular': participant.proof_of_extracurricular_activities,
    }.get(proof_type)

    if not proof_field:
        raise Http404("Proof not found.")

    # Determine content type from GET param or default to PDF
    filetype = request.GET.get('filetype', 'pdf').lower()
    content_types = {
        'pdf': 'application/pdf',
        'png': 'image/png',
        'jpg': 'image/jpeg',
        'jpeg': 'image/jpeg',
    }
    content_type = content_types.get(filetype, 'application/pdf')

    # Optionally, set Content-Disposition for inline display
    response = HttpResponse(proof_field, content_type=content_type)
    response['Content-Disposition'] = f'inline; filename="{proof_type}_proof_{registration_no}.{filetype}"'
    return response

@api_view(['POST'])
def generate_linkedin_preview(request):
    """
    Generate and preview LinkedIn post content without posting it
    """
    try:
        # Extract data from request
        data = request.data
        badge_name = data.get('badgeName')
        achievement_details = data.get('achievementDetails')
        participant_id = data.get('participant_id')  # ID of the participant who owns the badge
        badge_id = data.get('badge_id')  # ID of the badge being shared
        
        if not badge_name or not achievement_details:
            return Response({
                'error': 'Badge name and achievement details are required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Generate content using Gemini
        content, error = generate_linkedin_post_content(badge_name, achievement_details)
        if error:
            return Response({
                'error': 'Failed to generate post content',
                'details': error
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        # Check if the badge is already shared on LinkedIn
        linkedin_shared = False
        if participant_id and badge_id:
            try:
                participant = Participant.objects.get(registration_no=participant_id)
                participant_badge = ParticipantBadge.objects.get(participant=participant, badge__id=badge_id)
                linkedin_shared = participant_badge.linkedin_shared
            except (Participant.DoesNotExist, ParticipantBadge.DoesNotExist):
                # If no badge found, continue without error
                pass
            
        # Return the generated content for preview with badge info
        response_data = {
            'preview_content': content,
            'badge_name': badge_name,
            'message': 'Preview content generated successfully. Use the linkedin/post/ endpoint to post to LinkedIn.'
        }
        
        # Include badge and participant IDs if provided
        if badge_id:
            response_data['badge_id'] = badge_id
        if participant_id:
            response_data['participant_id'] = participant_id
        if linkedin_shared:
            response_data['linkedin_shared'] = True
            
        return Response(response_data, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'error': 'An error occurred',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
def get_participant_proofs(request, registration_no):
    """Get a participant's proof documents."""
    try:
        participant = Participant.objects.get(registration_no=registration_no)
        
        # Create a dictionary of proofs with base64 encoding
        proofs = {}
        
        # Helper function to encode binary data
        def encode_proof(binary_data):
            if binary_data:
                try:
                    return base64.b64encode(binary_data).decode('utf-8')
                except:
                    return None
            return None
        
        # Add each proof with proper encoding
        if participant.proof_of_research_publications:
            proofs['research_publications'] = encode_proof(participant.proof_of_research_publications)
            
        if participant.proof_of_hackathon_participation:
            proofs['hackathon_participation'] = encode_proof(participant.proof_of_hackathon_participation)
            
        if participant.proof_of_coding_competitions:
            proofs['coding_competitions'] = encode_proof(participant.proof_of_coding_competitions)
            
        if participant.proof_of_academic_performance:
            proofs['academic_performance'] = encode_proof(participant.proof_of_academic_performance)
            
        if participant.proof_of_internships:
            proofs['internships'] = encode_proof(participant.proof_of_internships)
            
        if participant.proof_of_extracurricular_activities:
            proofs['extracurricular_activities'] = encode_proof(participant.proof_of_extracurricular_activities)
        
        if not proofs:
            return Response({
                "message": "No proofs found for this participant"
            }, status=status.HTTP_404_NOT_FOUND)
            
        return Response(proofs)
        
    except Participant.DoesNotExist:
        return Response({
            "error": "Participant not found"
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            "error": "Failed to fetch proofs",
            "details": str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
def user_activity_heatmap(request, registration_no):
    """
    Returns daily activity data for a user for the last 6 months, suitable for a calendar heatmap.
    Supports filtering by activity type via ?type=quiz|session|badge|feedback
    """
    activity_type = request.query_params.get('type', None)
    end_date = timezone.now().date()
    start_date = end_date - timedelta(days=180)
    activity_counts = {}

    # Quiz completions (including archived)
    if activity_type in [None, '', 'quiz', 'all']:
        from .models import QuizResult
        quiz_qs = QuizResult.objects.filter(
            participant__registration_no=registration_no,
            completed_date__date__gte=start_date,
            completed_date__date__lte=end_date
        )
        quiz_by_day = quiz_qs.annotate(date=TruncDate('completed_date')).values('date').annotate(count=Count('id')).values('date', 'count')
        for entry in quiz_by_day:
            d = entry['date'].strftime('%Y-%m-%d')
            activity_counts[d] = activity_counts.get(d, 0) + entry['count']

    # Session attendance (including archived)
    if activity_type in [None, '', 'session', 'all']:
        from .models import Session, Participant
        try:
            session_qs = Session.objects.filter(
                Q(participants__registration_no=registration_no) | Q(mentor__registration_no=registration_no),
                date_time__date__gte=start_date,
                date_time__date__lte=end_date
            )
            session_by_day = session_qs.annotate(date=TruncDate('date_time')).values('date').annotate(count=Count('session_id')).values('date', 'count')
            for entry in session_by_day:
                d = entry['date'].strftime('%Y-%m-%d')
                activity_counts[d] = activity_counts.get(d, 0) + entry['count']
        except Exception as e:
            print(f"Error fetching sessions: {e}")

    # Badge claims (including archived)
    if activity_type in [None, '', 'badge', 'all']:
        from .models import ParticipantBadge
        badge_qs = ParticipantBadge.objects.filter(
            participant__registration_no=registration_no,
            claimed_date__date__gte=start_date,
            claimed_date__date__lte=end_date
        )
        badge_by_day = badge_qs.annotate(date=TruncDate('claimed_date')).values('date').annotate(count=Count('id')).values('date', 'count')
        for entry in badge_by_day:
            d = entry['date'].strftime('%Y-%m-%d')
            activity_counts[d] = activity_counts.get(d, 0) + entry['count']

    # Feedback submissions (including archived)
    if activity_type in [None, '', 'feedback', 'all']:
        from .models import MentorFeedback, ApplicationFeedback
        feedback_qs = MentorFeedback.objects.filter(
            Q(mentee__registration_no=registration_no) | Q(mentor__registration_no=registration_no),
            created_at__date__gte=start_date,
            created_at__date__lte=end_date
        )
        feedback_by_day = feedback_qs.annotate(date=TruncDate('created_at')).values('date').annotate(count=Count('id')).values('date', 'count')
        for entry in feedback_by_day:
            d = entry['date'].strftime('%Y-%m-%d')
            activity_counts[d] = activity_counts.get(d, 0) + entry['count']
        app_feedback_qs = ApplicationFeedback.objects.filter(
            participant__registration_no=registration_no,
            created_at__date__gte=start_date,
            created_at__date__lte=end_date
        )
        app_feedback_by_day = app_feedback_qs.annotate(date=TruncDate('created_at')).values('date').annotate(count=Count('id')).values('date', 'count')
        for entry in app_feedback_by_day:
            d = entry['date'].strftime('%Y-%m-%d')
            activity_counts[d] = activity_counts.get(d, 0) + entry['count']

    # Get archived activity from ParticipantHistory
    from .models import ParticipantHistory
    history_qs = ParticipantHistory.objects.filter(
        registration_no=registration_no,
        end_date__gte=start_date,
        end_date__lte=end_date
    )
    for history in history_qs:
        d = history.end_date.strftime('%Y-%m-%d')
        # Add historical activities
        if activity_type in [None, '', 'quiz', 'all']:
            activity_counts[d] = activity_counts.get(d, 0) + history.total_quizzes_completed
        if activity_type in [None, '', 'session', 'all']:
            activity_counts[d] = activity_counts.get(d, 0) + history.sessions_attended + history.sessions_conducted

    # Prepare response: sorted by date
    result = [
        {"date": d, "count": activity_counts[d]} for d in sorted(activity_counts.keys())
    ]
    return Response(result)

@api_view(['POST'])
def archive_semester_data(request):
    """Archive current semester data and prepare for new semester"""
    try:
        # Get department from request
        department_id = request.data.get('department_id')
        
        # Base query for relationships and participants
        relationship_query = MentorMenteeRelationship.objects.all()
        participant_query = Participant.objects.filter(status='active')
        
        # If department_id is provided, filter by department
        if department_id:
            relationship_query = relationship_query.filter(
                Q(mentor__department_id=department_id) | 
                Q(mentee__department_id=department_id)
            )
            participant_query = participant_query.filter(department_id=department_id)
        
        # 1. Archive all current relationships
        current_relationships = relationship_query
        archived_relationships = []
        
        for relationship in current_relationships:
            # Archive relationship data
            archived_relationships.append({
                'mentor_reg_no': relationship.mentor.registration_no,
                'mentee_reg_no': relationship.mentee.registration_no,
                'start_date': relationship.created_at,
                'end_date': timezone.now(),
                'department': relationship.mentor.department.name if relationship.mentor.department else 'No Department'
            })
        
        # 2. Archive participant data
        active_participants = participant_query
        archived_count = 0
        
        for participant in active_participants:
            # Calculate achievements
            total_badges = participant.badges_earned
            total_points = participant.leaderboard_points
            
            # Get quiz performance
            quiz_results = QuizResult.objects.filter(participant=participant)
            total_quizzes = quiz_results.count()
            avg_quiz_score = quiz_results.aggregate(Avg('percentage'))['percentage__avg'] or 0.0
            
            # Get mentoring history
            was_mentor = MentorMenteeRelationship.objects.filter(mentor=participant).exists()
            was_mentee = MentorMenteeRelationship.objects.filter(mentee=participant).exists()
            
            # Calculate mentor/mentee ratings
            mentor_feedback = MentorFeedback.objects.filter(relationship__mentor=participant)
            mentee_feedback = MentorFeedback.objects.filter(relationship__mentee=participant)
            
            mentor_rating = mentor_feedback.aggregate(Avg('overall_rating'))['overall_rating__avg'] if was_mentor else None
            mentee_rating = mentee_feedback.aggregate(Avg('overall_rating'))['overall_rating__avg'] if was_mentee else None
            
            # Get session participation
            sessions_attended = Session.objects.filter(participants=participant).count()
            sessions_conducted = Session.objects.filter(mentor=participant).count()
            
            # Create history record
            ParticipantHistory.objects.create(
                registration_no=participant.registration_no,
                name=participant.name,
                semester=participant.semester,
                branch=participant.branch,
                department=participant.department,
                total_badges_earned=total_badges,
                total_leaderboard_points=total_points,
                total_quizzes_completed=total_quizzes,
                average_quiz_score=avg_quiz_score,
                was_mentor=was_mentor,
                was_mentee=was_mentee,
                mentor_rating=mentor_rating,
                mentee_rating=mentee_rating,
                sessions_attended=sessions_attended,
                sessions_conducted=sessions_conducted,
                start_date=participant.date.date(),
                end_date=timezone.now().date()
            )
            archived_count += 1
        
        # 3. Delete all current relationships for the department
        current_relationships.delete()
        
        # 4. Reset participant status and profile data
        active_participants.update(
            # Clear mentoring preferences and status
            mentoring_preferences='',
            approval_status='pending',
            
            # Reset achievements
            badges_earned=0,
            leaderboard_points=0,
            is_super_mentor=False,
            
            # Clear profile data
            tech_stack='',
            areas_of_interest='',
            interest_preference1='',
            interest_preference2='',
            interest_preference3='',
            previous_mentoring_experience='',
            
            # Reset research data
            published_research_papers='None',
            proof_of_research_publications=None,
            
            # Reset hackathon data
            hackathon_participation='None',
            number_of_wins=0,
            number_of_participations=0,
            hackathon_role=None,
            proof_of_hackathon_participation=None,
            
            # Reset coding competitions data
            coding_competitions_participate='no',
            level_of_competition='None',
            number_of_coding_competitions=0,
            proof_of_coding_competitions=None,
            
            # Reset internship data
            internship_experience='no',
            number_of_internships=0,
            internship_description='',
            proof_of_internships=None,
            
            # Reset seminars & workshops data
            seminars_or_workshops_attended='no',
            describe_seminars_or_workshops='',
            
            # Reset extracurricular data
            extracurricular_activities='no',
            describe_extracurricular_activities='',
            proof_of_extracurricular_activities=None
        )
        
        # Get department name for response
        department_name = "All Departments"
        if department_id:
            department = Department.objects.filter(id=department_id).first()
            if department:
                department_name = department.name
        
        return Response({
            'message': f'Semester data archived successfully for {department_name}',
            'details': {
                'department': department_name,
                'relationships_archived': len(archived_relationships),
                'participants_archived': archived_count,
                'relationships_ended': current_relationships.count(),
                'participants_reset': active_participants.count()
            }
        })
        
    except Exception as e:
        return Response({
            'error': 'Failed to archive semester data',
            'details': str(e)
        }, status=500)

@api_view(['GET'])
def get_participant_history(request, registration_no):
    """
    Returns historical data for a participant across semesters.
    Useful for showing past achievements and for matching algorithm.
    """
    try:
        history = ParticipantHistory.objects.filter(registration_no=registration_no)
        if not history.exists():
            return Response({
                'message': 'No historical data found for this participant'
            })
        
        data = []
        for record in history:
            data.append({
                'semester': record.semester,
                'start_date': record.start_date,
                'end_date': record.end_date,
                'achievements': {
                    'total_badges': record.total_badges_earned,
                    'total_points': record.total_leaderboard_points,
                    'quizzes_completed': record.total_quizzes_completed,
                    'average_quiz_score': record.average_quiz_score
                },
                'mentoring': {
                    'was_mentor': record.was_mentor,
                    'was_mentee': record.was_mentee,
                    'mentor_rating': record.mentor_rating,
                    'mentee_rating': record.mentee_rating
                },
                'sessions': {
                    'attended': record.sessions_attended,
                    'conducted': record.sessions_conducted
                }
            })
        
        return Response(data)
        
    except Exception as e:
        return Response({
            'error': 'Failed to fetch participant history',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)