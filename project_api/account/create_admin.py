from account.models import Student

def create_admin_user():
    """Create or update admin user with hardcoded credentials"""
    
    email = "ycce_admin@gmail.com"
    password = "admin@wholeycce"
    
    # Check if user exists
    if Student.objects.filter(email=email).exists():
        admin_user = Student.objects.get(email=email)
        print(f"Admin user with email {email} already exists.")
        
        # Make sure the user is an admin
        if not admin_user.is_admin:
            admin_user.is_admin = True
            admin_user.save()
            print("Updated user to admin status.")
            
        # Update password if needed
        admin_user.set_password(password)
        admin_user.save()
        print("Updated admin password.")
        
    else:
        # Create new admin user
        admin_user = Student.objects.create_user(
            email=email,
            password=password,
            first_name="CT",
            last_name="Admin",
            reg_no="ADMIN01",
            mobile_number="9999999999",
            section="A",
            year="4",
            semester="8"
        )
        admin_user.is_admin = True
        admin_user.save()
        print(f"Created new admin user with email {email}")
    
    return admin_user

if __name__ == "__main__":
    admin_user = create_admin_user()
    print(f"Admin user {admin_user.email} is ready to use.") 