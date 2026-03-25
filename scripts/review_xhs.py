#!/usr/bin/env python3
"""
小红书笔记数据复盘脚本 - Obsidian 版本

自动追踪笔记在以下时间点的数据：
- 1小时、6小时、12小时、24小时、72小时、一周

复盘数据存储在 Obsidian Vault 中：
- 帖子: Posts/YYYY-MM/{date}-{slug}.md
- 复盘: Posts/Reviews/{date}-{slug}.md

使用方法:

# 记录新帖子并开始追踪
python review_xhs.py --create --title "标题" --desc "描述"

# 记录已发布帖子
python review_xhs.py --note-id xxx --record

# 追踪帖子数据
python review_xhs.py --note-id xxx --track

# 查看帖子历史数据
python review_xhs.py --note-id xxx --history

# 生成复盘报告
python review_xhs.py --note-id xxx --report

# 列出所有追踪的帖子
python review_xhs.py --list

环境配置:
在 .env 文件中配置：
XHS_COOKIE=your_cookie_string_here
OBSIDIAN_VAULT=D:/obsidianDB/peanut
"""

import argparse
import json
import os
import re
import sys
import time
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict, field

try:
    from dotenv import load_dotenv
except ImportError:
    print("⚠️  缺少 dotenv: pip install python-dotenv")

try:
    import requests
except ImportError:
    print("⚠️  缺少 requests: pip install requests")


# ============ 配置 ============

CHECKPOINT_INTERVALS = [
    ("1小时", 1 * 60 * 60),
    ("6小时", 6 * 60 * 60),
    ("12小时", 12 * 60 * 60),
    ("24小时", 24 * 60 * 60),
    ("72小时", 72 * 60 * 60),
    ("1周", 7 * 24 * 60 * 60),
]

ENGAGEMENT_BENCHMARKS = {
    "engagement_rate_good": 5.0,
    "engagement_rate_avg": 2.0,
    "collect_rate_good": 3.0,
    "collect_rate_avg": 1.0,
}


def load_config():
    """加载配置"""
    env_paths = [
        Path.cwd() / '.env',
        Path(__file__).parent.parent / '.env',
        Path(__file__).parent.parent.parent / '.env',
    ]

    for env_path in env_paths:
        if env_path.exists():
            load_dotenv(env_path)
            break

    # Cookie
    cookie = os.getenv('XHS_COOKIE')
    if not cookie:
        print("❌ 错误: 未找到 XHS_COOKIE 环境变量")
        sys.exit(1)

    # Obsidian Vault 路径
    vault_path = os.getenv('OBSIDIAN_VAULT', 'D:/obsidianDB/peanut')

    return {
        'cookie': cookie,
        'vault_path': Path(vault_path),
    }


def get_note_path(vault: Path, note_id: str) -> Optional[Path]:
    """根据 note_id 查找帖子文件路径"""
    # 搜索 Posts 目录
    posts_dir = vault / "Posts"
    if not posts_dir.exists():
        return None

    # 在所有月份目录中搜索
    for month_dir in posts_dir.rglob("*"):
        if month_dir.is_dir() and month_dir.name.startswith("20"):
            for md_file in month_dir.glob("*.md"):
                content = md_file.read_text(encoding="utf-8")
                if f"note_id: {note_id}" in content or f"note_id:\"{note_id}\"" in content:
                    return md_file
                # 检查 frontmatter 中的 id
                if "---" in content:
                    frontmatter = content.split("---")[1]
                    if f"note_id" in frontmatter and note_id in frontmatter:
                        return md_file
    return None


def get_review_path(vault: Path, note_id: str, title: str) -> Path:
    """获取复盘文件路径"""
    review_dir = vault / "Posts" / "Reviews"
    review_dir.mkdir(parents=True, exist_ok=True)

    # 生成安全的文件名
    slug = re.sub(r'[^\w\s-]', '', title)
    slug = re.sub(r'[-\s]+', '-', slug)[:30]
    date = datetime.now().strftime("%Y-%m-%d")

    return review_dir / f"{date}-{slug}.md"


