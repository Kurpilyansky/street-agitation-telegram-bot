import re


def escape_markdown(text):
    """Helper function to escape telegram markup symbols"""
    escape_chars = '\*_`\['
    return re.sub(r'([%s])' % escape_chars, r'\\\1', text or "")


def chunks(arr, chunk_len):
    return [arr[i:i + chunk_len] for i in range(0, len(arr), chunk_len)]
