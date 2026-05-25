from flask import Flask, render_template, request, jsonify
from models import db, Project
from datetime import datetime
import requests
import threading
import time
import hmac
import hashlib
import base64
import urllib.parse

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///data/projects.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

DINGTALK_TOKEN = None
DINGTALK_SECRET = None

# ==================== 路由 ====================
@app.route('/')
def index():
    projects = Project.query.all()
    return render_template('index.html', projects=projects, now=datetime.now())

@app.route('/add', methods=['POST'])
def add_project():
    name = request.form.get('name')
    expiry_str = request.form.get('expiry_date')
    remind_type = request.form.get('remind_type', 'expiry')
    
    try:
        expiry_date = datetime.strptime(expiry_str, '%Y-%m-%dT%H:%M')
        project = Project(name=name, expiry_date=expiry_date, remind_type=remind_type)
        
        if remind_type in ['weekly', 'monthly', 'yearly', 'custom']:
            if remind_type == 'custom':
                project.repeat_every = int(request.form.get('repeat_every', 1))
                project.repeat_unit = request.form.get('repeat_unit', 'day')
            elif remind_type == 'weekly':
                project.repeat_every = 1; project.repeat_unit = 'week'
            elif remind_type == 'monthly':
                project.repeat_every = 1; project.repeat_unit = 'month'
            elif remind_type == 'yearly':
                project.repeat_every = 1; project.repeat_unit = 'month'
        
        db.session.add(project)
        db.session.commit()
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'error', 'msg': str(e)}), 400


@app.route('/edit/<int:id>', methods=['POST'])
def edit_project(id):
    project = Project.query.get(id)
    if not project:
        return jsonify({'status': 'error'}), 404
    
    try:
        project.name = request.form.get('name')
        project.expiry_date = datetime.strptime(request.form.get('expiry_date'), '%Y-%m-%dT%H:%M')
        project.remind_type = request.form.get('remind_type')
        
        project.notified_30d = project.notified_20d = project.notified_10d = False
        project.notified_7d = project.notified_3d = project.notified_2d = project.notified_1d = False
        project.last_notified = None
        
        if project.remind_type in ['weekly', 'monthly', 'yearly', 'custom']:
            if project.remind_type == 'custom':
                project.repeat_every = int(request.form.get('repeat_every', 1))
                project.repeat_unit = request.form.get('repeat_unit', 'day')
            elif project.remind_type == 'weekly':
                project.repeat_every = 1; project.repeat_unit = 'week'
            elif project.remind_type == 'monthly':
                project.repeat_every = 1; project.repeat_unit = 'month'
            elif project.remind_type == 'yearly':
                project.repeat_every = 1; project.repeat_unit = 'month'
        
        db.session.commit()
        return jsonify({'status': 'success'})
    except:
        return jsonify({'status': 'error'}), 400


@app.route('/delete/<int:id>', methods=['POST'])
def delete_project(id):
    project = Project.query.get(id)
    if project:
        db.session.delete(project)
        db.session.commit()
        return jsonify({'status': 'success'})
    return jsonify({'status': 'error'}), 404


# 新增：单个项目测试发送
@app.route('/test_project/<int:id>', methods=['POST'])
def test_project(id):
    project = Project.query.get(id)
    if not project:
        return jsonify({'status': 'error', 'msg': '项目不存在'}), 404
    
    now = datetime.now()
    days_left = (project.expiry_date - now).days
    
    message = f"**🧪 项目测试提醒**\n\n**项目名称**：{project.name}\n**到期时间**：{project.expiry_date.strftime('%Y-%m-%d %H:%M')}\n**剩余天数**：{days_left} 天"
    
    success = send_dingtalk(message)
    if success:
        return jsonify({'status': 'success', 'msg': '测试消息已发送'})
    else:
        return jsonify({'status': 'error', 'msg': '发送失败，请检查钉钉配置'}), 400


@app.route('/get_project/<int:id>', methods=['GET'])
def get_project(id):
    project = Project.query.get(id)
    if project:
        return jsonify({
            'name': project.name,
            'expiry_date': project.expiry_date.strftime('%Y-%m-%dT%H:%M'),
            'remind_type': project.remind_type,
            'repeat_every': project.repeat_every,
            'repeat_unit': project.repeat_unit
        })
    return jsonify({'error': 'not found'}), 404


@app.route('/config', methods=['POST'])
def save_config():
    global DINGTALK_TOKEN, DINGTALK_SECRET
    DINGTALK_TOKEN = request.form.get('token')
    DINGTALK_SECRET = request.form.get('secret')
    return jsonify({'status': 'success'})


