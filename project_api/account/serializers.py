from rest_framework import serializers
from account.models import Student, Department, DepartmentParticipant
from django.utils.encoding import smart_str, force_bytes, DjangoUnicodeDecodeError
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from account.utils import Util
import random
from django.conf import settings
from django.utils import timezone

# Department Serializers
class DepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Department
        fields = ['id', 'name', 'code', 'description', 'created_at', 'updated_at']
        
class DepartmentParticipantSerializer(serializers.ModelSerializer):
    student_email = serializers.SerializerMethodField()
    department_name = serializers.SerializerMethodField()
    
    class Meta:
        model = DepartmentParticipant
        fields = ['id', 'student', 'student_email', 'department', 'department_name', 'registration_date', 'is_active', 'additional_info']
    
    def get_student_email(self, obj):
        return obj.student.email if obj.student else None
        
    def get_department_name(self, obj):
        return obj.department.name if obj.department else None
    
class UserRegistrationSerializer(serializers.ModelSerializer):
    password2 = serializers.CharField(style={'input_type': 'password'}, write_only=True)
    department_id = serializers.IntegerField(required=False, write_only=True, allow_null=True)

    class Meta:
        model = Student
        fields = ['email', 'first_name', 'last_name', 'reg_no', 'mobile_number', 'password', 'password2', 'section', 'year', 'semester', 'department_id']
        extra_kwargs = {
            'password': {'write_only': True}
        }

    def validate(self, attrs):
        password = attrs.get('password')
        password2 = attrs.get('password2')
        if password != password2:
            raise serializers.ValidationError("Password and Confirm Password don't match")
            
        # Validate department if provided
        department_id = attrs.get('department_id')
        print(f"Validating department_id: {department_id}")
        
        if department_id:
            try:
                department = Department.objects.get(id=department_id)
                print(f"Found department: {department.name}")
                attrs['department'] = department
            except Department.DoesNotExist:
                print(f"Department with ID {department_id} not found")
                raise serializers.ValidationError("Department does not exist")
        else:
            print("No department_id provided")
            attrs['department'] = None
                
        # Remove department_id from attrs as it's not a model field
        if 'department_id' in attrs:
            attrs.pop('department_id')
            
        return attrs

    def create(self, validated_data):
        print(f"Creating user with data: {validated_data}")
        department = validated_data.pop('department', None)
        user = Student.objects.create_user(**validated_data)
        
        if department:
            user.department = department
            user.save()
            
        return user

class SendOTPSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=255)
    class Meta:
        model = Student
        fields = ['email']

    def validate(self, attrs):
        email = attrs.get('email')
        if Student.objects.filter(email=email).exists():
            raise serializers.ValidationError("Student with this email already exist.")
        return attrs

class VerifyOTPSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=255)
    otp = serializers.CharField(max_length=6)

    def validate(self, data):
        return data
    
class UserLoginSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(max_length=255)
    class Meta:
        model = Student
        fields = ['email', 'password']

class UserProfileSerializer(serializers.ModelSerializer):
    department_name = serializers.SerializerMethodField()
    
    class Meta:
        model = Student
        fields = ['reg_no', 'email', 'first_name', 'middle_name', 'last_name', 'is_mentor', 'is_department_admin', 'year', 'semester', 'section', 'mobile_number', 'linkedin_access_token', 'department', 'department_name']
        
    def get_department_name(self, obj):
        return obj.department.name if obj.department else None


class UserChangePasswordSerializer(serializers.Serializer):
    password = serializers.CharField(max_length=255, style={'input_type':'password'}, write_only=True)
    password2 = serializers.CharField(max_length=255, style={'input_type':'password'}, write_only=True)
    class Meta:
        fields = ['password', 'password2']

    def validate(self, attrs):
        password = attrs.get('password')
        password2 = attrs.get('password2')
        user = self.context.get('user')

        if password != password2:
            raise serializers.ValidationError("Password and Confirm Password doesn't match")
        
        user.set_password(password)
        user.save()
        return attrs

class SendPasswordResetEmailSerializer(serializers.Serializer):
  email = serializers.EmailField(max_length=255)
  class Meta:
    fields = ['email']

  def validate(self, attrs):
    email = attrs.get('email')
    if Student.objects.filter(email=email).exists():
      user = Student.objects.get(email = email)
      uid = urlsafe_base64_encode(force_bytes(user.id))
      print('Encoded UID', uid)
      token = PasswordResetTokenGenerator().make_token(user)
      print('Password Reset Token', token)
      link = 'http://localhost:3000/api/user/reset/'+uid+'/'+token
      print('Password Reset Link', link)
      # Send EMail
      body = 'Click Following Link to Reset Your Password\n' + link + "\n\n\nLink will be expired in 15 min"
      data = {
        'subject':'Reset Your Password',
        'body':body,
        'to_email':user.email
      }
      Util.send_email(data)
      return attrs
    else:
      raise serializers.ValidationError('You are not a Registered User')
    

class UserPasswordResetSerializer(serializers.Serializer):
  password = serializers.CharField(max_length=255, style={'input_type':'password'}, write_only=True)
  password2 = serializers.CharField(max_length=255, style={'input_type':'password'}, write_only=True)
  class Meta:
    fields = ['password', 'password2']

  def validate(self, attrs):
    try:
      password = attrs.get('password')
      password2 = attrs.get('password2')
      uid = self.context.get('uid')
      token = self.context.get('token')
      if password != password2:
        raise serializers.ValidationError("Password and Confirm Password doesn't match")
      id = smart_str(urlsafe_base64_decode(uid))
      user = Student.objects.get(id=id)
      if not PasswordResetTokenGenerator().check_token(user, token):
        raise serializers.ValidationError('Token is not Valid or Expired')
      user.set_password(password)
      user.save()
      return attrs
    except DjangoUnicodeDecodeError as identifier:
      PasswordResetTokenGenerator().check_token(user, token)
      raise serializers.ValidationError('Token is not Valid or Expired')