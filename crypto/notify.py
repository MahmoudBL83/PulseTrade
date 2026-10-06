from threading import Thread
from crypto import app,db,celery
from crypto.models import Notification,Exchange,User
from flask_login import current_user
from flask import jsonify
from crypto import socketio
from datetime import datetime,timezone
import ccxt,json
import time

@socketio.on('connect')
def handle_connect():
    print('Client connected')


@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')

@socketio.on('notification')
def handle_notification(message):
    print('Notification received:', message)

def send_notification(message,id=None,exchange=None):
    with app.app_context():
        try:
            print('Sending notification:', message)
            if id is None:
                current_user2 = current_user
            else:
                current_user2 = User.query.filter_by(id=id).first()
            socketio.emit('new_notification', str(id if id else current_user.id)+"***"+message+'***'+datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')+f"***{(current_user2.exchange if exchange is None else exchange)}")
            message_sep = message.split("***")
            if len(message_sep) == 1:
                notification = Notification(content=message_sep[0],type="",date=datetime.now(timezone.utc),exchange=((current_user2.exchange if exchange is None else exchange) if message_sep[1]!='system' else None))
            else:
                notification = Notification(content=message_sep[0],type=message_sep[1],date=datetime.now(timezone.utc),exchange=((current_user2.exchange if exchange is None else exchange) if message_sep[1]!='system' else None))
            db.session.add(notification)
            current_user2.notifications.append(notification)
            db.session.commit()
        except Exception as e:
            print(e)

@app.route('/api/v1/read_notifications/')
def read_notifications():
    with app.app_context():
        current_user.notifications.filter(Notification.read==False).update({Notification.read: True})
        db.session.commit()

@app.route('/api/v1/get_notifications/')
def get_notifications():
    with app.app_context():
        notifications = current_user.notifications.order_by(Notification.date.desc()).all()
        return jsonify([notification.serialize() for notification in notifications])
    
@app.route('/api/v1/get_notifications_count/')
def get_notifications_count():
    with app.app_context():
        notifications_count = current_user.notifications.filter(Notification.read==False).count()
        return jsonify(notifications_count)

@celery.task
def monitor_orders():
    while True:
        time.sleep(1)
        with app.app_context():
            for current_user in User.query.all():
                exchange_name = current_user.exchanges.filter(Exchange.isActive==True).first().name
                if current_user.exchanges.filter(Exchange.name==exchange_name).first().password:
                    exchange = getattr(ccxt, exchange_name)({
                        'apiKey': current_user.exchanges.filter(Exchange.name==exchange_name).first().api_key,
                        'secret': current_user.exchanges.filter(Exchange.name==exchange_name).first().api_secret,
                        'password': current_user.exchanges.filter(Exchange.name==exchange_name).first().password,
                    })
                else:
                    exchange = getattr(ccxt, exchange_name)({
                        'apiKey': current_user.exchanges.filter(Exchange.name==exchange_name).first().api_key,
                        'secret': current_user.exchanges.filter(Exchange.name==exchange_name).first().api_secret,
                    })

                if current_user.exchanges.filter(Exchange.name==exchange_name).first().demo:
                    exchange.set_sandbox_mode(True)

                open_orders = json.loads(current_user.open_orders)

                for id in open_orders:
                    # Check if the order is closed
                    try:
                        order = exchange.fetch_order(id[0],symbol=id[1])
                        print(order)
                        if order['status'] == 'filled':
                            message = f"Order closed: {order['symbol']}"
                            # Send a notification to all connected clients
                            send_notification(f"the {id[2]} order with id {id[0]} for ${id[1]} has been filled" )
                            # Remove the order from the open orders list
                            open_orders.remove(id)
                            current_user.remove_from_open_orders([id[0],id[1],id[2]])
                            db.session.commit()
                    except:
                        pass