@app.route('/test_dingtalk', methods=['POST'])
def test_dingtalk():
    success = send_dingtalk("✅ 全局测试消息：钉钉机器人连接正常！")
    return jsonify({'status': 'success' if success else 'error'})


def send_dingtalk(message):
    global DINGTALK_TOKEN, DINGTALK_SECRET
    if not DINGTALK_TOKEN or not DINGTALK_SECRET:
        return False
    try:
        timestamp = str(round(time.time() * 1000))
        secret_enc = DINGTALK_SECRET.encode('utf-8')
        string_to_sign = f'{timestamp}\n{DINGTALK_SECRET}'
        hmac_code = hmac.new(secret_enc, string_to_sign.encode('utf-8'), digestmod=hashlib.sha256).digest()
        sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
        
        webhook = f"https://oapi.dingtalk.com/robot/send?access_token={DINGTALK_TOKEN}&timestamp={timestamp}&sign={sign}"
        data = {"msgtype": "markdown", "markdown": {"title": "项目提醒", "text": message}}
        resp = requests.post(webhook, json=data, timeout=10)
        return resp.json().get('errcode') == 0
    except:
        return False


# ==================== 定时任务 ====================
def check_expirations():
    with app.app_context():
        now = datetime.now()
        projects = Project.query.all()
        
        for p in projects:
            if p.remind_type == 'expiry':
                days_left = (p.expiry_date - now).days
                if 20 < days_left <= 30 and not p.notified_30d:
                    send_dingtalk(f"**⚠️ 项目即将到期**\n\n**项目**：{p.name}\n**到期**：{p.expiry_date.strftime('%Y-%m-%d %H:%M')}\n**剩余**：{days_left}天"); p.notified_30d = True
                elif 10 < days_left <= 20 and not p.notified_20d:
                    send_dingtalk(f"**⚠️ 项目即将到期**\n\n**项目**：{p.name}\n**到期**：{p.expiry_date.strftime('%Y-%m-%d %H:%M')}\n**剩余**：{days_left}天"); p.notified_20d = True
                elif 7 < days_left <= 10 and not p.notified_10d:
                    send_dingtalk(f"**⚠️ 项目即将到期**\n\n**项目**：{p.name}\n**到期**：{p.expiry_date.strftime('%Y-%m-%d %H:%M')}\n**剩余**：{days_left}天"); p.notified_10d = True
                elif 3 < days_left <= 7 and not p.notified_7d:
                    send_dingtalk(f"**🔴 项目即将到期**\n\n**项目**：{p.name}\n**到期**：{p.expiry_date.strftime('%Y-%m-%d %H:%M')}\n**剩余**：{days_left}天"); p.notified_7d = True
                elif 2 < days_left <= 3 and not p.notified_3d:
                    send_dingtalk(f"**🔴 项目即将到期**\n\n**项目**：{p.name}\n**到期**：{p.expiry_date.strftime('%Y-%m-%d %H:%M')}\n**剩余**：{days_left}天"); p.notified_3d = True
                elif 1 < days_left <= 2 and not p.notified_2d:
                    send_dingtalk(f"**🚨 项目即将到期**\n\n**项目**：{p.name}\n**到期**：{p.expiry_date.strftime('%Y-%m-%d %H:%M')}\n**剩余**：{days_left}天"); p.notified_2d = True
                elif 0 <= days_left <= 1 and not p.notified_1d:
                    send_dingtalk(f"**🚨 项目即将到期！**\n\n**项目**：{p.name}\n**到期**：{p.expiry_date.strftime('%Y-%m-%d %H:%M')}\n**剩余**：{days_left}天"); p.notified_1d = True

            else:
                should_notify = False
                if p.last_notified is None:
                    should_notify = True
                else:
                    delta = now - p.last_notified
                    if p.repeat_unit == 'day' and delta.days >= p.repeat_every:
                        should_notify = True
                    elif p.repeat_unit == 'week' and delta.days >= p.repeat_every * 7:
                        should_notify = True
                    elif p.repeat_unit == 'month':
                        months = (now.year - p.last_notified.year)*12 + (now.month - p.last_notified.month)
                        if months >= p.repeat_every:
                            should_notify = True
                
                if should_notify:
                    send_dingtalk(f"**🔄 周期提醒**\n\n**项目**：{p.name}\n**时间**：{now.strftime('%Y-%m-%d %H:%M')}")
                    p.last_notified = now

        db.session.commit()

def scheduler():
    while True:
        check_expirations()
        time.sleep(1800)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    threading.Thread(target=scheduler, daemon=True).start()
    app.run(host='0.0.0.0', port=5000)
