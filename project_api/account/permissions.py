from rest_framework import permissions

class IsAdminUser(permissions.BasePermission):
    """
    Custom permission to only allow admin users to access the view.
    """
    def has_permission(self, request, view):
        # Check if user is authenticated and is an admin
        return request.user and request.user.is_authenticated and request.user.is_admin 