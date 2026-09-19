# reverse-skill 本地自建 Claude Code 插件市场镜像
#
# 容器内提供：
#   1. /srv/reverse-skill.git   — 由当前工作区快照生成的 bare 仓库
#   2. /srv/marketplace.json    — 运行时按 PUBLIC_URL 生成，source 指向该 git 地址
#   3. nginx + git-http-backend — 80 端口同时提供静态市场文件与 smart HTTP git
#
# 客户端拉取：
#   claude plugin marketplace add http://<host>:<port>/marketplace.json
#   claude plugin install reverse-skill@reverse-skill
#
# 基础镜像选 Debian 而非 Alpine：Alpine 的 git 包不提供 git-http-backend，
# 而插件加载器以 `git clone --depth 1` 拉取，dumb HTTP 会报
# "dumb http transport does not support shallow capabilities"，必须走 smart HTTP。
FROM debian:stable-slim

ARG SKILL_VERSION=1.0.1
LABEL org.opencontainers.image.title="reverse-skill-market" \
      org.opencontainers.image.version="${SKILL_VERSION}" \
      org.opencontainers.image.description="Self-hosted Claude Code plugin marketplace for the reverse-skill catalog" \
      org.opencontainers.image.source="https://github.com/zhaoxuya520/reverse-skill"

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
 && apt-get install -y --no-install-recommends git nginx fcgiwrap spawn-fcgi ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && rm -f /etc/nginx/sites-enabled/default

WORKDIR /srv

# 把当前工作区打包成 git 快照。
# 刻意不 COPY .git 再 clone：工作区可能带未提交改动，容器内重新 init/commit
# 才能保证快照 == 构建时的真实文件树。
#
# 必须先剥掉嵌套的 .git 目录：工作区里若存在内层仓库（例如 skills/js-reverse-hello
# 自带的 .git），`git add -A` 会把它记成 gitlink 子模块指针，clone 出来是空目录，
# 该 skill 就会静默丢失。
COPY . /src/repo
RUN find /src/repo -mindepth 2 -name .git -prune -exec rm -rf {} + \
 && rm -rf /src/repo/.git \
 && cd /src/repo \
 && git init -q \
 && git add -A \
 && git -c user.email=build@reverse-skill.local -c user.name=reverse-skill-build \
      commit -qm "reverse-skill snapshot ${SKILL_VERSION}" \
 && git clone -q --bare /src/repo /srv/reverse-skill.git \
 && cd /srv/reverse-skill.git \
 && git symbolic-ref HEAD refs/heads/master \
 && git config http.receivepack false \
 && rm -rf /src

COPY docker/marketplace.json.tmpl /srv/marketplace.json.tmpl
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY docker/entrypoint.sh /entrypoint.sh
COPY docker/verify-snapshot.sh /verify-snapshot.sh
RUN chmod +x /entrypoint.sh /verify-snapshot.sh

# 构建期自检：脚本语法、nginx 配置、bare 仓库可解、smart-HTTP 组件齐备，
# 并断言快照内容与 plugin.json 声明的 skill 清单一致
# （防止嵌套 .git 之类问题静默丢 skill）。
RUN sh -n /entrypoint.sh \
 && nginx -t \
 && command -v fcgiwrap >/dev/null \
 && command -v spawn-fcgi >/dev/null \
 && test -x /usr/lib/git-core/git-http-backend \
 && grep -q '__BASE_URL__' /srv/marketplace.json.tmpl \
 && sh /verify-snapshot.sh

EXPOSE 80
ENTRYPOINT ["/entrypoint.sh"]
