#encoding=gbk
import time
import redis
import json
import pandas as pd
import sys
from datetime import datetime
from datetime import time as time_class
import requests
import threading




print(1)

# CN26F 价格数据
latest_prices = {"ask1": 0, "bid1": 0, "timestamp": 0}
reconnect_needed = False

data2 = {}  # 全局变量
redis_db=redis.Redis(host='127.0.0.1',port=6379,db=0)
a=0
b=0
etf1000_code= {}
redis_message1000= {}
strategyName=''
type=''
over=''
askPrice_old=0
bidPrice_old=0
askPrice_gua=0
bidPrice_gua=0
ying_max=-100000
ying_min=100000
ying2_max=-100000
ying2_min=100000
today_kong=0
yestoday_duo=0
redis_db.delete('IH_lock2')
redis_db.delete('IH_lock')

jc={"10009641.SHO":0}
mo_code={}

def fetch_single_price():
    """获取A50期指实时价格"""
    url = "https://futsseapi.eastmoney.com/static/104_CN26F_qt"
    params = {
        "callbackName": f"jQuery{int(time.time() * 1000)}_{int(time.time() * 1000)}",
        "field": "mrj,mcj",
        "token": "1101ffec61617c99be287c1bec3085ff",
        "_": int(time.time() * 1000)
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://quote.eastmoney.com/globalfuture/CN26F.html"
    }

    try:
        response = requests.get(url, params=params, headers=headers, timeout=2)
        if response.status_code == 200:
            json_str = response.text.split('(', 1)[1].rsplit(')', 1)[0]
            json_data = json.loads(json_str)

            if json_data.get("qt"):
                return {
                    "ask1": json_data["qt"].get("mcj"),
                    "bid1": json_data["qt"].get("mrj")
                }
    except Exception as e:
        print(f"CN26F API请求错误: {e}")
    return None

def price_updater():
    """独立的价格更新线程"""
    global latest_prices

    while True:
        start_time = time.time()
        price_data = fetch_single_price()

        if price_data and price_data["ask1"] is not None and price_data["bid1"] is not None:
            latest_prices.update({
                "ask1": price_data["ask1"],
                "bid1": price_data["bid1"],
                "timestamp": time.time()
            })

        elapsed = time.time() - start_time
        if elapsed < 0.2:
            time.sleep(0.2 - elapsed)

def find_min_askPrice(dictionary):
    result_index = None
    min_askPrice = float('inf')
    max_askVol = 0
    
    for key, value in dictionary.items():
        if key != 'MO2410-C-4000.IF' and value['askPrice'] < min_askPrice:
            min_askPrice = value['askPrice']
            max_askVol = value['askVol']
            result_index = key
        elif key != 'MO2410-C-4000.IF' and value['askPrice'] == min_askPrice and value['askVol'] > max_askVol:
            max_askVol = value['askVol']
            result_index = key
    
    return result_index

def show_data(data):
    tdata = {}
    for ar in dir(data):
        if ar[:2] != 'm_':continue
        try:
            tdata[ar] = data.__getattribute__(ar)
        except:
            tdata[ar] = '<CanNotConvert>'
    return tdata

def is_kong(data):
    for stock in data:
        if data[stock] == {}: 
            return True 
    return False
def round_to_even_decimal(num):
    rounded_num = round(num, 1)
    int_part, dec_part = str(rounded_num).split('.')
    if int(dec_part) % 2 != 0:
        rounded_num = round(rounded_num + 0.1, 1)

    return rounded_num
 
def calculate_option_time_value(option_type, market_price, strike_price, current_price):  

    if option_type == 'call':  
        intrinsic_value = max(0, current_price - strike_price)  
    elif option_type == 'put':  
        intrinsic_value = max(0, strike_price - current_price)  
    else:  
        raise ValueError("option_type  'call' or 'put'")  
    time_value = market_price - intrinsic_value  
    return round(time_value,1)  




 
    
