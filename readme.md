# danmaku bot

---

使用websocket异步方法获取B站直播弹幕、SC、礼物等消息

#### 功能：

- 解析websocket服务器消息
- 自动检测开播状态
- 支持房间号短ID
- 下载标准xml格式直播弹幕文件
- 下载直播封面
- CMD简易实时弹幕栏显示

---

#### 使用方法：

1. 命令行直接运行  
`python dmbot.py {房间号} -dl(可选)`  
默认不启动弹幕文件及封面下载，在最后输入`-dl`后开启。

2. 继承重写方法  
Class: `Client`  
function: 
    - `async def do_danmaku(self, data)` : 需要返回`ts`发送时间, `uid`用户ID, `text`文本， 用于写入xml文件。
    - `async def do_SC(self, data)`
    - `async def do_buy_guard(self, data)`
    - `async def do_gift(self, data)`
    - `async def do_welcome_guard(self, data)`
    - `async def do_heartbreak_reply(self, data)`
    - `async def do_auth_reply(self, data)`