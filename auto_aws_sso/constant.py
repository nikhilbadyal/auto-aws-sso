import os

project_selenium_dir = ".cache/auto-aws-sso/user_data"
default_profile = os.getenv("AWS_DEFAULT_PROFILE") or os.getenv("AWS_PROFILE") or "default"
