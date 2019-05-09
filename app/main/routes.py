from datetime import datetime
from flask import render_template, flash, redirect, url_for, request, g, jsonify, current_app
from flask_login import current_user, login_required
from flask_babel import _, get_locale
from guess_language import guess_language
from app import db
from app.main.forms import EditProfileForm, PostForm
from app.models import User, Post
from app.translate import translate
from app.main import bp


# @ symbol indicates what is known as a decorator (i.e. @bp.route, or @login_required):
#   - A decorator modifies the FN that follows it
#   - A common pattern with decorators is to use them to register FNs as callbacks for certain events.

# The @before_request decorator from Flask registers the decorated FN to be executed before the view FN
@bp.before_request
def before_request():

    # The get_locale() function from Flask-Babel returns a locale object, but I just want to have the language code,
    # which can be obtained by converting the object to a string
    g.locale = str(get_locale())

    # Check that the user is logged-in
    if current_user.is_authenticated:
        # If user is logged in than update the last_seen field to the current time (remember only happens on page load)
        current_user.last_seen = datetime.utcnow()
        # Commit the db session, so change made above is written to the db (db.session.add is w/in user_loader FN)
        db.session.commit()


# the @bp.route decorator creates an association between the URL given as an argument and the FN
# In this ex. there are three decorators (two of which
#   1. Associates the URL "/" to this FN.
#   2. Associates the URL "/index" to this FN.
#   3. Forces the user to be logged-in to be able to access a certain FN
#
# The first two decorators mean that when a browser requests either of these two URLs, Flask is going to invoke this FN
# and pass the return value of it back to the browser as a response. They also include the methods argument indicating
# that this particular function accepts GET and POST requests
#
# The third decorator checks within the User object associated with the browser and looks for the is_authenticated BOOL
#   - If set to TRUE than the user is allowed to see the page
#   - If set to FALSE than the user is redirected to the login page (org. page stored in NEXT to allow acc. redirect)
@bp.route('/', methods=['GET', 'POST'])
@bp.route('/index', methods=['GET', 'POST'])
@login_required
def index():
    form = PostForm()

    # This if statement handles the situation in which the user wishes to submit a new blog post (adding it the db)
    if form.validate_on_submit():

        # Each time a post is submitted, I run the text through the guess_language function to try to determine the
        # language. If the language comes back as unknown or if I get an unexpectedly long result, I play it safe and
        #  save an empty string to the database. I'm going to adopt the convention that any post that have the
        # language set to an empty string is assumed to have an unknown language.
        language = guess_language(form.post.data)
        if language == 'UNKNOWN' or len(language) > 5:
            language = ''

        post = Post(body=form.post.data, author=current_user, language=language)
        db.session.add(post)
        db.session.commit()

        # Display the success message and redirect/refresh to home page so user can see updated page with post
        flash('Your post is now live!')

        # It is a standard practice to respond to a POST request generated by a web form submission with a redirect.
        # This helps mitigate an annoyance with how the refresh command is implemented in web browsers. All the web
        # browser does when you hit the refresh key is to re-issue the last request. If a POST request with a form
        # submission returns a regular response, then a refresh will re-submit the form. Because this is unexpected,
        # the browser is going to ask the user to confirm the duplicate submission, but most users will not
        # understand what the browser is asking them. But if a POST request is answered with a redirect, the browser
        # is now instructed to send a GET request to grab the page indicated in the redirect, so now the last request
        # is not a POST request anymore, and the refresh command works in a more predictable way.
        #
        # This simple trick is called the Post/Redirect/Get pattern. It avoids inserting duplicate posts when a user
        # inadvertently refreshes the page after submitting a web form.
        return redirect(url_for('main.index'))

    # Get all posts from the current user and pass it as an argument to the html template view to be displayed
    #
    # The followed_posts method of the User class returns a SQLAlchemy query object that is configured to grab the
    # posts the user is interested in from the database. Calling all() on this query triggers its execution,
    # with the return value being a list with all the results.
    #
    # I end up with a structure similar to --> {'author':{'username': 'John'}, 'body': 'This is the body text'}
    #
    # Note: We are paginating the posts and to do so we must take the current page from the query string in the URL
    #       Additionally we must call the paginate method which can be called on any query object from Flask-SQLAlchemy
    #         It takes three arguments:
    #             1. The page number, starting from 1
    #             2. The number of items per page
    #             3. An error flag for bad queries (if true will return 404... if false it will return an empty list)
    #       The return value from paginate is a Pagination object.
    #       The items attribute of this object contains the list of items in the requested page

    page = request.args.get('page', 1, type=int)  # Arg 1: Query Variable, Arg 2: Default Value, Arg 3: D-TYPE (INT)
    posts = current_user.followed_posts().paginate(page, current_app.config['POSTS_PER_PAGE'], False)

    # Further Notes on PAGINATE class from SQL-Alchemy
    # An object constructed from the paginate class (such as 'page' constructed above) has many useful attributes in
    # addition to the items attribute. Four other useful attributes are shown below:
    #
    #      1.  has_next  :  True if there is at least one more page after the current one
    #      2.  has_prev  :  True if there is at least one more page before the current one
    #      3.  next_num  :  page number for the next page
    #      4.  prev_num  :  page number for the previous page
    #
    # With these four elements, I can generate next and prev page links and pass them to the templates for rendering:
    # The next_num and prev_num will work in concern with url_for to generate potential next/prev page urls
    #
    # One interesting aspect of the url_for() function is that you can add any keyword args to it, and if the names of
    # those args are not referenced in the URL directly, then Flask will include them in the URL as query arguments.
    #

    next_url = url_for('main.index', page=posts.next_num) if posts.has_next else None  # Conditional based on has_next
    prev_url = url_for('main.index', page=posts.prev_num) if posts.has_prev else None  # Conditional based on has_prev

    # render_template is a templating engine (Jinja2)
    #   - Just provide the name of the template and the variables
    #   - This will load the template you indicated and will pass the variables to the template as keyword arguments
    #   - In this case we are calling index.html & passing the string for title and array containing the posts
    return render_template('index.html',
                           title='Home Page', posts=posts.items, form=form, next_url=next_url, prev_url=prev_url)


