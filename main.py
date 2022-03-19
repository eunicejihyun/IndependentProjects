from flask import Flask, render_template, request, redirect, url_for, flash, abort
from flask_bootstrap import Bootstrap
from flask_login import login_user, LoginManager, login_required, current_user, logout_user
from werkzeug.security import generate_password_hash, check_password_hash
from forms import LoginForm, AddItemForm, AddUserForm, AddCategoryForm, AddBasicForm, StartOrderForm, \
    AddOrderItemForm
from tables import db, User, MenuItem, ItemMod, Category, Section, Role, Order, Table, OrderItem, OrderItemMod
from datetime import datetime
from functools import wraps
import os

# FLASK SETUP #########################################################################################################
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get("SECRET_KEY")
Bootstrap(app)
login_manager = LoginManager()
login_manager.init_app(app)

uri = os.environ.get("DB_URL", 'sqlite:///shop.db')
if uri.startswith("postgres://"):
    uri = uri.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = uri

# app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///complete_shop.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
with app.app_context():
    db.init_app(app)
    db.create_all()


# Trying to reduce repeated code = this creates the necessary data to be passed on for the menu.
def menu_create():
    menu = MenuItem.query.filter(MenuItem.status == "active").all()
    categories = Category.query.filter(Category.status == "active").all()
    sections = Section.query.filter(Section.status == "active").all()
    return menu, categories, sections


# Ensure only admin has access to certain pages
def admin_only(function):
    @wraps(function)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.id != 1:
            return abort(403)
        return function(*args, **kwargs)

    return decorated_function


# FLASK ROUTING #######################################################################################################
@app.route('/')
def home():
    user_count = db.session.query(User).count()
    if current_user.is_authenticated:
        return redirect(url_for('start_order'))
    elif user_count == 0:
        return redirect(url_for('setup'))
    else:
        return redirect(url_for('login'))


@app.route('/login', methods=['POST', 'GET'])
def login():
    menu, categories, sections = menu_create()
    form = LoginForm()

    if current_user.is_authenticated:
        return redirect(url_for('start_order'))
    if request.method == 'POST':
        employee_id = request.form.get('employee_id')
        password = request.form.get('password')

        user = db.session.query(User).filter_by(id=employee_id).first()
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
    return render_template('index.html', form=form, menu=menu, categories=categories, sections=sections)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login'))


# TAKE ORDERS ########################################################################################################

@app.route('/start-order', methods=['GET', 'POST'])
def start_order():
    menu, categories, sections = menu_create()
    table_options = [table.name for table in db.session.query(Table).filter(Table.status == 'available').all()]
    form = StartOrderForm()
    form.table.choices = table_options
    started_order = db.session.query(Order).filter(Order.user_id == current_user.id,
                                                   Order.status == "started").order_by(Order.id.desc()).first()

    if started_order:
        return redirect(url_for('complete_order'))
    if form.validate_on_submit():
        table = db.session.query(Table).filter(Table.name == form.table.data).first()
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
    return render_template('start-order.html', form=form, menu=menu, categories=categories, sections=sections)


@app.route('/complete-order', methods=['GET', 'POST'])
@login_required
def complete_order():
    menu, categories, sections = menu_create()
    form = AddOrderItemForm()
    item_id = request.args.get("item_id")
    order_id = request.args.get("order_id")

    if order_id:
        order = db.session.query(Order).get(order_id)
    else:
        order = db.session.query(Order).filter(Order.user_id == current_user.id, Order.status == "started").order_by(
            Order.id.desc()).first()

    # Variable created to save item ID and avoid cyclical code
    if item_id:
        order_item = db.session.query(MenuItem).get(item_id)

        # Set Mod Variation Choices for Form
        if order_item.mods:
            options = [mod.variations.split(',') for mod in order_item.mods]
        else:
            options = []
        padding = [['']] * (3 - len(options))
        mod_choices = options + padding
        [form.mod1.choices, form.mod2.choices, form.mod3.choices] = mod_choices

        if form.validate_on_submit():
            price = db.session.query(MenuItem).get(item_id).price
            data = form.data
            notes = data['notes']
            order_id = order.id

            # CHECK 1: If adding the same exact item then update previous data
            same_item = db.session.query(OrderItem).filter(
                OrderItem.notes == notes,
                OrderItem.item_id == item_id,
                OrderItem.order_id == order_id
            ).first()

            if same_item:
                new_mods = [data[x] for x in data if "mod" in x and data[x] != ""]
                prev_mods = [x.chosen_var for x in same_item.order_item_mods]
                print(new_mods, prev_mods)

                if new_mods == prev_mods:
                    same_item.quantity += data['quantity']
                    same_item.subtotal = same_item.quantity * price
                    db.session.commit()
                    return redirect(url_for('complete_order', order_id=order_id))
            # END CHECK 1

            data = form.data
            new_order_item = OrderItem(
                quantity=data['quantity'],
                notes=data['notes'],
                subtotal=data['quantity'] * price,
                item_id=item_id,
                order_id=order.id
            )
            db.session.add(new_order_item)
            db.session.commit()

            mod_names = [mod.id for mod in order_item.mods]
            mod_count = 0
            for x in data:
                if "mod" in x and data[x] != "":
                    new_oi_mod = OrderItemMod(
                        chosen_var=data[x],
                        order_item_id=new_order_item.id,
                        mod_id=mod_names[mod_count]
                    )
                    db.session.add(new_oi_mod)
                    db.session.commit()
                    mod_count += 1

            return redirect(url_for('complete_order', order_id=order_id))

        return render_template('complete-order.html', form=form, menu=menu, categories=categories, sections=sections,
                               order=order, item=order_item)

    return render_template('complete-order.html', form=form, menu=menu, categories=categories, sections=sections,
                           order=order)


