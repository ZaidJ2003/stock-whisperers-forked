from flask import Flask, abort, redirect, render_template, request, url_for, flash, jsonify, session

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
from src.repositories.user_repository import user_repository_singleton
from sqlalchemy import or_, func
from flask_mail import Mail, Message
from src.models import db, users, live_posts, Post
from datetime import datetime, timedelta
from itsdangerous.url_safe import URLSafeTimedSerializer as Serializer
import random

thread = None
thread_lock = Lock()
load_dotenv()

#Flask Initialization 
app = Flask(__name__)

#Bcrypt Initialization
bcrypt = Bcrypt(app) 
app.secret_key = os.getenv('APP_SECRET_KEY', 'default')

# If bugs occur with sockets then try: 
# app.config['SECRET_KEY'] = 'ABC'

#Sockets Initialization
socketio = SocketIO(app, cors_allowed_origins='*')

app.debug = True

# DB connection
app.config['SQLALCHEMY_DATABASE_URI'] = f'postgresql://{os.getenv("DB_USER")}:{os.getenv("DB_PASS")}@{os.getenv("DB_HOST")}:{os.getenv("DB_PORT")}/{os.getenv("DB_NAME")}'

db.init_app(app)

# Login Initialization
login_manager = LoginManager(app)

# Make sure you are not on school wifi when trying to send emails, it will not work.
# Mail Initialization
app.config['MAIL_SERVER'] = 'smtp.googlemail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True

# app.config['MAIL_USERNAME'] = os.getenv('EMAIL_USER')
# app.config['MAIL_PASSWORD'] = os.getenv('EMAIL_PASS')
app.config['MAIL_USERNAME'] = 'the.stock.whisperers@gmail.com'
app.config['MAIL_PASSWORD'] = 'spwlegjkdfjabdhx'
mail = Mail(app)

# Variables to use for email verification
code = 0
temp_user_info = []

@login_manager.user_loader
def load_user(user_id):
    return users.query.get(int(user_id))

#Override Yahoo Finance
yf.pdr_override()