def init(C):
    global today_kong,yestoday_duo,bidPrice_gua,askPrice_gua,data2,redis_db,jc,etf1000_code,a ,strategyName,redis_message1000,type,askPrice_old,bidPrice_old,mo_code,over,ying_max,ying_min,ying2_max,ying2_min

    # 启动 CN26F 价格更新线程
    price_thread = threading.Thread(target=price_updater, daemon=True)
    price_thread.start()
    print("CN26F 价格更新线程已启动")

    def call_back(data):
        #print(data)
        #return
        global today_kong,yestoday_duo,bidPrice_gua,askPrice_gua,data2,redis_db,jc,etf1000_code,a ,strategyName,redis_message1000,type,askPrice_old,bidPrice_old,mo_code,over,ying_max,ying_min,ying2_max,ying2_min

        # 检查 CN26F 数据是否已初始化
        if latest_prices["timestamp"] == 0:
            print("等待 CN26F 数据初始化...")
            return

        # 检查 CN26F 数据是否过期（超过60秒未更新）
        current_time_unix = time.time()
        if current_time_unix - latest_prices["timestamp"] > 60:
            print(f"警告：CN26F数据已过期 ({int(current_time_unix - latest_prices['timestamp'])}秒)")
            return

        # 填充 CN26F 价格到 data2（价格除以5进行单位转换）
        data2['10009641.SHO']['askPrice'] = latest_prices["ask1"] / 5
        data2['10009641.SHO']['bidPrice'] = latest_prices["bid1"] / 5
        print(f"CN26F价格: 卖一={latest_prices['ask1']}/5={data2['10009641.SHO']['askPrice']}, "
              f"买一={latest_prices['bid1']}/5={data2['10009641.SHO']['bidPrice']}")

        if type=='over': 
            print('over')
            return
        if redis_db.get('IH_lock2') is not None:
            print('IH_lock2')
            return
        current_time = datetime.now().time()
        target_time = time_class(23, 55)

        #print(current_time)
        #print(target_time)
        
        if current_time > target_time:
            if  strategyName!='': 
                orderid = get_last_order_id(account, 'FUTURE', 'order',strategyName)
                print(cancel(orderid, account, 'FUTURE', C))
                strategyName=''
            print('time over')
            return

        Vol=4
        for stock in data:
            #print(data[stock])
            #return
            if stock[-3:]=='SZO' or stock[-3:]=='SHO':
                if data[stock]['askVol'][0]>Vol:
                    data[stock]['real_askPrice']=data[stock]['askPrice'][0]
                    data2[stock]['prType']=2
                elif  (data[stock]['askVol'][0]+data[stock]['askVol'][1]) >Vol :
                    data[stock]['real_askPrice']=data[stock]['askPrice'][1]
                    data2[stock]['prType']=1
                elif  (data[stock]['askVol'][0]+data[stock]['askVol'][1]+data[stock]['askVol'][2]) >Vol :
                    data[stock]['real_askPrice']=data[stock]['askPrice'][2]
                    data2[stock]['prType']=0
                elif  (data[stock]['askVol'][0]+data[stock]['askVol'][1]+data[stock]['askVol'][2]+data[stock]['askVol'][3]) >Vol :
                    data[stock]['real_askPrice']=data[stock]['askPrice'][3]
                    data2[stock]['prType']=0
                elif  (data[stock]['askVol'][0]+data[stock]['askVol'][1]+data[stock]['askVol'][2]+data[stock]['askVol'][3]+data[stock]['askVol'][4]) >Vol :
                    data[stock]['real_askPrice']=data[stock]['askPrice'][4]
                    data2[stock]['prType']=0
                else:
                    data[stock]['real_askPrice']=100000
                
                data2[stock]['askPrice']=data[stock]['real_askPrice']
            else:
                data2[stock]['askPrice']=data[stock]['askPrice'][0]
                
            data2[stock]['bidPrice']=data[stock]['bidPrice'][0]
            
            if stock[-3:]=='SZO' or stock[-3:]=='SHO':

                if data[stock]['bidVol'][0]>Vol:
                    data[stock]['real_bidPrice']=data[stock]['bidPrice'][0]
                    data2[stock]['prType2']=8
                elif  (data[stock]['bidVol'][0]+data[stock]['bidVol'][1]) >Vol :

                    data[stock]['real_bidPrice']=data[stock]['bidPrice'][1]
                    data2[stock]['prType2']=9
                elif  (data[stock]['bidVol'][0]+data[stock]['bidVol'][1]+data[stock]['bidVol'][2]) >Vol :
                    data[stock]['real_bidPrice']=data[stock]['bidPrice'][2]
                    data2[stock]['prType2']=10
                elif  (data[stock]['bidVol'][0]+data[stock]['bidVol'][1]+data[stock]['bidVol'][2]+data[stock]['bidVol'][3]) >Vol :
                    data[stock]['real_bidPrice']=data[stock]['bidPrice'][3]
                    data2[stock]['prType2']=10
                elif  (data[stock]['bidVol'][0]+data[stock]['bidVol'][1]+data[stock]['bidVol'][2]+data[stock]['bidVol'][3]+data[stock]['bidVol'][4]) >Vol :
                    data[stock]['real_bidPrice']=data[stock]['bidPrice'][4]
                    data2[stock]['prType2']=10
                else:
                    data[stock]['real_bidPrice']=0.00001
                    
                data2[stock]['bidPrice']=data[stock]['real_bidPrice']
          
            data2[stock]['askVol']=data[stock]['askVol'][0]

            data2[stock]['bidVol']=data[stock]['bidVol'][0]
    #        data2[stock]['iopv']=data[stock]['askPrice'][0]-get_etf_iopv(stock)
        if is_kong(data2): 
            return
            #pass
        #data['MO2409-C-3900']['bidPrice']=555    
        #print(data) 
        

        #result_stock = '10009641.SHO'

        #ying_jz = int(redis_db.get('ying_jz'))
        #ying2_jz = int(redis_db.get('ying2_jz'))

        ying_jz = 25.99
        ying2_jz = -17.2

        if over=='over' and type=='open' and a==0: 
            
            print('orderpass')

            strategy_time = float(strategyName)
            current_time = datetime.now().timestamp()
            
 

            ying_gua=  askPrice_gua - data2['10009641.SHO']['askPrice']*1000
            data2['10009641.SHO']['askPrice']=round(data2['10009641.SHO']['askPrice']+0.0001,4)
            etf1000_code=   {'Stock':'CN26F','Price':data2['10009641.SHO']['askPrice']}  
            print(current_time)
            print(ying_gua,data2['10009640.SHO']['bidPrice'],askPrice_gua)
            if (ying_gua < ying_jz+1.0 or ying_gua > ying_jz+2 or current_time > strategy_time + 60):

                orderid = get_last_order_id(account, 'FUTURE', 'order',strategyName)
                print(cancel(orderid, account, 'FUTURE', C))
                print('cancel')
                strategyName=''   
                over=''
                #type=''
                redis_db.delete('IH_lock')
            return

        
        if over=='over' and type=='close' and a==0: 
            print('orderpass_close')
            strategy_time = float(strategyName)
            current_time = datetime.now().timestamp()


            ying2_gua=data2['10009641.SHO']['bidPrice']*1000 - bidPrice_gua
            data2['10009641.SHO']['bidPrice']=round(data2['10009641.SHO']['bidPrice']-0.0001,4)
            etf1000_code=   {'Stock':'CN26F','Price':data2['10009641.SHO']['bidPrice']}  
            print(current_time)
            print(ying2_gua,data2['10009640.SHO']['askPrice'],bidPrice_gua)
            if (ying2_gua < ying2_jz+1 or ying2_gua > ying2_jz+10 or current_time > strategy_time + 60):
                

                orderid = get_last_order_id(account, 'FUTURE', 'order',strategyName)
                print(cancel(orderid, account, 'FUTURE', C))
                print('cancel')
                strategyName=''   
                over=''
                #type=''
                redis_db.delete('IH_lock')
            return
        if over=='over': 
            return



        ying= data2['10009640.SHO']['bidPrice'] - data2['10009641.SHO']['askPrice']*1000
        print('ying',ying,data2['10009640.SHO']['bidPrice'], data2['10009641.SHO']['askPrice'])

        

        if 1 and ying>ying_jz  and ying<100000 and ying>-100000: 
            if 1:
                strategyName=str(datetime.now().timestamp())
                print(strategyName)
                askPrice_gua = data2['10009640.SHO']['bidPrice']+1.2

                order=passorder(3, 1101, account, '10009640.SHO', 11, askPrice_gua, 1,strategyName, 2, "b",C)
                data2['10009641.SHO']['askPrice']=round(data2['10009641.SHO']['askPrice']+0.0001,4)
                etf1000_code=   {'Stock':'CN26F','Price':data2['10009641.SHO']['askPrice']}  

                a=1
                redis_db.set('IH_lock', 1)
                type='open'
                over='over'
                return


        ying2= data2['10009641.SHO']['bidPrice']*1000 - data2['10009640.SHO']['askPrice']
        print('ying2',ying2, data2['10009641.SHO']['bidPrice'],data2['10009640.SHO']['askPrice'])
        
        if 1>2 and ying2>ying2_jz  and ying2<100000 and ying2>-100000 : 

            if 1:
                
                strategyName=str(datetime.now().timestamp())
                print(strategyName,today_kong)
                bidPrice_gua = data2['10009640.SHO']['askPrice']-2.0

                order=passorder(8, 1101, account, '10009640.SHO', 11, bidPrice_gua, 1,strategyName, 2, "b",C)
                data2['10009641.SHO']['bidPrice']=round(data2['10009641.SHO']['bidPrice']-0.0001,4)
                etf1000_code=   {'Stock':'CN26F','Price':data2['10009641.SHO']['bidPrice']}  

                a=1
                redis_db.set('IH_lock', 1)
                type='close'
                over='over'
                return
                
        if 1>2: #直接开单的代码
            if 1:
                strategyName=str(datetime.now().timestamp())
                print(strategyName)
                #order=passorder(0, 1101, account, '10009640.SHO', 11, data2['10009641.SHO']['askPrice'], 1,strategyName, 2, "b",C)
                order=passorder(3, 1101, account, '10009641.SHO', 11, data2['10009641.SHO']['bidPrice'], 1,strategyName, 2, "b",C)
                #etf1000_code=   {'Stock':result_stock,'Price':data[result_stock]['bidPrice']}

                a=1
                #type='close'
                over='over'

        record_max_values(ying, ying2)
    C.set_account(account)
    
    orders = get_trade_detail_data(account, 'FUTURE', 'order')

    for o in orders:
        #print(o.m_strInstrumentID)
        #print(f'a: {o.m_strInstrumentID}, b: {o.m_strExchangeID}, c: {o.m_strInstrumentName}, d: {o.m_nOffsetFlag}',
        #f'f: {o.m_nVolumeTotalOriginal}, e: {o.m_dTradedPrice}, aa: {o.m_nVolumeTraded}, aa:{o.m_nOrderStatus}')
        
        
        if (o.m_nVolumeTotalOriginal!=o.m_nVolumeTraded and o.m_nOrderStatus!=54) and o.m_strInstrumentID=='10009640.SHO':
            print('has order')
            return


    #C.stock_list = ["MO2410-C-4000.IF","512100.SH"] 10009641.SHO
    # 只订阅 10009640.SHO，CN26F 价格通过独立线程获取
    C.stock_list = ["10009640.SHO"]
    for stock in C.stock_list:
        data2[stock] = {}
    # 为 CN26F 数据预留空间（键名保持为 10009641.SHO 以最小化代码改动）
    data2['10009641.SHO'] = {}
