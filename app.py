from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, Response
from flask_cors import CORS
import hashlib
import json
import os
from functools import wraps
from werkzeug.utils import secure_filename
from datetime import datetime
import time
import queue
import uuid

app = Flask(__name__)
CORS(app)
app.secret_key = 'your-secret-key-here'  # Change this to a secure secret key

# Import blueprints after app initialization
from routes.admin import admin_bp

# Register blueprints
app.register_blueprint(admin_bp, url_prefix='/admin')

# Ensure the data directory exists
if not os.path.exists('data'):
    os.makedirs('data')

# Initialize JSON files if they don't exist
def init_json_files():
    files = ['users.json', 'skills.json', 'connections.json', 'schedules.json', 'profile.json', 'messages.json']
    for file in files:
        path = f'data/{file}'
        if not os.path.exists(path):
            with open(path, 'w') as f:
                if file == 'skills.json':
                    json.dump({}, f)
                elif file in ['connections.json', 'schedules.json', 'messages.json']:
                    json.dump([], f)
                elif file == 'profile.json':
                    json.dump({'profiles': []}, f)
                else:
                    json.dump([], f)

init_json_files()

def load_json(filename):
    try:
        with open(f'data/{filename}', 'r') as f:
            return json.load(f)
    except:
        return [] if filename != 'skills.json' else {}

def save_json(data, filename):
    with open(f'data/{filename}', 'w') as f:
        json.dump(data, f, indent=4)

def hash_password(password):
    salt = "skillswap_salt"
    salted_password = password + salt
    return hashlib.sha256(salted_password.encode()).hexdigest()

def verify_password(stored_hash, password):
    salt = "skillswap_salt"
    salted_password = password + salt
    return stored_hash == hashlib.sha256(salted_password.encode()).hexdigest()

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login to access this page', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Configure upload folder
UPLOAD_FOLDER = os.path.join('static', 'uploads', 'profiles')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5MB max file size

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH

# Create upload folder if it doesn't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.context_processor
def inject_profile():
    if 'user_id' in session:
        user_id = str(session['user_id'])
        profiles = load_json('profile.json')
        user_profiles = [p for p in profiles['profiles'] if str(p['user_id']) == user_id]
        user_profile = max(user_profiles, key=lambda x: x.get('updated_at', '')) if user_profiles else None
        
        if not user_profile:
            user_profile = {
                "user_id": user_id,
                "profile_picture": "default-avatar.png",
                "about": "",
                "location": "",
                "interests": [],
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }
            profiles['profiles'].append(user_profile)
            save_json(profiles, 'profile.json')
        
        return {'profile': user_profile}
    return {'profile': None}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        users = load_json('users.json')
        user = next((user for user in users if user['email'] == email), None)
        
        if user and verify_password(user['password'], password):
            # Check if user is active
            if not user.get('is_active', True):  # Default to True if is_active is not set
                flash('Your account has been deactivated. Please contact the administrator.', 'error')
                return redirect(url_for('login'))
            
            session['user_id'] = user['id']
            session['user_name'] = user['fullname']
            flash('Successfully logged in!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid email or password', 'error')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        fullname = request.form.get('fullname')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        if password != confirm_password:
            flash('Passwords do not match', 'error')
            return redirect(url_for('register'))
        
        users = load_json('users.json')
        
        if any(user['email'] == email for user in users):
            flash('Email already registered', 'error')
            return redirect(url_for('register'))
        
        new_user = {
            'id': len(users) + 1,
            'fullname': fullname,
            'email': email,
            'password': hash_password(password),
            'about': ''
        }
        
        users.append(new_user)
        save_json(users, 'users.json')
        
        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/dashboard')
@login_required
def dashboard():
    user_id = str(session['user_id'])
    
    # Load profile data
    profiles = load_json('profile.json')
    users = load_json('users.json')
    user_profile = next((p for p in profiles['profiles'] if str(p['user_id']) == user_id), None)
    
    # Load skills data
    skills_data = load_json('skills.json')
    user_skills = skills_data.get('user_skills', {}).get(user_id, [])
    
    # Get user's interests
    user_interests = user_profile.get('interests', []) if user_profile else []
    
    # Load connections data
    connections = load_json('connections.json')
    
    # Get other users' skills
    other_users_skills = []
    for profile in profiles['profiles']:
        if str(profile['user_id']) != user_id:
            user_data = next((u for u in users if str(u['id']) == str(profile['user_id'])), None)
            user_skills_list = skills_data.get('user_skills', {}).get(str(profile['user_id']), [])
            if user_skills_list and user_data:
                # Check if users are connected
                is_connected = any(
                    (str(conn['user_id']) == user_id and str(conn['connected_user_id']) == str(profile['user_id']) and conn['status'] == 'connected') or
                    (str(conn['user_id']) == str(profile['user_id']) and str(conn['connected_user_id']) == user_id and conn['status'] == 'connected')
                    for conn in connections
                )
                
                for skill in user_skills_list:
                    other_users_skills.append({
                        'user_id': str(user_data['id']),
                        'user_name': user_data['fullname'],
                        'profile_picture': profile.get('profile_picture', 'default-avatar.png'),
                        'skill_name': skill['skill_name'],
                        'qualification': skill['qualification'],
                        'years_of_experience': skill['years_of_experience'],
                        'description': skill['description'],
                        'matches_interest': skill['skill_name'] in user_interests,
                        'is_connected': is_connected
                    })
    
    # Sort skills: prioritize matching interests, then by years of experience
    other_users_skills.sort(key=lambda x: (-x['matches_interest'], -x['years_of_experience']))
    
    # Get featured users (users with similar interests)
    featured_users = []
    for profile in profiles['profiles']:
        if str(profile['user_id']) != user_id:
            user_data = next((u for u in users if str(u['id']) == str(profile['user_id'])), None)
            user_skills_list = skills_data.get('user_skills', {}).get(str(profile['user_id']), [])
            if user_skills_list and user_data:
                # Check if users are connected
                is_connected = any(
                    (str(conn['user_id']) == user_id and str(conn['connected_user_id']) == str(profile['user_id']) and conn['status'] == 'connected') or
                    (str(conn['user_id']) == str(profile['user_id']) and str(conn['connected_user_id']) == user_id and conn['status'] == 'connected')
                    for conn in connections
                )
                
                # Check for matching interests
                has_matching_interests = any(interest in user_interests for interest in profile.get('interests', []))
                
                if has_matching_interests:
                    featured_users.append({
                        'id': str(user_data['id']),
                        'name': user_data['fullname'],
                        'profile_picture': profile.get('profile_picture', 'default-avatar.png'),
                        'skills': [skill['skill_name'] for skill in user_skills_list[:3]],
                        'is_connected': is_connected
                    })
    
    # Sort featured users by number of matching interests
    featured_users.sort(key=lambda x: len(set(x['skills']) & set(user_interests)), reverse=True)
    
    return render_template('dashboard.html',
                         active_page='home',
                         profile=user_profile,
                         user_skills=user_skills,
                         other_users_skills=other_users_skills,
                         featured_users=featured_users[:4])

