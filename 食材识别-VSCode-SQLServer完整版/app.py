import os
import json
import uuid
import requests
import base64
import random
from dotenv import load_dotenv
from PIL import Image
from datetime import datetime, date, timedelta
from flask import Flask, request, jsonify, render_template, session
from werkzeug.security import generate_password_hash, check_password_hash
import pyodbc

load_dotenv()
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "change-me-in-env")

# ===== 环境配置 =====
ENV = os.environ.get('FLASK_ENV', 'development')

# ===== 本地 SQL Server 配置 =====
DB_SERVER = os.environ.get("DB_SERVER", r"localhost\SQLEXPRESS")
DB_NAME = os.environ.get("DB_NAME", "food_db")
DB_DRIVER = os.environ.get("DB_DRIVER", "ODBC Driver 18 for SQL Server")
DB_TRUSTED_CONNECTION = os.environ.get("DB_TRUSTED_CONNECTION", "yes").lower() in ("1", "yes", "true")

def _connection_string(database=None):
    parts = [
        f"DRIVER={{{DB_DRIVER}}}",
        f"SERVER={DB_SERVER}",
        f"DATABASE={database or DB_NAME}",
        "TrustServerCertificate=yes",
    ]
    if DB_TRUSTED_CONNECTION:
        parts.append("Trusted_Connection=yes")
    else:
        parts.extend([
            f"UID={os.environ.get('DB_USER', 'sa')}",
            f"PWD={os.environ.get('DB_PASSWORD', '')}",
        ])
    return ";".join(parts)

def get_db_connection():
    """获取本地 SQL Server 数据库连接"""
    return pyodbc.connect(_connection_string())

