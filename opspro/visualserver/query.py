#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 16-7-28 下午4:22
# @Author  : youzeshun
# 数据查询api,将查询到的机房实时流量数据和机房最大带宽数据进行组合
# 有逻辑上的处理，如排序等
import idcconf
import spider
import collections
from opspro.public.define import *

g_oSpider = spider.CSpider()


# 不能获得数据则报警，并且记录原因。以便处理
def GetIPTop():
    jIPTop = g_oSpider.ReadJson(idcconf.URL_IDC_TOP)
    return eval(str(jIPTop))  # 先转json是为了避免中文未被编码。转dict是因为python遍历json对象有问题，目前没有定位问题。所以转为字典进行后续遍历


def GetIDCTraff():
    jIDCTraff = g_oSpider.ReadJson(idcconf.URL_IDC_TRFF)
    return eval(str(jIDCTraff))


def IsEnableFormat(dData):
    if not isinstance(dData, dict):
        return 0
    if not 'result' in dData:
        return 0
    if not u'netout' in dData['result']:
        return 0
    return 1


def GetIPTraff(sIP):
    sUrl = "%s%s" % (idcconf.URL_SERVER_INFO, sIP)
    jServerInfo = g_oSpider.ReadJson(sUrl)
    if not IsEnableFormat(jServerInfo):
        ExecManagerFunc('alert', 'Alert', '不可用的服务器信息', YouZeShun)
        return None
    return jServerInfo


def getTotalTop(dAllIP, dAllIPInfo):
    '''
    @param dAllIP: 所有服务器ｉｐ和流量的对应关系，格式{ip:流量}
    @param dAllIPInfo: 所有服务器ｉｐ的详细信息,格式｛ip:{"usage": "用途", "ip": "xxx", "traffic":浮点数流量, "tenant": "供应商"}｝
    @return:流量最高的十个ip的信息，用于机房总计圆饼图的外环
    '''
    # sort是又大到小，sorted是由小到大
    lstAllIP = sorted(dAllIP.iteritems(), key=lambda d: d[1], reverse=True)
    lstAllIP = lstAllIP[0:10]
    dTotalTop = collections.OrderedDict()
    # print fTotalUsed, iTotalBand,int(fTotalUsed - fTotalTopUsed)
    for i in lstAllIP:
        sIP = i[0]
        dTotalTop[sIP] = dAllIPInfo[sIP]
    return dTotalTop


def getServerRoomTop(sServerRoom, jIPTop):
    if sServerRoom in jIPTop:
        # print '缓存信息：', sServerRoom, jIPTop[sServerRoom]
        listServerRoomTop = jIPTop[sServerRoom]
        # print '对 {0} 进行了top10的缓存'.format(Transcoding(sServerRoom))
        ExecManagerFunc('cache', 'store', {sServerRoom: listServerRoomTop})
    elif ExecManagerFunc('cache', 'has_key', sServerRoom):
        sServerRoomTop = ExecManagerFunc('cache', 'key', sServerRoom)
        listServerRoomTop = eval(sServerRoomTop)
        # print sServerRoom, '使用缓存数据', ExecManagerFunc('cache', 'all')
        str_error = '机房: %s 没有Top10数据,已经使用了缓存数据' % Transcoding(sServerRoom)  # 按照utf-8进行编码
        ExecManagerFunc('alert', 'Alert', str_error, YouZeShun, 60 * 60)
        ExecManagerFunc('log', 'WriteLog', str_error, 'status/error')
    else:
        str_error = '机房: %s 没有Top10数据,连缓存都没有' % Transcoding(sServerRoom)  # 按照utf-8进行编码
        ExecManagerFunc('alert', 'Alert', str_error, YouZeShun, 60 * 60)
        listServerRoomTop = []
    return listServerRoomTop


def getDataEchart(dDataEchart, sServerRoom, sLine, fUsedBand, iTotalLineBand, dEchartOuter, sInnerName):
    if not sServerRoom in dDataEchart:
        dDataEchart[sServerRoom] = {}
    dDataEchart[sServerRoom][sLine] = {
        'inner': {
            'used': fUsedBand,
            'total': iTotalLineBand
        },
        'outer': dEchartOuter,
        'inner_name': sInnerName,
    }
    return dDataEchart


