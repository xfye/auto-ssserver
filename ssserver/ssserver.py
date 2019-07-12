#coding: utf-8
import time
import sys
import argparse
import json
import socket
import random
import uuid
import traceback
from config import *
from QcloudApi.qcloudapi import QcloudApi
from fabric.api import task, run
import fabric

def retry(func):
    def wrapper(self, *args, **kwargs):
        for i in range(3):
            try:
                return func(self, *args, **kwargs)
            except:
                if i != 2:
                    print('retry...')
                else:
                    raise
    return wrapper

def is_remote_tcp_port_alive(host, port):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3)
        try:
            sock.connect((host, port))
            return True
        except Exception:
            return False
    except Exception as ex:
        raise ex
    finally:
        sock.close()

class QCloudException(Exception):
    def __init__(self, code, message):
        self.code = code
        self.message = message

    def __str__(self):
        return 'QCloudException(code={},message={})'.format(self.code, self.message)

@task
def install_shadowsocks():
    run('sudo -u root apt-get update')
    run('sudo -u root curl https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py')
    run('sudo -u root python /tmp/get-pip.py')
    run('sudo -u root pip install shadowsocks')

@task
def start_ssserver():
    # Install
    run('sudo -u root apt-get update')
    run('sudo -u root curl https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py')
    run('sudo -u root python /tmp/get-pip.py')
    run('sudo -u root pip install shadowsocks')

    # Start
    run('sudo -u root ssserver -p 8387 -k \'{}\' -d start'.format(SSSERVER_PASSWORD))