# This is the FN for viewing a user profile and is associated with a custom URL dependant upon the user (/user/<>)
# Login is obv. required for this page to be accessed
@bp.route('/user/<username>')
@login_required
def user(username):
    # Return the matching user object resulting from a db query using the html passed username variable (first or 404)
    user = User.query.filter_by(username=username).first_or_404()

    # Get all posts from the current user and pass it as an argument to the html template view to be displayed
    #
    # The followed_posts method of the User class returns a SQLAlchemy query object that is configured to grab the
    # posts the user is interested in from the database. Calling all() on this query triggers its execution,
    # with the return value being a list with all the results.
    #
    # For more information on paginate and it's various attributes see the index route at the top of this file
    #
    # To get the list of posts from the user, I take advantage of the fact that the user.posts relationship is a
    # query that is already set up by SQLAlchemy as a result of the db.relationship() definition in the User model.
    #
    # Take this query and add an order_by() clause so that I get the newest posts first, and then do the pagination
    # exactly like I did for the posts in the index and explore pages. Note that the pagination links that are
    # generated by the url_for() function need the extra username argument (point back at the user profile page)
    page = request.args.get('page', 1, type=int)
    posts = user.posts.order_by(Post.timestamp.desc()).paginate(page, current_app.config['POSTS_PER_PAGE'], False)

    next_url = url_for('main.user', username=user.username, page=posts.next_num) if posts.has_next else None
    prev_url = url_for('main.user', username=user.username, page=posts.prev_num) if posts.has_prev else None

    # Return html (if not 404'd) for user.html passing the queried user object and the fake posts
    return render_template('user.html', user=user, posts=posts.items, next_url=next_url, prev_url=prev_url)


# This is the FN for editing a profile and is associated with the /edit_profile address
# This function accepts both HTTP GET & POST requests
# This page requires the user to be authenticated to be accessed
@bp.route('/edit_profile', methods=['GET', 'POST'])
@login_required
def edit_profile():
    # Above in the imports the EditProfileForm() class was imported and we are instantiating an object (form)
    form = EditProfileForm(current_user.username)  # We use the current_user.username to pass default text in form

    # Form validation as explained above
    if form.validate_on_submit():
        # Update the current_user username & about_me and commit the changes to the database and display confirmation
        current_user.username = form.username.data
        current_user.email = form.email.data
        current_user.about_me = form.about_me.data

        db.session.commit()
        flash('Your changes have been saved.')
        # Redirect to the edit profile page (passing the current_user) so that the user can see updated default fields
        return redirect(url_for('main.edit_profile'))

    # If form validation fails (but it is a GET request)
    elif request.method == 'GET':
        # Set the default form data (text that appears) to be the users current username and about me information
        form.username.data = current_user.username
        form.email.data = current_user.email
        form.about_me.data = current_user.about_me

    # If form validation fails (but it is a POST request) than re-render the edit_profile html passing approp. args
    return render_template('edit_profile.html', title='Edit Profile', form=form)


