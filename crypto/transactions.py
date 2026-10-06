from flask import render_template, request, redirect, url_for, jsonify
import ccxt
from flask_login import login_required,current_user
from crypto import app, db,jwt_required
from crypto.models import Exchange, Post, Transaction
from crypto.notify import send_notification
from crypto.exchanges import connectExchange

@app.route('/api/v1/deposit/', methods=['POST','GET'])
@jwt_required
def crypto_deposit():
    '''
        function for making deposit to exchange
        the parameters are:
        symbol: the symbol of the coin to deposit
        network: the network of the coin to deposit
        the response is:
        {
            "message": "successful deposit",
            "ok": true,
            "deposit": deposit
        }
        deposit is the response from the exchange
    '''
    if current_user.exchanges.filter(Exchange.isActive==True).first() is None:
        if request.method == 'POST':
            return jsonify('message','No active exchange found')
        else:
            return redirect(url_for('exchanges'))
        
    exchange_name = current_user.exchanges.filter(Exchange.isActive == True).first().name
    exchange = connectExchange(exchange_name)
    if request.method == 'POST':
        try:
            symbol = request.json['symbol']
            network = request.json['network']
            if 'fetchDepositAddress' in exchange.describe()['has']:
                if exchange.fetch_currencies() is None or exchange.describe()['has']['fetchDepositAddress'] == False:
                    return jsonify({'message': 'Depsoit is not possible'})
            else:
                return jsonify({'message': 'Depsoit is not possible'})
                
            # Initiate deposit with exchange
            deposit = exchange.fetch_deposit_address(symbol, {'network': network})
            '''print(deposit)
            send_notification(f'Deposit completed on {exchange_name} for {symbol}***Deposit')'''
            print(deposit)
            return jsonify({'message':f"Send only {symbol} to this address {deposit['address']}",
                            'ok':True,
                            'address':deposit['address'],
                            'tag':deposit['tag'] if 'tag' in deposit else None
                            })
        
        except ccxt.InsufficientFunds as e:
            return jsonify({'message': f'Error Depositing order on {exchange_name}: Insufficient funds. {str(e)}'})
        except ccxt.InvalidOrder as e:
            return jsonify({'message': f'Error Depositing order on {exchange_name}: Invalid order. {str(e)}'})
        except ccxt.NetworkError as e:
            return jsonify({'message': f'Error Depositing order on {exchange_name}: Network error. {str(e)}'})
        except ccxt.ExchangeError as e:
            return jsonify({'message': f'Error Depositing order on {exchange_name}: Exchange error. {str(e)}'})
        except ccxt.BaseError as e:
            return jsonify({'message': f'Error Depositing order on {exchange_name}: {str(e)}'})
    
    if exchange.describe()['has']['fetchDepositAddress']:
        return render_template('deposit.html',
                            exchanges = current_user.exchanges.all(),
                            current_user=current_user,posts = Post.query.all(),
                            notifications=current_user.notifications.all(),
                            deposits = connectExchange().fetch_deposits() if 'fetchDeposits' in exchange.describe()['has'] and exchange.describe()['has']['fetchDeposits'] else [],
                        )
    else:
        return render_template('404.html',exchanges=current_user.exchanges.all())

#get all deposits history
@app.route('/api/v1/deposits/', methods=['POST','GET'])
@jwt_required
def crypto_deposits():
    '''
    the deposits are returned in the following format:
    [
        {
            "info": {
                "currency": "BTC",
                "amount": "0.0001",
                "txid": "5f7a0a9c03aa675e4a06f5b0",
                "address": "3J98t1WpEZ73CNmQviecrnyiWrnqRhWNLy",
                "addressTo": "3J98t1WpEZ73CNmQviecrnyiWrnqRhWNLy",
                "type": "withdrawal",
                "timestamp": "1601817600000",
                "status": "success"
            },
        }
    ]
    '''
    return jsonify(connectExchange().fetch_deposits())

