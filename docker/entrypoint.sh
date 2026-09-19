#!/bin/sh
# 启动 git smart-HTTP 后端与 nginx，并按运行时 PUBLIC_URL 生成 marketplace.json。
# 主机名/端口在构建期未知，必须延迟到容器启动时决定。
set -eu

BASE="${PUBLIC_URL:-http://localhost:8899}"
# 去掉结尾斜杠，避免出现 //reverse-skill.git
BASE="${BASE%/}"

echo "[entrypoint] PUBLIC_URL=${BASE}"

sed "s|__BASE_URL__|${BASE}|g" /srv/marketplace.json.tmpl > /srv/marketplace.json

# 启动 fcgiwrap（nginx -> git-http-backend 的桥）。
# nginx worker 以 www-data 运行，socket 需对 www-data 可写。
SOCK=/run/fcgiwrap.sock
rm -f "$SOCK"
spawn-fcgi -s "$SOCK" -U www-data -G www-data -M 0660 -- /usr/sbin/fcgiwrap
echo "[entrypoint] fcgiwrap socket ready: $SOCK"

echo "[entrypoint] marketplace: ${BASE}/marketplace.json"
echo "[entrypoint] git remote : ${BASE}/reverse-skill.git"

exec nginx -g 'daemon off;'
