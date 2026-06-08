import os


class Config:
    # --- Sécurité ---
    SECRET_KEY = os.environ.get('SECRET_KEY', 'change-moi-en-prod')

    # --- Base de données ---
    DB_USER     = os.environ.get('DB_USER', 'pizzeria')
    DB_PASSWORD = os.environ.get('DB_PASSWORD', 'ton_mot_de_passe')
    DB_HOST     = os.environ.get('DB_HOST', 'db')       # nom du service Docker
    DB_PORT     = os.environ.get('DB_PORT', '3306')
    DB_NAME     = os.environ.get('DB_NAME', 'pizzeria_db')

    SQLALCHEMY_DATABASE_URI = (
        f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}"
        f"@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # --- Session ---
    SESSION_COOKIE_HTTPONLY  = True
    SESSION_COOKIE_SAMESITE  = 'Lax'
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 24 * 7  # 7 jours en secondes
