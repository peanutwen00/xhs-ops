#!/usr/bin/env python3
"""
小红书笔记发布脚本

支持浏览器自动化发布和API发布两种方式

使用方法:

# 基本用法（浏览器自动化）
python publish_xhs.py --title "标题" --desc "描述" --images cover.png card_1.png

# 使用API模式发布
python publish_xhs.py --title "标题" --desc "描述" --images *.png --api-mode

# 定时发布
python publish_xhs.py -t "标题" -d "描述" -i *.png --post-time "2024-12-01 10:00:00"

# 仅验证模式
python publish_xhs.py -t "标题" -d "描述" -i *.png --dry-run

环境配置:

在 .env 文件中配置：
XHS_COOKIE=your_cookie_string_here
XHS_API_URL=http://localhost:5005  # API模式需要

依赖安装:
pip install playwright python-dotenv requests
playwright install chromium
"""

import argparse
import os
import sys
import json
import random
import time
from pathlib import Path
from typing import List, Optional, Dict, Any

try:
    from dotenv import load_dotenv
except ImportError:
    print("⚠️  缺少 dotenv: pip install python-dotenv")

try:
    import requests
except ImportError:
    print("⚠️  缺少 requests: pip install requests")


def load_cookie() -> str:
    """从 .env 文件加载 Cookie"""
    env_paths = [
        Path.cwd() / '.env',
        Path(__file__).parent.parent / '.env',
        Path(__file__).parent.parent.parent / '.env',
    ]

    for env_path in env_paths:
        if env_path.exists():
            load_dotenv(env_path)
            break

    cookie = os.getenv('XHS_COOKIE')
    if not cookie:
        print("❌ 错误: 未找到 XHS_COOKIE 环境变量")
        print("\n请创建 .env 文件，添加以下内容：")
        print("XHS_COOKIE=your_cookie_string_here")
        print("\nCookie 获取方式：")
        print("1. 在浏览器中登录小红书（https://www.xiaohongshu.com）")
        print("2. 打开开发者工具（F12）")
        print("3. 在 Network 标签中查看任意请求的 Cookie 头")
        print("4. 复制完整的 cookie 字符串")
        sys.exit(1)

    return cookie


def parse_cookie(cookie_string: str) -> Dict[str, str]:
    """解析 Cookie 字符串为字典"""
    cookies = {}
    for item in cookie_string.split(';'):
        item = item.strip()
        if '=' in item:
            key, value = item.split('=', 1)
            cookies[key.strip()] = value.strip()
    return cookies


def validate_images(image_paths: List[str]) -> List[str]:
    """验证图片文件是否存在"""
    valid_images = []
    for path in image_paths:
        if os.path.exists(path):
            valid_images.append(os.path.abspath(path))
        else:
            print(f"⚠️  警告: 图片不存在 - {path}")

    if not valid_images:
        print("❌ 错误: 没有有效的图片文件")
        sys.exit(1)

    return valid_images


