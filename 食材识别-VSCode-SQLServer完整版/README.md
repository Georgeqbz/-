# 智能食检（VS Code + 本地 SQL Server）

## 第一次运行

1. 在 SQL Server 配置管理器中确认 SQL Server 服务已启动。
2. 确认已安装 **ODBC Driver 18 for SQL Server**。
3. 用 VS Code 打开本文件夹。
4. 在 VS Code 终端执行：

```powershell
py -m venv .venv
.\.venv\Scripts\activate
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

5. 打开 `.env`，按你的 SQL Server 实例名修改 `DB_SERVER`。
6. 运行 `app.py`，或按 `F5` 选择“运行智能食检”。
7. 浏览器打开 <http://127.0.0.1:5000>。

程序首次启动会自动创建 `smart_food_db` 数据库、数据表、索引和少量演示数据。

## 个人营养 AI 助手

登录后点击页面右下角的发光 AI 核心。助手只通过当前登录会话读取该用户自己的用户名、
健康目标、今日识别、收藏食谱和最近对话，不会读取其他用户的数据。对话记录保存在
SQL Server 的 `assistant_messages` 表中。

若要启用真正的通义千问开放式对话，请在 `.env` 填写：

```dotenv
DASHSCOPE_API_KEY=你的阿里云百炼API Key
QWEN_MODEL=qwen-plus
QWEN_API_URL=https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions
```

启用后，助手会把当前登录用户的用户名、健康目标、今日识别、收藏摘要和最近对话发送给
阿里云百炼，Qwen 负责通用知识与个性化回答。不会发送密码、数据库连接信息或 API 密钥。

## 常见 SQL Server 实例名

- SQL Server Express：`localhost\SQLEXPRESS`
- 默认实例：`localhost`
- LocalDB：`(localdb)\MSSQLLocalDB`

默认配置使用 Windows 身份验证。若使用 `sa` 登录，把 `.env` 改为：

```dotenv
DB_TRUSTED_CONNECTION=no
DB_USER=sa
DB_PASSWORD=你的密码
```

## 图片识别

在 `.env` 填写百度和天聚数行密钥后才会启用真实图片识别与在线菜谱。密钥不要写回 `app.py`，也不要提交 `.env`。
