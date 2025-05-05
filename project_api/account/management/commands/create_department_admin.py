import os
from django.core.management.base import BaseCommand, CommandError
from account.models import Student, Department
from django.utils.crypto import get_random_string

class Command(BaseCommand):
    help = 'Creates department admin users for testing'

    def add_arguments(self, parser):
        parser.add_argument('--email', type=str, help='Email for the department admin')
        parser.add_argument('--password', type=str, help='Password for the department admin')
        parser.add_argument('--department', type=int, help='Department ID')
        parser.add_argument('--list-departments', action='store_true', help='List all departments')

    def handle(self, *args, **options):
        # List departments if requested
        if options['list_departments']:
            departments = Department.objects.all()
            self.stdout.write(self.style.SUCCESS('Available departments:'))
            for dept in departments:
                self.stdout.write(f"ID: {dept.id}, Name: {dept.name}, Code: {dept.code}")
            return

        email = options['email']
        password = options['password']
        department_id = options['department']
        
        if not all([email, password, department_id]):
            self.stdout.write(self.style.ERROR('All parameters are required: --email, --password, --department'))
            return
            
        try:
            department = Department.objects.get(id=department_id)
        except Department.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'Department with ID {department_id} does not exist'))
            return
            
        # Check if user exists
        try:
            user = Student.objects.get(email=email)
            user.set_password(password)
            user.is_department_admin = True
            user.department = department
            user.save()
            self.stdout.write(self.style.SUCCESS(f'Updated existing user {email} as department admin for {department.name}'))
        except Student.DoesNotExist:
            # Create new user
            user = Student.objects.create_user(
                email=email,
                password=password,
                first_name='Department',
                last_name='Admin',
                mobile_number='1234567890',
                reg_no=get_random_string(8, '0123456789'),
                section='A',
                year='1',
                semester='1',
                department=department
            )
            user.is_department_admin = True
            user.save()
            self.stdout.write(self.style.SUCCESS(f'Created new department admin user {email} for {department.name}'))
            
        self.stdout.write(self.style.SUCCESS('Successfully created department admin user')) 