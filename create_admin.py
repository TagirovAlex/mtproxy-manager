#!/usr/bin/env python3
"""
MTProxy Manager - Скрипт создания/изменения администратора
Запускается на сервере для управления администраторами в БД
"""

import os
import sys
import getpass
import argparse

# Добавляем текущую директорию в путь
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Загружаем переменные окружения из .env
from dotenv import load_dotenv
load_dotenv()


def create_app_context():
    """Создание контекста приложения"""
    from app import create_app, db
    app = create_app(os.environ.get('FLASK_CONFIG', 'default'))
    return app, db


def list_admins():
    """Список всех администраторов"""
    app, db = create_app_context()
    
    with app.app_context():
        from app.models import User
        
        admins = User.query.filter_by(is_admin=True).all()
        
        if not admins:
            print("\n⚠️  Администраторы не найдены.\n")
            return
        
        print("\n📋 Список администраторов:")
        print("-" * 60)
        for admin in admins:
            status = "✓ Активен" if admin.is_approved and not admin.is_blocked else "✗ Неактивен"
            print(f"  ID: {admin.id:<4} | {admin.email:<30} | {status}")
        print("-" * 60)
        print(f"  Всего: {len(admins)}\n")


def create_admin(email, password, force=False):
    """Создание нового администратора"""
    app, db = create_app_context()
    
    with app.app_context():
        from app.models import User
        
        # Проверяем существует ли пользователь
        existing = User.query.filter_by(email=email.lower()).first()
        
        if existing:
            if force:
                # Обновляем существующего
                existing.set_password(password)
                existing.is_admin = True
                existing.is_approved = True
                existing.is_blocked = False
                existing.failed_login_attempts = 0
                existing.locked_until = None
                db.session.commit()
                print(f"\n✅ Пользователь {email} обновлён и назначен администратором.\n")
            else:
                print(f"\n⚠️  Пользователь {email} уже существует.")
                print("   Используйте --force для обновления пароля и прав.\n")
                return False
        else:
            # Создаём нового
            user = User(email=email.lower())
            user.set_password(password)
            user.is_admin = True
            user.is_approved = True
            user.is_blocked = False
            
            db.session.add(user)
            db.session.commit()
            print(f"\n✅ Администратор {email} успешно создан.\n")
        
        return True


def change_password(email, password):
    """Изменение пароля пользователя"""
    app, db = create_app_context()
    
    with app.app_context():
        from app.models import User
        
        user = User.query.filter_by(email=email.lower()).first()
        
        if not user:
            print(f"\n❌ Пользователь {email} не найден.\n")
            return False
        
        user.set_password(password)
        user.failed_login_attempts = 0
        user.locked_until = None
        db.session.commit()
        
        print(f"\n✅ Пароль для {email} успешно изменён.\n")
        return True


def promote_admin(email):
    """Назначение пользователя администратором"""
    app, db = create_app_context()
    
    with app.app_context():
        from app.models import User
        
        user = User.query.filter_by(email=email.lower()).first()
        
        if not user:
            print(f"\n❌ Пользователь {email} не найден.\n")
            return False
        
        if user.is_admin:
            print(f"\n⚠️  {email} уже является администратором.\n")
            return True
        
        user.is_admin = True
        user.is_approved = True
        db.session.commit()
        
        print(f"\n✅ {email} назначен администратором.\n")
        return True


def demote_admin(email):
    """Снятие прав администратора"""
    app, db = create_app_context()
    
    with app.app_context():
        from app.models import User
        
        user = User.query.filter_by(email=email.lower()).first()
        
        if not user:
            print(f"\n❌ Пользователь {email} не найден.\n")
            return False
        
        if not user.is_admin:
            print(f"\n⚠️  {email} не является администратором.\n")
            return True
        
        # Проверяем что останется хотя бы один админ
        admin_count = User.query.filter_by(is_admin=True).count()
        if admin_count <= 1:
            print("\n❌ Нельзя снять права с единственного администратора.\n")
            return False
        
        user.is_admin = False
        db.session.commit()
        
        print(f"\n✅ Права администратора сняты с {email}.\n")
        return True


