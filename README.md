# 小红书科技账号运营助手

一站式工具：账号分析 | 竞品拆解 | 选题灵感 | 自动发布 | 配图生成

## 安装

```bash
/plugin install "/Users/izumi/Documents/code/xhs-ops"
```

## 安装依赖

```bash
pip install playwright markdown pillow python-dotenv requests
playwright install chromium
```

## 配置

创建 `.env` 文件：
```
XHS_COOKIE=你的小红书cookie
```

Cookie 获取：在小红书网页版打开开发者工具，复制 Network 请求的 Cookie。

## 使用示例

### 分析账号
```
分析我的AI工具账号：https://www.xiaohongshu.com/user/profile/xxx
```

### 竞品分析
```
分析这几个科技账号，给我可执行的优化建议
```

### 生成选题
```
生成下一周的AI工具选题，定位是程序员效率工具
```

### 发布笔记
```
发布一篇Claude测评，标题用了30天Claude，说说真实感受
正文：分享深度使用心得...
配图用ocean风格
```

### 生成配图
```
生成代码技巧分享的封面，风格terminal
```

### 检查评论
```
检查并回复最新评论
```

## 脚本

```bash
# 配图生成
python scripts/render_xhs.py --cover "标题" -s ocean
python scripts/render_xhs.py -t "标题" -c "正文" -s terminal

# 发布
python scripts/publish_xhs.py -t "标题" -d "正文" -i *.png --dry-run
```

## 项目结构

```
xhs-ops/
├── SKILL.md              # 核心技能文件
├── README.md
├── requirements.txt
└── scripts/
    ├── render_xhs.py    # 配图渲染
    └── publish_xhs.py   # 发布脚本
```

## 注意事项

- ⚠️ 发布前需确认
- 默认仅自己可见草稿
- 每日发布 1-2 篇为宜
- 遇到风控提示立即停止
test
