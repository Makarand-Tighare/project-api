from django.core.management.base import BaseCommand
from mentor_mentee.models import Participant
from account.models import Department

class Command(BaseCommand):
    help = 'Updates participants with department assignments based on their branch code'

    def add_arguments(self, parser):
        parser.add_argument('--department', type=str, help='Department code to assign (optional)')
        parser.add_argument('--limit', type=int, default=0, help='Limit number of participants to update (0 = all)')

    def handle(self, *args, **options):
        department_code = options.get('department')
        limit = options.get('limit', 0)
        
        if department_code:
            try:
                department = Department.objects.get(code__iexact=department_code)
                self.stdout.write(f"Found department: {department.name} (ID: {department.id})")
                
                # Get participants with matching branch code (case insensitive)
                participants = Participant.objects.filter(branch__iexact=department_code)
                count = participants.count()
                
                if limit > 0:
                    participants = participants[:limit]
                    self.stdout.write(f"Limiting to {limit} participants")
                
                self.stdout.write(f"Found {count} participants with branch '{department_code}'")
                
                # Update participants
                updated = 0
                for p in participants:
                    p.department = department
                    p.save()
                    updated += 1
                    self.stdout.write(f"Updated {p.name} ({p.registration_no})")
                
                self.stdout.write(self.style.SUCCESS(f"Updated {updated} participants with department {department.name}"))
                
            except Department.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"Department with code '{department_code}' not found"))
                return
        else:
            # Update all participants based on their branch
            departments = Department.objects.all()
            self.stdout.write(f"Found {departments.count()} departments")
            
            participants = Participant.objects.all()
            total = participants.count()
            
            if limit > 0:
                participants = participants[:limit]
                self.stdout.write(f"Limiting to {limit} participants out of {total}")
            else:
                self.stdout.write(f"Processing all {total} participants")
            
            updated = 0
            department_counts = {}
            
            for p in participants:
                # Find matching department by branch code
                branch_code = p.branch.upper() if p.branch else None
                if branch_code:
                    dept = Department.objects.filter(code__iexact=branch_code).first()
                    if dept:
                        p.department = dept
                        p.save()
                        updated += 1
                        
                        # Count by department
                        if dept.name not in department_counts:
                            department_counts[dept.name] = 0
                        department_counts[dept.name] += 1
            
            # Report results
            self.stdout.write(self.style.SUCCESS(f"Updated {updated} participants with departments"))
            
            if department_counts:
                self.stdout.write("\nAssignment by department:")
                for dept_name, count in department_counts.items():
                    self.stdout.write(f"- {dept_name}: {count} participants") 