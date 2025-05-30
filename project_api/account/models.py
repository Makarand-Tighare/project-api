from django.db import models
from django.contrib.auth.models import BaseUserManager,AbstractBaseUser, PermissionsMixin
from account.choise import *
from django.utils import timezone
from datetime import timedelta

# Create your models here.

class Department(models.Model):
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=10, unique=True)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

#  Custom User Manager
class StudentManager(BaseUserManager):
  def create_user(self, email, first_name, last_name, mobile_number, reg_no, section, year, semester, department=None, password=None, password2=None):
      """
      Creates and saves a User with the given email, name, tc and password.
      """
      if not email:
          raise ValueError('User must have an email address')

      user = self.model(
          email=self.normalize_email(email),
          first_name=first_name,
          last_name=last_name,
          mobile_number=mobile_number,
          reg_no=reg_no,
          section=section,
          year=year,
          semester=semester,
          department=department,
      )

      user.set_password(password)
      user.save(using=self._db)
      return user
  
  def create_superuser(self,email,password,**other_fields):
    other_fields.setdefault('is_admin',True)
    other_fields.setdefault('is_active',True)
    
    if not email:
        raise ValueError(("Users must have an email address"))
    
    email=self.normalize_email(email)
    user=self.model(email=email,**other_fields)
    user.set_password(password)
    user.save()
    return user

class Student(AbstractBaseUser,PermissionsMixin):
  
  email = models.EmailField(
      verbose_name='Email',
      max_length=255,
      unique=True,
  )
  first_name = models.CharField(max_length=200)
  middle_name = models.CharField(max_length=200)
  last_name = models.CharField(max_length=200)
  mobile_number = models.CharField(max_length=13)
  reg_no = models.CharField(max_length=8)
  section = models.CharField(max_length=1,choices=SECTION_CHOICES)
  semester = models.CharField(max_length=1,choices=SEMESTER_CHOICES)
  year = models.CharField(max_length=1,choices=YEAR_CHOICES)
  department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, related_name='students')
  is_active = models.BooleanField(default=True)
  is_mentor = models.BooleanField(default=False)
  is_admin = models.BooleanField(default=False)
  is_department_admin = models.BooleanField(default=False)  # New field for department admin
  created_at = models.DateTimeField(auto_now_add=True)
  updated_at = models.DateTimeField(auto_now=True)

  linkedin_access_token = models.CharField(max_length=1000, blank=True, null=True)
  
  # Google OAuth fields
  google_token = models.CharField(max_length=1000, blank=True, null=True)
  google_refresh_token = models.CharField(max_length=1000, blank=True, null=True)
  google_token_uri = models.CharField(max_length=255, blank=True, null=True)
  google_token_expiry = models.DateTimeField(null=True, blank=True)
  google_scopes = models.TextField(blank=True, null=True)  # Stored as JSON string

  objects = StudentManager()

  USERNAME_FIELD = 'email'
  REQUIRED_FIELDS = ['first_name', 'last_name','mobile_number','reg_no']

  def __str__(self):
      return self.email

  def has_perm(self, perm, obj=None):
      "Does the user have a specific permission?"
      # Simplest possible answer: Yes, always
      return self.is_admin

  def has_module_perms(self, app_label):
      "Does the user have permissions to view the app `app_label`?"
      # Simplest possible answer: Yes, always
      return True

  @property
  def is_staff(self):
      "Is the user a member of staff?"
      # Simplest possible answer: All admins are staff
      return self.is_admin
      
# Department-specific participant model
class DepartmentParticipant(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='department_participations')
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name='participants')
    registration_date = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    additional_info = models.JSONField(blank=True, null=True)  # Flexible field for department-specific data
    
    class Meta:
        unique_together = ('student', 'department')  # Prevent duplicate enrollments
        
    def __str__(self):
        return f"{self.student.email} - {self.department.name}"

class OTP(models.Model):
    email = models.EmailField()
    otp = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)

    def __str__(self):
        return f"OTP for {self.email}"
    
    def save(self, *args, **kwargs):
        # Set expiration time to 10 minutes from now if not already set
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(minutes=10)
        super().save(*args, **kwargs)

    @property
    def is_expired(self):
        return timezone.now() > self.expires_at