from flask import Flask, render_template, request, redirect, url_for, flash, abort, jsonify
from flask_bootstrap import Bootstrap
from flask_login import login_user, LoginManager, login_required, current_user, logout_user
from werkzeug.security import generate_password_hash, check_password_hash
from forms import LoginForm, AddItemForm, AddUserForm, AddCategoryForm, AddBasicForm, StartOrderForm, \
    AddOrderItemForm
from tables import db, User, MenuItem, ItemMod, ItemModVar, Category, Section, Role, Order, Table, OrderItem
from datetime import datetime
from functools import wraps
import csv
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get("SECRET_KEY")
Bootstrap(app)
login_manager = LoginManager()
login_manager.init_app(app)

uri = os.environ.get("DB_URL", 'sqlite:///shop.db')
if uri.startswith("postgres://"):
    uri = uri.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = uri

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
with app.app_context():
    db.init_app(app)
    db.create_all()


# ---------------------------------------------------------------------------------------------------------------------
#  NON-ROUTING FUNCTIONS
# ---------------------------------------------------------------------------------------------------------------------
def make_unique(submitted_list: list):
    """
    removes duplicate values in the submitted list
    used in prefill_data()
    """
    unique_list = []
    for item in submitted_list:
        if item not in unique_list:
            unique_list.append(item)
    return unique_list


def menu_create():
    """
    Generates necessary data to be passed on to create the menu (left side of app)
    """
    menu = MenuItem.query.filter_by(status="active").all()
    categories = Category.query.all()
    sections = Section.query.all()
    return menu, categories, sections


def admin_only(function):
    """
    Ensures only the owner has access to specified pages (i.e. setup pages)
    """

    @wraps(function)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role.name != 'Owner':
            return abort(403)
        return function(*args, **kwargs)

    return decorated_function


def get_key(dictionary: dict, search):
    """
    Used in add_item_mod(), edit_menu_item()
    """
    for item in dictionary:
        if dictionary[item] == search:
            return item
    print('Value not in dictionary')
    return


def add_padding(required_length: int, list_to_update: list):
    """
    Used in complete_order()
    Created to avoid ValueError: not enough values to unpack
    """
    padding = [""] * (required_length - len(list_to_update))
    return list_to_update + padding


def change(old: list, new: list):
    """
    Used to detect changes. See edit_menu_item() and edit_user()
    x: represents original values
    y: represents submitted/new values
    Returns:
         final_values: represents updated values
         changed: binary saying whether or not there were updates
    """
    final_values = []
    changed = False
    for index in range(len(old)):
        original_value = old[index]
        submitted_value = new[index]
        if original_value != submitted_value:
            changed = True
            final_values.append(submitted_value)
        else:
            final_values.append(original_value)
    return final_values, changed


def add_menu_sections(category_id: int, sections_list: str):
    """
    used in add_category(), edit_category(), prefill_data()
    """
    sections = sections_list.title().split(',')
    try:
        sections.remove("")
    except ValueError:
        pass

    for section in sections:
        duplicate_section = Section.query.filter_by(name=section, category_id=category_id).first()
        if duplicate_section:
            continue
        new_section = Section(
            name=section,
            category_id=category_id
        )
        db.session.add(new_section)
        db.session.commit()
    return


