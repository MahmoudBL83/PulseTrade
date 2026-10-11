import logging

from flask import render_template, request, redirect, url_for, jsonify
import ccxt
from crypto import app,db, jwt_required, auth_required
from crypto.models import Exchange,Exchange2, Post, User, Notification, PAPER_EXCHANGE
from crypto import get_current_user
from crypto.functions import connectExchange, build_exchange, CCXT_OPTIONS  # noqa: F401 (re-exported)

log = logging.getLogger("pulsetrade.exchanges")


def nav_context(user):
    """Context every legacy dashboard page needs for its header/sidebar.
    Notifications and posts are capped so pages stay fast for old accounts."""
    notes = user.notifications.order_by(Notification.id.desc()).limit(50).all()[::-1]
    return {
        "exchanges": user.exchanges.all(),
        "current_user": user,
        "notifications": notes,
        "posts": Post.query.order_by(Post.created_at.desc()).limit(8).all()[::-1],
    }


_TEST_URL_CACHE = {}


def _has_testnet(name):
    if name not in _TEST_URL_CACHE:
        try:
            _TEST_URL_CACHE[name] = 'test' in getattr(ccxt, name)().describe()['urls']
        except Exception:
            _TEST_URL_CACHE[name] = False
    return _TEST_URL_CACHE[name]


@app.route('/exchanges')
@jwt_required
def exchanges():
    current_user = get_current_user()
    exchanges_json = []
    for exchange in Exchange2.query.filter(Exchange2.isActive).all():
        if exchange.exchange not in ccxt.exchanges:
            continue
        ex = exchange.serialize()
        ex['test'] = _has_testnet(exchange.exchange)
        exchanges_json.append(ex)

    return render_template("exchanges.html",
                            exchanges2 = exchanges_json,
                            **nav_context(current_user),
                        )

@app.route('/api/v1/exchanges/')
@jwt_required
def get_exchanges():
    current_user = get_current_user()
    # return all exchanges of user by its id as api from outside the flask app
    return jsonify([exchange.serialize() for exchange in current_user.exchanges.all()])


def _activate(user, exchange_name):
    for exchange in user.exchanges.all():
        exchange.isActive = exchange.name == exchange_name
    user.exchange = exchange_name


def connect_paper(user):
    """Attach the simulated paper exchange to ``user`` (idempotent)."""
    row = user.exchanges.filter(Exchange.name == PAPER_EXCHANGE).first()
    if row is None:
        row = Exchange(name=PAPER_EXCHANGE, demo=False, isActive=True, owner_id=user.id)
        row.set_creds(None, None, None)
        db.session.add(row)
        from crypto.paper import get_account
        get_account(user.id)
    _activate(user, PAPER_EXCHANGE)
    db.session.commit()
    return row


