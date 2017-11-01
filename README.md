# auto-ssserver

This small program will do the following things.

1. Creates s security group named `ssserver-sg` and opens port 22 (sshd port) and 8387 (ssserver port) to the world.
2. Buys a `S1.SMALL1` instance on QCloud www.qcloud.com based on your secrete id and secrete key.
3. Installs and starts ssserver binding to port 8387.

After that, you can use a shadowsocks client to connect to the server.

Have fun!

## Install

```
git clone https://github.com/xfye/auto-ssserver.git
pip install -r requirements.txt
```

## Config

config.py example:

```
SECRET_ID = 'your secret id'
SECRET_KEY = 'your secrete key'
SSSERVER_PASSWORD = 'qq#baidu.com'
REGION = 'hk'
API_VERSION = '2017-03-20'
```

## Usage

- Start a Shadowsocks server.

```
python ssserver.py start
```

- Stop the server

```
python ssserver.py start
```

- Show the server's public IP

```
python ssserver.py start
```