class BrowserPublisher:
    """浏览器自动化发布模式"""

    def __init__(self):
        self.browser = None
        self.context = None
        self.page = None

    async def init(self):
        """初始化浏览器"""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            print("❌ 错误: 缺少 playwright")
            print("请运行: pip install playwright && playwright install chromium")
            sys.exit(1)

        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=False)
        self.context = await self.browser.new_context(
            viewport={'width': 1280, 'height': 800}
        )
        self.page = await self.context.new_page()

        # 登录小红书
        await self._login()

    async def _login(self):
        """登录小红书"""
        print("🔐 正在检查登录状态...")

        await self.page.goto('https://www.xiaohongshu.com')
        await self.page.wait_for_load_state('networkidle')

        # 检查是否需要登录
        if '/user/profile' not in self.page.url:
            print("📱 请在浏览器中完成扫码登录...")
            await self.page.wait_for_url('**/user/profile/**', timeout=120000)
            print("✅ 登录成功！")

    def _human_delay(self, min_sec: float = 1.0, max_sec: float = 3.0):
        """模拟人类延迟"""
        delay = random.uniform(min_sec, max_sec)
        time.sleep(delay)

    async def publish(self, title: str, desc: str, images: List[str]) -> Dict[str, Any]:
        """发布图文笔记"""
        print(f"\n🚀 准备发布笔记（浏览器模式）...")
        print(f" 📌 标题: {title}")
        print(f" 📝 描述: {desc[:50]}..." if len(desc) > 50 else f" 📝 描述: {desc}")
        print(f" 🖼️  图片数量: {len(images)}")

        try:
            # 进入发布页面
            print("📄 进入创作入口...")
            await self.page.goto('https://www.xiaohongshu.com/publish')
            self._human_delay(2, 4)

            # 上传图片
            print("🖼️  上传图片...")
            upload_input = await self.page.wait_for_selector(
                'input[type="file"]',
                timeout=10000
            )
            await upload_input.set_input_files(images)
            self._human_delay(3, 5)

            # 等待图片上传完成
            await self.page.wait_for_selector('.upload-progress', state='hidden', timeout=30000)
            print("✅ 图片上传完成")

            # 填写标题
            print("✏️  填写标题...")
            title_input = await self.page.wait_for_selector('input[data-component="title"]', timeout=10000)
            await title_input.click()
            self._human_delay(0.5, 1)

            # 模拟人类输入
            for char in title:
                await title_input.type(char)
                self._human_delay(0.05, 0.15)
            print("✅ 标题填写完成")

            # 填写正文
            print("📝 填写正文...")
            desc_input = await self.page.wait_for_selector('textarea[data-component="desc"]', timeout=10000)
            await desc_input.click()
            self._human_delay(0.5, 1)

            for char in desc:
                await desc_input.type(char)
                self._human_delay(0.03, 0.1)
            print("✅ 正文填写完成")

            # 提交前确认
            print("\n⏸️  发布前确认...")
            print("请检查内容是否正确，然后告诉我\"确认发布\"继续")

            return {"status": "pending_confirm", "page_url": self.page.url}

        except Exception as e:
            print(f"\n❌ 发布过程出错: {e}")
            raise

    async def confirm_publish(self) -> Dict[str, Any]:
        """确认发布"""
        try:
            print("🚀 确认发布...")
            publish_btn = await self.page.wait_for_selector('button[data-component="publish"]', timeout=10000)
            await publish_btn.click()
            self._human_delay(3, 5)

            # 检查是否发布成功
            if 'explore' in self.page.url or 'discovery' in self.page.url:
                note_id = self.page.url.split('/')[-1].split('?')[0]
                print("\n✨ 笔记发布成功！")
                print(f" 📎 笔记ID: {note_id}")
                print(f" 🔗 链接: https://www.xiaohongshu.com/explore/{note_id}")
                return {"status": "success", "note_id": note_id}
            else:
                print("\n⚠️  发布结果未知，请手动检查")
                return {"status": "unknown", "page_url": self.page.url}

        except Exception as e:
            print(f"\n❌ 发布确认失败: {e}")
            return {"status": "failed", "error": str(e)}

    async def close(self):
        """关闭浏览器"""
        if self.browser:
            await self.browser.close()
        if hasattr(self, 'playwright'):
            await self.playwright.stop()


