#!/usr/bin/env python3
"""
小红书配图渲染脚本

将Markdown或文本内容渲染成小红书风格的卡片图片

使用方法:
    # 生成单张卡片
    python render_xhs.py --title "标题" --content "正文" --style "purple"

    # 生成封面大字报
    python render_xhs.py --cover "封面大字" --style "playful-geometric"

    # 从Markdown文件渲染
    python render_xhs.py --input "content.md" --style "xiaohongshu"

    # 指定分页模式
    python render_xhs.py --title "标题" --content "正文" --pagination "auto-split"

环境:
    - 需要 playwright: pip install playwright && playwright install chromium
    - 输出目录: /tmp/openclaw/uploads/
"""

import argparse
import asyncio
import os
import re
import sys
import random
from pathlib import Path
from typing import List, Optional, Tuple

# 卡片尺寸配置
CARD_WIDTH = 1080
CARD_HEIGHT = 1440
SAFE_HEIGHT = 1340
PADDING = 60
LINE_HEIGHT = 1.8

# 主题样式定义
STYLES = {
    "purple": {
        "bg_start": "#667eea",
        "bg_end": "#764ba2",
        "text": "#ffffff",
        "accent": "#f0e6ff",
        "gradient_angle": 135
    },
    "xiaohongshu": {
        "bg_start": "#fe4c4c",
        "bg_end": "#ff6b6b",
        "text": "#ffffff",
        "accent": "#fff5f5",
        "gradient_angle": 135
    },
    "mint": {
        "bg_start": "#11998e",
        "bg_end": "#38ef7d",
        "text": "#ffffff",
        "accent": "#e8fff5",
        "gradient_angle": 135
    },
    "sunset": {
        "bg_start": "#ff7e5f",
        "bg_end": "#feb47b",
        "text": "#ffffff",
        "accent": "#fff8f5",
        "gradient_angle": 135
    },
    "ocean": {
        "bg_start": "#2193b0",
        "bg_end": "#6dd5ed",
        "text": "#ffffff",
        "accent": "#f0faff",
        "gradient_angle": 135
    },
    "elegant": {
        "bg_start": "#2c3e50",
        "bg_end": "#4ca1af",
        "text": "#ffffff",
        "accent": "#f5f5f5",
        "gradient_angle": 135
    },
    "dark": {
        "bg_start": "#0f0f0f",
        "bg_end": "#434343",
        "text": "#ffffff",
        "accent": "#1a1a1a",
        "gradient_angle": 135
    }
}

# 封面大字报样式
COVER_STYLES = {
    "default": {
        "font_size": 120,
        "bold": True,
        "shadow": True,
        "emoji": False
    },
    "playful-geometric": {
        "font_size": 100,
        "bold": True,
        "shadow": True,
        "emoji": True,
        "bg_pattern": "circles"
    },
    "neo-brutalism": {
        "font_size": 90,
        "bold": True,
        "shadow": True,
        "border": 8,
        "emoji": True
    },
    "botanical": {
        "font_size": 80,
        "bold": False,
        "shadow": False,
        "decorative": "leaves",
        "emoji": False
    },
    "professional": {
        "font_size": 100,
        "bold": True,
        "shadow": False,
        "line": True,
        "emoji": False
    },
    "retro": {
        "font_size": 85,
        "bold": True,
        "shadow": True,
        "texture": "grain",
        "emoji": False
    },
    "terminal": {
        "font_size": 72,
        "bold": False,
        "shadow": False,
        "font_family": "monospace",
        "emoji": False
    },
    "sketch": {
        "font_size": 95,
        "bold": True,
        "shadow": False,
        "handwritten": True,
        "emoji": True
    }
}

# 分页模式
PAGINATION_MODES = ["separator", "auto-fit", "auto-split", "dynamic"]


