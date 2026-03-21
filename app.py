# app.py
import streamlit as st

st.set_page_config(layout="wide")

pg = st.navigation(
    [
        st.Page("pages/view_strategies.py", title="Home"),
        st.Page("pages/new_strategy.py", title="Add Strategy"),
    ]
)
pg.run()
