from flask_wtf import FlaskForm
from wtforms import (
    StringField,
    PasswordField,
    BooleanField,
    SubmitField,
    TextAreaField,
    SelectField,
    IntegerField,
    HiddenField,
)
from wtforms.validators import (
    DataRequired,
    Email,
    EqualTo,
    Length,
    ValidationError,
    Optional,
    NumberRange,
)
from app.models import User, ProxyInstance


class LoginForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Пароль", validators=[DataRequired()])
    remember_me = BooleanField("Запомнить меня")
    submit = SubmitField("Войти")


class RegistrationForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=120)])
    password = PasswordField("Пароль", validators=[DataRequired(), Length(min=8)])
    password2 = PasswordField("Повторите пароль", validators=[DataRequired(), EqualTo("password")])
    submit = SubmitField("Зарегистрироваться")

    def validate_email(self, field):
        if User.query.filter_by(email=field.data.lower()).first():
            raise ValidationError("Этот email уже зарегистрирован")


class ProfileForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=120)])
    current_password = PasswordField("Текущий пароль", validators=[Optional()])
    new_password = PasswordField("Новый пароль", validators=[Optional(), Length(min=8)])
    new_password2 = PasswordField("Повторите новый пароль", validators=[EqualTo("new_password")])
    submit = SubmitField("Сохранить")

    def __init__(self, original_email, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.original_email = original_email

    def validate_email(self, field):
        if field.data.lower() != self.original_email.lower():
            if User.query.filter_by(email=field.data.lower()).first():
                raise ValidationError("Этот email уже используется")

    def validate_current_password(self, field):
        if self.new_password.data and not field.data:
            raise ValidationError("Введите текущий пароль для смены пароля")


class CreateKeyForm(FlaskForm):
    name = StringField("Названи�� инстанса", validators=[DataRequired(), Length(min=1, max=100)])
    bind_port = IntegerField("Порт", validators=[DataRequired(), NumberRange(min=1, max=65535)])
    bind_ip = StringField("IP", validators=[DataRequired(), Length(min=3, max=64)], default="0.0.0.0")
    fake_tls_domain = StringField("Домен FakeTLS", validators=[DataRequired(), Length(min=3, max=255)])
    owner_user_id = SelectField("Пользователь", coerce=int, validators=[Optional()])
    notes = TextAreaField("Заметки", validators=[Optional(), Length(max=1000)])
    submit = SubmitField("Создать инстанс")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        users = User.query.filter_by(is_approved=True, is_blocked=False).all()
        self.owner_user_id.choices = [(0, "— Не привязан —")] + [(u.id, u.email) for u in users]

    def validate_bind_port(self, field):
        if ProxyInstance.query.filter_by(bind_ip=self.bind_ip.data.strip(), bind_port=field.data).first():
            raise ValidationError("Этот IP:порт уже занят другим инстансом")


class EditKeyForm(FlaskForm):
    name = StringField("Название инстанса", validators=[DataRequired(), Length(min=1, max=100)])
    bind_port = IntegerField("Порт", validators=[DataRequired(), NumberRange(min=1, max=65535)])
    bind_ip = StringField("IP", validators=[DataRequired(), Length(min=3, max=64)])
    fake_tls_domain = StringField("Домен FakeTLS", validators=[DataRequired(), Length(min=3, max=255)])
    owner_user_id = SelectField("Пользователь", coerce=int, validators=[Optional()])
    is_enabled = BooleanField("Включен")
    is_blocked = BooleanField("Заблокирован")
    notes = TextAreaField("Заметки", validators=[Optional(), Length(max=1000)])
    submit = SubmitField("Сохранить")

    def __init__(self, instance_id=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance_id = instance_id
        users = User.query.filter_by(is_approved=True, is_blocked=False).all()
        self.owner_user_id.choices = [(0, "— Не привязан —")] + [(u.id, u.email) for u in users]

    def validate_bind_port(self, field):
        query = ProxyInstance.query.filter_by(bind_ip=self.bind_ip.data.strip(), bind_port=field.data)
        if self.instance_id:
            query = query.filter(ProxyInstance.id != self.instance_id)
        if query.first():
            raise ValidationError("Этот IP:порт уже занят другим инстансом")


class UserManageForm(FlaskForm):
    is_approved = BooleanField("Подтвержден")
    is_admin = BooleanField("Администратор")
    is_blocked = BooleanField("Заблокирован")
    submit = SubmitField("Сохранить")


class SettingsForm(FlaskForm):
    server_domain = StringField("Домен сервера", validators=[DataRequired(), Length(max=255)])
    max_keys_per_user = IntegerField("Максимум инстансов на пользователя", validators=[DataRequired(), NumberRange(min=1, max=100)])
    auto_backup_enabled = BooleanField("Автоматический бэкап")
    auto_backup_interval = SelectField("Интервал бэкапа", choices=[("daily", "Ежедневно"), ("weekly", "Еженедельно"), ("monthly", "Ежемесячно")])
    submit = SubmitField("Сохранить настройки")


class BackupForm(FlaskForm):
    notes = TextAreaField("Примечание к бэкапу", validators=[Length(max=500)])
    submit = SubmitField("Создать бэкап")


class ScriptRunForm(FlaskForm):
    script_name = HiddenField("Имя скрипта", validators=[DataRequired()])
    submit = SubmitField("Выполнить")


class ConfirmActionForm(FlaskForm):
    confirm = HiddenField("Подтверждение", default="yes")
    submit = SubmitField("Подтвердить")