// Common dashboard functionality
document.addEventListener('DOMContentLoaded', function() {
    // Initialize any dashboard-wide functionality here
    console.log('Dashboard initialized');
}); 

// Function to send a connection request to another user
async function connectWithUser(userId) {
    try {
        const response = await fetch('/api/connections/request', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ user_id: userId })
        });

        const data = await response.json();

        if (response.ok) {
            // Show success message
            alert('Connection request sent successfully!');
            // Update the button state
            const button = document.querySelector(`[data-user-id="${userId}"]`);
            if (button) {
                button.disabled = true;
                button.innerHTML = '<i class="fas fa-check"></i> Request Sent';
            }
        } else {
            // Show error message
            alert(data.message || 'Failed to send connection request');
        }
    } catch (error) {
        console.error('Error sending connection request:', error);
        alert('Failed to send connection request. Please try again.');
    }
}

// Function to view user details
async function viewUserDetails(userId) {
    try {
        const response = await fetch(`/api/users/${userId}`);
        const data = await response.json();

        if (response.ok) {
            // Update modal content
            document.getElementById('userDetailsImage').src = data.profile_picture || '/static/images/default-avatar.png';
            document.getElementById('userDetailsName').textContent = data.name;
            document.getElementById('userDetailsEmail').textContent = data.email;
            document.getElementById('userDetailsLocation').textContent = data.location || 'Location not specified';
            
            // Update skills
            const skillsContainer = document.getElementById('userDetailsSkills');
            skillsContainer.innerHTML = data.skills.map(skill => `
                <div class="skill-tag">
                    <span class="skill-name">${skill.name}</span>
                    <span class="qualification-badge ${skill.qualification.toLowerCase()}">${skill.qualification}</span>
                </div>
            `).join('');

            // Show the modal
            document.getElementById('userDetailsModal').style.display = 'block';
        } else {
            alert(data.message || 'Failed to load user details');
        }
    } catch (error) {
        console.error('Error loading user details:', error);
        alert('Failed to load user details. Please try again.');
    }
}

// Close modal when clicking the close button
document.querySelector('.close-modal').addEventListener('click', function() {
    document.getElementById('userDetailsModal').style.display = 'none';
});

// Close modal when clicking outside
window.addEventListener('click', function(event) {
    const modal = document.getElementById('userDetailsModal');
    if (event.target === modal) {
        modal.style.display = 'none';
    }
}); 