#    C.stock_list = ["au00.SF","10009640.SHO"]
    C.subID = C.subscribe_whole_quote(C.stock_list,callback=call_back)
    print(C.subID)



def order_callback(C,orderInfo):
    o=show_data(orderInfo)
    #print(show_data(orderInfo))
    #print(o)
    global redis_db,etf1000_code,redis_message1000,a,strategyName,type ,mo_code

    #print(o.m_nVolumeTotalOriginal,o.m_nVolumeTraded,o.m_dTradedPrice,o.m_strProductID) 
    print(o['m_nOrderStatus'])
    if o['m_nOrderStatus']==50:
        a=0
    if o['m_nVolumeTotalOriginal']==o['m_nVolumeTraded'] and type=='open' and o['m_strInstrumentID']=='HO2507-C-3000':
        strategyName=''
        type='over'

        redis_db.set('etf1000_code', json.dumps(etf1000_code))
        redis_message1000['etf1000_code']= etf1000_code
        redis_db.publish('etf1000_code',json.dumps(redis_message1000))
        print('ok')
        print(redis_message1000)
        #sys.exit()
            
    if o['m_nVolumeTotalOriginal']==o['m_nVolumeTraded'] and type=='close' and o['m_strInstrumentID']=='HO2507-C-3000':
            
        strategyName=''
        type='over'

        redis_db.set('etf1000_code_close_price', json.dumps(etf1000_code))
        redis_message1000['etf1000_code_close_price']= etf1000_code
        publish=redis_db.publish('etf1000_code',json.dumps(redis_message1000))
        print('ok')
        print(redis_message1000)
        #sys.exit()
    print(o['m_nVolumeTotalOriginal'],o['m_nVolumeTraded'],o['m_dTradedPrice'],o['m_strInstrumentID'])




