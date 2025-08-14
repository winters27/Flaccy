import sys
import os

# Add the vendor directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'vendor')))

from app import create_app
from app.orpheus_handler import initialize_modules
from dotenv import load_dotenv
import os

load_dotenv()
# Ensure USE_X_ACCEL_REDIRECT is not set to 'true' in a local dev environment
os.environ['USE_X_ACCEL_REDIRECT'] = 'false'

app = create_app()

with app.app_context():
    initialize_modules()

if __name__ == '__main__':
    # For local development only
    app.run(host='0.0.0.0', port=5000, debug=False)