def parse_frontmatter(content: str) -> tuple:
    """解析 Obsidian frontmatter"""
    if not content.startswith("---"):
        return {}, content

    parts = content[3:].split("---", 1)
    if len(parts) < 2:
        return {}, content

    frontmatter_text = parts[0]
    body = parts[1]

    # 简单解析 YAML frontmatter
    fm = {}
    for line in frontmatter_text.split("\n"):
        if ":" in line:
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip().strip('"\'')
            if value.startswith("[") and value.endswith("]"):
                # 简单列表处理
                fm[key] = value.strip("[]").split(",")
            else:
                fm[key] = value

    return fm, body


def update_frontmatter(content: str, updates: Dict) -> str:
    """更新 frontmatter"""
    fm, body = parse_frontmatter(content)

    # 合并更新
    fm.update(updates)

    # 重新生成 frontmatter
    fm_lines = ["---"]
    for key, value in fm.items():
        if isinstance(value, list):
            fm_lines.append(f"{key}: [{', '.join(str(v) for v in value)}]")
        else:
            fm_lines.append(f"{key}: {value}")
    fm_lines.append("---")

    return "\n".join(fm_lines) + "\n" + body


def extract_tracking_data(content: str) -> List[Dict]:
    """从笔记内容中提取追踪数据"""
    data = []

    # 查找 ## 📊 数据记录 部分
    if "📊 数据记录" in content or "数据记录" in content:
        # 简单解析：查找所有时间点和对应的数字
        lines = content.split("\n")
        current_checkpoint = None

        for line in lines:
            # 检查是否是时间点标题
            for name, _ in CHECKPOINT_INTERVALS:
                if name in line:
                    current_checkpoint = {"time_since_publish": name}
                    break

            # 检查是否是数据行
            if current_checkpoint:
                if "浏览" in line or "曝光" in line:
                    nums = re.findall(r'[\d,，]+', line)
                    if nums:
                        current_checkpoint["views"] = int(nums[0].replace(",", "").replace("，", ""))
                elif "点赞" in line:
                    nums = re.findall(r'[\d,，]+', line)
                    if nums:
                        current_checkpoint["likes"] = int(nums[0].replace(",", "").replace("，", ""))
                elif "收藏" in line:
                    nums = re.findall(r'[\d,，]+', line)
                    if nums:
                        current_checkpoint["collects"] = int(nums[0].replace(",", "").replace("，", ""))
                elif "评论" in line:
                    nums = re.findall(r'[\d,，]+', line)
                    if nums:
                        current_checkpoint["comments"] = int(nums[0].replace(",", "").replace("，", ""))

                # 如果已经收集完数据，重置
                if all(k in current_checkpoint for k in ["views", "likes", "collects", "comments"]):
                    data.append(current_checkpoint)
                    current_checkpoint = None

    return data


def calculate_time_since(published_at: str) -> str:
    """计算距离发布的时间"""
    try:
        formats = ["%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"]
        published_time = None
        for fmt in formats:
            try:
                published_time = datetime.strptime(published_at[:19] if len(published_at) > 19 else published_at, fmt)
                break
            except:
                continue

        if published_time is None:
            return "未知"

        now = datetime.now()
        delta = now - published_time

        if delta.days > 0:
            return f"{delta.days}天{delta.seconds // 3600}小时"
        elif delta.seconds >= 3600:
            return f"{delta.seconds // 3600}小时"
        elif delta.seconds >= 60:
            return f"{delta.seconds // 60}分钟"
        else:
            return f"{delta.seconds}秒"
    except:
        return "未知"


