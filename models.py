import time
import json
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Project(db.Model):
  __tablename__ = 'projects'

  id = db.Column(db.Integer, primary_key=True)
  name = db.Column(db.String(100), nullable=False, default="Smart Home Project")
  domain_type = db.Column(db.String(50), default="smarthome")
  background_image = db.Column(
      db.String(255), default="/static/images/denah_rumah.png"
  )
  canvas_width = db.Column(db.Integer, default=800)
  canvas_height = db.Column(db.Integer, default=600)
  generated_json = db.Column(db.Text, nullable=True)
  updated_at = db.Column(db.Integer, default=lambda: int(time.time()))

  controllers = db.relationship(
      'ControllerBoard',
      backref='project',
      lazy=True,
      cascade="all, delete-orphan",
  )
  widgets = db.relationship(
      'WidgetNode', backref='project', lazy=True, cascade="all, delete-orphan"
  )


class ControllerBoard(db.Model):
  __tablename__ = 'controller_boards'

  id = db.Column(db.Integer, primary_key=True)
  project_id = db.Column(
      db.Integer, db.ForeignKey('projects.id'), nullable=False
  )
  board_name = db.Column(db.String(50), default="ESP32-WROOM-32")
  device_id = db.Column(db.String(50), default="panel01")

  function_blocks = db.relationship(
      'FunctionBlock', backref='board', lazy=True, cascade="all, delete-orphan"
  )


class FunctionBlock(db.Model):
  __tablename__ = 'function_blocks'

  id = db.Column(db.Integer, primary_key=True)
  board_id = db.Column(
      db.Integer, db.ForeignKey('controller_boards.id'), nullable=False
  )
  fb_identifier = db.Column(db.String(50), nullable=False)
  module_type = db.Column(db.String(50), default="RELAY_8CH")
  total_channels = db.Column(db.Integer, default=8)

  mappings = db.relationship(
      'IOMapping',
      backref='function_block',
      lazy=True,
      cascade="all, delete-orphan",
  )


class WidgetNode(db.Model):
  __tablename__ = 'widget_nodes'

  id = db.Column(db.Integer, primary_key=True)
  project_id = db.Column(
      db.Integer, db.ForeignKey('projects.id'), nullable=False
  )
  widget_id = db.Column(db.String(50), nullable=False)
  label_name = db.Column(db.String(50), nullable=False)
  zone_name = db.Column(db.String(50), nullable=False, default='Area Umum')
  widget_type = db.Column(db.String(50), default="LAMP_INDICATOR")
  pos_x = db.Column(db.Float, default=50.0)
  pos_y = db.Column(db.Float, default=50.0)

  mapping = db.relationship(
      'IOMapping',
      backref='widget',
      uselist=False,
      cascade="all, delete-orphan",
  )


class IOMapping(db.Model):
  __tablename__ = 'io_mappings'

  id = db.Column(db.Integer, primary_key=True)
  widget_id = db.Column(
      db.Integer, db.ForeignKey('widget_nodes.id'), nullable=False
  )
  fb_id = db.Column(
      db.Integer, db.ForeignKey('function_blocks.id'), nullable=False
  )
  channel_index = db.Column(db.Integer, nullable=False)
  gpio_pin = db.Column(db.Integer, nullable=False)
  array_order = db.Column(db.Integer, nullable=False)