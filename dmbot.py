import asyncio
import zlib
import websockets
import json
import requests
import struct
import time as _time
import os
import sys

STRUCT = struct.Struct(">I2H2I")
PATH = "./"
DANMAKU_FILE = "danmaku"
COVER_FILE = "cover"
DANMU_INFO = "https://api.live.bilibili.com/xlive/web-room/v1/index/getDanmuInfo?id="
ROOM_INFO = "https://api.live.bilibili.com/xlive/web-room/v1/index/getInfoByRoom?room_id="
DEFAULT_HOST = {"host": "broadcastlv.chat.bilibili.com", "wss_port": "443"}

HEADER = {
    "Referer": "https://www.bilibili.com/",
    "accept-encoding": "gzip, deflate, br",
    "accept": "*/*",
    "sec-fetch-site": "same-site",
    "sec-fetch-mode": "no-cors",
    "sec-fetch-dest": "script",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/86.0.4240.183 Safari/537.36 Edg/86.0.622.63",
    "Accept-language": "zh-CN,zh;q=0.9,en;q=0.8,ja;q=0.7,en-GB;q=0.6,en-US;q=0.5",
}

XML_FRAME = '''<?xml version='1.0' encoding='UTF-8'?>
<i>
<chatserver>chat.bilibili.com</chatserver>
<chatid>114514</chatid>
<mission>0</mission>
<maxlimit>100000</maxlimit>
<state>0</state>
<real_name>0</real_name>
<source>k-v</source>
</i>'''

class VER:
    JSON = 0
    INT = 1
    BUFFER = 2

class OPERATION:
    HANDSHAKE = 0
    HANDSHAKE_REPLY = 1
    HEARTBEAT = 2
    HEARTBEAT_REPLY = 3
    SEND_MSG = 4
    SEND_MSG_REPLY = 5
    DISCONNECT_REPLY = 6
    AUTH = 7
    AUTH_REPLY = 8
    RAW = 9
    PROTO_READY = 10
    PROTO_FINISH = 11
    CHANGE_ROOM = 12
    CHANGE_ROOM_REPLY = 13
    REGISTER = 14
    REGISTER_REPLY = 15
    UNREGISTER = 16
    UNREGISTER_REPLY = 17

def pack(data, operation):
    body = json.dumps(data).encode("utf-8")
    header = STRUCT.pack(
        STRUCT.size + len(body),
        STRUCT.size,
        1,
        operation,
        1,
    )
    return header + body

