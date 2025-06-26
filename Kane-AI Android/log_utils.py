import logging
import logging.config
import sys
import os
from logging import LoggerAdapter
from pythonjsonlogger import jsonlogger
from logging.handlers import RotatingFileHandler


stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setLevel(logging.INFO)

MAGIC_STRING = "lAmd@R0ck5"

if sys.platform.startswith('linux'):
    log_file_path = '/home/ltuser/foreman/kane-hyex-test.log'
elif sys.platform.startswith('win'):
    log_file_path = "/foreman/kane-hyex-test.log"
else:
    log_file_path = "/Users/ltuser/foreman/kane-hyex-test.log"
var_log_handler = RotatingFileHandler(log_file_path, maxBytes=5_000_000, backupCount=5)
_CONTEXT = {
    "test_id":     os.getenv("TEST_ID", ""),     
    "commit_id":   os.getenv("COMMIT_ID", ""),   
    "org_id":      os.getenv("ORG_ID", "0"),     
    "test_run_id": os.getenv("TEST_RUN_ID", ""), 
}
class ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        for k, v in _CONTEXT.items():
            setattr(record, k, v)
        return True                  # ‑‑> keep the record
log_fmt = (
    "%(asctime)s %(name)s %(levelname)s %(message)s "
    "%(test_id)s %(commit_id)s %(org_id)s %(test_run_id)s"
)
json_formatter = jsonlogger.JsonFormatter(log_fmt)


var_log_handler.setFormatter(json_formatter)
var_log_handler.addFilter(ContextFilter())
# Get the main logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.addHandler(stream_handler)
logger.addHandler(var_log_handler)

# Dictionary to store adapters based on test_id
adapters = {}


class StreamToLogger:
    def __init__(self, logger, log_level):
        self.logger = logger
        self.log_level = log_level
        self.linebuf = ''

    def write(self, buf):
        self.linebuf += buf
        while '\n' in self.linebuf:
            line, self.linebuf = self.linebuf.split('\n', 1)
            self.logger.log(self.log_level, line.rstrip())

    def flush(self):
        if self.linebuf:
            self.logger.log(self.log_level, self.linebuf.rstrip())
            self.linebuf = ''

    def isatty(self):
        return False

class AutohealInfo:
    def __init__(self, org_id = "", test_id = "", test_version = "", ktm_email = "", username = "", execution = None, authoring= None):
        self.event_type = "autoheal"
        self.meta = {
            "org_id": org_id,
            "test_id": test_id,
            "test_version": test_version,
            "ktm_email": ktm_email,
            "username": username
        }
        self.execution = execution
        self.authoring = authoring
        self.magic_string = MAGIC_STRING

    def to_dict(self):
        return {
            "event_type": self.event_type,
            "meta": self.meta,
            "execution": self.execution,
            "authoring": self.authoring,
            "magic_string": self.magic_string
        }
    
def log_autoheal_selector(org_id = "", test_id = "", test_version = "", ktm_email = "", username = "", execution = None, authoring= None):
    autoheal_info = AutohealInfo(org_id, test_id, test_version, ktm_email, username, execution, authoring)
    logger.info(autoheal_info.to_dict())

stdout_logger = logging.getLogger('STDOUT')
stdout_logger.setLevel(logging.INFO)
stdout_logger.addHandler(var_log_handler)
stdout_logger.addHandler(stream_handler)

stderr_logger = logging.getLogger('STDERR')
stderr_logger.setLevel(logging.ERROR)
stderr_logger.addHandler(var_log_handler)
stderr_logger.addHandler(stream_handler)

# Redirect stdout and stderr to the logger
sl_out = StreamToLogger(stdout_logger, logging.INFO)
sys.stdout = sl_out

sl_err = StreamToLogger(stderr_logger, logging.ERROR)
sys.stderr = sl_err