def add_mod_var(item: MenuItem, mod_name: str, vars_list: str):
    """
    Used in add_menu_item() and edit_menu_item()
    Created to deal with complexity of adding item mods and their variations
    *NOTE: "vars" refers to a collection of objects of type ItemModVar

    MOD: VAR (MV) TYPES
    1. new mod: new vars - add mod
    2. same mod: new vars - add mod
    3. same mod: same vars - associate item with existing mod

    NEW VAR TYPES
    1. same var - associate existing var with new mod
    2. new var - add var
    """
    variations = [var.strip().title() for var in vars_list.split(',')]
    try:
        variations.remove("")
    except ValueError:
        pass

    same_name_mods = db.session.query(ItemMod).filter(ItemMod.name == mod_name).all()
    if same_name_mods:
        mod_opts = {}
        for mod in same_name_mods:
            mod_opts[mod.id] = [var.name for var in mod.vars]
        if variations in mod_opts.values():
            # MV TYPE 3
            mod_id = get_key(mod_opts, variations)
            same_mod = db.session.query(ItemMod).filter(ItemMod.id == mod_id).first()
            item.mods.append(same_mod)
            return

    # add the new mod
    new_mod = ItemMod(name=mod_name.title())
    db.session.add(new_mod)
    new_mod.items.append(item)

    # are any vars the same?
    for var in variations:
        db_vars = [var.name for var in ItemModVar.query.all()]
        if var in db_vars:
            # VAR TYPE 1
            same_var = db.session.query(ItemModVar).filter(ItemModVar.name == var).first()
            new_mod.vars.append(same_var)
        else:
            # VAR TYPE 2
            new_var = ItemModVar(name=var)
            db.session.add(new_var)
            new_var.mods.append(new_mod)
    db.session.commit()

    # Database cleanup
    # If there are mods not associated with an item, delete
    all_mods = [mod.id for mod in ItemMod.query.all() if len(mod.items) == 0]
    for mod_id in all_mods:
        mod = ItemMod.query.get(mod_id)
        # dissociate mod from vars to prevent var deletion
        mod.vars = []
        db.session.delete(mod)
        db.session.commit()
    return


# ---------------------------------------------------------------------------------------------------------------------
#  ROUTES THAT RETURN DETAILS FOR GET REQUESTS VIA JS OR PREFILL DATA
# ---------------------------------------------------------------------------------------------------------------------
@app.route('/details/item/<int:item_id>')
@login_required
def get_item_details(item_id):
    item = MenuItem.query.get(item_id)
    details = {
        'id': item.id,
        'name': item.name,
        'price': item.price,
        'description': item.description,
        'mods': [(mod.name, [var.name for var in mod.vars]) for mod in item.mods]
    }
    return jsonify(details)


@app.route('/details/category/<category_name>')
@login_required
def get_category_details(category_name):
    category = Category.query.filter_by(name=category_name).first()
    details = {
        'id': category.id,
        'name': category.name,
        'sections': [section.name for section in category.sections]
    }
    return jsonify(details)


@app.route('/import-data')
def import_data():
    # create dictionary from csv data
    data = {}
    with open('sample-menu.csv', 'r', newline='', encoding='utf-8-sig') as file:
        file_reader = csv.reader(file, delimiter=',')
        for row in file_reader:
            data[row.pop(0)] = row

    updates = False

    # add categories
    categories = {}
    for category in make_unique(data["category"]):
        existing_category = Category.query.filter_by(name=category.upper()).first()
        if existing_category:
            categories[category] = existing_category.id
            continue
        new_category = Category(name=category.upper())
        db.session.add(new_category)
        db.session.commit()
        categories[new_category.name] = new_category.id
        updates = True

    # add sections
    cat_sec = make_unique([(data["category"][index], data["section"][index]) for index in range(len(data["section"]))])
    for cs in cat_sec:
        category = Category.query.filter_by(name=cs[0].upper()).first()
        existing_section = Section.query.filter_by(name=cs[1].title(), category_id=category.id).first()
        if existing_section:
            continue
        add_menu_sections(category.id, cs[1])
        updates = True

    # add menu items
    for index in range(len(data["name"])):
        # if the item exists, skip
        if MenuItem.query.filter_by(name=data["name"][index].title()).first():
            continue
        category = Category.query.filter_by(name=data["category"][index].upper()).first()
        section = Section.query.filter_by(category_id=category.id, name=data["section"][index].title()).first()
        new_item = MenuItem(
            name=data["name"][index].title(),
            price=data["price"][index],
            description=data["description"][index],
            status="active",
            category_id=category.id,
            section_id=section.id
        )
        db.session.add(new_item)
        for loop in range(1, 4):
            add_mod_var(new_item, data["mod" + str(loop)][index].title(), data["vars" + str(loop)][index])
        db.session.commit()
        updates = True

    if updates:
        flash('Success! Dummy data added.')
    else:
        flash('No changes were made. Dummy data has already been added.')
    return redirect(url_for('home'))


