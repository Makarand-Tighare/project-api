from rest_framework import permissions

class IsAdminUser(permissions.BasePermission):
    """
    Custom permission to only allow admin users to access the view.
    """
    def has_permission(self, request, view):
        # Check if user is authenticated and is an admin
        return request.user and request.user.is_authenticated and request.user.is_admin 

class IsDepartmentAdminUser(permissions.BasePermission):
    """
    Custom permission to only allow department admin users to access the view.
    """
    def has_permission(self, request, view):
        # Check if user is authenticated and is a department admin
        return request.user and request.user.is_authenticated and request.user.is_department_admin
        
class IsDepartmentAdminForDepartment(permissions.BasePermission):
    """
    Permission that allows only department admins to access data for their department.
    """
    def has_object_permission(self, request, view, obj):
        # Check if user is a department admin and belongs to the same department as the object
        if not request.user.is_authenticated or not request.user.is_department_admin:
            return False
            
        # Get department from object
        if hasattr(obj, 'department'):
            return obj.department == request.user.department
        elif hasattr(obj, 'student') and hasattr(obj.student, 'department'):
            return obj.student.department == request.user.department
        
        return False 