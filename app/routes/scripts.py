"""
Маршруты выполнения скриптов (только для администратора)
"""

import os
import subprocess
import threading
from datetime import datetime
from functools import wraps
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, current_app
from flask_login import login_required, current_user

scripts_bp = Blueprint('scripts', __name__)

# Хранилище результатов выполнения (в памяти)
script_results = {}


def admin_required(f):
    """Декоратор для проверки прав администратора"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Необходимо войти в систему', 'warning')
            return redirect(url_for('auth.login'))
        if not current_user.is_admin:
            flash('Доступ запрещён', 'danger')
            return redirect(url_for('keys.list_keys'))
        return f(*args, **kwargs)
    return decorated_function


def get_scripts_dir():
    """Получение директории скриптов"""
    return current_app.config.get('SCRIPTS_PATH', 'scripts')


def get_available_scripts():
    """Получение списка доступных скриптов"""
    scripts_dir = get_scripts_dir()
    scripts = []
    
    if not os.path.exists(scripts_dir):
        os.makedirs(scripts_dir, exist_ok=True)
        return scripts
    
    for filename in os.listdir(scripts_dir):
        filepath = os.path.join(scripts_dir, filename)
        
        # Пропускаем не-файлы и README
        if not os.path.isfile(filepath):
            continue
        if filename.startswith('.'):
            continue
        if filename.lower() == 'readme.md':
            continue
        
        # Проверяем расширение
        allowed_extensions = ['.sh', '.py', '.bash']
        ext = os.path.splitext(filename)[1].lower()
        if ext not in allowed_extensions:
            continue
        
        # Получаем информацию о файле
        stat = os.stat(filepath)
        is_executable = os.access(filepath, os.X_OK)
        
        # Читаем описание из первой строки комментария
        description = ''
        try:
            with open(filepath, 'r') as f:
                first_lines = f.readlines()[:5]
                for line in first_lines:
                    line = line.strip()
                    if line.startswith('#') and not line.startswith('#!'):
                        description = line.lstrip('#').strip()
                        break
        except Exception:
            pass
        
        scripts.append({
            'name': filename,
            'path': filepath,
            'size': stat.st_size,
            'modified': datetime.fromtimestamp(stat.st_mtime),
            'executable': is_executable,
            'extension': ext,
            'description': description
        })
    
    return sorted(scripts, key=lambda x: x['name'])


def is_safe_script_name(name):
    """Проверка безопасности имени скрипта"""
    # Запрещаем path traversal
    if '..' in name or '/' in name or '\\' in name:
        return False
    
    # Разрешаем только определённые символы
    import re
    if not re.match(r'^[a-zA-Z0-9_\-\.]+$', name):
        return False
    
    return True


def run_script_async(script_path, script_id, app):
    """Асинхронное выполнение скрипта"""
    with app.app_context():
        try:
            script_results[script_id]['status'] = 'running'
            script_results[script_id]['started_at'] = datetime.utcnow().isoformat()
            
            # Определяем интерпретатор
            ext = os.path.splitext(script_path)[1].lower()
            if ext == '.py':
                cmd = ['python3', script_path]
            elif ext in ['.sh', '.bash']:
                cmd = ['bash', script_path]
            else:
                cmd = [script_path]
            
            # Выполняем скрипт
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,  # 5 минут таймаут
                cwd=os.path.dirname(script_path)
            )
            
            script_results[script_id]['status'] = 'completed'
            script_results[script_id]['exit_code'] = result.returncode
            script_results[script_id]['stdout'] = result.stdout
            script_results[script_id]['stderr'] = result.stderr
            script_results[script_id]['finished_at'] = datetime.utcnow().isoformat()
            
        except subprocess.TimeoutExpired:
            script_results[script_id]['status'] = 'timeout'
            script_results[script_id]['error'] = 'Превышено время выполнения (5 минут)'
            script_results[script_id]['finished_at'] = datetime.utcnow().isoformat()
            
        except Exception as e:
            script_results[script_id]['status'] = 'error'
            script_results[script_id]['error'] = str(e)
            script_results[script_id]['finished_at'] = datetime.utcnow().isoformat()


@scripts_bp.route('/')
@login_required
@admin_required
def index():
    """Список доступных скриптов"""
    scripts = get_available_scripts()
    
    # Получаем статусы выполняемых скриптов
    running_scripts = {
        k: v for k, v in script_results.items() 
        if v.get('status') == 'running'
    }
    
    return render_template('admin/scripts.html', 
        scripts=scripts,
        running_scripts=running_scripts
    )


@scripts_bp.route('/run/<script_name>', methods=['POST'])
@login_required
@admin_required
def run_script(script_name):
    """Запуск скрипта"""
    # Проверка безопасности имени
    if not is_safe_script_name(script_name):
        flash('Недопустимое имя скрипта', 'danger')
        return redirect(url_for('scripts.index'))
    
    scripts_dir = get_scripts_dir()
    script_path = os.path.join(scripts_dir, script_name)
    
    # Проверка существования
    if not os.path.isfile(script_path):
        flash('Скрипт не найден', 'danger')
        return redirect(url_for('scripts.index'))
    
    # Генерируем ID для отслеживания
    import secrets
    script_id = secrets.token_hex(8)
    
    # Инициализируем результат
    script_results[script_id] = {
        'script_name': script_name,
        'status': 'pending',
        'created_at': datetime.utcnow().isoformat(),
        'user': current_user.email
    }
    
    # Запускаем в отдельном потоке
    app = current_app._get_current_object()
    thread = threading.Thread(
        target=run_script_async,
        args=(script_path, script_id, app)
    )
    thread.daemon = True
    thread.start()
    
    flash(f'Скрипт "{script_name}" запущен. ID: {script_id}', 'info')
    return redirect(url_for('scripts.result', script_id=script_id))


@scripts_bp.route('/result/<script_id>')
@login_required
@admin_required
def result(script_id):
    """Просмотр результата выполнения скрипта"""
    if script_id not in script_results:
        flash('Результат не найден', 'danger')
        return redirect(url_for('scripts.index'))
    
    result = script_results[script_id]
    return render_template('admin/script_result.html', 
        script_id=script_id,
        result=result
    )


@scripts_bp.route('/api/result/<script_id>')
@login_required
@admin_required
def api_result(script_id):
    """API для получения статуса выполнения"""
    if script_id not in script_results:
        return jsonify({'error': 'Not found'}), 404
    
    return jsonify(script_results[script_id])


@scripts_bp.route('/view/<script_name>')
@login_required
@admin_required
def view_script(script_name):
    """Просмотр содержимого скрипта"""
    if not is_safe_script_name(script_name):
        flash('Недопустимое имя скрипта', 'danger')
        return redirect(url_for('scripts.index'))
    
    scripts_dir = get_scripts_dir()
    script_path = os.path.join(scripts_dir, script_name)
    
    if not os.path.isfile(script_path):
        flash('Скрипт не найден', 'danger')
        return redirect(url_for('scripts.index'))
    
    try:
        with open(script_path, 'r') as f:
            content = f.read()
    except Exception as e:
        flash(f'Ошибка чтения файла: {str(e)}', 'danger')
        return redirect(url_for('scripts.index'))
    
    return render_template('admin/script_view.html',
        script_name=script_name,
        content=content
    )


@scripts_bp.route('/history')
@login_required
@admin_required
def history():
    """История выполнения скриптов"""
    # Сортируем по времени создания (новые первые)
    sorted_results = sorted(
        script_results.items(),
        key=lambda x: x[1].get('created_at', ''),
        reverse=True
    )
    
    return render_template('admin/script_history.html',
        results=sorted_results[:50]  # Последние 50
    )


@scripts_bp.route('/clear-history', methods=['POST'])
@login_required
@admin_required
def clear_history():
    """Очистка истории выполнения"""
    # Удаляем только завершённые
    to_delete = [
        k for k, v in script_results.items()
        if v.get('status') not in ['running', 'pending']
    ]
    
    for key in to_delete:
        del script_results[key]
    
    flash(f'Удалено {len(to_delete)} записей из истории', 'success')
    return redirect(url_for('scripts.history'))