def init_database():
    """自动创建本地数据库、表、索引和演示数据。"""
    master = pyodbc.connect(_connection_string("master"), autocommit=True)
    db_identifier = DB_NAME.replace("]", "]]")
    db_literal = DB_NAME.replace("'", "''")
    master.cursor().execute(
        f"IF DB_ID(N'{db_literal}') IS NULL CREATE DATABASE [{db_identifier}]"
    )
    master.close()

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            IF OBJECT_ID(N'dbo.users', N'U') IS NULL
            CREATE TABLE dbo.users (
                id INT IDENTITY(1,1) PRIMARY KEY,
                username VARCHAR(80) NOT NULL UNIQUE,
                password_hash VARCHAR(256) NOT NULL,
                created_at DATETIME2 NOT NULL DEFAULT SYSDATETIME(),
                last_login DATETIME2 NULL
            )
        """)
        cursor.execute("""
            IF OBJECT_ID(N'dbo.ingredients', N'U') IS NULL
            CREATE TABLE dbo.ingredients (
                id INT IDENTITY(1,1) PRIMARY KEY,
                name NVARCHAR(50) NOT NULL,
                calories INT NOT NULL,
                emoji NVARCHAR(10) NULL,
                protein DECIMAL(6,2) NULL,
                fat DECIMAL(6,2) NULL,
                carb DECIMAL(6,2) NULL,
                created_at DATETIME2 NOT NULL DEFAULT SYSDATETIME()
            )
        """)
        cursor.execute("""
            IF OBJECT_ID(N'dbo.healthy_recipes', N'U') IS NULL
            CREATE TABLE dbo.healthy_recipes (
                id INT IDENTITY(1,1) PRIMARY KEY,
                name NVARCHAR(100) NOT NULL,
                calories INT NOT NULL,
                ingredients NVARCHAR(MAX) NOT NULL,
                steps NVARCHAR(MAX) NOT NULL,
                tips NVARCHAR(255) NULL,
                cuisine NVARCHAR(50) NOT NULL DEFAULT N'减脂餐',
                feature NVARCHAR(100) NOT NULL DEFAULT N'低卡健康',
                created_at DATETIME2 NOT NULL DEFAULT SYSDATETIME()
            )
        """)
        cursor.execute("""
            IF OBJECT_ID(N'dbo.user_favorites', N'U') IS NULL
            CREATE TABLE dbo.user_favorites (
                id INT IDENTITY(1,1) PRIMARY KEY,
                user_id INT NOT NULL,
                recipe_id INT NOT NULL,
                recipe_type NVARCHAR(20) NOT NULL DEFAULT N'healthy',
                recipe_name NVARCHAR(100) NOT NULL,
                recipe_calories INT NULL,
                recipe_ingredients NVARCHAR(MAX) NULL,
                recipe_steps NVARCHAR(MAX) NULL,
                recipe_tips NVARCHAR(255) NULL,
                recipe_cuisine NVARCHAR(50) NULL,
                recipe_feature NVARCHAR(100) NULL,
                tag NVARCHAR(20) NOT NULL DEFAULT N'想吃',
                created_at DATETIME2 NOT NULL DEFAULT SYSDATETIME(),
                CONSTRAINT UQ_user_favorite UNIQUE (user_id, recipe_id, recipe_type),
                CONSTRAINT FK_favorites_users FOREIGN KEY (user_id) REFERENCES dbo.users(id) ON DELETE CASCADE
            )
        """)
        cursor.execute("""
            IF OBJECT_ID(N'dbo.search_history', N'U') IS NULL
            CREATE TABLE dbo.search_history (
                id INT IDENTITY(1,1) PRIMARY KEY,
                user_id INT NULL,
                keyword NVARCHAR(100) NOT NULL,
                created_at DATETIME2 NOT NULL DEFAULT SYSDATETIME(),
                CONSTRAINT FK_search_users FOREIGN KEY (user_id) REFERENCES dbo.users(id) ON DELETE CASCADE
            )
        """)
        cursor.execute("""
            IF OBJECT_ID(N'dbo.health_profiles', N'U') IS NULL
            CREATE TABLE dbo.health_profiles (
                user_id INT NOT NULL PRIMARY KEY,
                gender NVARCHAR(10) NOT NULL DEFAULT N'male',
                age INT NOT NULL DEFAULT 25,
                height_cm DECIMAL(6,2) NOT NULL DEFAULT 170,
                weight_kg DECIMAL(6,2) NOT NULL DEFAULT 65,
                activity_level DECIMAL(4,2) NOT NULL DEFAULT 1.375,
                goal NVARCHAR(20) NOT NULL DEFAULT N'maintain',
                updated_at DATETIME2 NOT NULL DEFAULT SYSDATETIME(),
                CONSTRAINT FK_health_profiles_users FOREIGN KEY (user_id)
                    REFERENCES dbo.users(id) ON DELETE CASCADE
            )
        """)
        cursor.execute("""
            IF OBJECT_ID(N'dbo.assistant_messages', N'U') IS NULL
            CREATE TABLE dbo.assistant_messages (
                id INT IDENTITY(1,1) PRIMARY KEY,
                user_id INT NOT NULL,
                role NVARCHAR(20) NOT NULL,
                content NVARCHAR(1000) NOT NULL,
                created_at DATETIME2 NOT NULL DEFAULT SYSDATETIME(),
                CONSTRAINT FK_assistant_messages_users FOREIGN KEY (user_id)
                    REFERENCES dbo.users(id) ON DELETE CASCADE
            )
        """)
        cursor.execute("""
            IF OBJECT_ID(N'dbo.history', N'U') IS NULL
            CREATE TABLE dbo.history (
                id INT IDENTITY(1,1) PRIMARY KEY,
                user_id INT NOT NULL,
                food_name NVARCHAR(100) NOT NULL,
                recognized_as NVARCHAR(100) NULL,
                calorie_per_100g NVARCHAR(50) NULL,
                protein NVARCHAR(50) NULL,
                fat NVARCHAR(50) NULL,
                carbohydrate NVARCHAR(50) NULL,
                created_at DATETIME2 NOT NULL DEFAULT SYSDATETIME(),
                CONSTRAINT FK_history_users FOREIGN KEY (user_id) REFERENCES dbo.users(id) ON DELETE CASCADE
            )
        """)
        cursor.execute("""
            IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name=N'idx_history_user_id' AND object_id=OBJECT_ID(N'dbo.history'))
                CREATE INDEX idx_history_user_id ON dbo.history(user_id);
            IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name=N'idx_history_created_at' AND object_id=OBJECT_ID(N'dbo.history'))
                CREATE INDEX idx_history_created_at ON dbo.history(created_at);
        """)
        cursor.execute("""
            IF NOT EXISTS (SELECT 1 FROM dbo.ingredients)
            INSERT INTO dbo.ingredients (name, calories, emoji, protein, fat, carb) VALUES
            (N'西红柿',19,N'🍅',0.9,0.2,4.0),(N'鸡胸肉',133,N'🍗',24.6,1.9,2.5),
            (N'西兰花',36,N'🥦',4.1,0.6,4.3),(N'鸡蛋',144,N'🥚',13.3,8.8,2.8),
            (N'土豆',81,N'🥔',2.6,0.2,17.8),(N'黄瓜',16,N'🥒',0.8,0.2,2.9);

            IF NOT EXISTS (SELECT 1 FROM dbo.healthy_recipes)
            INSERT INTO dbo.healthy_recipes (name, calories, ingredients, steps, tips, cuisine, feature) VALUES
            (N'香煎鸡胸肉',260,N'鸡胸肉, 西兰花, 黑胡椒',N'鸡胸肉腌制后煎熟；西兰花焯水装盘。',N'少油慢煎更嫩。',N'减脂餐',N'高蛋白'),
            (N'番茄鸡蛋',220,N'西红柿, 鸡蛋',N'鸡蛋炒熟盛出；番茄炒软后混合。',N'少糖少盐。',N'家常菜',N'营养均衡'),
            (N'黄瓜土豆沙拉',190,N'黄瓜, 土豆, 生菜',N'土豆蒸熟切块；与黄瓜、生菜拌匀。',N'用无糖酸奶代替沙拉酱。',N'轻食',N'低脂饱腹');

            MERGE dbo.healthy_recipes AS target
            USING (VALUES
              (N'西兰花虾仁',230,N'西兰花, 虾仁, 蒜',N'西兰花焯水，虾仁炒熟后加入西兰花翻炒。',N'虾仁提前去虾线。',N'减脂餐',N'高蛋白低脂'),
              (N'鸡胸肉藜麦碗',360,N'鸡胸肉, 藜麦, 生菜, 玉米',N'藜麦煮熟，鸡胸肉煎熟切片，与蔬菜装碗。',N'酱汁控制在一汤匙内。',N'轻食',N'均衡饱腹'),
              (N'番茄豆腐汤',160,N'番茄, 嫩豆腐, 金针菇',N'番茄炒出汁后加水，放入豆腐和金针菇煮熟。',N'出锅前再放盐。',N'汤羹',N'低卡暖胃'),
              (N'燕麦香蕉早餐杯',310,N'燕麦, 香蕉, 无糖酸奶, 坚果',N'燕麦与酸奶分层装杯，加入香蕉片和少量坚果。',N'冷藏一晚口感更好。',N'早餐',N'高纤维'),
              (N'牛肉蔬菜卷',330,N'瘦牛肉, 生菜, 彩椒, 全麦饼',N'牛肉和彩椒炒熟，放入全麦饼和生菜卷起。',N'选择低脂牛肉。',N'轻食',N'高蛋白'),
              (N'南瓜小米粥',180,N'南瓜, 小米',N'南瓜切块，与淘洗后的小米一起煮至软糯。',N'不额外加糖。',N'早餐',N'清淡易消化'),
              (N'清蒸鲈鱼',280,N'鲈鱼, 姜, 葱',N'鱼身放姜片蒸熟，出锅撒葱丝并淋少量热油。',N'根据鱼大小调整蒸制时间。',N'家常菜',N'优质蛋白'),
              (N'菌菇鸡蛋汤',150,N'鸡蛋, 香菇, 海鲜菇',N'菌菇煮熟后淋入蛋液，调味即可。',N'蛋液缓慢倒入更均匀。',N'汤羹',N'低脂鲜美'),
              (N'紫薯酸奶碗',260,N'紫薯, 无糖酸奶, 蓝莓',N'紫薯蒸熟压泥，加入酸奶和蓝莓。',N'选择无添加糖酸奶。',N'早餐',N'高纤维低脂'),
              (N'芦笋炒鸡丁',250,N'芦笋, 鸡胸肉, 胡萝卜',N'鸡胸肉切丁炒熟，加入芦笋和胡萝卜翻炒。',N'大火快炒保持脆嫩。',N'减脂餐',N'高蛋白'),
              (N'冬瓜虾皮汤',95,N'冬瓜, 虾皮, 香葱',N'冬瓜煮至透明，加入虾皮和香葱。',N'虾皮含盐，少放盐。',N'汤羹',N'清爽低卡'),
              (N'全麦鸡蛋三明治',340,N'全麦面包, 鸡蛋, 生菜, 番茄',N'鸡蛋煎熟，与生菜番茄夹入全麦面包。',N'可用水煮蛋进一步减脂。',N'早餐',N'营养均衡')
            ) AS source(name, calories, ingredients, steps, tips, cuisine, feature)
            ON target.name = source.name
            WHEN NOT MATCHED THEN INSERT
              (name, calories, ingredients, steps, tips, cuisine, feature)
            VALUES
              (source.name, source.calories, source.ingredients, source.steps,
               source.tips, source.cuisine, source.feature);
        """)
        conn.commit()
        print("✅ 数据库表初始化成功")
    except Exception as e:
        conn.rollback()
        raise RuntimeError(f"SQL Server 数据库初始化失败: {e}") from e
    finally:
        conn.close()

# 配置上传文件夹
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ===== API密钥 =====
BAIDU_API_KEY = os.environ.get("BAIDU_API_KEY", "")
BAIDU_SECRET_KEY = os.environ.get("BAIDU_SECRET_KEY", "")
TIANAPI_KEY = os.environ.get("TIANAPI_KEY", "")
DASHSCOPE_API_KEY = os.environ.get("DASHSCOPE_API_KEY", "")
QWEN_MODEL = os.environ.get("QWEN_MODEL", "qwen-plus")
QWEN_API_URL = os.environ.get(
    "QWEN_API_URL",
    "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
)

# ========== 图片检测功能 ==========
def get_baidu_token():
    url = "https://aip.baidubce.com/oauth/2.0/token"
    params = {
        "grant_type": "client_credentials",
        "client_id": BAIDU_API_KEY,
        "client_secret": BAIDU_SECRET_KEY,
    }
    response = requests.post(url, params=params)
    result = response.json()
    return result.get("access_token")

def convert_to_jpg(image_path):
    try:
        img = Image.open(image_path)
        if img.mode in ("RGBA", "LA", "P"):
            rgb_img = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "RGBA":
                rgb_img.paste(img, mask=img.split()[3])
            else:
                rgb_img.paste(img)
            img = rgb_img
        elif img.mode != "RGB":
            img = img.convert("RGB")
        new_path = os.path.splitext(image_path)[0] + "_converted.jpg"
        img.save(new_path, "JPEG", quality=95)
        return new_path
    except Exception:
        return None

def recognize_with_baidu(image_path, token):
    with open(image_path, "rb") as f:
        base64_image = base64.b64encode(f.read()).decode("utf-8")
    url = f"https://aip.baidubce.com/rest/2.0/image-classify/v2/advanced_general?access_token={token}"
    data = {"image": base64_image, "top_num": 1}
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    response = requests.post(url, headers=headers, data=data)
    result = response.json()
    if "result" in result and len(result["result"]) > 0:
        return result["result"][0].get("keyword", "未知")
    return None

def search_nutrient_by_name(food_name):
    mapping = {"非菜": "马铃薯", "马铃薯": "土豆", "蕃茄": "西红柿"}
    search_name = mapping.get(food_name, food_name)
    url = "https://apis.tianapi.com/nutrient/index"
    params = {"key": TIANAPI_KEY, "mode": 0, "word": search_name, "num": 1}
    response = requests.get(url, params=params)
    result = response.json()
    if result.get("code") == 200:
        data_list = result.get("result", {}).get("list", [])
        if data_list:
            return data_list[0]
    return None

def detect_food_from_image(image_path):
    converted = convert_to_jpg(image_path)
    if not converted:
        return {"error": "图片转换失败"}
    token = get_baidu_token()
    if not token:
        return {"error": "百度token获取失败"}
    recognized = recognize_with_baidu(converted, token)
    if not recognized:
        return {"error": "图片识别失败"}
    nutrient = search_nutrient_by_name(recognized)
    try:
        os.remove(converted)
    except:
        pass
    if nutrient:
        return {
            "success": True,
            "recognized_as": recognized,
            "food": nutrient.get("name"),
            "calorie_per_100g": f"{nutrient.get('rl')} 千卡",
            "protein": f"{nutrient.get('dbz')} 克",
            "fat": f"{nutrient.get('zf')} 克",
            "carbohydrate": f"{nutrient.get('shhf')} 克",
        }
    else:
        return {
            "success": False,
            "recognized_as": recognized,
            "error": f"未找到 '{recognized}' 的热量数据",
        }

# ========== Flask 路由 ==========
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login')
def login_page():
    return render_template('login.html')

@app.route('/register')
def register_page():
    return render_template('login.html')

@app.route('/recipes')
def recipes_page():
    return render_template('recipes.html')

@app.route('/profile')
def profile_page():
    return render_template('profile.html')

@app.route('/analysis')
def analysis_page():
    return render_template('analysis.html')

@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return jsonify({"success": False, "message": "用户名和密码不能为空"})
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT COUNT(*) FROM users WHERE username = ?", (username,))
        count = cursor.fetchone()[0]
        if count > 0:
            return jsonify({"success": False, "message": "用户名已存在"})
        
        password_hash = generate_password_hash(password)
        cursor.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", 
                      (username, password_hash))
        conn.commit()
        return jsonify({"success": True, "message": "注册成功"})
    except Exception as e:
        return jsonify({"success": False, "message": f"注册失败: {str(e)}"})
    finally:
        conn.close()

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT id, username, password_hash FROM users WHERE username = ?", (username,))
        user = cursor.fetchone()
        
        if user and check_password_hash(user[2], password):
            cursor.execute("UPDATE users SET last_login = SYSDATETIME() WHERE id = ?", (user[0],))
            conn.commit()
            session['user_id'] = user[0]
            session['username'] = user[1]
            return jsonify({"success": True, "message": "登录成功", "username": user[1]})
        else:
            return jsonify({"success": False, "message": "用户名或密码错误"})
    except Exception as e:
        return jsonify({"success": False, "message": f"登录失败: {str(e)}"})
    finally:
        conn.close()

@app.route('/api/logout', methods=['POST'])
def logout():
    session.pop('user_id', None)
    session.pop('username', None)
    return jsonify({"success": True})

@app.route('/api/check_login', methods=['GET'])
def check_login():
    if 'username' in session and 'user_id' in session:
        return jsonify({
            "logged_in": True, 
            "username": session['username'],
            "user_id": session['user_id']
        })
    return jsonify({"logged_in": False})

@app.route('/detect', methods=['POST'])
def detect():
    if 'image' not in request.files:
        return jsonify({"error": "请上传图片"}), 400
    file = request.files['image']
    if file.filename == '':
        return jsonify({"error": "未选择文件"}), 400
    ext = file.filename.rsplit('.', 1)[-1].lower()
    filename = f"{uuid.uuid4().hex}.{ext}"
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    file.save(filepath)
    try:
        result = detect_food_from_image(filepath)
        return jsonify(result)
    finally:
        try:
            os.remove(filepath)
        except:
            pass

# ========== 每日热门食材接口 ==========
@app.route('/api/daily_ingredients')
def daily_ingredients():
    """返回每日热门食材（随机6种，同一天相同）"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT COUNT(*) FROM ingredients")
        total = cursor.fetchone()[0]
        
        if total == 0:
            return jsonify([])
        
        today = date.today().isoformat()
        seed = 0
        for ch in today:
            seed += ord(ch)
        random.seed(seed)
        
        ids = random.sample(range(1, total + 1), min(6, total))
        
        placeholders = ','.join(['?'] * len(ids))
        query = f"SELECT name, calories, emoji, protein, fat, carb FROM ingredients WHERE id IN ({placeholders})"
        cursor.execute(query, ids)
        results = cursor.fetchall()
        
        ingredients = []
        for row in results:
            ingredients.append({
                "name": row[0],
                "calories": row[1],
                "emoji": row[2] if row[2] else "🥔",
                "protein": float(row[3]) if row[3] else 0,
                "fat": float(row[4]) if row[4] else 0,
                "carb": float(row[5]) if row[5] else 0
            })
        
        random.shuffle(ingredients)
        return jsonify(ingredients)
        
    except Exception as e:
        print(f"获取每日食材失败: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

# ========== 菜谱查询接口 ==========
@app.route('/api/recipes')
def get_recipes():
    """获取菜谱推荐列表"""
    query = request.args.get('query', '')
    page = request.args.get('page', 1, type=int)
    per_page = 8
    
    url = "https://apis.tianapi.com/caipu/index"
    params = {
        "key": TIANAPI_KEY,
        "word": query if query else "家常菜",
        "page": page,
        "num": per_page
    }
    
    try:
        response = requests.get(url, params=params)
        result = response.json()
        
        if result.get('code') == 200:
            recipes = []
            for item in result.get('result', {}).get('list', []):
                recipes.append({
                    "id": item.get('id'),
                    "name": item.get('cp_name', ''),
                    "image": item.get('img', ''),
                    "ingredients": item.get('yuanliao', ''),
                    "type": item.get('type_name', ''),
                    "steps": item.get('zuofa', ''),
                    "feature": item.get('texing', ''),
                    "tips": item.get('tishi', '')
                })
            
            has_next = len(recipes) == per_page
            
            return jsonify({
                "success": True,
                "recipes": recipes,
                "page": page,
                "has_next": has_next
            })
        else:
            return jsonify({"success": False, "error": result.get('msg')})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

# ========== 减脂餐推荐接口 ==========
@app.route('/api/healthy_recipes')
def get_healthy_recipes():
    """获取减脂餐推荐（每日随机3道）"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT COUNT(*) FROM healthy_recipes")
        total = cursor.fetchone()[0]
        
        if total == 0:
            return jsonify([])
        
        today = date.today().isoformat()
        seed = 0
        for ch in today:
            seed += ord(ch)
        random.seed(seed)
        
        ids = random.sample(range(1, total + 1), min(3, total))
        
        placeholders = ','.join(['?'] * len(ids))
        query = f"SELECT id, name, calories, ingredients, steps, tips, cuisine, feature FROM healthy_recipes WHERE id IN ({placeholders})"
        cursor.execute(query, ids)
        results = cursor.fetchall()
        
        recipes = []
        for row in results:
            recipes.append({
                "id": row[0],
                "name": row[1],
                "calories": row[2],
                "ingredients": row[3],
                "steps": row[4],
                "tips": row[5] if row[5] else "",
                "cuisine": row[6] if row[6] else "减脂餐",
                "feature": row[7] if row[7] else "低卡健康",
                "matched": False
            })
        
        return jsonify(recipes)
        
    except Exception as e:
        print(f"获取减脂餐失败: {e}")
        return jsonify([])
    finally:
        conn.close()

# ========== 根据食材推荐减脂餐（匹配食材后随机推荐）==========
@app.route('/api/recommend_by_ingredient')
def recommend_by_ingredient():
    """根据食材推荐相关减脂餐（匹配后随机排序，每次最多6道）"""
    ingredient = request.args.get('ingredient', '')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        if not ingredient:
            return jsonify([])
        
        # 同时匹配菜名与食材，作为在线菜谱接口的本地兜底
        cursor.execute("""
            SELECT id, name, calories, ingredients, steps, tips, cuisine, feature 
            FROM healthy_recipes 
            WHERE name LIKE ? OR ingredients LIKE ?
        """, (f'%{ingredient}%', f'%{ingredient}%'))
        results = cursor.fetchall()
        
        if not results:
            return jsonify([])
        
        recipes = []
        for row in results:
            recipes.append({
                "id": row[0],
                "name": row[1],
                "calories": row[2],
                "ingredients": row[3],
                "steps": row[4],
                "tips": row[5] if row[5] else "",
                "cuisine": row[6] if row[6] else "减脂餐",
                "feature": row[7] if row[7] else "低卡健康",
                "matched": True
            })
        
        # 随机打乱顺序
        random.shuffle(recipes)
        
        if len(recipes) > 12:
            recipes = recipes[:12]
        
        return jsonify(recipes)
        
    except Exception as e:
        print(f"推荐减脂餐失败: {e}")
        return jsonify([])
    finally:
        conn.close()

# ========== 收藏功能接口 ==========
@app.route('/api/favorite/add', methods=['POST'])
def add_favorite():
    if 'user_id' not in session:
        return jsonify({"success": False, "message": "请先登录"}), 401
    
    data = request.json
    user_id = session['user_id']
    recipe_id = data.get('recipe_id')
    recipe_type = data.get('recipe_type', 'healthy')
    recipe_name = data.get('recipe_name', '')
    recipe_calories = data.get('recipe_calories', 0)
    recipe_ingredients = data.get('recipe_ingredients', '')
    recipe_steps = data.get('recipe_steps', '')
    recipe_tips = data.get('recipe_tips', '')
    recipe_cuisine = data.get('recipe_cuisine', '减脂餐')
    recipe_feature = data.get('recipe_feature', '低卡健康')
    
    if not recipe_id or not recipe_name:
        return jsonify({"success": False, "message": "参数不完整"})
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            INSERT INTO user_favorites 
            (user_id, recipe_id, recipe_type, recipe_name, recipe_calories, 
             recipe_ingredients, recipe_steps, recipe_tips, recipe_cuisine, recipe_feature)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (user_id, recipe_id, recipe_type, recipe_name, recipe_calories,
              recipe_ingredients, recipe_steps, recipe_tips, recipe_cuisine, recipe_feature))
        conn.commit()
        return jsonify({"success": True, "message": "收藏成功"})
    except pyodbc.IntegrityError:
        return jsonify({"success": False, "message": "已经收藏过了"})
    except Exception as e:
        return jsonify({"success": False, "message": f"收藏失败: {str(e)}"})
    finally:
        conn.close()

@app.route('/api/favorite/remove', methods=['POST'])
def remove_favorite():
    if 'user_id' not in session:
        return jsonify({"success": False, "message": "请先登录"}), 401
    
    data = request.json
    user_id = session['user_id']
    recipe_id = data.get('recipe_id')
    recipe_type = data.get('recipe_type', 'healthy')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            DELETE FROM user_favorites 
            WHERE user_id = ? AND recipe_id = ? AND recipe_type = ?
        """, (user_id, recipe_id, recipe_type))
        conn.commit()
        return jsonify({"success": True, "message": "已取消收藏"})
    except Exception as e:
        return jsonify({"success": False, "message": f"取消失败: {str(e)}"})
    finally:
        conn.close()

