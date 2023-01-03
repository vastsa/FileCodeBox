import chardet


# 将UTF-8编码的文件转换为GBK编码
def utf8togbk(file):
    with open(file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    with open(file, 'w', encoding='gbk') as f:
        f.writelines(lines)


# 获取文件编码
def get_encoding(file):
    with open(file, 'rb') as f:
        return chardet.detect(f.read())['encoding']


# 获取文件编码，如果为utf-8编码，就转换为gbk编码
def convert_encoding(file):
    if get_encoding(file) == 'utf-8':
        utf8togbk(file)
