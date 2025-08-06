from gevent import monkey
monkey.patch_all()

from app import create_app
from app.orpheus_handler import initialize_modules
from gevent.pywsgi import WSGIServer
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Create the Flask app
app = create_app()

# Initialize OrpheusDL modules within the app context
with app.app_context():
    initialize_modules()

if __name__ == '__main__':
    print("Starting server on http://0.0.0.0:5000")
    http_server = WSGIServer(('0.0.0.0', 5000), app)
    http_server.serve_forever()
