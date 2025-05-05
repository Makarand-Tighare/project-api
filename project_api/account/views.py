import os
import random
import requests
import json
from rest_framework.response import Response
from rest_framework import status
from rest_framework.views import APIView
from account.serializers import (
    UserRegistrationSerializer, UserLoginSerializer, UserProfileSerializer,
    UserChangePasswordSerializer, SendPasswordResetEmailSerializer,
    UserPasswordResetSerializer, SendOTPSerializer, VerifyOTPSerializer,
    DepartmentSerializer, DepartmentParticipantSerializer
)
from django.contrib.auth import authenticate
from account.renderers import UserRenderer
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.permissions import IsAuthenticated
from django.utils.timezone import make_aware
from datetime import datetime, timedelta
from django.utils import timezone
from account.models import Student, Department, DepartmentParticipant
from account.utils import Util
from dotenv import load_dotenv
from account.permissions import IsAdminUser, IsDepartmentAdminUser, IsDepartmentAdminForDepartment
from django.db.models import Q

# Load environment variables
load_dotenv()

# Generate Token Manually
def get_tokens_for_user(user):
  refresh = RefreshToken.for_user(user)
  # Add claims to the token
  refresh['is_admin'] = user.is_admin
  refresh['is_department_admin'] = user.is_department_admin
  if user.department:
    refresh['department_id'] = user.department.id
  
  return {
      'refresh': str(refresh),
      'access': str(refresh.access_token),
  }

# Admin login view
class AdminLoginView(APIView):
  renderer_classes = [UserRenderer]
  def post(self, request, format=None):
    try:
      email = request.data.get('email')
      password = request.data.get('password')
      
      print(f"Admin login attempt: {email}")  # Debug logging
      
      # Special case for hardcoded admin credentials
      if email == "ycce_ct_admin@gmail.com":
        # Get or create the admin user to ensure it exists
        try:
          admin_user = Student.objects.get(email=email)
          # Verify password directly for the special admin
          if not admin_user.check_password(password):
            return Response({
              'errors': {'non_field_errors': ['Invalid password for admin account']}
            }, status=status.HTTP_401_UNAUTHORIZED)
        except Student.DoesNotExist:
          # This should not happen if create_admin.py is run
          return Response({
            'errors': {'non_field_errors': ['Admin account does not exist']}
          }, status=status.HTTP_404_NOT_FOUND)
        
        # Admin user exists and password is valid
        if not admin_user.is_admin:
          admin_user.is_admin = True
          admin_user.save()
          print(f"Updated user {email} to admin status.")
          
        token = get_tokens_for_user(admin_user)
        return Response({
          'token': token,
          'msg': 'Admin Login Success',
          'is_admin': True
        }, status=status.HTTP_200_OK)
      
      # Regular admin authentication flow
      user = authenticate(email=email, password=password)
      
      if user is not None:
        # Check if user is an admin or department admin
        if user.is_admin:
          token = get_tokens_for_user(user)
          return Response({
            'token': token,
            'msg': 'Admin Login Success',
            'is_admin': True
          }, status=status.HTTP_200_OK)
        elif user.is_department_admin:
          token = get_tokens_for_user(user)
          return Response({
            'token': token,
            'msg': 'Department Admin Login Success',
            'is_department_admin': True,
            'department': user.department.name if user.department else None
          }, status=status.HTTP_200_OK)
        else:
          return Response({
            'errors': {'non_field_errors': ['You are not authorized as an admin']}
          }, status=status.HTTP_403_FORBIDDEN)
      else:
        return Response({
          'errors': {'non_field_errors': ['Email or Password is not Valid']}
        }, status=status.HTTP_401_UNAUTHORIZED)
    except Exception as e:
      print(f"Admin login error: {str(e)}")  # Debug logging
      return Response({
        'errors': {'non_field_errors': [str(e)]}
      }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class UserRegistrationView(APIView):
  renderer_classes = [UserRenderer]
  def post(self, request, format=None):
    print("Registration data:", request.data)  # Debug data
    
    serializer = UserRegistrationSerializer(data=request.data, context={'request': request})
    
    if not serializer.is_valid():
      print("Serializer errors:", serializer.errors)  # Debug validation errors
      return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
      
    user = serializer.save()
    print(f"User created with department: {user.department}")  # Debug department
    
    # If department is selected, also create a DepartmentParticipant entry
    if user.department:
      print(f"Creating participant for department: {user.department.name}")  # Debug
      DepartmentParticipant.objects.create(
        student=user,
        department=user.department
      )
    else:
      print("No department selected during registration")
      
    token = get_tokens_for_user(user)
    return Response({'token':token, 'msg':'Registration Successful'}, status=status.HTTP_201_CREATED)
  
class SendOTPView(APIView):
    renderer_classes = [UserRenderer]
    def post(self, request):
        serializer = SendOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']
        otp = random.randint(100000, 999999)
        request.session['otp'] = otp
        request.session['otp_email'] = email
        request.session['otp_expires_at'] = timezone.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"OTP sent to {email}: {otp}")  # Debug logging
        body = f'Your OTP Code code is {otp}\n\nOtp is valid for 10 min only'
        data = {
          'subject':'Verify your account',
          'body':body,
          'to_email':email
        }
        Util.send_email(data)
        return Response({"msg": "OTP sent successfully."}, status=status.HTTP_200_OK)


