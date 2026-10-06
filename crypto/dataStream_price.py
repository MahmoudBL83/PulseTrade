import json
import random
import re
import string
#from websocket import create_connection
from search_crypto import search

def generateSession():
    stringLength = 12
    letters = string.ascii_lowercase
    random_string = "".join(random.choice(letters) for i in range(stringLength))
    return "qs_" + random_string

def prependHeader(st):
    return "~m~" + str(len(st)) + "~m~" + st

def constructMessage(func, paramList):
    return json.dumps({"m": func, "p": paramList}, separators=(",", ":"))

def createMessage(func, paramList):
    return prependHeader(constructMessage(func, paramList))

def sendMessage(ws, func, args):
    try:
        ws.send(createMessage(func, args))
    except Exception as e:
        tradingViewSocket = "wss://data.tradingview.com/socket.io/websocket"
        headers = json.dumps({"Origin": "https://data.tradingview.com"})
        #ws = create_connection(tradingViewSocket, headers=headers)

def send_ping_packet(ws, result):
    ping_str = re.findall(".......(.*)", result)
    if ping_str:
        ping_str = ping_str[0]
        ws.send(f"~m~{len(ping_str)}~m~{ping_str}")

def sendPingPacket(ws, result):
    pingStr = re.findall(".......(.*)", result)
    if len(pingStr) != 0:
        pingStr = pingStr[0]
        ws.send("~m~" + str(len(pingStr)) + "~m~" + pingStr)



def socketJob(ws, symbol_id,tradingViewSocket,headers):
    try:
        result = ws.recv()
        price = 0
        if "session_id" in result:
            return socketJob(ws, symbol_id,tradingViewSocket,headers)
        if "quote_completed" in result :
            try:
                Res = re.findall("^.*?({.*)$", result)
                jsonStr = Res[0].split("~m~")[0]

                try:
                    jsonRes = json.loads(jsonStr)
                except json.JSONDecodeError:
                    # Handle non-JSON strings
                    return socketJob(ws, symbol_id,tradingViewSocket,headers)
                if jsonStr:
                    if jsonRes["m"] == "qsd":
                        price = jsonRes["p"][1]["v"]["lp"]
                        if 'volume' in jsonRes["p"][1]["v"]:
                            volume = jsonRes["p"][1]["v"]["volume"]
                        else:
                            volume = 0
                        if 'ch' in jsonRes["p"][1]["v"]:
                            change = jsonRes["p"][1]["v"]["ch"]
                        else:
                            change = 0

                        if 'chp' in jsonRes["p"][1]["v"]:
                            change_percentage = jsonRes["p"][1]["v"]["chp"]
                else:
                    send_ping_packet(ws, result)
                    #return socketJob(ws, symbol_id,tradingViewSocket,headers)
                return price,volume,change,change_percentage
            except Exception as e:
                send_ping_packet(ws, result)
                #return socketJob(ws, symbol_id,tradingViewSocket,headers)
        else:
            #send_ping_packet(ws, result)
            return socketJob(ws, symbol_id,tradingViewSocket,headers)

    
    except json.JSONDecodeError as e:
        # Log error message and problematic message for debugging purposes
        print(f"JSON decode error: {e}")
        print(f"Problematic message:")
        return 0,0,0,0
    except KeyboardInterrupt:
        print("\nGoodbye!")
        exit(0)
    except Exception as e:
        print(f"ERROR: {e}\nTradingView message:")
        return 0,0,0,0
