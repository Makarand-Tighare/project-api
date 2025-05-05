import os
import random
from django.core.management.base import BaseCommand
from account.models import Student, Department, DepartmentParticipant
from django.utils.crypto import get_random_string

class Command(BaseCommand):
    help = 'Creates test student users in departments'

    def add_arguments(self, parser):
        parser.add_argument('--count', type=int, default=5, help='Number of students per department')
        parser.add_argument('--department', type=int, help='Department ID (optional, if not provided creates students in all departments)')

    def handle(self, *args, **options):
        count = options['count']
        department_id = options['department']
        
        if department_id:
            try:
                departments = [Department.objects.get(id=department_id)]
            except Department.DoesNotExist:
                self.stdout.write(self.style.ERROR(f'Department with ID {department_id} does not exist'))
                return
        else:
            departments = Department.objects.all()
            
        total_students = 0
        
        for department in departments:
            for i in range(count):
                # Create a unique email for each student
                email = f"student_{department.code.lower()}_{i+1}@example.com"
                
                # Check if the user already exists
                if Student.objects.filter(email=email).exists():
                    self.stdout.write(f"Student {email} already exists, skipping...")
                    continue
                
                # Random registration number
                reg_no = get_random_string(8, '0123456789')
                
                # Create the student
                student = Student.objects.create_user(
                    email=email,
                    password="Student@123",
                    first_name=f"Student{i+1}",
                    last_name=department.code,
                    mobile_number=f"98765{random.randint(10000, 99999)}",
                    reg_no=reg_no,
                    section=random.choice(['A', 'B', 'C']),
                    year=str(random.randint(1, 4)),
                    semester=str(random.randint(1, 8)),
                    department=department
                )
                
                # Create department participant
                DepartmentParticipant.objects.create(
                    student=student,
                    department=department
                )
                
                total_students += 1
                self.stdout.write(f"Created student {email} in {department.name}")
                
        self.stdout.write(self.style.SUCCESS(f'Successfully created {total_students} test students')) 