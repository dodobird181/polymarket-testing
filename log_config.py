from logging import INFO, WARNING, basicConfig, getLogger

# Configure logger
basicConfig(level=INFO, format="%(message)s")

# Silence noisy libraries
getLogger("httpx").setLevel(WARNING)