hourly_max_ying = float('-inf')
hourly_max_ying2 = float('-inf')
minute_max_ying = float('-inf')
minute_max_ying2 = float('-inf')
ten_minute_max_ying = float('-inf')
ten_minute_max_ying2 = float('-inf')


# 获取当前时间信息初始化
now = datetime.now()
#current_hour = now.strftime("%Y%m%d%H")  # 去掉“-”
#current_minute = now.strftime("%Y%m%d%H%M")  # 去掉“-”和“：”
#current_ten_minute = f"{now.strftime('%Y%m%d%H')}{(now.minute // 10) * 10:02d}"  # 仅保留数字

current_hour = now.strftime("%Y-%m-%d %H")
current_minute = now.strftime("%Y-%m-%d %H:%M")
current_ten_minute = f"{now.strftime('%Y-%m-%d %H')}:{(now.minute // 10) * 10:02d}"

def record_max_values(ying, ying2):
    global hourly_max_ying, hourly_max_ying2
    global minute_max_ying, minute_max_ying2
    global ten_minute_max_ying, ten_minute_max_ying2
    global current_hour, current_minute, current_ten_minute

    # 判断并更新当前最大值和 Redis Zset
    if -100000 < ying < 100000:
        if ying > hourly_max_ying:  # 仅在当前值大于历史最大值时更新
            hourly_max_ying = ying
            redis_db.zadd(f'qq:ying_hour_max_list', {current_hour: hourly_max_ying})  # 使用 current_hour 作为 member，max_ying 作为 score

        if ying > minute_max_ying:
            minute_max_ying = ying
            redis_db.zadd(f'qq:ying_minute_max_list', {current_minute: minute_max_ying})  # 使用 current_minute 作为 member，max_ying 作为 score

        if ying > ten_minute_max_ying:
            ten_minute_max_ying = ying
            redis_db.zadd(f'qq:ying_ten_minute_max_list', {current_ten_minute: ten_minute_max_ying})  # 使用 current_ten_minute 作为 member，max_ying 作为 score

    if -100000 < ying2 < 100000:
        if ying2 > hourly_max_ying2:  # 仅在当前值大于历史最大值时更新
            hourly_max_ying2 = ying2
            redis_db.zadd(f'qq:ying2_hour_max_list', {current_hour: hourly_max_ying2})  # 使用 current_hour 作为 member，max_ying2 作为 score

        if ying2 > minute_max_ying2:
            minute_max_ying2 = ying2
            redis_db.zadd(f'qq:ying2_minute_max_list', {current_minute: minute_max_ying2})  # 使用 current_minute 作为 member，max_ying2 作为 score

        if ying2 > ten_minute_max_ying2:
            ten_minute_max_ying2 = ying2
            redis_db.zadd(f'qq:ying2_ten_minute_max_list', {current_ten_minute: ten_minute_max_ying2})  # 使用当前十分钟作为 member

    # 更新当前时间
    now = datetime.now()
    new_hour = now.strftime("%Y-%m-%d %H")
    new_minute = now.strftime("%Y-%m-%d %H:%M")
    new_ten_minute = f"{now.strftime('%Y-%m-%d %H')}:{(now.minute // 10) * 10:02d}"

    # 检查时间段变更
    if new_hour != current_hour:
        current_hour = new_hour
        # 当小时改变时，重置当前小时最大值
        hourly_max_ying = float('-inf')
        hourly_max_ying2 = float('-inf')

    if new_minute != current_minute:
        current_minute = new_minute
        # 当分钟改变时，重置当前分钟最大值
        minute_max_ying = float('-inf')
        minute_max_ying2 = float('-inf')

    if new_ten_minute != current_ten_minute:
        current_ten_minute = new_ten_minute
        # 当十分钟改变时，重置当前十分钟最大值
        ten_minute_max_ying = float('-inf')
        ten_minute_max_ying2 = float('-inf')
