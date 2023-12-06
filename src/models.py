from flask_sqlalchemy import SQLAlchemy
from itsdangerous.url_safe import URLSafeTimedSerializer as Serializer
from sqlalchemy import CheckConstraint, text
from sqlalchemy.sql import func
from flask_login import UserMixin
import os
# from src import app

db = SQLAlchemy()

#users table
class users(db.Model, UserMixin):  
    user_id = db.Column(db.Integer, primary_key = True)

    first_name = db.Column(db.String(255), nullable = False)

    last_name = db.Column(db.String(255), nullable = False)

    username = db.Column(db.String(255), nullable = False, unique = True)

    email = db.Column(db.String(255), nullable = False, unique = True)

    password = db.Column(db.String(255), nullable = False)

    role = db.Column(db.String(255), nullable = True)

    registration_date = db.Column(db.DateTime, nullable=True, default=func.now())

    last_login = db.Column(db.DateTime, nullable=True, default=func.now())

    profile_picture = db.Column(db.String(255), nullable = True)


    def __init__(self, first_name: str, last_name: str, username: str, email:str , password: str, profile_picture: str):
        self.first_name = first_name
        self.last_name = last_name
        self.username = username
        self.email = email
        self.password = password
        self.profile_picture = profile_picture

    def get_reset_token(self, expires_sec=900):
        # must have app_secret key variable in env file
        app_secret_key = os.getenv('APP_SECRET_KEY')
        if app_secret_key:
            s = Serializer(app_secret_key)
            token = s.dumps({'user_id' : self.user_id})
            if isinstance(token, bytes):
                token = token.decode()
            return token
        return None
    
    @staticmethod
    def verify_reset_token(token):
        # must have app_secret key variable in env file
        app_secret_key = os.getenv('APP_SECRET_KEY')
        if app_secret_key:
            s = Serializer(app_secret_key)
            try:
                user_id = s.loads(token)['user_id']
            except:
                return None
            return users.query.get(user_id)
        return None

    def __repr__(self) -> str:
        return f'users({self.first_name}, {self.last_name})'
    
    def get_id(self):
        return str(self.user_id)


#live posts table
class live_posts(db.Model):
    post_id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.String(255), nullable=False)
    date = db.Column(db.DateTime(timezone=True), nullable = True, default = func.now())
    
    # Foreign key referencing the users table
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    
    # Establish the relationship with the User model
    user = db.relationship('users', backref=db.backref('live_posts', lazy=True))

    def __init__(self, content: str, user_id:int):
        self.content = content
        self.user_id = user_id

    def __repr__(self) -> str:
        return f'live_posts({self.post_id}, {self.content}, {self.user_id})'


#post
class Post(db.Model):
    # PRIMARY KEY post_id SERIAL,
    post_id = db.Column(db.Integer, primary_key = True)

    # title VARCHAR(255) NOT NULL,
    title = db.Column(db.String(255), nullable = False)

    # content TEXT,
    content = db.Column(db.Text, nullable = True)

    # date_posted TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    date_posted = db.Column(db.DateTime, nullable = False, server_default=text('NOW()'))

    # likes INT NOT NULL DEFAULT 0,
    likes = db.Column(db.Integer, nullable = True, default = 0)

    # image BLOB,
    file_upload = db.Column(db.String(255), nullable = True, default = 'default.jpg')

    # user_id INT,
    # FOREIGN KEY (user_id) references users(user_id)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable = False)

    # post creator
    creator = db.relationship('users', backref='creator', foreign_keys=[user_id])

    liked_by = db.relationship('users', secondary='likes', backref='liked_posts')

    # each post's comments
    comments = db.relationship('Comment', backref='comments')

    # def __init__(self, title: str, content: str):
    #     self.title = title
    #     self.content = content

    def __init__(self, user_id: int, title: str, content: str):
        self.user_id = user_id
        self.title = title
        self.content = content

    def __repr__(self) -> str:
        return f'Post #{self.post_id} by {self.user_id})'

#post comments
class Comment(db.Model):
    # PRIMARY KEY comment_id SERIAL,
    comment_id = db.Column(db.Integer, primary_key = True)

    # content TEXT,
    content = db.Column(db.Text, nullable = True)

    # date_posted TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    date_posted = db.Column(db.DateTime, nullable = False, server_default=text('NOW()'))

    # likes INT NOT NULL DEFAULT 0,
    likes = db.Column(db.Integer, nullable = True, default = 0)

    # user_id INT,
    # FOREIGN KEY (user_id) references users(user_id)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable = False)

    # post_id INT,
    # FOREIGN KEY (post_id) references posts(post_id)
    post_id = db.Column(db.Integer, db.ForeignKey('post.post_id'), nullable = False)

    # each user's comments
    comment_creator = db.relationship('users', backref='comment_creator', foreign_keys=[user_id])

    def __init__(self, user_id: int, post_id: int, content: str):
        self.user_id = user_id
        self.post_id = post_id
        self.content = content

    def __repr__(self) -> str:
        return f'{self.content}'
    
likes = db.Table(
    'likes',
    db.Column('user_id', db.Integer, db.ForeignKey('users.user_id'), primary_key=True),
    db.Column('post_id', db.Integer, db.ForeignKey('post.post_id'), primary_key=True)
)

# friendships table
# class friendships(db.Model):
#     friendship_id = db.Column(db.Integer, primary_key = True)

#     user1_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable = False)

#     user2_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable = False)

#     user1 = db.relationship('User', foreign_keys=[user1_id])
#     user2 = db.relationship('User', foreign_keys=[user2_id])

#     __table_args__ = (CheckConstraint('user1_id < user2_id'))