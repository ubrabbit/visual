#!/usr/bin/env bash
# 作者:youzeshun

# 当服务器信息更新的时候需要删除两种缓存
# 1.交换机网口和线路的映射关系，如沈阳联通走２２网口  static/idc/cache/ip_to_interface.yaml
# 2.点击页面时，ip 或者 线路 对应的七天和一天历史流量信息 static/idc/cache/key_value.db

basePath=$(cd `dirname $0`;pwd)
pathMap="${basePath}/static/idc/cache/ip_to_interface.yaml"
pathDb="${basePath}/static/idc/cache/key_value.db"

if [ -f ${pathMap} ];then
    echo '删除缓存：'${pathMap}
    rm -f ${pathMap}
fi

if [ -f ${pathDb} ];then
    echo '删除键值对数据：'${pathDb}
    rm -f ${pathDb}
fi