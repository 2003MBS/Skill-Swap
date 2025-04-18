 
# SkillSwap

SkillSwap is a platform where users can connect with skilled professionals, share knowledge, and learn new skills through direct interactions.

## Features
- Direct connections with skilled professionals
- Real-time chat functionality
- Verified skill profiles
- Flexible learning schedule

## Tech Stack
- Frontend: HTML, CSS, JavaScript
- Backend: Flask (Python)
- Database: JSON files

## Setup Instructions

1. Create a virtual environment:
```bash
python -m venv venv
```

2. Activate the virtual environment:
- On Windows:
```bash
venv\Scripts\activate
```
- On macOS/Linux:
```bash
source venv/bin/activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Run the application:
```bash
python app.py
```

5. Open your browser and navigate to:
```
http://localhost:5000
```

## Project Structure
```
SkillSwap/
├── app.py              # Main Flask application
├── requirements.txt    # Python dependencies
├── static/            # Static files
│   ├── css/          # CSS files
│   └── js/           # JavaScript files
├── templates/         # HTML templates
│   └── index.html    # Main landing page
└── data/             # JSON data storage
```

## Contributing
Feel free to submit issues and enhancement requests.