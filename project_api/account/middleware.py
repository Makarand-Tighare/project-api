import re
from django.http import JsonResponse
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework import status

class AdminProtectionMiddleware:
    """
    Middleware to protect admin routes by checking if the user has admin privileges.
    Routes matching the pattern /api/admin/* will be protected, except for login.
    """
    def __init__(self, get_response):
        self.get_response = get_response
        # Define the pattern for admin routes
        self.admin_url_pattern = re.compile(r'^/api/admin/')
        # Define pattern for admin login which should NOT be protected
        self.admin_login_pattern = re.compile(r'^/api/admin/login/')
        self.jwt_auth = JWTAuthentication()

    def __call__(self, request):
        # Check if the path matches the admin route pattern
        if self.admin_url_pattern.match(request.path):
            # Skip authentication for admin login endpoint and CORS preflight requests
            if self.admin_login_pattern.match(request.path) or request.method == 'OPTIONS':
                return self.get_response(request)
                
            # Try to authenticate the user with JWT
            try:
                auth_header = request.headers.get('Authorization')
                if not auth_header:
                    return JsonResponse({
                        'error': 'Authentication credentials were not provided.'
                    }, status=status.HTTP_401_UNAUTHORIZED)
                
                # Extract and validate the token
                validated_token = self.jwt_auth.get_validated_token(
                    self.jwt_auth.get_raw_token(auth_header)
                )
                
                # Check if the token has the is_admin claim and it's True
                if not validated_token.get('is_admin', False):
                    return JsonResponse({
                        'error': 'You do not have permission to access this resource.'
                    }, status=status.HTTP_403_FORBIDDEN)
                    
            except Exception as e:
                return JsonResponse({
                    'error': str(e)
                }, status=status.HTTP_401_UNAUTHORIZED)
                
        # Proceed with the request
        return self.get_response(request) 