class SSServerInstance(object):
    def __init__(self, secret_id, secret_key, ssserver_password, region, api_version):
        self.sg_name = 'ssserver-sg'
        self.sg_id = None
        self.instance_name = 'ssserver-host'
        self.instance_id = None
        self.secret_id = secret_id
        self.secret_key = secret_key
        self.region = region
        self.instance_password = ssserver_password
        self.api_version = api_version

    def _init_security_group(self):
        try:
            self.sg_id = self._get_security_group_id()
        except QCloudException as ex:
            print('Getting security group failed.')
            raise ex

        if self.sg_id is None:
            print('Security group () does not exist. Creating it.'.format(self.sg_name))
            try:
                self.sg_id = self._create_security_group()
            except QCloudException as ex:
                print('Creating security group () failed'.format(self.sg_name))
                raise ex

        try:
            self._init_security_group_policy(self.sg_id)
        except QCloudException as ex:
            print('Initializing security group policy failed.')
            raise ex

    def _get_api_config(self):
        return {
            'Region': self.region,
            'secretId': self.secret_id,
            'secretKey': self.secret_key,
            'Version': self.api_version
        }

    def _get_security_group_id(self):
        module = 'dfw'
        action = 'DescribeSecurityGroupEx'
        params = {
            'sgName': self.sg_name
        }
        service = QcloudApi(module, self._get_api_config())
        response = service.call(action, params)
        data = json.loads(response)
        if data['code'] == 0:
            # Succeeded
            for sg_item in data['data']['detail']:
                if sg_item['sgName'] == self.sg_name:
                    return sg_item['sgId']
            return None
        else:
            raise QCloudException(code=data['code'], message=data['message'])

    def _create_security_group(self):
        module = 'dfw'
        action = 'CreateSecurityGroup'
        params = {
            'sgName': self.sg_name
        }
        service = QcloudApi(module, self._get_api_config())
        data = json.loads(service.call(action, params))
        if data['code'] == 0:
            return data['data']['sgId']
        else:
            raise QCloudException(code=data['code'], message=data['message'])

    def _init_security_group_policy(self, sg_id):
        module = 'dfw'
        action = 'ModifySecurityGroupPolicys'
        params = {
            'sgId': sg_id,
            'ingress': [
                {
                    'ipProtocol': 'tcp',
                    'cidrIp': '0.0.0.0/0',
                    'portRange': 8387,
                    'desc': 'allow ssserver port',
                    'action': 'ACCEPT',
                },
                {
                    'ipProtocol': 'tcp',
                    'cidrIp': '0.0.0.0/0',
                    'portRange': 22,
                    'desc': 'ssh port',
                    'action': 'ACCEPT',
                }
            ],
            'egress': [
                {
                    'action': 'ACCEPT'
                }
            ]
        }
        service = QcloudApi(module, self._get_api_config())
        response = json.loads(service.call(action, params))
        if response['code'] != 0:
            raise QCloudException(code=response['code'], message=response['message'])

    def _get_instance_id(self):
        module = 'cvm'
        action = 'DescribeInstances'
        params = {
            'Limit': 1,
            'Filters': [
                {
                    'Name': 'instance-name',
                    'Values': [self.instance_name]
                }
            ]
        }
        service = QcloudApi(module, self._get_api_config())
        response = json.loads(service.call(action, params))
        if 'Error' in response['Response']:
            raise QCloudException(1, response['Response']['Error']['Message'])

        if 'InstanceSet' in response['Response'] and response['Response']['InstanceSet']:
            return response['Response']['InstanceSet'][0]['InstanceId']
        else:
            return None

    def describe_instances(self):
        module = 'cvm'
        action = 'DescribeInstances'
        params = {'Limit':1}
        service = QcloudApi(module, self._get_api_config())
        print(json.loads(service.call(action, params)))

    def _create_instance(self, token):
        module = 'cvm'
        action = 'RunInstances'
        params = {
            'Version': '2017-03-12',
            'InstanceChargeType': 'POSTPAID_BY_HOUR',
            'Placement': {
                'Zone': 'ap-hongkong-1',           # 香港一区
            },
            'InstanceType': 'S1.SMALL1',
            'ImageId': 'img-pyqx34y1',      # Ubuntu Server 16.04.1 LTS 64
            'InternetAccessible': {
                'InternetChargeType': 'TRAFFIC_POSTPAID_BY_HOUR',
                'InternetMaxBandwidthOut': 100
            },
            'InstanceName': self.instance_name,
            'LoginSettings': {
                'Password': self.instance_password,
            },
            'SecurityGroupIds': [self.sg_id],
            'ClientToken': token,
        }
        service = QcloudApi(module, self._get_api_config())
        response = json.loads(service.call(action, params))
        print(response)

        if 'Error' in response['Response']:
            raise QCloudException(1, response['Response']['Error']['Message'])

        if 'InstanceIdSet' in response['Response'] and response['Response']['InstanceIdSet']:
            print(response)
            return response['Response']['InstanceIdSet'][0]
        else:
            return None

    def _destroy_instance(self, instance_id):
        module = 'cvm'
        action = 'TerminateInstances'
        params = {
            'Version': '2017-03-12',
            'InstanceIds': [instance_id],
        }
        service = QcloudApi(module, self._get_api_config())
        response = json.loads(service.call(action, params))

        if 'Error' in response['Response']:
            raise QCloudException(1, response['Response']['Error']['Message'])

    def describe_images(self):
        module = 'image'
        action = 'DescribeImages'
        params = {
            'Limit': 30,
        }
        service = QcloudApi(module, self._get_api_config())
        response = json.loads(service.call(action, params))
        return response['Response']['ImageSet']

    def describe_zones(self):
        module = 'cvm'
        action = 'DescribeZones'
        params = {
        }
        service = QcloudApi(module, self._get_api_config())
        print(json.loads(service.call(action, params)))

    def _describe_instance(self, instance_id):
        module = 'cvm'
        action = 'DescribeInstances'
        params = {
            'InstanceIds': [instance_id],
        }
        service = QcloudApi(module, self._get_api_config())
        response = json.loads(service.call(action, params))

        if 'Error' in response['Response']:
            raise QCloudException(1, response['Response']['Error']['Message'])

        if 'InstanceSet' in response['Response'] and response['Response']['InstanceSet']:
            return response['Response']['InstanceSet'][0]
        else:
            return None

    @retry
    def _get_instance_public_ip(self, instance_id):
        try:
            instance = self._describe_instance(instance_id)
            if (instance is not None) and ('PublicIpAddresses' in instance) and (instance['PublicIpAddresses']):
                return instance['PublicIpAddresses'][0]
            else:
                return None
        except QCloudException as ex:
            print('Getting instance public ip failed.')
            print(ex)
            raise ex

    def _start_ssserver(self):
        fabric.tasks.execute(start_ssserver, hosts=['ubuntu@{}'.format(self.instance_public_ip)])

    def start(self):
        try:
            self._init_security_group()
        except QCloudException as ex:
            print('Initializing security group failed.')
            print(ex)
            return None

        try:
            self.instance_id = self._get_instance_id()
            if self.instance_id is None:
                print('The instance does not exist.')
        except QCloudException as ex:
            print('Getting instance id failed. {}'.format(ex))
            return None

        try:
            if self.instance_id is None:
                print('The instance does not exist. Creating it.')
                self.instance_id = self._create_instance(str(uuid.uuid4()))
                print('The instance is created. id={}'.format(self.instance_id))
        except QCloudException as ex:
            print('Creating instance failed.')
            print(ex)
            return None

        while True:
            self.instance_public_ip = self._get_instance_public_ip(self.instance_id)
            if self.instance_public_ip is not None:
                break
            else:
                print('The public address of the instance is not ready. sleep(5) and retry.')
                time.sleep(5)

        while True:
            if is_remote_tcp_port_alive(self.instance_public_ip, 22):
                break
            print('22 port of the instance is not ready. sleep(5) and retry.')
            time.sleep(5)

        self._start_ssserver()

        return self.instance_public_ip

    def destroy(self):
        try:
            self.instance_id = self._get_instance_id()
            if self.instance_id is None:
                print('The instance does not exist.')
                return True
            else:
                self._destroy_instance(self.instance_id)
                return True
        except QCloudException as ex:
            print(traceback.format_exc())
            return False

    def get_public_ip(self):
        try:
            self.instance_id = self._get_instance_id()
            if self.instance_id is None:
                print('The instance does not exist.')
                return None
        except QCloudException as ex:
            print('Getting instance id failed. {}'.format(ex))
            return None

        try:
            return self._get_instance_public_ip(self.instance_id)
        except QCloudException as ex:
            return None

