import os
import random
import requests
import json
from rest_framework.response import Response
from rest_framework import status
from rest_framework.views import APIView
from account.serializers import UserRegistrationSerializer,UserLoginSerializer,UserProfileSerializer,UserChangePasswordSerializer,SendPasswordResetEmailSerializer,UserPasswordResetSerializer,SendOTPSerializer,VerifyOTPSerializer
from django.contrib.auth import authenticate
from account.renderers import UserRenderer
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.permissions import IsAuthenticated
from django.utils.timezone import make_aware
from datetime import datetime, timedelta
from django.utils import timezone
from account.models import Student
from account.utils import Util
from dotenv import load_dotenv
from account.permissions import IsAdminUser

# Load environment variables
load_dotenv()

# Generate Token Manually
def get_tokens_for_user(user):
  refresh = RefreshToken.for_user(user)
  # Add claims to the token
  refresh['is_admin'] = user.is_admin
  
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
        # Check if user is an admin
        if user.is_admin:
          token = get_tokens_for_user(user)
          return Response({
            'token': token,
            'msg': 'Admin Login Success',
            'is_admin': True
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
    serializer = UserRegistrationSerializer(data=request.data, context={'request': request})
    serializer.is_valid(raise_exception=True)
    user = serializer.save()
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
      return Response({'token':token, 'msg':'Login Success'}, status=status.HTTP_200_OK)
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
      
      # Return dashboard data
      return Response({
        'stats': {
          'total_users': total_users,
          'active_users': active_users,
          'mentors': mentors,
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