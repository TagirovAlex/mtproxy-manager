from flask_wtf import FlaskForm
from wtforms import (StringField, PasswordField, BooleanField, SubmitField,
                     TextAreaField, SelectField, IntegerField, HiddenField)
from wtforms.validators import (DataRequired, Email, EqualTo, Length, 
                                ValidationError, Optional, NumberRange)
from app.models import User


class LoginForm(FlaskForm):
    """Форма входа"""
    email = StringField('Email', validators=[
        DataRequired(message='Введите email'),
        Email(message='Некорректный email')
    ])
    password = PasswordField('Пароль', validators=[
        DataRequired(message='Введите пароль')
    ])
    remember_me = BooleanField('Запомнить меня')
    submit = SubmitField('Войти')


class RegistrationForm(FlaskForm):
    """Форма регистрации"""
    email = StringField('Email', validators=[
        DataRequired(message='Введите email'),
        Email(message='Некорректный email'),
        Length(max=120, message='Email слишком длинный')
    ])
    password = PasswordField('Пароль', validators=[
        DataRequired(message='Введите пароль'),
        Length(min=8, message='Пароль должен быть не менее 8 символов')
    ])
    password2 = PasswordField('Повторите пароль', validators=[
        DataRequired(message='Повторите пароль'),
        EqualTo('password', message='Пароли не совпадают')
    ])
    submit = SubmitField('Зарегистрироваться')
    
    def validate_email(self, field):
        """Проверка уникальности email"""
        if User.query.filter_by(email=field.data.lower()).first():
            raise ValidationError('Этот email уже зарегистрирован')


class ProfileForm(FlaskForm):
    """Форма редактирования профиля"""
    email = StringField('Email', validators=[
        DataRequired(message='Введите email'),
        Email(message='Некорректный email'),
        Length(max=120)
    ])
    current_password = PasswordField('Теку��ий пароль', validators=[
        Optional()
    ])
    new_password = PasswordField('Новый пароль', validators=[
        Optional(),
        Length(min=8, message='Пароль должен быть не менее 8 символов')
    ])
    new_password2 = PasswordField('Повторите новый пароль', validators=[
        EqualTo('new_password', message='Пароли не совпадают')
    ])
    submit = SubmitField('Сохранить')
    
    def __init__(self, original_email, *args, **kwargs):
        super(ProfileForm, self).__init__(*args, **kwargs)
        self.original_email = original_email
    
    def validate_email(self, field):
        """Проверка уникальности email при изменении"""
        if field.data.lower() != self.original_email.lower():
            if User.query.filter_by(email=field.data.lower()).first():
                raise ValidationError('Этот email уже используется')
    
    def validate_current_password(self, field):
        """Проверка текущего пароля при смене пароля"""
        if self.new_password.data and not field.data:
            raise ValidationError('Введите текущий пароль для смены пароля')


class CreateKeyForm(FlaskForm):
    """Форма создания ключа (минимальная)"""
    name = StringField('Название ключа', validators=[
        DataRequired(message='Введите название'),
        Length(min=1, max=100, message='Название от 1 до 100 символов')
    ])
    submit = SubmitField('Создать ключ')


class EditKeyForm(FlaskForm):
    """Форма редактирования ключа (полная)"""
    name = StringField('Название ключа', validators=[
        DataRequired(message='Введите название'),
        Length(min=1, max=100)
    ])
    fake_tls_domain = SelectField('Домен FakeTLS', choices=[
        ('www.google.com', 'www.google.com'),
        ('www.microsoft.com', 'www.microsoft.com'),
        ('www.apple.com', 'www.apple.com'),
        ('www.cloudflare.com', 'www.cloudflare.com'),
        ('www.amazon.com', 'www.amazon.com'),
        ('www.youtube.com', 'www.youtube.com'),
        ('www.facebook.com', 'www.facebook.com'),
    ])
    user_id = SelectField('Привязка к пользователю', coerce=int, validators=[
        Optional()
    ])
    is_active = BooleanField('Активен')
    
    # Лимиты трафика
    traffic_limit_enabled = BooleanField('Установить лимит трафика')
    traffic_limit_value = IntegerField('Лимит', validators=[
        Optional(),
        NumberRange(min=1, message='Лимит должен быть положительным')
    ])
    traffic_limit_unit = SelectField('Единица', choices=[
        ('MB', 'МБ'),
        ('GB', 'ГБ'),
        ('TB', 'ТБ')
    ])
    traffic_limit_period = SelectField('Период', choices=[
        ('day', 'День'),
        ('week', 'Неделя'),
        ('month', 'Месяц')
    ])
    
    notes = TextAreaField('Заметки', validators=[
        Length(max=1000, message='Максимум 1000 символов')
    ])
    submit = SubmitField('Сохранить')
    
    def __init__(self, *args, **kwargs):
        super(EditKeyForm, self).__init__(*args, **kwargs)
        # Загрузка списка пользователей для выбора
        users = User.query.filter_by(is_approved=True, is_blocked=False).all()
        self.user_id.choices = [(0, '— Не привязан —')] + [
            (u.id, u.email) for u in users
        ]


class UserManageForm(FlaskForm):
    """Форма управления пользователем (для админа)"""
    is_approved = BooleanField('Подтвержден')
    is_admin = BooleanField('Администратор')
    is_blocked = BooleanField('Заблокирован')
    submit = SubmitField('Сохранить')


class SettingsForm(FlaskForm):
    """Форма настроек приложения"""
    server_domain = StringField('Домен сервера', validators=[
        DataRequired(message='Введите домен сервера'),
        Length(max=255)
    ])
    mtg_port = IntegerField('Порт MTG', validators=[
        DataRequired(),
        NumberRange(min=1, max=65535, message='Порт от 1 до 65535')
    ])
    max_keys_per_user = IntegerField('Максимум ключей на пользователя', validators=[
        DataRequired(),
        NumberRange(min=1, max=100)
    ])
    auto_backup_enabled = BooleanField('Автоматический бэкап')
    auto_backup_interval = SelectField('Интервал бэкапа', choices=[
        ('daily', 'Ежедневно'),
        ('weekly', 'Еженедельно'),
        ('monthly', 'Ежемесячно')
    ])
    submit = SubmitField('Сохранить настройки')


class BackupForm(FlaskForm):
    """Форма создания бэкапа"""
    notes = TextAreaField('Примечание к бэкапу', validators=[
        Length(max=500)
    ])
    submit = SubmitField('Создать бэкап')


class ScriptRunForm(FlaskForm):
    """Форма запуска скрипта"""
    script_name = HiddenField('Имя скрипта', validators=[
        DataRequired()
    ])
    submit = SubmitField('Выполнить')


class ConfirmActionForm(FlaskForm):
    """Форма подтверждения действия"""
    confirm = HiddenField('Подтверждение', default='yes')
    submit = SubmitField('Подтвердить')