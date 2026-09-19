# 本地自建 Claude Code 插件市场

把 reverse-skill 的全部 skill 打包成一个 **自托管的 Claude Code 插件市场**，用 Docker 跑起来后，任何一台机器两条命令就能拉全部 skill。

不依赖 GitHub、不依赖官方市场、不需要手动 clone。

## 它是什么

容器里跑三样东西：

| 组件 | 作用 |
|---|---|
| `/srv/reverse-skill.git` | 构建时由当前工作区生成的 bare git 仓库（smart HTTP 可克隆） |
| `/srv/marketplace.json` | 运行时按 `PUBLIC_URL` 生成的 Claude 市场清单 |
| nginx + `git-http-backend` | 80 端口同时提供市场文件与 git 服务 |

客户端 `claude plugin marketplace add` 拿到清单，`claude plugin install` 通过 git 拉取插件内容。

## 快速开始

```bash
# 1. 构建并启动
cd /path/to/reverse-skill
docker compose -f docker/docker-compose.yml up -d --build

# 2. 自检
curl -s http://127.0.0.1:8899/healthz
curl -s http://127.0.0.1:8899/marketplace.json | head

# 3. 客户端拉取
claude plugin marketplace add http://127.0.0.1:8899/marketplace.json
claude plugin install reverse-skill@reverse-skill

# 4. 确认挂载
claude plugin details reverse-skill@reverse-skill
```

预期 `Skills (50)`。

## 局域网 / 远程共享

`marketplace.json` 里的 git 地址由 `PUBLIC_URL` 决定，客户端必须能访问到它。
换地址时**两处都要改**：端口映射 + `PUBLIC_URL`。

```yaml
ports:
  - "8899:80"
environment:
  PUBLIC_URL: "http://192.168.1.50:8899"   # 改成客户端可达地址
```

```bash
docker compose -f docker/docker-compose.yml up -d
claude plugin marketplace add http://192.168.1.50:8899/marketplace.json
```

## 更新内容后如何发布

镜像内的 git 快照是**构建时**从工作区生成的，改了 skill 必须重新构建：

```bash
docker compose -f docker/docker-compose.yml up -d --build
claude plugin marketplace update reverse-skill
claude plugin install reverse-skill@reverse-skill   # 重新安装以刷新
```

## 设计要点（踩过的坑）

| 坑 | 结论 |
|---|---|
| **URL 市场不支持相对路径 source** | 清单里的 `source` 必须用绝对 URL（`{"source":"url","url":"..."}`）。写 `"."` 或 `"./x"` 会装失败。 |
| **dumb HTTP 不支持浅克隆** | 插件加载器用 `git clone --depth 1`。纯静态文件托管会报 `dumb http transport does not support shallow capabilities`，**必须**接 `git-http-backend`（smart HTTP）。 |
| **Alpine 没有 git-http-backend** | Alpine 的 `git` 包不含该二进制，基础镜像改用 `debian:stable-slim`。 |
| **嵌套 `.git` 会静默吞 skill** | 若某 skill 目录自带 `.git`，`git add -A` 会记成 gitlink，clone 出来是空目录。构建时先 `find -mindepth 2 -name .git -exec rm -rf`，并用 `verify-snapshot.sh` 断言声明数 == 实际数。 |
| **根级 `skills/SKILL.md` 会遮蔽全部子 skill** | Claude Code 见到 `skills/SKILL.md` 就把 `skills/` 当**单个** skill，跳过所有嵌套目录。因此 `.claude-plugin/plugin.json` 必须**逐条列出**每个 skill 路径（通配符不展开）。 |

## 文件说明

| 文件 | 作用 |
|---|---|
| `Dockerfile` | 镜像定义：快照 git 化 + nginx + smart HTTP |
| `docker-compose.yml` | 一键起服务，含 `PUBLIC_URL` 与健康检查 |
| `nginx.conf` | 静态市场文件 + `git-http-backend` FastCGI 路由 |
| `entrypoint.sh` | 生成 `marketplace.json`、拉起 fcgiwrap、启动 nginx |
| `verify-snapshot.sh` | 构建期断言 skill 清单与快照一致 |
| `marketplace.json.tmpl` | 市场清单模板，`__BASE_URL__` 运行时替换 |

## 卸载

```bash
claude plugin uninstall reverse-skill@reverse-skill
claude plugin marketplace remove reverse-skill
docker compose -f docker/docker-compose.yml down
```

## 公网部署（已实测）

本仓库当前实例已挂在 **`https://skill.vanseny.it.com`**，拓扑：

```
Claude Code
   │  HTTPS
   ▼
Cloudflare Tunnel (cloudflared-local)
   │  hostname: skill.vanseny.it.com → host.docker.internal:8899
   ▼
reverse-skill-market 容器 (:80)
   ├── /marketplace.json          ← 静态，PUBLIC_URL 生成
   └── /reverse-skill.git/*       ← git-http-backend (smart HTTP)
```

对应 tunnel 配置（Ingress 段）：

```yaml
- hostname: "skill.vanseny.it.com"
  service: "http://host.docker.internal:8899"
  originRequest:
    httpHostHeader: "localhost:8899"
```

### 客户端拉取

```bash
claude plugin marketplace add https://skill.vanseny.it.com/marketplace.json
claude plugin install reverse-skill@reverse-skill
claude plugin details reverse-skill@reverse-skill   # 预期 Skills (50)
```

### 关键点：PUBLIC_URL 必须是客户端可达地址

`marketplace.json` 里的 git 地址由 `PUBLIC_URL` 生成，**它必须是客户端能访问的地址**，
不能是 `127.0.0.1`（那样每个客户端会去连自己的本机）。

| 场景 | PUBLIC_URL |
|---|---|
| 公网域名（当前） | `https://skill.vanseny.it.com` |
| 仅本机调试 | `http://127.0.0.1:8899` |
| 局域网共享 | `http://192.168.x.x:8899` |

改完需 `docker compose up -d` 重建容器以重新生成清单。

### 验证公网链路

```bash
curl -s https://skill.vanseny.it.com/healthz
curl -s https://skill.vanseny.it.com/marketplace.json | head
git clone --depth 1 https://skill.vanseny.it.com/reverse-skill.git /tmp/t && ls /tmp/t/skills | wc -l
```
