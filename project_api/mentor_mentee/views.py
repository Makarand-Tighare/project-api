import requests
import json
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from .models import Participant, MentorMenteeRelationship, Session, QuizResult, Badge, ParticipantBadge
from .serializers import ParticipantSerializer, SessionSerializer, MentorInfoSerializer, MenteeInfoSerializer, QuizResultSerializer, BadgeSerializer, ParticipantBadgeSerializer
from collections import defaultdict
from itertools import cycle
from django.db import transaction
from rest_framework.permissions import IsAuthenticated  # or AllowAny if public
import os
from dotenv import load_dotenv
import datetime
from django.db import models
from account.models import Student  # Import Student model for email lookup

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
        # Ensure the approval status is set to pending for new participants
        data = request.data.copy()
        data['approval_status'] = 'pending'  # Force pending status for all new registrations
        
        serializer = ParticipantSerializer(data=data)
        if serializer.is_valid():
            participant = serializer.save()
            return Response({
                'msg': 'Details saved successfully',
                'note': 'Your registration is pending admin approval',
                'participant': ParticipantSerializer(participant).data
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET'])
def list_participants(request):
    """List all participants"""
    try:
        # Check if the user is a department admin
        user = request.user
        department_filter = None
        
        # If this is a department admin, they should only see participants from their department
        if hasattr(user, 'is_department_admin') and user.is_department_admin and user.department:
            department_filter = user.department
            print(f"Department admin filtering for department: {department_filter.name}")
            
            # Get participants only from this department
            participants = Participant.objects.filter(department=department_filter)
        else:
            # Regular admin or non-logged in user gets all participants
            participants = Participant.objects.all()
            
        serializer = ParticipantSerializer(participants, many=True)
        
        # Add department info to response
        response_data = {
            'participants': serializer.data,
            'count': participants.count()
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
    """
    # Handle possible nan or empty values
    mentor_tech = mentor['tech_stack'] if 'tech_stack' in mentor and mentor['tech_stack'] and mentor['tech_stack'] != 'nan' else ''
    mentee_tech = mentee['tech_stack'] if 'tech_stack' in mentee and mentee['tech_stack'] and mentee['tech_stack'] != 'nan' else ''
    mentor_interest = mentor['areas_of_interest'] if 'areas_of_interest' in mentor and mentor['areas_of_interest'] and mentor['areas_of_interest'] != 'nan' else ''
    mentee_interest = mentee['areas_of_interest'] if 'areas_of_interest' in mentee and mentee['areas_of_interest'] and mentee['areas_of_interest'] != 'nan' else ''
    
    # Get prioritized interests
    mentor_pref1 = mentor.get('interest_preference1', '')
    mentor_pref2 = mentor.get('interest_preference2', '')
    mentor_pref3 = mentor.get('interest_preference3', '')
    mentee_pref1 = mentee.get('interest_preference1', '')
    mentee_pref2 = mentee.get('interest_preference2', '')
    mentee_pref3 = mentee.get('interest_preference3', '')
    
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
    
    # Calculate preference match score (higher is better)
    preference_score = 0
    
    # Check if mentor's preferences match mentee's interests/tech
    if mentor_pref1 and (mentor_pref1 in mentee_interests or any(mentor_pref1 in tech for tech in mentee_tech_stack)):
        preference_score += 10  # Highest priority match
    if mentor_pref2 and (mentor_pref2 in mentee_interests or any(mentor_pref2 in tech for tech in mentee_tech_stack)):
        preference_score += 6   # Medium priority match
    if mentor_pref3 and (mentor_pref3 in mentee_interests or any(mentor_pref3 in tech for tech in mentee_tech_stack)):
        preference_score += 3   # Lower priority match
    
    # Check if mentee's preferences match mentor's interests/tech
    if mentee_pref1 and (mentee_pref1 in mentor_interests or any(mentee_pref1 in tech for tech in mentor_tech_stack)):
        preference_score += 10  # Highest priority match
    if mentee_pref2 and (mentee_pref2 in mentor_interests or any(mentee_pref2 in tech for tech in mentor_tech_stack)):
        preference_score += 6   # Medium priority match
    if mentee_pref3 and (mentee_pref3 in mentor_interests or any(mentee_pref3 in tech for tech in mentor_tech_stack)):
        preference_score += 3   # Lower priority match
    
    # NEW: Consider badge count and super mentor status
    badge_bonus = 0
    if 'badges_earned' in mentor and mentor['badges_earned']:
        badge_count = int(mentor['badges_earned'])
        # Scale the badge bonus from 0-10 based on badge count
        badge_bonus = min(10, badge_count * 2)
    
    # Super mentors get higher compatibility scores
    super_mentor_bonus = 0
    if 'is_super_mentor' in mentor and mentor['is_super_mentor']:
        super_mentor_bonus = 10  # Significant boost for super mentors
    
    # Combine all findings with new badge and super mentor bonuses
    return common_tech, common_interests, preference_score, badge_bonus, super_mentor_bonus

def match_mentors_mentees(students):
    """
    Match mentors with mentees dynamically - ensuring ALL students are classified and matched.
    
    This function can handle both initial matching of all participants and 
    incremental matching of new participants.
    """
    MAX_MENTEES_PER_MENTOR = 4  # Target number of mentees per mentor (3-5)
    mentors = []
    mentees = []
    matches = []
    unclassified = []
    
    # Filter out participants who haven't been approved by admin
    approved_students = []
    for student in students:
        if 'approval_status' in student and student['approval_status'] == 'approved':
            # Only include participants with approved status
            approved_students.append(student)
    
    # If no approved participants, return early
    if not approved_students:
        return {
            "error": "No approved participants found for matching",
            "message": "All participants need to be approved by an admin before matching",
            "suggestion": "Please approve some participants and try again"
        }
    
    # Continue with matching using only approved participants
    students = approved_students
    
    # Ensure all students have department_id if at least one does
    # This will help with department-restricted matching
    has_department = any('department_id' in s for s in students)
    
    if has_department:
        # Group by department_id
        departments = {}
        for student in students:
            dept_id = student.get('department_id')
            if dept_id not in departments:
                departments[dept_id] = []
            departments[dept_id].append(student)
            
        # If we have multiple departments, handle each separately
        if len(departments) > 1:
            all_matches = []
            for dept_id, dept_students in departments.items():
                # Skip empty departments (shouldn't happen but just in case)
                if not dept_students:
                    continue
                    
                print(f"Matching students in department ID: {dept_id}")
                dept_matches = perform_matching(dept_students)
                
                # Handle error cases
                if isinstance(dept_matches, dict) and 'error' in dept_matches:
                    # Continue with other departments
                    print(f"Error matching department {dept_id}: {dept_matches['error']}")
                    continue
                    
                all_matches.extend(dept_matches)
                
            # Return the combined matches
            return {
                'matches': all_matches,
                'statistics': {
                    'total_departments': len(departments),
                    'departments_matched': sum(1 for dept_id in departments if departments[dept_id])
                }
            }
    
    # If we have a single department or no department info, proceed normally
    return perform_matching(students)
    
def perform_matching(students):
    """Helper function that does the actual matching algorithm"""
    MAX_MENTEES_PER_MENTOR = 4  # Target number of mentees per mentor (3-5)
    mentors = []
    mentees = []
    matches = []
    unclassified = []

    # If there are very few students to match (like 1 or 2), we may need to supplement
    # them with existing matched participants to create proper mentor/mentee roles
    is_small_batch = len(students) <= 3
    
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
        
        # Special case for small batches - put them all as mentees if possible
        if is_small_batch and len(mentors) == 0:
            # For small batches with no declared mentors, prioritize making them mentees
            # We will try to match them with existing mentors later
            mentees.extend(unclassified)
        else:
            # Normal case: determine mentors based on scores
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
    
    # For small batches, if we have only mentees, we'll need to handle them specially later
    small_batch_mentees_only = is_small_batch and len(mentors) == 0 and len(mentees) > 0
   
    # If we have too few mentors, convert some high-scoring mentees (unless it's a small batch)
    if not small_batch_mentees_only and len(mentors) < len(mentees) / MAX_MENTEES_PER_MENTOR:
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
    
    # Special case for small batches with only mentees - return them as unmatched
    # They will be matched by the view function with existing mentors in the database
    if small_batch_mentees_only:
        return {
            "matches": [],
            "unmatched_mentees": mentees,
            "statistics": {
                "total_participants": len(students),
                "total_mentees": len(mentees),
                "total_mentors": 0,
                "participants_matched": 0,
                "match_quality_counts": {
                    "high": 0,
                    "medium": 0,
                    "low": 0,
                    "assigned": 0,
                    "peer_mentor": 0
                }
            }
        }
    
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
            common_tech, common_interests, preference_score, badge_bonus, super_mentor_bonus = has_common_interests(mentor, mentee)
            
            # Calculate match score based on common interests
            tech_score = len(common_tech) * 3  # Weight tech stack higher
            interest_score = len(common_interests) * 2
            
            # Additional compatibility factors
            # Same branch is a plus
            branch_score = 2 if mentor.get('branch') == mentee.get('branch') else 0
            
            # Prioritize preference matches heavily
            preference_match_score = preference_score * 2  # Double weight for explicit preferences
            
            # Total compatibility score
            compatibility_score = tech_score + interest_score + branch_score + preference_match_score
            
            # Add badge and super mentor bonuses
            compatibility_score += badge_bonus + super_mentor_bonus
            
            match_scores.append({
                'mentor': mentor,
                'mentee': mentee,
                'score': compatibility_score,
                'common_tech': common_tech,
                'common_interests': common_interests,
                'preference_score': preference_score,
                'badge_bonus': badge_bonus,
                'super_mentor_bonus': super_mentor_bonus,
                'compatibility': "high" if compatibility_score >= 15 else 
                                 "medium" if compatibility_score >= 7 else "low"
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
                "tech_stack": mentor['tech_stack'],
                "badges_earned": mentor.get('badges_earned', 0),
                "is_super_mentor": mentor.get('is_super_mentor', False)
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
            "common_interests": [],
            "preference_score": 0,
            "badge_bonus": 0,
            "super_mentor_bonus": 0
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
                        "tech_stack": mentor['tech_stack'],
                        "badges_earned": mentor.get('badges_earned', 0),
                        "is_super_mentor": mentor.get('is_super_mentor', False)
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
                    "common_interests": [],
                    "preference_score": 0,
                    "badge_bonus": 0,
                    "super_mentor_bonus": 0
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
                    "tech_stack": lead_mentor['tech_stack'],
                    "badges_earned": lead_mentor.get('badges_earned', 0),
                    "is_super_mentor": lead_mentor.get('is_super_mentor', False)
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
                "common_interests": [],
                "preference_score": 0,
                "badge_bonus": 0,
                "super_mentor_bonus": 0
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
                            "tech_stack": best_mentor['tech_stack'],
                            "badges_earned": best_mentor.get('badges_earned', 0),
                            "is_super_mentor": best_mentor.get('is_super_mentor', False)
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
                        "common_interests": [],
                        "preference_score": 0,
                        "badge_bonus": 0,
                        "super_mentor_bonus": 0
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
            department=department_filter
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
            department=department_filter
        )
    else:
        # Check if there are pending approvals overall
        pending_approvals_count = Participant.objects.filter(approval_status='pending').count()
        
        if pending_approvals_count > 0:
            return Response({
                "error": "Approval required before matching",
                "message": f"There are {pending_approvals_count} participants pending approval",
                "action_required": "Please approve or reject pending participants before matching",
                "pending_count": pending_approvals_count
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get all APPROVED participants
        participants = Participant.objects.filter(approval_status='approved')
    
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
            
            # Check if there are pending approvals for this department
            pending_approvals_count = Participant.objects.filter(
                approval_status='pending',
                department=department_filter
            ).count()
            
            if pending_approvals_count > 0:
                return Response({
                    "error": "Approval required before viewing relationships",
                    "message": f"There are {pending_approvals_count} participants pending approval in your department",
                    "action_required": "Please approve or reject pending participants first",
                    "pending_count": pending_approvals_count
                }, status=status.HTTP_400_BAD_REQUEST)
            
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
            # Check if there are pending approvals overall
            pending_approvals_count = Participant.objects.filter(approval_status='pending').count()
            
            if pending_approvals_count > 0:
                return Response({
                    "error": "Approval required before viewing relationships",
                    "message": f"There are {pending_approvals_count} participants pending approval",
                    "action_required": "Please approve or reject pending participants first",
                    "pending_count": pending_approvals_count
                }, status=status.HTTP_400_BAD_REQUEST)
            
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
                department=department_filter
            ).count()
            
            if pending_approvals_count > 0:
                return Response({
                    "error": "Approval required before creating relationships",
                    "message": f"There are {pending_approvals_count} participants pending approval in your department",
                    "action_required": "Please approve or reject pending participants first",
                    "pending_count": pending_approvals_count
                }, status=status.HTTP_400_BAD_REQUEST)
        else:
            # Check if there are pending approvals overall
            pending_approvals_count = Participant.objects.filter(approval_status='pending').count()
            
            if pending_approvals_count > 0:
                return Response({
                    "error": "Approval required before creating relationships",
                    "message": f"There are {pending_approvals_count} participants pending approval",
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
            
            # Check if there are pending approvals for this department
            pending_approvals_count = Participant.objects.filter(
                approval_status='pending',
                department=department_filter
            ).count()
            
            if pending_approvals_count > 0:
                return Response({
                    "error": "Approval required before viewing unmatched participants",
                    "message": f"There are {pending_approvals_count} participants pending approval in your department",
                    "action_required": "Please approve or reject pending participants first",
                    "pending_count": pending_approvals_count
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Get all approved participants from this department
            all_participants = Participant.objects.filter(
                department=department_filter,
                approval_status='approved'
            )
        else:
            # Check if there are pending approvals overall
            pending_approvals_count = Participant.objects.filter(approval_status='pending').count()
            
            if pending_approvals_count > 0:
                return Response({
                    "error": "Approval required before viewing unmatched participants",
                    "message": f"There are {pending_approvals_count} participants pending approval",
                    "action_required": "Please approve or reject pending participants first",
                    "pending_count": pending_approvals_count
                }, status=status.HTTP_400_BAD_REQUEST)
            
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
            # Each session is worth 100 points
            sessions = Session.objects.filter(mentor=participant).count()
            sessions_as_participant = Session.objects.filter(participants=participant).count()
            sessions_score = (sessions * 100) + (sessions_as_participant * 50)
            
            # Check if participant is a mentor (has mentees)
            mentor_relationships = MentorMenteeRelationship.objects.filter(mentor=participant)
            is_mentor = mentor_relationships.exists()
            
            # NEW: Points for quizzes assigned by mentor
            # Each quiz assigned is worth 30 points plus bonus points based on mentee performance
            assigned_quizzes = QuizResult.objects.filter(mentor=participant)
            assigned_quiz_count = assigned_quizzes.count()
            quiz_assignment_score = assigned_quiz_count * 30
            
            # Add bonus points for completed quizzes with good performance
            completed_assigned_quizzes = assigned_quizzes.filter(status='completed')
            if completed_assigned_quizzes.exists():
                # Add bonus for each completed quiz based on mentee's performance
                for quiz in completed_assigned_quizzes:
                    # Higher mentee score = more points for mentor (10-30 points per quiz)
                    performance_bonus = min(30, int(quiz.percentage / 3.33))
                    quiz_assignment_score += performance_bonus
            
            if is_mentor:
                # For mentors: Add points for each mentee and their quiz performance
                mentees = [rel.mentee for rel in mentor_relationships]
                mentee_count = len(mentees)
                mentee_score = mentee_count * 200  # Base score for each mentee
                
                # Add score for mentee quiz performance
                for mentee in mentees:
                    # Get completed quizzes for this mentee
                    quizzes = QuizResult.objects.filter(
                        participant=mentee,
                        status='completed'
                    )
                    
                    if quizzes.exists():
                        quiz_count = quizzes.count()
                        avg_score = quizzes.aggregate(models.Avg('percentage'))['percentage__avg'] or 0
                        
                        # Add points for each quiz and bonus for good performance
                        quiz_score += (quiz_count * 20) + (avg_score * 2)
            else:
                # For mentees: Calculate scores based on their own quizzes
                quizzes = QuizResult.objects.filter(
                    participant=participant,
                    status='completed'
                )
                
                if quizzes.exists():
                    quiz_count = quizzes.count()
                    avg_score = quizzes.aggregate(models.Avg('percentage'))['percentage__avg'] or 0
                    
                    # Add points for each quiz (50 points each) and bonus for good performance
                    quiz_score = (quiz_count * 50) + (avg_score * 5)
            
            # Calculate total score - include quiz assignment points
            total_score = sessions_score + quiz_score + mentee_score + quiz_assignment_score
            
            # Add bonus for badges and super mentor status
            if participant.badges_earned > 0:
                total_score += participant.badges_earned * 100
                
            if participant.is_super_mentor:
                total_score += 500  # Super mentor bonus
            
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
                'quiz_assignment_score': quiz_assignment_score,  # New field for assigned quizzes
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