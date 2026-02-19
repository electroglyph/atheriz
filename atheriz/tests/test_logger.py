import logging
import os
from pathlib import Path
from atheriz.logger import logger
import pytest

def test_logger_output(tmp_path):
    """
    Verify that INFO, WARNING, and ERROR messages are correctly handled by the logger.
    We test this by adding a temporary FileHandler to simulate the server's log file.
    """
    log_file = tmp_path / "server.log"
    
    # Add a temporary file handler
    file_handler = logging.FileHandler(log_file)
    formatter = logging.Formatter("%(levelname)s: %(name)s: %(message)s")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    try:
        # Generate log messages
        test_info = "This is a test info message"
        test_warn = "This is a test warning message"
        test_error = "This is a test error message"
        
        logger.info(test_info)
        logger.warning(test_warn)
        logger.error(test_error)
        
        # Ensure all messages are flushed
        file_handler.flush()
        
        # Read and verify content
        content = log_file.read_text()
        
        assert f"INFO: atheriz: {test_info}" in content
        assert f"WARNING: atheriz: {test_warn}" in content
        assert f"ERROR: atheriz: {test_error}" in content
        
    finally:
        # Cleanup: remove the handler to avoid affecting other tests
        logger.removeHandler(file_handler)
        file_handler.close()

def test_logger_level_filtering(tmp_path):
    """
    Verify that the logger respects levels (e.g. DEBUG messages shouldn't appear if level is INFO).
    """
    log_file = tmp_path / "level_test.log"
    file_handler = logging.FileHandler(log_file)
    logger.addHandler(file_handler)
    
    # Save original level
    original_level = logger.level
    
    try:
        logger.setLevel(logging.INFO)
        
        logger.debug("This debug message should NOT appear")
        logger.info("This info message SHOULD appear")
        
        file_handler.flush()
        content = log_file.read_text()
        
        assert "This info message SHOULD appear" in content
        assert "This debug message should NOT appear" not in content
        
    finally:
        logger.setLevel(original_level)
        logger.removeHandler(file_handler)
        file_handler.close()

def test_debug_level_capture(tmp_path):
    """
    Verify that when LOG_LEVEL is set to "debug", logger.debug() messages are captured.
    """
    import atheriz.settings as settings
    from importlib import reload
    import atheriz.logger as atheriz_logger
    
    log_file = tmp_path / "debug_test.log"
    file_handler = logging.FileHandler(log_file)
    formatter = logging.Formatter("%(levelname)s: %(name)s: %(message)s")
    file_handler.setFormatter(formatter)
    atheriz_logger.logger.addHandler(file_handler)
    
    # Save original settings/level
    original_level_setting = settings.LOG_LEVEL
    original_logger_level = atheriz_logger.logger.level
    
    try:
        # Simulate setting LOG_LEVEL to "debug" and applying it via the new helper
        settings.LOG_LEVEL = "debug"
        atheriz_logger.apply_settings()
        atheriz_logger._setup_logger()
            
        atheriz_logger.logger.debug("Test DEBUG message")
        
        file_handler.flush()
        content = log_file.read_text()
        
        assert "DEBUG: atheriz: Test DEBUG message" in content
        
    finally:
        # Restore
        settings.LOG_LEVEL = original_level_setting
        atheriz_logger.logger.setLevel(original_logger_level)
        atheriz_logger.logger.removeHandler(file_handler)
        file_handler.close()