@app.route('/reset-app')
def delete_data():
    for table in reversed(db.metadata.sorted_tables):
        db.session.execute(table.delete())
    db.session.commit()
    return redirect(url_for('home'))


# ---------------------------------------------------------------------------------------------------------------------
#  FLASK ROUTES: HOME, LOGIN, LOGOUT
# ---------------------------------------------------------------------------------------------------------------------
@app.route('/')
def home():
    """
    If the active user is authenticated, redirect to the start order page.
    If there are no users registered (system has never been used before):
     - create the owner role, add a dummy owner user, login, and redirect to setup page to set-up the system.
    Else redirect to login page.
    """
    user_count = User.query.count()
    if current_user.is_authenticated:
        return redirect(url_for('start_order'))
    elif user_count == 0:
        new_role = Role(name="Owner")
        db.session.add(new_role)
        db.session.commit()
        owner_user = User(
            full_name="SETUP ACCOUNT",
            email="your@mail.com",
            password=generate_password_hash("password", method="pbkdf2:sha256", salt_length=8),
            role_id=new_role.id,
            status="active"
        )
        take_out = Table(
            name="Take Out",
            status="available"
        )
        db.session.add_all([take_out, owner_user])
        db.session.commit()
        login_user(owner_user)
        return redirect(url_for('setup'))
    return redirect(url_for('login'))


@app.route('/login', methods=['POST', 'GET'])
def login():
    menu, categories, sections = menu_create()
    form = LoginForm()

    if current_user.is_authenticated:
        return redirect(url_for('start_order'))
    if form.validate_on_submit():
        employee_id = request.form.get('employee_id')
        password = request.form.get('password')

        user = User.query.get(employee_id)
        if user:
            if check_password_hash(user.password, password):
                login_user(user)
                return redirect(url_for('start_order'))
            else:
                flash('Password incorrect.')
                return redirect(url_for('login'))
        else:
            flash('Employee ID is not registered in the database.')
            return redirect(url_for('login'))
    return render_template('login.html', form=form, menu=menu, categories=categories, sections=sections)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login'))


# ---------------------------------------------------------------------------------------------------------------------
#  FLASK ROUTES: TAKE AN ORDER
# ---------------------------------------------------------------------------------------------------------------------
@app.route('/start-order', methods=['GET', 'POST'])
def start_order():
    menu, categories, sections = menu_create()
    form = StartOrderForm()
    form.table.choices = [table.name for table in Table.query.filter_by(status='available').all()]
    started_order = Order.query.filter_by(user_id=current_user.id, status="started").first()

    if started_order:
        return redirect(url_for('complete_order'))
    if form.validate_on_submit():
        table = Table.query.filter_by(name=form.table.data).first()
        new_order = Order(
            customer_name=form.name.data,
            status='started',
            created_at=datetime.now().strftime("%m/%d/%Y %H:%M:%S"),
            table_id=table.id,
            user_id=current_user.id
        )
        if table.name != "Take Out":
            table.status = 'unavailable'
        db.session.add(new_order)
        db.session.commit()
        return redirect(url_for('complete_order'))
    return render_template('order-start.html', form=form, menu=menu, categories=categories, sections=sections)


