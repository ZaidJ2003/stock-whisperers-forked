from flask import Flask, abort, redirect, render_template, request, url_for, flash, jsonify
# from flask_wtf import FileField
#Market Data
import yfinance as yf
import plotly.graph_objs as go 
import json
import plotly
import plotly.express as px
import pandas as pd

#Server Setup
from flask_socketio import SocketIO, emit
from threading import Lock
from flask_bcrypt import Bcrypt 
import os
from dotenv import load_dotenv
from flask_login import login_user, login_required, logout_user, current_user, LoginManager
from src.repositories.post_repository import post_repository_singleton
from src.models import db, users, live_posts, Post
from datetime import datetime, timedelta

thread = None
thread_lock = Lock()
load_dotenv()

#Flask Initialization 
app = Flask(__name__)

#Bcrypt Initialization
bcrypt = Bcrypt(app) 
app.secret_key = 'try'

# If bugs occur with sockets then try: 
# app.config['SECRET_KEY'] = 'ABC'

#Sockets Initialization
socketio = SocketIO(app, cors_allowed_origins='*')

app.debug = True

app.config['SQLALCHEMY_DATABASE_URI'] = f'postgresql://{os.getenv("DB_USER")}:{os.getenv("DB_PASS")}@{os.getenv("DB_HOST")}:{os.getenv("DB_PORT")}/{os.getenv("DB_NAME")}'

db.init_app(app)

login_manager = LoginManager(app)
login_manager.login_view = '/login'

@login_manager.user_loader
def load_user(user_id):
    return users.query.get(int(user_id))

#Override Yahoo Finance
yf.pdr_override()

#Create input field for our desired stock
def get_plotly_json(stock):
    #Retrieve stock data frame (df) from yfinance API at an interval of 1m
    df = yf.download(tickers=stock,period='1d',interval='1m', threads = True)
    df['Datetime'] = df.index.strftime('%I:%M %p')

    print(df)
    #Declare plotly figure (go)
    fig=go.Figure()

    fig.add_trace(go.Candlestick(x=df.index,
                    open=df['Open'],
                    high=df['High'],
                    low=df['Low'],
                    close=df['Close'], name = 'market data'))

    fig.update_layout(
        title= str(stock)+' Live Share Price:',
        yaxis_title='Stock Price (USD per Shares)')

    fig.update_xaxes(
        rangeslider_visible=True,
        rangeselector=dict(
            buttons=list([
                dict(count=15, label="15m", step="minute", stepmode="backward"),
                dict(count=45, label="45m", step="minute", stepmode="backward"),
                dict(count=1, label="HTD", step="hour", stepmode="todate"),
                dict(count=3, label="3h", step="hour", stepmode="backward"),
                dict(step="all")
            ])
        )
    )
    graph_json = json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)
    return graph_json

def background_thread():
    print("Generating graph sensor values")
    while True:
        value = get_plotly_json('AAPL')  # Corrected stock symbol
        socketio.emit('updateGraph', {'value': value})  # Corrected event name
        socketio.sleep(10)


@app.get('/')
def index():
    graph = get_plotly_json('AAPL')
    return render_template('index.html', user=current_user, plot=graph)

#Create Comments or add a temporary get/post request. That has a pass statement.
#Example:
#@app.get('/test')
#def testing():
#    pass


#TODO: Create a get request for the upload page.
@app.get('/upload')
def upload():
    return render_template('upload.html', user=current_user)

#TODO: Create a post request for the upload page.
@app.post('/upload')
def upload_post():
    title = request.form.get('title')
    description = request.form.get('text')
    if title == '' or title is None:
        abort(400)
    created_post = post_repository_singleton.create_post(title, description, current_user.user_id)
    return redirect('/posts')

# when a user likes a post
@app.post('/posts/like')
def like_post():
    post_id = request.form.get('post_id')
    user_id = request.form.get('user_id')
    if post_id == '' or post_id is None or user_id == '' or user_id is None:
        abort(400)
    post_repository_singleton.add_like(post_id, user_id)

    return jsonify({'status': 'success'})

# when a user comments on a post
@app.post('/posts/<int:post_id>/comment')
def comment_post(post_id):
    print('commenting on post')
    user_id = request.form.get('user_id')
    print(user_id)
    content = request.form.get('content')
    print(content)
    if post_id == '' or post_id is None or user_id == '' or user_id is None or content == '' or content is None:
        abort(400)
    post_repository_singleton.add_comment(user_id, post_id, content)

    return redirect(f'/posts/{post_id}')

