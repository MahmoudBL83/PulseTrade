from flask import render_template, request, redirect, url_for, jsonify
import ccxt
from flask_login import login_required,current_user
from crypto import app,db, jwt_required
from crypto.models import Exchange,Exchange2, Post, User
from crypto import get_current_user

@app.route('/exchanges')
@jwt_required
def exchanges():
    #exchange = connectExchange()
    current_user = get_current_user()
    exchanges_json = []
    for exchange in Exchange2.query.filter(Exchange2.isActive).all():
        ex = exchange.serialize()
        
        exchangeNow = getattr(ccxt,exchange.exchange)()
        if 'test' in exchangeNow.describe()['urls']:
            test = True
        else:
            test = False
        ex['test'] = test
        exchanges_json.append(ex)

    return render_template("exchanges.html",
                            exchanges2 = exchanges_json,
                            exchanges = current_user.exchanges.all(),
                            current_user=current_user,
                            notifications=current_user.notifications.all(),
                            posts = Post.query.all()
                        )

@app.route('/api/v1/exchanges/')
@jwt_required
def get_exchanges():
    current_user = get_current_user()
    # return all exchanges of user by its id as api from outside the flask app
    return jsonify([exchange.serialize() for exchange in current_user.exchanges.all()])

# Define an endpoint to connect to an exchange
@app.route('/api/v1/connect/', methods=['POST'])
def connect_exchange():
    current_user = get_current_user()
    # Parse the API key and secret from the request body
    api_key = request.json['api_key']
    secret_key = request.json['api_secret']
    exchange_name = request.json['exchange_name']
    password = request.json['password']
    demo = request.json['demo']
    exchange = None

    if exchange_name not in ccxt.exchanges:
        return jsonify({'status': 'error', 'message': f'Unsupported exchange: {exchange_name}'})

    #check if user has linked an exchange before with the same name
    if current_user.exchanges.filter(Exchange.name==exchange_name).first():
        return jsonify({
            'status': 'error',
            'message': f'You have already linked {exchange_name} API',
        })
    else:
        # Initialize the exchange API client with the provided credentials
        _opts = {'timeout': 10000, 'enableRateLimit': True}
        if password:
            exchange = getattr(ccxt, exchange_name)({
                'apiKey': api_key,
                'secret': secret_key,
                'password':password,
                **_opts,
            })
        else:
            exchange = getattr(ccxt, exchange_name)({
                'apiKey': api_key,
                'secret': secret_key,
                **_opts,
            })
        if demo:
            exchange.set_sandbox_mode(True)

        try:
            exchange.load_markets()
            exchange.fetch_balance()
            
            activeExchange = Exchange(api_key=api_key,api_secret=secret_key,name=exchange_name,password=password,demo=demo,isActive=True)
            activeExchange.set_creds(api_key,secret_key,password)

            if len(current_user.exchanges.filter(Exchange.isActive==True).all())==0:
                activeExchange.isActive = True

            db.session.add(activeExchange)
            current_user.exchanges.append(activeExchange)
            current_user.exchange = exchange_name
            db.session.commit()
            exchanges = current_user.exchanges.all()
            for exchange in exchanges:
                exchange.isActive = False

            current_user.exchanges.filter_by(name=exchange_name).first().isActive = True
            current_user.exchange = exchange_name
            db.session.commit()
            return jsonify({
                'status': 'success',
                'message': f'Connected to {exchange_name} API',
                'ok': True,
            })
        except ccxt.AuthenticationError:
            return jsonify({
                'status': 'error',
                'message': 'Invalid API credentials',
            })
        except ccxt.ExchangeError:
            return jsonify({
                'status': 'error',
                'message': f'Failed to connect to {exchange_name} API',
            })

        except ccxt.NetworkError as network_error:
            return jsonify({
                'status': 'error',
                'message': 'Network error occurred',
            })
        except ccxt.RequestTimeout as timeout_error:
            return jsonify({
                'status': 'error',
                'message': 'Request timeout',
            })
        except ccxt.ExchangeNotAvailable as unavailable_error:
            return jsonify({
                'status': 'error',
                'message': 'Exchange not available',
            })
        except Exception as e:
            return jsonify({
                'status': 'error',
                'message': 'An unexpected error occurred',
            })
    

# Define an endpoint to disconnect from an exchange
@app.route('/api/v1/disconnect/', methods=['POST'])
def disconnect_exchange():
    current_user = get_current_user()
    exchange_name = request.json['exchange_name']
    db.session.delete(current_user.exchanges.filter(Exchange.name==exchange_name).first())
    db.session.commit()
    return jsonify({
        'status': 'success',
        'message': f'discineected from {exchange_name} API',
    })

# Define an endpoint to get the user's connected exchanges
@app.route('/api/v1/fav_exchange/', methods=['POST'])
def fav_exchange():
    current_user = get_current_user()
    exchange_name = request.json['exchange_name']
    exchanges = current_user.exchanges.all()
    for exchange in exchanges:
        exchange.isActive = False

    current_user.exchanges.filter_by(name=exchange_name).first().isActive = True
    current_user.exchange = exchange_name
    db.session.commit()
    return jsonify({
        'status': 'success',
        'message': f'{exchange_name} is now your favorite exchange',
    })

def connectExchange(exchange_name=None,id=None):
    if id:
        current_user2 = User.query.get(id)
    else:
        current_user2 = current_user
    if exchange_name is None:
        if current_user2.exchanges.filter(Exchange.isActive==True).first():
            exchange_name = current_user2.exchanges.filter(Exchange.isActive==True).first().name
        else:
            return redirect(url_for('exchanges'))
    api_key,api_secret,password = current_user2.exchanges.filter(Exchange.name==exchange_name).first().get_creds()
    if current_user2.exchanges.filter(Exchange.name==exchange_name).first().password:
        exchange = getattr(ccxt, exchange_name)({
            'apiKey': api_key,
            'secret': api_secret,
            'password': password,
        })
    else:
        exchange = getattr(ccxt, exchange_name)({
            'apiKey': api_key,
            'secret': api_secret,
        })

    if current_user2.exchanges.filter(Exchange.name==exchange_name).first().demo:
            exchange.set_sandbox_mode(True)
    
    return exchange

#demo mode 
@app.route('/api/v1/demo/', methods=['POST'])
def demo():
    current_user = get_current_user()
    message = 'You are now in demo mode' if request.json['demo'] else 'You are now in live mode'
    current_user.demo = request.json['demo']
    db.session.commit()
    return jsonify({
        'status': 'success',
        'message': message,
    })