class VerifyOtpView(APIView):
    renderer_classes = [UserRenderer]
    def post(self, request):
        serializer = VerifyOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']
        otp = serializer.validated_data['otp']

        # Retrieve session data
        session_otp = request.session.get('otp')
        session_email = request.session.get('otp_email')
        session_otp_expires_at = request.session.get('otp_expires_at')
        
        if not all([session_otp, session_email, session_otp_expires_at]):
          return Response({'msg': 'OTP not found or session expired'}, status=status.HTTP_400_BAD_REQUEST)

        # Parse session_otp_expires_at back to datetime
        session_otp_expires_at = make_aware(datetime.strptime(session_otp_expires_at, '%Y-%m-%d %H:%M:%S'))

        if email != session_email:
          return Response({'msg': 'Email mismatch'}, status=status.HTTP_400_BAD_REQUEST)
        
        if timezone.now() - timedelta(minutes=10) > session_otp_expires_at:
            return Response({'msg': 'OTP expired'}, status=status.HTTP_400_BAD_REQUEST)
        if str(session_otp) == str(otp):
            try:
                request.session.flush()  # Clear the session after verification
                return Response({'msg': 'OTP verified successfully'}, status=status.HTTP_200_OK)

            except Student.DoesNotExist:
                return Response({'msg': 'Unexpected error occurs please try after some time'}, status=status.HTTP_404_NOT_FOUND)
        else:
            return Response({'msg': 'Invalid OTP'}, status=status.HTTP_400_BAD_REQUEST)
    

class UserLoginView(APIView):
  renderer_classes = [UserRenderer]
  def post(self, request, format=None):
    serializer = UserLoginSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    email = serializer.data.get('email')
    password = serializer.data.get('password')
    user = authenticate(email=email, password=password)
    print(user)
    if user is not None:
      token = get_tokens_for_user(user)
      response_data = {
        'token': token, 
        'msg': 'Login Success',
        'is_admin': user.is_admin,
        'is_department_admin': user.is_department_admin
      }
      
      if user.department:
        response_data['department'] = {
          'id': user.department.id,
          'name': user.department.name
        }
        
      return Response(response_data, status=status.HTTP_200_OK)
    else:
      return Response({'errors':{'non_field_errors':['Email or Password is not Valid']}}, status=status.HTTP_404_NOT_FOUND)


class UserProfileView(APIView):
  renderer_classes = [UserRenderer]
  permission_classes = [IsAuthenticated]
  def get(self, request, format=None):
    serializer = UserProfileSerializer(request.user)
    return Response(serializer.data, status=status.HTTP_200_OK)
  

class UserChangePasswordView(APIView):
  renderer_classes = [UserRenderer]
  permission_classes = [IsAuthenticated]
  def post(self, request, format=None):
    serializer = UserChangePasswordSerializer(data=request.data, context={'user':request.user})
    serializer.is_valid(raise_exception=True)
    return Response({'msg':'Password Changed Successfully'}, status=status.HTTP_200_OK)
  

class SendPasswordResetEmailView(APIView):
  renderer_classes = [UserRenderer]
  def post(self, request, format=None):
    serializer = SendPasswordResetEmailSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    return Response({'msg':'Password Reset link send. Please check your Email'}, status=status.HTTP_200_OK)
  

class UserPasswordResetView(APIView):
  renderer_classes = [UserRenderer]
  def post(self, request, uid, token, format=None):
    serializer = UserPasswordResetSerializer(data=request.data, context={'uid':uid, 'token':token})
    serializer.is_valid(raise_exception=True)
    return Response({'msg':'Password Reset Successfully'}, status=status.HTTP_200_OK)

