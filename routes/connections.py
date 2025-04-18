from flask import Blueprint, jsonify, request, current_app
import json
import os
from datetime import datetime
from auth import login_required

connections_bp = Blueprint('connections', __name__)

def load_connections():
    """Load connections from JSON file"""
    connections_file = os.path.join(current_app.root_path, 'data', 'connections.json')
    if os.path.exists(connections_file):
        with open(connections_file, 'r') as f:
            return json.load(f)
    return []

def save_connections(connections):
    """Save connections to JSON file"""
    connections_file = os.path.join(current_app.root_path, 'data', 'connections.json')
    with open(connections_file, 'w') as f:
        json.dump(connections, f, indent=4)

@connections_bp.route('/api/connections', methods=['GET'])
@login_required
def get_connections():
    """Get all connections for the current user"""
    connections = load_connections()
    current_user_id = request.user.id

    # Filter connections for current user
    pending_connections = []
    connected_users = []

    for conn in connections:
        if conn['user_id'] == current_user_id:
            if conn['status'] == 'pending':
                pending_connections.append(conn)
            elif conn['status'] == 'connected':
                connected_users.append(conn)
        elif conn['connected_user_id'] == current_user_id:
            if conn['status'] == 'pending':
                pending_connections.append(conn)
            elif conn['status'] == 'connected':
                connected_users.append(conn)

    return jsonify({
        'pending_connections': pending_connections,
        'connected_users': connected_users
    })

@connections_bp.route('/api/connections/accept/<connection_id>', methods=['POST'])
@login_required
def accept_connection(connection_id):
    """Accept a connection request"""
    connections = load_connections()
    current_user_id = request.user.id

    # Find the connection
    connection = next((conn for conn in connections if conn['id'] == connection_id), None)
    
    if not connection:
        return jsonify({'success': False, 'message': 'Connection not found'}), 404

    # Verify the current user is the recipient
    if connection['connected_user_id'] != current_user_id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    # Update connection status
    connection['status'] = 'connected'
    connection['accepted_at'] = datetime.now().isoformat()

    # Save updated connections
    save_connections(connections)

    return jsonify({'success': True, 'message': 'Connection accepted'})

@connections_bp.route('/api/connections/reject/<connection_id>', methods=['POST'])
@login_required
def reject_connection(connection_id):
    """Reject a connection request"""
    connections = load_connections()
    current_user_id = request.user.id

    # Find the connection
    connection = next((conn for conn in connections if conn['id'] == connection_id), None)
    
    if not connection:
        return jsonify({'success': False, 'message': 'Connection not found'}), 404

    # Verify the current user is the recipient
    if connection['connected_user_id'] != current_user_id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    # Remove the connection
    connections = [conn for conn in connections if conn['id'] != connection_id]
    save_connections(connections)

    return jsonify({'success': True, 'message': 'Connection rejected'})

@connections_bp.route('/api/connections/request', methods=['POST'])
@login_required
def request_connection():
    """Send a connection request"""
    data = request.get_json()
    target_user_id = data.get('user_id')
    
    if not target_user_id:
        return jsonify({'success': False, 'message': 'Target user ID is required'}), 400

    connections = load_connections()
    current_user_id = request.user.id

    # Check if connection already exists
    existing_connection = next(
        (conn for conn in connections 
         if (conn['user_id'] == current_user_id and conn['connected_user_id'] == target_user_id) or
         (conn['user_id'] == target_user_id and conn['connected_user_id'] == current_user_id)),
        None
    )

    if existing_connection:
        return jsonify({'success': False, 'message': 'Connection already exists'}), 400

    # Create new connection request
    new_connection = {
        'id': str(len(connections) + 1),
        'user_id': current_user_id,
        'connected_user_id': target_user_id,
        'status': 'pending',
        'created_at': datetime.now().isoformat()
    }

    connections.append(new_connection)
    save_connections(connections)

    return jsonify({'success': True, 'message': 'Connection request sent'}) 