class ApiPublisher:
    """API 发布模式"""

    def __init__(self, cookie: str, api_url: str = None):
        self.cookie = cookie
        self.api_url = api_url or os.getenv('XHS_API_URL', 'http://localhost:5005')
        self.session_id = 'xhs_auto_session'

    def init_client(self):
        """初始化 API 客户端"""
        print(f"📡 连接 API 服务: {self.api_url}")

        try:
            resp = requests.get(f"{self.api_url}/health", timeout=5)
            if resp.status_code != 200:
                raise Exception("API 服务不可用")
        except requests.exceptions.RequestException as e:
            print(f"❌ 无法连接到 API 服务: {e}")
            print(f"\n💡 请确保 xhs-api 服务已启动")
            sys.exit(1)

        # 初始化 session
        try:
            resp = requests.post(
                f"{self.api_url}/init",
                json={"session_id": self.session_id, "cookie": self.cookie},
                timeout=30
            )
            result = resp.json()
            if result.get('status') == 'success':
                print(f"✅ API 初始化成功")
                user_info = result.get('user_info', {})
                if user_info:
                    print(f"👤 当前用户: {user_info.get('nickname', '未知')}")
            else:
                raise Exception(result.get('error', '初始化失败'))
        except Exception as e:
            print(f"❌ API 初始化失败: {e}")
            sys.exit(1)

    def publish(self, title: str, desc: str, images: List[str], is_private: bool = True) -> Dict[str, Any]:
        """发布图文笔记"""
        print(f"\n🚀 准备发布笔记（API 模式）...")
        print(f" 📌 标题: {title}")
        print(f" 📝 描述: {desc[:50]}..." if len(desc) > 50 else f" 📝 描述: {desc}")
        print(f" 🖼️  图片数量: {len(images)}")

        try:
            payload = {
                "session_id": self.session_id,
                "title": title,
                "desc": desc,
                "files": images,
                "is_private": is_private
            }

            resp = requests.post(
                f"{self.api_url}/publish/image",
                json=payload,
                timeout=120
            )
            result = resp.json()

            if resp.status_code == 200 and result.get('status') == 'success':
                print("\n✨ 笔记发布成功！")
                publish_result = result.get('result', {})
                note_id = publish_result.get('note_id') or publish_result.get('id')
                if note_id:
                    print(f" 📎 笔记ID: {note_id}")
                    print(f" 🔗 链接: https://www.xiaohongshu.com/explore/{note_id}")
                return publish_result
            else:
                raise Exception(result.get('error', '发布失败'))

        except Exception as e:
            print(f"\n❌ 发布失败: {e}")
            return {"status": "failed", "error": str(e)}


def main():
    parser = argparse.ArgumentParser(
        description='小红书笔记发布工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
示例:

# 基本用法（浏览器自动化）
python publish_xhs.py -t "我的标题" -d "正文内容" -i cover.png card_1.png card_2.png

# 公开发布
python publish_xhs.py -t "我的标题" -d "正文内容" -i *.png --public

# 使用 API 模式
python publish_xhs.py -t "我的标题" -d "正文内容" -i *.png --api-mode

# 仅验证
python publish_xhs.py -t "我的标题" -d "正文内容" -i *.png --dry-run
        '''
    )

    parser.add_argument('-t', '--title', required=True, help='笔记标题（不超过20字）')
    parser.add_argument('-d', '--desc', default='', help='笔记描述/正文内容')
    parser.add_argument('-i', '--images', nargs='+', required=True, help='图片文件路径')
    parser.add_argument('--public', action='store_true', help='公开发布（默认为仅自己可见）')
    parser.add_argument('--api-mode', action='store_true', help='使用 API 模式发布')
    parser.add_argument('--dry-run', action='store_true', help='仅验证，不实际发布')
    parser.add_argument('--api-url', default=None, help='API 服务地址')

    args = parser.parse_args()

    # 验证标题长度
    if len(args.title) > 20:
        print(f"⚠️  警告: 标题超过20字，将被截断")
        args.title = args.title[:20]

    # 验证图片
    valid_images = validate_images(args.images)

    if args.dry_run:
        print("\n🔍 验证模式 - 不会实际发布")
        print(f" 📌 标题: {args.title}")
        print(f" 📝 描述: {args.desc}")
        print(f" 🖼️  图片: {valid_images}")
        print(f" 🔒 私密: {not args.public}")
        print("\n✅ 验证通过，可以发布")
        return

    # 选择发布方式
    if args.api_mode:
        cookie = load_cookie()
        publisher = ApiPublisher(cookie, args.api_url)
        publisher.init_client()
        result = publisher.publish(
            title=args.title,
            desc=args.desc,
            images=valid_images,
            is_private=not args.public
        )
    else:
        # 浏览器模式
        import asyncio

        async def run_browser():
            publisher = BrowserPublisher()
            await publisher.init()
            result = await publisher.publish(args.title, args.desc, valid_images)
            await publisher.close()
            return result

        result = asyncio.run(run_browser())
        print(f"\n结果: {result}")


if __name__ == '__main__':
    main()
