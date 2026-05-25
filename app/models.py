from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    expiry_date = db.Column(db.DateTime, nullable=False)
    
    # 提醒类型
    remind_type = db.Column(db.String(20), default='expiry')   # expiry / custom
    repeat_every = db.Column(db.Integer, default=1)
    repeat_unit = db.Column(db.String(10), default='day')     # day / week / month
    
    # 到期提醒标记
    notified_30d = db.Column(db.Boolean, default=False)
    notified_15d = db.Column(db.Boolean, default=False)
    notified_7d = db.Column(db.Boolean, default=False)
    notified_1d = db.Column(db.Boolean, default=False)
    
    # 自定义周期最后提醒时间
    last_notified = db.Column(db.DateTime, nullable=True)

    def __repr__(self):
        return f'<Project {self.name}>'