@app.route('/complete-order', methods=['GET', 'POST'])
@login_required
def complete_order():
    menu, categories, sections = menu_create()
    form = AddOrderItemForm()
    started_order = Order.query.filter_by(user_id=current_user.id, status="started").first()
    requested_order = Order.query.get(request.args.get('id'))
    order = started_order or requested_order

    # set choices for form
    all_vars = [var.name for var in ItemModVar.query.all()] + ['null']
    form.mod1.choices = form.mod2.choices = form.mod3.choices = all_vars

    if form.validate_on_submit():
        data = form.data
        item_id = data['item_id']
        order_item = db.session.query(MenuItem).get(item_id)
        price = order_item.price
        new_quantity = data['quantity']
        notes = data['notes']
        new_vars = [data[x] for x in data if "mod" in x and data[x] != "null"]

        # CHECK 1: If adding the same exact item then update previous data
        similar_items = db.session.query(OrderItem).filter(
            OrderItem.item_id == item_id,
            OrderItem.notes == notes,
            OrderItem.order_id == order.id
        ).all()
        if similar_items:
            item_details = {item: [var.name for var in item.vars] for item in similar_items}
            if new_vars in item_details.values():
                same_item = get_key(item_details, new_vars)
                same_item.quantity += new_quantity
                same_item.subtotal = same_item.quantity * price
                db.session.commit()
                return redirect(url_for('complete_order', id=order.id))

        # Create a new item
        new_order_item = OrderItem(
            quantity=new_quantity,
            notes=notes,
            subtotal=new_quantity * price,
            item_id=item_id,
            order_id=order.id
        )
        db.session.add(new_order_item)

        # associate vars with new ordered item
        order_item_vars = ItemModVar.query.filter(ItemModVar.name.in_(new_vars)).all()
        new_order_item.vars.extend(order_item_vars)
        db.session.commit()
        return redirect(url_for('complete_order', id=order.id))
    return render_template('order-complete.html', form=form, menu=menu, categories=categories, sections=sections,
                           order=order)


@app.route('/submit-order')
@login_required
def submit_order():
    order = Order.query.get(request.args.get('id'))
    if len(order.order_items) > 0:
        order.status = 'submitted'
        order.submitted_at = datetime.now().strftime("%m/%d/%Y %H:%M:%S")
        db.session.commit()
        flash(f"Success: ORDER #{order.id} submitted")
        return redirect(url_for('show_orders'))
    else:
        flash(f"Please add an item.")
        return redirect(url_for('complete_order'))


@app.route('/delete-order-item')
@login_required
def delete_order_item():
    order_item = OrderItem.query.get(request.args.get('id'))
    order_id = order_item.order_id
    db.session.delete(order_item)
    db.session.commit()
    return redirect(url_for('complete_order', id=order_id))


@app.route('/cancel-order')
@login_required
def cancel_order():
    # Get Active Order
    order = Order.query.get(request.args.get('id'))
    not_empty_order = OrderItem.query.filter_by(order_id=order.id).all()
    order.table.status = "available"
    if not_empty_order:
        order.status = 'cancelled'
        order.closed_at = datetime.now().strftime("%m/%d/%Y %H:%M:%S")
        flash(f"Success: Order #{order.id} for {order.customer_name} cancelled")
    else:
        db.session.delete(order)
        flash(f"Success: Order #{order.id} for {order.customer_name} deleted")
    db.session.commit()

    return redirect(url_for('show_orders'))


@app.route('/close-order')
@login_required
def close_order():
    # Get Active Order
    order = db.session.query(Order).get(request.args.get('id'))
    order.status = 'closed'
    order.table.status = 'available'
    order.closed_at = datetime.now().strftime("%m/%d/%Y %H:%M:%S")
    flash(f"Success: Order #{order.id} for {order.customer_name} closed")
    db.session.commit()
    return redirect(url_for('show_orders'))


# ---------------------------------------------------------------------------------------------------------------------
#  FLASK ROUTES: SYSTEM SETUP & SETTINGS
# ---------------------------------------------------------------------------------------------------------------------
@app.route('/setup')
@admin_only
def setup():
    menu, categories, sections = menu_create()
    return render_template('setup.html', menu=menu, categories=categories, sections=sections)


@app.route('/orders')
def show_orders():
    menu, categories, sections = menu_create()
    orders = Order.query.filter(Order.status.not_in(['closed', 'cancelled', 'started'])).all()
    closed_orders = db.session.query(Order).filter(Order.status == "closed").all()
    lifetime_total = 0
    for x in closed_orders:
        for y in x.order_items:
            lifetime_total += y.subtotal
    return render_template('orders-show.html', menu=menu, categories=categories, sections=sections, orders=orders,
                           total=lifetime_total)


