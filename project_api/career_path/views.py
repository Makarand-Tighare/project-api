from django.shortcuts import render
import json
import os
import requests
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from django.db import transaction
from django.utils import timezone
from dotenv import load_dotenv
from django.core.exceptions import ObjectDoesNotExist
import time
import uuid

from .models import (
    CareerPath, CareerSkill, CareerMilestone, 
    IntermediateRole, RecommendedProject,
    Resume,
    ResumePDF
)
from .serializers import (
    CareerPathSerializer, CareerPathInputSerializer, 
    GenerateCareerPathSerializer, CareerMilestoneSerializer,
    MilestoneInputSerializer,
    ResumeSerializer,
    EnhanceTextSerializer,
    ResumePDFSerializer
)
from .utils import enhance_text_with_ai, generate_resume_pdf

# Load environment variables
load_dotenv()

# Get Gemini API key from environment variables
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY")

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_career_path(request):
    """
    Get the authenticated user's career path data
    """
    try:
        career_path = CareerPath.objects.filter(user=request.user).first()
        
        if career_path:
            serializer = CareerPathSerializer(career_path)
            return Response(serializer.data)
        else:
            return Response(
                {"message": "Career path not found for this user"}, 
                status=status.HTTP_404_NOT_FOUND
            )
    except Exception as e:
        return Response(
            {"error": str(e)}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_update_career_path(request):
    """
    Create or update career path for the authenticated user
    """
    try:
        # Check if career path already exists for this user
        career_path = CareerPath.objects.filter(user=request.user).first()
        
        if career_path:
            # Update existing career path
            serializer = CareerPathInputSerializer(career_path, data=request.data, partial=True)
        else:
            # Create new career path
            serializer = CareerPathInputSerializer(data=request.data)
        
        if serializer.is_valid():
            # Save with the authenticated user
            career_path = serializer.save(user=request.user)
            
            # Return the full career path data
            response_serializer = CareerPathSerializer(career_path)
            return Response(response_serializer.data)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    except Exception as e:
        return Response(
            {"error": str(e)}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generate_career_path(request):
    """
    Generate career path recommendations using Gemini AI
    """
    try:
        # Validate input data
        serializer = GenerateCareerPathSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        # Extract data from request
        current_role = serializer.validated_data['current_role']
        target_role = serializer.validated_data['target_role']
        timeline = serializer.validated_data['timeline']
        current_skills = serializer.validated_data['current_skills']
        education = serializer.validated_data['education']
        
        # Generate career path using Gemini API
        ai_response = generate_career_path_with_gemini(
            current_role, target_role, timeline, current_skills, education
        )
        
        if 'error' in ai_response:
            return Response(ai_response, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        # Save the generated career path to the database
        with transaction.atomic():
            # Create or update career path
            career_path, created = CareerPath.objects.update_or_create(
                user=request.user,
                defaults={
                    'current_role': current_role,
                    'target_role': target_role,
                    'timeline': timeline,
                    'current_skills': current_skills,
                    'education': education,
                    'description': ai_response.get('career_path_description', '')
                }
            )
            
            # Clear existing related data if updating
            if not created:
                career_path.skills.all().delete()
                career_path.milestones.all().delete()
                career_path.intermediate_roles.all().delete()
                career_path.recommended_projects.all().delete()
            
            # Add skills
            for skill_data in ai_response.get('skills_to_develop', []):
                CareerSkill.objects.create(
                    career_path=career_path,
                    name=skill_data.get('name', ''),
                    importance=skill_data.get('importance_level', 'medium').lower(),
                    reason=skill_data.get('reason', '')
                )
            
            # Add milestones
            for milestone_data in ai_response.get('milestones', []):
                CareerMilestone.objects.create(
                    career_path=career_path,
                    title=milestone_data.get('title', ''),
                    description=milestone_data.get('description', ''),
                    estimated_timeline=milestone_data.get('estimated_timeline', ''),
                    skills_involved=','.join(milestone_data.get('skills_involved', []))
                )
            
            # Add intermediate roles
            for role_data in ai_response.get('intermediate_roles', []):
                IntermediateRole.objects.create(
                    career_path=career_path,
                    title=role_data.get('title', ''),
                    description=role_data.get('description', '')
                )
            
            # Add recommended projects
            for project_data in ai_response.get('recommended_projects', []):
                RecommendedProject.objects.create(
                    career_path=career_path,
                    title=project_data.get('title', ''),
                    description=project_data.get('description', ''),
                    skills_demonstrated=','.join(project_data.get('skills_demonstrated', []))
                )
        
        # Return the career path with all related data
        response_serializer = CareerPathSerializer(career_path)
        return Response(response_serializer.data)
    
    except Exception as e:
        return Response(
            {"error": str(e)}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_milestones(request):
    """
    Get all milestones for the authenticated user's career path
    """
    try:
        career_path = get_object_or_404(CareerPath, user=request.user)
        milestones = career_path.milestones.all()
        serializer = CareerMilestoneSerializer(milestones, many=True)
        return Response(serializer.data)
    
    except Exception as e:
        return Response(
            {"error": str(e)}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def add_milestone(request):
    """
    Add a new milestone to the user's career path
    """
    try:
        career_path = get_object_or_404(CareerPath, user=request.user)
        
        serializer = MilestoneInputSerializer(data=request.data)
        if serializer.is_valid():
            milestone = serializer.save(career_path=career_path)
            response_serializer = CareerMilestoneSerializer(milestone)
            return Response(response_serializer.data, status=status.HTTP_201_CREATED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    except Exception as e:
        return Response(
            {"error": str(e)}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def update_milestone_status(request, milestone_id):
    """
    Update milestone status (not_started, in_progress, completed)
    """
    try:
        # Get the career path for the authenticated user
        career_path = get_object_or_404(CareerPath, user=request.user)
        
        # Get the milestone
        milestone = get_object_or_404(CareerMilestone, id=milestone_id, career_path=career_path)
        
        # Update the status
        status_value = request.data.get('status')
        if status_value not in [choice[0] for choice in CareerMilestone.STATUS_CHOICES]:
            return Response(
                {"error": "Invalid status value"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        milestone.status = status_value
        milestone.save()
        
        serializer = CareerMilestoneSerializer(milestone)
        return Response(serializer.data)
    
    except Exception as e:
        return Response(
            {"error": str(e)}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

def generate_career_path_with_gemini(current_role, target_role, timeline, current_skills, education):
    """
    Generate career path recommendations using Gemini API
    """
    try:
        # Gemini API endpoint
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
        
        # Prompt for Gemini AI
        prompt = f"""
        You are a career advisor specialized in technology and software development careers.
        
        User's current role: {current_role}
        User's target role: {target_role}
        Timeline: {timeline}
        Current skills: {current_skills}
        Educational background: {education}
        
        Based on this information, please provide:
        
        1. A detailed career path from their current role to their target role, broken down into clear milestones with estimated timelines. Each milestone should be specific and measurable.
        
        2. A prioritized list of 5-7 specific skills they should develop to achieve their goal, with brief explanations of why each skill is important.
        
        3. Recommended projects or experiences that would help demonstrate these skills to potential employers.
        
        4. Potential intermediate roles that might be stepping stones to their ultimate target role.
        
        Format your response as a structured JSON with the following keys:
        - career_path_description (string)
        - milestones (array of objects with title, description, estimated_timeline, and skills_involved)
        - skills_to_develop (array of objects with name, importance_level, and reason)
        - recommended_projects (array of objects with title, description, and skills_demonstrated)
        - intermediate_roles (array of objects with title and description)
        
        Keep your recommendations specific, actionable, and tailored to the user's timeline and current background.
        """
        
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
            
            # Parse the JSON from the response text
            try:
                # Check if the response is wrapped in markdown code blocks
                if "```json" in generated_text:
                    # Extract content between markdown code blocks
                    start_idx = generated_text.find("```json") + 7  # Skip past ```json
                    end_idx = generated_text.rfind("```")
                    if end_idx > start_idx:
                        json_text = generated_text[start_idx:end_idx].strip()
                    else:
                        json_text = generated_text
                else:
                    json_text = generated_text
                
                # Clean up any remaining issues
                json_text = json_text.strip()
                
                # Parse the JSON
                result = json.loads(json_text)
                return result
            
            except json.JSONDecodeError as e:
                return {
                    "error": f"Failed to parse JSON from AI response: {str(e)}",
                    "raw_response": generated_text
                }
        else:
            return {
                "error": f"Gemini API error: {response.status_code}",
                "details": response.text
            }
        
    except Exception as e:
        return {"error": str(e)}

# Resume API endpoints
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_resume(request):
    """
    Get the user's saved resume
    """
    try:
        resume = Resume.objects.get(user=request.user)
        return Response(resume.data)
    except Resume.DoesNotExist:
        # Return empty resume structure if not found
        return Response({
            "basics": {
                "name": "",
                "email": request.user.email,
                "phone": request.user.mobile_number if hasattr(request.user, 'mobile_number') else "",
                "location": "",
                "summary": ""
            },
            "education": [],
            "experience": [],
            "skills": {
                "technical": [],
                "soft": []
            },
            "projects": [],
            "certifications": [],
            "achievements": []
        })

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def save_resume(request):
    """
    Save or update the user's resume
    """
    try:
        resume, created = Resume.objects.get_or_create(user=request.user)
        resume.data = request.data
        resume.save()
        return Response(resume.data)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def enhance_text(request):
    """
    Use AI to enhance resume text
    """
    serializer = EnhanceTextSerializer(data=request.data)
    if serializer.is_valid():
        text = serializer.validated_data['text']
        context = serializer.validated_data['context']
        target = serializer.validated_data['target']
        
        try:
            enhanced_text = enhance_text_with_ai(text, context, target)
            return Response({'enhanced_text': enhanced_text})
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    else:
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
