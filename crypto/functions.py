import json
from flask import redirect, url_for
import ccxt
from flask_login import current_user
from crypto import models
import asyncio


def connectExchange(exchange_name=None,id=None):
    if id:
        current_user2 = models.User.query.get(id)
    else:
        current_user2 = current_user
    if exchange_name is None:
        if current_user2.exchanges.filter(models.Exchange.isActive==True).first():
            exchange_name = current_user2.exchanges.filter(models.Exchange.isActive==True).first().name
        else:
            return redirect(url_for('exchanges'))
    api_key,api_secret,password = current_user2.exchanges.filter(models.Exchange.name==exchange_name).first().get_creds()
    if current_user2.exchanges.filter(models.Exchange.name==exchange_name).first().password:
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

    if current_user2.exchanges.filter(models.Exchange.name==exchange_name).first().demo:
            exchange.set_sandbox_mode(True)
    
    return exchange

def getPrice_assets(exchange_name,symbol,id=None,volume_par=False,full=False):
    exchange_name = exchange_name.replace('okex','okx').upper()
    #exchange_name = "OKX"
    #exchange_name = exchange_name.lower().replace('okx','okex')
    '''exchange = connectExchange(exchange_name,id)
    
    
    try:
        if symbol.split("/")[0]=='USDK' or symbol.split("/")[0]=='USDP' or symbol.split("/")[0]=='PAX' or symbol.split("/")[0]=='USDT' or symbol.split("/")[0]=='TUSD' or symbol.split("/")[0]=='USDC' or symbol.split("/")[0]=='USDS':
            return 1
        else:
            return exchange.fetch_ticker(symbol)['last']
    except:
        try:
            pairs = []
            print(exchange_name)
            exchange = connectExchange(exchange_name,id)
            for currency in exchange.fetch_markets():
                pairs.append(currency['symbol'])

            common_pairs = []
            
            for pair in pairs:
                if pair != symbol:
                    common_symbol = set(pair.split('/')) & set(symbol.split('/'))
                    
                    if len(common_symbol) == 1:
                        common_pairs.append(pair)
            
            common_pairs = common_pairs[:2]
            related_pairs = []
            for pair in pairs:
                pair1=None
                pair2=None
                if pair.split('/')[0] == symbol.split('/')[0] or pair.split('/')[1] == symbol.split('/')[0]:
                    pair1 = pair
                if pair.split('/')[0] == symbol.split('/')[1] or pair.split('/')[1] == symbol.split('/')[1]:
                    pair2 = pair
                if pair1 and pair2:
                    related_pairs.append(pair)
                
            print(symbol)
            print(related_pairs)

            related_pairs = related_pairs[:2]
            
            if symbol.split('/')[0] == symbol.split('/')[1]:
                return 1
            elif len(related_pairs) == 2:
                if related_pairs[0].split('/')[0] == related_pairs[1].split('/')[0] or related_pairs[0].split('/')[1] == related_pairs[1].split('/')[1]:
                    price1 = exchange.fetch_ticker(related_pairs[0])['last']
                    price2 = exchange.fetch_ticker(related_pairs[1])['last']
                else:
                    price1 = exchange.fetch_ticker(related_pairs[1])['last']
                    price2 = exchange.fetch_ticker(related_pairs[0])['last']
                return price1*price2
            else:
                return 0
            
        except:
            return 0

        


        if symbol.split('/')[1] != 'USDT':
            price1 = 0
            price2 = 0
            exchange = connectExchange(exchange_name,id)
            
            price1 = exchange.fetch_ticker(symbol.split("/")[0]+"/"+"USDT")['last']
            price2 = exchange.fetch_ticker(symbol.split("/")[1]+"/"+"USDT")['last']
            if not price1 or not price2:
                return 0
            if  price1 == 0:
                return 0
            return price1/price2
        elif symbol.split("/")[1] == 'USDT' and symbol.split("/")[0] != 'USDT':
            price = 0
            exchange = connectExchange(exchange_name,id)
            price = exchange.fetch_ticker(symbol)['last']
            return price
        elif symbol.split("/")[0] == symbol.split("/")[1]:
            return 1
        else:
            return 0
    except Exception as e:
        print(e)
        return 0


        if symbol.split("/")[0] == symbol.split("/")[1]:
            price = 1
        elif symbol.split('/')[1] != 'USDT':
            price1 = 0
            price2 = 0
            exchange = connectExchange(exchange_name,id)
            exchange_name = exchange_name.upper().replace('OKEX','OKX')
            price1 = exchange.fetch_ticker(symbol.split("/")[1]+"/"+"USDT")['last']
            if symbol.split("/")[0]!='USDT':
                price2 = exchange.fetch_ticker(symbol.split("/")[0]+"/"+"USDT")['last']
            else:
                price2 = 1
            if not price1 or not price2:
                return 0
            if  price1 == 0:
                return 0
            return price2/price1

        else:
            exchange = connectExchange(exchange_name,id)
            exchange_name = exchange_name.upper().replace('OKEX','OKX')
            price = exchange.fetch_ticker(symbol)['last']
    except:
        return 0'''
    price = 0
    volume = 0
    change = 0
    percentage = 0
    high = 0
    low = 0
    open_price = 0
    reversed = False
    if (symbol == 'USDT/USDT' or symbol =='USDK/USDT' or symbol =='USDP/USDT' or symbol =='PAX/USDT' or symbol =='USDT/USDT' or symbol =='TUSD/USDT' or symbol =='USDS/USDT'):
        price = 1
        volume = 1

    else:
        if symbol.split('/')[0] == 'USDT':
            symbol = symbol.split('/')[1]+'/USDT'
            reversed = True
        try:
            symbol_id = f"{str(exchange_name).upper().replace('OKEX','OKX')}{symbol.split('/')[0]+symbol.split('/')[1]}"
            with open("pricesData/"+f"{symbol_id}.json", "r") as f:
                data = json.load(f)[symbol]
                price = data[0]
                volume = data[1]
                change = data[2]
                percentage = data[3]
                high = data[4]
                low = data[5]
                open_price = data[6]
            
        except:
            try:
                symbol_id = f"{str(exchange_name).upper().replace('OKEX','OKX')}{symbol.split('/')[0]+symbol.split('/')[1]}"
                if symbol.split('/')[1] == 'USDT':
                    with open("pricesData/"+f"{symbol_id}.json", "r") as f:
                        data = json.load(f)[symbol]
                        price = data[0]
                            
                else:
                    price1 = 0
                    price2 = 0
                    symbol_id1 = f"{str(exchange_name).upper().replace('OKEX','OKX')}{symbol.split('/')[1]+'USDT'}"
                    with open("pricesData/"+f"{symbol_id1}.json", "r") as f:
                        data = json.load(f)[symbol.split('/')[1]+"/"+'USDT']
                        price1 = data[0]
                    symbol_id2 = f"{str(exchange_name).upper().replace('OKEX','OKX')}{symbol.split('/')[0]+'USDT'}"
                    with open("pricesData/"+f"{symbol_id2}.json", "r") as f:
                        price2 = json.load(f)[symbol.split('/')[0]+"/"+'USDT'][0]
                    if (not price1 or not price2):
                        price = 0
                    if  price1 == 0:
                        price = 0
                    else:
                        price = price2/price1
                try:
                    with open("pricesData/"+f"{symbol_id}.json", "r") as f:
                        data = json.load(f)[symbol]
                        volume = data[1]
                        change = data[2]
                        percentage = data[3]
                        high = data[4]
                        low = data[5]
                        open_price = data[6]
                except:
                    volume = 0
                    change = 0
                    percentage = 0
                    high = 0
                    low = 0
                    open_price = 0
            except:
                price = 0
                volume = 0
                change = 0
                percentage = 0
                high = 0
                low = 0
                open_price = 0


    if reversed:
        if price != 0:
            price = 1/price
        else:
            price = 0        
    
    if volume_par:
        return price,volume
    elif full:
        return price,volume,change,percentage,high,low,open_price
    else:
        return price


