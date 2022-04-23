from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import relationship
from flask_login import UserMixin

db = SQLAlchemy()

# ---------------------------------------------------------------------------------------------------------------------
#  CONFIGURE DATABASE TABLES
# ---------------------------------------------------------------------------------------------------------------------
item__mod = db.Table(
    'item__mod',
    db.Column('item_id', db.Integer, db.ForeignKey('item.id'), primary_key=True),
    db.Column('mod_id', db.Integer, db.ForeignKey('mod.id'), primary_key=True)
)

mod__var = db.Table(
    'mod__var',
    db.Column('mod_id', db.Integer, db.ForeignKey('mod.id'), primary_key=True),
    db.Column('var_id', db.Integer, db.ForeignKey('var.id'), primary_key=True)
)

order_item__var = db.Table(
    'order_item__var',
    db.Column('order_item_id', db.Integer, db.ForeignKey('order_item.id'), primary_key=True),
    db.Column('var_id', db.Integer, db.ForeignKey('var.id'), primary_key=True)
)


class User(UserMixin, db.Model):
    """
    status options: active, inactive
    """
    __tablename__ = "user"
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(250), nullable=False)
    status = db.Column(db.String(50), nullable=False)
    role_id = db.Column(db.Integer, db.ForeignKey("role.id"))
    role = relationship("Role", back_populates="users")
    orders = relationship("Order", back_populates="user")


class MenuItem(db.Model):
    """
    status options: active, inactive
    """
    __tablename__ = "item"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(30), nullable=False, unique=True)
    price = db.Column(db.Integer, nullable=False)
    description = db.Column(db.String(120), nullable=True)
    status = db.Column(db.String(50), nullable=False)
    mods = relationship("ItemMod", secondary=item__mod, back_populates="items")
    category_id = db.Column(db.Integer, db.ForeignKey("category.id"))
    category = relationship("Category", back_populates="items")
    section_id = db.Column(db.Integer, db.ForeignKey("section.id"))
    section = relationship("Section", back_populates="items")
    order_items = relationship("OrderItem", back_populates="item")


class ItemMod(db.Model):
    """
    basically a label for a package of vars
    """
    __tablename__ = "mod"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(30), nullable=False)
    items = relationship("MenuItem", secondary=item__mod, back_populates="mods")
    vars = relationship("ItemModVar", secondary=mod__var, back_populates="mods")


class ItemModVar(db.Model):
    __tablename__ = "var"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(30), nullable=False, unique=True)
    mods = relationship("ItemMod", secondary=mod__var, back_populates="vars")
    order_items = relationship("OrderItem", secondary=order_item__var, back_populates="vars")


class Category(db.Model):
    __tablename__ = "category"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(30), nullable=False, unique=True)
    items = relationship("MenuItem", back_populates="category")
    sections = relationship("Section", back_populates="category")


class Section(db.Model):
    __tablename__ = "section"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    items = relationship("MenuItem", back_populates="section")
    category_id = db.Column(db.Integer, db.ForeignKey("category.id"))
    category = relationship("Category", back_populates="sections")


class Role(db.Model):
    __tablename__ = "role"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False, unique=True)
    users = relationship("User", back_populates="role")


class Table(db.Model):
    """
    status options: available, unavailable, inactive
    """
    __tablename__ = "table"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False, unique=True)
    orders = relationship("Order", back_populates="table")
    status = db.Column(db.String(50), nullable=False)


class Order(db.Model):
    """
    status options: started, cancelled, submitted, closed
    """
    __tablename__ = "order"
    id = db.Column(db.Integer, primary_key=True)
    customer_name = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.String(100), nullable=False)
    submitted_at = db.Column(db.String(100))
    closed_at = db.Column(db.String(100))
    table = relationship("Table", back_populates="orders")
    table_id = db.Column(db.Integer, db.ForeignKey("table.id"))
    order_items = relationship("OrderItem", back_populates="order")
    user = relationship("User", back_populates="orders")
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))


# Created because of Many-to-Many Relationship between Order and Items
class OrderItem(db.Model):
    __tablename__ = "order_item"
    id = db.Column(db.Integer, primary_key=True)
    quantity = db.Column(db.Integer, nullable=False)
    notes = db.Column(db.String(200))
    subtotal = db.Column(db.Float, nullable=False)
    item = relationship("MenuItem", back_populates="order_items")
    item_id = db.Column(db.Integer, db.ForeignKey("item.id"))
    order = relationship("Order", back_populates="order_items")
    order_id = db.Column(db.Integer, db.ForeignKey("order.id"))
    vars = relationship("ItemModVar", secondary=order_item__var, back_populates="order_items")
