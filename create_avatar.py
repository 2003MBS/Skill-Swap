from PIL import Image, ImageDraw
import os

def create_default_avatar():
    # Create a new image with a white background
    size = (200, 200)
    image = Image.new('RGB', size, '#f0f0f0')
    draw = ImageDraw.Draw(image)
    
    # Draw a circle for the head
    circle_color = '#007bff'
    circle_bbox = (50, 30, 150, 130)
    draw.ellipse(circle_bbox, fill=circle_color)
    
    # Draw a larger circle for the body
    body_color = '#007bff'
    body_bbox = (40, 120, 160, 220)
    draw.ellipse(body_bbox, fill=body_color)
    
    # Ensure the directory exists
    os.makedirs('static/images', exist_ok=True)
    
    # Save the image
    image.save('static/images/default-avatar.png', 'PNG')

if __name__ == '__main__':
    create_default_avatar() 