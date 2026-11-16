"""Record a reproducible local UI demonstration without external services."""
import os
import runpy

os.environ['RECORD_DEMO']='1'
runpy.run_module('scripts.browser_smoke',run_name='__main__')