class Clint:
    def __init__(self, roomid, download=False, trans=False, update_interval=3, heartbeat_interval=30):
        self._roomid = int(roomid)
        self.download = download
        self.trans = trans
        self.update_interval = update_interval
        self.heartbeat_interval = heartbeat_interval
        self.hot = 0
        self.xml_path = f'{PATH}/{DANMAKU_FILE}/'
        self.cover_path = f'{PATH}/{COVER_FILE}/'
        if download == True:
            if not os.path.exists(self.xml_path):
                os.mkdir(self.xml_path)
            if not os.path.exists(self.cover_path):
                os.mkdir(self.cover_path)
        try:
            self.getRoomInfo()
        except:
            print("Error when getting room info.")


    def start(self):
        self.getHostList()
        try:
            asyncio.get_event_loop().run_until_complete(self.loop())
        except KeyboardInterrupt:
            print("exit.")

    async def loop(self):
        retry = 0
        while True:
            try:
                host = self.host_list[retry]
                async with websockets.connect(f'wss://{host["host"]}:{host["wss_port"]}/sub') as websocket:
                    self.websocket = websocket
                    await self.sendEnterMsg()
                    tasks = [
                        self.getMessage(), 
                        self.updateRoomInfo(),
                        self.sendHeartBeat(),
                    ]
                    await asyncio.wait(tasks)
            except asyncio.TimeoutError:
                print("! Timeout.")
                retry = retry + 1
                await asyncio.sleep(1)
                continue
            except BaseException as e:
                print(e)
                break

    def getRoomInfo(self):
        url = ROOM_INFO + str(self._roomid)
        r = requests.get(url, headers=HEADER)
        roomInfo = json.loads(r.text)["data"]["room_info"]
        self.live_sataus = roomInfo["live_status"]
        self.roomid = roomInfo["room_id"]
        self.title = roomInfo["title"]
        self.cover = roomInfo["cover"]
        self.start_time = roomInfo["live_start_time"] 
        self.file_name = '[' + str(self._roomid) + ']' + _time.strftime("%Y.%m.%d %H-%M-%S", _time.localtime(self.start_time))
        # write xml frame and cover
        if self.download and self.live_sataus:
            if not os.path.exists(self.xml_path + self.file_name + '.xml'):
                # xml frame
                with open(self.xml_path + self.file_name + '.xml', "w", encoding="utf-8") as f:
                    f.write(XML_FRAME)
            if not os.path.exists(self.cover_path + self.file_name + '.png'):
                # cover
                r = requests.get(self.cover, headers=HEADER)
                with open(self.cover_path + self.file_name + '.png', "wb") as f:
                    f.write(r.content)

    async def updateRoomInfo(self):
        while True:
            try:
                self.getRoomInfo()
                await asyncio.sleep(self.update_interval)
            except (requests.exceptions.ProxyError, requests.exceptions.ChunkedEncodingError):
                print("ConnectError in getting room info.")
                await asyncio.sleep(3)
                self.getRoomInfo()

    def getHostList(self):
        try:
            url = DANMU_INFO + str(roomid)
            r = requests.get(url, headers=HEADER)
            self.host_list = json.loads(r.text)["data"]["host_list"]
            self.token = json.loads(r.text)["data"]["token"]
        except:
            self.host_list = [DEFAULT_HOST]
            self.token = None

    async def sendEnterMsg(self):
        body = {
            "uid": 0,
            "roomid": self.roomid,
            "protover": 2,
            "platform": "web",
            "clientver": "1.14.3",
            "type": 2,
        }
        if self.token:
            body["key"] = self.token
        await self.websocket.send(bytes(pack(body, OPERATION.AUTH)))

    async def sendHeartBeat(self):
        while True:
            await self.websocket.send(bytes(pack({}, OPERATION.HEARTBEAT)))
            await asyncio.sleep(self.heartbeat_interval)

    async def getMessage(self):
        while True:
            msg = await self.websocket.recv()
            await self.handelMsg(msg)

    async def handelMsg(self, msg):
        packetLength, headerLength, ver, operation, seqId = STRUCT.unpack_from(msg, 0)
        
        # 数据包相连时
        if packetLength < len(msg):
            await self.handelMsg(msg[packetLength:])
            msg = msg[:packetLength]

        body = msg[headerLength:]

        # 信息
        if operation == OPERATION.SEND_MSG_REPLY:
            # 解压
            if ver == VER.BUFFER:
                body = zlib.decompress(body)
                await self.handelMsg(body)
            else:
                body = json.loads(body.decode("utf-8"))

                # 弹幕
                if body['cmd'] == "DANMU_MSG":
                    ts, uid, text = await self.do_danmaku(body["info"])
                    if self.live_sataus:
                        if self.download:
                            await self.dl_danmaku(ts-self.start_time, ts, uid, text)
                        if self.trans:
                            await self.dl_trans(ts-self.start_time, ts, uid, text)

                # SC
                elif body['cmd'] == "SUPER_CHAT_MESSAGE":
                    await self.do_SC(body["data"])
                # SC_JPN (重复)
                elif body['cmd'] == "SUPER_CHAT_MESSAGE_JPN":
                    #await self.do_SC(body["data"])  #重复显示
                    pass
                # 欢迎舰长
                elif body['cmd'] == "WELCOME_GUARD":
                    await self.do_welcome_guard(body["data"])
                # 礼物
                elif body['cmd'] == "SEND_GIFT":
                    await self.do_gift(body["data"])
                # 舰长
                elif body['cmd'] == "GUARD_BUY":
                    await self.do_buy_guard(body["data"])

        # 心跳回应
        elif operation == OPERATION.HEARTBEAT_REPLY:
            await self.do_heartbreak_reply(body)
        
        # 进房回应
        elif operation == OPERATION.AUTH_REPLY:
            await self.do_auth_reply(body)
        
        # 其他消息
        else:
            #print(body)
            pass
    
    async def dl_danmaku(self, time, ts, uid, text):
        with open(self.xml_path + self.file_name + '.xml', "r", encoding="utf-8") as f:
            res = f.read()
            context = res[:-4] + f'<d p="{time},1,25,16777215,{ts},0,{uid},0">{text}</d>\n</i>'
            with open(self.xml_path + self.file_name + '.xml', "w", encoding="utf-8") as f:
                f.write(context)

    async def dl_trans(self, time, ts, uid, text):
        if text[0] == "【" and text[-1] == "】":
            ts = _time.strftime("%H:%M:%S", _time.localtime(ts))
            m, s = divmod(int(time), 60)
            h, m = divmod(m, 60)
            time = str("%d:%02d:%02d" % (h, m, int(s)))
            with open(self.xml_path + self.file_name + ".txt", "a", encoding="utf-8") as f:
                context = "[{}][{}]{} ({})\n".format(ts, time, text, uid)
                f.write(context)

    async def do_danmaku(self, data):
        text = data[1]
        user = data[2][1]
        uid = data[2][0]
        ts = data[9]["ts"]  # timestamp
        print(f'- {user}: {text}')
        return ts, uid, text

    async def do_SC(self, data):
        SCid = data["id"]
        uid = data["uid"]
        user = data["user_info"]["uname"]
        price = data["price"]
        msg = data["message"]
        if data.__contains__("message_trans"):
            if data["message_trans"] != "":
                msg_JPN = f'({data["message_trans"]})' + '\n'
        #elif data.__contains__("message_jpn"):
            #msg_JPN = f'({data["message_jpn"]})'
        else:
            msg_JPN = ""
        #time = data["time"]  # duration(second)
        #start_time = data["start_time"]
        #end_time = data["end_time"]
        print(f'[￥{price}] {msg}\n    {msg_JPN}    .by {user}')

    async def do_buy_guard(self, data):
        uid = data["uid"]
        user = data["username"]
        gift = data["gift_name"]
        print(f'[Member({gift})] by {user}')

    async def do_gift(self, data):
        uid = data["uid"]
        user = data["uname"]
        price = data["price"]
        gift = data["giftName"]
        time = data["timestamp"]
        num = data["num"]
        print(f'[{gift}] X {num} by {user}')

    async def do_welcome_guard(self, data):
        #uid = data["uid"]
        #user = data["username"]
        #level = data["guard_level"]  # 总督，提督，舰长 = 1，2，3
        pass

    async def do_heartbreak_reply(self, data):
        hot = int.from_bytes(data, 'big')
        if self.hot:
            if hot / 1000000 > 1 and (hot / 1000000 - int(self.hot / 1000000)) >= 1:
                print(f'[int({hot}/1000000)*1000000 人气达成]')
        self.hot = hot

    async def do_auth_reply(self, data):
        pass

if __name__ == "__main__":
    params = sys.argv[1:]
    if len(params) > 0:
        dl = True if "-dl" in params else False
        trans = True if "-tr" in params else False
        clint = Clint(params[0], download=dl, trans=trans)
    else:
        raise Exception("Params Error")
    clint.start()