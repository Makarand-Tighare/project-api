import requests
import json
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from .models import Participant, MentorMenteeRelationship, Session, QuizResult
from .serializers import ParticipantSerializer, SessionSerializer, MentorInfoSerializer, MenteeInfoSerializer, QuizResultSerializer
from collections import defaultdict
from itertools import cycle
from django.db import transaction
from rest_framework.permissions import IsAuthenticated  # or AllowAny if public
import os
from dotenv import load_dotenv
import datetime

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY")  # Use .env or fallback

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

    return score

def has_common_interests(mentor, mentee):
    """Check if mentor and mentee share common tech stack or areas of interest."""
    # Handle possible nan or empty values
    mentor_tech = mentor['tech_stack'] if 'tech_stack' in mentor and mentor['tech_stack'] and mentor['tech_stack'] != 'nan' else ''
    mentee_tech = mentee['tech_stack'] if 'tech_stack' in mentee and mentee['tech_stack'] and mentee['tech_stack'] != 'nan' else ''
    mentor_interest = mentor['areas_of_interest'] if 'areas_of_interest' in mentor and mentor['areas_of_interest'] and mentor['areas_of_interest'] != 'nan' else ''
    mentee_interest = mentee['areas_of_interest'] if 'areas_of_interest' in mentee and mentee['areas_of_interest'] and mentee['areas_of_interest'] != 'nan' else ''
    
    # Split by comma and clean up spaces
    mentor_tech_stack = set(tech.strip() for tech in mentor_tech.split(',')) if mentor_tech else set()
    mentee_tech_stack = set(tech.strip() for tech in mentee_tech.split(',')) if mentee_tech else set()
    mentor_interests = set(interest.strip() for interest in mentor_interest.split(',')) if mentor_interest else set()
    mentee_interests = set(interest.strip() for interest in mentee_interest.split(',')) if mentee_interest else set()
    
    # Check for common interests
    common_tech = mentor_tech_stack.intersection(mentee_tech_stack)
    common_interests = mentor_interests.intersection(mentee_interests)
    
    # Check for partial matches in tech stack (e.g., "JavaScript" in "JavaScript, Node.js")
    if not common_tech:
        partial_matches = set()
        for m_tech in mentor_tech_stack:
            for s_tech in mentee_tech_stack:
                if m_tech in s_tech or s_tech in m_tech:
                    partial_matches.add((m_tech, s_tech))
        common_tech = partial_matches
    
    # Same for interests
    if not common_interests:
        partial_matches = set()
        for m_int in mentor_interests:
            for s_int in mentee_interests:
                if m_int in s_int or s_int in m_int:
                    partial_matches.add((m_int, s_int))
        common_interests = partial_matches
    
    return common_tech, common_interests