def getPrice(exchange_name,symbol,id=None,volume=False):
    try:
        exchange_name = exchange_name.lower()
        exchange = connectExchange(exchange_name,id)
        data = exchange.fetch_ticker(symbol)
        #data = asyncio.get_event_loop().run_until_complete(exchange.fetch_ticker(symbol))
        price = data['close']
        if volume:
            volume = data['baseVolume']
            return price,volume
        
        '''if symbol == 'USDT/USDT':
            price = 1
            return price

        if symbol.split('/')[1] == 'USDT':
            symbol_id = f"{str(exchange_name).upper().replace('OKEX','OKX')}{symbol.split('/')[0]+symbol.split('/')[1]}"
            with open("pricesData/"+f"{symbol_id}.json", "r") as f:
                price = json.load(f)[symbol][0]
        else:
            price1 = 0
            price2 = 0
            symbol_id1 = f"{str(exchange_name).upper().replace('OKEX','OKX')}{symbol.split('/')[1]+'USDT'}"
            with open("pricesData/"+f"{symbol_id1}.json", "r") as f:
                price1 = json.load(f)[symbol.split('/')[1]+"/"+'USDT'][0]
            symbol_id2 = f"{str(exchange_name).upper().replace('OKEX','OKX')}{symbol.split('/')[0]+'USDT'}"
            with open("pricesData/"+f"{symbol_id2}.json", "r") as f:
                price2 = json.load(f)[symbol.split('/')[0]+"/"+'USDT'][0]
            if not price1 or not price2:
                return 0
            if  price1 == 0:
                price = 0
            else:
                price = price2/price1'''

        return price
    except:
        return 0

def getVolume(exchange_name,symbol,id=None):
    try:
        exchange = connectExchange(exchange_name,id)
        volume = exchange.fetch_ticker(symbol)['baseVolume']
            
    except:
        volume = 0
        
    return volume