from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import relationship
from flask_login import UserMixin

db = SQLAlchemy()


# CONFIGURE DATABASE TABLES ###########################################################################################
class User(UserMixin, db.Model):
    __tablename__ = "user"
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(25), nullable=False)
    last_name = db.Column(db.String(25), nullable=False)
    email = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(50), nullable=False)
    role_id = db.Column(db.Integer, db.ForeignKey("role.id"))
    role = relationship("Role", back_populates="users")
    orders = relationship("Order", back_populates="user")


class MenuItem(db.Model):
    __tablename__ = "item"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(30), nullable=False, unique=True)
    price = db.Column(db.Integer, nullable=False)
    description = db.Column(db.String(120), nullable=True)
    mods = relationship("ItemMod", back_populates="item")
    category_id = db.Column(db.Integer, db.ForeignKey("category.id"))
    category = relationship("Category", back_populates="items")
    section_id = db.Column(db.Integer, db.ForeignKey("section.id"))
    section = relationship("Section", back_populates="items")
    order_items = relationship("OrderItem", back_populates="item")
    status = db.Column(db.String(50), nullable=False)


class ItemMod(db.Model):
    __tablename__ = "modification"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(30), nullable=False)
    variations = db.Column(db.String(200), nullable=False)
    item_id = db.Column(db.Integer, db.ForeignKey("item.id"))
    item = relationship("MenuItem", back_populates="mods")
    order_item_mods = relationship("OrderItemMod", back_populates="mod")
    status = db.Column(db.String(50), nullable=False)


class Category(db.Model):
    __tablename__ = "category"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(30), nullable=False)
    items = relationship("MenuItem", back_populates="category")
    sections = relationship("Section", back_populates="category")
    status = db.Column(db.String(50), nullable=False)


class Section(db.Model):
    __tablename__ = "section"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    items = relationship("MenuItem", back_populates="section")
    category_id = db.Column(db.Integer, db.ForeignKey("category.id"))
    category = relationship("Category", back_populates="sections")
    status = db.Column(db.String(50), nullable=False)


class Role(db.Model):
    __tablename__ = "role"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    users = relationship("User", back_populates="role")


class Table(db.Model):
    __tablename__ = "table"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False, unique=True)
    orders = relationship("Order", back_populates="table")
    status = db.Column(db.String(50), nullable=False)


class Order(db.Model):
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
    order_item_mods = relationship("OrderItemMod", back_populates="order_item")
    item = relationship("MenuItem", back_populates="order_items")
    item_id = db.Column(db.Integer, db.ForeignKey("item.id"))
    order = relationship("Order", back_populates="order_items")
    order_id = db.Column(db.Integer, db.ForeignKey("order.id"))


# Created because of Many-to-Many Relationship between OrderItem and Mods
class OrderItemMod(db.Model):
    __tablename__ = "order_item_mods"
    id = db.Column(db.Integer, primary_key=True)
    chosen_var = db.Column(db.String(200), nullable=False)
    order_item = relationship("OrderItem", back_populates="order_item_mods")
    order_item_id = db.Column(db.Integer, db.ForeignKey("order_item.id"))
    mod = relationship("ItemMod", back_populates="order_item_mods")
    mod_id = db.Column(db.Integer, db.ForeignKey("modification.id"))