def getOtherUseBand(dOtherUsedBand, sServerRoom, iTotalServerUsedBand, fTopUsed):
    iOther = int(iTotalServerUsedBand - fTopUsed)
    if iOther < 0:
        iOther = 0
    if iOther < -iTotalServerUsedBand * 0.1:
        sMsg = '机房流量Top10大于机房已用流量，且误差大于已用流量的10%。机房已用流量：{0}，TOp10流量：{1}'.format(iTotalServerUsedBand, int(fTopUsed))
        ExecManagerFunc('alert', 'Alert', sMsg, YouZeShun)
    if not sServerRoom in dOtherUsedBand:
        dOtherUsedBand[sServerRoom] = {}
    dOtherUsedBand[sServerRoom]['other'] = iOther  # 除了top10使用的
    dOtherUsedBand[sServerRoom]['used'] = iTotalServerUsedBand
    return dOtherUsedBand


# 合并机房流量数据和机房top10数据，转为echart 的接口需要的数据形式。这里可以转为能被echart读取的格式
def GetDataEchart(jIDCTraff, jIPTop):
    '''
    确定无法精简，拆分本方法不会让代码更易读
    @param jIDCTraff: 线路流量
    @param jIPTop: top10数据
    @return: 合并后的字典，echart外圆的other字段
    '''
    if not jIDCTraff or not jIPTop:
        return {}, {}
    dDataEchart = collections.OrderedDict()
    # 机房各个线路的可用带宽之和
    iTotalBand = 0  # 所有机房的带宽和
    fTotalUsed = 0  # 所有机房已用带宽和
    fTotalTopUsed = 0  # 所有机房Top10使用的流量和
    dAllIP = {}
    dAllIPInfo = {}
    dOtherUsedBand = {}
    for sServerRoom in jIDCTraff:
        # 强尧传来的数据是有序的，为了不破坏顺序这里使用有序字典。有序字典能和json互转，且顺序不会破坏
        dEchartOuter = collections.OrderedDict()
        fTopUsed = 0
        listServerRoomTop = getServerRoomTop(sServerRoom, jIPTop)  # 得到一个机房的流量top10列表
        for dServerInfo in listServerRoomTop:
            sIP = dServerInfo['ip']
            fTraffic = dServerInfo['traffic']
            dEchartOuter[sIP] = dServerInfo  # 用于绘制外环top10 的信息，包括流量，用途
            dAllIP[sIP] = fTraffic  # 所有机房的Top 10 ip，用于绘制一个所有机房统计信息的Top 10
            dAllIPInfo[sIP] = dServerInfo
            # 该机房的流量使用top10带宽用量总和
            fTopUsed += fTraffic
        else:
            fTopUsed = 0
        fTotalTopUsed += fTopUsed  # 所有机房top 10 的流量，用于计算出其他ip的使用量

        iTotalServerUsedBand = 0
        dDataEchart[sServerRoom] = {}
        for sLine in jIDCTraff[sServerRoom]:
            # iTotalLineBand 线路的总带宽
            iTotalLineBand = jIDCTraff[sServerRoom][sLine][u'band']
            fUsedBand = jIDCTraff[sServerRoom][sLine][u'traffic_out']
            iTotalBand += iTotalLineBand  # 所有机房的带宽和
            fTotalUsed += fUsedBand  # 所有机房已用带宽和
            iTotalServerUsedBand += fUsedBand
            dDataEchart = getDataEchart(dDataEchart, sServerRoom, sLine, fUsedBand, iTotalLineBand, dEchartOuter,
                                        jIDCTraff[sServerRoom][sLine][u'ip'])
        # 计算每个机房的其他
        dOtherUsedBand = getOtherUseBand(dOtherUsedBand, sServerRoom, iTotalServerUsedBand, fTopUsed)
    dTotalTop = getTotalTop(dAllIP, dAllIPInfo)
    dDataEchart = getDataEchart(dDataEchart, '机房总计', '机房总计', int(fTotalUsed), iTotalBand, dTotalTop, '机房统计')
    # dOtherUsedBand 是机房的其他ip使用流量 = 机房的总流量 - 机房top10的IP使用流量
    dOtherUsedBand = getOtherUseBand(dOtherUsedBand, '机房总计', fTotalUsed, fTotalTopUsed)
    return dDataEchart, dOtherUsedBand


def AddOuterItem(dDataEchart, dOtherUsedBand):
    if not dDataEchart or not dOtherUsedBand:
        return {}
    for sServerRoom in dDataEchart:
        for sLine in dDataEchart[sServerRoom]:
            dDataEchart[sServerRoom][sLine]['outer']['other'] = dOtherUsedBand[sServerRoom]['other']
            dDataEchart[sServerRoom][sLine]['used'] = dOtherUsedBand[sServerRoom]['used']
    return dDataEchart