@app.route('/add-role', methods=['GET', 'POST'])
@admin_only
def add_role():
    menu, categories, sections = menu_create()
    form = AddBasicForm()
    roles = Role.query.all()
    if form.validate_on_submit():
        role_name = form.field.data.title()
        role_exists = Role.query.filter_by(name=role_name).first()
        if not role_exists:
            new_role = Role(name=role_name)
            db.session.add(new_role)
            db.session.commit()
            flash(f'Success: {new_role.name} role added')
            return redirect(url_for('add_role'))
        else:
            flash('ERROR: Role names must be unique')
    return render_template('update-role-table.html', form=form, menu=menu, categories=categories, sections=sections,
                           roles=roles)


@app.route('/delete-role')
@admin_only
def delete_role():
    role_id = request.args.get('id')
    users = User.query.filter_by(role_id=role_id).all()
    if not users:
        role = Role.query.get(role_id)
        flash(f'Success: {role.name} role has been deleted')
        db.session.delete(role)
        db.session.commit()
    else:
        flash(f'ERROR: That role is currently assigned to a user.')
    return redirect(url_for('add_role'))


@app.route('/add-user', methods=['POST', 'GET'])
@admin_only
def add_user():
    menu, categories, sections = menu_create()
    users = User.query.filter_by(status="active").all()
    form = AddUserForm()
    form.role.choices = [role.name for role in Role.query.all()]
    if form.validate_on_submit():
        data = form.data
        role_id = Role.query.filter_by(name=data["role"]).first().id
        new_user = User(
            full_name=data["full_name"],
            email=data["email"],
            password=generate_password_hash(data["password"], method="pbkdf2:sha256", salt_length=8),
            role_id=role_id,
            status="active"
        )
        db.session.add(new_user)
        db.session.commit()
        flash(f"Success! {new_user.full_name}'s ID is {new_user.id}")
        return redirect(url_for('add_user'))
    return render_template('update-user.html', form=form, menu=menu, categories=categories, sections=sections,
                           users=users)


@app.route('/delete-user')
@admin_only
def remove_user():
    user_id = request.args.get('id')
    user = User.query.get(user_id)
    user.status = "inactive"
    db.session.commit()
    flash(f'SUCCESS: {user.full_name} is now inactive')
    return redirect(url_for('add_user'))


@app.route('/edit-user', methods=['GET', 'POST'])
@admin_only
def edit_user():
    menu, categories, sections = menu_create()
    users = User.query.filter_by(status="active").all()
    form = AddUserForm()
    form.role.choices = [role.name for role in Role.query.all()]

    user_id = request.args.get('id')
    user = db.session.query(User).get(user_id)

    if form.validate_on_submit():
        data = form.data
        submitted_role_id = Role.query.filter_by(name=data["role"]).first().id
        original = [user.full_name, user.email, user.role_id]
        submit = [data["full_name"], data["email"], submitted_role_id]
        [user.full_name, user.email, user.role_id], updates = change(original, submit)
        if not check_password_hash(user.password, data["password"]):
            user.password = generate_password_hash(data["password"], method="pbkdf2:sha256", salt_length=8)
            updates = True
        if updates:
            db.session.commit()
            flash(f"Success! {user.full_name}'s info has been updated")
        else:
            flash(f"Error: No changes detected")
        return redirect(url_for('add_user'))

    # SET DEFAULTS
    form.full_name.default, form.email.default, form.role.default = user.full_name, user.email, user.role.name
    form.process()
    return render_template('update-user.html', form=form, menu=menu, categories=categories, sections=sections,
                           users=users)


@app.route('/add-table', methods=['GET', 'POST'])
@admin_only
def add_table():
    menu, categories, sections = menu_create()
    tables = Table.query.all()
    form = AddBasicForm()
    if form.validate_on_submit():
        table_name = form.data["field"].title()
        table_exists = Table.query.filter_by(name=table_name).first()
        if not table_exists:
            new_table = Table(
                name=table_name,
                status="available"
            )
            db.session.add(new_table)
            db.session.commit()
            flash(f'Success: {new_table.name} added')
            return redirect(url_for('add_table'))
        flash('ERROR: Table names must be unique')
    return render_template('update-role-table.html', form=form, menu=menu, categories=categories, sections=sections,
                           tables=tables)


