from flask import Flask, render_template
import requests
from models import db, NewsItem
from moonshot import MoonshotTranslator
from dotenv import load_dotenv
import os
import threading

load_dotenv()

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///news.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

# 创建数据库表
with app.app_context():
    db.create_all()

# Hacker News API配置
HN_API = "https://hacker-news.firebaseio.com/v0"
TOP_STORIES_URL = f"{HN_API}/topstories.json"
ITEM_URL = f"{HN_API}/item/"

# 初始化翻译器
translator = MoonshotTranslator()

def fetch_and_translate_news():
    """获取并翻译新闻的后台任务"""
    with app.app_context():
        # 获取热门故事ID
        story_ids = requests.get(TOP_STORIES_URL).json()[:30]
        
        for story_id in story_ids:
            # 检查是否已在数据库中
            item = NewsItem.query.get(story_id)
            
            if not item:
                # 从HN API获取详情
                story_data = requests.get(f"{ITEM_URL}{story_id}.json").json()
                
                # 创建新记录
                item = NewsItem(
                    id=story_id,
                    original_title=story_data.get('title', ''),
                    original_url=story_data.get('url', ''),
                    score=story_data.get('score', 0),
                    time=story_data.get('time', 0)
                )
                db.session.add(item)
                db.session.commit()
            
            # 如果未翻译或翻译失败，尝试翻译
            if item.translation_status in [0, 3]:
                try:
                    # 更新状态为翻译中
                    item.translation_status = 1
                    db.session.commit()
                    
                    # 调用翻译API
                    translated = translator.translate_title(item.original_title)
                    
                    if translated:
                        item.translated_title = translated
                        item.translation_status = 2  # 标记为已翻译
                    else:
                        item.translation_status = 3  # 标记为翻译失败
                    
                    db.session.commit()
                except Exception as e:
                    print(f"翻译新闻 {item.id} 失败: {e}")
                    item.translation_status = 3
                    db.session.commit()

@app.route('/')
def index():
    """首页显示新闻列表"""
    # 获取所有已翻译的新闻（按评分排序）
    news_items = NewsItem.query.filter(
        NewsItem.translation_status == 2
    ).order_by(NewsItem.score.desc()).limit(30).all()
    
    return render_template('index.html', news_items=news_items)

def run_background_task():
    """启动后台任务定时获取并翻译新闻"""
    import time
    while True:
        print("开始获取并翻译新闻...")
        fetch_and_translate_news()
        # 每5分钟更新一次
        time.sleep(300)

if __name__ == '__main__':
    # 启动后台任务线程
    bg_thread = threading.Thread(target=run_background_task, daemon=True)
    bg_thread.start()
    
    # 启动Flask应用
    app.run(port=5000, debug=True)