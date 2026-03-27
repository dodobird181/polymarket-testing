from pathlib import Path
from sys import path as systempath

systempath.insert(0, str(Path(__file__).parents[2]))

from streamlit import Page, navigation, set_page_config

"""
Entrypoint for the streamlit dashboard app.
"""

if __name__ == "__main__":
    set_page_config(layout="wide")
    pages = [
        Page(Path("src/streamlit/view_strategies.py").absolute(), title="Home"),
        Page(Path("src/streamlit/new_strategy.py").absolute(), title="Add Strategy"),
    ]
    page = navigation(pages)
    page.run()