def get_next_checkpoint(published_at: str) -> Optional[tuple]:
    """获取下一个待记录的时间点"""
    try:
        formats = ["%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"]
        published_time = None
        for fmt in formats:
            try:
                published_time = datetime.strptime(published_at[:19] if len(published_at) > 19 else published_at, fmt)
                break
            except:
                continue

        if published_time is None:
            return None

        now = datetime.now()
        elapsed = (now - published_time).total_seconds()

        for name, seconds in CHECKPOINT_INTERVALS:
            if elapsed < seconds:
                return (name, seconds - elapsed)

        return None

    except:
        return None


def human_delay(min_sec: float = 1.0, max_sec: float = 3.0):
    """模拟人类延迟"""
    delay = random.uniform(min_sec, max_sec)
    time.sleep(delay)


# ============ 核心功能 ============

def generate_report(note_path: Path, title: str, published_at: str, checkpoints: List[Dict]) -> str:
    """生成复盘报告"""
    if not checkpoints:
        return "❌ 没有足够的数据生成报告"

    latest = checkpoints[-1]

    # 计算各指标
    views = latest.get("views", 0)
    likes = latest.get("likes", 0)
    collects = latest.get("collects", 0)
    comments = latest.get("comments", 0)

    engagement_rate = ((likes + collects + comments) / views * 100) if views > 0 else 0
    collect_rate = (collects / views * 100) if views > 0 else 0
    like_rate = (likes / views * 100) if views > 0 else 0

    report = f"""---
type: review
note_id: {note_path.stem[:20]}
title: {title}
published_at: {published_at}
generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
checkpoints_count: {len(checkpoints)}
---

# {title} - 复盘报告

> 发布于 {published_at} · 已运行时长 {calculate_time_since(published_at)}

## 📈 核心数据（{latest.get("time_since_publish", "最新")}）

| 指标 | 数值 |
|------|------|
| 浏览量 | {views:,} |
| 点赞数 | {likes:,} |
| 收藏数 | {collects:,} |
| 评论数 | {comments:,} |

## 📊 互动分析

| 指标 | 数值 | 参考标准 |
|------|------|----------|
| 互动率 | {engagement_rate:.2f}% | 优秀 >5%, 一般 >2% |
| 收藏率 | {collect_rate:.2f}% | 优秀 >3%, 一般 >1% |
| 点赞率 | {like_rate:.2f}% | - |

## ⏰ 各时间点数据

| 时间点 | 浏览量 | 点赞 | 收藏 | 评论 |
|--------|--------|------|------|------|
"""

    for cp in checkpoints:
        report += f"| {cp.get('time_since_publish', '?')} | {cp.get('views', 0):,} | {cp.get('likes', 0):,} | {cp.get('collects', 0):,} | {cp.get('comments', 0):,} |\n"

    # 增长分析
    if len(checkpoints) >= 2:
        report += f"""
## 💹 增长分析

"""
        for i in range(1, len(checkpoints)):
            prev = checkpoints[i-1]
            curr = checkpoints[i]
            view_diff = curr.get('views', 0) - prev.get('views', 0)
            report += f"- {prev.get('time_since_publish', '?')} → {curr.get('time_since_publish', '?')}: 浏览 {view_diff:+,}\n"

    # 优化建议
    suggestions = []
    if engagement_rate < 1.0:
        suggestions.append("**互动率较低** (<1%): 建议优化标题和封面，提高点击率")
    elif engagement_rate < 2.0:
        suggestions.append("**互动率一般** (1-2%): 内容有一定吸引力，可继续优化")
    elif engagement_rate >= 5.0:
        suggestions.append("**互动率优秀** (>5%): 内容质量高，可以复用此套路")

    if collect_rate < 0.5:
        suggestions.append("**收藏率过低** (<0.5%): 内容实用性不足，建议增加干货/教程类内容")
    elif collect_rate < 1.0:
        suggestions.append("**收藏率一般**: 可增加「收藏价值」元素，如清单、模板等")
    elif collect_rate >= 3.0:
        suggestions.append("**收藏率很高** (>3%): 内容实用性强，保持此类风格")

    if comments < 5 and views > 100:
        suggestions.append("**评论数偏少**: 可在内容中增加互动性问题，引导讨论")

    if not suggestions:
        suggestions.append("数据表现良好，继续保持当前策略")

    report += f"""
## 💡 优化建议

"""
    for i, s in enumerate(suggestions, 1):
        report += f"{i}. {s}\n"

    report += f"""
## 📋 后续行动

"""
    actions = []
    if engagement_rate < 2.0:
        actions.append("本周测试3种不同封面风格，寻找最优解")
    if collect_rate < 1.0:
        actions.append("在后续内容中增加「可操作性」的实操步骤")
    actions.append(f"⏰ {len(checkpoints)}/{len(CHECKPOINT_INTERVALS)} 时间点已记录")
    actions.append("每周复盘一次，积累数据优化内容策略")

    for i, action in enumerate(actions, 1):
        report += f"{i}. {action}\n"

    report += f"""
---

*由 xhs-ops 自动生成 · {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}*
"""

    return report


