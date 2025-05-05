from account.models import Student, Department

print("Department Admin Check:")
print("======================")

# Get all admins
admins = Student.objects.filter(is_department_admin=True)
print(f"Total Department Admins: {admins.count()}")
print("")

# Check each department
print("Department Status:")
for dept in Department.objects.all().order_by('id'):
    dept_admins = Student.objects.filter(is_department_admin=True, department=dept)
    if dept_admins.exists():
        print(f"ID {dept.id}: {dept.name} ({dept.code}) - Admin: {dept_admins.first().email}")
    else:
        print(f"ID {dept.id}: {dept.name} ({dept.code}) - NO ADMIN ASSIGNED")

print("")
print("All Department Admins:")
for admin in admins:
    dept_name = admin.department.name if admin.department else "None"
    print(f"Admin: {admin.email} - Department: {dept_name}") 