def cmd_start():
    ss = SSServerInstance(secret_id=SECRET_ID,
                          secret_key=SECRET_KEY,
                          ssserver_password=SSSERVER_PASSWORD,
                          region=REGION,
                          api_version=API_VERSION)
    instance_public_ip = ss.start()
    if instance_public_ip is not None:
        print('ssserver started successfully.')
        print('public ip is {}'.format(instance_public_ip))
    else:
        print('ssserver starting failed.')

def cmd_stop():
    ss = SSServerInstance(secret_id=SECRET_ID,
                          secret_key=SECRET_KEY,
                          ssserver_password=SSSERVER_PASSWORD,
                          region=REGION,
                          api_version=API_VERSION)
    if ss.destroy():
        print('The instance is destroyed successfully.')

def cmd_show():
    ss = SSServerInstance(secret_id=SECRET_ID,
                          secret_key=SECRET_KEY,
                          ssserver_password=SSSERVER_PASSWORD,
                          region=REGION,
                          api_version=API_VERSION)
    public_ip = ss.get_public_ip()
    if public_ip is not None:
        print(public_ip)

def main(argv):
    parser = argparse.ArgumentParser(prog='ssserver')
    subparsers = parser.add_subparsers(help='sub-command help')

    parser_start = subparsers.add_parser('start')
    parser_start.set_defaults(func=cmd_start)

    parser_stop = subparsers.add_parser('stop')
    parser_stop.set_defaults(func=cmd_stop)

    parser_show = subparsers.add_parser('show')
    parser_show.set_defaults(func=cmd_show)

    args = parser.parse_args()
    args = vars(args)
    if 'func' not in args:
        parser.print_help()
        return 1
    else:
        func = args.pop("func")
        return func()

if __name__ == '__main__':
    main(sys.argv[1:])