@app.route('/submit-order/<int:order_id>')
@login_required
def submit_order(order_id):
    # Get Active Order
    order = db.session.query(Order).get(order_id)
    if len(order.order_items) > 0:
        order.status = 'submitted'
        order.submitted_at = datetime.now().strftime("%m/%d/%Y %H:%M:%S")
        db.session.commit()
        flash(f"Success: ORDER #{order.id} submitted")
        return redirect(url_for('show_orders'))
    else:
        flash(f"Please select at least one item.")
        return redirect(url_for('complete_order'))


@app.route('/delete/order-item/<int:oi_id>')
@login_required
def delete_order_item(oi_id):
    order_id = request.args.get('order_id')
    order_item = OrderItem.query.get(oi_id)
    db.session.delete(order_item)
    db.session.commit()
    return redirect(url_for('complete_order', order_id=order_id))


@app.route('/cancel-order/<int:order_id>')
@login_required
def cancel_order(order_id):
    # Get Active Order
    order = db.session.query(Order).get(order_id)
    not_empty_order = db.session.query(OrderItem).filter(OrderItem.order_id == order.id).all()
    if not_empty_order:
        order.status = 'cancelled'
        order.closed_at = datetime.now().strftime("%m/%d/%Y %H:%M:%S")
        flash(f"Success: Order #{order.id} for {order.customer_name} cancelled")
    else:
        db.session.delete(order)
        flash(f"Success: Order #{order.id} for {order.customer_name} deleted")
    db.session.commit()

    return redirect(url_for('show_orders'))


@app.route('/close-order/<int:order_id>')
@login_required
def close_order(order_id):
    # Get Active Order
    order = db.session.query(Order).get(order_id)
    order.status = 'closed'
    order.table.status = 'available'
    order.closed_at = datetime.now().strftime("%m/%d/%Y %H:%M:%S")
    flash(f"Success: Order #{order.id} for {order.customer_name} closed")
    db.session.commit()
    return redirect(url_for('show_orders'))


# INITIAL DATABASE SETUP ##############################################################################################

@app.route('/setup', methods=['GET', 'POST'])
def setup():
    menu, categories, sections = menu_create()
    # SEE IF THIS IS A FIRST TIME SETUP.
    user_count = db.session.query(User).count()
    if user_count == 0:
        owner_role = Role(
            name="Owner"
        )
        db.session.add(owner_role)
        owner_user = User(
            first_name="SETUP",
            last_name="ACCOUNT",
            email="your@mail.com",
            password=generate_password_hash("password", method="pbkdf2:sha256", salt_length=8),
            role_id=1,
            status="active"
        )
        take_out = Table(
            name="Take Out",
            status="available"
        )
        db.session.add_all([take_out, owner_user])
        db.session.commit()
        login_user(owner_user)
    return render_template('settings.html', menu=menu, categories=categories, sections=sections)


@app.route('/settings')
@admin_only
def settings():
    menu, categories, sections = menu_create()
    return render_template('settings.html', menu=menu, categories=categories, sections=sections)


