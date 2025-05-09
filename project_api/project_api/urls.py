from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/user/', include('account.urls')),
    path('api/admin/', include('account.admin_urls')),  # Admin API endpoints
    path('api/mentor_mentee/', include('mentor_mentee.urls')),
    path('api/utility/', include('projectUtility.urls')),
    path('api/career/', include('career_path.urls')),  # Career Path API endpoints
]

# Serve media files in development
# During development, we serve media files regardless of DEBUG setting
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
