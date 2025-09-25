import os
from app import create_app

# Create Flask application instance
app = create_app(os.environ.get('FLASK_CONFIG', 'default'))

if __name__ == '__main__':
    app.run(debug=True, port=5000)