# ============ API 客户端 ============

class XHSClient:
    """小红书 API 客户端"""

    def __init__(self, cookie: str, api_url: str = None):
        self.cookie = cookie
        self.api_url = api_url or os.getenv('XHS_API_URL', 'http://localhost:5005')
        self.session_id = 'xhs_review_session'

    def init(self):
        """初始化 API 连接"""
        print(f"📡 连接 API 服务: {self.api_url}")

        try:
            resp = requests.get(f"{self.api_url}/health", timeout=5)
            if resp.status_code != 200:
                raise Exception("API 服务不可用")
        except requests.exceptions.RequestException as e:
            print(f"❌ 无法连接到 API 服务: {e}")
            print(f"\n💡 请确保 xhs-api 服务已启动")
            sys.exit(1)

        try:
            resp = requests.post(
                f"{self.api_url}/init",
                json={"session_id": self.session_id, "cookie": self.cookie},
                timeout=30
            )
            result = resp.json()
            if result.get('status') == 'success':
                print(f"✅ API 初始化成功")
            else:
                raise Exception(result.get('error', '初始化失败'))
        except Exception as e:
            print(f"❌ API 初始化失败: {e}")
            sys.exit(1)

    def get_note_stats(self, note_id: str) -> Optional[Dict[str, Any]]:
        """获取笔记统计数据"""
        try:
            resp = requests.get(f"{self.api_url}/note/{note_id}/stats", timeout=10)
            if resp.status_code == 200:
                return resp.json()

            resp = requests.get(f"{self.api_url}/note/{note_id}", timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                interact_info = data.get("result", {}).get("interact_info", {})
                return {
                    "liked_count": int(interact_info.get("liked_count", 0) or 0),
                    "collected_count": int(interact_info.get("collected_count", 0) or 0),
                    "comment_count": int(interact_info.get("comment_count", 0) or 0),
                    "share_count": int(interact_info.get("share_count", 0) or 0),
                }
        except Exception as e:
            print(f"⚠️  API 获取失败: {e}")
        return None

    def get_note_info(self, note_id: str) -> Optional[Dict[str, Any]]:
        """获取笔记基本信息"""
        try:
            resp = requests.get(f"{self.api_url}/note/{note_id}", timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                note_card = data.get("result", {}).get("note_card", {})
                return {
                    "title": note_card.get("title", ""),
                    "published_at": note_card.get("time", ""),
                    "cover_url": note_card.get("image_list", [{}])[0].get("url_default", ""),
                }
        except Exception as e:
            print(f"⚠️  获取笔记信息失败: {e}")
        return None


# ============ Obsidian 操作 ============

def find_all_posts(vault: Path) -> List[tuple]:
    """查找所有帖子"""
    posts = []
    posts_dir = vault / "Posts"

    if not posts_dir.exists():
        return posts

    for month_dir in posts_dir.rglob("*"):
        if month_dir.is_dir() and month_dir.name.startswith("20"):
            for md_file in month_dir.glob("*.md"):
                try:
                    content = md_file.read_text(encoding="utf-8")
                    fm, _ = parse_frontmatter(content)

                    if fm.get("status") == "published":
                        posts.append({
                            "path": md_file,
                            "title": fm.get("title", md_file.stem),
                            "note_id": fm.get("note_id", ""),
                            "published_at": fm.get("published_at", ""),
                            "checkpoints": extract_tracking_data(content),
                        })
                except Exception as e:
                    print(f"⚠️  读取 {md_file} 失败: {e}")

    return sorted(posts, key=lambda x: x["published_at"], reverse=True)


def update_post_tracking(note_path: Path, checkpoint: Dict) -> bool:
    """更新帖子的追踪数据"""
    try:
        content = note_path.read_text(encoding="utf-8")
        fm, body = parse_frontmatter(content)

        # 更新时间戳
        fm["last_check"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        fm["last_check_interval"] = checkpoint.get("time_since_publish", "")

        # 构建数据记录表格
        tracking_section = f"""
## 📊 数据记录

| 时间点 | 浏览量 | 点赞 | 收藏 | 评论 |
|--------|--------|------|------|------|
"""

        # 保留原有的数据行（如果格式正确）
        existing_data = extract_tracking_data(body)
        existing_data.append(checkpoint)

        for cp in existing_data:
            tracking_section += f"| {cp.get('time_since_publish', '?')} | {cp.get('views', 0):,} | {cp.get('likes', 0):,} | {cp.get('collects', 0):,} | {cp.get('comments', 0):,} |\n"

        # 重建文件
        fm_lines = ["---"]
        for key, value in fm.items():
            if isinstance(value, list):
                fm_lines.append(f"{key}: [{', '.join(str(v) for v in value)}]")
            else:
                fm_lines.append(f"{key}: {value}")
        fm_lines.append("---")

        # 保留原有内容，替换或添加数据记录部分
        if "## 📊 数据记录" in body or "## 数据记录" in body:
            # 替换已有数据记录部分
            pattern = r"##.?.?数据记录.*?(?=\n##|\n---|\Z)"
            body = re.sub(pattern, tracking_section.strip(), body, flags=re.DOTALL)
        else:
            # 在末尾添加
            body = body.rstrip() + "\n" + tracking_section

        new_content = "\n".join(fm_lines) + "\n" + body
        note_path.write_text(new_content, encoding="utf-8")

        return True

    except Exception as e:
        print(f"❌ 更新追踪数据失败: {e}")
        return False


# ============ 命令行接口 ============

def cmd_create(args, config):
    """创建新帖子记录"""
    vault = config['vault_path']

    # 生成文件路径
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    slug = re.sub(r'[^\w\s-]', '', args.title)
    slug = re.sub(r'[-\s]+', '-', slug)[:30]

    posts_dir = vault / "Posts" / now.strftime("%Y-%m-%d")
    posts_dir.mkdir(parents=True, exist_ok=True)

    note_path = posts_dir / f"{date_str}-{slug}.md"

    if note_path.exists():
        print(f"❌ 文件已存在: {note_path}")
        return

    # 生成笔记内容
    content = f"""---
title: "{args.title}"
note_id: "{args.note_id or now.strftime('%Y%m%d%H%M%S')}"
status: {"published" if args.publish else "draft"}
platform: xiaohongshu
tags: [{args.tags or ""}]
published_at: {now.strftime("%Y-%m-%d %H:%M:%S")}
last_check: {now.strftime("%Y-%m-%d %H:%M:%S")}
last_check_interval: ""
---

# {args.title}

## 📌 一句话亮点


## 📝 正文

{args.desc or ""}

## 🏷 推荐标签
#{args.tags or ""}

## 📊 数据记录

| 时间点 | 浏览量 | 点赞 | 收藏 | 评论 |
|--------|--------|------|------|------|
| - | - | - | - | - |

---

*由 xhs-ops 生成 · {now.strftime("%Y-%m-%d %H:%M:%S")}*
"""

    note_path.write_text(content, encoding="utf-8")
    print(f"✅ 帖子记录已创建: {note_path}")

    if args.publish:
        print(f"\n📝 请手动发布后，使用以下命令记录数据:")
        print(f"   python scripts/review_xhs.py --note-id {args.note_id or now.strftime('%Y%m%d%H%M%S')} --record --api-mode")


def cmd_record(args, config):
    """记录帖子数据"""
    vault = config['vault_path']
    cookie = config['cookie']

    # 查找帖子
    note_path = get_note_path(vault, args.note_id) if args.note_id else None

    if not note_path:
        # 尝试模糊匹配
        posts = find_all_posts(vault)
        for post in posts:
            if args.note_id in post["path"].stem:
                note_path = post["path"]
                break

    if not note_path:
        print(f"❌ 找不到帖子: {args.note_id}")
        return

    print(f"\n📝 帖子: {note_path.stem}")
    print(f"📂 路径: {note_path}")

    # 读取当前内容
    content = note_path.read_text(encoding="utf-8")
    fm, _ = parse_frontmatter(content)

    published_at = fm.get("published_at", datetime.now().strftime("%Y-%m-%d"))
    title = fm.get("title", note_path.stem)

    print(f"   发布时间: {published_at}")
    print(f"   已运行时长: {calculate_time_since(published_at)}")

    # 获取数据
    if args.api_mode:
        client = XHSClient(cookie, args.api_url)
        client.init()

        note_id = fm.get("note_id", args.note_id)
        stats = client.get_note_stats(note_id)

        if not stats:
            print(f"⚠️  无法获取统计数据，使用手动输入")
            stats = {
                "liked_count": 0,
                "collected_count": 0,
                "comment_count": 0,
                "share_count": 0,
            }
    else:
        # 手动输入
        print("\n📊 请输入当前数据:")
        views = int(input("   浏览量: ") or 0)
        likes = int(input("   点赞数: ") or 0)
        collects = int(input("   收藏数: ") or 0)
        comments = int(input("   评论数: ") or 0)

        stats = {
            "liked_count": likes,
            "collected_count": collects,
            "comment_count": comments,
            "views": views,
        }

    # 创建数据点
    now = datetime.now()
    time_since = calculate_time_since(published_at)

    checkpoint = {
        "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
        "time_since_publish": time_since,
        "views": stats.get("views", 0),
        "likes": stats.get("liked_count", 0),
        "collects": stats.get("collected_count", 0),
        "comments": stats.get("comment_count", 0),
        "shares": stats.get("share_count", 0),
    }

    print(f"""
✨ 数据记录成功！
  时间点: {time_since}
  浏览量: {checkpoint['views']}
  点赞数: {checkpoint['likes']}
  收藏数: {checkpoint['collects']}
  评论数: {checkpoint['comments']}
    """)

    # 更新笔记
    update_post_tracking(note_path, checkpoint)


def cmd_track(args, config):
    """持续追踪帖子数据"""
    vault = config['vault_path']

    note_path = get_note_path(vault, args.note_id) if args.note_id else None
    if not note_path:
        posts = find_all_posts(vault)
        for post in posts:
            if args.note_id in post["path"].stem:
                note_path = post["path"]
                break

    if not note_path:
        print(f"❌ 找不到帖子: {args.note_id}")
        return

    content = note_path.read_text(encoding="utf-8")
    fm, _ = parse_frontmatter(content)

    published_at = fm.get("published_at", "")
    title = fm.get("title", note_path.stem)

    print(f"\n🔄 开始追踪: {title}")
    print(f"   笔记ID: {args.note_id}")
    print(f"   发布时间: {published_at}")

    next_cp = get_next_checkpoint(published_at)
    if not next_cp:
        print(f"\n✅ 所有时间点已记录完毕，生成报告：")
        checkpoints = extract_tracking_data(content)
        report = generate_report(note_path, title, published_at, checkpoints)
        print(report)
        return

    time_name, seconds_left = next_cp
    print(f"\n⏰ 下一个记录点: {time_name}")
    print(f"   预计还需等待: {seconds_left/3600:.1f} 小时")

    if not args.daemon:
        print("\n💡 使用 --daemon 参数可以持续追踪")
        return

    print("\n🔄 进入持续追踪模式，按 Ctrl+C 退出...")

    try:
        while True:
            current_next = get_next_checkpoint(published_at)
            if not current_next:
                print("\n✅ 所有时间点已记录完毕！")
                break

            time_name, seconds_left = current_next
            if seconds_left <= 0:
                print(f"\n⏰ 到达 {time_name} 记录点，正在获取数据...")
                cmd_record(args, config)
                content = note_path.read_text(encoding="utf-8")
            else:
                print(f"\r⏳ 等待 {time_name}... ({seconds_left/3600:.1f}h remaining)", end="", flush=True)
                time.sleep(60)

    except KeyboardInterrupt:
        print("\n\n👋 停止追踪")


def cmd_history(args, config):
    """查看帖子历史数据"""
    vault = config['vault_path']

    note_path = get_note_path(vault, args.note_id) if args.note_id else None
    if not note_path:
        posts = find_all_posts(vault)
        for post in posts:
            if args.note_id in post["path"].stem:
                note_path = post["path"]
                break

    if not note_path:
        print(f"❌ 找不到帖子: {args.note_id}")
        return

    content = note_path.read_text(encoding="utf-8")
    fm, _ = parse_frontmatter(content)

    published_at = fm.get("published_at", "")
    title = fm.get("title", note_path.stem)
    checkpoints = extract_tracking_data(content)

    print(f"\n📜 历史数据: {title}")
    print(f"   帖子ID: {args.note_id}")
    print(f"   发布时间: {published_at}")
    print(f"   已运行时长: {calculate_time_since(published_at)}")
    print(f"\n{'时间点':<12} {'浏览量':<12} {'点赞':<10} {'收藏':<10} {'评论':<8}")
    print("-" * 60)

    for cp in checkpoints:
        print(f"{cp.get('time_since_publish', '?'):<12} {cp.get('views', 0):<12,} {cp.get('likes', 0):<10,} {cp.get('collects', 0):<10,} {cp.get('comments', 0):<8,}")


def cmd_report(args, config):
    """生成复盘报告"""
    vault = config['vault_path']

    note_path = get_note_path(vault, args.note_id) if args.note_id else None
    if not note_path:
        posts = find_all_posts(vault)
        for post in posts:
            if args.note_id in post["path"].stem:
                note_path = post["path"]
                break

    if not note_path:
        print(f"❌ 找不到帖子: {args.note_id}")
        return

    content = note_path.read_text(encoding="utf-8")
    fm, _ = parse_frontmatter(content)

    published_at = fm.get("published_at", "")
    title = fm.get("title", note_path.stem)
    checkpoints = extract_tracking_data(content)

    report = generate_report(note_path, title, published_at, checkpoints)
    print(report)

    # 保存复盘到 Reviews 文件夹
    review_path = get_review_path(vault, args.note_id, title)
    review_path.write_text(report, encoding="utf-8")
    print(f"\n📝 复盘报告已保存: {review_path}")


def cmd_list(config):
    """列出所有追踪的帖子"""
    vault = config['vault_path']
    posts = find_all_posts(vault)

    if not posts:
        print("\n📭 还没有追踪任何帖子")
        print("\n使用方法:")
        print("  python scripts/review_xhs.py --create --title '标题' --desc '内容'  # 创建帖子")
        print("  python scripts/review_xhs.py --note-id xxx --record --api-mode  # 记录数据")
        return

    print(f"\n📋 已追踪的帖子 ({len(posts)} 篇)")
    print("=" * 80)

    for post in posts:
        latest = post["checkpoints"][-1] if post["checkpoints"] else {}
        elapsed = calculate_time_since(post["published_at"])

        print(f"\n📌 {post['title']}")
        print(f"   ID: {post['note_id']}")
        print(f"   发布时间: {post['published_at']} ({elapsed})")
        print(f"   数据点: {len(post['checkpoints'])}")

        if latest:
            views = latest.get("views", 0)
            likes = latest.get("likes", 0)
            collects = latest.get("collects", 0)
            comments = latest.get("comments", 0)
            eng_rate = ((likes + collects + comments) / views * 100) if views > 0 else 0
            print(f"   最新: 👁️ {views:,} ⬆️ {likes:,} ⭐ {collects:,} 💬 {comments:,} | 互动率 {eng_rate:.1f}%")

        # 检查下一个待记录时间点
        next_cp = get_next_checkpoint(post["published_at"])
        if next_cp:
            time_name, seconds_left = next_cp
            print(f"   ⏰ 下个记录点: {time_name} (约{seconds_left/3600:.1f}h后)")


# ============ 主函数 ============

def main():
    parser = argparse.ArgumentParser(
        description='小红书笔记复盘工具 (Obsidian版)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
示例:

# 创建新帖子记录
python scripts/review_xhs.py --create --title "标题" --desc "正文" --tags "AI,效率工具"

# 首次记录帖子数据
python scripts/review_xhs.py --note-id xxx --record --api-mode

# 持续追踪
python scripts/review_xhs.py --note-id xxx --track --daemon

# 查看历史数据
python scripts/review_xhs.py --note-id xxx --history

# 生成复盘报告
python scripts/review_xhs.py --note-id xxx --report

# 列出所有帖子
python scripts/review_xhs.py --list
        '''
    )

    parser.add_argument('--create', action='store_true', help='创建新帖子记录')
    parser.add_argument('--title', help='帖子标题')
    parser.add_argument('--desc', help='帖子正文')
    parser.add_argument('--tags', help='标签（逗号分隔）')
    parser.add_argument('--publish', action='store_true', help='标记为已发布')
    parser.add_argument('--note-id', help='帖子ID或文件名的一部分')
    parser.add_argument('--record', action='store_true', help='记录当前数据')
    parser.add_argument('--track', action='store_true', help='持续追踪数据')
    parser.add_argument('--daemon', action='store_true', help='持续运行模式')
    parser.add_argument('--history', action='store_true', help='查看历史数据')
    parser.add_argument('--report', action='store_true', help='生成复盘报告')
    parser.add_argument('--list', action='store_true', help='列出所有追踪的帖子')
    parser.add_argument('--api-mode', action='store_true', help='使用 API 模式')
    parser.add_argument('--api-url', default=None, help='API 服务地址')

    args = parser.parse_args()

    # 加载配置
    config = load_config()
    print(f"📁 Obsidian Vault: {config['vault_path']}")

    if len(sys.argv) == 1:
        parser.print_help()
        print("\n💡 快速开始:")
        print("  1. python scripts/review_xhs.py --create --title '标题' --desc '内容' --publish")
        print("  2. python scripts/review_xhs.py --note-id xxx --record --api-mode")
        print("  3. python scripts/review_xhs.py --note-id xxx --report")
        print("  4. python scripts/review_xhs.py --list")
        return

    if args.create:
        if not args.title:
            print("❌ --create 需要指定 --title")
            return
        cmd_create(args, config)

    elif args.record:
        if not args.note_id:
            print("❌ --record 需要指定 --note-id")
            return
        cmd_record(args, config)

    elif args.track:
        if not args.note_id:
            print("❌ --track 需要指定 --note-id")
            return
        cmd_track(args, config)

    elif args.history:
        if not args.note_id:
            print("❌ --history 需要指定 --note-id")
            return
        cmd_history(args, config)

    elif args.report:
        if not args.note_id:
            print("❌ --report 需要指定 --note-id")
            return
        cmd_report(args, config)

    elif args.list:
        cmd_list(config)

    else:
        parser.print_help()


if __name__ == '__main__':
    main()