@app.route('/api/favorite/list')
def get_favorites():
    if 'user_id' not in session:
        return jsonify({"success": False, "message": "请先登录"}), 401
    
    user_id = session['user_id']
    page = request.args.get('page', 1, type=int)
    per_page = 8
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT COUNT(*) FROM user_favorites WHERE user_id = ?", (user_id,))
        total = cursor.fetchone()[0]
        
        offset = (page - 1) * per_page
        cursor.execute("""
            SELECT id, recipe_id, recipe_type, recipe_name, recipe_calories, 
                   recipe_ingredients, recipe_steps, recipe_tips, recipe_cuisine, recipe_feature
            FROM user_favorites 
            WHERE user_id = ? 
            ORDER BY created_at DESC
            OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
        """, (user_id, offset, per_page))
        results = cursor.fetchall()
        
        favorites = []
        for row in results:
            favorites.append({
                "favorite_id": row[0],
                "recipe_id": row[1],
                "recipe_type": row[2],
                "name": row[3],
                "calories": row[4],
                "ingredients": row[5],
                "steps": row[6],
                "tips": row[7] if row[7] else "",
                "cuisine": row[8] if row[8] else "减脂餐",
                "feature": row[9] if row[9] else "低卡健康"
            })
        
        return jsonify({
            "success": True,
            "favorites": favorites,
            "total": total,
            "page": page,
            "total_pages": (total + per_page - 1) // per_page
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})
    finally:
        conn.close()

