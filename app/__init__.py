from flask import Flask
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
import os
import redis
import logging
import structlog

db = SQLAlchemy()

def create_app():

    app = Flask(__name__, static_folder='static', template_folder='templates')
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', os.urandom(24))
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///flaccy.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    CORS(app)

    # Artifacts and proxy configuration
    artifacts_dir = os.environ.get('ARTIFACTS_DIR') or os.path.join(app.instance_path, 'artifacts')
    os.makedirs(artifacts_dir, exist_ok=True)
    app.config['ARTIFACTS_DIR'] = artifacts_dir
    app.config['X_ACCEL_REDIRECT_PREFIX'] = os.environ.get('X_ACCEL_REDIRECT_PREFIX')
    # Optional owner for artifacts (set via env to control file ownership, e.g. 1000)
    owner_uid = os.environ.get('ARTIFACTS_OWNER_UID')
    owner_gid = os.environ.get('ARTIFACTS_OWNER_GID')
    app.config['ARTIFACTS_OWNER_UID'] = int(owner_uid) if owner_uid is not None else None
    app.config['ARTIFACTS_OWNER_GID'] = int(owner_gid) if owner_gid is not None else None

    # Configure logging
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    app.logger = structlog.get_logger()

    # If an artifacts owner was requested, attempt to set ownership on the artifacts directory.
    try:
        if app.config.get('ARTIFACTS_OWNER_UID') is not None and app.config.get('ARTIFACTS_OWNER_GID') is not None:
            os.chown(app.config['ARTIFACTS_DIR'], int(app.config['ARTIFACTS_OWNER_UID']), int(app.config['ARTIFACTS_OWNER_GID']))
    except Exception:
        # Logging is configured so use app.logger to surface issues, but don't fail startup
        try:
            app.logger.exception("Failed to chown artifacts directory", path=app.config.get('ARTIFACTS_DIR'))
        except Exception:
            pass

    db.init_app(app)

    app.redis = redis.from_url(os.environ.get('REDIS_URL', 'redis://localhost:6379/0'))
    from . import events
    events.initialize(app.redis)

    # Ensure the instance folder exists
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    with app.app_context():
        # Import parts of our application
        from . import routes
        from . import models
        
        db.create_all()

        # Register Blueprints
        app.register_blueprint(routes.main_bp)

    return app
