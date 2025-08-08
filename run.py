from app import create_app
from app.orpheus_handler import initialize_modules
from dotenv import load_dotenv

load_dotenv()

app = create_app()

with app.app_context():
    initialize_modules()

if __name__ == '__main__':
    # For local development only
    app.run(host='0.0.0.0', port=5000, debug=False)