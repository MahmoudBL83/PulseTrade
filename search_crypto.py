import json
from bs4 import BeautifulSoup
import requests

# Define a function to search for symbols in a market
def search():
    # type = 'stock' | 'futures' | 'forex' | 'cfd' | 'crypto' | 'index' | 'economic'
    # query = what you want to search!
    # it returns first matching item
    '''res = requests.get(
        f"https://symbol-search.tradingview.com/symbol_search/?query=usdt&type=crypto&exchange=OKX"
    )
    if res.status_code == 200:
        res = res.json()
        assert len(res) != 0, "Nothing Found."
        return res
    else:
        print("Network Error!")
        exit(1)'''
    '''url = 'https://www.tradingview.com/markets/cryptocurrencies/prices-all/'
    response = requests.get(url)

    if response.status_code == 200:
        soup = BeautifulSoup(response.text, 'html.parser')
        table = soup.find_all('table')[0]
        rows = table.find_all('tr')

        symbols = []
        for row in rows[1:200]:
            if(row.find_all('td')[0].find("a").text.strip() != "GNO" and row.find_all('td')[0].find("a").text.strip() != "BIT" and row.find_all('td')[0].find("a").text.strip() != "GUSD" and row.find_all('td')[0].find("a").text.strip() != "MIOTA" and row.find_all('td')[0].find("a").text.strip() != "HT" and row.find_all('td')[0].find("a").text.strip() != "TUSD" and row.find_all('td')[0].find("a").text.strip() != "TWT" and row.find_all('td')[0].find("a").text.strip() != "VET" and row.find_all('td')[0].find("a").text.strip() != "QNT" and row.find_all('td')[0].find("a").text.strip() != "USDD" and row.find_all('td')[0].find("a").text.strip() != "MIOT" and row.find_all('td')[0].find("a").text.strip() != "BUSD" and row.find_all('td')[0].find("a").text.strip() != "BUS" and row.find_all('td')[0].find("a").text.strip() != "KAVA" and row.find_all('td')[0].find("a").text.strip() != "KCS" and row.find_all('td')[0].find("a").text.strip() != "XDC" and row.find_all('td')[0].find("a").text.strip() != "FXS" and row.find_all('td')[0].find("a").text.strip() != "USDP" and row.find_all('td')[0].find("a").text.strip() != "GT" and row.find_all('td')[0].find("a").text.strip() != "RUNE" and row.find_all('td')[0].find("a").text.strip() != "RNDR" and row.find_all('td')[0].find("a").text.strip() != "CAKE" and row.find_all('td')[0].find("a").text.strip() != "USDT" and row.find_all('td')[0].find("a").text.strip() != "PAXG" and row.find_all('td')[0].find("a").text.strip() != "BSV" and row.find_all('td')[0].find("a").text.strip() != "BSH" and row.find_all('td')[0].find("a").text.strip() != "INJ"):
                symbol = {"symbol":row.find_all('td')[0].find("a").text.strip() + "USDT","description":row.find_all('td')[0].find("a").text.strip()+"/Tether","type":"spot","exchange":"OKX","currency_code":"USDT","currency-logoid":"crypto/XTVCUSDT","base-currency-logoid":"crypto/XTVCOKB","provider_id":"okx","typespecs":["crypto"]}
                symbols.append(symbol)

        return [pair for pair in symbols if pair['type'] == "spot"]
    else:
        print(f"Error: {response.status_code}")'''
    
    symbols = []
    with open("search_crypto.json", "r") as f:
        symbols_file = json.load(f)
        for symbol in symbols_file:
            if(symbol != "GNO" and symbol != "ANKR" and symbol != "MX" and symbol != "OSMO" and symbol != "EDU" and symbol != "TEL" and symbol != "MLK" and symbol != "FLUX" and symbol != "PENDLE" and symbol != "RXD" and symbol != "HEX" and symbol != "HOT" and symbol != "EVER" and symbol != "RXD" and symbol != "AURA" and symbol != "HOPR" and symbol != "POWR" and symbol != "WNXM" and symbol != "DERO" and symbol != "SWTH" and symbol != "TLM" and symbol != "OCEAN" and symbol != "FOR" and symbol != "PRE" and symbol != "SOUL" and symbol != "HIVE" and symbol != "POOLX" and symbol != "LADYS" and symbol != "CRTS" and symbol != "BSCPAD" and symbol != "BONK" and symbol != "SQUIDGROW" and symbol != "EGG" and symbol != "XPLA" and symbol != "FARM" and symbol != "KWENTA" and symbol != "SIDUS" and symbol != "BTG" and symbol != "LAZIO" and symbol != "FRAX" and symbol != "PSP" and symbol != "CHR" and symbol != "MLT" and symbol != "CPOOL" and symbol != "POND" and symbol != "DERC" and symbol != "ARKM" and symbol != "AMB" and symbol != "ZANO" and symbol != "WRLD" and symbol != "CHESS" and symbol != "VIB" and symbol != "AGLA" and symbol != "FET" and symbol != "BAN" and symbol != "ALPH" and symbol != "UFT" and symbol != "GNS" and symbol != "ROSE" and symbol != "BFC" and symbol != "STRAX" and symbol != "USDJ" and symbol != "GYEN" and symbol != "DIMO" and symbol != "RBN" and symbol != "VEGA" and symbol != "TITAN"and symbol != "KLV"and symbol != "WTC" and symbol != "BBF" and symbol != "BETA" and symbol != "SUKU" and symbol != "GRV" and symbol != "FX" and symbol != "BIT" and symbol != "GUSD" and symbol != "MIOTA" and symbol != "HT" and symbol != "TUSD" and symbol != "TWT" and symbol != "VET" and symbol != "QNT" and symbol != "USDD" and symbol != "MIOT" and symbol != "BUSD" and symbol != "BUS" and symbol != "KAVA" and symbol != "KCS" and symbol != "XDC" and symbol != "FXS" and symbol != "USDP" and symbol != "GT" and symbol != "RUNE" and symbol != "RNDR" and symbol != "CAKE" and symbol != "USDT" and symbol != "PAXG" and symbol != "BSV" and symbol != "BSH" and symbol != "INJ"):
                symbols.append({"symbol":symbol + "USDT","description":symbol+"/Tether","type":"spot","exchange":"OKX","currency_code":"USDT","currency-logoid":"crypto/XTVCUSDT","base-currency-logoid":"crypto/XTVCOKB","provider_id":"okx","typespecs":["crypto"]})
            
    return symbols