# Add a new class for profile updates
class UserProfileUpdateView(APIView):
  renderer_classes = [UserRenderer]
  permission_classes = [IsAuthenticated]
  
  def patch(self, request, format=None):
    try:
      # Get the user object
      user = request.user
      
      # Use request.data which is already parsed by DRF
      data = request.data
      
      # Update fields if they exist in the request
      if 'first_name' in data:
        user.first_name = data['first_name']
      if 'last_name' in data:
        user.last_name = data['last_name']
      if 'mobile_number' in data:
        user.mobile_number = data['mobile_number']
      if 'section' in data:
        user.section = data['section']
      if 'year' in data:
        user.year = data['year']
      if 'semester' in data:
        user.semester = data['semester']
      
      # Handle department update
      if 'department_id' in data:
        try:
          department = Department.objects.get(id=data['department_id'])
          user.department = department
          
          # Create DepartmentParticipant if not exists
          DepartmentParticipant.objects.get_or_create(
            student=user,
            department=department,
            defaults={'is_active': True}
          )
        except Department.DoesNotExist:
          return Response({
            'error': f"Department with ID {data['department_id']} does not exist"
          }, status=status.HTTP_400_BAD_REQUEST)
      
      # Save the updated user
      user.save()
      
      # Return the updated user data
      serializer = UserProfileSerializer(user)
      return Response({
        'msg': 'Profile updated successfully',
        'user': serializer.data
      }, status=status.HTTP_200_OK)
    
    except Exception as e:
      return Response({
        'error': str(e)
      }, status=status.HTTP_400_BAD_REQUEST)

# Department management views
class DepartmentListCreateView(APIView):
  permission_classes = [IsAuthenticated, IsAdminUser]
  
  def get(self, request):
    """Get all departments"""
    departments = Department.objects.all()
    serializer = DepartmentSerializer(departments, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)
  
  def post(self, request):
    """Create a new department"""
    serializer = DepartmentSerializer(data=request.data)
    if serializer.is_valid():
      serializer.save()
      return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
class DepartmentDetailView(APIView):
  permission_classes = [IsAuthenticated]
  
  def get_object(self, pk):
    try:
      return Department.objects.get(pk=pk)
    except Department.DoesNotExist:
      return None
  
  def get(self, request, pk):
    """Get department details"""
    department = self.get_object(pk)
    if not department:
      return Response({'error': 'Department not found'}, status=status.HTTP_404_NOT_FOUND)
      
    # Check permissions - Admin can access any department, department admin only their own
    if request.user.is_department_admin and request.user.department != department:
      return Response({'error': 'You do not have permission to view this department'}, 
                      status=status.HTTP_403_FORBIDDEN)
      
    serializer = DepartmentSerializer(department)
    return Response(serializer.data, status=status.HTTP_200_OK)
  
  def put(self, request, pk):
    """Update department details - admin only"""
    if not request.user.is_admin:
      return Response({'error': 'Only system admins can update departments'}, 
                      status=status.HTTP_403_FORBIDDEN)
                      
    department = self.get_object(pk)
    if not department:
      return Response({'error': 'Department not found'}, status=status.HTTP_404_NOT_FOUND)
      
    serializer = DepartmentSerializer(department, data=request.data)
    if serializer.is_valid():
      serializer.save()
      return Response(serializer.data, status=status.HTTP_200_OK)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

# Manage department participants
class DepartmentParticipantsView(APIView):
  permission_classes = [IsAuthenticated]
  
  def get(self, request, department_id):
    """Get all participants for a department"""
    try:
      department = Department.objects.get(pk=department_id)
    except Department.DoesNotExist:
      return Response({'error': 'Department not found'}, status=status.HTTP_404_NOT_FOUND)
      
    # Check permissions - Admin can access any department, department admin only their own
    if request.user.is_department_admin and request.user.department != department:
      return Response({'error': 'You do not have permission to view participants for this department'}, 
                      status=status.HTTP_403_FORBIDDEN)
    
    # Get participants
    participants = DepartmentParticipant.objects.filter(department=department)
    serializer = DepartmentParticipantSerializer(participants, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)
  
  def post(self, request, department_id):
    """Add a participant to a department"""
    try:
      department = Department.objects.get(pk=department_id)
    except Department.DoesNotExist:
      return Response({'error': 'Department not found'}, status=status.HTTP_404_NOT_FOUND)
      
    # Check permissions - Admin can add to any department, department admin only their own
    if request.user.is_department_admin and request.user.department != department:
      return Response({'error': 'You do not have permission to add participants to this department'}, 
                      status=status.HTTP_403_FORBIDDEN)
    
    # Get student by email or id
    student_id = request.data.get('student_id')
    student_email = request.data.get('student_email')
    
    if not student_id and not student_email:
      return Response({'error': 'student_id or student_email is required'}, 
                      status=status.HTTP_400_BAD_REQUEST)
    
    try:
      if student_id:
        student = Student.objects.get(id=student_id)
      else:
        student = Student.objects.get(email=student_email)
    except Student.DoesNotExist:
      return Response({'error': 'Student not found'}, status=status.HTTP_404_NOT_FOUND)
    
    # Check if already a participant
    if DepartmentParticipant.objects.filter(student=student, department=department).exists():
      return Response({'error': 'Student is already a participant in this department'}, 
                      status=status.HTTP_400_BAD_REQUEST)
    
    # Create participant
    additional_info = request.data.get('additional_info', {})
    participant = DepartmentParticipant.objects.create(
      student=student,
      department=department,
      additional_info=additional_info
    )
    
    # Update student's department if not already set
    if not student.department:
      student.department = department
      student.save()
    
    serializer = DepartmentParticipantSerializer(participant)
    return Response(serializer.data, status=status.HTTP_201_CREATED)

