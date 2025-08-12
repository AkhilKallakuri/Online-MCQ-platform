from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.hashers import make_password, check_password
from django.conf import settings
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import bson
from pymongo import MongoClient
from datetime import datetime
import pytz
import os
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

# MongoDB connection
DB = MongoClient('mongodb://localhost:27017/')['contest_platform']

def get_logged_in_user(request):
    user_id = request.session.get('user_id')
    if user_id:
        try:
            user = DB.users.find_one({'_id': bson.ObjectId(user_id)})
            if user:
                return user
            else:
                messages.error(request, 'User not found. Please log in again.')
        except bson.errors.InvalidId:
            messages.error(request, 'Invalid session. Please log in again.')
    return None


def google_login(request):
    # Initialize OAuth flow
    flow = InstalledAppFlow.from_client_config(
        {
            "web": {
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["http://127.0.0.1:8000/auth/google/callback"],
            }
        },
        scopes=[
            "openid",
            "https://www.googleapis.com/auth/userinfo.email",
            "https://www.googleapis.com/auth/userinfo.profile"
        ],
    )

    flow.redirect_uri = "http://127.0.0.1:8000/auth/google/callback"

    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent',
    )

    # Store state in session
    request.session['google_oauth_state'] = state

    return redirect(authorization_url)