@app.route('/api/favorite/check', methods=['POST'])
def check_favorite():
    if 'user_id' not in session:
        return jsonify({"is_favorited": False})
    
    data = request.json
    user_id = session['user_id']
    recipe_id = data.get('recipe_id')
    recipe_type = data.get('recipe_type', 'healthy')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT COUNT(*) FROM user_favorites 
            WHERE user_id = ? AND recipe_id = ? AND recipe_type = ?
        """, (user_id, recipe_id, recipe_type))
        count = cursor.fetchone()[0]
        return jsonify({"is_favorited": count > 0})
    except Exception as e:
        return jsonify({"is_favorited": False})
    finally:
        conn.close()

@app.route('/api/favorite/keys')
def favorite_keys():
    """批量返回收藏状态，避免食谱卡片逐个请求。"""
    if 'user_id' not in session:
        return jsonify({"success": True, "keys": []})
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT recipe_type, recipe_id FROM user_favorites WHERE user_id = ?",
            (session['user_id'],)
        )
        return jsonify({
            "success": True,
            "keys": [f"{row[0]}:{row[1]}" for row in cursor.fetchall()]
        })
    finally:
        conn.close()

# ========== 历史记录接口 ==========
@app.route('/api/history/add', methods=['POST'])
def add_history():
    """添加历史记录"""
    if 'user_id' not in session:
        return jsonify({"success": False, "message": "请先登录"}), 401
    
    data = request.json
    user_id = session['user_id']
    food_name = data.get('food_name', '')
    recognized_as = data.get('recognized_as', '')
    calorie_per_100g = data.get('calorie_per_100g', '')
    protein = data.get('protein', '')
    fat = data.get('fat', '')
    carbohydrate = data.get('carbohydrate', '')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            INSERT INTO history (user_id, food_name, recognized_as, calorie_per_100g, protein, fat, carbohydrate)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (user_id, food_name, recognized_as, calorie_per_100g, protein, fat, carbohydrate))
        conn.commit()
        return jsonify({"success": True, "message": "已保存到历史记录"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})
    finally:
        conn.close()

@app.route('/api/history/list')
def get_history():
    """获取历史记录列表"""
    if 'user_id' not in session:
        return jsonify({"success": False, "message": "请先登录"}), 401
    
    user_id = session['user_id']
    page = request.args.get('page', 1, type=int)
    per_page = 8
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT COUNT(*) FROM history WHERE user_id = ?", (user_id,))
        total = cursor.fetchone()[0]
        
        offset = (page - 1) * per_page
        cursor.execute("""
            SELECT id, food_name, recognized_as, calorie_per_100g, protein, fat, carbohydrate, created_at
            FROM history 
            WHERE user_id = ? 
            ORDER BY created_at DESC
            OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
        """, (user_id, offset, per_page))
        results = cursor.fetchall()
        
        history = []
        for row in results:
            history.append({
                "id": row[0],
                "food_name": row[1],
                "recognized_as": row[2],
                "calorie_per_100g": row[3],
                "protein": row[4],
                "fat": row[5],
                "carbohydrate": row[6],
                "created_at": row[7].strftime('%Y-%m-%d %H:%M') if row[7] else ''
            })
        
        return jsonify({
            "success": True,
            "history": history,
            "total": total,
            "page": page,
            "total_pages": (total + per_page - 1) // per_page
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})
    finally:
        conn.close()

@app.route('/api/history/clear', methods=['POST'])
def clear_history():
    """清空历史记录"""
    if 'user_id' not in session:
        return jsonify({"success": False, "message": "请先登录"}), 401
    
    user_id = session['user_id']
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("DELETE FROM history WHERE user_id = ?", (user_id,))
        conn.commit()
        return jsonify({"success": True, "message": "历史记录已清空"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})
    finally:
        conn.close()

@app.route('/api/history/delete/<int:history_id>', methods=['DELETE'])
def delete_history_item(history_id):
    """删除单条历史记录"""
    if 'user_id' not in session:
        return jsonify({"success": False, "message": "请先登录"}), 401
    
    user_id = session['user_id']
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("DELETE FROM history WHERE id = ? AND user_id = ?", (history_id, user_id))
        conn.commit()
        return jsonify({"success": True, "message": "已删除"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})
    finally:
        conn.close()

def _number(text):
    try:
        return float(str(text or "").split()[0])
    except (TypeError, ValueError):
        return 0.0

@app.route('/api/favorite/list_by_tag')
def favorites_by_tag():
    if 'user_id' not in session:
        return jsonify({"success": False, "message": "请先登录"}), 401
    tag = request.args.get('tag', '想吃')
    page = max(request.args.get('page', 1, type=int), 1)
    per_page = 8
    offset = (page - 1) * per_page
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT COUNT(*) FROM user_favorites WHERE user_id = ? AND tag = ?",
            (session['user_id'], tag)
        )
        total = cursor.fetchone()[0]
        cursor.execute("""
            SELECT id, recipe_id, recipe_type, recipe_name, recipe_calories,
                   recipe_ingredients, recipe_steps, recipe_tips, recipe_cuisine,
                   recipe_feature, tag
            FROM user_favorites
            WHERE user_id = ? AND tag = ?
            ORDER BY created_at DESC
            OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
        """, (session['user_id'], tag, offset, per_page))
        favorites = [{
            "favorite_id": row[0], "recipe_id": row[1], "recipe_type": row[2],
            "name": row[3], "calories": row[4], "ingredients": row[5],
            "steps": row[6], "tips": row[7] or "", "cuisine": row[8] or "减脂餐",
            "feature": row[9] or "低卡健康", "tag": row[10]
        } for row in cursor.fetchall()]
        return jsonify({
            "success": True, "favorites": favorites, "total": total, "page": page,
            "total_pages": (total + per_page - 1) // per_page
        })
    finally:
        conn.close()

@app.route('/api/favorite/update_tag', methods=['POST'])
def update_favorite_tag():
    if 'user_id' not in session:
        return jsonify({"success": False, "message": "请先登录"}), 401
    data = request.get_json(silent=True) or {}
    tag = data.get('tag')
    if tag not in ('想吃', '做过', '拿手'):
        return jsonify({"success": False, "message": "标签无效"}), 400
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE user_favorites SET tag = ? WHERE id = ? AND user_id = ?",
            (tag, data.get('favorite_id'), session['user_id'])
        )
        conn.commit()
        return jsonify({"success": True})
    finally:
        conn.close()

@app.route('/api/search/save', methods=['POST'])
def save_search():
    keyword = (request.get_json(silent=True) or {}).get('keyword', '').strip()[:100]
    if not keyword:
        return jsonify({"success": False}), 400
    conn = get_db_connection()
    try:
        conn.cursor().execute(
            "INSERT INTO search_history (user_id, keyword) VALUES (?, ?)",
            (session.get('user_id'), keyword)
        )
        conn.commit()
        return jsonify({"success": True})
    finally:
        conn.close()

@app.route('/api/search/history')
def search_history():
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        if session.get('user_id'):
            cursor.execute("""
                SELECT DISTINCT TOP 8 keyword FROM search_history
                WHERE user_id = ? ORDER BY keyword
            """, (session['user_id'],))
        else:
            return jsonify({"success": True, "history": []})
        return jsonify({"success": True, "history": [row[0] for row in cursor.fetchall()]})
    finally:
        conn.close()

@app.route('/api/search/clear_history', methods=['POST'])
def clear_search_history():
    if session.get('user_id'):
        conn = get_db_connection()
        try:
            conn.cursor().execute("DELETE FROM search_history WHERE user_id = ?", (session['user_id'],))
            conn.commit()
        finally:
            conn.close()
    return jsonify({"success": True})

@app.route('/api/search/hot')
def hot_searches():
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT TOP 8 keyword, COUNT(*) AS search_count
            FROM search_history GROUP BY keyword ORDER BY search_count DESC
        """)
        return jsonify({"success": True, "hot": [
            {"keyword": row[0], "count": row[1]} for row in cursor.fetchall()
        ]})
    finally:
        conn.close()