# Assign a department admin
class AssignDepartmentAdminView(APIView):
  permission_classes = [IsAuthenticated, IsAdminUser]
  
  def post(self, request):
    """Assign a user as department admin"""
    student_id = request.data.get('student_id')
    student_email = request.data.get('student_email')
    department_id = request.data.get('department_id')
    
    if not department_id:
      return Response({'error': 'department_id is required'}, 
                      status=status.HTTP_400_BAD_REQUEST)
                      
    if not student_id and not student_email:
      return Response({'error': 'student_id or student_email is required'}, 
                      status=status.HTTP_400_BAD_REQUEST)
    
    try:
      department = Department.objects.get(pk=department_id)
    except Department.DoesNotExist:
      return Response({'error': 'Department not found'}, status=status.HTTP_404_NOT_FOUND)
    
    try:
      if student_id:
        student = Student.objects.get(id=student_id)
      else:
        student = Student.objects.get(email=student_email)
    except Student.DoesNotExist:
      return Response({'error': 'Student not found'}, status=status.HTTP_404_NOT_FOUND)
    
    # Make student a department admin
    student.is_department_admin = True
    student.department = department
    student.save()
    
    # Make sure student is also a participant
    DepartmentParticipant.objects.get_or_create(
      student=student,
      department=department,
      defaults={'is_active': True}
    )
    
    return Response({
      'msg': f'User {student.email} set as admin for {department.name} department',
      'user': UserProfileSerializer(student).data
    }, status=status.HTTP_200_OK)

# List all department admins
class DepartmentAdminsView(APIView):
  permission_classes = [IsAuthenticated, IsAdminUser]
  
  def get(self, request):
    """Get all department admins"""
    admins = Student.objects.filter(is_department_admin=True)
    serializer = UserProfileSerializer(admins, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)

# Example of an admin-only view
class AdminDashboardView(APIView):
  permission_classes = [IsAuthenticated, IsAdminUser]
  
  def get(self, request, format=None):
    """
    Admin dashboard endpoint that retrieves system statistics and metrics
    only available to admin users.
    """
    try:
      # Get total number of users
      total_users = Student.objects.count()
      active_users = Student.objects.filter(is_active=True).count()
      
      # Get count of mentors
      mentors = Student.objects.filter(is_mentor=True).count()
      
      # Department stats
      departments = Department.objects.all()
      department_stats = []
      
      for dept in departments:
        participants_count = DepartmentParticipant.objects.filter(department=dept).count()
        department_stats.append({
          'id': dept.id,
          'name': dept.name,
          'participants_count': participants_count
        })
      
      # Return dashboard data
      return Response({
        'stats': {
          'total_users': total_users,
          'active_users': active_users,
          'mentors': mentors,
          'departments': len(departments)
        },
        'department_stats': department_stats,
        'admin_info': {
          'user_email': request.user.email,
          'admin_since': request.user.created_at.strftime('%Y-%m-%d'),
        }
      }, status=status.HTTP_200_OK)
    except Exception as e:
      return Response({
        'error': str(e)
      }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# Department admin dashboard
class DepartmentAdminDashboardView(APIView):
  permission_classes = [IsAuthenticated, IsDepartmentAdminUser]
  
  def get(self, request):
    """Dashboard for department admins showing only their department data"""
    try:
      department = request.user.department
      if not department:
        return Response({
          'error': 'You are not assigned to any department'
        }, status=status.HTTP_400_BAD_REQUEST)
        
      # Get participants in this department
      participants = DepartmentParticipant.objects.filter(department=department)
      participant_count = participants.count()
      active_participants = participants.filter(is_active=True).count()
      
      # Return dashboard data
      return Response({
        'department': DepartmentSerializer(department).data,
        'stats': {
          'total_participants': participant_count,
          'active_participants': active_participants,
        },
        'admin_info': {
          'user_email': request.user.email,
          'admin_since': request.user.created_at.strftime('%Y-%m-%d'),
        }
      }, status=status.HTTP_200_OK)
    except Exception as e:
      return Response({
        'error': str(e)
      }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# Public view for getting departments (for registration)
class DepartmentListPublicView(APIView):
  def get(self, request):
    """Get all departments - public endpoint"""
    departments = Department.objects.all()
    serializer = DepartmentSerializer(departments, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)