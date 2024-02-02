from flask import Flask, request, jsonify, g
from googleapiclient.discovery import build
from apscheduler.schedulers.background import BackgroundScheduler
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import requests

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///videos.db'  # Change this for other databases
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Replace 'YOUR_API_KEY' with your actual YouTube API key
API_KEY = 'YOUR API KEY'
youtube = build('youtube', 'v3', developerKey=API_KEY)

scheduler = BackgroundScheduler()
scheduler.start()

class Video(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    published_at = db.Column(db.DateTime, nullable=False)
    thumbnails = db.Column(db.String(255), nullable=True)

@app.route('/videos', methods=['GET'])
def get_latest_videos():
    tag = request.args.get('tag', default='', type=str)
    page_token = request.args.get('pageToken', default=None, type=str)

    results = fetch_videos(tag, page_token)
    return jsonify(results)

def fetch_videos(tag, page_token=None):
    request = youtube.search().list(
        q=tag,
        type='video',
        part='snippet',
        order='date',
        maxResults=10,
        pageToken=page_token
    )

    response = request.execute()

    videos = []
    for item in response.get('items', []):
        video_data = {
            'title': item['snippet']['title'],
            'description': item['snippet']['description'],
            'published_at': datetime.strptime(item['snippet']['publishedAt'], '%Y-%m-%dT%H:%M:%SZ'),
            'thumbnails': item['snippet']['thumbnails']['default']['url']
        }

        # Save the video data to the database
        save_video_to_database(video_data)

        videos.append(video_data)

    next_page_token = response.get('nextPageToken')
    return {'videos': videos, 'nextPageToken': next_page_token}

def save_video_to_database(video_data):
    video = Video(
        title=video_data['title'],
        description=video_data['description'],
        published_at=video_data['published_at'],
        thumbnails=video_data['thumbnails']
    )
    db.session.add(video)
    db.session.commit()

def get_db():
     with app.app_context():
        if not hasattr(g, 'db'):
            g.db = db.session

        return g.db

@app.teardown_appcontext
def teardown_db(exception):
    db = getattr(g, 'db', None)

    if db is not None:
        db.close()

@app.route('/stored_videos', methods=['GET'])
def get_stored_videos():
    page = request.args.get('page', default=1, type=int)
    per_page = request.args.get('per_page', default=10, type=int)

    stored_videos = Video.query.order_by(Video.published_at.desc()).paginate(page=page, per_page=per_page)
    
    videos = []
    for stored_video in stored_videos.items:
        video_data = {
            'title': stored_video.title,
            'description': stored_video.description,
            'published_at': stored_video.published_at.strftime('%Y-%m-%dT%H:%M:%SZ'),
            'thumbnails': stored_video.thumbnails
        }
        videos.append(video_data)

    return jsonify({'videos': videos, 'total_pages': stored_videos.pages, 'current_page': page})

# Separate function to fetch videos within the application context
def fetch_videos_within_context(app, tag):
    with app.app_context():
        fetch_videos(tag)

    
# Scheduler to fetch videos every 10 seconds
@scheduler.scheduled_job('interval', seconds=10)
def fetch_videos_periodically():
    tag = 'http://127.0.0.1:7070/videos'
    print("Fetching videos...")
    
    with app.app_context():
        fetch_videos(tag)

    # Call the route to retrieve stored videos
    stored_videos_response = requests.get('http://127.0.0.1:7070/stored_videos')
    stored_videos_data = stored_videos_response.json()
    print("Stored Videos:", stored_videos_data)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        app.run(debug=True, port=7070)