def match_mentors_mentees(students):
    """Match mentors with mentees dynamically - ensuring ALL students are classified and matched."""
    MAX_MENTEES_PER_MENTOR = 4  # Target number of mentees per mentor (3-5)
    mentors = []
    mentees = []
    matches = []
    unclassified = []

    # First pass: Classify based on mentoring_preferences, score, and semester
    for student in students:
        # Try to respect mentoring_preferences if specified
        if 'mentoring_preferences' in student and student['mentoring_preferences'] == 'mentor':
            mentors.append(student)
        elif 'mentoring_preferences' in student and student['mentoring_preferences'] == 'mentee':
            mentees.append(student)
        # Otherwise use score and semester as fallback
        else:
            unclassified.append(student)
    
    # Classify unclassified students based on their score
    if unclassified:
        # Calculate scores for unclassified students
        for student in unclassified:
            student['score'] = evaluate_student(student)
        
        # Sort by score (highest first)
        unclassified.sort(key=lambda s: s['score'], reverse=True)
        
        # Determine how many mentors we need based on remaining mentees
        needed_mentors = max(1, (len(mentees) + len(unclassified)) // MAX_MENTEES_PER_MENTOR)
        needed_mentors -= len(mentors)  # Adjust for existing mentors
        
        if needed_mentors > 0:
            # Take top scoring students as mentors
            new_mentors = unclassified[:needed_mentors]
            mentors.extend(new_mentors)
            unclassified = unclassified[needed_mentors:]
        
        # Rest become mentees
        mentees.extend(unclassified)
    
    # Calculate mentor scores for later use
    for mentor in mentors:
        mentor['score'] = evaluate_student(mentor)
    
    # Sort mentors by their evaluated score (highest first)
    mentors.sort(key=lambda m: m['score'], reverse=True)
    
    # If we have too few mentors, convert some high-scoring mentees
    if len(mentors) < len(mentees) / MAX_MENTEES_PER_MENTOR:
        # Calculate how many additional mentors needed
        needed_mentors = max(1, len(mentees) // MAX_MENTEES_PER_MENTOR - len(mentors))
        
        # Score all mentees
        for mentee in mentees:
            mentee['score'] = evaluate_student(mentee)
        
        # Sort mentees by score (highest first)
        sorted_mentees = sorted(mentees, key=lambda m: m['score'], reverse=True)
        
        # Take top N as mentors
        new_mentors = sorted_mentees[:needed_mentors]
        mentors.extend(new_mentors)
        
        # Remove these from mentees list
        mentee_reg_nos_to_remove = [m['registration_no'] for m in new_mentors]
        mentees = [m for m in mentees if m['registration_no'] not in mentee_reg_nos_to_remove]
    
    # Final check to ensure we have mentors
    if not mentors:
        return {
            "error": "Failed to classify participants into mentors and mentees",
            "suggestion": "Please check participant data and ensure some participants meet mentor criteria"
        }
    
    # Log the counts
    print(f"Classified {len(mentors)} mentors and {len(mentees)} mentees out of {len(students)} total students")
        
    # Dictionary to count mentees per mentor
    mentor_mentee_count = defaultdict(int)
    
    # Calculate match quality for all mentor-mentee pairs
    match_scores = []
    for mentee in mentees:
        for mentor in mentors:
            # Skip if mentor and mentee are the same person
            if mentor['registration_no'] == mentee['registration_no']:
                continue
                
            # Skip if mentor already has max mentees
            if mentor_mentee_count[mentor['registration_no']] >= MAX_MENTEES_PER_MENTOR:
                continue
                
            # Get common interests
            common_tech, common_interests = has_common_interests(mentor, mentee)
            
            # Calculate match score based on common interests
            tech_score = len(common_tech) * 3  # Weight tech stack higher
            interest_score = len(common_interests) * 2
            
            # Additional compatibility factors
            # Same branch is a plus
            branch_score = 2 if mentor.get('branch') == mentee.get('branch') else 0
            
            # Total compatibility score
            compatibility_score = tech_score + interest_score + branch_score
            
            match_scores.append({
                'mentor': mentor,
                'mentee': mentee,
                'score': compatibility_score,
                'common_tech': common_tech,
                'common_interests': common_interests,
                'compatibility': "high" if compatibility_score >= 5 else 
                                 "medium" if compatibility_score >= 2 else "low"
            })
    
    # Sort match scores by compatibility score (highest first)
    match_scores.sort(key=lambda x: x['score'], reverse=True)
    
    # Match mentees based on highest compatibility
    matched_mentees = set()
    
    # First do highly compatible matches
    for match in match_scores:
        mentor = match['mentor']
        mentee = match['mentee']
        
        # Skip if this mentee is already matched or if mentor has reached max mentees
        if mentee['registration_no'] in matched_mentees or mentor_mentee_count[mentor['registration_no']] >= MAX_MENTEES_PER_MENTOR:
            continue
            
        matches.append({
            "mentor": {
                "name": mentor['name'],
                "registration_no": mentor['registration_no'],
                "semester": mentor['semester'],
                "branch": mentor['branch'],
                "tech_stack": mentor['tech_stack']
            },
            "mentee": {
                "name": mentee['name'],
                "registration_no": mentee['registration_no'],
                "semester": mentee['semester'],
                "branch": mentee['branch'],
                "tech_stack": mentee['tech_stack']
            },
            "match_quality": match['compatibility'],
            "common_tech": list(match['common_tech']),
            "common_interests": list(match['common_interests'])
        })
        
        matched_mentees.add(mentee['registration_no'])
        mentor_mentee_count[mentor['registration_no']] += 1
    
    # Handle unmatched mentees - these need to be assigned even if there's no compatibility
    unmatched_mentees = [m for m in mentees if m['registration_no'] not in matched_mentees]
    
    if unmatched_mentees:
        print(f"Assigning {len(unmatched_mentees)} mentees with no direct compatibility")
        
        for mentee in unmatched_mentees:
            # Find available mentor with fewest mentees
            available_mentors = [m for m in mentors if mentor_mentee_count[m['registration_no']] < MAX_MENTEES_PER_MENTOR]
            
            if not available_mentors:
                # If all mentors are at capacity, we need to add more mentors or increase capacity
                print("All mentors at capacity, increasing capacity for high-scoring mentors")
                # Increase capacity for highest-scoring mentors
                sorted_mentors = sorted(mentors, key=lambda m: m.get('score', 0), reverse=True)
                available_mentors = sorted_mentors[:max(1, len(sorted_mentors) // 3)]  # Top third get extra capacity
            
            if available_mentors:
                # Find mentor with fewest mentees
                mentor = min(available_mentors, key=lambda m: mentor_mentee_count[m['registration_no']])
                
                # Create a generic match
                matches.append({
                    "mentor": {
                        "name": mentor['name'],
                        "registration_no": mentor['registration_no'],
                        "semester": mentor['semester'],
                        "branch": mentor['branch'],
                        "tech_stack": mentor['tech_stack']
                    },
                    "mentee": {
                        "name": mentee['name'],
                        "registration_no": mentee['registration_no'],
                        "semester": mentee['semester'],
                        "branch": mentee['branch'],
                        "tech_stack": mentee['tech_stack']
                    },
                    "match_quality": "assigned",
                    "common_tech": [],
                    "common_interests": []
                })
                
                matched_mentees.add(mentee['registration_no'])
                mentor_mentee_count[mentor['registration_no']] += 1
    
    # Handle unmatched mentors
    matched_mentors = set(m['mentor']['registration_no'] for m in matches)
    unmatched_mentors = [m for m in mentors if m['registration_no'] not in matched_mentors]
    
    if unmatched_mentors:
        print(f"Found {len(unmatched_mentors)} mentors without mentees - creating peer matches")
        
        # Sort unmatched mentors by score (lowest first)
        unmatched_mentors.sort(key=lambda m: m.get('score', 0))
        
        # Create peer mentor relationships (pair them up)
        while len(unmatched_mentors) >= 2:
            # Take two mentors
            mentee_mentor = unmatched_mentors.pop(0)  # Lower score becomes mentee
            lead_mentor = unmatched_mentors.pop(0)    # Higher score becomes mentor
            
            # Create a peer mentoring match
            matches.append({
                "mentor": {
                    "name": lead_mentor['name'],
                    "registration_no": lead_mentor['registration_no'],
                    "semester": lead_mentor['semester'],
                    "branch": lead_mentor['branch'],
                    "tech_stack": lead_mentor['tech_stack']
                },
                "mentee": {
                    "name": mentee_mentor['name'],
                    "registration_no": mentee_mentor['registration_no'],
                    "semester": mentee_mentor['semester'],
                    "branch": mentee_mentor['branch'],
                    "tech_stack": mentee_mentor['tech_stack']
                },
                "match_quality": "peer-mentor",
                "common_tech": [],
                "common_interests": []
            })
            
            mentor_mentee_count[lead_mentor['registration_no']] += 1
            matched_mentors.add(lead_mentor['registration_no'])
            matched_mentees.add(mentee_mentor['registration_no'])
        
        # If one mentor remains unmatched, assign them as mentee to a mentor with fewest mentees
        if unmatched_mentors:
            remaining_mentor = unmatched_mentors[0]
            
            # Find matched mentor with fewest mentees
            matched_mentor_reg_nos = list(matched_mentors)
            if matched_mentor_reg_nos:
                # Only include mentors who aren't at max capacity
                available_mentors = [m for m in mentors 
                                   if m['registration_no'] in matched_mentor_reg_nos 
                                   and m['registration_no'] != remaining_mentor['registration_no']
                                   and mentor_mentee_count[m['registration_no']] < MAX_MENTEES_PER_MENTOR]
                
                if available_mentors:
                    best_mentor = min(available_mentors, key=lambda m: mentor_mentee_count[m['registration_no']])
                    
                    matches.append({
                        "mentor": {
                            "name": best_mentor['name'],
                            "registration_no": best_mentor['registration_no'],
                            "semester": best_mentor['semester'],
                            "branch": best_mentor['branch'],
                            "tech_stack": best_mentor['tech_stack']
                        },
                        "mentee": {
                            "name": remaining_mentor['name'],
                            "registration_no": remaining_mentor['registration_no'],
                            "semester": remaining_mentor['semester'],
                            "branch": remaining_mentor['branch'],
                            "tech_stack": remaining_mentor['tech_stack']
                        },
                        "match_quality": "peer-mentor",
                        "common_tech": [],
                        "common_interests": []
                    })
                    
                    mentor_mentee_count[best_mentor['registration_no']] += 1
                    matched_mentees.add(remaining_mentor['registration_no'])
    
    # Add mentor statistics to each match
    for match in matches:
        mentor_reg_no = match['mentor']['registration_no']
        match['mentor']['mentee_count'] = mentor_mentee_count[mentor_reg_no]
    
    # Calculate how many participants were successfully matched
    all_matched_participants = set(m['mentor']['registration_no'] for m in matches) | set(m['mentee']['registration_no'] for m in matches)
    
    return {
        "matches": matches,
        "statistics": {
            "total_participants": len(students),
            "total_mentees": len(mentees),
            "total_mentors": len(mentors),
            "participants_matched": len(all_matched_participants),
            "average_mentees_per_mentor": round(sum(mentor_mentee_count.values()) / len(mentors), 2) if mentors else 0,
            "mentor_loads": dict(mentor_mentee_count),
            "match_quality_counts": {
                "high": len([m for m in matches if m['match_quality'] == 'high']),
                "medium": len([m for m in matches if m['match_quality'] == 'medium']),
                "low": len([m for m in matches if m['match_quality'] == 'low']),
                "assigned": len([m for m in matches if m['match_quality'] == 'assigned']),
                "peer_mentor": len([m for m in matches if m['match_quality'] == 'peer-mentor'])
            }
        }
    }

@api_view(['GET'])
def match_participants(request):
    """Endpoint to trigger mentor-mentee matching."""
    participants = Participant.objects.all()
    serializer = ParticipantSerializer(participants, many=True)
    students = serializer.data
    
    if not students:
        return Response({"error": "No participants found"}, status=status.HTTP_404_NOT_FOUND)

    matches = match_mentors_mentees(students)
    
    # Check if there was an error in matching
    if isinstance(matches, dict) and 'error' in matches:
        return Response(matches, status=status.HTTP_400_BAD_REQUEST)
    
    # Save relationships to database
    try:
        with transaction.atomic():
            # Clear existing relationships (optional - remove if you want to keep historical matches)
            MentorMenteeRelationship.objects.all().delete()
            
            # Create new relationships
            for match in matches['matches']:
                mentor_reg_no = match['mentor']['registration_no']
                mentee_reg_no = match['mentee']['registration_no']
                
                try:
                    mentor = Participant.objects.get(registration_no=mentor_reg_no)
                    mentee = Participant.objects.get(registration_no=mentee_reg_no)
                    
                    # Create the relationship
                    MentorMenteeRelationship.objects.create(
                        mentor=mentor,
                        mentee=mentee
                    )
                except Participant.DoesNotExist:
                    # Skip if either mentor or mentee doesn't exist
                    continue
    except Exception as e:
        return Response({
            "error": "Failed to save mentor-mentee relationships",
            "details": str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
    return Response({
        "matches": matches['matches'],
        "participants_matched": matches['statistics']['participants_matched'],
        "total_participants": matches['statistics']['total_participants'],
        "match_quality": {
            "interest_based": len([m for m in matches['matches'] if m['match_quality'] == 'interest-based']),
            "assigned": len([m for m in matches['matches'] if m['match_quality'] == 'assigned']),
            "peer_mentor": len([m for m in matches['matches'] if m['match_quality'] == 'peer-mentor'])
        },
        "statistics": matches['statistics']
    })

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
        serializer = ParticipantSerializer(participant)
        return Response(serializer.data)
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
    """List all mentor-mentee relationships for admin view."""
    try:
        relationships = MentorMenteeRelationship.objects.all()
        
        result = []
        for rel in relationships:
            result.append({
                "id": rel.id,
                "mentor": {
                    "name": rel.mentor.name,
                    "registration_no": rel.mentor.registration_no,
                    "semester": rel.mentor.semester
                },
                "mentee": {
                    "name": rel.mentee.name,
                    "registration_no": rel.mentee.registration_no,
                    "semester": rel.mentee.semester
                },
                "created_at": rel.created_at
            })
            
        return Response(result, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            "error": "Failed to retrieve relationships",
            "details": str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
def create_relationship(request):
    """Create a new mentor-mentee relationship manually."""
    try:
        mentor_reg_no = request.data.get('mentor_registration_no')
        mentee_reg_no = request.data.get('mentee_registration_no')
        
        if not mentor_reg_no or not mentee_reg_no:
            return Response({
                "error": "Both mentor and mentee registration numbers are required"
            }, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            mentor = Participant.objects.get(registration_no=mentor_reg_no)
            mentee = Participant.objects.get(registration_no=mentee_reg_no)
        except Participant.DoesNotExist:
            return Response({
                "error": "Mentor or mentee not found"
            }, status=status.HTTP_404_NOT_FOUND)
            
        # Check if relationship already exists
        if MentorMenteeRelationship.objects.filter(mentor=mentor, mentee=mentee).exists():
            return Response({
                "error": "This mentor-mentee relationship already exists"
            }, status=status.HTTP_400_BAD_REQUEST)
            
        # Create the relationship
        relationship = MentorMenteeRelationship.objects.create(
            mentor=mentor,
            mentee=mentee
        )
        
        return Response({
            "message": "Relationship created successfully",
            "relationship": {
                "id": relationship.id,
                "mentor": {
                    "name": mentor.name,
                    "registration_no": mentor.registration_no
                },
                "mentee": {
                    "name": mentee.name,
                    "registration_no": mentee.registration_no
                }
            }
        }, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        return Response({
            "error": "Failed to create relationship",
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
        
        if mentor_reg_no:
            try:
                mentor = Participant.objects.get(registration_no=mentor_reg_no)
                relationship.mentor = mentor
            except Participant.DoesNotExist:
                return Response({
                    "error": "Mentor not found"
                }, status=status.HTTP_404_NOT_FOUND)
                
        if mentee_reg_no:
            try:
                mentee = Participant.objects.get(registration_no=mentee_reg_no)
                relationship.mentee = mentee
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
        # Get all participants
        all_participants = Participant.objects.all()
        
        # Get all participants who are mentors or mentees in a relationship
        mentors_in_relationships = MentorMenteeRelationship.objects.values_list('mentor', flat=True).distinct()
        mentees_in_relationships = MentorMenteeRelationship.objects.values_list('mentee', flat=True).distinct()
        
        # Combine the two lists to get all participants in relationships
        matched_reg_nos = set(mentors_in_relationships) | set(mentees_in_relationships)
        
        # Filter for participants who are not in any relationship
        unmatched_participants = all_participants.exclude(registration_no__in=matched_reg_nos)
        
        # Serialize the unmatched participants
        serializer = ParticipantSerializer(unmatched_participants, many=True)
        
        # Return response with additional information
        return Response({
            "count": unmatched_participants.count(),
            "total_participants": all_participants.count(),
            "unmatched_participants": serializer.data
        })
        
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
        f"Generate a quiz with {num_questions} multiple-choice questions on the topic: '{prompt}'. "
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
        if mentee and relationship_validated:
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
            
            # Include the quiz_id in the response
            return Response({
                'quiz': quiz,
                'quiz_id': pending_quiz.id,
                'mentee': {
                    'name': mentee.name,
                    'registration_no': mentee.registration_no
                },
                'mentor': mentor_id,
                'status': 'pending',
                'message': f'Quiz assigned to {mentee.name} successfully'
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
    return Response(serializer.data, status=201)

@api_view(['GET'])
def get_participant_quiz_results(request, registration_no):
    """Get all quiz results for a specific participant."""
    try:
        participant = Participant.objects.get(registration_no=registration_no)
        quiz_results = QuizResult.objects.filter(participant=participant)
        serializer = QuizResultSerializer(quiz_results, many=True)
        return Response(serializer.data)
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
        return Response(serializer.data)
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