from flask import Flask
from config import Config
from models import db


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)

    from routes.main import main_bp
    from routes.auth import auth_bp
    from routes.employees import employees_bp
    from routes.schedules import schedules_bp
    from routes.settings import settings_bp
    from routes.feedbacks import feedbacks_bp
    from routes.admin import admin_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(employees_bp)
    app.register_blueprint(schedules_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(feedbacks_bp)
    app.register_blueprint(admin_bp)

    return app


if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)