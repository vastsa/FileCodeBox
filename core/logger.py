import logging
import sys


def setup_logger():
    # 创建logger对象
    _logger = logging.getLogger('FileCodeBox')
    _logger.setLevel(logging.INFO)

    # 创建控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)

    # 设置日志格式
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(formatter)

    # 添加处理器到logger
    _logger.addHandler(console_handler)

    return _logger


# 创建全局logger实例
logger = setup_logger()
