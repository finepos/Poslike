# app/initialization.py
from .extensions import db
from .models import ColorSetting

def init_app_data(app):
    """Створює таблиці та початкові налаштування, якщо їх немає."""
    with app.app_context():
        db.create_all()
        if ColorSetting.query.count() == 0:
            colors = [
                {'level_name': 'status-level-5', 'background_color': '#c0f5b0', 'text_color': '#000000', 'label': '100% - 81%'},
                {'level_name': 'status-level-4', 'background_color': '#ecf5b0', 'text_color': '#000000', 'label': '80% - 61%'},
                {'level_name': 'status-level-3', 'background_color': '#f5e3b0', 'text_color': '#000000', 'label': '60% - 41%'},
                {'level_name': 'status-level-2', 'background_color': '#f5cfb0', 'text_color': '#000000', 'label': '40% - 21%'},
                {'level_name': 'status-level-1', 'background_color': '#f5b9b0', 'text_color': '#000000', 'label': '20% - 0%'},
                {'level_name': 'status-critical', 'background_color': '#f5b9b0', 'text_color': '#ffffff', 'label': 'Нижче мінімуму'}
            ]
            for color_data in colors:
                db.session.add(ColorSetting(**color_data))
            db.session.commit()
            print("Створено стандартні налаштування кольорів.")