@app.route('/orders')
def show_orders():
    menu, categories, sections = menu_create()
    orders = db.session.query(Order).filter(Order.status.not_in(['closed', 'cancelled'])).all()
    closed_orders = db.session.query(Order).filter(Order.status == "closed").all()
    lifetime_total = 0
    for x in closed_orders:
        for y in x.order_items:
            lifetime_total += y.subtotal
    return render_template('show-orders.html', menu=menu, categories=categories, sections=sections, orders=orders,
                           total=lifetime_total)


@app.route('/add-role', methods=['GET', 'POST'])
@admin_only
def add_role():
    menu, categories, sections = menu_create()
    form = AddBasicForm()
    roles = db.session.query(Role).all()
    if form.validate_on_submit():
        data = form.data

        role_exists = db.session.query(Role).filter(Role.name == data["field"].title()).first()

        if not role_exists:
            new_role = Role(
                name=data["field"].title()
            )
            db.session.add(new_role)
            db.session.commit()
            flash(f'Success: {new_role.name} roles added')
            return redirect(url_for('add_role'))
        else:
            flash('ERROR: Role names must be unique')

    return render_template('add-role-table.html', form=form, menu=menu, categories=categories, sections=sections,
                           roles=roles)


@app.route('/delete/role')
@admin_only
def delete_role():
    role_id = request.args.get("role_id")
    users = db.session.query(User).filter(User.role_id == role_id).all()
    if not users:
        role = Role.query.get(role_id)
        db.session.delete(role)
        db.session.commit()
    else:
        flash(f'ERROR: That role is currently assigned to a user.')
    return redirect(url_for('add_role'))


@app.route('/add-user', methods=['POST', 'GET'])
@admin_only
def add_user():
    menu, categories, sections = menu_create()
    roles = [role[0] for role in db.session.query(Role.name.distinct()).all()]
    users = db.session.query(User).filter(User.status == "active").all()
    form = AddUserForm()
    form.role.choices = roles
    if form.validate_on_submit():
        role_name = request.form.get("role")
        role_id = db.session.query(Role.id).filter(Role.name == role_name).first().id

        new_user = User(
            first_name=request.form.get("first_name"),
            last_name=request.form.get("last_name"),
            email=request.form.get("email"),
            password=generate_password_hash(request.form.get("password"), method="pbkdf2:sha256", salt_length=8),
            role_id=role_id,
            status="active"
        )
        db.session.add(new_user)
        db.session.commit()
        flash(f"Success! {request.form.get('first_name')}'s ID is {new_user.id}")
        return redirect(url_for('add_user'))
    return render_template('add-user.html', form=form, menu=menu, categories=categories, sections=sections, users=users)


@app.route('/delete/user')
@admin_only
def remove_user():
    user_id = request.args.get("user_id")
    user = User.query.get(user_id)
    user.status = "inactive"
    db.session.commit()
    flash(f'SUCCESS: {user.first_name} is now inactive')
    return redirect(url_for('add_user'))


@app.route('/edit-user', methods=['GET', 'POST'])
@admin_only
def edit_user():
    menu, categories, sections = menu_create()
    users = db.session.query(User).filter(User.status == "active").all()
    form = AddUserForm()

    user_id = request.args.get("user_id")
    user = db.session.query(User).get(user_id)
    print(user)

    # Set Defaults
    roles = [role[0] for role in db.session.query(Role.name.distinct()).all()]
    form.role.choices = roles

    if form.validate_on_submit():
        updates = 0
        if request.form.get("first_name") != user.first_name:
            user.first_name = request.form.get("first_name").title()
            updates += 1
        if request.form.get("last_name") != user.last_name:
            user.last_name = request.form.get("last_name").title()
            updates += 1
        if request.form.get("email") != user.email:
            user.email = request.form.get("email")
            updates += 1
        if not check_password_hash(user.password, request.form.get("password")):
            user.password = generate_password_hash(request.form.get("password"), method="pbkdf2:sha256", salt_length=8)
            updates += 1
        if request.form.get("role") != user.role.name:
            user.role_id = db.session.query(Role.id).filter(Role.name == request.form.get("role")).first().id
            updates += 1
        if updates > 0:
            db.session.commit()
            flash(f"Success! {user.first_name}'s information has been updated")
        else:
            flash(f"Error: No changes detected")
        return redirect(url_for('add_user'))

    # SET DEFAULTS
    form.first_name.default = user.first_name
    form.last_name.default = user.last_name
    form.email.default = user.email
    form.role.default = user.role.name
    form.process()

    return render_template('add-user.html', form=form, menu=menu, categories=categories, sections=sections, users=users)