@app.route('/api/v1/transfer/', methods=['POST', 'GET'])
@jwt_required
def crypto_transfer():
    '''
        function for making transfer between spot and funding
        the parameters are:
        amount: the amount to transfer
        side: the side of the transfer (funding or spot)
        symbol: the symbol of the coin to transfer
    '''
    if current_user.exchanges.filter(Exchange.isActive==True).first() is None:
        if request.method == 'POST':
            return jsonify('message','No active exchange found')
        else:
            return redirect(url_for('exchanges'))
    exchange_name = current_user.exchanges.filter(Exchange.isActive == True).first().name
    exchange = connectExchange(exchange_name)
    if request.method == 'POST':
        amount = request.json['amount']
        side = request.json['side']
        symbol = request.json['symbol']

        try:
            if side == 'funding':
                result = exchange.transfer(symbol, amount,"spot", "funding")
                send_notification(f'Transfer completed on {exchange_name} for {amount} {symbol} from spot to funding***Transfer')
            else:
                result = exchange.transfer(symbol, amount, "funding","spot")
                send_notification(f'Transfer completed on {exchange_name} for {amount} {symbol} from funding to spot***Transfer')


            if result['id']:
                message = f'Transfer successful. ID: {result["id"]}'
                return jsonify({'message': message,'ok':True})
            else:
                return jsonify({'message': 'Transfer failed'})

        except ccxt.InsufficientFunds as e:
            return jsonify({'message': str(e)})

        except ccxt.ExchangeError as e:
            return jsonify({'message': str(e)})

        except ccxt.NetworkError as e:
            return jsonify({'message': str(e)})

        except Exception as e:
            return jsonify({'message': 'An error occurred. Please try again later.'})
    if 'transfer' in exchange.describe()['has']:
        if exchange.describe()['has']['transfer']:
            try:
                transfers = exchange.fetch_transfers()[::-1]
                formatted_transfers = []
                for order in transfers:
                    formatted_transfer = {
                        'id': order['id'],
                        'amount': round(float(order['amount']),4),
                        'currency': order['currency'],
                        'from': 'spot' if order['fromAccount']=='trading' else order['fromAccount'],
                        'to': 'spot' if order['toAccount']=='trading' else order['toAccount'],
                        'timestamp': order['timestamp'],
                    }
                    if order['toAccount'] == 'funding' or order['fromAccount'] == 'funding' or True:
                        formatted_transfers.append(formatted_transfer)
            except:
                formatted_transfers = []

            return render_template('transfer.html',
                                        transfers = formatted_transfers,
                                        exchanges=current_user.exchanges.all(),
                                        current_user=current_user,
                                        posts = Post.query.all(),
                                        notifications=current_user.notifications.all()
                                    )
    else:
        return render_template('404.html',exchanges=current_user.exchanges.all())

@app.route('/api/v1/convert/', methods=['POST','GET'])
@jwt_required
def crypto_convert():
    if current_user.exchanges.filter(Exchange.isActive==True).first() is None:
        if request.method == 'POST':
            return jsonify('message','No active exchange found')
        else:
            return redirect(url_for('exchanges'))
    exchange_name = current_user.exchanges.filter(Exchange.isActive == True).first().name
    
    if request.method == 'POST':
        try:
            # Extract the parameters from the JSON request
            amount = request.json['amount']
            order_type = request.json['order_type']
            source_asset = request.json['source_asset']
            target_asset = request.json['target_asset']
            side = str(request.json['side'])


            # Create the exchange object with the API credentials
            exchange = connectExchange(exchange_name)
            # Construct the symbol based on the chosen assets
            symbol = f"{source_asset}/{target_asset}"
            
            # Check if the exchange supports the specified trading pair
            if exchange.describe()['has']['createOrder']:
                # Set the order type based on the parameter
                if order_type == 'market':
                    order = exchange.create_order(symbol, 'market', ('sell' if side=="1" else "buy"), amount)
                    db.session.add(Transaction(user_id=current_user.id,exchange=exchange_name,symbol=symbol,type=('sell' if side=="1" else "buy"),amount=amount,value=exchange.fetch_order(order['id'],symbol=symbol)['price']))
                    if side == '1':
                        send_notification(f'Conversion completed on {exchange_name} to convert {amount} {source_asset} to {float(exchange.fetch_order(order["id"],symbol)["price"])*float(amount)} {target_asset}***Convert')
                    else:
                        send_notification(f'Conversion completed on {exchange_name} to convert {float(exchange.fetch_order(order["id"],symbol)["price"])*float(amount)} {target_asset} to {amount} {source_asset}***Convert')
                elif order_type == 'limit':
                    # Additional parameters for limit orders
                    price = request.json['price']
                    order = exchange.create_order(symbol, 'limit', ('sell' if side=="1" else "buy"), amount, price)
                    if side == '1':
                        send_notification(f'Conversion started on {exchange_name} to convert {amount} {source_asset} to {float(price)*float(amount)} {target_asset}***Convert')
                    else:
                        send_notification(f'Conversion started on {exchange_name} to convert {float(price)*float(amount)} {target_asset} to {amount} {source_asset}***Convert')
                    current_user.append_to_open_orders([order['id'], symbol,'convert'])
                else:
                    return jsonify({'message': 'Invalid order type. Supported types: market, limit.'})
                # Return the order details as JSON response
                return jsonify({'message': f"Conversion order created on {exchange_name}.",'ok':True, 'order': order})
            else:
                return jsonify({'message': f"{exchange_name} does not support the {symbol} trading pair."})
        except ccxt.InsufficientFunds as e:
            return jsonify({'message': f'Error creating order on {exchange_name}: Insufficient funds. {str(e)}'})
        except ccxt.InvalidOrder as e:
            return jsonify({'message': f'Error creating order on {exchange_name}: Invalid order. {str(e)}'})
        except ccxt.NetworkError as e:
            return jsonify({'message': f'Error creating order on {exchange_name}: Network error. {str(e)}'})
        except ccxt.ExchangeError as e:
            return jsonify({'message': f'Error creating order on {exchange_name}: Exchange error. {str(e)}'})
        except ccxt.BaseError as e:
            return jsonify({'message': f'Error creating order on {exchange_name}: {str(e)}'})
        
        
    
    exchange = connectExchange()
    
    pairs = []
    for currency in exchange.fetch_markets():
        if currency['active'] and currency['spot']:
            pairs.append(currency['symbol'])

    return render_template('convert.html',
                           exchanges = current_user.exchanges.all(),
                           current_user=current_user,
                           posts = Post.query.all(),
                           notifications=current_user.notifications.all(),
                           pairs = pairs,
                           )


