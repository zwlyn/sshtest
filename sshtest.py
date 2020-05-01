#-*- coding:utf-8 -*-
# apt-get install python3-paramiko
import paramiko
import threading
import time
import json
import pymysql
from log import logger
from apscheduler.schedulers.background import BackgroundScheduler
import datetime
import random
import os
import ipaddress

Lock = threading.Lock()

class SshTest(object):
    def __init__(self, configPath=None):
        self.configPath = configPath
        if self.configPath is None:
            with open("config.json", "r") as f:
                config = json.load(f)
                dbconfig = config['dbconfig']
        else:
            with open(self.configPath, "r") as f:
                config = json.load(f)
                dbconfig = config['dbconfig']

        self.dbname = dbconfig['database']
        self.tablename = dbconfig['table']
        self.dbhost = dbconfig['host']
        self.user = dbconfig['user']
        self.password = dbconfig['password']
        self.port = dbconfig['port']
        self.testnum = int(config['testnum'])
        self.interval = int(config['interval'])

        logger.info("config: %s" % json.dumps(config, indent=4))
        self.conn = pymysql.connect(host=self.dbhost, port=self.port, user=self.user, passwd=self.password)
        self.cursor = self.conn.cursor()
        self.cursor.execute("create database if not exists %s" % self.dbname)
        self.cursor.execute('use %s' % self.dbname)
        self.cursor.execute("select database()")
        sql = '''
        create table if not exists %s(
        host char(255),
        category char(255),
        state char(255),
        testTime char(255),
        primary key(host)
        );
        ''' % self.tablename

        self.cursor.execute(sql)

        self.startTime = None
        self.onlineMap = {
            "DigitalOcean":0,
            "GoogleCloud":0,
            "MicrosoftAzureCloud":0,
            "AmazonWebService":0
        }
        self.timer = time.time()


    def insertInfo(self, host, category, state, testTime):
        sql = '''insert into %s(host,category,state,testTime)
                 values("%s","%s","%s","%s")
                 on duplicate key update category=values(category),state=values(state),
                 testTime=values(testTime);
              ''' % (self.tablename, host, category, state, testTime)

        global Lock
        Lock.acquire()

        self.cursor.execute(sql)
        self.conn.commit()

        Lock.release()


    def ssh(self, host, category=""):
        try:
            testTime = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            transport = paramiko.Transport((host, 22))
            self.insertInfo(host, category, "online", testTime)
            self.onlineMap[category] += 1
            logger.info("category:%s OnlineNum: %d, host: %s " % (category, self.onlineMap[category], host))
        except Exception as e:
            logger.error(e)
            logger.info("%s connect error" % category)
            #insertInfo(host, category, "disconnect", testTime)

    def createThread(self, target, args, join=False):
        if join is False:
            newThread = threading.Thread(target=self.ssh, args=args)
            newThread.start()
        else:
            newThread = threading.Thread(target=self.ssh, args=args)
            newThread.start()
            newThread.join()


    def getIpBlocks(self, category):
        with open("data/%s_ipblocks.json" % category, 'r') as f:
           ipBlockList = (json.load(f)['ipList'])

        return ipBlockList

    def loadHugeIpList(self, category):
        '''only design for MicrosoftAzureCloud and AmazonWebService,
           Because their data is so huge, need to compute.
        '''
        ipBlockList = self.getIpBlocks(category)
        blockRandom = random.sample(ipBlockList, 1000)
        randomList = []
        for ipblock in blockRandom:
            net = ipaddress.ip_network(ipblock)
            ipList = []
            for ip in net.hosts():
                ipList.append(str(ip))

            if len(ipList) == 0:
                randomNum = 0
            elif len(ipList) < 50:
                randomNum = len(ipList)
            else:
                randomNum = 50
            randomList.extend(random.sample(ipList, randomNum))
            if len(randomList) > self.testnum:
                randomList = randomList[:self.testnum]
                break
        return {
            "randomList": randomList,
            "category": category
            }

    def loadIpList(self, category):
        '''get dict with randomList and category
           param category is in "DigitalOcean", "GoogleCloud", "MicrosoftAzureCloud" 
           and "AmazonWebService"
        '''
        if category in ['MicrosoftAzureCloud', 'AmazonWebService']:
            return self.loadHugeIpList(category)

        filename = os.sep.join(["data", category + ".json"])

        with open(filename, 'r') as f:
           ipList = (json.load(f)['ipList'])
           logger.info("%s load success." % filename)
        
        randomList = random.sample(ipList, self.testnum)
        return {
            "randomList": randomList,
            "category": category
            }

    def record(self):
        '''save test time and Oline record to record.json
        '''
        if os.path.exists("record.json") is False:
            with open("record.json", "w") as f:
                f.write(json.dumps({"testList":[]}, indent=4))

        with open("record.json", "r") as f:
            msg = json.load(f)['testList']

        if self.onlineMap == {
            "DigitalOcean":0,
            "GoogleCloud":0,
            "MicrosoftAzureCloud":0,
            "AmazonWebService":0
        }:
            return

        msg.append({
            "startTime": self.startTime,
            "Online": self.onlineMap
        })
        with open("record.json", "w") as f:
            f.write(json.dumps({
                "testList": msg
                }, indent=4))

        # init Online
        self.onlineMap = {
            "DigitalOcean":0,
            "GoogleCloud":0,
            "MicrosoftAzureCloud":0,
            "AmazonWebService":0
        }
        return

    def backupRecord(self):
        if os.path.exists("record.json"):
            os.rename("record.json", "record.backup%s.json" % datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))
            return

    def main(self):
        #try:
        self.startTime = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        self.record()
        self.timer = time.time()
        
        if self.configPath is None:
            mapList = []
            categoryList = ['DigitalOcean', 'AmazonWebService', 'MicrosoftAzureCloud']
            #categoryList = ['AmazonWebService', 'MicrosoftAzureCloud']
            for category in categoryList:
                loadIpMap = self.loadIpList(category) 
                mapList.append(loadIpMap)

            for item in mapList:
                for host in item['randomList']:
                    logger.info("current thread num:%d" % len(threading.enumerate()))
                    if len(threading.enumerate()) <= 11300:
                        self.createThread(self.ssh, (host, item['category']))
                    else:
                        self.createThread(self.ssh, (host, item['category']), join=True)

        # except Exception as e:
        #     logger.error(e)

def schedule(task, interval):    
    # sshTest.main()
    # sshTest.record()
    schedulers = BackgroundScheduler()
    schedulers.add_job(task, 'interval', seconds=interval)
    schedulers.start()
    while True:
        time.sleep(5)

    conn.close()

if __name__ == '__main__':
    sshTest = SshTest()
    sshTest.backupRecord()
    schedule(sshTest.main, sshTest.interval)