# format timestamp to display how long ago a post was made
@app.template_filter('time_ago')
def time_ago_filter(timestamp):
    now = datetime.now()
    time_difference = now - timestamp

    if time_difference < timedelta(minutes=1):
        return 'just now'
    elif time_difference < timedelta(hours=1):
        minutes = int(time_difference.total_seconds() / 60)
        return f'{minutes} minute{"s" if minutes != 1 else ""} ago'
    elif time_difference < timedelta(days=1):
        hours = int(time_difference.total_seconds() / 3600)
        return f'{hours} hour{"s" if hours != 1 else ""} ago'
    else:
        days = int(time_difference.total_seconds() / (3600 * 24))
        return f'{days} day{"s" if days != 1 else ""} ago'

#TODO: Create a get request for the posts page.
@app.get('/posts')
def posts():
    all_posts = post_repository_singleton.get_all_posts_with_users()
    return render_template('posts.html', list_posts_active=True, posts=all_posts, user=current_user)

@app.get('/posts/<int:post_id>')
def post(post_id):
    post = post_repository_singleton.get_post_by_id(post_id)
    return render_template('single_post.html', post=post, user=current_user)

#TODO: Create a get request for the user login page.
@app.get('/login')
def login():
    return render_template('login.html', user=current_user)

@app.post('/login')
def verify_login():
    username = request.form.get('username')
    password = request.form.get('password')

    if username == '' or password == '':
        abort(400) 

    temp_username = users.query.filter_by(username = username).first()

    if temp_username is not None:
        if bcrypt.check_password_hash(temp_username.password, password):
            flash('Successfully logged in, ' + temp_username.first_name + '!', category= 'success') 
            login_user(temp_username, remember=True)
            # figure out how to send this msg to home page
            return redirect('/')
        else:
            flash('Incorrect username or password', category='error')
    else:
        flash('Username does not exist', category='error')

    return redirect('/login')

@app.get('/logout')
@login_required
def logout():
    logout_user()
    return redirect('/login')


@app.get('/register')
def register():
    return render_template('register.html', user=current_user)

@app.post('/register')
def create_user():
    first_name = request.form.get('first-name')
    last_name = request.form.get('last-name')
    username = request.form.get('username')
    # email = request.form.get('email')
    password = request.form.get('password')

    if username == '' or password == '' or first_name == '' or last_name == '':
        abort(400)

    temp_user = users.query.filter_by(username = username).first()
    if temp_user is not None:
        flash('Username already exists', category= 'error')

    if len(first_name) <= 1:
        flash('First name must be greater than 1 character', category='error')
    elif len(last_name) <= 1:
        flash('Last name must be greater than 1 character', category='error')
    elif len(username) < 4:
        flash('Username name must be at least 4 characters', category='error')
    elif len(password) < 8:
        flash('Password must be contain at least 8 characters, a number, and a special character', category='error')
    else:
        temp_user = users(first_name, last_name, username, bcrypt.generate_password_hash(password).decode('utf-8'))
        db.session.add(temp_user)
        db.session.commit()
        login_user(temp_user, remember= True)
        flash('account successfully created!', category= 'success')
        return redirect('/')

    return redirect('/register')

#TODO: Create a get request for the profile page.
@app.get('/profile/<int:user_id>')
@login_required
def profile(user_id):
    user = current_user
    profile_picture = url_for('static', filename = 'profile_pics/' + user.profile_picture)

    return render_template('profile.html', user=user, profile_picture=profile_picture)

#TODO: Create a get request for live comments.
@app.get('/comment')
def live_comment():
    pass

# TODO: Implement the 'Post Discussions' feature
@app.get('/post discussions')
def Post_discussions():
    pass

@app.post('/users/<int:user_id>')
def edit_profile(user_id: int):
    user = current_user

    user.email = request.form.get('email')
    user.username = request.form.get('username')

    profile_pic = request.files['profile_picture']
    db.session.add(user)
    db.session.commit()

    return redirect(f'/profile/{user_id}', user_id=user_id)

# # TODO: Implement the 'Post Discussions' feature
# @app.get('post discussions')
# def Post_discussions():
#     pass

@socketio.on('connect')
def connect():
    global thread
    print('Client connected')

    global thread
    with thread_lock:
        if thread is None:
            thread = socketio.start_background_task(background_thread)

"""
Decorator for disconnect
"""

@socketio.on('disconnect')
def disconnect():
    print('Client disconnected',  request.sid)

if __name__ == '__main__':
    socketio.run(app)
