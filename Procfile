run_high_buy_30_stoploss: PYTHONUNBUFFERED=1 poetry run python live_monitor.py strategy_logs/run_high_buy_30_stoploss.jsonl strategy_files/run_high_buy_30_stoploss.py
plot_watcher: PYTHONUNBUFFERED=1 poetry run python plot_watcher.py strategy_logs
procfile_regenerator: PYTHONUNBUFFERED=1 poetry run python procfile_regenerator.py
streamlit_app: PYTHONUNBUFFERED=1 poetry run streamlit run app.py --server.headless true