@app.route('/add-table', methods=['GET', 'POST'])
@admin_only
def add_table():
    menu, categories, sections = menu_create()
    tables = db.session.query(Table).all()
    form = AddBasicForm()
    if form.validate_on_submit():

        data = form.data
        print(data)
        table_exists = db.session.query(Table).filter(Table.name == data["field"].title()).first()

        if not table_exists:
            new_table = Table(
                name=data["field"].title(),
                status="available"
            )
            db.session.add(new_table)
            db.session.commit()
            flash(f'Success: {new_table.name} added')
            return redirect(url_for('add_table'))
        else:
            flash('ERROR: Table names must be unique')
    return render_template('add-role-table.html', form=form, menu=menu, categories=categories, sections=sections,
                           tables=tables)


@app.route('/remove-table')
@admin_only
def remove_table():
    table_id = request.args.get("table_id")
    table = Table.query.get(table_id)
    orders = db.session.query(Order).filter(Order.table_id == table_id).all()
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
        new_category = Category(
            name=data['category'].upper(),
            status="active"
        )
        db.session.add(new_category)
        db.session.commit()

        category_id = new_category.id

        for x in data:
            if "section" in x and data[x] != "":
                new_section = Section(
                    name=data[x].title(),
                    category_id=category_id,
                    status="active"
                )
                db.session.add(new_section)
                db.session.commit()
        flash(f'Success! {data["category"].upper()} added')
        return redirect(url_for('add_category'))
    return render_template('add-category.html', form=form, menu=menu, categories=categories, sections=sections)


@app.route('/edit-category', methods=['GET', 'POST'])
@admin_only
def edit_category():
    menu, categories, sections = menu_create()
    form = AddCategoryForm()
    category_id = request.args.get("category_id")
    category = db.session.query(Category).get(category_id)
    current_sections = [x.name for x in category.sections]

    if form.validate_on_submit():
        data = form.data
        print(data)

        updated_sections = [data[x].title() for x in data if 'section' in x and data[x] != '']
        print(updated_sections)
        add_sections = [section for section in updated_sections if section not in current_sections]
        remove_sections = [section for section in current_sections if section not in updated_sections]

        updates = 0
        if data['category'].upper() != category.name:
            category.name = data['category'].upper()
            db.session.commit()
            updates += 1
        if len(add_sections) > 0:
            for x in add_sections:
                new_section = Section(
                    name=x.title(),
                    status="active",
                    category_id=category_id
                )
                db.session.add(new_section)
                db.session.commit()
                updates += 1
        if len(remove_sections) > 0:
            for x in remove_sections:
                section = db.session.query(Section).filter(Section.name == x).first()
                section_in_use = db.session.query(MenuItem).filter(MenuItem.section_id == section.id).all()
                if section_in_use:
                    x.status = "inactive"
                else:
                    db.session.delete(section)
                    db.session.commit()
                updates += 1

        if updates > 0:
            flash(f"Success! {section.name} has been updated")
        else:
            flash(f"Error: No changes detected")
        return redirect(url_for('add_category'))

    padding = [""] * (3 - len(current_sections))
    default_values = current_sections + padding
    form.section1.default, form.section2.default, form.section3.default = default_values
    form.category.default = category.name
    form.process()

    return render_template('add-category.html', form=form, menu=menu, categories=categories, sections=sections)


@app.route('/remove-category', methods=['GET', 'POST'])
@admin_only
def remove_category():
    category_id = request.args.get("category_id")
    category = db.session.query(Category).get(category_id)
    category_in_use = db.session.query(MenuItem).filter(MenuItem.category_id == category_id).first()
    if category_in_use:
        category.status = "inactive"
        flash(f"Success: {category.name} is now inactive")
    else:
        sections = db.session.query(Section).filter(Section.category_id == category_id).all()
        for section in sections:
            db.session.delete(section)
        db.session.delete(category)
        flash(f"Success: {category.name} has been deleted")
    db.session.commit()
    return redirect(url_for('add_category'))


@app.route('/update-menu', methods=['GET', 'POST'])
@admin_only
def add_item():
    menu, categories, sections = menu_create()

    category_options = [category[0] for category in db.session.query(Category.name.distinct()).all()]
    section_options = [section[0] for section in db.session.query(Section.name.distinct()).all()]
    form = AddItemForm()
    form.category.choices = category_options
    form.section.choices = section_options
    if form.validate_on_submit():
        data = form.data
        category_id = db.session.query(Category).filter(Category.name == data['category']).first().id
        section_id = db.session.query(Section).filter(Section.name == data['section']).first().id

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
            type_data = data['type' + str(i)]
            var_data = data['variation' + str(i)]
            if type_data != "" and var_data != "":
                new_mod = ItemMod(
                    name=type_data.title(),
                    variations=var_data.title(),
                    item_id=new_item.id,
                    status="active"
                )
                db.session.add(new_mod)
                db.session.commit()
        flash(f'Success! {form.name.data} added to the menu')
        return redirect(url_for('add_item'))
    return render_template('update-menu.html', form=form, menu=menu, categories=categories, sections=sections)