@app.route('/profile')
@login_required
def profile():
    user_id = session['user_id']
    users = load_json('users.json')
    user = next((u for u in users if u['id'] == user_id), None)
    
    # Load profile data
    profiles = load_json('profile.json')
    profile_data = next((p for p in profiles['profiles'] if p['user_id'] == user_id), None)
    
    # Load user's skills from skills.json
    skills_data = load_json('skills.json')
    user_skills = skills_data.get('user_skills', {}).get(str(user_id), [])
    
    if not profile_data:
        # Create default profile if none exists
        profile_data = {
            "user_id": user_id,
            "profile_picture": "default-avatar.png",
            "about": "",
            "location": "",
            "interests": [],
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }
        profiles['profiles'].append(profile_data)
        save_json(profiles, 'profile.json')
    
    return render_template('profile.html',
                         active_page='profile',
                         user=user,
                         profile=profile_data,
                         user_skills=user_skills)

@app.route('/api/profile/update', methods=['POST'])
@login_required
def update_profile():
    user_id = session['user_id']
    profiles = load_json('profile.json')
    profile_data = next((p for p in profiles['profiles'] if p['user_id'] == user_id), None)
    
    if not profile_data:
        return jsonify({'success': False, 'error': 'Profile not found'})
    
    # Handle profile picture upload
    if 'profile_picture' in request.files:
        file = request.files['profile_picture']
        if file and allowed_file(file.filename):
            try:
                filename = secure_filename(file.filename)
                # Add timestamp to filename to prevent overwriting
                filename = f"{int(time.time())}_{filename}"
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)
                
                # Delete old profile picture if it exists and is not the default
                old_picture = profile_data.get('profile_picture')
                if old_picture and old_picture != 'default-avatar.png':
                    old_file_path = os.path.join(app.config['UPLOAD_FOLDER'], old_picture)
                    if os.path.exists(old_file_path):
                        os.remove(old_file_path)
                
                # Update profile picture in profile data
                profile_data['profile_picture'] = filename
                profile_data['updated_at'] = datetime.now().isoformat()
                save_json(profiles, 'profile.json')
                return jsonify({'success': True})
            except Exception as e:
                print(f"Error uploading file: {str(e)}")
                return jsonify({'success': False, 'error': str(e)})
    
    # Handle other profile updates
    data = request.form
    profile_data['about'] = data.get('about', profile_data.get('about', ''))
    profile_data['location'] = data.get('location', profile_data.get('location', ''))
    profile_data['updated_at'] = datetime.now().isoformat()
    save_json(profiles, 'profile.json')
    
    return jsonify({'success': True})

@app.route('/api/skills/add', methods=['POST'])
@login_required
def add_skill():
    user_id = str(session['user_id'])
    data = request.get_json()
    
    if not data.get('skill_name'):
        return jsonify({'success': False, 'error': 'Skill name is required'})
    
    skills_data = load_json('skills.json')
    
    # Initialize user's skills array if it doesn't exist
    if 'user_skills' not in skills_data:
        skills_data['user_skills'] = {}
    if user_id not in skills_data['user_skills']:
        skills_data['user_skills'][user_id] = []
    
    # Create new skill with detailed information
    new_skill = {
        "skill_id": f"{data['skill_name'].lower()}_{len(skills_data['user_skills'][user_id]) + 1}",
        "skill_name": data['skill_name'],
        "description": data.get('description', ''),
        "qualification": data.get('qualification', 'Beginner'),
        "years_of_experience": data.get('years_of_experience', 0),
        "certifications": data.get('certifications', []),
        "projects": data.get('projects', []),
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat()
    }
    
    # Add the new skill to user's skills
    skills_data['user_skills'][user_id].append(new_skill)
    save_json(skills_data, 'skills.json')
    
    return jsonify({'success': True, 'skill': new_skill})

@app.route('/api/interests/add', methods=['POST'])
@login_required
def add_user_interest():
    user_id = session['user_id']
    interest = request.get_json().get('interest')
    
    if not interest:
        return jsonify({'success': False, 'error': 'No interest provided'})
    
    user_interests = load_json('user_interests.json')
    
    interest_entry = next((item for item in user_interests if item['user_id'] == user_id), None)
    if interest_entry:
        if interest not in interest_entry['interests']:
            interest_entry['interests'].append(interest)
    else:
        user_interests.append({
            'user_id': user_id,
            'interests': [interest]
        })
    
    save_json(user_interests, 'user_interests.json')
    return jsonify({'success': True})

@app.route('/search')
@login_required
def search():
    return render_template('search.html', active_page='search')

@app.route('/api/search')
@login_required
def api_search():
    query = request.args.get('q', '').strip().lower()
    
    if not query:
        return jsonify({
            'users': [],
            'skills': []
        })
    
    results = {
        'users': [],
        'skills': []
    }
    
    # Load all necessary data
    users = load_json('users.json')
    profiles = load_json('profile.json')
    skills_data = load_json('skills.json')
    connections = load_json('connections.json')
    current_user_id = str(session['user_id'])
    
    # Search users
    for user in users:
        if (query in user['fullname'].lower() or 
            (user.get('location') and query in user['location'].lower())):
            # Don't include the current user in results
            if str(user['id']) != current_user_id:
                # Get user's profile
                user_profile = next((p for p in profiles['profiles'] if str(p['user_id']) == str(user['id'])), None)
                
                # Get user's skills
                user_skills = skills_data.get('user_skills', {}).get(str(user['id']), [])
                
                # Check connection status
                is_connected = any(
                    (str(conn['user_id']) == current_user_id and str(conn['connected_user_id']) == str(user['id']) and conn['status'] == 'connected') or
                    (str(conn['user_id']) == str(user['id']) and str(conn['connected_user_id']) == current_user_id and conn['status'] == 'connected')
                    for conn in connections
                )
                
                # Check for pending request
                pending_request = any(
                    (str(conn['user_id']) == current_user_id and str(conn['connected_user_id']) == str(user['id']) and conn['status'] == 'pending') or
                    (str(conn['user_id']) == str(user['id']) and str(conn['connected_user_id']) == current_user_id and conn['status'] == 'pending')
                    for conn in connections
                )
                
                results['users'].append({
                    'id': user['id'],
                    'username': user['fullname'],
                    'location': user_profile.get('location', 'Not specified') if user_profile else 'Not specified',
                    'profile_picture': user_profile.get('profile_picture', 'default-avatar.png') if user_profile else 'default-avatar.png',
                    'about': user_profile.get('about', '') if user_profile else '',
                    'skills': [{
                        'name': skill['skill_name'],
                        'qualification': skill['qualification'],
                        'years': skill['years_of_experience']
                    } for skill in user_skills[:3]],  # Show top 3 skills
                    'total_skills': len(user_skills),
                    'is_connected': is_connected,
                    'pending_request': pending_request
                })
    
    # Search skills
    for user_id, user_skills in skills_data.get('user_skills', {}).items():
        for skill in user_skills:
            if (query in skill['skill_name'].lower() or 
                query in skill['description'].lower()):
                # Get user information
                user = next((u for u in users if str(u['id']) == str(user_id)), None)
                if user and str(user['id']) != str(session['user_id']):
                    # Get user's profile
                    user_profile = next((p for p in profiles['profiles'] if str(p['user_id']) == str(user_id)), None)
                    
                    results['skills'].append({
                        'id': skill['skill_id'],
                        'skill_name': skill['skill_name'],
                        'description': skill['description'],
                        'qualification': skill['qualification'],
                        'years_of_experience': skill['years_of_experience'],
                        'certifications': skill.get('certifications', []),
                        'projects': skill.get('projects', []),
                        'user': {
                            'id': user['id'],
                            'username': user['fullname'],
                            'location': user_profile.get('location', 'Not specified') if user_profile else 'Not specified',
                            'profile_picture': user_profile.get('profile_picture', 'default-avatar.png') if user_profile else 'default-avatar.png',
                            'about': user_profile.get('about', '') if user_profile else ''
                        }
                    })
    
    return jsonify(results)