# The two FNs below could be combined and we pass some kind of action type (follow/unfollow) as an arg from URL
# This is the FN for following a user and is associated with the /follow/<username> path
# This page requires the user to be authenticated to be accessed
@bp.route('/follow/<username>')
@login_required
def follow(username):
    # set the user variable to be the first returned match for the passed user (to be followed) arg
    user = User.query.filter_by(username=username).first()

    # If we can't find the user than display an error message and redirect to the home page
    if user is None:
        flash('User {} not found.'.format(username))
        return redirect(url_for('main.index'))

    # If we find that the desired user is actually ourselves than flash an error message and redirect to our user page
    if user == current_user:
        flash('You cannot follow yourself!')
        return redirect(url_for('main.user', username=username))

    # Call the follow module to update the database field and then commit the changes to memory
    current_user.follow(user)
    db.session.commit()

    # Display a success message and redirect the user to their appropriate user page
    flash('You are following {}!'.format(username))
    return redirect(url_for('main.user', username=username))


# This is the FN for un-following a user and is associated with the /unfollow/<username> path
# This page requires the user to be authenticated to be accessed
@bp.route('/unfollow/<username>')
@login_required
def unfollow(username):
    # set the user variable to be the first returned match for the passed user (to be followed) arg
    user = User.query.filter_by(username=username).first()

    # If we can't find the user than display an error message and redirect to the home page
    if user is None:
        flash('User {} not found.'.format(username))
        return redirect(url_for('main.index'))

    # If we find that the desired user is actually ourselves than flash an error message and redirect to our user page
    if user == current_user:
        flash('You cannot unfollow yourself!')
        return redirect(url_for('main.user', username=username))

    # Call the unfollow module to update the database field and then commit the changes to memory
    current_user.unfollow(user)
    db.session.commit()

    # Display a success message and redirect the user to their appropriate user page
    flash('You are not following {}.'.format(username))
    return redirect(url_for('main.user', username=username))


# This is the FN for viewing the global stream of posts from all users and is associated with the /explore path
# This page requires the user to be authenticated to be accessed
@bp.route('/explore')
@login_required
def explore():
    # Get all the posts from the post table ordered by timestamp
    # For notes on pagination see index route and/or flask documentation
    page = request.args.get('page', 1, type=int)
    posts = Post.query.order_by(Post.timestamp.desc()).paginate(page, current_app.config['POSTS_PER_PAGE'], False)
    next_url = url_for('main.explore', page=posts.next_num) if posts.has_next else None
    prev_url = url_for('main.explore', page=posts.prev_num) if posts.has_prev else None
    # Return the home page html without the form argument being passed
    # The explore page should be identical except not limited to the user and his/her followed users
    # Additionally it should not contain the ability to write a post (no form)
    return render_template('index.html', title='Explore', posts=posts.items, next_url=next_url, prev_url=prev_url)


# This is the FN called when a user wishes to translate a post from one language to another (it accepts only POST req)
# This function is associated with the /translate path and to access it the user must be authenticated
#
# An asynchronous (or Ajax) request is similar to the routes and view functions that I have created in the
# application, with the only difference that instead of returning HTML or a redirect, it just returns data,
# formatted as XML or more commonly JSON. Below you can see the translation view function, which invokes the
# Microsoft Translator API and then returns the translated text in JSON format
@bp.route('/translate', methods=['POST'])
@login_required
def translate_text():
    return jsonify({'text': translate(request.form['text'],
                                      request.form['source_language'],
                                      request.form['dest_language'])})

# There is really no absolute rule as to when to use GET or POST. Since the client will be sending data I decided to
# use a POST request, as that is similar to the requests that submit form data.
#
# The request.form attribute is a dictionary that Flask exposes with all the data that has included in the submission.
# When I worked with web forms, I did not need to look at request.form because Flask-WTF does all that work for me,
# but in this case, there is no web form, so I have to access the data directly.
#
# In this function we invoke the translate() function from the previous section passing the three arguments directly
# from the data that was submitted with the request. The result is incorporated into a single-key dictionary,
# under the key text, and the dictionary is passed as an argument to Flask's jsonify() function, which converts the
# dictionary to a JSON formatted payload.
#
# The return value from jsonify() is the HTTP response that is going to be sent back to the client.