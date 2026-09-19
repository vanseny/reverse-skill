#!/bin/sh
# 构建期自检：断言 bare 快照里的 skill 与 .claude-plugin/plugin.json 声明的清单一致。
#
# 为什么需要：工作区若含嵌套 .git（例如某个 skill 目录自带仓库），`git add -A`
# 会把它记成 gitlink 指针，clone 出来是空目录 —— 该 skill 静默丢失，
# 而镜像本身仍然构建成功。这里把"声明数 == 实际数"变成硬门禁。
set -eu

REPO=/srv/reverse-skill.git
MANIFEST_CHECKOUT=/tmp/snapshot-check

rm -rf "$MANIFEST_CHECKOUT"
git clone -q --depth 1 "$REPO" "$MANIFEST_CHECKOUT"

# 快照里真实存在的 skill（每个 SKILL.md 一个）
actual=$(find "$MANIFEST_CHECKOUT/skills" -name SKILL.md -type f | wc -l | tr -d ' ')

# plugin.json 声明的 skill 路径数
declared=$(grep -o '"\./skills[^"]*/"' "$MANIFEST_CHECKOUT/.claude-plugin/plugin.json" | wc -l | tr -d ' ')

echo "[verify-snapshot] declared=$declared actual=$actual"

if [ "$declared" -ne "$actual" ]; then
    echo "[verify-snapshot] FAIL: plugin.json declares $declared skills but snapshot has $actual SKILL.md files" >&2
    echo "[verify-snapshot] likely cause: a nested .git directory was captured as a gitlink. Check for skills/*/.git" >&2
    exit 1
fi

# 空目录检测：gitlink 会 clone 成空目录，这里显式报出
for d in $(find "$MANIFEST_CHECKOUT/skills" -mindepth 1 -maxdepth 2 -type d -empty); do
    echo "[verify-snapshot] FAIL: empty skill directory in snapshot: ${d#$MANIFEST_CHECKOUT/}" >&2
    exit 1
done

rm -rf "$MANIFEST_CHECKOUT"
echo "[verify-snapshot] OK: $actual skills present and consistent"