@app.route('/logout')
def logout():
    session.clear()
    flash('Successfully logged out', 'success')
    return redirect(url_for('login'))

@app.route('/skills')
@login_required
def skills():
    user_id = session['user_id']
    user_skills = load_json('user_skills.json')
    all_skills = load_json('skills.json')
    
    # Get current user's skills
    current_user_skills = next((item['skills'] for item in user_skills if item['user_id'] == user_id), [])
    
    # Get available skills (skills not in user's current list)
    available_skills = [
        {'name': skill, 'icon': info.get('icon', 'star'), 'description': info.get('description', '')}
        for skill, info in all_skills.items()
        if skill not in current_user_skills
    ]
    
    return render_template('skills.html',
                         active_page='skills',
                         user_skills=current_user_skills,
                         available_skills=available_skills)

@app.route('/api/skills/remove/<skill_id>', methods=['POST'])
@login_required
def remove_skill(skill_id):
    user_id = str(session['user_id'])
    skills_data = load_json('skills.json')
    
    if 'user_skills' not in skills_data or user_id not in skills_data['user_skills']:
        return jsonify({'success': False, 'error': 'No skills found'})
    
    # Remove the skill from user's skills
    skills_data['user_skills'][user_id] = [
        skill for skill in skills_data['user_skills'][user_id]
        if skill['skill_id'] != skill_id
    ]
    
    save_json(skills_data, 'skills.json')
    return jsonify({'success': True})

@app.route('/connections')
@login_required
def connections():
    user_id = session['user_id']
    users = load_json('users.json')
    user_skills = load_json('user_skills.json')
    
    # Get current user's skills
    current_user_skills = next((item['skills'] for item in user_skills if item['user_id'] == user_id), [])
    
    # Get connected users (users with matching skills)
    connected_users = []
    for user in users:
        if user['id'] == user_id:  # Skip current user
            continue
            
        user_skill_list = next((item['skills'] for item in user_skills if item['user_id'] == user['id']), [])
        
        # Check for matching skills
        matching_skills = set(current_user_skills) & set(user_skill_list)
        if matching_skills:
            connected_users.append({
                'username': user['fullname'],
                'profile_picture': url_for('static', filename='images/default-avatar.png'),
                'matching_skills': list(matching_skills)
            })
    
    return render_template('connections.html',
                         active_page='connections',
                         connected_users=connected_users)

@app.route('/api/profile/interests/add', methods=['POST'])
@login_required
def add_interest():
    user_id = session['user_id']
    interest = request.get_json().get('interest')
    
    if not interest:
        return jsonify({'success': False, 'error': 'No interest provided'})
    
    profiles = load_json('profile.json')
    profile_data = next((p for p in profiles['profiles'] if p['user_id'] == user_id), None)
    
    if profile_data and interest not in profile_data['interests']:
        profile_data['interests'].append(interest)
        profile_data['updated_at'] = datetime.now().isoformat()
        save_json(profiles, 'profile.json')
        return jsonify({'success': True})
    
    return jsonify({'success': False, 'error': 'Interest already exists'})

@app.route('/api/profile/interests/remove', methods=['POST'])
@login_required
def remove_interest():
    user_id = session['user_id']
    interest = request.get_json().get('interest')
    
    if not interest:
        return jsonify({'success': False, 'error': 'No interest provided'})
    
    profiles = load_json('profile.json')
    profile_data = next((p for p in profiles['profiles'] if p['user_id'] == user_id), None)
    
    if profile_data and interest in profile_data['interests']:
        profile_data['interests'].remove(interest)
        profile_data['updated_at'] = datetime.now().isoformat()
        save_json(profiles, 'profile.json')
        return jsonify({'success': True})
    
    return jsonify({'success': False, 'error': 'Interest not found'})

@app.route('/api/profile/education/add', methods=['POST'])
@login_required
def add_education():
    user_id = session['user_id']
    education_data = request.get_json()
    
    # Load current profile data
    profiles = load_json('profile.json')
    
    # Find user's profile
    user_profile = next((p for p in profiles['profiles'] if p['user_id'] == user_id), None)
    
    if not user_profile:
        return jsonify({'success': False, 'message': 'Profile not found'})
    
    # Initialize education list if it doesn't exist
    if 'education' not in user_profile:
        user_profile['education'] = []
    
    # Add new education entry
    user_profile['education'].append(education_data)
    user_profile['updated_at'] = datetime.now().isoformat()
    
    # Save updated profile data
    save_json(profiles, 'profile.json')
    
    return jsonify({'success': True})

@app.route('/api/profile/work/add', methods=['POST'])
@login_required
def add_work():
    user_id = session['user_id']
    work_data = request.get_json()
    
    # Load current profile data
    profiles = load_json('profile.json')
    
    # Find user's profile
    user_profile = next((p for p in profiles['profiles'] if p['user_id'] == user_id), None)
    
    if not user_profile:
        return jsonify({'success': False, 'message': 'Profile not found'})
    
    # Initialize work experience list if it doesn't exist
    if 'work_experience' not in user_profile:
        user_profile['work_experience'] = []
    
    # Add new work experience entry
    user_profile['work_experience'].append(work_data)
    user_profile['updated_at'] = datetime.now().isoformat()
    
    # Save updated profile data
    save_json(profiles, 'profile.json')
    
    return jsonify({'success': True})

@app.route('/api/profile/education/<education_id>', methods=['GET'])
@login_required
def get_education(education_id):
    try:
        user_id = session['user_id']
        profiles = load_json('profile.json')
        
        # Find user's profile
        user_profile = next((p for p in profiles['profiles'] if p['user_id'] == user_id), None)
        
        if not user_profile or 'education' not in user_profile:
            return jsonify({'success': False, 'message': 'Profile or education not found'})
        
        education = next((edu for edu in user_profile['education'] if edu['id'] == education_id), None)
        
        if not education:
            return jsonify({'success': False, 'message': 'Education not found'})
        
        return jsonify({'success': True, 'education': education})
    except Exception as e:
        print(f"Error in get_education: {str(e)}")
        return jsonify({'success': False, 'message': 'Internal server error'})

