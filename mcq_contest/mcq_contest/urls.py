from django.urls import path
from contests import views

urlpatterns = [
    path('', views.home, name='home'),
    path('login/', views.login, name='login'),
    path('register/', views.register, name='register'),
    path('student_dashboard/', views.student_dashboard, name='student_dashboard'),
    path('admin_dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('contest/<str:contest_id>/attempt/', views.attempt_contest, name='attempt_contest'),
    path('create_contest/', views.create_contest, name='create_contest'),
    path('edit_contest/<str:contest_id>/', views.edit_contest, name='edit_contest'),
    path('delete_contest/<str:contest_id>/', views.delete_contest, name='delete_contest'),
    path('contest_leaderboard/<str:contest_id>/', views.contest_leaderboard, name='contest_leaderboard'), 
    path('logout/', views.logout, name='logout'),
    path('auth/google/login/', views.google_login, name='google_login'),
    path('auth/google/callback/', views.google_callback, name='google_callback'),
]