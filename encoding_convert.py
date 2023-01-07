# 获取文件编码
import chardet


def get_encoding(file):
    with open(file, 'rb') as f:
        return chardet.detect(f.read())['encoding']


# 将其他编码的文件转换为UTF-8编码
def other2utf8(file, encoding):
    with open(file, 'r', encoding=encoding) as f:
        lines = f.readlines()
    with open(file, 'w', encoding='utf-8') as f:
        f.writelines(lines)


# 获取文件编码，如果为utf-8编码，就转换为gbk编码
def convert_encoding(file):
    encoding = get_encoding(file)
    if encoding != 'utf-8':
        other2utf8(file, encoding)