def parse_markdown_file(filepath: str) -> Tuple[Optional[str], List[str]]:
    """解析Markdown文件，提取标题和内容"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        return parse_markdown(content)
    except Exception as e:
        print(f"读取文件失败: {e}")
        return None, []


def parse_markdown(content: str) -> Tuple[Optional[str], List[str]]:
    """解析Markdown内容"""
    lines = content.strip().split('\n')
    title = None
    paragraphs = []
    current_para = []

    for line in lines:
        line = line.strip()
        if not line:
            if current_para:
                paragraphs.append(' '.join(current_para))
                current_para = []
            continue

        # 提取标题
        if line.startswith('# ') and not title:
            title = line[2:].strip()
        elif line.startswith('#'):
            # 跳过子标题
            if current_para:
                paragraphs.append(' '.join(current_para))
                current_para = []
            paragraphs.append(f"[SUBTITLE]{line.lstrip('#').strip()}[/SUBTITLE]")
        elif line.startswith('---'):
            # 分隔符
            if current_para:
                paragraphs.append(' '.join(current_para))
                current_para = []
            paragraphs.append("[PAGE_BREAK]")
        elif line.startswith('- ') or line.startswith('* '):
            # 列表项
            current_para.append(line[2:].strip())
        elif line.startswith(('1.', '2.', '3.', '4.', '5.')):
            # 数字列表
            current_para.append(line.split('.', 1)[1].strip() if '.' in line else line)
        else:
            # 清理Markdown格式
            cleaned = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', line)  # 链接
            cleaned = re.sub(r'\*\*([^\*]+)\*\*', r'\1', cleaned)  # 粗体
            cleaned = re.sub(r'\*([^\*]+)\*', r'\1', cleaned)  # 斜体
            cleaned = re.sub(r'`([^`]+)`', r'\1', cleaned)  # 行内代码
            current_para.append(cleaned)

    if current_para:
        paragraphs.append(' '.join(current_para))

    return title, [p for p in paragraphs if p and not p.startswith('[PAGE_BREAK]')]


def split_content_by_separator(content: List[str]) -> List[List[str]]:
    """按分隔符拆分内容"""
    pages = []
    current_page = []

    for item in content:
        if item == "[PAGE_BREAK]":
            if current_page:
                pages.append(current_page)
                current_page = []
        else:
            current_page.append(item)

    if current_page:
        pages.append(current_page)

    return pages if pages else [content]


def estimate_content_height(text: str, font_size: int = 42, width: int = None) -> float:
    """估算内容高度"""
    width = width or (CARD_WIDTH - PADDING * 2)
    chars_per_line = width // (font_size * 0.6)
    lines = 0
    for para in text.split('\n'):
        para_lines = max(1, len(para) // chars_per_line + (1 if len(para) % chars_per_line else 0))
        lines += para_lines
    return lines * font_size * LINE_HEIGHT


def smart_split_content(content: List[str], max_height: float) -> List[List[str]]:
    """智能分页"""
    pages = []
    current_page = []
    current_height = 0

    for item in content:
        if item.startswith('[SUBTITLE]'):
            item_height = 60  # 子标题高度
        else:
            item_height = estimate_content_height(item)

        if current_height + item_height > max_height and current_page:
            pages.append(current_page)
            current_page = [item]
            current_height = item_height
        else:
            current_page.append(item)
            current_height += item_height

    if current_page:
        pages.append(current_page)

    return pages if pages else [content]


def convert_markdown_to_html(content: List[str], style: dict) -> str:
    """将内容转换为HTML"""
    html_parts = []

    for item in content:
        if item.startswith('[SUBTITLE]'):
            title_text = item.replace('[SUBTITLE]', '').replace('[/SUBTITLE]', '')
            html_parts.append(f'<h2 class="subtitle">{title_text}</h2>')
        else:
            # 处理换行
            text = item.replace('\n', '<br>')
            html_parts.append(f'<p class="content">{text}</p>')

    return '\n'.join(html_parts)


def generate_cover_html(text: str, style_name: str = "default") -> str:
    """生成封面大字报HTML"""
    cover_style = COVER_STYLES.get(style_name, COVER_STYLES["default"])
    base_style = random.choice(list(STYLES.values()))
    bg_start = base_style["bg_start"]
    bg_end = base_style["bg_end"]
    text_color = base_style["text"]
    accent = base_style["accent"]

    font_size = cover_style.get("font_size", 120)
    font_weight = "bold" if cover_style.get("bold", True) else "normal"

    shadow_html = ""
    if cover_style.get("shadow", True):
        shadow_html = f"""
        .cover-text {{
            text-shadow: 8px 8px 0 rgba(0,0,0,0.3);
        }}
        """

    border_html = ""
    if cover_style.get("border"):
        border_html = f"""
        .cover-container {{
            border: {cover_style['border']}px solid {text_color};
        }}
        """

    line_html = ""
    if cover_style.get("line", False):
        line_html = f"""
        .cover-line {{
            width: 200px;
            height: 4px;
            background: {accent};
            margin: 30px auto;
        }}
        """

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{
                width: {CARD_WIDTH}px;
                height: {CARD_HEIGHT}px;
                background: linear-gradient({base_style.get('gradient_angle', 135)}deg, {bg_start}, {bg_end});
                display: flex;
                justify-content: center;
                align-items: center;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            }}
            .cover-container {{
                width: {CARD_WIDTH - PADDING * 2}px;
                height: {CARD_HEIGHT - PADDING * 2}px;
                display: flex;
                flex-direction: column;
                justify-content: center;
                align-items: center;
                text-align: center;
                padding: 60px;
                {border_html}
            }}
            .cover-text {{
                font-size: {font_size}px;
                font-weight: {font_weight};
                color: {text_color};
                line-height: 1.4;
                max-width: 100%;
                word-wrap: break-word;
            }}
            .cover-accent {{
                width: 100px;
                height: 4px;
                background: {accent};
                margin: 40px 0;
                opacity: 0.8;
            }}
            .cover-tag {{
                font-size: 28px;
                color: {accent};
                margin-top: 40px;
                letter-spacing: 8px;
            }}
            {shadow_html}
            {line_html}
        </style>
    </head>
    <body>
        <div class="cover-container">
            <div class="cover-text">{text}</div>
            <div class="cover-accent"></div>
            {line_html}
            <div class="cover-tag">XIAOHONGSHU</div>
        </div>
    </body>
    </html>
    """
    return html