@app.route('/api/v1/withdraw/', methods=['POST','GET'])
@jwt_required
def crypto_withdraw():
    if current_user.exchanges.filter(Exchange.isActive==True).first() is None:
        if request.method == 'POST':
            return jsonify('message','No active exchange found')
        else:
            return redirect(url_for('exchanges'))
    exchange_name = current_user.exchanges.filter(Exchange.isActive == True).first().name
    exchange = connectExchange(exchange_name)
    if request.method == 'POST':
        try:
            amount = request.json['amount']
            recipient_address = request.json['recipient_address']
            currency = request.json['currency']
            network_user = request.json['network']
            if exchange.fetch_currencies() is None:
                return jsonify({'message': 'Withdraw is not possible'})

            # Specify the network parameter for each exchange
            params = {'network': network_user}
            # Add additional elif statements for other exchanges as needed

            # Execute the withdrawal and check the response for errors
            response = exchange.withdraw(currency, amount, recipient_address,None, params)
            if 'info' in response and 'status' in response['info'] and response['info']['status'] == '0':
                error_msg = "User identity verification is required for this withdrawal"
                return jsonify({"message": error_msg}), 400
            elif 'error' in response:
                error_msg = response['error']
                return jsonify({"message": error_msg}), 400
            else:
                # The response will contain information about the withdrawal, such as the ID of the withdrawal and its status
                print(response)
                send_notification(f'Withdraw completed on {exchange_name} for {amount} {currency}***Withdraw')
                return jsonify({"message": "withdraw done",'ok':True})
        except ccxt.NetworkError as e:
            # Handle network errors (e.g. connection issues)
            error_msg = f"Network error: {str(e)}"
            return jsonify({"message": error_msg}), 500
        except ccxt.ExchangeError as e:
            # Handle exchange errors (e.g. invalid parameters, insufficient funds)
            error_msg = f"Exchange error: {str(e)}"
            return jsonify({"message": error_msg}), 400
        except Exception as e:
            # Handle other errors (e.g. unexpected errors)
            error_msg = f"Unexpected error: {str(e)}"
            return jsonify({"message": error_msg}), 500
    if 'withdraw' in exchange.describe()['has']:
        if exchange.describe()['has']['withdraw']:
            return render_template('withdraw.html',
                                        exchanges = current_user.exchanges.all(),
                                        current_user=current_user,posts = Post.query.all(),
                                        notifications=current_user.notifications.all(),
                                        withdrawals = connectExchange().fetch_withdrawals() if 'fetchWithdrawals' in exchange.describe()['has'] and exchange.describe()['has']['fetchWithdrawals'] else [],
                                )
    else:
        return render_template('404.html',exchanges=current_user.exchanges.all())
    
