#!/usr/bin/env python3
"""
MTProxy Manager - Точка входа приложения
"""

import os
import sys

# Добавляем текущую директорию в путь
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app

# Создаём приложение
app = create_app(os.environ.get('FLASK_CONFIG', 'default'))

if __name__ == '__main__':
    # Параметры запуска
    host = os.environ.get('FLASK_HOST', '127.0.0.1')
    port = int(os.environ.get('FLASK_PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'false').lower() in ('true', '1', 'yes')
    
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║                    MTProxy Manager                           ║
║                                                              ║
║  Запуск сервера: http://{host}:{port:<5}                        ║
║  Режим отладки: {'Включён' if debug else 'Выключен':<10}                              ║
║                                                              ║
║  Для production используйте:                                 ║
║  gunicorn -w 4 -b 0.0.0.0:5000 run:app                      ║
╚══════════════════════════════════════════════════════════════╝
    """)
    
    app.run(host=host, port=port, debug=debug)