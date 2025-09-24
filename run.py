from app import app
from flaskwebgui import FlaskUI

if __name__ == "__main__":
    # This runs Flask inside a desktop window
    ui = FlaskUI(app, width=1200, height=800)
    ui.run()