def reset_user(email):
    """Сброс блокировки и счётчика попыток входа"""
    app, db = create_app_context()
    
    with app.app_context():
        from app.models import User
        
        user = User.query.filter_by(email=email.lower()).first()
        
        if not user:
            print(f"\n❌ Пользователь {email} не найден.\n")
            return False
        
        user.is_blocked = False
        user.failed_login_attempts = 0
        user.locked_until = None
        db.session.commit()
        
        print(f"\n✅ Блокировка и счётчик попыток сброшены для {email}.\n")
        return True


def delete_user(email, confirm=False):
    """Удаление пользователя"""
    app, db = create_app_context()
    
    with app.app_context():
        from app.models import User, ProxyKey
        
        user = User.query.filter_by(email=email.lower()).first()
        
        if not user:
            print(f"\n❌ Пользователь {email} не найден.\n")
            return False
        
        if user.is_admin:
            admin_count = User.query.filter_by(is_admin=True).count()
            if admin_count <= 1:
                print("\n❌ Нельзя удалить единственного администратора.\n")
                return False
        
        if not confirm:
            print(f"\n⚠️  Вы уверены, что хотите удалить {email}?")
            print("   Используйте --confirm для подтверждения.\n")
            return False
        
        # Отвязываем ключи
        ProxyKey.query.filter_by(user_id=user.id).update({'user_id': None})
        
        db.session.delete(user)
        db.session.commit()
        
        print(f"\n✅ Пользователь {email} удалён.\n")
        return True


def get_password_interactive(confirm=True):
    """Интерактивный ввод пароля"""
    while True:
        password = getpass.getpass("Введите пароль: ")
        
        if len(password) < 8:
            print("❌ Пароль должен быть не менее 8 символов.")
            continue
        
        if confirm:
            password2 = getpass.getpass("Повторите пароль: ")
            if password != password2:
                print("❌ Пароли не совпадают.")
                continue
        
        return password


def main():
    parser = argparse.ArgumentParser(
        description='MTProxy Manager - Управление администраторами',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:
  %(prog)s --list                           Список администраторов
  %(prog)s --create admin@example.com       Создать администратора
  %(prog)s --create admin@example.com --force   Обновить существующего
  %(prog)s --password admin@example.com     Изменить пароль
  %(prog)s --promote user@example.com       Назначить администратором
  %(prog)s --demote admin@example.com       Снять права админа
  %(prog)s --reset user@example.com         Сбросить блокировку
  %(prog)s --delete user@example.com --confirm  Удалить пользователя
        """
    )
    
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--list', '-l', action='store_true',
                       help='Показать список администраторов')
    group.add_argument('--create', '-c', metavar='EMAIL',
                       help='Создать нового администратора')
    group.add_argument('--password', '-p', metavar='EMAIL',
                       help='Изменить пароль пользователя')
    group.add_argument('--promote', metavar='EMAIL',
                       help='Назначить пользователя администратором')
    group.add_argument('--demote', metavar='EMAIL',
                       help='Снять права администратора')
    group.add_argument('--reset', '-r', metavar='EMAIL',
                       help='Сбросить блокировку пользователя')
    group.add_argument('--delete', '-d', metavar='EMAIL',
                       help='Удалить пользователя')
    
    parser.add_argument('--force', '-f', action='store_true',
                       help='Принудительное обновление при создании')
    parser.add_argument('--confirm', action='store_true',
                       help='Подтверждение удаления')
    parser.add_argument('--password-value', metavar='PASSWORD',
                       help='Пароль (не рекомендуется, лучше ввести интерактивно)')
    
    args = parser.parse_args()
    
    print("""
╔══════════════════════════════════════════════════════════════╗
║           MTProxy Manager - Управление администраторами      ║
╚══════════════════════════════════════════════════════════════╝
    """)
    
    try:
        if args.list:
            list_admins()
        
        elif args.create:
            password = args.password_value or get_password_interactive()
            create_admin(args.create, password, args.force)
        
        elif args.password:
            password = args.password_value or get_password_interactive()
            change_password(args.password, password)
        
        elif args.promote:
            promote_admin(args.promote)
        
        elif args.demote:
            demote_admin(args.demote)
        
        elif args.reset:
            reset_user(args.reset)
        
        elif args.delete:
            delete_user(args.delete, args.confirm)
    
    except KeyboardInterrupt:
        print("\n\n⚠️  Операция отменена.\n")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Ошибка: {e}\n")
        sys.exit(1)


if __name__ == '__main__':
    main()