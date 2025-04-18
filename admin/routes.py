@admin_bp.route('/logout')
def admin_logout():
    # Clear the session
    session.clear()
    # Redirect to admin login page
    return redirect(url_for('admin_bp.admin_login')) 