#get all withdrawals history
@app.route('/api/v1/withdrawals/', methods=['POST','GET'])
@jwt_required
def crypto_withdrawals():
    '''
    the withdrawals are returned in the following format:
    [
        {
            "info": {
                "currency": "BTC",
                "amount": "0.0001",
                "txid": "5f7a0a9c03aa675e4a06f5b0",
                "address": "3J98t1WpEZ73CNmQviecrnyiWrnqRhWNLy",
                "addressTo": "3J98t1WpEZ73CNmQviecrnyiWrnqRhWNLy",
                "type": "withdrawal",
                "timestamp": "1601817600000",
                "status": "success"
            },
        }
    ]
    '''
    return jsonify(connectExchange().fetch_withdrawals() if 'fetchWithdrawals' in connectExchange().describe()['has'] and connectExchange().describe()['has']['fetchWithdrawals'] else [])

@app.route('/api/v1/precision/<exchange_name>', methods=['POST','GET'])
@jwt_required
def get_precision(exchange_name):
    symbol = request.json['symbol']
    exchange = connectExchange(exchange_name)
    if exchange.fetch_markets() is None:
        return jsonify([])
    print(symbol)
    #load markets first
    exchange.load_markets()
    print(exchange.market(symbol))
    print(exchange.market(symbol)['precision'])
    amount = exchange.market(symbol)['precision']['amount']
    price = exchange.market(symbol)['precision']['price']

    return jsonify({'amount':amount,'price':price})


@app.route('/api/v1/currencies/<exchange_name>', methods=['POST','GET'])
@jwt_required
def get_currencies(exchange_name):
    '''
    the currencies are returned in the following format:
    {
        "active": true,
        "code": "ETHW",
        "deposit": true,
        "fee": 0.01,
        "id": "ETHW",
        "limits": {
            "amount": {
                "max": null,
                "min": null
            },
            "deposit": {
                "max": null,
                "min": 0
            },
            "withdraw": {
                "max": null,
                "min": 0.01
            }
        },
        "name": "ETHW",
        "networks": {
            "ETHW": {
                "active": true,
                "deposit": true,
                "fee": 0.01,
                "id": "ETHW",
                "info": {
                    "chain": "ETHW",
                    "chainDeposit": "1",
                    "chainType": "ETHW",
                    "chainWithdraw": "1",
                    "confirmation": "50",
                    "depositMin": "0",
                    "minAccuracy": "8",
                    "withdrawFee": "0.01",
                    "withdrawMin": "0.01",
                    "withdrawPercentageFee": "0"
                },
                "limits": {
                    "deposit": {
                        "max": null,
                        "min": 0
                    },
                    "withdraw": {
                        "max": null,
                        "min": 0.01
                    }
                },
                "network": "ETHW",
                "precision": 1e-8,
                "withdraw": true
            }
        },
        "precision": 1e-8,
        "withdraw": true
    }
    '''
    exchange = connectExchange(exchange_name)
    if exchange.fetch_currencies() is None:
        return jsonify([])
    
    return jsonify(list(map(lambda x: x[1],exchange.fetch_currencies().items())))

@app.route('/api/v1/fees', methods=['POST','GET'])
@jwt_required
def get_fees():
    code = request.args.get('code')
    exchange = connectExchange()
    return jsonify(exchange.fetch_deposit_withdraw_fees([code]))

@app.route('/api/v1/markets/<exchange_name>', methods=['POST','GET'])
@jwt_required
def get_markets(exchange_name):
    '''
    the markets are returned in the following format:
    {
        "base": {
            "1INCH": "1INCH",
            "1SOL": "1SOL",
            "3P": "3P",
            ...
        },
        "quote": {
            "BRZ": "BRZ",
            "BTC": "BTC",
            ...
        }
    }
    '''
    exchange = connectExchange(exchange_name)

    if exchange.fetch_markets() is None:
        return jsonify([])
    
    currencies = exchange.fetch_markets()
    return jsonify({"base": {key: value for key, value in zip([currency["base"] for currency in currencies], [currency["base"] for currency in currencies])}, "quote": {key: value for key, value in zip([currency["quote"] for currency in currencies], [currency["quote"] for currency in currencies])}})

@app.route('/api/v1/all_markets/<exchange_name>', methods=['POST','GET'])
@jwt_required
def get_all_markets(exchange_name):
    exchange = connectExchange(exchange_name)

    if exchange.fetch_markets() is None:
        return jsonify([])
    pairs = []
    for currency in exchange.fetch_markets():
        if currency['active'] and currency['spot']:
            pairs.append(currency['symbol'])

    return jsonify(pairs)

