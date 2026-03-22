from logging import DEBUG, INFO, WARNING, basicConfig, getLogger

# Configure logger
basicConfig(level=INFO, format="%(asctime)s %(levelname)s: %(message)s")

# Silence noisy libraries
getLogger("httpx").setLevel(WARNING)