@app.route('/api/profile/education/update', methods=['POST'])
@login_required
def update_education():
    try:
        user_id = session['user_id']
        education_data = request.get_json()
        
        profiles = load_json('profile.json')
        user_profile = next((p for p in profiles['profiles'] if p['user_id'] == user_id), None)
        
        if not user_profile or 'education' not in user_profile:
            return jsonify({'success': False, 'message': 'Profile or education not found'})
        
        education_list = user_profile['education']
        
        # Find and update the education entry
        for i, edu in enumerate(education_list):
            if edu['id'] == education_data['id']:
                education_list[i] = education_data
                break
        
        user_profile['education'] = education_list
        user_profile['updated_at'] = datetime.now().isoformat()
        
        save_json(profiles, 'profile.json')
        return jsonify({'success': True})
    except Exception as e:
        print(f"Error in update_education: {str(e)}")
        return jsonify({'success': False, 'message': 'Internal server error'})

@app.route('/api/profile/work/<work_id>', methods=['GET'])
@login_required
def get_work(work_id):
    try:
        user_id = session['user_id']
        profiles = load_json('profile.json')
        
        # Find user's profile
        user_profile = next((p for p in profiles['profiles'] if p['user_id'] == user_id), None)
        
        if not user_profile or 'work_experience' not in user_profile:
            return jsonify({'success': False, 'message': 'Profile or work experience not found'})
        
        work = next((w for w in user_profile['work_experience'] if w['id'] == work_id), None)
        
        if not work:
            return jsonify({'success': False, 'message': 'Work experience not found'})
        
        return jsonify({'success': True, 'work': work})
    except Exception as e:
        print(f"Error in get_work: {str(e)}")
        return jsonify({'success': False, 'message': 'Internal server error'})

@app.route('/api/profile/work/update', methods=['POST'])
@login_required
def update_work():
    try:
        user_id = session['user_id']
        work_data = request.get_json()
        
        profiles = load_json('profile.json')
        user_profile = next((p for p in profiles['profiles'] if p['user_id'] == user_id), None)
        
        if not user_profile or 'work_experience' not in user_profile:
            return jsonify({'success': False, 'message': 'Profile or work experience not found'})
        
        work_list = user_profile['work_experience']
        
        # Find and update the work entry
        for i, work in enumerate(work_list):
            if work['id'] == work_data['id']:
                work_list[i] = work_data
                break
        
        user_profile['work_experience'] = work_list
        user_profile['updated_at'] = datetime.now().isoformat()
        
        save_json(profiles, 'profile.json')
        return jsonify({'success': True})
    except Exception as e:
        print(f"Error in update_work: {str(e)}")
        return jsonify({'success': False, 'message': 'Internal server error'})

@app.route('/api/skills/<skill_id>', methods=['GET'])
@login_required
def get_skill(skill_id):
    try:
        user_id = str(session['user_id'])
        skills_data = load_json('skills.json')
        
        if 'user_skills' not in skills_data or user_id not in skills_data['user_skills']:
            return jsonify({'success': False, 'message': 'No skills found'})
        
        skill = next((s for s in skills_data['user_skills'][user_id] if s['skill_id'] == skill_id), None)
        
        if not skill:
            return jsonify({'success': False, 'message': 'Skill not found'})
        
        return jsonify({'success': True, 'skill': skill})
    except Exception as e:
        print(f"Error in get_skill: {str(e)}")
        return jsonify({'success': False, 'message': 'Internal server error'})

@app.route('/api/skills/update', methods=['POST'])
@login_required
def update_skill():
    try:
        user_id = str(session['user_id'])
        skill_data = request.get_json()
        
        if not skill_data.get('skill_id'):
            return jsonify({'success': False, 'message': 'Skill ID is required'})
        
        skills_data = load_json('skills.json')
        
        if 'user_skills' not in skills_data or user_id not in skills_data['user_skills']:
            return jsonify({'success': False, 'message': 'No skills found'})
        
        skill_list = skills_data['user_skills'][user_id]
        
        # Find and update the skill
        for i, skill in enumerate(skill_list):
            if skill['skill_id'] == skill_data['skill_id']:
                skill_list[i] = {
                    **skill,
                    **skill_data,
                    'updated_at': datetime.now().isoformat()
                }
                break
        
        skills_data['user_skills'][user_id] = skill_list
        save_json(skills_data, 'skills.json')
        
        return jsonify({'success': True})
    except Exception as e:
        print(f"Error in update_skill: {str(e)}")
        return jsonify({'success': False, 'message': 'Internal server error'})

