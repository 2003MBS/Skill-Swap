from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from functools import wraps
import json
import os
from datetime import datetime

admin_bp = Blueprint('admin_bp', __name__)

# Admin credentials (in a real app, these would be stored securely)
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_id' not in session:
            flash('Please login as admin to access this page', 'error')
            return redirect(url_for('admin_bp.admin_login'))
        return f(*args, **kwargs)
    return decorated_function

def load_json(filename):
    try:
        with open(f'data/{filename}', 'r') as f:
            return json.load(f)
    except:
        return [] if filename != 'skills.json' else {}

def save_json(data, filename):
    with open(f'data/{filename}', 'w') as f:
        json.dump(data, f, indent=4)

@admin_bp.route('/admlogin', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if username == 'admin' and password == 'admin123':
            session['admin_id'] = 1
            flash('Successfully logged in as admin!', 'success')
            return redirect(url_for('admin_bp.admin_dashboard'))
        else:
            flash('Invalid admin credentials', 'error')
    
    return render_template('admin_login.html')

@admin_bp.route('/admin_dashboard')
@admin_required
def admin_dashboard():
    users = load_json('users.json')
    profiles = load_json('profile.json')
    skills_data = load_json('skills.json')
    
    # Get all user skills
    all_user_skills = []
    for user_id, user_skills in skills_data.get('user_skills', {}).items():
        user = next((u for u in users if str(u['id']) == str(user_id)), None)
        if user:
            for skill in user_skills:
                all_user_skills.append({
                    'user_id': user_id,
                    'user_name': user['fullname'],
                    'skill_id': skill['skill_id'],
                    'skill_name': skill['skill_name'],
                    'description': skill['description'],
                    'qualification': skill['qualification'],
                    'years_of_experience': skill['years_of_experience'],
                    'status': skill.get('status', 'pending')  # Default to pending if not set
                })
    
    return render_template('admin_dashboard.html', 
                         users=users,
                         profiles=profiles,
                         all_user_skills=all_user_skills)

@admin_bp.route('/users/toggle/<int:user_id>', methods=['POST'])
@admin_required
def toggle_user_status(user_id):
    users = load_json('users.json')
    user = next((u for u in users if u['id'] == user_id), None)
    
    if user:
        user['is_active'] = not user.get('is_active', True)
        save_json(users, 'users.json')
        status = 'activated' if user['is_active'] else 'deactivated'
        flash(f'User {status} successfully!', 'success')
    else:
        flash('User not found!', 'error')
    
    return redirect(url_for('admin_bp.admin_dashboard'))

@admin_bp.route('/users/delete/<int:user_id>', methods=['POST'])
@admin_required
def delete_user(user_id):
    users = load_json('users.json')
    profiles = load_json('profile.json')
    skills_data = load_json('skills.json')
    
    # Remove user from users list
    users = [u for u in users if u['id'] != user_id]
    save_json(users, 'users.json')
    
    # Remove user's profile
    if 'profiles' in profiles:
        profiles['profiles'] = [p for p in profiles['profiles'] if p['user_id'] != user_id]
        save_json(profiles, 'profile.json')
    
    # Remove user's skills
    if 'user_skills' in skills_data and str(user_id) in skills_data['user_skills']:
        del skills_data['user_skills'][str(user_id)]
        save_json(skills_data, 'skills.json')
    
    flash('User deleted successfully!', 'success')
    return redirect(url_for('admin_bp.admin_dashboard'))

@admin_bp.route('/skills/accept/<user_id>/<skill_id>', methods=['POST'])
@admin_required
def accept_skill(user_id, skill_id):
    skills_data = load_json('skills.json')
    
    if 'user_skills' in skills_data and user_id in skills_data['user_skills']:
        for skill in skills_data['user_skills'][user_id]:
            if skill['skill_id'] == skill_id:
                skill['status'] = 'accepted'
                save_json(skills_data, 'skills.json')
                flash('Skill accepted successfully!', 'success')
                break
    
    return redirect(url_for('admin_bp.admin_dashboard'))

@admin_bp.route('/skills/reject/<user_id>/<skill_id>', methods=['POST'])
@admin_required
def reject_skill(user_id, skill_id):
    skills_data = load_json('skills.json')
    
    if 'user_skills' in skills_data and user_id in skills_data['user_skills']:
        skills_data['user_skills'][user_id] = [
            skill for skill in skills_data['user_skills'][user_id]
            if skill['skill_id'] != skill_id
        ]
        save_json(skills_data, 'skills.json')
        flash('Skill rejected successfully!', 'success')
    
    return redirect(url_for('admin_bp.admin_dashboard'))

@admin_bp.route('/admin_logout')
def admin_logout():
    session.pop('admin_id', None)
    flash('Successfully logged out from admin panel', 'success')
    return redirect(url_for('admin_bp.admin_login')) 