def generate_card_html(title: str, content: str, style_name: str = "purple") -> str:
    """生成卡片HTML"""
    style = STYLES.get(style_name, STYLES["purple"])
    bg_start = style["bg_start"]
    bg_end = style["bg_end"]
    text_color = style["text"]
    accent = style["accent"]

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{
                width: {CARD_WIDTH}px;
                min-height: {CARD_HEIGHT}px;
                background: linear-gradient({style.get('gradient_angle', 135)}deg, {bg_start}, {bg_end});
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                color: {text_color};
                padding: {PADDING}px;
            }}
            .header {{
                margin-bottom: 40px;
            }}
            .title {{
                font-size: 56px;
                font-weight: bold;
                line-height: 1.3;
                text-shadow: 4px 4px 0 rgba(0,0,0,0.2);
            }}
            .content {{
                font-size: 42px;
                line-height: {LINE_HEIGHT};
                opacity: 0.95;
            }}
            .subtitle {{
                font-size: 48px;
                font-weight: bold;
                margin: 30px 0 20px 0;
                padding-bottom: 15px;
                border-bottom: 3px solid {accent};
            }}
            .footer {{
                position: fixed;
                bottom: 40px;
                left: {PADDING}px;
                right: {PADDING}px;
                display: flex;
                justify-content: space-between;
                align-items: center;
            }}
            .tag {{
                font-size: 24px;
                color: {accent};
                letter-spacing: 4px;
            }}
            .brand {{
                font-size: 24px;
                opacity: 0.7;
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1 class="title">{title}</h1>
        </div>
        <div class="content">
            {content}
        </div>
        <div class="footer">
            <span class="tag">#小红书</span>
            <span class="brand">@创作者</span>
        </div>
    </body>
    </html>
    """
    return html


async def measure_content_height(page, html: str) -> float:
    """测量HTML内容实际高度"""
    await page.set_content(html)
    await page.wait_for_load_state('networkidle')
    height = await page.evaluate('''() => {
        return document.body.scrollHeight;
    }''')
    return height


async def render_html_to_image(page, html: str, output_path: str, viewport_size: dict = None):
    """将HTML渲染为图片"""
    viewport = viewport_size or {"width": CARD_WIDTH, "height": CARD_HEIGHT}
    await page.set_viewport_size(viewport)
    await page.set_content(html)
    await page.wait_for_load_state('networkidle')

    await page.screenshot(path=output_path, full_page=True)
    print(f"✓ 生成图片: {output_path}")


async def process_and_render_cards(
    cards: List[Tuple[str, str]],
    style: str,
    output_dir: str,
    prefix: str = "card"
) -> List[str]:
    """处理并渲染多个卡片"""
    from playwright.async_api import async_playwright

    output_paths = []

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()

        for i, (title, content) in enumerate(cards):
            html = generate_card_html(title, content, style)
            output_path = os.path.join(output_dir, f"{prefix}_{i+1}.png")
            await render_html_to_image(page, html, output_path)
            output_paths.append(output_path)

        await browser.close()

    return output_paths


def render_markdown_to_cards(
    title: str,
    content: List[str],
    style: str = "purple",
    pagination: str = "auto-split",
    output_dir: str = "/tmp/openclaw/uploads",
    prefix: str = "card"
) -> List[str]:
    """将Markdown内容渲染为多个卡片"""
    # 分页
    if pagination == "separator":
        pages = split_content_by_separator(content)
    elif pagination in ["auto-fit", "auto-split"]:
        pages = smart_split_content(content, SAFE_HEIGHT)
    elif pagination == "dynamic":
        # 动态分页：每页一个主要内容块
        pages = [[item] for item in content]
    else:
        pages = [content]

    # 准备卡片数据
    cards = []
    for i, page_content in enumerate(pages):
        card_title = f"{title} ({i+1}/{len(pages)})" if len(pages) > 1 else title
        card_content = '\n'.join(page_content)
        cards.append((card_title, convert_markdown_to_html([card_content], {})))

    # 渲染
    return asyncio.run(process_and_render_cards(cards, style, output_dir, prefix))


def render_cover_to_image(
    text: str,
    style: str = "default",
    output_path: str = "/tmp/openclaw/uploads/cover.png"
) -> str:
    """渲染封面大字报"""
    html = generate_cover_html(text, style)

    asyncio.run(render_html_to_image_simple(html, output_path))
    return output_path


async def render_html_to_image_simple(html: str, output_path: str):
    """简单的HTML渲染"""
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await render_html_to_image(page, html, output_path)
        await browser.close()


def list_styles():
    """列出所有可用的样式"""
    print("\n📦 可用配色主题:")
    for name in STYLES.keys():
        print(f"   - {name}")

    print("\n📦 可用封面大字报样式:")
    for name in COVER_STYLES.keys():
        print(f"   - {name}")

    print("\n📦 可用分页模式:")
    for mode in PAGINATION_MODES:
        print(f"   - {mode}")


def main():
    parser = argparse.ArgumentParser(
        description='小红书配图渲染工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
示例:

# 生成单张卡片
python render_xhs.py -t "职场干货" -c "职场沟通技巧分享..."

# 生成多卡片
python render_xhs.py -t "5个技巧" -c "技巧1... --- 技巧2..." -p auto-split

# 生成封面大字报
python render_xhs.py --cover "今日分享" --cover-style playful-geometric

# 从Markdown渲染
python render_xhs.py -i post.md -s xiaohongshu

# 列出所有样式
python render_xhs.py --list-styles
        '''
    )

    parser.add_argument('-t', '--title', help='卡片标题')
    parser.add_argument('-c', '--content', help='正文内容（用---分隔多页）')
    parser.add_argument('-i', '--input', help='Markdown文件路径')
    parser.add_argument('--cover', help='封面大字报文字')
    parser.add_argument('-s', '--style', default='purple', help='配色主题')
    parser.add_argument('--cover-style', default='default', help='封面大字报样式')
    parser.add_argument('-p', '--pagination', default='auto-split', choices=PAGINATION_MODES, help='分页模式')
    parser.add_argument('-o', '--output', default='/tmp/openclaw/uploads/', help='输出目录')
    parser.add_argument('--prefix', default='card', help='文件名前缀')
    parser.add_argument('--list-styles', action='store_true', help='列出所有样式')

    args = parser.parse_args()

    if args.list_styles:
        list_styles()
        return

    # 验证参数
    if not args.cover and not (args.title or args.input):
        print("❌ 错误: 请提供 --cover 或 --title/--content 或 --input")
        parser.print_help()
        sys.exit(1)

    # 确保输出目录存在
    os.makedirs(args.output, exist_ok=True)

    # 生成封面
    if args.cover:
        output_path = os.path.join(args.output, 'cover.png')
        render_cover_to_image(args.cover, args.cover_style, output_path)
        print(f"\n✨ 封面生成完成: {output_path}")
        return

    # 获取内容和标题
    if args.input:
        title, content_parts = parse_markdown_file(args.input)
        if not title and not args.title:
            print("❌ 错误: Markdown文件未找到标题，请手动指定 -t")
            sys.exit(1)
        title = args.title or title
        content = content_parts
    else:
        title = args.title
        # 按分隔符拆分内容
        content = args.content.split('---') if args.content else []

    # 渲染卡片
    output_paths = render_markdown_to_cards(
        title=title,
        content=[p.strip() for p in content if p.strip()],
        style=args.style,
        pagination=args.pagination,
        output_dir=args.output,
        prefix=args.prefix
    )

    print(f"\n✨ 生成了 {len(output_paths)} 张卡片:")
    for path in output_paths:
        print(f"   - {path}")


if __name__ == '__main__':
    main()
