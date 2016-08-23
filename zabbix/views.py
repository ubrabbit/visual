# <coding:utf-8>
from django.shortcuts import HttpResponse
from django.views.generic import View

from tool import spider
import re
import json
from conf import *
from tool import keycache

# 用途：传一个ip，返回两组html标签。分别为该ip的一天和七天流量记录
# 流程：查询ip是交换机ip还是服务器ip

# demo host:http://127.0.0.1/zabbix/chart/113.106.204.9
# demo switch:http://127.0.0.1/zabbix/chart/113.106.204.126

g_object_key_store = keycache.CKeyStore(STR_PATH_KEY_VALUE)


class CZabbix(View, spider.CSpider):
    m_zabbix_chart_full = 'http://10.32.18.176:8088/zapi/graph/?id=123&ip={0}&type={1}'  # {0}为ip，type为’host‘或者‘switch’
    m_zabbix_chart_traffic = 'http://10.32.64.64/zabbix/chart2.php?graphid={0}&period={1}&updateProfile=1&profileIdx=web.screens&width=700'
    m_dict_map = DICT_SWITCH_MAP

    def __init__(self):
        # 为了方便获得数据，使用一个字典来维持在该类中需要用到的参数。这样数据传递不会乱，而且数据结构直观
        self.m_dict_ret = {
            'traffic': {
                '1day': self.m_zabbix_chart_traffic,
                '7day': self.m_zabbix_chart_traffic,
                'graphid': '',  # 对应zabbix的graph id
            },
            'type': '',  # host or switch
            'ip': '',
            'line': '',  # 线路，不同线路能使用一个交换机ip，所以单靠交换机ip无法区分线路
        }

    # 判断一个ip返回的信息是交换机所有的
    def get_info(self):
        '''
        :return: 返回zabbix接口中关于一个ip的所有信息
        '''
        str_ip = self.m_dict_ret['ip']
        if str_ip in self.m_dict_map:
            str_api_url_zabbix = self.m_zabbix_chart_full.format(str_ip, 'switch')
            self.m_dict_ret['type'] = 'switch'
        else:
            str_api_url_zabbix = self.m_zabbix_chart_full.format(str_ip, 'host')
            self.m_dict_ret['type'] = 'host'
        json_info = self.ReadJson(str_api_url_zabbix)
        return json_info

    def get_server_chart_url(self, list_ret):
        for dict_item in list_ret:
            if 'Traffic on interface eth0' in dict_item:
                str_url = dict_item['Traffic on interface eth0']
                return str_url
        return ''

    def get_switch_chart_url(self, list_ret):
        str_interface = get_interface(self.m_dict_ret['ip'], self.m_dict_ret['line'])
        for dict_interface_url in list_ret:
            for str_full_interface, str_url in dict_interface_url.iteritems():
                if str_interface in str_full_interface:
                    return str_url

    def get_chart_url(self, json_info):
        '''
        :param json_info:
        :return: 类型#http://10.32.64.64/zabbix/chart2.php?graphid=50832&period=3600&updateProfile=1&profileIdx=web.screens&width=900
        '''
        if not json_info:
            return ''
        if not isinstance(json_info, dict):
            return ''
        if not json_info.has_key('result'):
            return ''
        ret = json_info['result']
        if isinstance(ret, dict):
            # 字典说明错了
            return ''
        if self.m_dict_ret['type'] == 'host':
            str_traffic_url_demo = self.get_server_chart_url(ret)
        elif self.m_dict_ret['type'] == 'switch':
            str_traffic_url_demo = self.get_switch_chart_url(ret)
        else:
            str_traffic_url_demo = ''
        return str_traffic_url_demo

    def get_graph_id(self, str_traffic_url_demo):
        '''
        :param str_traffic_url_demo: 例如# http://10.32.64.64/zabbix/chart2.php?graphid=50832&period=3600&updateProfile=1&profileIdx=web.screens&width=600
        :return: None。仅仅从demo url中提取出 graph id 保存起来
        '''
        if not str_traffic_url_demo:
            return ''
        object_ret = re.search('(?<=graphid=)\d+', str_traffic_url_demo)
        if object_ret:
            self.m_dict_ret['traffic']['graphid'] = object_ret.group(0)

    def assemble(self):
        str_graph_id = self.m_dict_ret['traffic']['graphid']
        if not str_graph_id:
            return ''
        self.m_dict_ret['traffic']['1day'] = self.m_zabbix_chart_traffic.format(str_graph_id, 60 * 60 * 24)
        self.m_dict_ret['traffic']['7day'] = self.m_zabbix_chart_traffic.format(str_graph_id, 60 * 60 * 24 * 7),

    def is_enable_args_format(self, *args, **kwargs):
        if len(args) == 1:
            return 1
        # 需要一个ip
        return 0

    def clear(self):
        self.__init__()

    def has_cache(self):
        if g_object_key_store.has_key(self.m_dict_ret['ip']):
            return 1
        return 0

    def add_cache(self, json_chart_info):
        if not self.m_dict_ret['traffic']['graphid']:
            return
        dict_cache = {
            self.m_dict_ret['ip']: json_chart_info
        }
        g_object_key_store.store(dict_cache)

    def read_cache(self, str_ip):
        str_chart_info = g_object_key_store.key(str_ip)
        # print  '读取缓存', str_chart_info
        dict_chart_info = eval(str_chart_info)
        json_chart_info = json.dumps(dict_chart_info)
        return json_chart_info

    def new_info(self):
        json_info = self.get_info()
        str_traffic_url_demo = self.get_chart_url(json_info)  # 强尧的demo url，其中包含了图形对应的graph id
        self.get_graph_id(str_traffic_url_demo)
        self.assemble()
        json_chart_info = json.dumps(self.m_dict_ret)
        return json_chart_info

    def get(self, request, *args, **kwargs):
        self.clear()  # 清理上次执行时遗留的数据
        if request.method == 'GET':  # and request.is_ajax():
            self.m_dict_ret['ip'] = request.GET.get('ip')
            self.m_dict_ret['line'] = request.GET.get('line')
        if self.has_cache():  # 检查是否有缓存数据可用。缓存可能导致数据不更新，需要删除缓存文件以让程序重新获得数据
            json_chart_info = self.read_cache(self.m_dict_ret['ip'])
        else:
            json_chart_info = self.new_info()
            self.add_cache(json_chart_info)
        return HttpResponse(json_chart_info)

        # 报错文档：
        # 'str' object has no attribute 'get'
        # return 的必须是 HttpResponse()，其他django方法只是做了封装