@app.route('/api/diet/overview')
def diet_overview():
    if 'user_id' not in session:
        return jsonify({"has_data": False, "message": "请先登录"})
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT food_name, calorie_per_100g, protein, fat, carbohydrate
            FROM history WHERE user_id = ?
        """, (session['user_id'],))
        rows = cursor.fetchall()
        if not rows:
            return jsonify({"has_data": False, "message": "暂无识别记录"})
        calories = sum(_number(row[1]) for row in rows)
        protein = sum(_number(row[2]) for row in rows)
        fat = sum(_number(row[3]) for row in rows)
        carb = sum(_number(row[4]) for row in rows)
        frequency = {}
        for row in rows:
            frequency[row[0]] = frequency.get(row[0], 0) + 1
        return jsonify({
            "has_data": True, "total_calories": round(calories, 1),
            "total_protein": round(protein, 1), "total_fat": round(fat, 1),
            "total_carb": round(carb, 1), "protein_ratio": round(protein, 1),
            "fat_ratio": round(fat, 1), "carb_ratio": round(carb, 1),
            "top_foods": [{"name": k, "count": v} for k, v in
                          sorted(frequency.items(), key=lambda item: item[1], reverse=True)[:5]],
            "suggestions": ["饮食尽量多样化", "注意控制总热量", "保持充足蛋白质摄入"]
        })
    finally:
        conn.close()

@app.route('/api/diet/trend')
def diet_trend():
    if 'user_id' not in session:
        return jsonify([])
    start = date.today() - timedelta(days=6)
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT CAST(created_at AS date), calorie_per_100g
            FROM history WHERE user_id = ? AND created_at >= ?
        """, (session['user_id'], start))
        totals = {}
        for day, value in cursor.fetchall():
            totals[day.isoformat()] = totals.get(day.isoformat(), 0) + _number(value)
        return jsonify([{
            "date": (start + timedelta(days=i)).strftime("%m-%d"),
            "calories": round(totals.get((start + timedelta(days=i)).isoformat(), 0), 1)
        } for i in range(7)])
    finally:
        conn.close()