@app.route('/remove-table')
@admin_only
def remove_table():
    table_id = request.args.get('id')
    table = Table.query.get(table_id)
    orders = Order.query.filter_by(table_id=table_id).all()
    if not orders:
        db.session.delete(table)
        flash(f'Success: {table.name} has been deleted')
    else:
        table.status = "inactive"
        flash(f'Success: {table.name} is now inactive')
    db.session.commit()
    return redirect(url_for('add_table'))


@app.route('/add-category', methods=['GET', 'POST'])
@admin_only
def add_category():
    menu, categories, sections = menu_create()
    form = AddCategoryForm()
    if form.validate_on_submit():
        data = form.data
        category_name = data['category'].upper()

        category_exists = Category.query.filter_by(name=category_name).first()
        if category_exists:
            flash(f'ERROR: Category names must be unique')
            return redirect(url_for('add_category'))

        new_category = Category(name=category_name)
        db.session.add(new_category)
        db.session.commit()

        add_menu_sections(new_category.id, data['sections'])

        flash(f'Success! {data["category"].upper()} added')
        return redirect(url_for('add_category'))
    return render_template('update-category.html', form=form, menu=menu, categories=categories, sections=sections)


@app.route('/edit-category', methods=['GET', 'POST'])
@admin_only
def edit_category():
    menu, categories, sections = menu_create()
    form = AddCategoryForm()
    category = Category.query.get(request.args.get('id'))

    if form.validate_on_submit():
        data = form.data

        # was the category name updated?
        if data["category"].upper() != category.name:
            # is the updated name in use?
            category_exists = Category.query.filter_by(name=data["category"].upper()).first()
            if category_exists:
                flash(f'ERROR: Category names must be unique')
                return redirect(url_for('add_category'))
            category.name = data["category"].upper()
            db.session.commit()

        current_sections = [section.name for section in category.sections]
        updated_sections = data['sections'].title().split(',')
        add_sections = list(set(updated_sections) - set(current_sections))
        remove_sections = list(set(current_sections) - set(updated_sections))
        if add_sections:
            add_menu_sections(category.id, ','.join(add_sections))
        if remove_sections:
            for section_name in remove_sections:
                section = Section.query.filter_by(name=section_name, category_id=category.id).first()
                section_in_use = [item for item in section.items if item.status == 'active']
                if section_in_use:
                    flash(f"Error: Items are associated with the section {section_name}")
                    return redirect(url_for('add_category'))
                section.items = []
                db.session.delete(section)
                db.session.commit()
        return redirect(url_for('add_category'))

    current_sections = ','.join([section.name for section in category.sections])
    form.category.default, form.sections.default = category.name, current_sections
    form.process()
    return render_template('update-category.html', form=form, menu=menu, categories=categories, sections=sections)


@app.route('/remove-category', methods=['GET', 'POST'])
@admin_only
def remove_category():
    category = Category.query.get(request.args.get('id'))
    category_in_use = [item for item in category.items if item.status == 'active']
    if category_in_use:
        flash(f"Error: Items are associated with the category {category.name}")
    else:
        for section in Section.query.filter_by(category_id=category.id).all():
            db.session.delete(section)
        db.session.delete(category)
        flash(f"Success: {category.name} has been deleted")
    db.session.commit()
    return redirect(url_for('add_category'))


# ---------------------------------------------------------------------------------------------------------------------
#  FLASK ROUTES: EDIT MENU ITEMS
# ---------------------------------------------------------------------------------------------------------------------
@app.route('/update-menu', methods=['GET', 'POST'])
@admin_only
def add_menu_item():
    menu, categories, sections = menu_create()
    form = AddItemForm()
    form.category.choices = [category.name for category in categories]
    form.section.choices = [section.name for section in sections]

    if form.validate_on_submit():
        data = form.data

        # is the item name unique?
        if MenuItem.query.filter_by(name=data['name']).first():
            flash(f'Error: Item names must be unique.')
            return redirect(url_for('add_menu_item'))

        category_id = Category.query.filter(Category.name == data['category']).first().id
        section_id = Section.query.filter(Section.name == data['section']).first().id

        new_item = MenuItem(
            name=data['name'],
            price=data['price'],
            category_id=category_id,
            section_id=section_id,
            description=data['description'],
            status="active"
        )
        db.session.add(new_item)
        db.session.commit()

        # MODS
        for i in range(1, 4):
            mod_name = data['mod' + str(i)].title()
            var_data = data['vars' + str(i)].title()

            if mod_name and var_data:
                add_mod_var(new_item, mod_name, var_data)

        flash(f'Success! {form.name.data} added to the menu')

        return redirect(url_for('add_menu_item'))

    return render_template('update-menu.html', form=form, menu=menu, categories=categories, sections=sections)