# Define an endpoint to connect to an exchange
@app.route('/api/v1/connect/', methods=['POST'])
@auth_required
def connect_exchange():
    current_user = get_current_user()
    body = request.get_json(silent=True) or {}
    exchange_name = str(body.get('exchange_name') or '').strip()
    if exchange_name == PAPER_EXCHANGE:
        connect_paper(current_user)
        return jsonify({'status': 'success', 'message': 'Paper trading account connected', 'ok': True})

    api_key = str(body.get('api_key') or '').strip()
    secret_key = str(body.get('api_secret') or '').strip()
    password = str(body.get('password') or '').strip()
    demo = bool(body.get('demo'))

    if exchange_name not in ccxt.exchanges:
        return jsonify({'status': 'error', 'message': f'Unsupported exchange: {exchange_name}'}), 400
    if not api_key or not secret_key:
        return jsonify({'status': 'error', 'message': 'API key and secret are required'}), 400

    #check if user has linked an exchange before with the same name
    if current_user.exchanges.filter(Exchange.name==exchange_name).first():
        return jsonify({
            'status': 'error',
            'message': f'You have already linked {exchange_name} API',
        })

    # Initialize the exchange API client with the provided credentials
    opts = {'apiKey': api_key, 'secret': secret_key, **CCXT_OPTIONS}
    if password:
        opts['password'] = password
    exchange = getattr(ccxt, exchange_name)(opts)
    if demo:
        try:
            exchange.set_sandbox_mode(True)
        except Exception:
            return jsonify({'status': 'error', 'message': f'{exchange_name} has no testnet'}), 400

    try:
        exchange.load_markets()
        exchange.fetch_balance()

        activeExchange = Exchange(name=exchange_name,demo=demo,isActive=True)
        activeExchange.set_creds(api_key,secret_key,password)
        db.session.add(activeExchange)
        current_user.exchanges.append(activeExchange)
        db.session.flush()
        _activate(current_user, exchange_name)
        db.session.commit()
        return jsonify({
            'status': 'success',
            'message': f'Connected to {exchange_name} API',
            'ok': True,
        })
    except ccxt.AuthenticationError:
        return jsonify({'status': 'error', 'ok': False, 'code': 'authentication_failed',
                        'message': 'Binance rejected the API key. Check the key, secret, account permissions, testnet setting, and any IP allowlist.'
                        if exchange_name == 'binance' else 'The exchange rejected the API credentials.'}), 401
    except ccxt.RequestTimeout:
        return jsonify({'status': 'error', 'ok': False, 'code': 'exchange_timeout',
                        'message': f'{exchange_name} did not respond in time. Please retry.'}), 504
    except ccxt.ExchangeNotAvailable as e:
        detail = str(e).lower()
        if 'restricted location' in detail or ' 451' in detail:
            log.warning('%s rejected the server region (HTTP 451) during connection', exchange_name)
            return jsonify({'status': 'error', 'ok': False, 'code': 'exchange_region_restricted',
                            'message': f'{exchange_name} rejected this server location (HTTP 451). The request comes from the hosting server, not your browser. Use a supported deployment region or contact the exchange.'}), 503
        log.warning('%s unavailable during connection: %s', exchange_name, type(e).__name__)
        return jsonify({'status': 'error', 'ok': False, 'code': 'exchange_unavailable',
                        'message': f'{exchange_name} is temporarily unreachable from this server. Please retry later.'}), 503
    except ccxt.NetworkError:
        return jsonify({'status': 'error', 'ok': False, 'code': 'exchange_network_error',
                        'message': f'This server could not reach {exchange_name}. Please retry later.'}), 502
    except ccxt.ExchangeError:
        return jsonify({'status': 'error', 'ok': False, 'code': 'exchange_error',
                        'message': f'{exchange_name} rejected the connection. Check account permissions and the production/testnet setting.'}), 502
    except RuntimeError as e:  # FERNET_KEY missing
        return jsonify({'status': 'error', 'message': str(e)}), 500
    except Exception:
        log.exception('unexpected connection failure for %s', exchange_name)
        return jsonify({'status': 'error', 'ok': False, 'code': 'connection_error',
                        'message': 'An unexpected error occurred'}), 500


# Define an endpoint to disconnect from an exchange
@app.route('/api/v1/disconnect/', methods=['POST'])
@auth_required
def disconnect_exchange():
    current_user = get_current_user()
    exchange_name = (request.get_json(silent=True) or {}).get('exchange_name')
    row = current_user.exchanges.filter(Exchange.name==exchange_name).first()
    if row is None:
        return jsonify({'status': 'error', 'message': f'{exchange_name} is not connected', 'ok': False}), 404
    was_active = row.isActive
    db.session.delete(row)
    db.session.flush()
    if was_active:
        nxt = current_user.exchanges.first()
        if nxt is not None:
            _activate(current_user, nxt.name)
        else:
            current_user.exchange = None
    db.session.commit()
    return jsonify({
        'status': 'success',
        'message': f'disconnected from {exchange_name} API',
        'ok': True,
    })

# Define an endpoint to get the user's connected exchanges
@app.route('/api/v1/fav_exchange/', methods=['POST'])
@auth_required
def fav_exchange():
    current_user = get_current_user()
    exchange_name = (request.get_json(silent=True) or {}).get('exchange_name')
    if current_user.exchanges.filter_by(name=exchange_name).first() is None:
        return jsonify({'status': 'error', 'message': f'{exchange_name} is not connected', 'ok': False}), 404
    _activate(current_user, exchange_name)
    db.session.commit()
    return jsonify({
        'status': 'success',
        'message': f'{exchange_name} is now your favorite exchange',
        'ok': True,
    })

#demo mode
@app.route('/api/v1/demo/', methods=['POST'])
@auth_required
def demo():
    current_user = get_current_user()
    enabled = bool((request.get_json(silent=True) or {}).get('demo'))
    message = 'You are now in demo mode' if enabled else 'You are now in live mode'
    current_user.demo = enabled
    if enabled:
        connect_paper(current_user)
    else:
        live = current_user.exchanges.filter(Exchange.name != PAPER_EXCHANGE).first()
        if live is not None:
            _activate(current_user, live.name)
    db.session.commit()
    return jsonify({
        'status': 'success',
        'message': message,
        'ok': True,
    })
