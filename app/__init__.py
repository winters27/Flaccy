from flask import Flask
from flask_cors import CORS
import os

def create_app():
    app = Flask(__name__, static_folder='static', template_folder='templates')
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', os.urandom(24))
    CORS(app)

    # Ensure the instance folder exists
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    with app.app_context():
        # Import parts of our application
        from . import routes
        
        # Register Blueprints
        app.register_blueprint(routes.main_bp)

    return app
