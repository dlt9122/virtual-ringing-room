from flask import render_template, send_from_directory, abort, flash, redirect, url_for, session, request
from flask_login import login_user, logout_user, current_user, login_required
from app import app, towers, log, db, blog_posts
from app.models import User
from flask_login import current_user, login_user, logout_user, login_required
from app.forms import LoginForm, RegistrationForm, UserSettingsForm
from urllib.parse import urlparse
import string
import random


# redirect for static files on subdomains

@app.route('/<int:tower_id>/static/<path:path>')
@app.route('/<int:tower_id>/<decorator>/static/<path:path>')
def redirect_static(tower_id, path, decorator = None):
    return send_from_directory(app.static_folder, path)


# Serve the landing page

@app.route('/', methods=('GET', 'POST'))
def index():
    return render_template('landing_page.html')


# Create / find other towers/rooms as an observer
@app.route('/<int:tower_id>/listen')
@app.route('/<int:tower_id>/<decorator>/listen')
def observer(tower_id, decorator=None):
    try:
        towers.garbage_collection(tower_id)
        tower = towers[tower_id]
    except KeyError:
        log('Bad tower_id')
        abort(404)
    return render_template('ringing_room.html',
                           tower=tower,
                           listen_link=True)

# Helper function to generate a random string for use as a unique user_id
def assign_user_id():
    letters = string.ascii_lowercase
    return ''.join(random.choice(letters) for i in range(8))

# Create / find other towers/rooms
@app.route('/<int:tower_id>')
@app.route('/<int:tower_id>/<decorator>')
def tower(tower_id, decorator=None):
    try:
        towers.garbage_collection(tower_id)
        tower = towers[tower_id]
    except KeyError:
        log('Bad tower_id')
        abort(404)
    if current_user.is_anonymous:
        # Not logged in.
        session['user_name'] = ''
        name_available = True
    else:
        # User is logged in. Their globally-unique user_name works as both id and display
        session['user_id'] = current_user.username
        session['user_name'] = current_user.username
        name_available = True # it's globally unique
                         
    # Pass in both the tower and the user_name
    return render_template('ringing_room.html',
                            tower = tower,
                            user_name = session['user_name'],
                            name_available = name_available,
                            listen_link = False)


#  Serve the static pages

@app.route('/about')
def about():
    return render_template('about.html')


@app.route('/help')
def help():
    return render_template('help.html')


@app.route('/contact')
def contact():
    return render_template('contact.html')


@app.route('/donate')
def donate():
    return render_template('donate.html')

@app.route('/authenticate')
def authenticate():
    login_form = LoginForm()
    registration_form = RegistrationForm()
    next = request.args.get('next')
    return render_template('authenticate.html', 
                           login_form=login_form,
                           registration_form=registration_form,
                           next=next)

@app.route('/login', methods=['POST'])
def login():
    login_form = LoginForm()
    registration_form = RegistrationForm()
    next = request.args.get('next')
    if urlparse(next).netloc != '':
        # All our next redirections will be relative; if there's a netloc, that means
        # someone has tampered with the next arg and we should throw it out
        next = ''
    if login_form.validate_on_submit():

        user = User.query.filter_by(email=login_form.username.data).first() or \
               User.query.filter_by(username=login_form.username.data).first()
        if user is None or not user.check_password(login_form.password.data):
            raise ValidationError('Incorrect username or password.')
            return redirect(url_for('authenticate'))

        login_user(user, remember=login_form.remember_me.data)

        return redirect(next or url_for('index'))
    return render_template('authenticate.html', 
                           login_form=login_form,
                           registration_form=registration_form,
                           next=next)


@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('index'))
    
@app.route('/register', methods=['POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    next = request.args.get('next')
    login_form = LoginForm()
    registration_form = RegistrationForm()
    if registration_form.validate_on_submit():
        user = User(username=registration_form.username.data, email=registration_form.email.data)
        user.set_password(registration_form.password.data)
        db.session.add(user)
        db.session.commit()

        login_user(user)

        return redirect(url_for('index'))
    return render_template('authenticate.html', 
                           login_form=login_form,
                           registration_form=registration_form,
                           next=next)

@app.route('/settings', methods=['GET','POST'])
@login_required
def user_settings():
    form = UserSettingsForm()
    if form.validate_on_submit() and current_user.check_password(form.password.data):
        if form.new_password.data:
            current_user.set_password(form.new_password.data)
            flash('Password updated.')
        if form.new_email.data:
            current_user.email = form.new_email.data
        if form.new_username.data:
            current_user.username = form.new_username.data
            flash('Username updated.')
        db.session.commit()
    return render_template('user_settings.html', form=form)



# Blog


# Helper function: Get a list of tags
# If you give it a post, it gets the tags for just that post, else it gets all the tags for all posts
def get_blog_tags(post=None):
    if post and 'tags' in post.meta:
        return (tag.strip() for tag in post.meta.get('tags').split(','))
    return set(tag.strip() for p in blog_posts \
               if 'tags' in p.meta and 'published' in p.meta \
               for tag in p.meta.get('tags').split(','))

# Helper function:
# Get the n most recent post titles & dates, for use in the sidebar
def get_recent_posts(n=10):
    return (p for p in sorted(blog_posts, 
                             key = lambda x: x.meta.get('published'),
                             reverse=True)[:n]
            )

# The default "front page" view, with recent articles & snippets.
@app.route('/blog/')
def blog():

    # First, assemble a list of all published posts
    post_list = (p for p in blog_posts if 'published' in p.meta)

    # take them in reverse chronological order
    latest = sorted(post_list, reverse = True, key = lambda p: p.meta['published'])

    # Figure out pagination
    posts_per_page = 5
    pagination = int(request.args.get('page') or 1) # Get the ?page= argument or just default to 1
    start_of_range = (pagination-1)*posts_per_page 
    end_of_range = pagination*posts_per_page

    return render_template('blog_front.html', 
                           posts=latest[start_of_range:end_of_range],
                           recent_posts=get_recent_posts(),
                           tags=get_blog_tags(),
                           title='Blog')


# Single post view
@app.route('/blog/<string:post>')
def blog_post(post):
    p = blog_posts.get(post)
    return render_template('blog_post.html',
                           post=p,
                           recent_posts=get_recent_posts(),
                           tags=get_blog_tags(),
                           title=p.meta.get('title'))

# Index view
@app.route('/blog/index')
def blog_index():
    posts = sorted((p for p in blog_posts if 'published' in p.meta),
               key=lambda x: x.meta.get('published'), reverse=True)
    tag = request.args.get('tag')
    if tag:
        posts = (p for p in posts if 'tags' in p.meta and tag in get_blog_tags(p))
    return render_template('blog_index.html',
                           posts=posts,
                           recent_posts=get_recent_posts(),
                           tags=get_blog_tags(),
                           title=tag or 'Index')
                           


# Index view



# This is necessary to serve images correctly
@app.route('/blog/images/<path:path>')
def redirect_blog_media(path):
    return send_from_directory('blog/images/', path)