@app.route('/edit-menu-item/<int:id>', methods=['GET', 'POST'])
@admin_only
def edit_menu_item(id):
    menu, categories, sections = menu_create()
    item = MenuItem.query.get(id)
    form = AddItemForm()
    form.category.choices = [category.name for category in categories]
    form.section.choices = [section.name for section in sections]

    current_mod_vars = {mod.name: ','.join([var.name for var in mod.vars]) for mod in item.mods}
    current_mods = {mod.name: mod for mod in item.mods}

    if form.validate_on_submit():
        data = form.data
        category_id = Category.query.filter(Category.name == data['category']).first().id
        section_id = Section.query.filter(Section.name == data['section']).first().id

        original = [item.name, item.price, item.category_id, item.section_id, item.description]
        submit = [data['name'], int(data['price']), category_id, section_id, data['description']]

        [item.name, item.price, item.category_id, item.section_id, item.description], updates = change(original, submit)
        db.session.commit()

        updated_mod_vars = {data["mod" + str(i)].title(): data["vars" + str(i)].title() for i in range(1, 4)}

        """
        MOD: VAR TYPES
        1. new mod: new vars - create a new mod
        2. new mod: same vars - update existing mod name
        3. same mod: new vars - create a new mod
        4. same mod: same vars - do nothing
        5. not included mod: vars - dissociate item from mod
        """
        for mv in current_mod_vars:
            if mv in updated_mod_vars:
                if current_mod_vars[mv] != updated_mod_vars[mv]:
                    # TYPE 3
                    add_mod_var(item, mv, updated_mod_vars[mv])
                    updates = True
                # TYPE 4
                del updated_mod_vars[mv]

            else:
                if current_mod_vars[mv] in updated_mod_vars.values():
                    # TYPE 2
                    new_mod_name = get_key(updated_mod_vars, current_mod_vars[mv])
                    current_mods[mv].name = new_mod_name
                    del updated_mod_vars[new_mod_name]
                    updates = True
                else:
                    # TYPE 5
                    item.mods.remove(current_mods[mv])
                    updates = True
        db.session.commit()

        for mv in updated_mod_vars:
            # TYPE 1
            add_mod_var(item, mv, updated_mod_vars[mv])
            updates = True

        if updates:
            flash(f"Success! {item.name} has been updated")
        else:
            flash(f"Error: No changes detected")

        return redirect(url_for('add_menu_item'))

    # Set default values for the form
    form.name.default, form.price.default, form.category.default, form.section.default, form.description.default \
        = item.name, item.price, item.category.name, item.section.name, item.description
    form.mod1.default, form.mod2.default, form.mod3.default = add_padding(3, list(current_mod_vars))
    form.vars1.default, form.vars2.default, form.vars3.default = add_padding(3, list(current_mod_vars.values()))
    form.process()

    return render_template('update-menu.html', form=form, menu=menu, categories=categories, sections=sections,
                           item_id=id)


@app.route('/remove-menu-item')
@admin_only
def remove_menu_item():
    """
    item is made inactive due to several many:many relationships
    """
    item = MenuItem.query.get(request.args.get('id'))
    if item.order_items:
        item.status = "inactive"
        flash(f"Success: {item.name} is now inactive.")
    else:
        item.mods = []
        db.session.delete(item)
        flash(f"Success: {item.name} has been deleted.")
    db.session.commit()
    return redirect(url_for('add_menu_item'))


if __name__ == "__main__":
    app.run(debug=True)
