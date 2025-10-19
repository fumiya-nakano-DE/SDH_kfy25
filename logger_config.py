import logging
from logging.handlers import RotatingFileHandler
import sys
from datetime import datetime


def setup_logger():
    logger = logging.getLogger("ritsudo_server")
    logger.setLevel(logging.DEBUG)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    console_formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(filename)s:%(lineno)d - %(funcName)s()] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler.setFormatter(console_formatter)

    file_handler = RotatingFileHandler(
        "ritsudo_server.log", maxBytes=10 * 1024 * 1024, backupCount=100
    )
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(filename)s:%(lineno)d - %(funcName)s()] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    class StreamToLogger:
        def __init__(self, logger, level):
            self.logger = logger
            self.level = level
            self.linebuf = ""

        def write(self, buf):
            for line in buf.rstrip().splitlines():
                self.logger.log(self.level, line)

        def flush(self):
            pass

    sys.stderr = StreamToLogger(logger, logging.ERROR)
    logger.info("stderr is redirected to ritsudo_server.log")

    return logger


logger = setup_logger()
