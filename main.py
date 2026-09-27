# Importing flask module
from flask import Flask, render_template
# Flask constructor takes the name of
# current module (__name__) as argument
app = Flask(__name__)
# The route() function of the Flask class is a decorator,
# which tells the application which URL should call
# the associated function home() and run the code written in
# index.html file
@app.route('/')
def home():
    return render_template('index.html')
# Flask's render_template() helper function is used to serve an HTML template as the response
# so home page will render the form produced by index.html template
# main driver function
if __name__ == "__main__":
# run() method of Flask class runs the application
# on the local development server.
    app.run()