#Create input field for our desired stock
def get_plotly_json(stock):
    #Retrieve stock data frame (df) from yfinance API at an interval of 1m
    df = yf.download(tickers=stock,period='1d',interval='1m', threads = True)
    #df['Regular time'] = df.index.strftime('%I:%M %p')

    print(df)
    #Declare plotly figure (go)
    fig=go.Figure()

    fig.add_trace(go.Candlestick(x=df.index,
                    open=df['Open'],
                    high=df['High'],
                    low=df['Low'],
                    close=df['Close'], name = 'market data'))

    fig.update_layout(
        #title= str(stock)+' Live Share Price:',
        #template='plotly_dark',
        autosize=True,
        uirevision=True,
        #yaxis_title='Stock Price (USD per Shares)'
        )

    fig.update_xaxes(
        rangeslider_visible=True,
        tickformat="%I:%M %p",
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
    return render_template('index.html', user = session.get('username'), plot=graph)

#Create Comments or add a temporary get/post request. That has a pass statement.
#Example:
#@app.get('/test')
#def testing():
#    pass


#TODO: Create a get request for the upload page.
@app.get('/upload')
def upload():
    if 'username' not in session:
        abort(401)
    return render_template('upload.html', user=session.get('username'))

#TODO: Create a post request for the upload page.
@app.post('/upload')
def upload_post():
    title = request.form.get('title')
    description = request.form.get('text')
    if title == '' or title is None:
        abort(400)
    user = user_repository_singleton.get_user_by_username(session.get('username'))
    created_post = post_repository_singleton.create_post(title, description, user.user_id)
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
    user_id = user_repository_singleton.get_user_by_username(session.get('username')).user_id
    content = request.form.get('content')
    if post_id == '' or post_id is None or content == '' or content is None:
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
    if 'username' not in session:
        user = None
    else:
        user = user_repository_singleton.get_user_by_username(session.get('username'))
    return render_template('posts.html', list_posts_active=True, posts=all_posts, user=user)

@app.get('/posts/<int:post_id>')
def post(post_id):
    if 'username' not in session:
        abort(401)
    post = post_repository_singleton.get_post_by_id(post_id)
    user = user_repository_singleton.get_user_by_username(session.get('username'))
    return render_template('single_post.html', post=post, user=user)

#TODO: Create a get request for the user login page.
@app.get('/login')
def login():
    if user_repository_singleton.is_logged_in():
        return redirect('/')
    return render_template('login.html', user = session.get('username'))

def send_verification_email(email):
    if not email:
        abort(400)
    global code   
    code = random.randint(100000, 999999)
    msg = Message('Verification code', sender='noreply@stock-whisperers.com', recipients=[email])
    msg.body = f'''Enter the 6-digit code below to verify your identity.

{code}

If you did not make this request, please ignore this email
'''
    mail.send(msg)

# to-do: when user inputs invalid code email resends, move to post route. fix invalid code error
@app.get('/verify_user/<username>/<method>')
def verify_user(username, method):
    return render_template('verify_user.html', username = username, method = method)

@app.post('/verify_user/<username>/<method>')
def verify_code(username, method):
    global code
    user_code = request.form.get('user-code')
    if not user_code:
        abort(400)
    if str(code) != str(user_code):
        flash('Incorrect code. Try Again', category='error')
        return redirect(f'/verify_user/{username}/{method}')

    if method == "signup":
        user_repository_singleton.add_user(temp_user_info[0], temp_user_info[1], temp_user_info[2], temp_user_info[3], temp_user_info[4], temp_user_info[5])
        user = user_repository_singleton.get_user_by_username(temp_user_info[2])
        if not user:
            abort(401)
        user_repository_singleton.login_user(user.username)
        flash('Successfully created an account. Welcome, ' + user.first_name + '!', category= 'success') 
        return redirect('/')

    user = user_repository_singleton.get_user_by_username(username)
    if not user:
        abort(401)
    flash('Successfully logged in, ' + user.first_name + '!', category= 'success') 
    user_repository_singleton.login_user(user.username)
    return redirect('/')
    
@app.post('/login')
def verify_login():
    if user_repository_singleton.is_logged_in():
        return abort(400)
    username = request.form.get('username')
    password = request.form.get('password')

    if not username or not password:
        flash('Please enter a username and a password', category= 'error') 
        return redirect('/login')

    temp_username = users.query.filter((func.lower(users.username) == username.lower()) | (func.lower(users.email) == username.lower())).first()

    if temp_username is not None:
        if bcrypt.check_password_hash(temp_username.password, password):
            time_difference = datetime.utcnow() - temp_username.last_login

            if time_difference > timedelta(days=14):
                send_verification_email(temp_username.email)
                return redirect(f'/verify_user/{temp_username.username}/login')
            else:
                flash('Successfully logged in, ' + temp_username.first_name + '!', category= 'success') 
                user_repository_singleton.login_user(username)
                return redirect('/')
        else:
            flash('Incorrect username or password', category='error')
    else:
        flash('Username does not exist', category='error')

    return redirect('/login')

@app.get('/logout')
def logout():
    if not user_repository_singleton.is_logged_in():
        abort(401)
    user_repository_singleton.logout_user()
    return redirect('/login')

@app.get('/register')
def register():
    if user_repository_singleton.is_logged_in():
        return redirect('/')
    return render_template('register.html', user = session.get('username'))

@app.post('/register')
def create_user():
    if user_repository_singleton.is_logged_in():
        return abort(400)
    first_name = request.form.get('first-name')
    last_name = request.form.get('last-name')
    username = request.form.get('username')
    email = request.form.get('email')
    password = request.form.get('password')
    
    # temp path until we switch to storing pp as a blob
    profile_picture = 'static/profile_pics/default-profile-pic.jpg'

    if not username or not password or not first_name or not last_name or not email:
        flash('Please fill out all of the fields') 
        return redirect('/register')

    temp_user = users.query.filter((func.lower(users.username) == username.lower()) | (func.lower(users.email) == email.lower())).first()
    if temp_user is not None:
        if temp_user.email.lower() == email.lower():
            flash('email already exists', category= 'error')
        elif temp_user.username.lower() == username.lower():
            flash('username already exists', category= 'error')
            
        return redirect('/register')
    
    if user_repository_singleton.validate_input(first_name, last_name, username, password):
        global temp_user_info
        temp_user_info = [first_name, last_name, username, email, bcrypt.generate_password_hash(password).decode(), profile_picture]
        send_verification_email(email)
        return redirect(f'/verify_user/{username}/signup')

    return redirect('/register')

# Route for requesting password reset
@app.get('/request_password_reset')
def request_password_form():
    return render_template('request_password_reset.html')

@app.post('/request_password_reset')
def request_password_reset():
    if user_repository_singleton.is_logged_in():
        return redirect(url_for('index.html'))
    email = request.form.get('email')
    if not email:
        flash('please enter an email address.', category = 'error')
        return redirect('/request_password_reset')
    temp_user = users.query.filter_by(email = email).first()
    if not temp_user:
        flash('User with associated email address does not exist. Please register first.' , category='error')
        return redirect('/request_password_reset')
    token = temp_user.get_reset_token()
    msg = Message('Password Reset Request', sender='noreply@stock-whisperers.com', recipients=[temp_user.email])
    msg.body = f'''To reset your password, click the following link:
{url_for('password_reset', token = token, _external = True)}

If you did not make this request, please ignore this email
'''
    mail.send(msg)
    flash('An email has been sent with instructions to reset your password',  category='success')
    return redirect(url_for('verify_login'))
    
@app.get('/password_reset/<token>')
def password_reset_form(token):
    if user_repository_singleton.is_logged_in():
        return redirect('/')
    user = users.verify_reset_token(token)
    if user is None:
        flash('Invalid or expired token', category = 'error')
        return redirect('/login')
    return render_template('reset_password.html', token = token)

# Route for resetting a password
@app.post('/password_reset/<token>')
def password_reset(token):
    if user_repository_singleton.is_logged_in():
        return redirect('/')
    user = users.verify_reset_token(token)
    if user is None:
        flash('Invalid or expired token', category = 'error')
        return redirect('/request_password_reset')
    
    password = request.form.get('password')
    confirm_password = request.form.get('confirm-password')
    if not password or not confirm_password:
        flash('Please fill out all of the fileds',  category='error')
    elif password != confirm_password:
        flash('Passwords do not match',  category='error')
    elif (len(password) < 6) or not any(char.isdigit() for char in password) or not any(char.isalpha() for char in password) or any(char.isspace() for char in password):
        flash('Password must contain at least 6 characters, a letter, a number, and no spaces', category='error')
    else:
        user.password = bcrypt.generate_password_hash(password).decode()
        db.session.commit()
        flash('your password has been updated!', category = 'success')
        return redirect('/login')
    
    return redirect(f'/password_reset/{token}')

#TODO: Create a get request for the profile page.
@app.get('/profile/<int:user_id>')
@login_required
def profile(user_id):
    if 'username' not in session:
        abort(401)
    
    user = users.query.get(user_id)

    if user.profile_picture:
        profile_picture = url_for('static', filename = 'profile_pics/' + user.profile_picture)
    else:
        profile_picture = url_for('static', filename = 'profile_pics/default-profile-pic.jpg')
    return render_template('profile.html', user=user, profile_picture=profile_picture)

#TODO: Create a get request for live comments.
@app.get('/comment')
def live_comment():
    comments = live_posts.query.order_by(live_posts.date.desc()).all()
    comments_data = [ 
        {'post_id': comment.post_id, 
         'content': comment.content, 
         'user_id': comment.user_id, 
         'date': comment.date.strftime("%Y/%m/%d %H:%M:%S")}
        for comment in comments
    ] 
    return jsonify(comments_data)  

# sokcetIO to handle comments: 
@socketio.on('send_comment') 
def handle_send_comment (data): 
    if user_repository_singleton.is_logged_in():
        emit('error', {'message': 'Not logged in, please log in to comment :)'})
        return 
    user_id = session['user_id']
    content = data['comment']  

    # store comments
    new_comment = live_posts(content=content, user_id=user_id) 
    db.session.add(new_comment)
    db.session.commit()

    # emitting  new comments: 
    emit('new_comment', {'user_id': user_id, 'content': content, 'post_id': new_comment.post_id}, broadcast=True)  

# TODO: Implement the 'Post Discussions' feature
@app.get('/post discussions')
def Post_discussions():
    pass

@app.post('/users/<int:user_id>')
def edit_profile(user_id: int):
    if 'username' not in session:
        abort(401)

    user = users.query.get(user_id)


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
