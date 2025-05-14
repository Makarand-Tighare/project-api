from django.core.mail import EmailMessage
import os
from twilio.rest import Client
from django.conf import settings

class Util:
  @staticmethod
  def send_email(data):
    email = EmailMessage(
      subject=data['subject'],
      body=data['body'],
      from_email=os.environ.get('EMAIL_FROM'),
      to=[data['to_email']]
    )
    email.send()

class SMSUtil:
  @staticmethod
  def send_otp(phone_number):
    """
    Send OTP to the provided phone number using Twilio Verify API
    """
    try:
      # Twilio credentials from settings
      account_sid = settings.TWILIO_ACCOUNT_SID
      auth_token = settings.TWILIO_AUTH_TOKEN
      verify_service_sid = settings.TWILIO_VERIFY_SID
      
      # Initialize Twilio client
      client = Client(account_sid, auth_token)
      
      # Send verification code
      verification = client.verify \
          .v2 \
          .services(verify_service_sid) \
          .verifications \
          .create(to=phone_number, channel='sms')
      
      return {
        'success': True,
        'sid': verification.sid,
        'status': verification.status
      }
    except Exception as e:
      return {
        'success': False,
        'error': str(e)
      }
      
  @staticmethod
  def verify_otp(phone_number, code):
    """
    Verify the OTP code sent to the phone number
    """
    try:
      # Twilio credentials from settings
      account_sid = settings.TWILIO_ACCOUNT_SID
      auth_token = settings.TWILIO_AUTH_TOKEN
      verify_service_sid = settings.TWILIO_VERIFY_SID
      
      # Initialize Twilio client
      client = Client(account_sid, auth_token)
      
      # Check verification code
      verification_check = client.verify \
          .v2 \
          .services(verify_service_sid) \
          .verification_checks \
          .create(to=phone_number, code=code)
      
      return {
        'success': True,
        'status': verification_check.status
      }
    except Exception as e:
      return {
        'success': False,
        'error': str(e)
      }