"""Entry point: python run.py"""
import os

from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(
        host=os.getenv("FLASK_RUN_HOST", "127.0.0.1"),
        port=int(os.getenv("FLASK_RUN_PORT", "5000")),
        debug=app.config["DEBUG"],
        # The reloader would load the embedding model and Chroma client twice.
        use_reloader=False,
    )