def _assistant_context(user_id):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT food_name, recognized_as, calorie_per_100g,
                   protein, fat, carbohydrate, created_at
            FROM history
            WHERE user_id = ? AND CAST(created_at AS date) = CAST(GETDATE() AS date)
            ORDER BY created_at DESC
        """, (user_id,))
        detections = [{
            "food_name": row[0], "recognized_as": row[1],
            "calories": row[2], "protein": row[3], "fat": row[4],
            "carbohydrate": row[5],
            "time": row[6].strftime("%H:%M") if row[6] else ""
        } for row in cursor.fetchall()]

        cursor.execute("""
            SELECT TOP 8 recipe_name, recipe_calories, recipe_cuisine, tag
            FROM user_favorites WHERE user_id = ? ORDER BY created_at DESC
        """, (user_id,))
        favorites = [{
            "name": row[0], "calories": row[1], "cuisine": row[2], "tag": row[3]
        } for row in cursor.fetchall()]
        cursor.execute("SELECT COUNT(*) FROM user_favorites WHERE user_id = ?", (user_id,))
        favorite_count = cursor.fetchone()[0]

        cursor.execute("""
            SELECT gender, age, height_cm, weight_kg, activity_level, goal
            FROM health_profiles WHERE user_id = ?
        """, (user_id,))
        row = cursor.fetchone()
        profile = None
        if row:
            profile = {
                "gender": row[0], "age": row[1], "height_cm": float(row[2]),
                "weight_kg": float(row[3]), "activity_level": float(row[4]),
                "goal": row[5],
                "metrics": _health_metrics(
                    row[0], row[1], float(row[2]), float(row[3]), float(row[4]), row[5]
                )
            }

        cursor.execute("""
            SELECT TOP 10 role, content, created_at FROM assistant_messages
            WHERE user_id = ? ORDER BY created_at DESC
        """, (user_id,))
        recent = [{
            "role": row[0], "content": row[1],
            "time": row[2].strftime("%m-%d %H:%M") if row[2] else ""
        } for row in reversed(cursor.fetchall())]
        return {
            "username": session.get("username", "用户"),
            "detections": detections,
            "favorites": favorites,
            "favorite_count": favorite_count,
            "profile": profile,
            "recent_messages": recent,
            "today": {
                "count": len(detections),
                "calories": round(sum(_number(item["calories"]) for item in detections), 1),
                "protein": round(sum(_number(item["protein"]) for item in detections), 1)
            }
        }
    finally:
        conn.close()

def _assistant_reply(question, context):
    name = context["username"]
    foods = [item["food_name"] for item in context["detections"]]
    favorites = [item["name"] for item in context["favorites"]]
    profile = context["profile"]
    today = context["today"]
    q = question.lower()

    if any(word in q for word in ("我是谁", "名字", "叫什么")):
        return f"你是 {name}。我只会读取你当前登录账号下的健康档案、收藏和识别记录。"
    if any(word in q for word in ("今天", "检测", "识别", "吃了")):
        if not foods:
            return f"{name}，你今天还没有食材识别记录。可以先去识别中心上传一张食材图片。"
        return (f"{name}，你今天共识别了 {today['count']} 次：{'、'.join(foods)}。"
                f"按每条记录的 100 克参考值累计约 {today['calories']} 千卡、"
                f"蛋白质 {today['protein']} 克。")
    if any(word in q for word in ("收藏", "喜欢", "食谱")):
        if not favorites:
            return f"{name}，你还没有收藏食谱。去智能食谱页点击红心，我就能结合收藏偏好给你建议。"
        return f"{name}，你最近收藏了：{'、'.join(favorites[:6])}。你的收藏偏好会用于后续饮食建议。"
    if any(word in q for word in ("bmi", "目标", "体重", "代谢", "热量", "健康")):
        if not profile:
            return f"{name}，你还没有填写健康目标。请到个人中心 → 健康目标录入身高、体重和活动水平。"
        metrics = profile["metrics"]
        goals = {"lose": "减脂", "maintain": "保持体重", "gain": "增肌"}
        return (f"{name}，你当前目标是{goals.get(profile['goal'], '健康管理')}，"
                f"BMI 为 {metrics['bmi']}（{metrics['bmi_label']}），基础代谢约 "
                f"{metrics['bmr']} 千卡，每日目标热量约 {metrics['daily_target']} 千卡。")
    if any(word in q for word in ("推荐", "吃什么", "晚餐", "午餐", "早餐")):
        base = foods[0] if foods else "鸡胸肉"
        preference = favorites[0] if favorites else "高蛋白轻食"
        return (f"{name}，结合你今天的识别记录和收藏偏好，建议围绕“{base}”搭配一份"
                f"{preference}风格餐食，并补充深色蔬菜。你可以在食谱库搜索“{base}”。")
    return (f"{name}，我已经连接到你的个人营养档案。你可以问我："
            "“我今天识别了什么”“我的收藏有哪些”“我的目标热量是多少”或“今天吃什么”。")

def _qwen_reply(question, context):
    """将当前用户的最小必要上下文交给 Qwen，生成开放式个性化回答。"""
    if not DASHSCOPE_API_KEY:
        return None
    safe_context = {
        "username": context["username"],
        "today_detections": context["detections"],
        "favorite_recipes": context["favorites"],
        "favorite_count": context["favorite_count"],
        "health_profile": context["profile"],
        "today_summary": context["today"]
    }
    system_prompt = (
        "你是“智能食检”的个人营养AI助手，由通义千问提供通用知识能力。"
        "请结合给出的当前登录用户资料回答，同时也可以回答营养、食材、烹饪、生活常识"
        "及其他一般知识问题。不要声称看到了资料中没有的信息；不要诊断疾病；涉及医疗问题"
        "应提示咨询专业医生。回答使用简洁自然的中文。当前用户资料JSON："
        + json.dumps(safe_context, ensure_ascii=False, default=str)
    )
    history = [{
        "role": item["role"],
        "content": item["content"]
    } for item in context["recent_messages"][-8:]
      if item["role"] in ("user", "assistant")]
    payload = {
        "model": QWEN_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            *history,
            {"role": "user", "content": question}
        ],
        "temperature": 0.7,
        "max_tokens": 900
    }
    response = requests.post(
        QWEN_API_URL,
        headers={
            "Authorization": f"Bearer {DASHSCOPE_API_KEY}",
            "Content-Type": "application/json"
        },
        json=payload,
        timeout=45
    )
    response.raise_for_status()
    data = response.json()
    return data["choices"][0]["message"]["content"].strip()

@app.route('/api/assistant/context')
def assistant_context():
    if 'user_id' not in session:
        return jsonify({"success": False, "logged_in": False, "message": "登录后连接个人营养档案"})
    context = _assistant_context(session['user_id'])
    return jsonify({
        "success": True, "logged_in": True,
        "model_enabled": bool(DASHSCOPE_API_KEY),
        "model": QWEN_MODEL if DASHSCOPE_API_KEY else "local-context",
        **context
    })

@app.route('/api/chat', methods=['POST'])
def local_chat():
    if 'user_id' not in session:
        return jsonify({"success": False, "error": "请先登录，我才能读取你的个人营养档案。"}), 401
    question = (request.get_json(silent=True) or {}).get('question', '').strip()
    if not question:
        return jsonify({"success": False, "error": "请输入问题"})
    question = question[:500]
    context = _assistant_context(session['user_id'])
    mode = "local-context"
    try:
        reply = _qwen_reply(question, context)
        if reply:
            mode = QWEN_MODEL
        else:
            reply = _assistant_reply(question, context)
    except Exception as e:
        print(f"Qwen 调用失败，已切换本地助手: {e}")
        reply = _assistant_reply(question, context)
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO assistant_messages (user_id, role, content) VALUES (?, N'user', ?)",
            (session['user_id'], question)
        )
        cursor.execute(
            "INSERT INTO assistant_messages (user_id, role, content) VALUES (?, N'assistant', ?)",
            (session['user_id'], reply[:1000])
        )
        conn.commit()
    finally:
        conn.close()
    return jsonify({
        "success": True, "reply": reply,
        "context_updated": True, "mode": mode
    })

def _health_metrics(gender, age, height, weight, activity, goal):
    bmi = weight / ((height / 100) ** 2)
    bmr = 10 * weight + 6.25 * height - 5 * age + (5 if gender == "male" else -161)
    target = bmr * activity + {"lose": -400, "gain": 300}.get(goal, 0)
    bmi_label = "偏瘦" if bmi < 18.5 else "正常" if bmi < 24 else "偏高" if bmi < 28 else "肥胖"
    return {
        "bmi": round(bmi, 1),
        "bmi_label": bmi_label,
        "bmr": round(bmr),
        "daily_target": max(round(target), 1000)
    }

@app.route('/api/profile/health', methods=['GET', 'POST'])
def health_profile():
    if 'user_id' not in session:
        return jsonify({"success": False, "message": "请先登录"}), 401
    user_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        if request.method == 'POST':
            data = request.get_json(silent=True) or {}
            gender = data.get('gender', 'male')
            age = int(data.get('age', 25))
            height = float(data.get('height_cm', 170))
            weight = float(data.get('weight_kg', 65))
            activity = float(data.get('activity_level', 1.375))
            goal = data.get('goal', 'maintain')
            if gender not in ('male', 'female') or goal not in ('lose', 'maintain', 'gain'):
                return jsonify({"success": False, "message": "健康档案参数无效"}), 400
            if not (12 <= age <= 100 and 100 <= height <= 230 and 30 <= weight <= 300):
                return jsonify({"success": False, "message": "请检查年龄、身高和体重"}), 400
            cursor.execute("""
                MERGE dbo.health_profiles AS target
                USING (SELECT ? AS user_id) AS source
                ON target.user_id = source.user_id
                WHEN MATCHED THEN UPDATE SET gender=?, age=?, height_cm=?, weight_kg=?,
                    activity_level=?, goal=?, updated_at=SYSDATETIME()
                WHEN NOT MATCHED THEN INSERT
                    (user_id, gender, age, height_cm, weight_kg, activity_level, goal)
                    VALUES (?, ?, ?, ?, ?, ?, ?);
            """, (user_id, gender, age, height, weight, activity, goal,
                  user_id, gender, age, height, weight, activity, goal))
            conn.commit()
        cursor.execute("""
            SELECT gender, age, height_cm, weight_kg, activity_level, goal
            FROM dbo.health_profiles WHERE user_id = ?
        """, (user_id,))
        row = cursor.fetchone()
        if not row:
            return jsonify({"success": True, "has_profile": False})
        profile = {
            "gender": row[0], "age": row[1], "height_cm": float(row[2]),
            "weight_kg": float(row[3]), "activity_level": float(row[4]), "goal": row[5]
        }
        return jsonify({
            "success": True, "has_profile": True, "profile": profile,
            "metrics": _health_metrics(row[0], row[1], float(row[2]), float(row[3]),
                                       float(row[4]), row[5])
        })
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "请输入有效的数字"}), 400
    finally:
        conn.close()

# 初始化数据库
with app.app_context():
    init_database()

if __name__ == '__main__':
    print(f"当前环境: {ENV}")
    print(f"使用本地 SQL Server: {DB_SERVER} / {DB_NAME}")
    app.run(host='127.0.0.1', port=int(os.environ.get("PORT", "5000")), debug=ENV == "development")
