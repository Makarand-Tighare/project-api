from django.core.management.base import BaseCommand
from account.models import Department

class Command(BaseCommand):
    help = 'Create standard departments in the database'

    def handle(self, *args, **options):
        departments = [
            {"name": "Computer Science Engineering", "code": "CSE", "description": "Computer Science Engineering"},
            {"name": "Computer Science and Design", "code": "CSD", "description": "Computer Science and Design"},
            {"name": "Artificial Intelligence and Data Science", "code": "AIDS", "description": "AI and Data Science"},
            {"name": "Artificial Intelligence and Machine Learning", "code": "AIML", "description": "AI and Machine Learning"},
            {"name": "Computer Science Engineering (IoT)", "code": "CSE-IOT", "description": "CSE with IoT specialization"},
            {"name": "Computer Technology", "code": "CT", "description": "Computer Technology"},
            {"name": "Electronics and Telecommunication Engineering", "code": "ETC", "description": "E&TC Engineering"},
            {"name": "Electrical Engineering", "code": "EL", "description": "Electrical Engineering"},
            {"name": "Mechanical Engineering", "code": "ME", "description": "Mechanical Engineering"},
            {"name": "Civil Engineering", "code": "CE", "description": "Civil Engineering"},
            {"name": "Information Technology", "code": "IT", "description": "Information Technology"},
            {"name": "Electronics Engineering", "code": "ELE", "description": "Electronics Engineering"}
        ]
        
        created_count = 0
        existing_count = 0
        
        for dept_data in departments:
            department, created = Department.objects.get_or_create(
                code=dept_data["code"],
                defaults={
                    "name": dept_data["name"],
                    "description": dept_data["description"]
                }
            )
            
            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f'Created department: {department.name}'))
            else:
                existing_count += 1
                self.stdout.write(self.style.WARNING(f'Department already exists: {department.name}'))
        
        self.stdout.write(self.style.SUCCESS(f'Departments created: {created_count}, already existing: {existing_count}')) 