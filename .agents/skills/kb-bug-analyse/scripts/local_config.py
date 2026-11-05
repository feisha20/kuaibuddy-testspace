"""只从当前工作区的本机文件加载诊断配置，不输出配置值。"""
import os
from pathlib import Path
import shlex


def load_local_config():
    path = Path(__file__).resolve().parents[4] / '.env.observability'
    if not path.exists():
        return
    for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
        text = line.strip()
        if not text or text.startswith('#'):
            continue
        if '=' not in text:
            raise ValueError(f'本机观测配置第 {number} 行格式不正确')
        key, raw = text.split('=', 1)
        key = key.strip()
        if not key.startswith(('KB_LANGFUSE_', 'KB_ELK_')):
            continue
        try:
            values = shlex.split(raw, comments=True)
        except ValueError:
            raise ValueError(f'本机观测配置第 {number} 行格式不正确') from None
        if len(values) > 1:
            raise ValueError(f'本机观测配置第 {number} 行格式不正确')
        os.environ.setdefault(key, values[0] if values else '')