@app.route('/api/users/<user_id>')
@login_required
def get_user_details(user_id):
    try:
        # Load all necessary data
        users = load_json('users.json')
        profiles = load_json('profile.json')
        skills_data = load_json('skills.json')
        connections = load_json('connections.json')
        
        # Find user
        user = next((u for u in users if str(u['id']) == str(user_id)), None)
        if not user:
            return jsonify({'success': False, 'error': 'User not found'}), 404
        
        # Find profile
        profile = next((p for p in profiles['profiles'] if str(p['user_id']) == str(user_id)), None)
        if not profile:
            profile = {
                'user_id': user_id,
                'profile_picture': 'default-avatar.png',
                'about': '',
                'location': '',
                'interests': []
            }
        
        # Get skills
        skills = skills_data.get('user_skills', {}).get(str(user_id), [])
        
        # Check if connected
        is_connected = any(
            (str(c['user_id']) == str(session['user_id']) and str(c['connected_user_id']) == str(user_id) and c['status'] == 'connected') or
            (str(c['user_id']) == str(user_id) and str(c['connected_user_id']) == str(session['user_id']) and c['status'] == 'connected')
            for c in connections
        )
        
        # Check if there's a pending connection request
        pending_request = any(
            (str(c['user_id']) == str(session['user_id']) and str(c['connected_user_id']) == str(user_id) and c['status'] == 'pending') or
            (str(c['user_id']) == str(user_id) and str(c['connected_user_id']) == str(session['user_id']) and c['status'] == 'pending')
            for c in connections
        )
        
        return jsonify({
            'success': True,
            'user': {
                'id': user['id'],
                'name': user['fullname'],
                'email': user['email']
            },
            'profile': profile,
            'skills': skills,
            'is_connected': is_connected,
            'pending_request': pending_request
        })
        
    except Exception as e:
        print(f"Error in get_user_details: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/connections', methods=['GET'])
@login_required
def get_connections():
    """Get all connections for the current user"""
    try:
        connections = load_json('connections.json')
        current_user_id = session['user_id']
        users = load_json('users.json')
        profiles = load_json('profile.json')
        skills_data = load_json('skills.json')

        print(f"Current user ID: {current_user_id}")
        print(f"All connections: {connections}")
        print(f"All users: {users}")

        # Filter connections for current user
        pending_connections = []
        connected_users = []

        for conn in connections:
            print(f"Processing connection: {conn}")
            # Check if this connection involves the current user
            if str(conn['user_id']) != str(current_user_id) and str(conn['connected_user_id']) != str(current_user_id):
                print(f"Skipping connection - not relevant to current user")
                continue

            # Get user information based on who initiated the connection
            if str(conn['user_id']) == str(current_user_id):
                other_user_id = conn['connected_user_id']
                print(f"Current user is sender, other user ID: {other_user_id}")
            else:
                other_user_id = conn['user_id']
                print(f"Current user is receiver, other user ID: {other_user_id}")

            # Get user details
            user = next((u for u in users if str(u['id']) == str(other_user_id)), None)
            if not user:
                print(f"User not found for ID: {other_user_id}")
                continue

            # Get user profile
            user_profile = next((p for p in profiles['profiles'] if str(p['user_id']) == str(other_user_id)), None)
            
            # Get user skills
            user_skills = skills_data.get('user_skills', {}).get(str(other_user_id), [])
            matching_skills = [skill['skill_name'] for skill in user_skills]

            # Prepare user data
            user_data = {
                'id': user['id'],
                'username': user['fullname'],
                'profile_picture': user_profile.get('profile_picture', 'default-avatar.png') if user_profile else 'default-avatar.png',
                'matching_skills': matching_skills
            }

            if conn['status'] == 'pending':
                print(f"Adding pending connection: {conn}")
                # Include the original connection data for proper status display
                pending_connections.append({
                    'id': conn['id'],
                    'user': user_data,
                    'user_id': conn['user_id'],  # Include who sent the request
                    'connected_user_id': conn['connected_user_id'],
                    'created_at': conn['created_at']
                })
            elif conn['status'] == 'connected':
                print(f"Adding connected user: {user_data}")
                connected_users.append(user_data)

        print(f"Final pending connections: {pending_connections}")
        print(f"Final connected users: {connected_users}")

        return jsonify({
            'pending_connections': pending_connections,
            'connected_users': connected_users
        })
    except Exception as e:
        print(f"Error in get_connections: {str(e)}")
        return jsonify({'success': False, 'message': 'Internal server error'}), 500

@app.route('/api/connections/accept/<connection_id>', methods=['POST'])
@login_required
def accept_connection(connection_id):
    """Accept a connection request"""
    try:
        connections = load_json('connections.json')
        current_user_id = str(session['user_id'])  # Convert to string for comparison
        
        print(f"Accepting connection {connection_id} for user {current_user_id}")
        print(f"All connections: {connections}")
        
        # Find the connection - look for pending connections only
        connection = next((conn for conn in connections 
                          if str(conn['id']) == str(connection_id) 
                          and conn['status'] == 'pending'
                          and str(conn['connected_user_id']) == current_user_id), None)
        
        if not connection:
            print(f"Connection {connection_id} not found or not pending")
            return jsonify({'success': False, 'message': 'Connection not found or not pending'}), 404
            
        print(f"Found connection: {connection}")
        print(f"Connection receiver ID: {connection['connected_user_id']}")
        print(f"Current user ID: {current_user_id}")
            
        # Update connection status
        connection['status'] = 'connected'
        connection['accepted_at'] = datetime.now().isoformat()
        
        # Save updated connections
        save_json(connections, 'connections.json')
        print("Connection updated successfully")
        
        return jsonify({'success': True, 'message': 'Connection request accepted'})
    except Exception as e:
        print(f"Error in accept_connection: {str(e)}")
        return jsonify({'success': False, 'message': 'Internal server error'}), 500

@app.route('/api/connections/reject/<connection_id>', methods=['POST'])
@login_required
def reject_connection(connection_id):
    """Reject a connection request"""
    try:
        connections = load_json('connections.json')
        current_user_id = str(session['user_id'])  # Convert to string

        # Find the connection
        connection = next((conn for conn in connections if str(conn['id']) == str(connection_id)), None)
        
        if not connection:
            return jsonify({'success': False, 'message': 'Connection not found'}), 404

        # Verify the current user is the recipient
        if str(connection['connected_user_id']) != current_user_id:
            return jsonify({'success': False, 'message': 'Unauthorized'}), 403

        # Remove the connection
        connections = [conn for conn in connections if str(conn['id']) != str(connection_id)]
        save_json(connections, 'connections.json')

        return jsonify({'success': True, 'message': 'Connection rejected'})
    except Exception as e:
        print(f"Error in reject_connection: {str(e)}")
        return jsonify({'success': False, 'message': 'Internal server error'}), 500

@app.route('/api/connections/request', methods=['POST'])
@login_required
def request_connection():
    """Send a connection request"""
    try:
        data = request.get_json()
        target_user_id = str(data.get('user_id'))  # Convert to string
        
        if not target_user_id:
            return jsonify({'success': False, 'message': 'Target user ID is required'}), 400

        connections = load_json('connections.json')
        current_user_id = str(session['user_id'])  # Convert to string

        # Check if any connection exists between these users (pending or connected)
        existing_connection = next(
            (conn for conn in connections 
             if ((str(conn['user_id']) == current_user_id and str(conn['connected_user_id']) == target_user_id) or
                 (str(conn['user_id']) == target_user_id and str(conn['connected_user_id']) == current_user_id))),
            None
        )

        if existing_connection:
            if existing_connection['status'] == 'pending':
                return jsonify({'success': False, 'message': 'A pending connection already exists'}), 400
            else:
                return jsonify({'success': False, 'message': 'You are already connected with this user'}), 400

        # Create new connection request with unique ID
        new_connection = {
            'id': str(int(time.time())),  # Use timestamp as unique ID
            'user_id': current_user_id,
            'connected_user_id': target_user_id,
            'status': 'pending',
            'created_at': datetime.now().isoformat()
        }

        connections.append(new_connection)
        save_json(connections, 'connections.json')

        return jsonify({'success': True, 'message': 'Connection request sent'})
    except Exception as e:
        print(f"Error in request_connection: {str(e)}")
        return jsonify({'success': False, 'message': 'Internal server error'}), 500

@app.route('/api/connections/test', methods=['POST'])
@login_required
def test_connection():
    """Create a test connection request"""
    try:
        connections = load_json('connections.json')
        current_user_id = str(session['user_id'])
        
        # Create a test connection request
        test_connection = {
            'id': str(len(connections) + 1),
            'user_id': current_user_id,  # Current user sends the request
            'connected_user_id': '2',  # Connect to user with ID 2 (as string)
            'status': 'pending',
            'created_at': datetime.now().isoformat()
        }

        connections.append(test_connection)
        save_json(connections, 'connections.json')

        return jsonify({'success': True, 'message': 'Test connection request created'})
    except Exception as e:
        print(f"Error in test_connection: {str(e)}")
        return jsonify({'success': False, 'message': 'Internal server error'}), 500

@app.route('/api/connections/debug', methods=['GET'])
@login_required
def debug_connections():
    """Debug route to check connection data structure"""
    try:
        connections = load_json('connections.json')
        current_user_id = str(session['user_id'])
        
        # Convert all IDs to strings for consistent comparison
        debug_connections = []
        for conn in connections:
            debug_conn = {
                'id': str(conn['id']),
                'user_id': str(conn['user_id']),
                'connected_user_id': str(conn['connected_user_id']),
                'status': conn['status'],
                'created_at': conn['created_at']
            }
            debug_connections.append(debug_conn)
        
        return jsonify({
            'current_user_id': current_user_id,
            'current_user_id_type': str(type(current_user_id)),
            'connections': debug_connections
        })
    except Exception as e:
        print(f"Error in debug_connections: {str(e)}")
        return jsonify({'success': False, 'message': 'Internal server error'}), 500

# Messages routes
def mark_messages_as_read(conversation_key, user_id):
    """Mark all messages in a conversation as read for a specific user"""
    try:
        # Load messages
        with open('data/messages.json', 'r') as f:
            messages_data = json.load(f)
        
        # Initialize messages structure if it doesn't exist
        if 'messages' not in messages_data:
            messages_data['messages'] = {}
        
        # Check if conversation exists and has messages
        if conversation_key not in messages_data['messages']:
            messages_data['messages'][conversation_key] = []
            # Save the initialized structure
            with open('data/messages.json', 'w') as f:
                json.dump(messages_data, f, indent=4)
            return True  # Return True for new conversations
        
        messages = messages_data['messages'][conversation_key]
        if not messages:
            return True  # Return True for empty conversations
        
        # Mark messages as read
        has_unread = False
        for message in messages:
            if message['sender_id'] != user_id and not message.get('read', False):
                message['read'] = True
                has_unread = True
        
        # Only save if there were unread messages
        if has_unread:
            with open('data/messages.json', 'w') as f:
                json.dump(messages_data, f, indent=4)
        
        return True
    except Exception as e:
        print(f"Error marking messages as read: {str(e)}")
        return True  # Return True even on error to prevent UI issues

@app.route('/messages')
@login_required
def messages():
    user_id = str(session['user_id'])
    print(f"Current user ID: {user_id}")
    
    # Load connections
    connections = load_json('connections.json')
    print(f"All connections: {connections}")
    
    # Get connected users
    connected_users = []
    for conn in connections:
        if conn['status'] == 'connected':
            if str(conn['user_id']) == user_id:
                connected_users.append(str(conn['connected_user_id']))
            elif str(conn['connected_user_id']) == user_id:
                connected_users.append(str(conn['user_id']))
    print(f"Connected users: {connected_users}")
    
    # Load users data
    users = load_json('users.json')
    profiles = load_json('profile.json')
    print(f"All users: {users}")
    
    # Load messages data
    try:
        with open('data/messages.json', 'r') as f:
            messages_data = json.load(f)
    except FileNotFoundError:
        messages_data = {'messages': {}}
    
    # Get conversations
    conversations = []
    for connected_user_id in connected_users:
        user = next((u for u in users if str(u['id']) == connected_user_id), None)
        print(f"Looking for user with ID {connected_user_id}: {user}")
        if user:
            user_profile = next((p for p in profiles['profiles'] if str(p['user_id']) == connected_user_id), None)
            
            # Get conversation messages
            conversation_key = f"{min(user_id, connected_user_id)}_{max(user_id, connected_user_id)}"
            conversation_messages = messages_data.get('messages', {}).get(conversation_key, [])
            
            # Get last message and time
            last_message = 'No messages yet'
            last_message_time = ''
            unread_count = 0
            
            if conversation_messages:
                last_message = conversation_messages[-1]['content']
                last_message_time = conversation_messages[-1]['created_at']
                unread_count = sum(1 for msg in conversation_messages if msg['sender_id'] != user_id and not msg.get('read', False))
            
            conversations.append({
                'id': connected_user_id,
                'participants': [user_id, connected_user_id],
                'name': user['fullname'],
                'profile_picture': user_profile.get('profile_picture', 'default-avatar.png') if user_profile else 'default-avatar.png',
                'online': False,
                'last_message': last_message,
                'last_message_time': last_message_time,
                'unread_count': unread_count
            })
    print(f"Conversations: {conversations}")
    
    # Get active conversation from query parameter
    active_conversation_id = request.args.get('conversation_id')
    active_conversation = None
    messages = []
    
    if active_conversation_id:
        active_conversation = next((conv for conv in conversations if conv['id'] == active_conversation_id), None)
        if active_conversation:
            conversation_key = f"{min(user_id, active_conversation_id)}_{max(user_id, active_conversation_id)}"
            if conversation_key in messages_data.get('messages', {}):
                messages = messages_data['messages'][conversation_key]
                # Mark messages as read when viewing conversation
                mark_messages_as_read(conversation_key, user_id)
    
    # Convert all user IDs to strings for consistent comparison
    users = [{'id': str(u['id']), 'fullname': u['fullname']} for u in users]
    print(f"Processed users: {users}")

    # Load and categorize schedules
    try:
        with open('data/schedules.json', 'r') as f:
            schedules = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        schedules = []

    # Get current date and time
    current_datetime = datetime.now()
    
    # Filter and categorize schedules
    upcoming_schedules = []
    past_schedules = []
    
    for schedule in schedules:
        # Convert schedule date and time to datetime
        schedule_datetime = datetime.strptime(f"{schedule['date']} {schedule['time']}", "%Y-%m-%d %H:%M")
        
        # Get participant name
        participant = next((u for u in users if str(u['id']) == str(schedule['participant_id'])), None)
        participant_name = participant['fullname'] if participant else "Unknown User"
        
        # Create schedule object with participant name
        schedule_obj = {
            'id': schedule['id'],
            'title': schedule['title'],
            'date': schedule['date'],
            'time': schedule['time'],
            'participant': participant_name,
            'status': schedule['status'],
            'approval': schedule['approval'],
            'description': schedule.get('description', '')
        }
        
        # Categorize based on datetime
        if schedule_datetime > current_datetime:
            upcoming_schedules.append(schedule_obj)
        else:
            past_schedules.append(schedule_obj)
    
    # Sort schedules by date and time
    upcoming_schedules.sort(key=lambda x: (x['date'], x['time']))
    past_schedules.sort(key=lambda x: (x['date'], x['time']), reverse=True)
    
    return render_template('messages.html', 
                         conversations=conversations,
                         active_conversation=active_conversation,
                         messages=messages,
                         users=users,
                         active_page='messages',
                         upcoming_schedules=upcoming_schedules,
                         past_schedules=past_schedules)

@app.route('/messages/<conversation_id>')
def conversation(conversation_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    current_user_id = str(session['user_id'])
    
    # Verify connection exists
    with open('connections.json', 'r') as f:
        connections_data = json.load(f)
    
    is_connected = False
    for conn in connections_data.get('connections', []):
        if conn['status'] == 'connected':
            if (conn['sender_id'] == current_user_id and conn['receiver_id'] == conversation_id) or \
               (conn['sender_id'] == conversation_id and conn['receiver_id'] == current_user_id):
                is_connected = True
                break
    
    if not is_connected:
        return redirect(url_for('messages'))
    
    # Load users data
    with open('users.json', 'r') as f:
        users_data = json.load(f)
    
    # Get conversation partner
    conversation_partner = next((u for u in users_data['users'] if str(u['id']) == conversation_id), None)
    if not conversation_partner:
        return redirect(url_for('messages'))
    
    # Load messages
    messages = []
    try:
        with open('messages.json', 'r') as f:
            messages_data = json.load(f)
            conversation_messages = messages_data.get('messages', {}).get(f"{current_user_id}_{conversation_id}", [])
            messages = sorted(conversation_messages, key=lambda x: x['timestamp'])
    except FileNotFoundError:
        pass
    
    return render_template('messages.html',
                         conversations=[],  # This would be populated in a real app
                         active_conversation={
                             'id': conversation_id,
                             'name': conversation_partner['name'],
                             'profile_picture': conversation_partner.get('profile_picture'),
                             'online': False  # This would be handled with WebSocket in a real app
                         },
                         messages=messages,
                         active_page='messages')

def save_message(sender_id, receiver_id, content):
    """Save a message to the messages.json file"""
    try:
        # Load existing messages
        try:
            with open('data/messages.json', 'r') as f:
                messages_data = json.load(f)
        except FileNotFoundError:
            messages_data = {'messages': {}}
        
        # Create conversation key (always use smaller ID first)
        conversation_key = f"{min(sender_id, receiver_id)}_{max(sender_id, receiver_id)}"
        
        # Initialize conversation messages if not exists
        if conversation_key not in messages_data['messages']:
            messages_data['messages'][conversation_key] = []
        
        # Create new message
        new_message = {
            'id': str(len(messages_data['messages'][conversation_key]) + 1),
            'sender_id': sender_id,
            'content': content,
            'created_at': datetime.utcnow().isoformat(),
            'read': False
        }
        
        # Add message to conversation
        messages_data['messages'][conversation_key].append(new_message)
        
        # Save updated messages
        with open('data/messages.json', 'w') as f:
            json.dump(messages_data, f, indent=4)
        
        return True, new_message
    except Exception as e:
        print(f"Error saving message: {str(e)}")
        return False, str(e)

# Add this at the top with other global variables
message_queues = {}

@app.route('/api/messages/stream')
@login_required
def stream_messages():
    user_id = str(session['user_id'])
    
    def event_stream():
        # Create a queue for this user if it doesn't exist
        if user_id not in message_queues:
            message_queues[user_id] = queue.Queue()
        
        while True:
            try:
                # Get message from queue (non-blocking)
                message = message_queues[user_id].get_nowait()
                yield f"data: {json.dumps(message)}\n\n"
            except queue.Empty:
                # No message available, yield empty to keep connection alive
                yield "data: {}\n\n"
    
    return Response(event_stream(), mimetype='text/event-stream')

def notify_new_message(message, conversation_key):
    """Notify all participants in a conversation about a new message"""
    user_ids = conversation_key.split('_')
    for user_id in user_ids:
        if user_id in message_queues:
            message_queues[user_id].put(message)

@app.route('/api/messages/send', methods=['POST'])
@login_required
def send_message():
    try:
        data = request.get_json()
        sender_id = str(session['user_id'])
        receiver_id = data.get('conversation_id')
        content = data.get('content')
        
        if not receiver_id or not content:
            return jsonify({'success': False, 'error': 'Missing required fields'})
        
        success, result = save_message(sender_id, receiver_id, content)
        
        if success:
            # Notify participants about the new message
            conversation_key = f"{min(sender_id, receiver_id)}_{max(sender_id, receiver_id)}"
            notify_new_message(result, conversation_key)
            
            return jsonify({
                'success': True,
                'message': result
            })
        else:
            return jsonify({
                'success': False,
                'error': result
            })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })

@app.route('/api/messages/unread-count')
def get_unread_count():
    if 'user_id' not in session:
        return jsonify({'count': 0})
    
    current_user_id = str(session['user_id'])
    
    # Load messages
    try:
        with open('data/messages.json', 'r') as f:
            messages_data = json.load(f)
    except FileNotFoundError:
        return jsonify({'count': 0})
    
    # Count unread messages
    count = 0
    for conversation_key, messages in messages_data.get('messages', {}).items():
        user_id = conversation_key.split('_')[1]  # Get the other user's ID
        for message in messages:
            if message['sender_id'] != current_user_id and not message.get('read', False):
                count += 1
    
    return jsonify({'count': count})

@app.route('/api/messages/mark-read', methods=['POST'])
@login_required
def mark_conversation_read():
    """Mark all messages in a conversation as read"""
    try:
        data = request.get_json()
        conversation_id = data.get('conversation_id')
        user_id = str(session['user_id'])
        
        if not conversation_id:
            return jsonify({'success': False, 'error': 'Conversation ID is required'})
        
        conversation_key = f"{min(user_id, conversation_id)}_{max(user_id, conversation_id)}"
        success = mark_messages_as_read(conversation_key, user_id)
        
        if success:
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Failed to mark messages as read'})
    except Exception as e:
        print(f"Error marking conversation as read: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

# Add datetime filter
@app.template_filter('datetime')
def format_datetime(value):
    if value is None:
        return ""
    try:
        # Parse the ISO format string
        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
        # Format the datetime
        return dt.strftime("%b %d, %Y %I:%M %p")
    except (ValueError, AttributeError):
        return value

@app.route('/api/schedules', methods=['GET', 'POST'])
@login_required
def handle_schedules():
    if request.method == 'POST':
        data = request.get_json()
        required_fields = ['title', 'date', 'time', 'participant_id']
        
        # Validate required fields
        if not all(field in data for field in required_fields):
            return jsonify({'success': False, 'error': 'Missing required fields'})
        
        # Create new schedule
        new_schedule = {
            'id': str(uuid.uuid4()),
            'title': data['title'],
            'date': data['date'],
            'time': data['time'],
            'participant_id': str(data['participant_id']),  # Convert to string
            'creator_id': str(session.get('user_id')),  # Convert to string
            'status': 'scheduled',  # Initial status for tracking progress
            'approval': 'pending',  # Approval status for request
            'description': data.get('description', ''),
            'created_at': datetime.now().isoformat()
        }
        
        # Load existing schedules
        try:
            with open('data/schedules.json', 'r') as f:
                schedules = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            schedules = []
        
        # Append new schedule
        schedules.append(new_schedule)
        
        # Save updated schedules
        with open('data/schedules.json', 'w') as f:
            json.dump(schedules, f, indent=4)
        
        # Send request message to participant
        message_content = f"Schedule request: {new_schedule['title']} on {new_schedule['date']} at {new_schedule['time']}"
        success, message = save_message(
            str(session.get('user_id')),
            str(data['participant_id']),
            message_content
        )
        
        if success:
            # Add schedule information to the message
            message['type'] = 'schedule_request'
            message['schedule_id'] = new_schedule['id']
            
            # Update the message in the messages file
            conversation_key = f"{min(str(session.get('user_id')), str(data['participant_id']))}_{max(str(session.get('user_id')), str(data['participant_id']))}"
            with open('data/messages.json', 'r') as f:
                messages_data = json.load(f)
            messages_data['messages'][conversation_key][-1] = message
            with open('data/messages.json', 'w') as f:
                json.dump(messages_data, f, indent=4)
        
        return jsonify({'success': True, 'schedule': new_schedule})
    
    # GET request - return user's schedules
    try:
        with open('data/schedules.json', 'r') as f:
            schedules = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        schedules = []
    
    user_schedules = [
        schedule for schedule in schedules 
        if str(schedule['creator_id']) == str(session.get('user_id')) or 
           str(schedule['participant_id']) == str(session.get('user_id'))
    ]
    return jsonify({'success': True, 'schedules': user_schedules})

@app.route('/api/schedules/<schedule_id>/respond', methods=['POST'])
@login_required
def respond_to_schedule(schedule_id):
    try:
        data = request.get_json()
        print(f"Received schedule response request: {data}")
        
        if not data or 'response' not in data:
            return jsonify({'success': False, 'error': 'Invalid request'})
        
        response = data['response']
        if response not in ['accept', 'deny']:
            return jsonify({'success': False, 'error': 'Invalid response'})
        
        # Load schedules
        try:
            with open('data/schedules.json', 'r') as f:
                schedules = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return jsonify({'success': False, 'error': 'No schedules found'})
        
        print(f"Looking for schedule with ID: {schedule_id}")
        print(f"Available schedules: {schedules}")
        
        # Find the schedule
        schedule = next((s for s in schedules if str(s['id']) == str(schedule_id)), None)
        
        if not schedule:
            print(f"Schedule not found with ID: {schedule_id}")
            return jsonify({'success': False, 'error': 'Schedule not found'})
        
        print(f"Found schedule: {schedule}")
        
        # Check if user is the participant
        current_user_id = str(session.get('user_id'))
        if str(schedule['participant_id']) != current_user_id:
            print(f"Unauthorized: Current user {current_user_id} is not the participant {schedule['participant_id']}")
            return jsonify({'success': False, 'error': 'Unauthorized'})
        
        # Update schedule approval only, keep status unchanged
        schedule['approval'] = 'accepted' if response == 'accept' else 'denied'
        
        # Save updated schedule
        with open('data/schedules.json', 'w') as f:
            json.dump(schedules, f, indent=4)
        print(f"Updated schedule approval to: {schedule['approval']}")
        
        # Send response message to creator
        response_message = f"Schedule {response}ed: {schedule['title']}"
        success, message = save_message(
            current_user_id,
            str(schedule['creator_id']),
            response_message
        )
        
        if success:
            print(f"Successfully saved response message: {message}")
            # Add schedule information to the message
            message['type'] = 'schedule_response'
            message['schedule_id'] = schedule_id
            
            # Update the message in the messages file
            conversation_key = f"{min(current_user_id, str(schedule['creator_id']))}_{max(current_user_id, str(schedule['creator_id']))}"
            with open('data/messages.json', 'r') as f:
                messages_data = json.load(f)
            
            # Remove the schedule request message
            if conversation_key in messages_data['messages']:
                messages_data['messages'][conversation_key] = [
                    msg for msg in messages_data['messages'][conversation_key]
                    if not (msg.get('type') == 'schedule_request' and msg.get('schedule_id') == schedule_id)
                ]
            
            # Add the response message
            messages_data['messages'][conversation_key].append(message)
            
            with open('data/messages.json', 'w') as f:
                json.dump(messages_data, f, indent=4)
            print(f"Updated message in conversation: {conversation_key}")
        
        return jsonify({'success': True, 'schedule': schedule})
    except Exception as e:
        print(f"Error in respond_to_schedule: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/profile/<user_id>')
@login_required
def view_user_profile(user_id):
    try:
        print(f"Accessing profile for user_id: {user_id}")  # Debug log
        
        # Load all necessary data
        users = load_json('users.json')
        profiles = load_json('profile.json')
        skills_data = load_json('skills.json')
        connections = load_json('connections.json')
        
        print(f"Loaded data files successfully")  # Debug log
        
        # Find user
        user = next((u for u in users if str(u['id']) == str(user_id)), None)
        if not user:
            print(f"User not found with id: {user_id}")  # Debug log
            flash('User not found', 'error')
            return redirect(url_for('search'))
        
        print(f"Found user: {user}")  # Debug log
        
        # Find profile
        profile = next((p for p in profiles['profiles'] if str(p['user_id']) == str(user_id)), None)
        if not profile:
            print(f"Profile not found, creating default profile")  # Debug log
            profile = {
                'user_id': user_id,
                'profile_picture': 'default-avatar.png',
                'about': '',
                'location': '',
                'interests': []
            }
        
        print(f"Using profile: {profile}")  # Debug log
        
        # Get user's skills
        skills = skills_data.get('user_skills', {}).get(str(user_id), [])
        print(f"Found skills: {skills}")  # Debug log
        
        # Check if connected
        current_user_id = str(session['user_id'])
        is_connected = any(
            (str(c['user_id']) == current_user_id and str(c['connected_user_id']) == str(user_id) and c['status'] == 'connected') or
            (str(c['user_id']) == str(user_id) and str(c['connected_user_id']) == current_user_id and c['status'] == 'connected')
            for c in connections
        )
        
        # Check if there's a pending connection request
        pending_request = any(
            (str(c['user_id']) == current_user_id and str(c['connected_user_id']) == str(user_id) and c['status'] == 'pending') or
            (str(c['user_id']) == str(user_id) and str(c['connected_user_id']) == current_user_id and c['status'] == 'pending')
            for c in connections
        )
        
        print(f"Connection status - is_connected: {is_connected}, pending_request: {pending_request}")  # Debug log
        
        return render_template('view_profile.html',
                             user=user,
                             profile=profile,
                             skills=skills,
                             is_connected=is_connected,
                             pending_request=pending_request,
                             current_user_id=current_user_id)
                             
    except Exception as e:
        print(f"Error in view_user_profile: {str(e)}")  # Debug log
        flash('Error loading profile', 'error')
        return redirect(url_for('search'))

@app.route('/api/connections/disconnect/<user_id>', methods=['POST'])
@login_required
def disconnect_user(user_id):
    """Disconnect from a user"""
    try:
        connections = load_json('connections.json')
        current_user_id = str(session['user_id'])
        target_user_id = str(user_id)

        # Find the connection between these users
        connection = next(
            (conn for conn in connections 
             if ((str(conn['user_id']) == current_user_id and str(conn['connected_user_id']) == target_user_id) or
                 (str(conn['user_id']) == target_user_id and str(conn['connected_user_id']) == current_user_id))
             and conn['status'] == 'connected'),
            None
        )

        if not connection:
            return jsonify({'success': False, 'message': 'Connection not found'}), 404

        # Remove the connection
        connections = [conn for conn in connections if str(conn['id']) != str(connection['id'])]
        save_json(connections, 'connections.json')

        return jsonify({'success': True, 'message': 'Successfully disconnected'})
    except Exception as e:
        print(f"Error in disconnect_user: {str(e)}")
        return jsonify({'success': False, 'message': 'Internal server error'}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True, port=5001)