@app.route('/delete/menu_item/<int:item_id>')
@admin_only
def delete_menu_item(item_id):
    item = MenuItem.query.get(item_id)
    ordered_item = db.session.query(OrderItem).filter(OrderItem.item_id == item_id).all()
    if ordered_item:
        item.status = "inactive"
        flash(f"Success: {item.name} is now inactive.")
    else:
        db.session.delete(item)
        flash(f"Success: {item.name} has been deleted.")
    db.session.commit()
    return redirect(url_for('add_item'))


@app.route('/edit-menu', methods=['GET', 'POST'])
@admin_only
def edit_menu_item():
    menu, categories, sections = menu_create()
    item_id = request.args.get('item_id')
    item = db.session.query(MenuItem).get(item_id)

    category_options = [category[0] for category in db.session.query(Category.name.distinct()).all()]
    section_options = [section[0] for section in db.session.query(Section.name.distinct()).all()]
    form = AddItemForm()
    form.category.choices = category_options
    form.section.choices = section_options
    current_mod_types = [modType.name for modType in item.mods]
    current_mod_vars = [modType.variations for modType in item.mods]
    print(current_mod_types)

    if form.validate_on_submit():
        data = form.data
        category_id = db.session.query(Category).filter(Category.name == data['category']).first().id
        section_id = db.session.query(Section).filter(Section.name == data['section']).first().id

        def change(x, y, updates):
            if x != y:
                updates += 1
                print(x)
                return y, updates
            else:
                return x, updates

        updates = 0
        item.name, updates = change(item.name, data['name'], updates)
        item.price, updates = change(int(item.price), int(data['price']), updates)
        item.category_id, updates = change(item.category_id, category_id, updates)
        item.section_id, updates = change(item.section_id, section_id, updates)
        item.description, updates = change(item.description, data['description'], updates)
        db.session.commit()

        updated_mod_types = [data[x].title() for x in data if 'type' in x and data[x] != '']
        updated_mod_vars = [data[x].title() for x in data if 'variation' in x and data[x] != '']

        add_types = [mod_type for mod_type in updated_mod_types if mod_type not in current_mod_types]
        remove_types = [mod_type for mod_type in current_mod_types if mod_type not in updated_mod_types]
        add_vars = [mod_var for mod_var in updated_mod_vars if mod_var not in current_mod_vars]
        remove_vars = [mod_var for mod_var in current_mod_vars if mod_var not in updated_mod_vars]

        if len(add_types) > 0:
            for x in range(len(add_types)):
                new_mod = ItemMod(
                    name=add_types[x],
                    variations=add_vars[x],
                    status="active",
                    item_id=item_id
                )
                print(add_types[x])
                db.session.add(new_mod)
                db.session.commit()
                updates += 1
        if len(remove_types) > 0:
            for x in range(len(remove_types)):
                mod = db.session.query(ItemMod).filter(
                    ItemMod.name == remove_types[x] and ItemMod.item_id == item_id).first()
                mod_in_use = db.session.query(OrderItemMod).filter(OrderItemMod.mod_id == mod.id).first()
                if mod_in_use:
                    mod.status = "inactive"
                else:
                    db.session.delete(mod)
                    db.session.commit()
                updates += 1
                print(remove_types[x])

        if updates > 0:
            flash(f"Success! {item.name} has been updated")
        else:
            flash(f"Error: No changes detected")

        return redirect(url_for('add_item'))

    # Setting default values
    form.name.default = item.name
    form.price.default = item.price
    form.category.default = item.category.name
    form.section.default = item.section.name
    form.description.default = item.description

    padding = [""] * (3 - len(current_mod_types))
    default_types = current_mod_types + padding
    form.type1.default, form.type2.default, form.type3.default = default_types

    default_vars = current_mod_vars + padding
    form.variation1.default, form.variation2.default, form.variation3.default = default_vars
    form.process()

    return render_template('update-menu.html', form=form, menu=menu, categories=categories, sections=sections)


if __name__ == "__main__":
    app.run()
