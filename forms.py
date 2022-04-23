from wtforms import IntegerField, TextAreaField, StringField, SubmitField, PasswordField, EmailField, SelectField, \
    FloatField
from wtforms.validators import DataRequired, Email, InputRequired, NumberRange
from flask_wtf import FlaskForm


class LoginForm(FlaskForm):
    employee_id = StringField('Employee ID', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')


class AddItemForm(FlaskForm):
    name = StringField('Item Name', validators=[DataRequired()])
    price = FloatField('Price', validators=[NumberRange(min=1, message="Enter a positive value.")])
    category = SelectField('Category', coerce=str, validators=[InputRequired()])
    section = SelectField('Section', coerce=str)
    description = StringField('Description', validators=[DataRequired()])
    mod1 = StringField('Mod Name')
    vars1 = StringField('Mod Options')
    mod2 = StringField('Mod Name')
    vars2 = StringField('Mod Options')
    mod3 = StringField('Mod Name')
    vars3 = StringField('Mod Options')
    submit = SubmitField('Submit')


class AddUserForm(FlaskForm):
    full_name = StringField('First Name', validators=[DataRequired()])
    email = EmailField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    role = SelectField('Category', coerce=str, default="Server", validators=[InputRequired()])
    submit = SubmitField('Submit')


class AddCategoryForm(FlaskForm):
    category = StringField('Category', validators=[DataRequired()])
    sections = StringField('Section', validators=[DataRequired()])
    submit = SubmitField('Submit')


class AddBasicForm(FlaskForm):
    field = StringField('Field', validators=[DataRequired()])
    submit = SubmitField('Submit')


class StartOrderForm(FlaskForm):
    table = SelectField('Table', coerce=str, validators=[InputRequired()])
    name = StringField('Customer Name', validators=[DataRequired()])
    submit = SubmitField('Submit')


class AddOrderItemForm(FlaskForm):
    item_id = StringField('Item ID', validators=[DataRequired()])
    mod1 = SelectField('Mod1', coerce=str)
    mod2 = SelectField('Mod1', coerce=str)
    mod3 = SelectField('Mod1', coerce=str)
    notes = TextAreaField('Notes for the Chef')
    quantity = IntegerField('Quantity', default=1,
                            validators=[NumberRange(min=1, message="Quantity must be a positive number.")])
    add = SubmitField('Add')