def register(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        role = request.POST.get('role')

        # Validate inputs
        if not all([username, password, role]):
            messages.error(request, 'All fields are required.')
            return render(request, 'register.html', {'role': request.GET.get('role', 'student')})

        if role not in ['student', 'admin']:
            messages.error(request, 'Invalid role selected.')
            return render(request, 'register.html', {'role': request.GET.get('role', 'student')})

        # Check for duplicate username
        if DB.users.find_one({'username': username}):
            messages.error(request, 'Username already exists.')
            return render(request, 'register.html', {'role': request.GET.get('role', 'student')})

        # Create user
        user_data = {
            'username': username,
            'password': make_password(password),
            'role': role,
            'created_at': datetime.utcnow().isoformat()
        }

        try:
            result = DB.users.insert_one(user_data)
            user_id = result.inserted_id
            # Log user in
            request.session['user_id'] = str(user_id)
            messages.success(request, f'Welcome, {username}!')
            if role == 'admin':
                return redirect('admin_dashboard')
            return redirect('student_dashboard')
        except Exception as e:
            messages.error(request, f'Registration failed: {str(e)}')
            print(f"Registration error: {e}")
            return render(request, 'register.html', {'role': request.GET.get('role', 'student')})

    # GET request
    return render(request, 'register.html', {'role': request.GET.get('role', 'student')})


def google_callback(request):
    # Verify state to prevent CSRF
    state = request.session.get('google_oauth_state')
    if state != request.GET.get('state'):
        messages.error(request, 'Invalid state parameter.')
        return redirect('login')

    # Initialize OAuth flow
    flow = InstalledAppFlow.from_client_config(
        {
            "web": {
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [settings.GOOGLE_REDIRECT_URI],
            }
        },
        scopes=[
            "openid",
            "https://www.googleapis.com/auth/userinfo.email",
            "https://www.googleapis.com/auth/userinfo.profile"
        ],
    )

    flow.redirect_uri = settings.GOOGLE_REDIRECT_URI  # ✅ Correct redirect_uri

    try:
        # Fetch tokens
        flow.fetch_token(authorization_response=request.build_absolute_uri())
        credentials = flow.credentials

        # Get user info
        user_info_service = build('oauth2', 'v2', credentials=credentials)
        user_info = user_info_service.userinfo().get().execute()
        
        # Handle missing email
        email = user_info.get('email')
        if not email:
            messages.error(request, 'Could not retrieve email from Google.')
            return redirect('login')
        
        username = user_info.get('name', email.split('@')[0])
        role = request.GET.get('role', 'student')  # Get role from query parameter
        if role not in ['student', 'admin']:
            role = 'student'

        # Check if user exists in MongoDB
        user = DB.users.find_one({'email': email})
        if not user:
            user_data = {
                'username': username,
                'email': email,
                'password': None,
                'role': role,
                'created_at': datetime.utcnow().isoformat()
            }
            result = DB.users.insert_one(user_data)
            user_id = result.inserted_id
            user = user_data
            user['_id'] = user_id
        else:
            user_id = user['_id']

        # Save user in session
        request.session['user_id'] = str(user_id)
        messages.success(request, f'Welcome, {username}!')

        if user['role'] == 'admin':
            return redirect('admin_dashboard')
        return redirect('student_dashboard')

    except Exception as e:
        print(f"Google OAuth error: {e}")
        messages.error(request, f'Error during authentication: {str(e)}')
        return redirect('login')

def home(request):
    user = get_logged_in_user(request)
    if user:
        if user['role'] == 'admin':
            return redirect('admin_dashboard')
        return redirect('student_dashboard')
    return render(request, 'home.html')

def login(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        print(f"POST received - Username: {username}")  # Avoid logging password
        if not username or not password:
            messages.error(request, 'Username and password are required.')
            return render(request, 'login.html')
        user = DB.users.find_one({'username': username})
        if user:
            print(f"User found: {user['username']}, Role: {user['role']}")
            if user['password'] and check_password(password, user['password']):
                request.session['user_id'] = str(user['_id'])
                print(f"Logged in user: {user['username']}, session set: {request.session['user_id']}")
                messages.success(request, 'Login successful!')
                if user['role'] == 'admin':
                    return redirect('admin_dashboard')
                return redirect('student_dashboard')
            else:
                messages.error(request, 'Invalid password.')
        else:
            messages.error(request, 'Invalid username.')
        return render(request, 'login.html')
    
    print("GET request to login")
    user = get_logged_in_user(request)
    if user:
        print(f"Session exists for: {user['username']}, Role: {user['role']}")
    return render(request, 'login.html')

def student_dashboard(request):
    user = get_logged_in_user(request)
    if not user:
        messages.error(request, 'Please log in to access this page.')
        return redirect('login')
    if user['role'] != 'student':
        messages.error(request, 'You do not have permission to access this page.')
        return redirect('login')

    tz = pytz.timezone('Asia/Kolkata')
    now = datetime.now(tz)
    ongoing_contests = []
    upcoming_contests = []

    try:
        contest_cursor = DB.contests.find({'is_active': True})
        contest_list = list(contest_cursor)
        if not contest_list:
            messages.warning(request, 'No active contests found in the database.')

        for contest in contest_list:
            contest_id = str(contest.get('_id', 'unknown'))
            required_fields = ['name', 'start_datetime', 'end_datetime', 'questions']
            if not all(key in contest for key in required_fields):
                print(f"Skipping contest {contest_id} due to missing fields: {contest}")
                continue

            try:
                # Parse ISO-formatted datetimes
                start_dt = datetime.fromisoformat(contest['start_datetime'].replace('Z', '+00:00')).astimezone(tz)
                end_dt = datetime.fromisoformat(contest['end_datetime'].replace('Z', '+00:00')).astimezone(tz)
                is_ongoing = start_dt <= now <= end_dt
                is_upcoming = now < start_dt

                if is_ongoing or is_upcoming:
                    contest_dict = {
                        'id': contest_id,
                        'name': contest['name'],
                        'start_datetime': contest['start_datetime'],
                        'end_datetime': contest['end_datetime'],
                        'start_datetime_display': start_dt.strftime('%Y-%m-%d %H:%M:%S %Z'),
                        'end_datetime_display': end_dt.strftime('%Y-%m-%d %H:%M:%S %Z'),
                        'status': 'Ongoing' if is_ongoing else 'Upcoming',
                        'questions': contest['questions'],
                        'max_score': sum(q.get('score', 1) for q in contest['questions'])
                    }
                    # Check for attempt
                    attempt = DB.attempts.find_one({
                        'contest_id': contest_id,
                        'student_id': str(user['_id'])
                    })
                    contest_dict['attempted'] = bool(attempt)
                    contest_dict['user_score'] = attempt['score'] if attempt else None
                    contest_dict['participant_count'] = DB.attempts.count_documents({'contest_id': contest_id})

                    if is_ongoing:
                        ongoing_contests.append(contest_dict)
                    elif is_upcoming:
                        upcoming_contests.append(contest_dict)
            except ValueError as e:
                print(f"Date parsing error for contest {contest_id}: {e}")
                continue
            except Exception as e:
                print(f"Error processing contest {contest_id}: {e}")
                continue

    except Exception as e:
        print(f"Critical error in student_dashboard: {e}")
        messages.error(request, 'Error loading contests. Please try again later.')

    # Debug info
    debug_now = now.strftime('%Y-%m-%d %H:%M:%S %Z')

    return render(request, 'student_dashboard.html', {
        'ongoing_contests': ongoing_contests,
        'upcoming_contests': upcoming_contests,
        'username': user['username'],
        'debug_now': debug_now
    })

# Include other views (unchanged from previous submission for brevity)
def admin_dashboard(request):
    user = get_logged_in_user(request)
    if not user:
        messages.error(request, 'Please log in to access this page.')
        return redirect('login')
    if user['role'] != 'admin':
        messages.error(request, 'You do not have permission to access this page.')
        return redirect('login')

    tz = pytz.timezone('Asia/Kolkata')
    now = datetime.now(tz)
    contests = []

    try:
        contest_cursor = DB.contests.find()
        contest_list = list(contest_cursor)
        if not contest_list:
            messages.warning(request, 'No contests found in the database.')

        for contest in contest_list:
            try:
                contest_dict = dict(contest)
                contest_dict['id'] = str(contest['_id'])
                del contest_dict['_id']

                try:
                    start_dt = datetime.fromisoformat(contest['start_datetime'].replace('Z', '+00:00')).astimezone(tz)
                    end_dt = datetime.fromisoformat(contest['end_datetime'].replace('Z', '+00:00')).astimezone(tz)
                except ValueError as e:
                    print(f"Invalid datetime format for contest {contest_dict.get('id')}: {e}")
                    continue

                contest_dict['start_datetime_display'] = start_dt.strftime('%Y-%m-%d %H:%M:%S %Z')
                contest_dict['end_datetime_display'] = end_dt.strftime('%Y-%m-%d %H:%M:%S %Z')
                contest_dict['start_datetime'] = contest['start_datetime']
                contest_dict['end_datetime'] = contest['end_datetime']
                contest_dict['is_active'] = contest.get('is_active', True)

                questions = contest.get('questions', [])
                contest_dict['max_score'] = sum(q.get('score', 1) for q in questions)

                if not contest.get('is_active', True):
                    contest_dict['status'] = 'Inactive'
                elif now < start_dt:
                    contest_dict['status'] = 'Upcoming'
                elif start_dt <= now <= end_dt:
                    contest_dict['status'] = 'Ongoing'
                else:
                    contest_dict['status'] = 'Ended'

                attempts = list(DB.attempts.find({'contest_id': contest_dict['id']}))
                contest_dict['participant_count'] = len(attempts)
                contest_dict['scores'] = [attempt['score'] for attempt in attempts]
                contest_dict['leaderboard'] = sorted(
                    [{'student_id': attempt['student_id'], 'score': attempt['score']} for attempt in attempts],
                    key=lambda x: x['score'],
                    reverse=True
                )

                contests.append(contest_dict)
            except Exception as e:
                print(f"Error processing contest {contest_dict.get('id', 'unknown')}: {e}")
                continue

        total_contests = len(contests)
        upcoming_contests = sum(1 for c in contests if c['status'] == 'Upcoming')
        ongoing_contests = sum(1 for c in contests if c['status'] == 'Ongoing')

        debug_now = now.strftime('%Y-%m-%d %H:%M:%S %Z')

        return render(request, 'admin_dashboard.html', {
            'contests': contests,
            'username': user.get('username', 'User'),
            'total_contests': total_contests,
            'upcoming_contests': upcoming_contests,
            'ongoing_contests': ongoing_contests,
            'debug_now': debug_now
        })

    except Exception as e:
        print(f"Critical error in admin_dashboard: {e}")
        messages.error(request, 'Error loading admin dashboard. Please try again later.')
        return redirect('login')

def create_contest(request):
    user = get_logged_in_user(request)
    if not user:
        messages.error(request, 'Please log in to access this page.')
        return redirect('login')
    if user.get('role') != 'admin':
        messages.error(request, 'You do not have permission to access this page.')
        return redirect('admin_dashboard')

    if request.method == 'POST':
        try:
            name = request.POST.get('name')
            start_datetime_str = request.POST.get('start_datetime')
            end_datetime_str = request.POST.get('end_datetime')
            duration = request.POST.get('duration')
            question_count = int(request.POST.get('question_count', 0))

            if not all([name, start_datetime_str, end_datetime_str, duration]):
                messages.error(request, 'All fields are required.')
                return render(request, 'create_contest.html', {'username': user.get('username', 'User')})

            try:
                start_datetime = datetime.fromisoformat(start_datetime_str.replace('Z', '+00:00'))
                end_datetime = datetime.fromisoformat(end_datetime_str.replace('Z', '+00:00'))
            except ValueError:
                messages.error(request, 'Invalid date/time format.')
                return render(request, 'create_contest.html', {'username': user.get('username', 'User')})

            if end_datetime <= start_datetime:
                messages.error(request, 'End date/time must be after start date/time.')
                return render(request, 'create_contest.html', {'username': user.get('username', 'User')})

            try:
                duration = int(duration)
                if duration < 1:
                    messages.error(request, 'Duration must be at least 1 minute.')
                    return render(request, 'create_contest.html', {'username': user.get('username', 'User')})
            except ValueError:
                messages.error(request, 'Invalid duration format.')
                return render(request, 'create_contest.html', {'username': user.get('username', 'User')})

            questions = []
            for i in range(1, question_count + 1):
                q_type = request.POST.get(f'question_type_{i}')
                description = request.POST.get(f'question_description_{i}')
                score = request.POST.get(f'question_score_{i}', 1)
                correct_answer = request.POST.get(f'correct_answer_{i}')

                if not all([q_type, description, score, correct_answer]):
                    messages.error(request, f'Missing data for Question {i}.')
                    return render(request, 'create_contest.html', {'username': user.get('username', 'User')})

                try:
                    score = int(score)
                    if score < 0:
                        messages.error(request, f'Score for Question {i} must be non-negative.')
                        return render(request, 'create_contest.html', {'username': user.get('username', 'User')})
                except ValueError:
                    messages.error(request, f'Invalid score format for Question {i}.')
                    return render(request, 'create_contest.html', {'username': user.get('username', 'User')})

                question = {
                    'type': q_type,
                    'description': description,
                    'score': score
                }

                if q_type in ['mcq', 'msq']:
                    options = request.POST.getlist(f'options_{i}[]')
                    if len(options) < 2:
                        messages.error(request, f'Question {i} (MCQ/MSQ) requires at least 2 options.')
                        return render(request, 'create_contest.html', {'username': user.get('username', 'User')})
                    question['options'] = options
                    if q_type == 'msq':
                        question['answer'] = [ans.strip() for ans in correct_answer.split(',')]
                    else:
                        question['answer'] = correct_answer
                else:
                    question['answer'] = correct_answer

                questions.append(question)

            contest_data = {
                'name': name,
                'start_datetime': start_datetime.isoformat(),
                'end_datetime': end_datetime.isoformat(),
                'duration': duration,
                'questions': questions,
                'created_by': str(user['_id']),
                'is_active': True
            }

            DB.contests.insert_one(contest_data)
            messages.success(request, 'Contest created successfully!')
            return redirect('admin_dashboard')

        except Exception as e:
            messages.error(request, 'Error creating contest. Please try again.')
            print(f"Error in create_contest: {e}")
            return render(request, 'create_contest.html', {'username': user.get('username', 'User')})

    return render(request, 'create_contest.html', {'username': user.get('username', 'User')})

def edit_contest(request, contest_id):
    user = get_logged_in_user(request)
    if not user:
        messages.error(request, 'Please log in to access this page.')
        return redirect('login')
    if user.get('role') != 'admin':
        messages.error(request, 'You do not have permission to access this page.')
        return redirect('admin_dashboard')

    try:
        contest = DB.contests.find_one({'_id': bson.ObjectId(contest_id)})
        if not contest:
            messages.error(request, 'Contest not found.')
            return redirect('admin_dashboard')

        if request.method == 'POST':
            name = request.POST.get('name')
            start_datetime_str = request.POST.get('start_datetime')
            end_datetime_str = request.POST.get('end_datetime')
            duration = request.POST.get('duration')
            is_active = request.POST.get('is_active') == 'on'
            question_count = int(request.POST.get('question_count', 0))

            if not all([name, start_datetime_str, end_datetime_str, duration]):
                messages.error(request, 'All fields are required.')
                return render(request, 'edit_contest.html', {'contest': contest, 'username': user.get('username', 'User')})

            try:
                start_datetime = datetime.fromisoformat(start_datetime_str.replace('Z', '+00:00'))
                end_datetime = datetime.fromisoformat(end_datetime_str.replace('Z', '+00:00'))
            except ValueError:
                messages.error(request, 'Invalid date/time format.')
                return render(request, 'edit_contest.html', {'contest': contest, 'username': user.get('username', 'User')})

            if end_datetime <= start_datetime:
                messages.error(request, 'End date/time must be after start date/time.')
                return render(request, 'edit_contest.html', {'contest': contest, 'username': user.get('username', 'User')})

            try:
                duration = int(duration)
                if duration < 1:
                    messages.error(request, 'Duration must be at least 1 minute.')
                    return render(request, 'edit_contest.html', {'contest': contest, 'username': user.get('username', 'User')})
            except ValueError:
                messages.error(request, 'Invalid duration format.')
                return render(request, 'edit_contest.html', {'contest': contest, 'username': user.get('username', 'User')})

            questions = []
            for i in range(1, question_count + 1):
                q_type = request.POST.get(f'question_type_{i}')
                description = request.POST.get(f'question_description_{i}')
                score = request.POST.get(f'question_score_{i}', 1)
                correct_answer = request.POST.get(f'correct_answer_{i}')

                if not all([q_type, description, score, correct_answer]):
                    messages.error(request, f'Missing data for Question {i}.')
                    return render(request, 'edit_contest.html', {'contest': contest, 'username': user.get('username', 'User')})

                try:
                    score = int(score)
                    if score < 0:
                        messages.error(request, f'Score for Question {i} must be non-negative.')
                        return render(request, 'edit_contest.html', {'contest': contest, 'username': user.get('username', 'User')})
                except ValueError:
                    messages.error(request, f'Invalid score format for Question {i}.')
                    return render(request, 'edit_contest.html', {'contest': contest, 'username': user.get('username', 'User')})

                question = {
                    'type': q_type,
                    'description': description,
                    'score': score
                }

                if q_type in ['mcq', 'msq']:
                    options = request.POST.getlist(f'options_{i}[]')
                    if len(options) < 2:
                        messages.error(request, f'Question {i} (MCQ/MSQ) requires at least 2 options.')
                        return render(request, 'edit_contest.html', {'contest': contest, 'username': user.get('username', 'User')})
                    question['options'] = options
                    if q_type == 'msq':
                        question['answer'] = [ans.strip() for ans in correct_answer.split(',')]
                    else:
                        question['answer'] = correct_answer
                else:
                    question['answer'] = correct_answer

                questions.append(question)

            updated_contest = {
                'name': name,
                'start_datetime': start_datetime.isoformat(),
                'end_datetime': end_datetime.isoformat(),
                'duration': duration,
                'questions': questions,
                'created_by': str(user['_id']),
                'is_active': is_active
            }

            DB.contests.update_one(
                {'_id': bson.ObjectId(contest_id)},
                {'$set': updated_contest}
            )
            messages.success(request, 'Contest updated successfully!')
            return redirect('admin_dashboard')

        contest_dict = dict(contest)
        contest_dict['id'] = str(contest['_id'])
        contest_dict['start_datetime'] = contest['start_datetime'][:16]
        contest_dict['end_datetime'] = contest['end_datetime'][:16]
        contest_dict['questions'] = contest_dict.get('questions', [])
        for question in contest_dict['questions']:
            if isinstance(question.get('answer'), list):
                question['answer'] = ', '.join(question['answer'])
        return render(request, 'edit_contest.html', {
            'contest': contest_dict,
            'username': user.get('username', 'User')
        })

    except bson.errors.InvalidId:
        messages.error(request, 'Invalid contest ID.')
        return redirect('admin_dashboard')
    except Exception as e:
        messages.error(request, 'Error updating contest.')
        print(f"Error in edit_contest: {e}")
        return render(request, 'edit_contest.html', {'contest': contest, 'username': user.get('username', 'User')})

def attempt_contest(request, contest_id):
    user = get_logged_in_user(request)
    print(f"Attempt contest {contest_id} - Session user_id: {request.session.get('user_id')}")
    if not user:
        print("No user found, redirecting to login")
        messages.error(request, 'Please log in to access this page.')
        return redirect('login')
    print(f"User: {user['username']}, Role: {user['role']}")
    if user['role'] != 'student':
        print(f"Access denied for {user['username']}, redirecting to login")
        messages.error(request, 'You do not have permission to access this page.')
        return redirect('login')

    try:
        contest = DB.contests.find_one({'_id': bson.ObjectId(contest_id)})
        if not contest or 'questions' not in contest:
            print(f"Contest not found or invalid: {contest_id}")
            messages.error(request, 'Contest not found or invalid.')
            return redirect('student_dashboard')

        tz = pytz.timezone('Asia/Kolkata')
        now = datetime.now(tz)
        start_dt = datetime.fromisoformat(contest['start_datetime'].replace('Z', '+00:00')).astimezone(tz)
        end_dt = datetime.fromisoformat(contest['end_datetime'].replace('Z', '+00:00')).astimezone(tz)

        existing_attempt = DB.attempts.find_one({
            'contest_id': str(contest_id),
            'student_id': str(user['_id'])
        })

        if existing_attempt and existing_attempt.get('completed', False):
            print(f"Completed attempt found for {user['username']} in contest {contest_id}")
            messages.error(request, 'You have already submitted this contest.')
            return redirect('student_dashboard')

        duration_minutes = contest.get('duration', 60)
        duration_seconds = duration_minutes * 60

        attempt = existing_attempt or DB.attempts.find_one({
            'contest_id': str(contest_id),
            'student_id': str(user['_id']),
            'completed': {'$ne': True}
        })

        if not attempt and request.method != 'POST':
            attempt_data = {
                'contest_id': str(contest_id),
                'student_id': str(user['_id']),
                'start_time': now.isoformat(),
                'answers': {},
                'score': 0,
                'completed': False
            }
            DB.attempts.insert_one(attempt_data)
            attempt = attempt_data
            print(f"New attempt started for {user['username']} in contest {contest_id}")

        if attempt:
            start_time = datetime.fromisoformat(attempt['start_time'].replace('Z', '+00:00')).astimezone(tz)
            elapsed_seconds = (now - start_time).total_seconds()
            time_left = duration_seconds - elapsed_seconds

            if time_left <= 0 and not attempt.get('completed', False):
                print(f"Time expired for {user['username']} in contest {contest_id}")
                DB.attempts.update_one(
                    {'_id': attempt['_id']},
                    {'$set': {'completed': True, 'score': attempt.get('score', 0)}}
                )
                messages.error(request, 'Time is up for this contest.')
                return redirect('student_dashboard')

        if not contest.get('is_active', True):
            print(f"Contest {contest_id} is not active")
            messages.error(request, 'This contest is not active.')
            return redirect('student_dashboard')
        if now < start_dt:
            print(f"Contest {contest_id} not yet started")
            messages.error(request, 'This contest has not yet started.')
            return redirect('student_dashboard')
        if now > end_dt:
            print(f"Contest {contest_id} has ended")
            messages.error(request, 'This contest has already ended.')
            return redirect('student_dashboard')

        if request.method == 'POST':
            print("POST data:", request.POST)
            answers = {}
            for i, question in enumerate(contest['questions'], 1):
                if question.get('type') == 'msq':
                    answers[question['description']] = request.POST.getlist(f'answer_{i}') or []
                else:
                    answers[question['description']] = request.POST.get(f'answer_{i}')

            total_score = 0
            for question in contest['questions']:
                submitted_answer = answers.get(question['description'])
                correct_answer = question['answer']
                question_score = question.get('score', 1)

                print(f"Question: {question['description']}, Submitted: {submitted_answer}, Correct: {correct_answer}")

                if question.get('type') == 'msq':
                    submitted_answer = submitted_answer or []
                    correct_answer = correct_answer if isinstance(correct_answer, list) else [correct_answer]
                    if sorted(submitted_answer) == sorted(correct_answer):
                        total_score += question_score
                else:
                    if submitted_answer == correct_answer:
                        total_score += question_score

            DB.attempts.update_one(
                {'_id': attempt['_id']},
                {'$set': {
                    'answers': answers,
                    'score': total_score,
                    'completed': True
                }}
            )
            print(f"Attempt submitted for {user['username']} in contest {contest_id}, Score: {total_score}")
            messages.success(request, 'Contest submitted successfully!')
            return redirect('student_dashboard')

        contest_dict = dict(contest)
        contest_dict['id'] = str(contest['_id'])
        contest_dict['max_score'] = sum(q.get('score', 1) for q in contest['questions'])
        contest_dict['start_datetime_display'] = start_dt.strftime('%Y-%m-%d %H:%M:%S %Z')
        contest_dict['end_datetime_display'] = end_dt.strftime('%Y-%m-%d %H:%M:%S %Z')
        print(f"Rendering attempt_contest.html for {user['username']}")
        return render(request, 'attempt_contest.html', {'contest': contest_dict})

    except bson.errors.InvalidId:
        print(f"Invalid contest ID: {contest_id}")
        messages.error(request, 'Invalid contest ID.')
        return redirect('student_dashboard')
    except Exception as e:
        print(f"Error in attempt_contest: {e}")
        messages.error(request, 'An error occurred. Please try again.')
        return redirect('student_dashboard')
def delete_contest(request, contest_id):
    user = get_logged_in_user(request)
    if not user:
        messages.error(request, 'Please log in to access this page.')
        return redirect('login')
    if user['role'] != 'admin':
        messages.error(request, 'You do not have permission to delete contests.')
        return redirect('admin_dashboard')

    try:
        contest = DB.contests.find_one({'_id': bson.ObjectId(contest_id)})
        if not contest:
            messages.error(request, 'Contest not found.')
            return redirect('admin_dashboard')

        if request.method == 'POST':
            DB.contests.delete_one({'_id': bson.ObjectId(contest_id)})
            DB.attempts.delete_many({'contest_id': str(contest_id)})
            messages.success(request, 'Contest deleted successfully')
            return redirect('admin_dashboard')

        return render(request, 'delete_contest.html', {'contest': contest})
    except bson.errors.InvalidId:
        messages.error(request, 'Invalid contest ID.')
        return redirect('admin_dashboard')

from datetime import datetime
import pytz
import bson
from bson.errors import InvalidId
from dateutil import parser  # ✅ Added for flexible date parsing
from django.shortcuts import render, redirect
from django.contrib import messages

def contest_leaderboard(request, contest_id):
    user = get_logged_in_user(request)
    print(f"Leaderboard for contest_id: {contest_id} - Session user_id: {request.session.get('user_id')}")

    if not user:
        print("No user found, redirecting to login")
        messages.error(request, 'Please log in to access this page.')
        return redirect('login')

    if user['role'] != 'admin':
        print(f"Access denied for {user['username']}, redirecting to login")
        messages.error(request, 'You do not have permission to access this page.')
        return redirect('login')

    try:
        contest = DB.contests.find_one({'_id': bson.ObjectId(contest_id)})
        if not contest:
            print(f"Contest not found: {contest_id}")
            messages.error(request, 'Contest not found.')
            return redirect('admin_dashboard')

        print(f"Contest found: {contest['name']}")

        tz = pytz.timezone('Asia/Kolkata')

        # ✅ Safely parse start_datetime and end_datetime
        try:
            raw_start = contest.get('start_datetime')
            raw_end = contest.get('end_datetime')

            if not raw_start or not raw_end:
                raise ValueError("Start or end datetime missing")

            start_dt = parser.parse(raw_start).astimezone(tz)
            end_dt = parser.parse(raw_end).astimezone(tz)

            contest_dict = {
                'name': contest['name'],
                'start_datetime_display': start_dt.strftime('%Y-%m-%d %H:%M:%S %Z'),
                'end_datetime_display': end_dt.strftime('%Y-%m-%d %H:%M:%S %Z'),
            }
        except (ValueError, TypeError) as ve:
            print(f"Date parsing error for contest {contest_id}: {ve}")
            messages.error(request, 'Error parsing contest dates.')
            return redirect('admin_dashboard')

        # Fetch attempts
        attempts = list(DB.attempts.find({'contest_id': str(contest_id)}))
        participant_count = len(attempts)
        print(f"Found {participant_count} attempts for contest {contest_id}")

        leaderboard = []
        for attempt in attempts:
            student = DB.users.find_one({'_id': bson.ObjectId(attempt['student_id'])})
            student_name = student['username'] if student else 'Unknown'
            leaderboard.append({
                'student_name': student_name,
                'score': attempt['score']
            })

        # Sort leaderboard by score descending
        leaderboard.sort(key=lambda x: x['score'], reverse=True)

        print(f"Rendering contest_leaderboard.html - Participants: {participant_count}, Entries: {len(leaderboard)}")
        
        return render(request, 'contest_leaderboard.html', {
            'contest': contest_dict,
            'participant_count': participant_count,
            'leaderboard': leaderboard,
            'username': user['username']
        })

    except InvalidId:
        print(f"Invalid contest ID: {contest_id}")
        messages.error(request, 'Invalid contest ID.')
        return redirect('admin_dashboard')
    except Exception as e:
        print(f"Error in leaderboard for contest {contest_id}: {e}")
        messages.error(request, 'Error loading leaderboard.')
        return redirect('admin_dashboard')


def logout(request):
    request.session.flush()
    return redirect('home')